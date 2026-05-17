import Foundation
import SwiftUI

@Observable
class CredentialsManager {
    static let shared = CredentialsManager()

    private var isLoading = true
    private var batchSaveTimer: Timer?

    var ctmBasicAuth: String = "" {
        didSet { if !isLoading { scheduleBatchSave() } }
    }
    var openAIKey: String = "" {
        didSet { if !isLoading { scheduleBatchSave() } }
    }
    var ctmAccountID: String = "" {
        didSet { if !isLoading { scheduleBatchSave() } }
    }
    var makeWebhookURL: String = "" {
        didSet { if !isLoading { scheduleBatchSave() } }
    }
    var ctmConvertedField: String = "" {
        didSet { if !isLoading { scheduleBatchSave() } }
    }
    var ctmScoreField: String = "" {
        didSet { if !isLoading { scheduleBatchSave() } }
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

    private func scheduleBatchSave() {
        // Cancel any pending save
        batchSaveTimer?.invalidate()

        // Wait 1 second before saving ALL credentials in batch (ONE keychain prompt!)
        batchSaveTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: false) { [weak self] _ in
            self?.batchSave()
        }
    }

    private func batchSave() {
        // Save ALL credentials together
        save(.ctmBasicAuth, value: ctmBasicAuth)
        save(.openAIKey, value: openAIKey)
        save(.ctmAccountID, value: ctmAccountID)
        save(.makeWebhookURL, value: makeWebhookURL)
        save(.ctmConvertedField, value: ctmConvertedField)
        save(.ctmScoreField, value: ctmScoreField)
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
