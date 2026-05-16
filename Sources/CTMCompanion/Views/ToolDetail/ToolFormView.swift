import SwiftUI

struct ToolFormView: View {
    let tool: ToolDefinition
    let credentials: CredentialsManager
    @Binding var formValues: [String: String]

    var body: some View {
        Form {
            ForEach(tool.parameters) { param in
                if tool.id == .askAIPromptEnhancer && param.id == "prompt-text" {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(param.label)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                        TextEditor(text: .init(
                            get: { formValues[param.id] ?? "" },
                            set: { formValues[param.id] = $0 }
                        ))
                        .frame(height: 120)
                        .font(.system(.body, design: .monospaced))
                        .border(Color(nsColor: .separatorColor))
                        Text(param.helpText)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } else {
                    FormField(
                        parameter: param,
                        value: .init(
                            get: {
                                if param.id == "account-id" && formValues[param.id] == nil {
                                    return credentials.ctmAccountID
                                }
                                return formValues[param.id] ?? ""
                            },
                            set: { formValues[param.id] = $0 }
                        )
                    )
                }
            }
        }
    }
}

struct FormField: View {
    let parameter: ToolParameter
    @Binding var value: String

    var body: some View {
        switch parameter.type {
        case .text:
            TextField(parameter.label, text: $value)
                .help(parameter.helpText)

        case .secureText:
            SecureField(parameter.label, text: $value)
                .help(parameter.helpText)

        case .dateISO:
            VStack(alignment: .leading) {
                Text(parameter.label)
                HStack {
                    TextField("YYYY-MM-DD", text: $value)
                        .monospacedDigit()
                    Button(action: { value = dateString(Date()) }) {
                        Image(systemName: "calendar")
                    }
                }
            }
            .help(parameter.helpText)

        case .integer(let defaultValue):
            TextField(parameter.label, text: $value)
                .monospacedDigit()
                .help(parameter.helpText)
                .onAppear {
                    if value.isEmpty {
                        value = String(defaultValue)
                    }
                }

        case .decimal:
            TextField(parameter.label, text: $value)
                .monospacedDigit()
                .help(parameter.helpText)

        case .toggle:
            Toggle(parameter.label, isOn: .init(
                get: { value.lowercased() == "true" },
                set: { value = $0 ? "true" : "false" }
            ))
            .help(parameter.helpText)

        case .filePath:
            HStack {
                TextField(parameter.label, text: $value)
                Button(action: { selectFile() }) {
                    Image(systemName: "folder")
                }
            }
            .help(parameter.helpText)

        case .multiValue:
            TextField(parameter.label, text: $value)
                .help(parameter.helpText)
        }
    }

    private func dateString(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private func selectFile() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.begin { response in
            if response == .OK, let url = panel.url {
                value = url.path
            }
        }
    }
}
