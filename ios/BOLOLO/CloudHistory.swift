import Foundation
import SwiftData

enum CloudHistory {
    static let deviceTimeZone = TimeZone(identifier: "Asia/Shanghai")!
    static let pageSize = 100

    static func fetch(api: BololoAPI, device: P50Device, days: Int = 30) async throws -> [CloudPreparation] {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = deviceTimeZone
        let startOfToday = calendar.startOfDay(for: Date())
        guard let from = calendar.date(byAdding: .day, value: -max(1, days), to: startOfToday),
              let end = calendar.date(byAdding: .day, value: 1, to: startOfToday) else {
            throw CloudError.invalidResponse
        }

        let startMS = Int64(from.timeIntervalSince1970 * 1000)
        let endMS = Int64(end.timeIntervalSince1970 * 1000)
        var results: [CloudPreparation] = []
        var known = Set<String>()

        // The server's total/pages have been observed to be inconsistent.
        // Continue until a short/empty page, with a hard safety cap.
        for page in 1...50 {
            let records = try await api.historyPage(
                device: device, startMS: startMS, endMS: endMS,
                page: page, size: pageSize
            )
            var newThisPage = 0
            for raw in records {
                guard let prep = decode(raw), known.insert(prep.id).inserted else { continue }
                results.append(prep)
                newThisPage += 1
            }
            if records.count < pageSize || newThisPage == 0 { break }
        }
        return results.sorted { $0.date > $1.date }
    }

    static func decode(_ raw: Any) -> CloudPreparation? {
        guard let dict = raw as? [String: Any],
              let id = ValueReader.string(dict["id"]), !id.isEmpty,
              let dateString = dict["date"] as? String,
              let date = parseDate(dateString),
              let payload = dict["data"] as? String,
              let bytes = payload.data(using: .utf8),
              let values = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let volume = ValueReader.integer(values["waterOutput"]), (1...5000).contains(volume)
        else { return nil }
        let bottle = ValueReader.string(dict["bottleName"]) ?? ""
        return CloudPreparation(id: id, date: date, bottleName: bottle, waterML: volume)
    }

    private static func parseDate(_ text: String) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = deviceTimeZone
        for pattern in ["yyyy-MM-dd HH:mm:ss.SSS", "yyyy-MM-dd HH:mm:ss"] {
            formatter.dateFormat = pattern
            if let date = formatter.date(from: text) { return date }
        }
        return nil
    }

    @MainActor
    static func merge(_ preparations: [CloudPreparation], into context: ModelContext) throws -> Int {
        let previous = try context.fetch(FetchDescriptor<FeedEntry>())
        let ids = Set(previous.compactMap(\.cloudID))
        var inserted = 0
        for item in preparations where !ids.contains(item.id) {
            context.insert(FeedEntry(
                cloudID: item.id,
                timestamp: item.date,
                bottleName: item.bottleName,
                preparedML: item.waterML,
                source: "cloud"
            ))
            inserted += 1
        }
        try context.save()
        return inserted
    }
}
