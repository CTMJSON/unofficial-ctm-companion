import SwiftUI

struct SidebarView: View {
    @Binding var selectedTool: ToolID?
    @State private var history = RunHistoryManager.shared

    var body: some View {
        List(ToolRegistry.all, id: \.id) { tool in
            Button(action: { selectedTool = tool.id }) {
                HStack(alignment: .top, spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(tool.displayName)
                            .font(.headline)
                            .foregroundColor(selectedTool == tool.id ? BrandColors.primary : BrandColors.textPrimary)
                        Text(tool.description)
                            .font(.caption)
                            .foregroundColor(BrandColors.textSecondary)
                            .lineLimit(2)
                    }

                    Spacer()

                    if let count = Optional(history.recentRunCount(for: tool.id.rawValue)),
                       count > 0 {
                        Text("\(count)")
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .foregroundColor(.white)
                            .background(BrandColors.secondary)
                            .clipShape(Circle())
                            .frame(width: 28, height: 28)
                    }
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 12)
            }
            .buttonStyle(.plain)
            .background(selectedTool == tool.id ? BrandColors.backgroundLight : Color.clear)
            .cornerRadius(10)
        }
        .navigationSplitViewColumnWidth(min: 250, ideal: 300, max: 400)
    }
}
