import SwiftUI

struct ContentView: View {
    @State private var selectedTool: ToolID? = .accountAssessmentOnePager

    var body: some View {
        NavigationSplitView {
            SidebarView(selectedTool: $selectedTool)
        } detail: {
            if let selectedID = selectedTool,
               let tool = ToolRegistry.all.first(where: { $0.id == selectedID }) {
                ToolDetailView(tool: tool)
            } else {
                VStack {
                    Image(systemName: "app.dashed")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text("Select a tool from the sidebar")
                        .font(.headline)
                        .foregroundColor(.secondary)
                }
            }
        }
    }
}
