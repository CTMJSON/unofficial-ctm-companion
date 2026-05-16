import Foundation

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
