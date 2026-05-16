import Foundation
import AppKit

class OutputFileManager {
    private let fileManager = FileManager.default

    func discoverOutputFiles(in directory: URL) -> [URL] {
        guard let contents = try? fileManager.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: nil
        ) else {
            return []
        }

        let validExtensions = ["html", "csv", "md", "json", "txt"]
        return contents.filter { url in
            let ext = url.pathExtension.lowercased()
            return validExtensions.contains(ext) && !url.lastPathComponent.starts(with: ".")
        }.sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    func fileSize(at url: URL) -> String {
        guard let attributes = try? fileManager.attributesOfItem(atPath: url.path),
              let size = attributes[.size] as? NSNumber else {
            return "Unknown"
        }

        let bytes = size.int64Value
        if bytes < 1024 {
            return "\(bytes) B"
        } else if bytes < 1024 * 1024 {
            return String(format: "%.1f KB", Double(bytes) / 1024)
        } else {
            return String(format: "%.1f MB", Double(bytes) / (1024 * 1024))
        }
    }

    func openFile(at url: URL) {
        NSWorkspace.shared.open(url)
    }

    func revealInFinder(url: URL) {
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    func getOutputRootFolder() -> URL {
        let documents = fileManager.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return documents.appendingPathComponent("CTM Companion")
    }
}
