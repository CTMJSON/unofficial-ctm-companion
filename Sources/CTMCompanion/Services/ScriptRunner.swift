import Foundation
import AppKit

actor ScriptRunner {
    private let python: PythonEnvironment

    init(python: PythonEnvironment = .shared) {
        self.python = python
    }

    func run(
        tool: ToolDefinition,
        parameters: [String: String],
        credentials: CredentialStore,
        onLogLine: @escaping (String, Bool) -> Void,
        onExit: @escaping (Int32) -> Void
    ) async throws {
        // Handle softphone separately (it's a web app, not a Python script)
        if tool.id == .ctmSoftphone {
            return await runSoftphone(onLogLine: onLogLine, onExit: onExit)
        }

        let pythonPath = try await python.getVenvPythonPath()
        let outputDir = await python.getOutputPath(for: tool.id.rawValue)

        try FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)

        let scriptPath = try getScriptPath(for: tool)

        var args: [String] = []
        for param in tool.parameters {
            guard let value = parameters[param.id], !value.isEmpty else { continue }
            args.append(param.cliFlag)
            args.append(value)
        }

        args.append("--out-dir")
        args.append(outputDir.path)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [scriptPath] + args
        process.currentDirectoryURL = outputDir
        process.standardInput = FileHandle.nullDevice

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        process.environment = buildEnvironment(credentials: credentials)

        try startPipeReading(stdoutPipe, isError: false, onLogLine: onLogLine)
        try startPipeReading(stderrPipe, isError: true, onLogLine: onLogLine)

        try process.run()
        process.waitUntilExit()

        onExit(process.terminationStatus)
    }

    private func getScriptPath(for tool: ToolDefinition) throws -> String {
        let bundle = Bundle.main
        let scriptName = tool.scriptFilename.replacingOccurrences(of: ".py", with: "")

        // Try main bundle first
        if let path = bundle.path(forResource: scriptName, ofType: "py", inDirectory: "Scripts") {
            return path
        }

        // Try resource bundle (for SPM executable targets)
        if let resourceBundlePath = bundle.path(forResource: "CTMCompanion_CTMCompanion", ofType: "bundle"),
           let resourceBundle = Bundle(path: resourceBundlePath),
           let path = resourceBundle.path(forResource: scriptName, ofType: "py", inDirectory: "Scripts") {
            return path
        }

        // Fallback: check Scripts directory directly
        let fm = FileManager.default
        let scriptsDirs = [
            bundle.resourceURL?.appendingPathComponent("Scripts"),
            bundle.bundleURL.appendingPathComponent("Scripts")
        ].compactMap { $0 }

        for dir in scriptsDirs {
            let scriptPath = dir.appendingPathComponent("\(scriptName).py").path
            if fm.fileExists(atPath: scriptPath) {
                return scriptPath
            }
        }

        throw ScriptError.scriptNotFound(tool.scriptFilename)
    }

    private func buildEnvironment(credentials: CredentialStore) -> [String: String] {
        var env = ProcessInfo.processInfo.environment

        if let ctmAuth = credentials.get(.ctmBasicAuth) {
            env["CTM_BASIC_AUTH_25"] = ctmAuth
            env["CTM_BASIC_AUTH"] = ctmAuth
            env["CTM_API_KEY"] = ctmAuth
            env["CTM_AUTH"] = ctmAuth
        }

        if let accountID = credentials.get(.ctmAccountID) {
            env["CTM_ACCOUNT_ID"] = accountID
        }

        if let openAI = credentials.get(.openAIKey) {
            env["OPENAI_API_KEY"] = openAI
        }

        if let convertedField = credentials.get(.ctmConvertedField) {
            env["CTM_CONVERTED_FIELD"] = convertedField
        }

        if let scoreField = credentials.get(.ctmScoreField) {
            env["CTM_SCORE_FIELD"] = scoreField
        }

        if let webhook = credentials.get(.makeWebhookURL) {
            env["MAKE_WEBHOOK_URL"] = webhook
        }

        return env
    }

    private func runSoftphone(
        onLogLine: @escaping (String, Bool) -> Void,
        onExit: @escaping (Int32) -> Void
    ) async {
        onLogLine("🚀 Starting CTM Softphone...", false)

        // Look for softphone directory in multiple locations
        let fm = FileManager.default
        let homeDir = fm.homeDirectoryForCurrentUser

        let possiblePaths = [
            homeDir.appendingPathComponent("ctm-companion/softphone"),
            homeDir.appendingPathComponent(".ctm-companion/softphone"),
            URL(fileURLWithPath: "/Users/jasonsmith/ctm-companion/softphone"),
        ]

        var softphoneDir: URL?
        for path in possiblePaths {
            if fm.fileExists(atPath: path.path) {
                softphoneDir = path
                break
            }
        }

        guard let softphoneDir = softphoneDir else {
            onLogLine("❌ Softphone directory not found", true)
            onLogLine("", false)
            onLogLine("Softphone is included with CTM Companion but requires the softphone folder.", true)
            onLogLine("", false)
            onLogLine("If you cloned from GitHub:", false)
            onLogLine("  The softphone should be in ctm-companion/softphone/", false)
            onLogLine("", false)
            onLogLine("If you're using the DMG distribution:", false)
            onLogLine("  Download the softphone from: https://github.com/CTMJSON/Custom-CTM-Softphone-Example", true)
            onExit(1)
            return
        }

        onLogLine("📍 Found softphone at: \(softphoneDir.path)", false)

        // Start Flask server
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [softphoneDir.appendingPathComponent("app.py").path]
        process.currentDirectoryURL = softphoneDir

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
        process.standardInput = FileHandle.nullDevice

        do {
            try process.run()

            onLogLine("✅ Softphone server starting...", false)
            onLogLine("⏳ Waiting for server to be ready...", false)

            // Wait for server to start (check port 8080)
            var attempts = 0
            while attempts < 30 {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
                process.arguments = ["-c", "import socket; s = socket.socket(); s.connect(('localhost', 8080)); s.close()"]

                let testPipe = Pipe()
                process.standardOutput = testPipe
                process.standardError = testPipe

                do {
                    try process.run()
                    process.waitUntilExit()

                    if process.terminationStatus == 0 {
                        onLogLine("✅ Server ready!", false)
                        onLogLine("🌐 Opening http://localhost:8080 in browser...", false)

                        NSWorkspace.shared.open(URL(string: "http://localhost:8080")!)

                        onLogLine("✅ Softphone opened in browser", false)
                        onLogLine("💡 Tip: To close the server, close this window or press Ctrl+C", false)
                        onExit(0)
                        return
                    }
                } catch {
                    attempts += 1
                    try? await Task.sleep(nanoseconds: 100_000_000) // Wait 100ms
                }
            }

            onLogLine("⚠️ Server timeout - it may still be starting", true)
            onLogLine("Try opening http://localhost:8080 manually in your browser", false)
            onExit(0)

        } catch {
            onLogLine("❌ Failed to start softphone: \(error.localizedDescription)", true)
            onExit(1)
        }
    }

    private func startPipeReading(
        _ pipe: Pipe,
        isError: Bool,
        onLogLine: @escaping (String, Bool) -> Void
    ) throws {
        let handle = pipe.fileHandleForReading

        DispatchQueue.global().async {
            while true {
                let data = handle.availableData
                guard !data.isEmpty else { break }

                if let string = String(data: data, encoding: .utf8) {
                    let lines = string.split(separator: "\n", omittingEmptySubsequences: false)
                    for line in lines where !line.isEmpty {
                        onLogLine(String(line), isError)
                    }
                }
            }
        }
    }
}

class CredentialStore {
    private var credentials: [CredentialKey: String] = [:]

    func set(_ key: CredentialKey, value: String) {
        credentials[key] = value
    }

    func get(_ key: CredentialKey) -> String? {
        credentials[key]
    }

    func clear(_ key: CredentialKey) {
        credentials.removeValue(forKey: key)
    }
}

enum ScriptError: LocalizedError {
    case scriptNotFound(String)
    case executionFailed(String)

    var errorDescription: String? {
        switch self {
        case .scriptNotFound(let name):
            return "Script not found: \(name)"
        case .executionFailed(let msg):
            return "Execution failed: \(msg)"
        }
    }
}
