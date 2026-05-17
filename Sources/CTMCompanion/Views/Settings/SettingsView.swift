import SwiftUI

struct SettingsView: View {
    @State private var selectedTab: SettingsTab = .credentials

    enum SettingsTab {
        case credentials
        case output
        case python
        case history
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            CredentialsTab()
                .tabItem {
                    Label("Credentials", systemImage: "key.fill")
                }
                .tag(SettingsTab.credentials)

            OutputTab()
                .tabItem {
                    Label("Output", systemImage: "folder.fill")
                }
                .tag(SettingsTab.output)

            PythonTab()
                .tabItem {
                    Label("Python", systemImage: "terminal.fill")
                }
                .tag(SettingsTab.python)

            HistoryTab()
                .tabItem {
                    Label("History", systemImage: "clock.fill")
                }
                .tag(SettingsTab.history)
        }
        .frame(width: 600, height: 400)
    }
}

struct CredentialsTab: View {
    @State private var credentials = CredentialsManager.shared

    var body: some View {
        Form {
            Section("CTM API") {
                HStack {
                    SecureFieldWithReveal(
                        label: "CTM Basic Auth Token",
                        placeholder: "Enter your CTM basic auth token",
                        text: $credentials.ctmBasicAuth
                    )
                    if credentials.isSet(.ctmBasicAuth) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(BrandColors.success)
                    }
                }
                HStack {
                    TextField("Account ID", text: $credentials.ctmAccountID)
                    if credentials.isSet(.ctmAccountID) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(BrandColors.success)
                    }
                }
            }

            Section("OpenAI") {
                HStack {
                    SecureFieldWithReveal(
                        label: "OpenAI API Key",
                        placeholder: "sk-...",
                        text: $credentials.openAIKey
                    )
                    if credentials.isSet(.openAIKey) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(BrandColors.success)
                    }
                }
            }

            Section("Optional") {
                HStack(alignment: .center, spacing: 12) {
                    VStack(alignment: .trailing, spacing: 16) {
                        Text("Webhook URL")
                            .font(.body)
                        Text("Converted Field")
                            .font(.body)
                        Text("Score Field")
                            .font(.body)
                    }
                    .frame(width: 120, alignment: .trailing)

                    VStack(alignment: .leading, spacing: 8) {
                        TextField("", text: $credentials.makeWebhookURL)
                            .placeholder(when: credentials.makeWebhookURL.isEmpty) {
                                Text("https://webhook.site/... (any webhook endpoint)").foregroundColor(.gray)
                            }

                        TextField("", text: $credentials.ctmConvertedField)
                            .placeholder(when: credentials.ctmConvertedField.isEmpty) {
                                Text("did_the_caller_schedule").foregroundColor(.gray)
                            }

                        TextField("", text: $credentials.ctmScoreField)
                            .placeholder(when: credentials.ctmScoreField.isEmpty) {
                                Text("cumulative_score_percentage").foregroundColor(.gray)
                            }
                    }
                }
            }

            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Credentials are stored securely in macOS Keychain", systemImage: "lock.fill")
                        .font(.caption)
                        .foregroundColor(BrandColors.textSecondary)
                    Text("Never transmitted or written to disk")
                        .font(.caption)
                        .foregroundColor(BrandColors.textTertiary)
                }
            }
        }
        .padding()
    }
}

extension View {
    func placeholder<Content: View>(when shouldShow: Bool, alignment: Alignment = .leading, @ViewBuilder placeholder: () -> Content) -> some View {
        ZStack(alignment: alignment) {
            placeholder().opacity(shouldShow ? 1 : 0)
            self
        }
    }
}

struct OutputTab: View {
    @State private var outputFolder = "~/Documents/CTM Companion"

    var body: some View {
        Form {
            Section("Output Location") {
                HStack {
                    TextField("Output Folder", text: $outputFolder)
                    Button("Browse") {
                        selectFolder()
                    }
                }
            }

            Section("Options") {
                Toggle("Auto-open HTML files after run", isOn: .constant(true))
                Toggle("Show notification on completion", isOn: .constant(true))
            }
        }
        .padding()
    }

    private func selectFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.begin { response in
            if response == .OK, let url = panel.url {
                outputFolder = url.path
            }
        }
    }
}

struct PythonTab: View {
    @State private var pythonPath = "/opt/homebrew/bin/python3"
    @State private var venvStatus = "Venv not initialized"

    var body: some View {
        Form {
            Section("Python Detection") {
                TextField("Python Path", text: $pythonPath)
                    .disabled(true)
                Button("Choose Custom Python...") {
                    selectPython()
                }
            }

            Section("Environment") {
                Text("Venv Location: ~/Library/Application Support/CTMCompanion/venv/")
                    .font(.caption)
                Text(venvStatus)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Section("Actions") {
                Button("Reinstall Dependencies") { }
                Button("View Installed Packages") { }
            }
        }
        .padding()
    }

    private func selectPython() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.begin { response in
            if response == .OK, let url = panel.url {
                pythonPath = url.path
            }
        }
    }
}

struct HistoryTab: View {
    @State private var history = RunHistoryManager.shared

    var body: some View {
        Form {
            Section("Run History") {
                if history.entries.isEmpty {
                    Text("No runs yet")
                        .foregroundColor(.secondary)
                } else {
                    List(history.entries.prefix(20)) { entry in
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(entry.toolID.replacingOccurrences(of: "-", with: " ").capitalized)
                                    .font(.subheadline)
                                    .fontWeight(.semibold)
                                Text(formatDate(entry.timestamp))
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }

                            Spacer()

                            HStack(spacing: 8) {
                                Image(systemName: entry.succeeded ? "checkmark.circle.fill" : "xmark.circle.fill")
                                    .foregroundColor(entry.succeeded ? .green : .red)
                                Text(formatDuration(entry.duration))
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    .frame(maxHeight: .infinity)
                }
            }

            Section {
                Button(role: .destructive, action: { clearHistory() }) {
                    HStack {
                        Image(systemName: "trash.fill")
                        Text("Clear History")
                    }
                }
                .disabled(history.entries.isEmpty)
            }
        }
        .padding()
    }

    private func clearHistory() {
        history.entries = []
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    private func formatDuration(_ seconds: TimeInterval) -> String {
        if seconds < 60 {
            return String(format: "%.0fs", seconds)
        } else if seconds < 3600 {
            return String(format: "%.1fm", seconds / 60)
        } else {
            return String(format: "%.1fh", seconds / 3600)
        }
    }
}
