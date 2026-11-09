import Foundation

enum CloudError: LocalizedError {
    case missingSession
    case invalidResponse
    case cloudCode(String)
    case httpStatus(Int)
    case missingDevice
    case noControlPermission

    var errorDescription: String? {
        switch self {
        case .missingSession: return "请先登录 BOLOLO 账户"
        case .invalidResponse: return "云端响应格式不符合预期"
        case .cloudCode(let code): return "BOLOLO 业务错误：\(code)"
        case .httpStatus(let status): return "网络请求失败：HTTP \(status)"
        case .missingDevice: return "没有找到可用的 P50 设备（需要 sno 和 MAC）"
        case .noControlPermission: return "设备未授权控制，无法执行称重"
        }
    }
}

@MainActor
final class BololoAPI {
    static let appID = "91732ca20dfd4517b164c38aac162c43"
    static let productKey = "k1mvpMY27jy000000000000000000000"
    private let endpoint = URL(string: "https://app.bololoapp3.com/")!
    private let sessionKey = "bololo-session-v1"

    struct Session: Codable {
        let token: String
        let refreshToken: String
        let createdAt: TimeInterval
        let expiredAt: TimeInterval
    }

    private(set) var session: Session?

    init() {
        if let saved = KeychainStore.read(sessionKey),
           let decoded = try? JSONDecoder().decode(Session.self, from: saved) {
            session = decoded
        }
    }

    var hasSession: Bool { session != nil }

    func logout() {
        session = nil
        KeychainStore.delete(sessionKey)
    }

    private func save(_ value: Session) {
        session = value
        if let bytes = try? JSONEncoder().encode(value) {
            KeychainStore.write(bytes, for: sessionKey)
        }
    }

    private func seconds(_ value: Any?) -> TimeInterval {
        let raw = ValueReader.double(value) ?? 0
        return raw > 100_000_000_000 ? raw / 1000 : raw
    }

    private func parseSession(_ object: Any) throws -> Session {
        guard let data = object as? [String: Any] else { throw CloudError.invalidResponse }
        let jwt = data["jwtAuthenticationDto"] as? [String: Any] ?? [:]
        guard let token = ValueReader.string(jwt["token"] ?? data["token"]), !token.isEmpty,
              let refresh = ValueReader.string(data["refresh_token"] ?? data["refreshToken"]), !refresh.isEmpty
        else { throw CloudError.invalidResponse }
        return Session(
            token: token,
            refreshToken: refresh,
            createdAt: seconds(data["created_at"] ?? data["createdAt"]),
            expiredAt: seconds(data["expired_at"] ?? data["expiredAt"])
        )
    }

    /// The response can contain HTTP 200 but a non-200 BOLOLO business code.
    private func request(
        _ path: String,
        payload: Any? = nil,
        wrapped: Bool = true,
        token: String? = nil
    ) async throws -> Any {
        guard let url = URL(string: path, relativeTo: endpoint)?.absoluteURL,
              url.scheme == "https", url.host == endpoint.host
        else { throw CloudError.invalidResponse }

        var req = URLRequest(url: url)
        req.setValue(Self.appID, forHTTPHeaderField: "X-Gizwits-Application-Id")
        req.setValue("1.0", forHTTPHeaderField: "Version")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 15
        if let token { req.setValue(token, forHTTPHeaderField: "Authorization") }
        if let payload {
            req.httpMethod = "POST"
            let body: Any = wrapped ? ["appKey": Self.appID, "data": payload, "version": "1.0"] : payload
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        let (bytes, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw CloudError.invalidResponse }
        guard http.statusCode == 200 else { throw CloudError.httpStatus(http.statusCode) }
        guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any] else {
            throw CloudError.invalidResponse
        }
        let code = ValueReader.string(object["code"]) ?? ""
        guard code == "200" else { throw CloudError.cloudCode(code.isEmpty ? "unknown" : code) }
        return object["data"] ?? NSNull()
    }

    func sendSMS(to phone: String) async throws {
        guard phone.range(of: #"^\d{5,15}$"#, options: .regularExpression) != nil else {
            throw CloudError.invalidResponse
        }
        let challenge = try await request("app/user/codeToken")
        guard let challengeToken = challenge as? String, !challengeToken.isEmpty else {
            throw CloudError.invalidResponse
        }
        _ = try await request(
            "app/user/v2/mobileCode",
            payload: ["mobile": phone, "lang": "zh", "token": challengeToken]
        )
    }

    func login(phone: String, code: String, countryCode: String = "+86") async throws {
        guard phone.range(of: #"^\d{5,15}$"#, options: .regularExpression) != nil,
              code.range(of: #"^\d{4,8}$"#, options: .regularExpression) != nil else {
            throw CloudError.invalidResponse
        }
        let data = try await request("app/user/loginByMobile", payload: [
            "mobile": phone, "code": code, "lang": "zh",
            "mobileCountryCode": countryCode, "homeName": "我的家"
        ])
        save(try parseSession(data))
    }

    private func refresh() async throws {
        guard let old = session else { throw CloudError.missingSession }
        let data = try await request(
            "app/user/refresh_token",
            payload: [
                "clientId": Self.appID,
                "refresh": true,
                "refresh_token": old.refreshToken
            ],
            token: old.token
        )
        save(try parseSession(data))
    }

    func authorized(_ path: String, payload: Any? = nil, wrapped: Bool = true) async throws -> Any {
        guard var current = session else { throw CloudError.missingSession }
        let now = Date().timeIntervalSince1970
        if current.createdAt > 0, current.expiredAt > current.createdAt,
           now >= (current.createdAt + current.expiredAt) / 2 {
            try await refresh()
            guard let fresh = session else { throw CloudError.missingSession }
            current = fresh
        }
        do {
            return try await request(path, payload: payload, wrapped: wrapped, token: current.token)
        } catch CloudError.cloudCode(let code) where code == "505" || code == "526" {
            try await refresh()
            guard let fresh = session else { throw CloudError.missingSession }
            return try await request(path, payload: payload, wrapped: wrapped, token: fresh.token)
        }
    }

    func devices() async throws -> [P50Device] {
        let owned = try await authorized("app/smartHome/v2/users/devices")
        var found = Self.readDevices(owned)
        if let shared = try? await authorized("app/smartHome/homes/shareDeviceListV2") {
            found.append(contentsOf: Self.readDevices(shared))
        }
        var seen = Set<String>()
        return found.filter { seen.insert($0.sno).inserted }
    }

    /// Shared device lists are nested differently between app versions.
    private static func readDevices(_ input: Any) -> [P50Device] {
        var result: [P50Device] = []
        func traverse(_ value: Any) {
            if let list = value as? [Any] {
                list.forEach(traverse)
            } else if let dict = value as? [String: Any] {
                if let sno = ValueReader.string(dict["sno"]), !sno.isEmpty {
                    let raw = ValueReader.string(dict["mac"] ?? dict["deviceMac"] ?? dict["macAddress"]) ?? ""
                    let mac = raw.replacingOccurrences(of: ":", with: "")
                        .replacingOccurrences(of: "-", with: "").uppercased()
                    let name = ValueReader.string(dict["deviceName"] ?? dict["name"] ?? dict["alias"]) ?? "P50 Pro"
                    if mac.range(of: #"^[0-9A-F]{12}$"#, options: .regularExpression) != nil {
                        result.append(P50Device(sno: sno, mac: mac, name: name))
                    }
                }
                dict.values.forEach(traverse)
            }
        }
        traverse(input)
        return result
    }

    func status(for device: P50Device) async throws -> DeviceStatus {
        let payload = try await authorized(
            "bololo/app/device/status/\(Self.productKey)/\(device.mac)",
            payload: [String: String]()
        )
        guard let dict = payload as? [String: Any] else { throw CloudError.invalidResponse }
        let required = ["detect_status", "self_cleaning", "quantitative_fit", "function_status", "water_output"]
        let idle = required.allSatisfy { key in
            guard let value = dict[key] else { return false }
            return ValueReader.integer(value) == 0 || ValueReader.bool(value) == false
        }
        return DeviceStatus(
            isOnline: ValueReader.bool(dict["online"] ?? dict["isOnline"]),
            temperature: ValueReader.double(dict["temp_current"]),
            targetTemperature: ValueReader.double(dict["temp_set"]),
            workState: ValueReader.string(dict["work_state"]),
            lastPreparedML: ValueReader.integer(dict["record"]),
            selectedWaterML: ValueReader.integer(dict["wateryield"]),
            bottleNumber: ValueReader.integer(dict["bottle_record"]),
            bottleTag: ValueReader.integer(dict["bottle_tag"]),
            bottleWeightDG: ValueReader.integer(dict["bottle_weight"]),
            bottleList: ValueReader.string(dict["bottle_list"]),
            statusTime: ValueReader.string(dict["status_time"]),
            idle: idle
        )
    }

    func setBottleTag(_ value: Int, device: P50Device) async throws {
        guard [0, 1, 2].contains(value) else { throw CloudError.invalidResponse }
        var data: [String: Int] = ["bottle_tag": value]
        if value == 0 { data["new_bottles"] = 0 }
        let json = try JSONSerialization.data(withJSONObject: data, options: [.sortedKeys])
        guard let string = String(data: json, encoding: .utf8) else { throw CloudError.invalidResponse }
        let result = try await authorized(
            "bololo/app/device/control/\(Self.productKey)/\(device.mac)",
            payload: string
        )
        guard result as? Bool == true else { throw CloudError.noControlPermission }
    }

    func historyPage(device: P50Device, startMS: Int64, endMS: Int64, page: Int, size: Int) async throws -> [Any] {
        guard (1...1000).contains(page), (1...200).contains(size), startMS < endMS else {
            throw CloudError.invalidResponse
        }
        let json: [String: Any] = [
            "current": page, "size": size,
            "query": ["startTime": startMS, "endTime": endMS]
        ]
        // This endpoint requires a direct JSON body, NOT the usual appKey/data/version wrapper.
        let result = try await authorized(
            "bololo/appdataSata/foam/detail/\(device.sno)/3",
            payload: json,
            wrapped: false
        )
        guard let dict = result as? [String: Any],
              let records = dict["records"] as? [Any] else {
            throw CloudError.invalidResponse
        }
        return records
    }
}
