import Foundation
import SwiftData
import SwiftUI

@MainActor
final class AppState: ObservableObject {
    let api = BololoAPI()
    @Published var signedIn = false
    @Published var isBusy = false
    @Published var errorMessage: String?
    @Published var devices: [P50Device] = []
    @Published var selectedSno: String = ""
    @Published var status: DeviceStatus?
    @Published var lastSync: Date?
    @Published var lastImportCount: Int = 0
    @Published var historyWarning: String?
    @Published private(set) var smsCooldown = false

    private var initialized = false
    var selectedDevice: P50Device? { devices.first { $0.sno == selectedSno } }

    func bootstrap(context: ModelContext) async {
        guard !initialized else { return }
        initialized = true
        signedIn = api.hasSession
        guard signedIn else { return }
        await loadDevicesAndRefresh(context: context)
    }

    func requestSMS(phone: String) async {
        guard !isBusy, !smsCooldown else { return }
        isBusy = true
        // Locally throttle retries regardless of the cloud result. This is not a
        // claim about BOLOLO's server-side rate limit or error code 610.
        smsCooldown = true
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(60))
            self?.smsCooldown = false
        }
        defer { isBusy = false }
        do {
            try await api.sendSMS(to: phone)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func signIn(phone: String, code: String, context: ModelContext) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await api.login(phone: phone, code: code)
            signedIn = true
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
            return
        }
        await loadDevicesAndRefresh(context: context)
    }

    func signOut() {
        api.logout()
        signedIn = false
        devices = []
        selectedSno = ""
        status = nil
        lastSync = nil
        errorMessage = nil
    }

    func loadDevicesAndRefresh(context: ModelContext) async {
        guard signedIn else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            devices = try await api.devices()
            guard !devices.isEmpty else { throw CloudError.missingDevice }
            let preferred = UserDefaults.standard.string(forKey: "selected-sno") ?? ""
            if devices.contains(where: { $0.sno == preferred }) {
                selectedSno = preferred
            } else if !devices.contains(where: { $0.sno == selectedSno }) {
                selectedSno = devices[0].sno
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
            return
        }
        await refresh(context: context)
    }

    func selectDevice(_ sno: String, context: ModelContext) async {
        guard devices.contains(where: { $0.sno == sno }) else { return }
        selectedSno = sno
        UserDefaults.standard.set(sno, forKey: "selected-sno")
        status = nil
        await refresh(context: context)
    }

    func refresh(context: ModelContext) async {
        guard signedIn, let device = selectedDevice else { return }
        // Keep the status and history operations independently recoverable.
        do {
            status = try await api.status(for: device)
            errorMessage = nil
        } catch {
            errorMessage = "设备状态：\(error.localizedDescription)"
        }
        do {
            let events = try await CloudHistory.fetch(api: api, device: device)
            lastImportCount = try CloudHistory.merge(events, into: context)
            lastSync = Date()
            historyWarning = nil
        } catch {
            historyWarning = "云端历史未同步：\(error.localizedDescription)。请稍后重试；不要将本地记录视为完整历史。"
        }
    }
}
