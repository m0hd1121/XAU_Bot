// AppSettingsView.swift
// XAUBot – App Settings & Profile Management
// iOS 17+  |  Swift 5.9

import SwiftUI
import LocalAuthentication

struct AppSettingsView: View {

    @EnvironmentObject private var authService: AuthService
    @StateObject private var vm = AppSettingsViewModel()
    @State private var showLogoutConfirm = false
    @State private var showChangePassword = false
    @State private var show2FASetup = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: AppSpacing.sectionSpacing) {
                        profileCard
                        securitySection
                        serverSection
                        aboutSection
                        logoutButton
                        Color.clear.frame(height: AppSpacing.huge)
                    }
                    .padding(.horizontal, AppSpacing.screenPadding)
                    .padding(.top, AppSpacing.lg)
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.large)
            .sheet(isPresented: $showChangePassword) {
                ChangePasswordSheet(vm: vm)
            }
            .sheet(isPresented: $show2FASetup) {
                TwoFASetupSheet(vm: vm)
            }
            .alert("Logout", isPresented: $showLogoutConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Logout", role: .destructive) {
                    Task { await authService.logout() }
                }
            } message: {
                Text("You will need to log in again. WebSocket connection will close.")
            }
            .alert("Error", isPresented: .init(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.errorMessage = nil }
            } message: { Text(vm.errorMessage ?? "") }
            .alert("Success", isPresented: .init(
                get: { vm.successMessage != nil },
                set: { if !$0 { vm.successMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.successMessage = nil }
            } message: { Text(vm.successMessage ?? "") }
        }
        .task { await vm.loadProfile() }
    }

    // MARK: - Profile Card

    private var profileCard: some View {
        HStack(spacing: AppSpacing.md) {
            ZStack {
                Circle()
                    .fill(LinearGradient.goldGradient)
                    .frame(width: 56, height: 56)
                Text(String(vm.profile?.username.prefix(1).uppercased() ?? "?"))
                    .font(AppFont.displaySmall)
                    .foregroundColor(.black)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(vm.profile?.username ?? "Loading…")
                    .font(AppFont.headlineMedium)
                    .foregroundColor(.xauTextPrimary)
                HStack(spacing: 6) {
                    Text(vm.profile?.role.capitalized ?? "")
                        .font(AppFont.labelMedium)
                        .foregroundColor(.xauGold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.xauGold.opacity(0.15), in: Capsule())
                    if let lastLogin = vm.profile?.lastLogin {
                        Text("Last: \(lastLogin)")
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauTextTertiary)
                    }
                }
            }
            Spacer()
        }
        .padding(AppSpacing.cardPadding)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.xl))
        .overlay(RoundedRectangle(cornerRadius: AppRadius.xl)
            .strokeBorder(Color.xauGold.opacity(0.2), lineWidth: 0.5))
    }

    // MARK: - Security Section

    private var securitySection: some View {
        settingsGroup("Security", icon: "lock.shield.fill") {
            settingsRow(label: "Change Password", icon: "key.fill", color: .xauGold) {
                showChangePassword = true
            }

            settingsToggleRow(
                label: "2FA (TOTP)",
                icon: "qrcode",
                color: .xauInfo,
                enabled: vm.profile?.twoFaEnabled ?? false
            ) {
                show2FASetup = true
            }

            settingsToggleRow(
                label: "Biometric Login",
                icon: BiometricService.shared.biometricIcon,
                color: .xauProfit,
                enabled: vm.biometricEnabled
            ) {
                Task { await vm.toggleBiometric() }
            }
        }
    }

    // MARK: - Server Section

    private var serverSection: some View {
        settingsGroup("Server", icon: "server.rack") {
            VStack(alignment: .leading, spacing: 4) {
                Text("API URL")
                    .font(AppFont.labelSmall)
                    .foregroundColor(.xauTextTertiary)
                Text(vm.serverURL)
                    .font(AppFont.monoTiny)
                    .foregroundColor(.xauTextSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .padding(AppSpacing.cardPadding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.xauCard)
            .overlay(alignment: .bottom) { Divider().background(Color.xauBorder) }

            settingsRow(label: "Change Server URL", icon: "pencil", color: .xauGold) {
                vm.showEditURL = true
            }
        }
        .sheet(isPresented: $vm.showEditURL) { editURLSheet }
    }

    // MARK: - About Section

    private var aboutSection: some View {
        settingsGroup("About", icon: "info.circle.fill") {
            aboutRow("App Version", value: "1.0.0")
            aboutRow("Build", value: Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "—")
            aboutRow("iOS", value: UIDevice.current.systemVersion)
            aboutRow("Device", value: UIDevice.current.model)
        }
    }

    private func aboutRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(AppFont.bodySmall)
                .foregroundColor(.xauTextSecondary)
            Spacer()
            Text(value)
                .font(AppFont.monoSmall)
                .foregroundColor(.xauTextTertiary)
        }
        .padding(.horizontal, AppSpacing.cardPadding)
        .padding(.vertical, AppSpacing.sm)
        .overlay(alignment: .bottom) { Divider().background(Color.xauBorder) }
    }

    // MARK: - Logout

    private var logoutButton: some View {
        Button {
            showLogoutConfirm = true
        } label: {
            HStack {
                Image(systemName: "rectangle.portrait.and.arrow.right")
                Text("Logout")
            }
            .font(AppFont.headlineSmall)
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(AppSpacing.md)
            .background(Color.xauLoss)
            .clipShape(Capsule())
        }
    }

    // MARK: - Edit URL Sheet

    private var editURLSheet: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                VStack(spacing: AppSpacing.md) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("API Base URL")
                            .font(AppFont.labelMedium)
                            .foregroundColor(.xauTextTertiary)
                        TextField("https://your-vps.example.com:8443", text: $vm.editURL)
                            .keyboardType(.URL)
                            .autocapitalization(.none)
                            .font(AppFont.bodySmall)
                            .foregroundColor(.xauTextPrimary)
                            .padding(AppSpacing.cardPadding)
                            .background(Color.xauCard)
                            .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
                            .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
                                .strokeBorder(Color.xauBorder, lineWidth: 0.5))
                    }
                    .padding(.horizontal, AppSpacing.screenPadding)
                    .padding(.top, AppSpacing.xl)
                    Spacer()
                    Button {
                        vm.saveServerURL()
                    } label: {
                        Text("Save URL")
                            .font(AppFont.headlineSmall)
                            .foregroundColor(.black)
                            .frame(maxWidth: .infinity)
                            .padding(AppSpacing.md)
                            .background(LinearGradient.goldGradient)
                            .clipShape(Capsule())
                    }
                    .padding(.horizontal, AppSpacing.screenPadding)
                    .padding(.bottom, AppSpacing.xl)
                }
            }
            .navigationTitle("Server URL")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { vm.showEditURL = false }
                        .foregroundColor(.xauTextSecondary)
                }
            }
        }
    }

    // MARK: - Reusable Rows

    private func settingsGroup<Content: View>(_ title: String, icon: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.sm) {
            HStack(spacing: 6) {
                Image(systemName: icon).foregroundColor(.xauGold)
                Text(title).font(AppFont.headlineSmall).foregroundColor(.xauTextSecondary)
            }
            VStack(spacing: 0) { content() }
                .background(Color.xauCard)
                .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
                .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
                    .strokeBorder(Color.xauBorder, lineWidth: 0.5))
        }
    }

    private func settingsRow(label: String, icon: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                Image(systemName: icon)
                    .font(.system(size: 15))
                    .foregroundColor(color)
                    .frame(width: 24)
                Text(label)
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextPrimary)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 12))
                    .foregroundColor(.xauTextTertiary)
            }
            .padding(.horizontal, AppSpacing.cardPadding)
            .padding(.vertical, AppSpacing.sm)
        }
        .overlay(alignment: .bottom) { Divider().background(Color.xauBorder) }
    }

    private func settingsToggleRow(label: String, icon: String, color: Color, enabled: Bool, action: @escaping () -> Void) -> some View {
        HStack {
            Image(systemName: icon)
                .font(.system(size: 15))
                .foregroundColor(color)
                .frame(width: 24)
            Text(label)
                .font(AppFont.bodySmall)
                .foregroundColor(.xauTextPrimary)
            Spacer()
            Toggle("", isOn: .init(get: { enabled }, set: { _ in action() }))
                .tint(.xauGold)
                .labelsHidden()
        }
        .padding(.horizontal, AppSpacing.cardPadding)
        .padding(.vertical, AppSpacing.sm)
        .overlay(alignment: .bottom) { Divider().background(Color.xauBorder) }
    }
}

// MARK: - ChangePasswordSheet

private struct ChangePasswordSheet: View {
    @ObservedObject var vm: AppSettingsViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                VStack(spacing: AppSpacing.md) {
                    passwordField("Current Password", text: $vm.currentPassword)
                    passwordField("New Password", text: $vm.newPassword)
                    passwordField("Confirm New Password", text: $vm.confirmPassword)
                    Spacer()
                    Button {
                        Task {
                            await vm.changePassword()
                            if vm.successMessage != nil { dismiss() }
                        }
                    } label: {
                        Text("Update Password")
                            .font(AppFont.headlineSmall)
                            .foregroundColor(.black)
                            .frame(maxWidth: .infinity)
                            .padding(AppSpacing.md)
                            .background(LinearGradient.goldGradient)
                            .clipShape(Capsule())
                    }
                    .disabled(vm.newPassword.isEmpty || vm.newPassword != vm.confirmPassword)
                    .padding(.horizontal, AppSpacing.screenPadding)
                    .padding(.bottom, AppSpacing.xl)
                }
                .padding(.horizontal, AppSpacing.screenPadding)
                .padding(.top, AppSpacing.xl)
            }
            .navigationTitle("Change Password")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }.foregroundColor(.xauTextSecondary)
                }
            }
        }
    }

    private func passwordField(_ label: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(AppFont.labelMedium).foregroundColor(.xauTextTertiary)
            SecureField(label, text: text)
                .font(AppFont.bodySmall)
                .foregroundColor(.xauTextPrimary)
                .padding(AppSpacing.cardPadding)
                .background(Color.xauCard)
                .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
                .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
                    .strokeBorder(Color.xauBorder, lineWidth: 0.5))
        }
    }
}

// MARK: - 2FA Setup Sheet

private struct TwoFASetupSheet: View {
    @ObservedObject var vm: AppSettingsViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                VStack(spacing: AppSpacing.md) {
                    if let profile = vm.profile, profile.twoFaEnabled {
                        VStack(spacing: AppSpacing.md) {
                            Image(systemName: "checkmark.shield.fill")
                                .font(.system(size: 48))
                                .foregroundColor(.xauProfit)
                            Text("2FA is currently enabled.")
                                .font(AppFont.headlineSmall)
                                .foregroundColor(.xauTextPrimary)
                            Button("Disable 2FA") {
                                Task { await vm.disable2FA(); dismiss() }
                            }
                            .buttonStyle(DestructiveButtonStyle())
                        }
                    } else {
                        Text("Scan the QR code in your authenticator app, then enter the 6-digit code.")
                            .font(AppFont.bodySmall)
                            .foregroundColor(.xauTextSecondary)
                            .multilineTextAlignment(.center)
                        // TOTP verification field
                        TextField("6-digit code", text: $vm.totpCode)
                            .keyboardType(.numberPad)
                            .font(AppFont.monoMedium)
                            .foregroundColor(.xauTextPrimary)
                            .multilineTextAlignment(.center)
                            .padding(AppSpacing.cardPadding)
                            .background(Color.xauCard)
                            .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
                        Button("Enable 2FA") {
                            Task { await vm.enable2FA(); dismiss() }
                        }
                        .buttonStyle(GoldButtonStyle(isFullWidth: true))
                        .disabled(vm.totpCode.count != 6)
                    }
                    Spacer()
                }
                .padding(.horizontal, AppSpacing.screenPadding)
                .padding(.top, AppSpacing.xl)
            }
            .navigationTitle("Two-Factor Auth")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }.foregroundColor(.xauTextSecondary)
                }
            }
        }
    }
}

// MARK: - AppSettingsViewModel

@MainActor
final class AppSettingsViewModel: ObservableObject {
    @Published var profile: UserProfile?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var successMessage: String?
    @Published var showEditURL = false

    // Password change
    @Published var currentPassword = ""
    @Published var newPassword = ""
    @Published var confirmPassword = ""

    // 2FA
    @Published var totpCode = ""

    // Server
    @Published var editURL = ""
    var serverURL: String { KeychainService.shared.retrieveString(for: .serverURL) ?? "Not set" }

    var biometricEnabled: Bool {
        UserDefaults.standard.bool(forKey: "biometricEnabled")
    }

    func loadProfile() async {
        isLoading = true
        defer { isLoading = false }
        do {
            profile = try await APIClient.shared.request(Endpoint.me)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func changePassword() async {
        do {
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.changePassword(request: ChangePasswordRequest(
                    currentPassword: currentPassword,
                    newPassword: newPassword
                ))
            )
            currentPassword = ""; newPassword = ""; confirmPassword = ""
            successMessage = "Password changed successfully."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func enable2FA() async {
        do {
            let _: MessageResponse = try await APIClient.shared.request(Endpoint.me)
            successMessage = "2FA enabled."
            await loadProfile()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func disable2FA() async {
        do {
            let _: MessageResponse = try await APIClient.shared.request(Endpoint.me)
            successMessage = "2FA disabled."
            await loadProfile()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func toggleBiometric() async {
        let current = UserDefaults.standard.bool(forKey: "biometricEnabled")
        if !current {
            let result = await BiometricService.shared.authenticate(reason: "Enable biometric login")
            if result {
                UserDefaults.standard.set(true, forKey: "biometricEnabled")
                successMessage = "Biometric login enabled."
            } else {
                errorMessage = "Biometric authentication failed."
            }
        } else {
            UserDefaults.standard.set(false, forKey: "biometricEnabled")
            successMessage = "Biometric login disabled."
        }
        objectWillChange.send()
    }

    func saveServerURL() {
        guard !editURL.isEmpty else { return }
        KeychainService.shared.store(editURL, for: .serverURL)
        showEditURL = false
        successMessage = "Server URL updated."
        objectWillChange.send()
    }
}
