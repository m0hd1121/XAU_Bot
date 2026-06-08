// BiometricService.swift
// XAUBot – LocalAuthentication wrapper for Face ID / Touch ID / Optic ID
// iOS 17+  |  Swift 5.9

import Foundation
import LocalAuthentication
import os.log

// MARK: - Biometric Errors

enum BiometricError: LocalizedError {
    case notAvailable
    case notEnrolled
    case authenticationFailed
    case userCancelled
    case userFallback
    case biometryLockout
    case passcodeNotSet
    case unknown(Error)

    var errorDescription: String? {
        switch self {
        case .notAvailable:          return "Biometric authentication is not available on this device."
        case .notEnrolled:           return "No biometrics enrolled. Set up Face ID or Touch ID in Settings."
        case .authenticationFailed:  return "Biometric authentication failed."
        case .userCancelled:         return "Authentication was cancelled."
        case .userFallback:          return "Passcode entry requested."
        case .biometryLockout:       return "Biometrics locked due to too many failed attempts."
        case .passcodeNotSet:        return "Device passcode is not set."
        case .unknown(let e):        return e.localizedDescription
        }
    }
}

// MARK: - BiometricType

enum BiometricType {
    case faceID, touchID, opticID, none

    var displayName: String {
        switch self {
        case .faceID:  return "Face ID"
        case .touchID: return "Touch ID"
        case .opticID: return "Optic ID"
        case .none:    return "Biometrics"
        }
    }

    var systemImage: String {
        switch self {
        case .faceID:  return "faceid"
        case .touchID: return "touchid"
        case .opticID: return "eye"
        case .none:    return "lock.fill"
        }
    }
}

// MARK: - BiometricService

final class BiometricService {

    static let shared = BiometricService()
    private let logger = Logger(subsystem: "com.xaubot.app", category: "Biometric")

    private init() {}

    // MARK: - Availability

    var biometricType: BiometricType {
        let ctx = LAContext()
        var err: NSError?
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &err) else {
            return .none
        }
        switch ctx.biometryType {
        case .faceID:  return .faceID
        case .touchID: return .touchID
        case .opticID: return .opticID
        default:       return .none
        }
    }

    var isAvailable: Bool { biometricType != .none }

    /// Whether a biometric token has been saved for fast re-auth
    var isBiometricSetUp: Bool {
        KeychainService.shared.retrieveString(for: .biometricToken) != nil
    }

    // Alternate naming for linter-generated code
    var canUseBiometrics: Bool { isAvailable }

    var biometricTypeName: String { biometricType.displayName }
    var biometricIcon:     String { biometricType.systemImage }

    // MARK: - Authenticate

    func authenticate(reason: String) async -> Result<Bool, BiometricError> {
        let ctx = LAContext()
        ctx.localizedFallbackTitle = "Enter Passcode"
        ctx.localizedCancelTitle   = "Cancel"

        var policyError: NSError?
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &policyError) else {
            return .failure(mapLAError(policyError))
        }

        do {
            let success = try await ctx.evaluatePolicy(
                .deviceOwnerAuthenticationWithBiometrics,
                localizedReason: reason
            )
            return .success(success)
        } catch {
            return .failure(mapError(error))
        }
    }

    // MARK: - Token Management

    func saveBiometricToken(_ token: String) -> Bool {
        guard let data = token.data(using: .utf8) else { return false }
        return KeychainService.shared.storeBiometricProtected(data, for: .biometricToken)
    }

    func retrieveBiometricToken() -> String? {
        guard let data = KeychainService.shared.retrieveBiometricProtected(for: .biometricToken) else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    func clearBiometricToken() {
        KeychainService.shared.delete(key: .biometricToken)
    }

    // MARK: - Error Mapping

    private func mapError(_ error: Error) -> BiometricError {
        guard let la = error as? LAError else { return .unknown(error) }
        return mapLAError(la as NSError)
    }

    private func mapLAError(_ error: NSError?) -> BiometricError {
        guard let error else { return .notAvailable }
        switch LAError.Code(rawValue: error.code) {
        case .authenticationFailed: return .authenticationFailed
        case .userCancel:           return .userCancelled
        case .userFallback:         return .userFallback
        case .biometryNotAvailable: return .notAvailable
        case .biometryNotEnrolled:  return .notEnrolled
        case .biometryLockout:      return .biometryLockout
        case .passcodeNotSet:       return .passcodeNotSet
        default:                    return .unknown(error)
        }
    }
}
