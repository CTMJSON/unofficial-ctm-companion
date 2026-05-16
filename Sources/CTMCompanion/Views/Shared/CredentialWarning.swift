import SwiftUI

struct CredentialWarning: View {
    let missingCredentials: [CredentialKey]
    @Environment(\.openURL) var openURL

    var credentialDescriptions: [String] {
        missingCredentials.map { key in
            switch key {
            case .ctmBasicAuth:
                return "CTM Basic Auth Token"
            case .openAIKey:
                return "OpenAI API Key"
            case .ctmAccountID:
                return "Default Account ID"
            case .makeWebhookURL:
                return "Make.com Webhook URL"
            case .ctmConvertedField:
                return "CTM Converted Field"
            case .ctmScoreField:
                return "CTM Score Field"
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.circle.fill")
                    .foregroundColor(BrandColors.warning)
                    .font(.headline)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Missing Credentials")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundColor(BrandColors.textPrimary)
                    Text("Set the following in Settings: " + credentialDescriptions.joined(separator: ", "))
                        .font(.caption)
                        .foregroundColor(BrandColors.textSecondary)
                }

                Spacer()

                Button(action: { openSettings() }) {
                    Text("Settings")
                        .font(.caption)
                }
                .buttonStyle(.borderedProminent)
                .tint(BrandColors.primary)
            }
        }
        .padding(12)
        .background(BrandColors.warning.opacity(0.1))
        .cornerRadius(8)
    }

    private func openSettings() {
        NSApp.sendAction(Selector(("showPreferencesWindow:")), to: NSApp.delegate, from: nil)
    }
}
