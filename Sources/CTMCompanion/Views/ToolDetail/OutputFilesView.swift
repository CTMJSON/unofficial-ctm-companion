import SwiftUI

struct OutputFilesView: View {
    let run: ToolRun
    @State private var outputFiles: [OutputFile] = []
    @State private var isLoading = true

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Output Files")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                if isLoading {
                    ProgressView()
                        .scaleEffect(0.7)
                        .frame(width: 20, height: 20)
                } else {
                    Text("(\(outputFiles.count))")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()
            }

            if outputFiles.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "doc.fill")
                        .font(.system(size: 24))
                        .foregroundColor(.secondary)
                    Text("No output files found")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            } else {
                ScrollView {
                    VStack(spacing: 8) {
                        ForEach(outputFiles) { file in
                            OutputFileRow(file: file)
                        }
                    }
                }
                .frame(maxHeight: 150)
            }
        }
        .padding(12)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(6)
        .onAppear {
            discoverFiles()
        }
        .onChange(of: run.status) { _, newStatus in
            if newStatus == .succeeded || newStatus == .failed {
                discoverFiles()
            }
        }
    }

    private func discoverFiles() {
        Task {
            let outputPath = run.tool.id == .accountAssessment
                ? URL(fileURLWithPath: NSSearchPathForDirectoriesInDomains(
                    .documentDirectory, .userDomainMask, true)[0])
                    .appendingPathComponent("CTM Companion/\(run.tool.id.rawValue)")
                : URL(fileURLWithPath: NSSearchPathForDirectoriesInDomains(
                    .documentDirectory, .userDomainMask, true)[0])
                    .appendingPathComponent("CTM Companion")

            let manager = OutputFileManager()
            let files = manager.discoverOutputFiles(in: outputPath)

            let outputFiles = files.map { url in
                let size = manager.fileSize(at: url)
                return OutputFile(url: url, size: size)
            }

            DispatchQueue.main.async {
                self.outputFiles = outputFiles
                isLoading = false
            }
        }
    }
}

struct OutputFile: Identifiable {
    let id = UUID()
    let url: URL
    let size: String

    var filename: String {
        url.lastPathComponent
    }

    var fileIcon: String {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "html":
            return "globe"
        case "csv":
            return "tablecells"
        case "md", "markdown":
            return "doc.text"
        case "json":
            return "curlybraces"
        default:
            return "doc.fill"
        }
    }
}

struct OutputFileRow: View {
    let file: OutputFile
    @State private var isHovering = false

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: file.fileIcon)
                .frame(width: 20)
                .foregroundColor(.blue)

            VStack(alignment: .leading, spacing: 2) {
                Text(file.filename)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .lineLimit(1)
                Text(file.size)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            Spacer()

            HStack(spacing: 4) {
                Button(action: { openFile() }) {
                    Image(systemName: "arrow.up.right.square.fill")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .help("Open in default app")

                Button(action: { revealInFinder() }) {
                    Image(systemName: "folder.fill")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .help("Reveal in Finder")
            }
            .opacity(isHovering ? 1 : 0.5)
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 8)
        .background(Color(nsColor: .textBackgroundColor))
        .cornerRadius(4)
        .onHover { hovering in
            isHovering = hovering
        }
    }

    private func openFile() {
        let manager = OutputFileManager()
        manager.openFile(at: file.url)
    }

    private func revealInFinder() {
        let manager = OutputFileManager()
        manager.revealInFinder(url: file.url)
    }
}
