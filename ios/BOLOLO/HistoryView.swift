import SwiftUI
import SwiftData

struct HistoryView: View {
    @EnvironmentObject private var app: AppState
    @Environment(\.modelContext) private var context
    @Query(sort: \FeedEntry.timestamp, order: .reverse) private var entries: [FeedEntry]
    @State private var editing: FeedEntry?
    @State private var showingEditor = false

    var body: some View {
        List {
            Section {
                Text("备奶出水量和实喝奶量分开记录。云端同步不覆盖你手动修改的实际喝奶量。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                if let last = app.lastSync {
                    Text("已同步 · \(last.formatted(date: .numeric, time: .shortened))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Section("记录 · \(entries.count)") {
                if entries.isEmpty {
                    ContentUnavailableView("还没有喂养记录", systemImage: "list.bullet.rectangle", description: Text("点击右上角刷新云端历史，或手动添加。"))
                }
                ForEach(entries, id: \.id) { item in
                    Button {
                        editing = item
                        showingEditor = true
                    } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(item.timestamp.formatted(date: .abbreviated, time: .shortened))
                                    .font(.subheadline.bold())
                                Spacer()
                                Text(item.source == "cloud" ? "云端备奶" : "手动记录")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Text("备奶：\(item.preparedML.map { "\($0) mL" } ?? "未填写")")
                                .foregroundStyle(.primary)
                            if let consumed = item.consumedML {
                                Text("实际喝奶：\(consumed) mL")
                                    .foregroundStyle(.secondary)
                            }
                            if !item.bottleName.isEmpty {
                                Text("奶瓶：\(item.bottleName)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            if !item.note.isEmpty {
                                Text(item.note).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 5)
                    }
                    .buttonStyle(.plain)
                }
                .onDelete(perform: deleteManualEntries)
            }
        }
        .navigationTitle("喂养日记")
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button {
                    Task { await app.refresh(context: context) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                Button {
                    editing = nil
                    showingEditor = true
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .refreshable { await app.refresh(context: context) }
        .sheet(isPresented: $showingEditor) {
            NavigationStack { FeedEditor(existing: editing) }
        }
    }

    private func deleteManualEntries(at offsets: IndexSet) {
        for index in offsets {
            let item = entries[index]
            // Cloud history would be reimported on next synchronization.
            // Do not pretend deleting it here can delete data in the vendor cloud.
            if item.source == "manual" {
                context.delete(item)
            }
        }
        try? context.save()
    }
}

struct FeedEditor: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var context
    private let existing: FeedEntry?

    @State private var when: Date
    @State private var prepared: String
    @State private var consumed: String
    @State private var bottle: String
    @State private var note: String
    @State private var errorText: String?

    init(existing: FeedEntry? = nil) {
        self.existing = existing
        _when = State(initialValue: existing?.timestamp ?? Date())
        _prepared = State(initialValue: existing?.preparedML.map(String.init) ?? "")
        _consumed = State(initialValue: existing?.consumedML.map(String.init) ?? "")
        _bottle = State(initialValue: existing?.bottleName ?? "")
        _note = State(initialValue: existing?.note ?? "")
    }

    var body: some View {
        Form {
            Section("时间和奶瓶") {
                DatePicker("时间", selection: $when, in: ...Date(), displayedComponents: [.date, .hourAndMinute])
                TextField("奶瓶名称（可选）", text: $bottle)
            }
            Section("奶量") {
                TextField("备奶出水量 mL（可选）", text: $prepared)
                    .keyboardType(.numberPad)
                    .disabled(existing?.source == "cloud")
                TextField("实际喝奶量 mL（可选）", text: $consumed)
                    .keyboardType(.numberPad)
                Text("备奶出水量来自机器时不允许手动覆盖；实喝量请根据实际喂养情况填写。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Section("备注") {
                TextField("备注", text: $note, axis: .vertical)
                    .lineLimit(2...5)
            }
            if let errorText {
                Text(errorText).foregroundStyle(.red)
            }
        }
        .navigationTitle(existing == nil ? "手动补记" : "编辑记录")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("取消") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("保存") { save() }
            }
        }
    }

    private func save() {
        func parsed(_ text: String, maximum: Int) -> Int? {
            if text.trimmingCharacters(in: .whitespaces).isEmpty { return nil }
            guard let value = Int(text), (0...maximum).contains(value) else { return -1 }
            return value
        }
        let water = parsed(prepared, maximum: 5000)
        let milk = parsed(consumed, maximum: 1000)
        if water == -1 || milk == -1 {
            errorText = "请填写有效奶量（备奶不超过 5000 mL，实喝不超过 1000 mL）"
            return
        }
        if let entry = existing {
            if entry.source == "manual" { entry.preparedML = water }
            entry.consumedML = milk
            entry.timestamp = when
            entry.note = String(note.prefix(200))
            entry.bottleName = String(bottle.prefix(80))
            entry.userEdited = true
        } else {
            context.insert(FeedEntry(
                timestamp: when,
                bottleName: String(bottle.prefix(80)),
                preparedML: water,
                consumedML: milk,
                note: String(note.prefix(200)),
                source: "manual",
                userEdited: true
            ))
        }
        do {
            try context.save()
            dismiss()
        } catch {
            errorText = "保存失败：\(error.localizedDescription)"
        }
    }
}
