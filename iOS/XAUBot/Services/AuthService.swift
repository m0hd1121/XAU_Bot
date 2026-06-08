// AuthService.swift
// XAUBot – Auth service: login, biometric, session restore, logout, token refresh
// iOS 17+  |  Swift 5.9

import Foundation
import Combine
import os.log

// MARK: - AuthService

@MainActor
final class AuthService: ObservableObject {

    static let shared = AuthService()

    @Published private(set) var isAuthenticated = false
    @Published private(set) var currentUser:     UserProfile?

    private let logger   = Logger(subsystem: "com.xaubot.app", category: "AuthService")
    private let keychain = KeychainService.shared

    private init() {
        Task { await attemptSilentLogin() }
    }

    // MARK: - Handle successful login (called by AuthViewModel after APIClient.login returns)

    func handleSuccessfulLogin(_ response: LoginResponse) async {
        guard let access  = response.accessToken,
              let refresh = response.refreshToken else { return }

        keychain.store(access,  for: .accessToken)
        keychain.store(refresh, for: .refreshToken)

        do {
            let profile: UserProfile = try await APIClient.shared.request(Endpoint.me)
            currentUser      = profile
            isAuthenticated  = true
            keychain.store(profile.username, for: .username)
            logger.info("Session established for \(profile.username)")
        } catch {
            logger.error("Profile fetch failed after login: \(error)")
            isAuthenticated = true   // still authenticated; profile optional
        }
    }

    // MARK: - Restore session (called after biometric success with stored token)

    func restoreSession(token: String) async {
        // token is the stored access token; verify by fetching profile
        keychain.store(token, for: .accessToken)
        do {
            let profile: UserProfile = try await APIClient.shared.request(Endpoint.me)
            currentUser     = profile
            isAuthenticated = true
            logger.info("Session restored via biometric for \(profile.username)")
        } catch {
            logger.warning("Session restore failed: \(error)")
            isAuthenticated = false
            ToastManager.shared.show("Session expired. Please sign in with password.", type: .error)
        }
    }

    // MARK: - Silent login on app start

    func attemptSilentLogin() async {
        guard let refreshToken = keychain.retrieveString(for: .refreshToken) else { return }

        do {
            let req = RefreshRequest(refreshToken: refreshToken)
            let tokens: AuthTokens = try await APIClient.shared.request(
                Endpoint.refreshToken(request: req)
            )
            keychain.store(tokens.accessToken,  for: .accessToken)
            keychain.store(tokens.refreshToken, for: .refreshToken)

            let profile: UserProfile = try await APIClient.shared.request(Endpoint.me)
            currentUser     = profile
            isAuthenticated = true
            logger.info("Silent login succeeded for \(profile.username)")
        } catch {
            logger.info("Silent login failed – requires manual login")
            isAuthenticated = false
        }
    }

    // MARK: - Session Expiry (called by APIClient on 401 retry failure)

    func handleSessionExpiry() async {
        clearSession()
        ToastManager.shared.show("Session expired. Please sign in again.", type: .error)
    }

    // MARK: - Logout

    func logout() async {
        _ = try? await APIClient.shared.request(Endpoint.logout) as EmptyResponse
        clearSession()
        logger.info("Logged out")
    }

    // MARK: - Change Password

    func changePassword(current: String, new: String) async throws {
        let req = ChangePasswordRequest(currentPassword: current, newPassword: new)
        let _: MessageResponse = try await APIClient.shared.request(
            Endpoint.changePassword(request: req)
        )
    }

    // MARK: - Refresh Profile

    func refreshProfile() async throws {
        let profile: UserProfile = try await APIClient.shared.request(Endpoint.me)
        currentUser = profile
    }

    // MARK: - Private

    private func clearSession() {
        keychain.clearAll()
        currentUser     = nil
        isAuthenticated = false
    }
}
