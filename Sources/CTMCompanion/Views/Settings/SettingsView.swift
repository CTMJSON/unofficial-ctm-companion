import SwiftUI

struct SettingsView: View {
    @State private var selectedTab: SettingsTab = .credentials

    enum SettingsTab {
        case credentials
        case output
        case python
        case history
        case about
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

            AboutTab()
                .tabItem {
                    Label("About", systemImage: "info.circle.fill")
                }
                .tag(SettingsTab.about)
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

struct AboutTab: View {
    var body: some View {
        Form {
            Section {
                VStack(alignment: .center, spacing: 16) {
                    ZStack {
                        Circle()
                            .fill(
                                LinearGradient(
                                    gradient: Gradient(colors: [
                                        Color(red: 0.01, green: 0.75, blue: 0.96),
                                        Color(red: 0.07, green: 0.59, blue: 0.79),
                                        Color(red: 0.09, green: 0.36, blue: 0.55)
                                    ]),
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 80, height: 80)

                        Text("CTM")
                            .font(.system(size: 32, weight: .bold))
                            .foregroundColor(.white)
                    }

                    VStack(alignment: .center, spacing: 4) {
                        Text("CTM Companion")
                            .font(.title2)
                            .fontWeight(.bold)
                        Text("Version 1.0")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
            }

            Section("About") {
                VStack(alignment: .leading, spacing: 12) {
                    Text("CTM Companion brings powerful CTM analytics tools directly to your macOS desktop. All tools run locally with your credentials stored securely in Keychain.")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Divider()

                    VStack(alignment: .leading, spacing: 8) {
                        Label("7 integrated tools", systemImage: "checkmark.circle.fill")
                            .font(.caption)
                        Label("Secure Keychain storage", systemImage: "checkmark.circle.fill")
                            .font(.caption)
                        Label("Local execution only", systemImage: "checkmark.circle.fill")
                            .font(.caption)
                        Label("No telemetry or tracking", systemImage: "checkmark.circle.fill")
                            .font(.caption)
                    }
                    .foregroundColor(BrandColors.success)
                }
            }

            Section("Security & Privacy") {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Your data is yours. Nothing is collected, stored on disk, or sent anywhere without your explicit knowledge.")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundColor(.secondary)

                    Divider()

                    Text("🔒 Credential Security").font(.caption).fontWeight(.semibold)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("• Stored in macOS Keychain (OS-level encryption)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Each credential in separate encrypted Keychain entry")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Never written to disk as plain text")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Never transmitted to third parties")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Only used for CTM API and OpenAI API calls")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Secure update mechanism (no delete-then-add prompts)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }

                    Text("🚀 Script Execution").font(.caption).fontWeight(.semibold).padding(.top, 8)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("• All scripts run locally on your machine")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Python runs in isolated venv (~/Library/Application Support/)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Only standard Python packages (requests, openai)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Output saved only to ~/Documents/CTM Companion/")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }

                    Text("📊 Data Collection").font(.caption).fontWeight(.semibold).padding(.top, 8)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("• No telemetry or usage tracking")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• No data uploads to any server")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• No analytics or crash reporting")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• No network requests except CTM API and OpenAI API")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }

                    Text("💾 Local Storage").font(.caption).fontWeight(.semibold).padding(.top, 8)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("• Credentials: macOS Keychain only")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Output files: Local disk only")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• Run history: Local JSON in Application Support")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text("• No cloud sync or backup")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
            }

            Section("Developer") {
                VStack(alignment: .leading, spacing: 12) {
                    Text("This application is developed and maintained as a hobby and passionate side project.")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    HStack(spacing: 4) {
                        Text("By")
                            .font(.caption)
                        Link("jason.smith@ctm.com", destination: URL(string: "mailto:jason.smith@ctm.com")!)
                            .font(.caption)
                            .foregroundColor(BrandColors.primary)
                    }

                    Link("View on GitHub", destination: URL(string: "https://github.com/CTMJSON/ctm-companion")!)
                        .font(.caption)
                        .foregroundColor(BrandColors.primary)
                }
            }
        }
        .padding()
    }
}
