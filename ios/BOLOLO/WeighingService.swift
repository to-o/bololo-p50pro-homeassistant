import Foundation
import SwiftUI

/// Experimental HTTP-only weighing. The repository's verified implementation
/// uses MQTT acknowledgements; this polling-only variant needs on-device validation.
@MainActor
final class WeighingService: ObservableObject {
    enum Phase: String {
        case idle = "待机"
        case taring = "正在去皮"
        case ready = "请放稳奶瓶"
        case measuring = "正在称重"
        case completed = "称重完成"
        case failed = "称重失败"
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var weightGrams: Double?
    @Published private(set) var detail = "请确认机器停止出水、清洗和校准。"
    private var originalBottleList: String?
    private var oldStatusTime: String?

    func start(api: BololoAPI, device: P50Device) async {
        guard phase == .idle || phase == .failed || phase == .completed else { return }
        phase = .taring
        weightGrams = nil
        detail = "检查设备空闲状态…"
        do {
            let before = try await api.status(for: device)
            guard before.idle, before.bottleTag == 0,
                  let original = before.bottleList else {
                throw NSError(domain: "BOLOLO", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "设备不空闲或无法核对奶瓶列表"])
            }
            originalBottleList = original
            try await api.setBottleTag(0, device: device)
            try await api.setBottleTag(1, device: device)
            for _ in 0..<8 {
                let state = try await api.status(for: device)
                if state.idle && state.bottleTag == 1 {
                    phase = .ready
                    detail = "去皮完成。请将奶瓶放稳后点“读取重量”。"
                    return
                }
                try await Task.sleep(for: .seconds(1))
            }
            throw NSError(domain: "BOLOLO", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "没有收到去皮确认"])
        } catch {
            phase = .failed
            detail = error.localizedDescription
            await restoreIfSafe(api: api, device: device)
        }
    }

    func measure(api: BololoAPI, device: P50Device) async {
        guard phase == .ready else { return }
        phase = .measuring
        do {
            let before = try await api.status(for: device)
            guard before.idle, before.bottleTag == 1,
                  before.bottleList == originalBottleList,
                  let previous = before.statusTime else {
                throw NSError(domain: "BOLOLO", code: 3,
                              userInfo: [NSLocalizedDescriptionKey: "设备状态不符合称重前要求"])
            }
            oldStatusTime = previous
            try await api.setBottleTag(2, device: device)
            for _ in 0..<10 {
                let state = try await api.status(for: device)
                if state.idle, state.bottleTag == 0,
                   state.bottleList == originalBottleList,
                   state.statusTime != oldStatusTime,
                   let weightDG = state.bottleWeightDG, (1..<65535).contains(weightDG) {
                    weightGrams = Double(weightDG) / 10.0
                    phase = .completed
                    detail = "只读到本次重量；计算实际喝奶量还需要喂前重量。"
                    return
                }
                try await Task.sleep(for: .seconds(1))
            }
            throw NSError(domain: "BOLOLO", code: 4,
                          userInfo: [NSLocalizedDescriptionKey: "没有得到可确认的新重量"])
        } catch {
            phase = .failed
            detail = error.localizedDescription
            await restoreIfSafe(api: api, device: device)
        }
    }

    func reset() {
        phase = .idle
        detail = "请确认机器停止出水、清洗和校准。"
        weightGrams = nil
        originalBottleList = nil
        oldStatusTime = nil
    }

    func cancel(api: BololoAPI, device: P50Device) async {
        await restoreIfSafe(api: api, device: device)
        reset()
    }

    private func restoreIfSafe(api: BololoAPI, device: P50Device) async {
        // Never issue a reset when the appliance is actively busy.
        guard let state = try? await api.status(for: device),
              state.idle, state.bottleTag == 1 else { return }
        try? await api.setBottleTag(0, device: device)
    }
}
