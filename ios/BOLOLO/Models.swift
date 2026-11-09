import Foundation
import SwiftData

@Model
final class FeedEntry {
    @Attribute(.unique) var id: String
    var cloudID: String?
    var timestamp: Date
    var bottleName: String
    var preparedML: Int?
    var consumedML: Int?
    var note: String
    var source: String
    var userEdited: Bool

    init(
        id: String = UUID().uuidString,
        cloudID: String? = nil,
        timestamp: Date = Date(),
        bottleName: String = "",
        preparedML: Int? = nil,
        consumedML: Int? = nil,
        note: String = "",
        source: String = "manual",
        userEdited: Bool = false
    ) {
        self.id = id
        self.cloudID = cloudID
        self.timestamp = timestamp
        self.bottleName = bottleName
        self.preparedML = preparedML
        self.consumedML = consumedML
        self.note = note
        self.source = source
        self.userEdited = userEdited
    }
}

struct P50Device: Identifiable, Hashable {
    var sno: String
    var mac: String
    var name: String
    var id: String { sno }
}

struct DeviceStatus {
    var isOnline: Bool?
    var temperature: Double?
    var targetTemperature: Double?
    var workState: String?
    var lastPreparedML: Int?
    var selectedWaterML: Int?
    var bottleNumber: Int?
    var bottleTag: Int?
    var bottleWeightDG: Int?
    var bottleList: String?
    var statusTime: String?
    var idle: Bool
    var fetchedAt: Date = Date()
}

struct CloudPreparation {
    let id: String
    let date: Date
    let bottleName: String
    let waterML: Int
}

enum ValueReader {
    static func string(_ value: Any?) -> String? {
        guard let value else { return nil }
        if let text = value as? String { return text }
        if let number = value as? NSNumber { return number.stringValue }
        return nil
    }

    static func integer(_ value: Any?) -> Int? {
        guard let value else { return nil }
        if let number = value as? NSNumber { return number.intValue }
        if let string = value as? String { return Int(string) }
        return nil
    }

    static func double(_ value: Any?) -> Double? {
        guard let value else { return nil }
        if let number = value as? NSNumber { return number.doubleValue }
        if let string = value as? String { return Double(string) }
        return nil
    }

    static func bool(_ value: Any?) -> Bool? {
        guard let value else { return nil }
        if let number = value as? NSNumber { return number.boolValue }
        if let string = value as? String {
            switch string.lowercased() {
            case "true", "1": return true
            case "false", "0": return false
            default: return nil
            }
        }
        return nil
    }
}
