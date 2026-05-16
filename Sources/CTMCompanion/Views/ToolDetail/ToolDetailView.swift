import SwiftUI
import AppKit

struct ToolDetailView: View {
    let tool: ToolDefinition
    @State private var credentials = CredentialsManager.shared
    @State private var formValues: [String: String] = [:]
    @State private var currentRun: ToolRun?
    @State private var history = RunHistoryManager.shared

    var missingCredentials: [CredentialKey] {
        tool.requiredCredentials.filter { !credentials.isSet($0) }
    }

    var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 8) {
                Text(tool.displayName)
                    .font(.title2)
                    .fontWeight(.bold)
                Text(tool.description)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .borderBottom()

            if let run = currentRun {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        RunLogView(run: run)

                        if run.status == .succeeded && !run.outputFiles.isEmpty {
                            OutputFilesView(run: run)
                        } else if run.status == .failed {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(spacing: 8) {
                                    Image(systemName: "exclamationmark.circle.fill")
                                        .foregroundColor(BrandColors.error)
                                    Text("Execution Failed")
                                        .font(.subheadline)
                                        .fontWeight(.semibold)
                                }
                                Text("Check the output above for error details")
                                    .font(.caption)
                                    .foregroundColor(BrandColors.textSecondary)
                            }
                            .padding(12)
                            .background(BrandColors.error.opacity(0.1))
                            .cornerRadius(6)
                        }
                    }
                    .padding()
                }
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        if !missingCredentials.isEmpty {
                            CredentialWarning(missingCredentials: missingCredentials)
                        }

                        Section("Parameters") {
                            ToolFormView(tool: tool, credentials: credentials, formValues: $formValues)
                        }
                    }
                    .padding()
                }
            }

            Divider()

            HStack {
                Button(action: runTool) {
                    if currentRun?.status == .running {
                        ProgressView()
                            .scaleEffect(0.8)
                            .tint(.white)
                    } else {
                        Image(systemName: "play.fill")
                    }
                    Text(currentRun?.status == .running ? "Running…" : "Run Tool")
                }
                .buttonStyle(.borderedProminent)
                .tint(BrandColors.primary)
                .disabled(!missingCredentials.isEmpty || currentRun?.status == .running)
                .keyboardShortcut("r", modifiers: .command)

                Spacer()

                if let run = currentRun {
                    Text(run.statusText)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundColor(run.statusBadgeColor)
                } else {
                    Text(missingCredentials.isEmpty ? "Ready" : "Missing credentials")
                        .font(.caption)
                        .foregroundColor(missingCredentials.isEmpty ? BrandColors.textSecondary : BrandColors.warning)
                }
            }
            .padding()
        }
    }

    private func runTool() {
        let run = ToolRun(tool: tool)
        currentRun = run

        Task {
            do {
                run.status = .running

                let store = credentials.buildCredentialStore()
                let runner = ScriptRunner()
                let outputPath = await PythonEnvironment.shared.getOutputPath(for: tool.id.rawValue)

                try await runner.run(
                    tool: tool,
                    parameters: formValues,
                    credentials: store,
                    onLogLine: { text, isError in
                        run.addLogLine(text, isError: isError)
                    },
                    onExit: { code in
                        run.exitCode = code
                        run.status = code == 0 ? .succeeded : .failed

                        DispatchQueue.main.async {
                            history.addEntry(run)
                            NotificationService.shared.notifyCompletion(tool: tool.displayName, succeeded: code == 0)

                            if code == 0 {
                                let manager = OutputFileManager()
                                let files = manager.discoverOutputFiles(in: outputPath)
                                run.outputFiles = files

                                if let htmlFile = files.first(where: { $0.pathExtension == "html" }) {
                                    NSWorkspace.shared.open(htmlFile)
                                }
                            }
                        }
                    }
                )
            } catch {
                run.addLogLine("Error: \(error.localizedDescription)", isError: true)
                run.status = .failed
            }
        }
    }
}

struct BorderBottomModifier: ViewModifier {
    func body(content: Content) -> some View {
        VStack(spacing: 0) {
            content
            Divider()
        }
    }
}

extension View {
    func borderBottom() -> some View {
        modifier(BorderBottomModifier())
    }
}
