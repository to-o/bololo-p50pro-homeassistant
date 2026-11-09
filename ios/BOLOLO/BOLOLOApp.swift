import SwiftUI
import SwiftData

@main
struct BOLOLOApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
                .modelContainer(for: FeedEntry.self)
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var app: AppState
    @Environment(\.modelContext) private var context
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Group {
            if app.signedIn {
                MainTabs()
            } else {
                LoginView()
            }
        }
        .task { await app.bootstrap(context: context) }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active, app.signedIn {
                Task { await app.refresh(context: context) }
            }
        }
    }
}

struct MainTabs: View {
    var body: some View {
        TabView {
            NavigationStack {
                DashboardView()
            }
            .tabItem { Label("概览", systemImage: "house") }

            NavigationStack {
                HistoryView()
            }
            .tabItem { Label("喂养日记", systemImage: "list.bullet.rectangle") }

            NavigationStack {
                WeighingView()
            }
            .tabItem { Label("称重", systemImage: "scalemass") }

            NavigationStack {
                SettingsView()
            }
            .tabItem { Label("设置", systemImage: "gearshape") }
        }
    }
}

struct LoginView: View {
    @EnvironmentObject private var app: AppState
    @Environment(\.modelContext) private var context
    @State private var phone = ""
    @State private var code = ""
    @State private var requestedSMS = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Label("BOLOLO P50 Pro", systemImage: "cup.and.saucer.fill")
                        .font(.title2.bold())
                    Text("直接连接 BOLOLO 云端，不需要 OpenWrt 或家庭服务器。")
                        .foregroundStyle(.secondary)
                }
                Section("手机验证码登录") {
                    HStack {
                        Text("+86")
                        TextField("手机号", text: $phone)
                            .keyboardType(.phonePad)
                            .textContentType(.telephoneNumber)
                    }
                    HStack {
                        TextField("短信验证码", text: $code)
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)
                        Button("发送验证码") {
                            Task {
                                await app.requestSMS(phone: phone)
                                if app.errorMessage == nil { requestedSMS = true }
                            }
                        }
                        .disabled(app.isBusy || app.smsCooldown || phone.isEmpty)
                    }
                    if app.smsCooldown {
                        Text("为避免反复触发短信风控，本机发送间隔至少 60 秒。")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    if requestedSMS {
                        Text("短信请求已提交；请查看手机收到的验证码。")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    Button("登录") {
                        Task { await app.signIn(phone: phone, code: code, context: context) }
                    }
                    .frame(maxWidth: .infinity)
                    .disabled(app.isBusy || code.isEmpty)
                }
                if let error = app.errorMessage {
                    Section {
                        Text(error).foregroundStyle(.red)
                    }
                }
                Section {
                    Text("账户会话保存在 iPhone Keychain。设备状态与历史来自厂商 HTTPS 接口，不会通过本项目服务器转发。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("登录")
            .overlay { if app.isBusy { ProgressView() } }
        }
    }
}
