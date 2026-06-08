// KeychainService.swift
// XAUBot – Keychain wrapper for secure storage of tokens and configuration
// iOS 17+  |  Swift 5.9

import Foundation
import Security
import os.log

// MARK: - Keychain Key

enum KeychainKey: String, CaseIterable {
    case accessToken    = "com.xaubot.accessToken"
    case refreshToken   = "com.xaubot.refreshToken"
    case serverURL      = "com.xaubot.serverURL"
    case apiKey         = "com.xaubot.apiKey"
    case biometricToken = "com.xaubot.biometricToken"
    case deviceId       = "com.xaubot.deviceId"
    case username       = "com.xaubot.username"
}

// MARK: - KeychainService

final class KeychainService {

    static let shared = KeychainService()

    private let logger      = Logger(subsystem: "com.xaubot.app", category: "Keychain")
    private let serviceName = "com.xaubot.app"

    private init() {}

    // MARK: - String API (used by ViewModels and Services)

    /// Store a String value.  Returns true on success.
    @discardableResult
    func store(_ value: String, for key: KeychainKey) -> Bool {
        guard let data = value.data(using: .utf8) else { return false }
        return storeData(data, for: key)
    }

    /// Retrieve a stored String. Returns nil if absent.
    func retrieveString(for key: KeychainKey) -> String? {
        guard let data = retrieveData(for: key) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    // MARK: - Alternate naming convention (used by linter-generated code)

    @discardableResult
    func save(string: String, forKey key: KeychainKey) -> Bool {
        store(string, for: key)
    }

    func retrieveString(forKey key: KeychainKey) -> String? {
        retrieveString(for: key)
    }

    // MARK: - Data API

    @discardableResult
    func store(_ data: Data, for key: KeychainKey) -> Bool {
        storeData(data, for: key)
    }

    func retrieveData(for key: KeychainKey) -> Data? {
        var query = baseQuery(for: key)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess else {
            if status != errSecItemNotFound {
                logger.error("Keychain retrieve failed [\(key.rawValue)]: \(status)")
            }
            return nil
        }
        return result as? Data
    }

    // MARK: - Delete

    @discardableResult
    func delete(key: KeychainKey) -> Bool {
        let query  = baseQuery(for: key)
        let status = SecItemDelete(query as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }

    // MARK: - Biometric-Protected Storage

    @discardableResult
    func storeBiometricProtected(_ data: Data, for key: KeychainKey) -> Bool {
        var cfError: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(
            kCFAllocatorDefault,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.biometryAny],
            &cfError
        ) else {
            logger.error("Access control creation failed: \(cfError.debugDescription)")
            return false
        }

        var query = baseQuery(for: key)
        SecItemDelete(query as CFDictionary)
        query[kSecAttrAccessControl as String]  = access
        query[kSecUseAuthenticationUI as String] = kSecUseAuthenticationUIAllow
        query[kSecValueData as String]           = data

        let status = SecItemAdd(query as CFDictionary, nil)
        if status != errSecSuccess {
            logger.error("Biometric store failed [\(key.rawValue)]: \(status)")
            return false
        }
        return true
    }

    func retrieveBiometricProtected(for key: KeychainKey) -> Data? {
        var query = baseQuery(for: key)
        query[kSecReturnData as String]          = true
        query[kSecMatchLimit as String]          = kSecMatchLimitOne
        query[kSecUseAuthenticationUI as String]  = kSecUseAuthenticationUIAllow
        query[kSecUseOperationPrompt as String]   = "Authenticate to access XAUBot"

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess else {
            if status != errSecItemNotFound && status != errSecUserCanceled {
                logger.error("Biometric retrieve failed [\(key.rawValue)]: \(status)")
            }
            return nil
        }
        return result as? Data
    }

    // MARK: - Bulk Clear (Logout)

    func clearAll() {
        [KeychainKey.accessToken, .refreshToken, .biometricToken].forEach { delete(key: $0) }
    }

    // MARK: - Private

    private func storeData(_ data: Data, for key: KeychainKey) -> Bool {
        var query = baseQuery(for: key)
        query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        SecItemDelete(query as CFDictionary)
        query[kSecValueData as String] = data
        let status = SecItemAdd(query as CFDictionary, nil)
        if status != errSecSuccess {
            logger.error("Keychain store failed [\(key.rawValue)]: \(status)")
        }
        return status == errSecSuccess
    }

    private func baseQuery(for key: KeychainKey) -> [String: Any] {
        [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: key.rawValue
        ]
    }
}
