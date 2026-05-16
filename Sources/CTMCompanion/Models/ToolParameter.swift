import Foundation

enum ParameterType: Equatable {
    case text
    case secureText
    case dateISO
    case integer(default: Int)
    case decimal(default: Double)
    case toggle(default: Bool)
    case filePath
    case multiValue
}

struct ToolParameter: Identifiable, Equatable {
    let id: String
    let label: String
    let type: ParameterType
    let isRequired: Bool
    let helpText: String

    var cliFlag: String { "--\(id)" }

    static func == (lhs: ToolParameter, rhs: ToolParameter) -> Bool {
        lhs.id == rhs.id && lhs.label == rhs.label && lhs.type == rhs.type &&
            lhs.isRequired == rhs.isRequired && lhs.helpText == rhs.helpText
    }
}
