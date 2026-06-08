import SwiftUI

struct LoginView: View {
    @StateObject private var vm = AuthViewModel()
    @FocusState private var focused: LoginField?
    @State private var showPassword = false

    enum LoginField { case serverURL, username, password, totp }

    var body: some View {
        ZStack {
            LinearGradient.backgroundGradient.ignoresSafeArea()

            ScrollView {
                VStack(spacing: AppSpacing.xxl) {
                    logoSection
                    formSection
                    actionSection
                }
                .padding(.horizontal, AppSpacing.xxl)
                .padding(.top, 60)
            }
        }
        .loadingOverlay(vm.isLoading, message: "Logging in…")
    }

    // MARK: - Logo

    private var logoSection: some View {
        VStack(spacing: AppSpacing.md) {
            Image(systemName: "chart.line.uptrend.xyaxis.circle.fill")
                .font(.system(size: 72))
                .foregroundStyle(LinearGradient.goldGradient)
            Text("XAU Bot")
                .font(AppFont.largeTitle())
                .foregroundStyle(LinearGradient.goldGradient)
            Text("Trading Command Center")
                .font(AppFont.subheadline())
                .foregroundColor(.textSecondary)
        }
        .padding(.bottom, AppSpacing.lg)
    }

    // MARK: - Form

    private var formSection: some View {
        VStack(spacing: AppSpacing.md) {
            if let err = vm.errorMessage {
                HStack {
                    Image(systemName: "exclamationmark.circle")
                    Text(err)
                        .font(AppFont.footnote())
                }
                .foregroundColor(.lossRed)
                .padding(AppSpacing.md)
                .background(Color.lossRed.opacity(0.15))
                .cornerRadius(AppRadius.md)
            }

            loginField("Server URL", text: $vm.serverURL, icon: "server.rack",
                       keyboardType: .URL, field: .serverURL)
            loginField("Username",   text: $vm.username,  icon: "person.fill",
                       field: .username)

            ZStack(alignment: .trailing) {
                if showPassword {
                    loginField("Password", text: $vm.password, icon: "lock.fill",
                               field: .password)
                } else {
                    secureField()
                }
                Button {
                    showPassword.toggle()
                } label: {
                    Image(systemName: showPassword ? "eye.slash" : "eye")
                        .foregroundColor(.textSecondary)
                        .padding(.trailing, AppSpacing.lg)
                }
            }

            if vm.requires2FA {
                loginField("2FA Code", text: $vm.totpCode, icon: "key.fill",
                           keyboardType: .numberPad, field: .totp)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.spring(response: 0.4), value: vm.requires2FA)
    }

    private func loginField(_ placeholder: String, text: Binding<String>,
                            icon: String, keyboardType: UIKeyboardType = .default,
                            field: LoginField) -> some View {
        HStack(spacing: AppSpacing.md) {
            Image(systemName: icon)
                .foregroundColor(.goldAccent)
                .frame(width: 20)
            TextField(placeholder, text: text)
                .keyboardType(keyboardType)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .focused($focused, equals: field)
                .foregroundColor(.textPrimary)
        }
        .padding()
        .background(Color.appCard)
        .cornerRadius(AppRadius.md)
        .overlay(RoundedRectangle(cornerRadius: AppRadius.md)
            .stroke(focused == field ? Color.goldAccent : Color.borderColor, lineWidth: 1))
    }

    private func secureField() -> some View {
        HStack(spacing: AppSpacing.md) {
            Image(systemName: "lock.fill")
                .foregroundColor(.goldAccent)
                .frame(width: 20)
            SecureField("Password", text: $vm.password)
                .focused($focused, equals: .password)
                .foregroundColor(.textPrimary)
        }
        .padding()
        .background(Color.appCard)
        .cornerRadius(AppRadius.md)
        .overlay(RoundedRectangle(cornerRadius: AppRadius.md)
            .stroke(focused == .password ? Color.goldAccent : Color.borderColor, lineWidth: 1))
    }

    // MARK: - Actions

    private var actionSection: some View {
        VStack(spacing: AppSpacing.md) {
            Button {
                Task { await vm.login() }
            } label: {
                Text(vm.requires2FA ? "Verify 2FA" : "Sign In")
                    .font(AppFont.headline())
                    .foregroundColor(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, AppSpacing.lg)
                    .background(vm.canSubmit ? LinearGradient.goldGradient : LinearGradient(colors: [.gray], startPoint: .leading, endPoint: .trailing))
                    .cornerRadius(AppRadius.lg)
            }
            .disabled(!vm.canSubmit)

            if BiometricService.shared.canUseBiometrics {
                Button {
                    Task { await vm.biometricLogin() }
                } label: {
                    Label(BiometricService.shared.biometricTypeName, systemImage: BiometricService.shared.biometricIcon)
                        .font(AppFont.headline())
                        .foregroundColor(.goldAccent)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, AppSpacing.lg)
                        .background(Color.appCard)
                        .cornerRadius(AppRadius.lg)
                        .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
                            .stroke(Color.goldAccent.opacity(0.4), lineWidth: 1))
                }
            }
        }
    }
}
