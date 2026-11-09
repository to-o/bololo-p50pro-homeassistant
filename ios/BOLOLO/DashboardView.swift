import SwiftUI
import SwiftData
import Charts

struct DashboardView: View {
    @EnvironmentObject private var app: AppState
    @Environment(\.modelContext) private var context
    @Query(sort: \FeedEntry.timestamp, order: .reverse) private var entries: [FeedEntry]
    @State private var showingEditor = false

    private var today: [FeedEntry] {
        entries.filter { Calendar.current.isDateInToday($0.timestamp) }
    }

    private var preparedToday: Int {
        today.reduce(0) { $0 + ($1.preparedML ?? 0) }
    }

    private var stats: [DailyTotal] {
        let calendar = Calendar.current
        let start = calendar.startOfDay(for: Date())
        return (0..<7).reversed().compactMap { offset in
            guard let day = calendar.date(byAdding: .day, value: -offset, to: start) else { return nil }
            let total = entries
                .filter { calendar.isDate($0.timestamp, inSameDayAs: day) }
                .reduce(0) { $0 + ($1.preparedML ?? 0) }
            return DailyTotal(day: day, preparedML: total)
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let error = app.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.orange)
                }
                if let warning = app.historyWarning {
                    Label(warning, systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.orange)
                }
                GroupBox("设备状态") {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label(app.selectedDevice?.name ?? "未选择设备", systemImage: "cup.and.saucer")
                            Spacer()
                            if let status = app.status {
                                Text(status.isOnline == true ? "在线" : "状态未知")
                                    .foregroundStyle(status.isOnline == true ? .green : .secondary)
                            }
                        }
                        HStack(spacing: 18) {
                            valueCard("当前水温", app.status?.temperature.map { String(format: "%.1f °C", $0) } ?? "—")
                            valueCard("目标水温", app.status?.targetTemperature.map { String(format: "%.1f °C", $0) } ?? "—")
                        }
                        HStack(spacing: 18) {
                            valueCard("设定出水量", app.status?.selectedWaterML.map { "\($0) mL" } ?? "—")
                            valueCard("最近出水量", app.status?.lastPreparedML.map { "\($0) mL" } ?? "—")
                        }
                        if let time = app.status?.fetchedAt {
                            Text("最近查询：\(time.formatted(date: .omitted, time: .shortened))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                GroupBox("今日备奶") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("\(preparedToday) mL")
                            .font(.largeTitle.bold())
                        Text("\(today.count) 条记录 · 表示备奶出水量，不代表实际喝奶量")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                GroupBox("近 7 天备奶出水量") {
                    Chart(stats) { item in
                        BarMark(
                            x: .value("日期", item.day, unit: .day),
                            y: .value("备奶出水量", item.preparedML)
                        )
                    }
                    .frame(height: 180)
                }
                if let lastSync = app.lastSync {
                    Text("云端历史上次同步：\(lastSync.formatted(date: .abbreviated, time: .shortened))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Button {
                    showingEditor = true
                } label: {
                    Label("手动补记", systemImage: "plus.circle")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
        }
        .navigationTitle("BOLOLO")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await app.refresh(context: context) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .accessibilityLabel("刷新云端数据")
            }
        }
        .refreshable { await app.refresh(context: context) }
        .sheet(isPresented: $showingEditor) {
            NavigationStack { FeedEditor() }
        }
    }

    private func valueCard(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.headline).monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DailyTotal: Identifiable {
    let day: Date
    let preparedML: Int
    var id: Date { day }
}
