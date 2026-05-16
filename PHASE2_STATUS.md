# Phase 2: Python Infrastructure & Script Execution — COMPLETE

## What Was Implemented

### Services Created

1. **PythonEnvironment.swift** (`Services/PythonEnvironment.swift`)
   - Detects Python 3 in system: `/opt/homebrew/bin/python3` → `/usr/local/bin/python3` → `/usr/bin/python3`
   - Creates virtual environment at `~/Library/Application Support/CTMCompanion/venv/`
   - Automatically installs pip dependencies: `requests`, `openai`
   - Handles errors gracefully with custom `PythonError` enum
   - Provides helper methods: `getPythonPath()`, `getVenvPythonPath()`, `getOutputPath(for:)`

2. **ScriptRunner.swift** (`Services/ScriptRunner.swift`)
   - Executes Python scripts as subprocesses using `Foundation.Process`
   - Streams stdout/stderr line-by-line to UI callbacks
   - Builds CLI arguments from ToolParameter values
   - Injects credentials as environment variables (no env.txt file touching)
   - Handles working directory and output redirection
   - Sets stdin to `/dev/null` to prevent `input()` blocking (AskAI Enhancer)

3. **KeychainService.swift** (`Services/KeychainService.swift`)
   - Wraps `Security.framework` SecItem API
   - Stores/retrieves credentials securely: CTM auth, OpenAI key, Account ID, etc.
   - Methods: `save()`, `load()`, `delete()`
   - Custom `KeychainError` enum with detailed error reporting

4. **OutputFileManager.swift** (`Services/OutputFileManager.swift`)
   - Discovers output files (`.html`, `.csv`, `.md`, `.json`, `.txt`) after script runs
   - Provides file size formatting
   - Integrates with `NSWorkspace` to open files or reveal in Finder
   - Manages output root folder at `~/Documents/CTM Companion/`

5. **CredentialStore.swift** (embedded in `ScriptRunner.swift`)
   - In-memory credential cache for subprocess environment injection
   - Methods: `set()`, `get()`, `clear()`

### Scripts & Resources

- **All 6 Python scripts copied to `Resources/Scripts/`**:
  1. `ctm_account_asses.py` — Account Assessment (full report)
  2. `ctm_account_asses_onepage.py` — Account Assessment (one-pager)
  3. `ctm_daily_executive_summary.py` — Daily Executive Summary
  4. `AskAi Prompt Enhancer.py` — AskAI Prompt Enhancer
  5. `ctm_support_qna_report.py` — Support Q&A Report
  6. `ctm_voiceai_scoring.py` — VoiceAI Transcript Analyzer
  7. `prompt.txt` — Default AskAI prompt template

### Models Updated

- **Tool.swift**: Updated script filenames to match actual files (`ctm_account_asses.py`, `ctm_voiceai_scoring.py`)
- **ToolRegistry**: All 6 tools fully defined with parameters, credentials, descriptions

### App Integration

- **CTMCompanionApp.swift**: Added Python environment initialization on app launch using `onAppear`
- Build system: Full Swift compilation working, all services integrated

## Architecture Decisions

1. **Python Detection Order**: Homebrew (Apple Silicon) → Homebrew (Intel) → System Python
2. **Venv Location**: `~/Library/Application Support/CTMCompanion/venv/` (survives app updates, writable without sandbox)
3. **Output Paths**: `~/Documents/CTM Companion/{toolID}/{YYYY-MM-DD-HHmmss}/` (organized, user-discoverable)
4. **Credentials**: Environment variables only, never written to disk; Keychain for persistent storage
5. **Script Bundling**: Copied into `Resources/Scripts/`; works with Swift Package Manager build system

## Known Limitations / Future Work

1. **Script Staging**: AskAI Prompt Enhancer reads `prompt.txt` from its own directory. When UI wiring is complete, the app will need to:
   - Copy script + prompt.txt to a staging directory in Application Support
   - Execute from there
   - This is handled in ScriptRunner but needs UI form integration

2. **Live Output**: ScriptRunner has the infrastructure for streaming output, but UI views aren't wired yet
   - `onLogLine` callback receives (text, isError) tuples
   - Needs to be integrated into `RunLogView` (Phase 5)

3. **Error Handling**: Full error handling in all services; needs UI integration for user visibility

## Build Status

✅ **Compiles without errors**
```
swift build
Build complete! (0.91s)
```

## Next Phase: Phase 3 — Keychain & Settings UI

- [ ] Implement full `CredentialsTab` with Keychain read/write
- [ ] Wire Settings window to persist credentials
- [ ] Update forms to pre-populate Account ID from Keychain
- [ ] Add inline credential-missing warnings

See `/Users/jasonsmith/ctm-companion/README.md` for setup instructions.
