import SwiftUI

struct RunLogView: View {
    let run: ToolRun

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                HStack(spacing: 6) {
                    Circle()
                        .fill(run.statusBadgeColor)
                        .frame(width: 8, height: 8)
                    Text(run.statusText)
                        .font(.caption)
                        .fontWeight(.semibold)
                }

                Spacer()

                if run.status == .running {
                    ProgressView()
                        .scaleEffect(0.8)
                        .frame(width: 20, height: 20)
                }
            }
            .padding(8)
            .background(Color(nsColor: .controlBackgroundColor))
            .borderBottom()

            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(run.logLines) { line in
                            HStack(spacing: 8) {
                                Text(formatTime(line.timestamp))
                                    .font(.system(.caption, design: .monospaced))
                                    .foregroundColor(.secondary)
                                    .frame(width: 70, alignment: .leading)

                                Text(line.text)
                                    .font(.system(.caption, design: .monospaced))
                                    .foregroundColor(line.isError ? .red : .primary)
                                    .lineLimit(3)

                                Spacer()
                            }
                            .padding(.vertical, 4)
                            .padding(.horizontal, 8)
                            .id(line.id)
                        }

                        if run.logLines.isEmpty {
                            VStack(spacing: 8) {
                                Image(systemName: "terminal")
                                    .font(.system(size: 32))
                                    .foregroundColor(.secondary)
                                Text("Run will appear here")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .padding()
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                }
                .onChange(of: run.logLines.count) { _, _ in
                    if let lastLine = run.logLines.last {
                        withAnimation(.easeOut(duration: 0.1)) {
                            proxy.scrollTo(lastLine.id, anchor: .bottom)
                        }
                    }
                }
            }
        }
        .background(Color(nsColor: .textBackgroundColor))
        .cornerRadius(6)
    }

    private func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.timeStyle = .medium
        return formatter.string(from: date)
    }
}
