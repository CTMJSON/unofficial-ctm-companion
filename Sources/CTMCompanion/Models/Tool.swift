import Foundation

enum ToolID: String, CaseIterable, Identifiable {
    case accountAssessment = "ctm-account-assessment"
    case accountAssessmentOnePager = "ctm-account-assessment-onepager"
    case dailyExecutiveSummary = "ctm-daily-executive-summary-report"
    case askAIPromptEnhancer = "askai-prompt-enhancer"
    case supportQnAReport = "ctm-support-qna-report"
    case voiceAITranscriptAnalyzer = "voiceai-transcript-analyzer"

    var id: String { rawValue }
}

struct ToolDefinition: Identifiable {
    let id: ToolID
    let displayName: String
    let description: String
    let scriptFilename: String
    let parameters: [ToolParameter]
    let requiredCredentials: [CredentialKey]
    let outputDescription: String
    let pythonPackages: [String]
}

struct ToolRegistry {
    static let all: [ToolDefinition] = [
        ToolDefinition(
            id: .accountAssessment,
            displayName: "Account Assessment",
            description: "Full CTM account health report with routing inventory, call performance, and agent metrics",
            scriptFilename: "ctm_account_asses.py",
            parameters: [
                ToolParameter(id: "account-id", label: "Account ID", type: .text, isRequired: true, helpText: "Your CTM account ID"),
                ToolParameter(id: "start-date", label: "Start Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
                ToolParameter(id: "end-date", label: "End Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
                ToolParameter(id: "calls-limit", label: "Call Limit", type: .integer(default: 500), isRequired: false, helpText: "Max calls to analyze"),
            ],
            requiredCredentials: [.ctmBasicAuth],
            outputDescription: "HTML report + 7 CSV files",
            pythonPackages: ["requests"]
        ),

        ToolDefinition(
            id: .accountAssessmentOnePager,
            displayName: "Account Assessment (One-Pager)",
            description: "Executive-friendly single-page HTML report with KPIs and call analytics charts",
            scriptFilename: "ctm_account_asses_onepage.py",
            parameters: [
                ToolParameter(id: "account-id", label: "Account ID", type: .text, isRequired: true, helpText: "Your CTM account ID"),
                ToolParameter(id: "start-date", label: "Start Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
                ToolParameter(id: "end-date", label: "End Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
                ToolParameter(id: "calls-limit", label: "Call Limit", type: .integer(default: 500), isRequired: false, helpText: "Max calls to analyze"),
            ],
            requiredCredentials: [.ctmBasicAuth],
            outputDescription: "Single HTML file with charts",
            pythonPackages: ["requests"]
        ),

        ToolDefinition(
            id: .dailyExecutiveSummary,
            displayName: "Daily Executive Summary",
            description: "Automated daily email report with KPIs, agent scorecards, and performance breakdown (typically run daily via scheduling)",
            scriptFilename: "ctm_daily_executive_summary.py",
            parameters: [
                ToolParameter(id: "account-id", label: "Account ID", type: .text, isRequired: true, helpText: "Your CTM account ID"),
            ],
            requiredCredentials: [.ctmBasicAuth, .makeWebhookURL],
            outputDescription: "HTML email + JSON + 4 CSV files",
            pythonPackages: ["requests"]
        ),

        ToolDefinition(
            id: .askAIPromptEnhancer,
            displayName: "AskAI Prompt Enhancer",
            description: "Analyzes AskAI call evaluation mismatches and uses OpenAI to generate an improved prompt",
            scriptFilename: "AskAi Prompt Enhancer.py",
            parameters: [
                ToolParameter(id: "start-date", label: "Start Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
                ToolParameter(id: "end-date", label: "End Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
                ToolParameter(id: "prompt-text", label: "Current AskAI Prompt", type: .text, isRequired: true, helpText: "Your existing AskAI prompt text"),
                ToolParameter(id: "max-calls", label: "Max Calls", type: .integer(default: 100), isRequired: false, helpText: "Max calls to analyze"),
            ],
            requiredCredentials: [.ctmBasicAuth, .openAIKey],
            outputDescription: "Markdown prompt + CSV analysis",
            pythonPackages: ["requests", "openai"]
        ),

        ToolDefinition(
            id: .supportQnAReport,
            displayName: "Support Q&A Report",
            description: "Extracts Q&A from call transcripts using AI-assisted or rule-based parsing",
            scriptFilename: "ctm_support_qna_report.py",
            parameters: [
                ToolParameter(id: "account-id", label: "Account ID", type: .text, isRequired: true, helpText: "Your CTM account ID"),
                ToolParameter(id: "start-date", label: "Start Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
                ToolParameter(id: "end-date", label: "End Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
                ToolParameter(id: "use-openai", label: "Use OpenAI Extraction", type: .toggle(default: false), isRequired: false, helpText: "Enable LLM-assisted extraction"),
            ],
            requiredCredentials: [.ctmBasicAuth],
            outputDescription: "Self-contained HTML report with Q&A table",
            pythonPackages: ["requests", "openai"]
        ),

        ToolDefinition(
            id: .voiceAITranscriptAnalyzer,
            displayName: "VoiceAI Transcript Analyzer",
            description: "Analyzes voice AI and agent call transcripts using GPT-4 to assess quality and generate improvements",
            scriptFilename: "ctm_voiceai_scoring.py",
            parameters: [
                ToolParameter(id: "account-id", label: "Account ID", type: .text, isRequired: true, helpText: "Your CTM account ID"),
                ToolParameter(id: "start-date", label: "Start Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
                ToolParameter(id: "end-date", label: "End Date", type: .dateISO, isRequired: true, helpText: "YYYY-MM-DD"),
            ],
            requiredCredentials: [.ctmBasicAuth, .openAIKey],
            outputDescription: "CSV with GPT-4 analysis + recommendations",
            pythonPackages: ["requests", "openai"]
        ),
    ]
}
