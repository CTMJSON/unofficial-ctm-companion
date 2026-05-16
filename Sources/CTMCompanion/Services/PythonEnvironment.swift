import Foundation

actor PythonEnvironment {
    static let shared = PythonEnvironment()

    private let fileManager = FileManager.default
    private var detectedPythonPath: String?
    private var venvPath: URL?

    var isReady: Bool = false

    private init() {}

    func setup() async throws {
        let python = await detectPython()
        detectedPythonPath = python
        venvPath = venvDirectory()

        guard let venvPath else {
            throw PythonError.cannotCreateVenv
        }

        if !fileManager.fileExists(atPath: venvPath.path) {
            try await createVenv(pythonPath: python)
        }

        try await installDependencies(pythonPath: python)
        isReady = true
    }

    func getPythonPath() throws -> String {
        guard let path = detectedPythonPath else {
            throw PythonError.pythonNotFound
        }
        return path
    }

    func getVenvPythonPath() throws -> String {
        guard let venvPath else {
            throw PythonError.cannotCreateVenv
        }
        let venvPython = venvPath.appendingPathComponent("bin/python3")
        return venvPython.path
    }

    private func detectPython() async -> String {
        let candidates = [
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3"
        ]

        for candidate in candidates {
            if fileManager.fileExists(atPath: candidate) {
                return candidate
            }
        }

        return "/usr/bin/python3"
    }

    private func venvDirectory() -> URL? {
        let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
        return appSupport?.appendingPathComponent("CTMCompanion/venv")
    }

    private func createVenv(pythonPath: String) async throws {
        guard let venvPath else {
            throw PythonError.cannotCreateVenv
        }

        try fileManager.createDirectory(at: venvPath, withIntermediateDirectories: true)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = ["-m", "venv", venvPath.path]

        let errorPipe = Pipe()
        process.standardError = errorPipe

        try process.run()
        process.waitUntilExit()

        if process.terminationStatus != 0 {
            let errorData = errorPipe.fileHandleForReading.readDataToEndOfFile()
            let errorMsg = String(data: errorData, encoding: .utf8) ?? "Unknown error"
            throw PythonError.venvCreationFailed(errorMsg)
        }
    }

    private func installDependencies(pythonPath: String) async throws {
        guard let venvPath else {
            throw PythonError.cannotCreateVenv
        }

        let venvPip = venvPath.appendingPathComponent("bin/pip3")
        let process = Process()
        process.executableURL = venvPip
        process.arguments = ["install", "--quiet", "requests", "openai"]

        let errorPipe = Pipe()
        process.standardError = errorPipe

        try process.run()
        process.waitUntilExit()

        if process.terminationStatus != 0 {
            let errorData = errorPipe.fileHandleForReading.readDataToEndOfFile()
            let errorMsg = String(data: errorData, encoding: .utf8) ?? "Unknown error"
            throw PythonError.pipInstallFailed(errorMsg)
        }
    }

    func getScriptsPath() -> URL? {
        let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
        return appSupport?.appendingPathComponent("CTMCompanion/scripts")
    }

    func getOutputPath(for toolID: String) -> URL {
        let companion = fileManager.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("CTM Companion")
        let toolPath = companion.appendingPathComponent(toolID)

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd-HHmmss"
        let timestamp = formatter.string(from: Date())

        return toolPath.appendingPathComponent(timestamp)
    }
}

enum PythonError: LocalizedError {
    case pythonNotFound
    case cannotCreateVenv
    case venvCreationFailed(String)
    case pipInstallFailed(String)

    var errorDescription: String? {
        switch self {
        case .pythonNotFound:
            return "Python 3 not found. Please install Python via Homebrew or python.org."
        case .cannotCreateVenv:
            return "Could not create virtual environment."
        case .venvCreationFailed(let msg):
            return "Failed to create venv: \(msg)"
        case .pipInstallFailed(let msg):
            return "Failed to install dependencies: \(msg)"
        }
    }
}
