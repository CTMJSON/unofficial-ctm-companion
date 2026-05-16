import SwiftUI

struct SecureFieldWithReveal: View {
    let label: String
    let placeholder: String
    @Binding var text: String
    @State private var isRevealed = false

    var body: some View {
        HStack(spacing: 8) {
            if isRevealed {
                TextField(placeholder, text: $text)
                    .font(.system(.body, design: .monospaced))
            } else {
                SecureField(placeholder, text: $text)
            }

            Button(action: { isRevealed.toggle() }) {
                Image(systemName: isRevealed ? "eye.slash.fill" : "eye.fill")
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help(isRevealed ? "Hide" : "Reveal")
        }
    }
}
