import Foundation

struct RunHistoryEntry: Codable, Identifiable {
    let id: UUID
    let toolID: String
    let timestamp: Date
    let succeeded: Bool
    let duration: TimeInterval

    init(run: ToolRun) {
        self.id = run.id
        self.toolID = run.tool.id.rawValue
        self.timestamp = run.startedAt
        self.succeeded = run.status == .succeeded
        self.duration = Date().timeIntervalSince(run.startedAt)
    }
}

@Observable
class RunHistoryManager {
    static let shared = RunHistoryManager()

    var entries: [RunHistoryEntry] = []
    private let fileManager = FileManager.default
    private let historyFile: URL

    init() {
        let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let dir = appSupport.appendingPathComponent("CTMCompanion")
        self.historyFile = dir.appendingPathComponent("run_history.json")

        loadHistory()
    }

    func addEntry(_ run: ToolRun) {
        let entry = RunHistoryEntry(run: run)
        entries.insert(entry, at: 0)

        if entries.count > 50 {
            entries = Array(entries.prefix(50))
        }

        saveHistory()
    }

    func recentRunCount(for toolID: String) -> Int {
        entries.prefix(10).filter { $0.toolID == toolID }.count
    }

    private func loadHistory() {
        guard fileManager.fileExists(atPath: historyFile.path),
              let data = try? Data(contentsOf: historyFile),
              let decoded = try? JSONDecoder().decode([RunHistoryEntry].self, from: data) else {
            entries = []
            return
        }
        entries = decoded
    }

    private func saveHistory() {
        let dir = historyFile.deletingLastPathComponent()
        try? fileManager.createDirectory(at: dir, withIntermediateDirectories: true)

        if let encoded = try? JSONEncoder().encode(entries) {
            try? encoded.write(to: historyFile)
        }
    }
}
