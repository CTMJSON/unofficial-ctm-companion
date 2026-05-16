# CTM Companion — macOS App

A native SwiftUI macOS application for running CTM (Call Tracking Metrics) companion scripts with an intuitive sidebar-based UI.

## Phase 1: Skeleton — Setup Instructions

This is the initial skeleton of the CTM Companion app. To complete the setup and open this in Xcode:

### 1. Open the Project in Xcode

```bash
open /Users/jasonsmith/ctm-companion
```

Or:
- Launch Xcode
- File → Open
- Navigate to `/Users/jasonsmith/ctm-companion`

### 2. Create/Verify App Configuration

In Xcode:
1. Select the project in the Project Navigator
2. Select the "CTMCompanion" target
3. Set:
   - **Minimum Deployment**: macOS 14
   - **Bundle Identifier**: `com.ctm.companion` (or similar)
   - **Team**: Your development team (for signing)
4. Go to Signing & Capabilities:
   - Add capability: **Keychain Sharing**
   - Keychain Group: `com.ctm.companion`

### 3. Build and Run

```bash
cd /Users/jasonsmith/ctm-companion
swift build
```

Or press Cmd+R in Xcode to build and run.

## Project Structure

```
Sources/CTMCompanion/
├── CTMCompanionApp.swift        # @main entry point
├── Models/
│   ├── Tool.swift               # ToolID enum + ToolDefinition
│   ├── ToolParameter.swift       # Form field descriptor
│   ├── ToolRun.swift            # Run state tracking
│   └── Credentials.swift        # Credential key enum
├── Views/
│   ├── ContentView.swift        # Root NavigationSplitView
│   ├── Sidebar/SidebarView.swift
│   ├── ToolDetail/
│   │   ├── ToolDetailView.swift
│   │   └── ToolFormView.swift
│   └── Settings/SettingsView.swift
└── Services/                    # (Phase 2+)
    ├── PythonEnvironment.swift
    ├── ScriptRunner.swift
    ├── KeychainService.swift
    └── OutputFileManager.swift
```

## Next Steps

### Phase 2: Python Infrastructure
- [ ] Clone remaining repos: `ctm-account-assessment`, `ctm-daily-executive-summary-report`, `ctm-support-qna-report`, `VoiceAi-Call-Transcript-Analyzer`
- [ ] Implement `PythonEnvironment.swift` (Python detection, venv setup)
- [ ] Implement `ScriptRunner.swift` (subprocess execution with streaming)
- [ ] Add first-launch venv setup progress sheet
- [ ] Bundle Python scripts into `Resources/Scripts/`

### Phase 3: Keychain & Settings
- [ ] Implement `KeychainService.swift` (SecItem wrapper)
- [ ] Build full `SettingsView` with credential persistence
- [ ] Wire Keychain reads/writes

### Phase 4: Tool Forms
- [ ] Generic `ToolFormView` renderer
- [ ] `DateRangePicker` component
- [ ] Wire Run button to `ScriptRunner`

### Phase 5: Output Handling
- [ ] `RunLogView` with live stdout/stderr
- [ ] `OutputFileManager` and file discovery
- [ ] Open/Reveal/QuickLook button handlers

### Phase 6: Polish
- [ ] App icon
- [ ] Run history sidebar badges
- [ ] Keyboard shortcuts (Cmd+R, Cmd+,)
- [ ] End-to-end testing
- [ ] DMG packaging

## Development Notes

- **Minimum macOS**: 14 (Sonoma) for `@Observable` macro
- **SwiftUI**: Modern APIs (SwiftUI 5.0+ style)
- **Python**: Will use system Python or Homebrew Python on direct download (Python.framework for App Store later)
- **Credentials**: macOS Keychain via `Security.framework`
- **Distribution**: Direct download (.dmg) first, App Store later

## Running the Project

Once Xcode is set up:

```bash
# Build
swift build

# Run
swift run

# Run specific executable
open /Users/jasonsmith/ctm-companion/.build/debug/CTMCompanion.app
```

Or use Cmd+B (build) and Cmd+R (run) in Xcode.
