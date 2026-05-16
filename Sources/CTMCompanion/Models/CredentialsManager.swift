import Foundation
import SwiftUI

@Observable
class CredentialsManager {
    static let shared = CredentialsManager()

    private var isLoading = true

    var ctmBasicAuth: String = "" {
        didSet { if !isLoading { save(.ctmBasicAuth, value: ctmBasicAuth) } }
    }
    var openAIKey: String = "" {
        didSet { if !isLoading { save(.openAIKey, value: openAIKey) } }
    }
    var ctmAccountID: String = "" {
        didSet { if !isLoading { save(.ctmAccountID, value: ctmAccountID) } }
    }
    var makeWebhookURL: String = "" {
        didSet { if !isLoading { save(.makeWebhookURL, value: makeWebhookURL) } }
    }
    var ctmConvertedField: String = "" {
        didSet { if !isLoading { save(.ctmConvertedField, value: ctmConvertedField) } }
    }
    var ctmScoreField: String = "" {
        didSet { if !isLoading { save(.ctmScoreField, value: ctmScoreField) } }
    }

    private init() {
        loadAll()
        isLoading = false
    }

    private func loadAll() {
        ctmBasicAuth = (try? KeychainService.load(.ctmBasicAuth)) ?? ""
        openAIKey = (try? KeychainService.load(.openAIKey)) ?? ""
        ctmAccountID = (try? KeychainService.load(.ctmAccountID)) ?? ""
        makeWebhookURL = (try? KeychainService.load(.makeWebhookURL)) ?? ""
        ctmConvertedField = (try? KeychainService.load(.ctmConvertedField)) ?? ""
        ctmScoreField = (try? KeychainService.load(.ctmScoreField)) ?? ""
    }

    private func save(_ key: CredentialKey, value: String) {
        guard !value.isEmpty else {
            try? KeychainService.delete(key)
            return
        }
        try? KeychainService.save(value, for: key)
    }

    func isSet(_ key: CredentialKey) -> Bool {
        switch key {
        case .ctmBasicAuth: return !ctmBasicAuth.isEmpty
        case .openAIKey: return !openAIKey.isEmpty
        case .ctmAccountID: return !ctmAccountID.isEmpty
        case .makeWebhookURL: return !makeWebhookURL.isEmpty
        case .ctmConvertedField: return !ctmConvertedField.isEmpty
        case .ctmScoreField: return !ctmScoreField.isEmpty
        }
    }

    func value(for key: CredentialKey) -> String {
        switch key {
        case .ctmBasicAuth: return ctmBasicAuth
        case .openAIKey: return openAIKey
        case .ctmAccountID: return ctmAccountID
        case .makeWebhookURL: return makeWebhookURL
        case .ctmConvertedField: return ctmConvertedField
        case .ctmScoreField: return ctmScoreField
        }
    }

    func buildCredentialStore() -> CredentialStore {
        let store = CredentialStore()
        if !ctmBasicAuth.isEmpty {
            store.set(.ctmBasicAuth, value: ctmBasicAuth)
        }
        if !openAIKey.isEmpty {
            store.set(.openAIKey, value: openAIKey)
        }
        if !ctmAccountID.isEmpty {
            store.set(.ctmAccountID, value: ctmAccountID)
        }
        if !makeWebhookURL.isEmpty {
            store.set(.makeWebhookURL, value: makeWebhookURL)
        }
        if !ctmConvertedField.isEmpty {
            store.set(.ctmConvertedField, value: ctmConvertedField)
        }
        if !ctmScoreField.isEmpty {
            store.set(.ctmScoreField, value: ctmScoreField)
        }
        return store
    }
}
