import SwiftUI

@main
struct CTMCompanionApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 1000, minHeight: 600)
                .onAppear {
                    Task {
                        do {
                            try await PythonEnvironment.shared.setup()
                        } catch {
                            print("Python setup error: \(error.localizedDescription)")
                        }
                    }
                }
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.automatic)

        Settings {
            SettingsView()
        }
    }
}
