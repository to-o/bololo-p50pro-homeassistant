import SwiftUI
import SwiftData

struct SettingsView: View {
    @EnvironmentObject private var app: AppState
    @Environment(\.modelContext) private var context
    @Query private var entries: [FeedEntry]
    @State private var confirmErase = false

    var body: some View {
        Form {
            Section("P50 Pro 设备") {
                if app.devices.isEmpty {
                    Text("未发现具备有效 MAC 和 sno 的设备。请确认官方 App 已绑定或分享设备。")
                        .foregroundStyle(.secondary)
                } else {
                    Picker("当前设备", selection: Binding(
                        get: { app.selectedSno },
                        set: { new in
                            Task { await app.selectDevice(new, context: context) }
                        }
                    )) {
                        ForEach(app.devices) { device in
                            Text(device.name).tag(device.sno)
                        }
                    }
                }
                Button("重新扫描设备") {
                    Task { await app.loadDevicesAndRefresh(context: context) }
                }
            }
            Section("云端历史") {
                LabeledContent("同步方式", value: "HTTPS")
                LabeledContent("历史窗口", value: "最近 30 天")
                if let time = app.lastSync {
                    LabeledContent("上次同步", value: time.formatted(date: .abbreviated, time: .shortened))
                }
                Text("重开 App 时主动查询云端历史并按记录 ID 去重。厂商历史不包含实际喝奶量；不能保证超过查询窗口或云端保留期限的记录完整。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Section("本地隐私") {
                LabeledContent("喂养记录数", value: "\(entries.count)")
                Text("登录 Token 保存于设备 Keychain，喂养记录保存在本机 SwiftData，不上传到自建服务器。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                Button("清除本机喂养记录", role: .destructive) { confirmErase = true }
            }
            Section("账户") {
                Button("退出登录", role: .destructive) { app.signOut() }
            }
            Section {
                Text("本 App 为独立非官方客户端。厂商接口可能变更。称重仅供经过设备授权的用户进行可控测试。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("设置")
        .confirmationDialog("永久清除本机记录？", isPresented: $confirmErase) {
            Button("清除全部本机喂养记录", role: .destructive) {
                entries.forEach(context.delete)
                try? context.save()
            }
        } message: {
            Text("无法撤销。此操作不会删除 BOLOLO 云端历史，下次同步会重新导入仍可查询到的备奶记录。")
        }
    }
}
