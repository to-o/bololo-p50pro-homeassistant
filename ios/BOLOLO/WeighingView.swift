import SwiftUI

struct WeighingView: View {
    @EnvironmentObject private var app: AppState
    @StateObject private var service = WeighingService()
    @State private var askForTare = false

    var body: some View {
        Form {
            Section("实验性云端称重") {
                Label("仅在 iPhone 前台操作。纯 HTTPS 去皮与取重的闭环仍需 P50 实机验证。", systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
                Text("请确认设备不在出水、清洗或校准中。本功能不会自动出水，不会改变目标温度。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Section("状态") {
                LabeledContent("阶段", value: service.phase.rawValue)
                Text(service.detail).font(.subheadline)
                if let weight = service.weightGrams {
                    Text(String(format: "%.1f g", weight))
                        .font(.largeTitle.bold())
                }
            }
            Section("操作") {
                Button("开始去皮（托盘保持空置）") { askForTare = true }
                    .disabled(app.selectedDevice == nil || ![.idle, .completed, .failed].contains(service.phase))
                Button("奶瓶放稳，读取重量") {
                    guard let device = app.selectedDevice else { return }
                    Task { await service.measure(api: app.api, device: device) }
                }
                .disabled(service.phase != .ready)
                Button("取消 / 安全复位", role: .destructive) {
                    guard let device = app.selectedDevice else { return }
                    Task { await service.cancel(api: app.api, device: device) }
                }
                .disabled(service.phase == .idle)
            }
            Section {
                Text("仅显示当次克重，不会把结果自动写入实喝奶量。必须先实机核对历史时间戳、称重稳定性与奶瓶槽位行为，才能开放自动计算功能。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("P50 称重")
        .confirmationDialog("确定开始去皮？", isPresented: $askForTare) {
            Button("确认机器空闲，开始去皮") {
                guard let device = app.selectedDevice else { return }
                Task { await service.start(api: app.api, device: device) }
            }
        } message: {
            Text("清空托盘后开始，收到去皮确认再放稳奶瓶。此操作会向已授权设备发送控制指令。")
        }
    }
}
