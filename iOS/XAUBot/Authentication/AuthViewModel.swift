import SwiftUI
import Combine

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var username      = ""
    @Published var password      = ""
    @Published var serverURL     = ""
    @Published var totpCode      = ""
    @Published var isLoading     = false
    @Published var errorMessage: String?
    @Published var requires2FA   = false

    private var cancellables = Set<AnyCancellable>()

    init() {
        serverURL = KeychainService.shared.retrieveString(forKey: .serverURL) ?? ""
    }

    var canSubmit: Bool {
        !username.isEmpty && !password.isEmpty && !serverURL.isEmpty && !isLoading
    }

    func login() async {
        guard canSubmit else { return }
        isLoading = true
        errorMessage = nil

        // Save server URL
        _ = KeychainService.shared.save(string: serverURL, forKey: .serverURL)
        APIClient.shared.updateBaseURL(serverURL)

        do {
            let response = try await APIClient.shared.login(
                username: username,
                password: password,
                totpCode: requires2FA ? totpCode : nil
            )
            if response.requires2FA {
                requires2FA = true
                isLoading   = false
                return
            }
            await AuthService.shared.handleSuccessfulLogin(response)
        } catch let error as APIError {
            errorMessage = error.localizedDescription
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func biometricLogin() async {
        isLoading = true
        let result = await BiometricService.shared.authenticate(reason: "Log in to XAU Bot")
        switch result {
        case .success:
            if let token = KeychainService.shared.retrieveString(forKey: .accessToken) {
                await AuthService.shared.restoreSession(token: token)
            } else {
                errorMessage = "No saved session. Please log in with password."
            }
        case .failure(let err):
            errorMessage = err.localizedDescription
        }
        isLoading = false
    }
}
