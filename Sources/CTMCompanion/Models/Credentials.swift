import Foundation

enum CredentialKey: String, CaseIterable {
    case ctmBasicAuth = "com.ctm.companion.ctm-basic-auth"
    case openAIKey = "com.ctm.companion.openai-key"
    case ctmAccountID = "com.ctm.companion.account-id"
    case makeWebhookURL = "com.ctm.companion.make-webhook-url"
    case ctmConvertedField = "com.ctm.companion.converted-field"
    case ctmScoreField = "com.ctm.companion.score-field"
}
