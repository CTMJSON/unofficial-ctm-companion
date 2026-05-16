import Foundation

enum RunStatus {
    case idle
    case running
    case succeeded
    case failed
}

struct LogLine: Identifiable {
    let id = UUID()
    let text: String
    let isError: Bool
    let timestamp: Date
}

@Observable
class ToolRun: Identifiable {
    let id: UUID
    let tool: ToolDefinition
    let startedAt: Date
    var status: RunStatus = .idle
    var logLines: [LogLine] = []
    var outputFiles: [URL] = []
    var exitCode: Int32?

    init(tool: ToolDefinition) {
        self.id = UUID()
        self.tool = tool
        self.startedAt = Date()
    }

    func addLogLine(_ text: String, isError: Bool = false) {
        logLines.append(LogLine(text: text, isError: isError, timestamp: Date()))
    }

    var statusBadgeColor: Color {
        switch status {
        case .idle:
            return .gray
        case .running:
            return .blue
        case .succeeded:
            return .green
        case .failed:
            return .red
        }
    }

    var statusText: String {
        switch status {
        case .idle:
            return "Ready"
        case .running:
            return "Running…"
        case .succeeded:
            return "Completed"
        case .failed:
            return "Failed"
        }
    }
}

import SwiftUI
