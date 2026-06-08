// AccountView.swift
// XAUBot – Trading Account Management
// iOS 17+  |  Swift 5.9

import Combine
import SwiftUI

struct AccountView: View {

    @StateObject private var vm = AccountViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                content
            }
            .navigationTitle("Account")
            .navigationBarTitleDisplayMode(.large)
            .toolbar { toolbarContent }
            .sheet(isPresented: $vm.showAddAccount) { addAccountSheet }
            .alert("Disconnect Account", isPresented: $vm.showDisconnectConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Disconnect", role: .destructive) {
                    guard let id = vm.accountToDisconnect else { return }
                    Task { await vm.deleteAccount(id: id) }
                }
            } message: {
                Text("Remove this account from the bot? This cannot be undone without re-adding it.")
            }
            .alert("Error", isPresented: .init(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.errorMessage = nil }
            } message: { Text(vm.errorMessage ?? "") }
        }
        .task { await vm.load() }
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if vm.isLoading && vm.currentAccount == nil {
            ProgressView("Loading account…").tint(.xauGold)
        } else {
            ScrollView {
                VStack(spacing: AppSpacing.sectionSpacing) {
                    if let account = vm.currentAccount {
                        activeAccountCard(account)
                        balanceBreakdown(account)
                    } else {
                        noAccountCard
                    }

                    if !vm.accounts.isEmpty {
                        accountListSection
                    }

                    Color.clear.frame(height: AppSpacing.huge)
                }
                .padding(.horizontal, AppSpacing.screenPadding)
                .padding(.top, AppSpacing.lg)
            }
            .refreshable { await vm.load() }
        }
    }

    // MARK: - Active Account Card

    private func activeAccountCard(_ account: AccountInfo) -> some View {
        VStack(spacing: AppSpacing.md) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(account.broker)
                        .font(AppFont.headlineMedium)
                        .foregroundColor(.xauTextPrimary)
                    Text("#\(account.accountNumber)")
                        .font(AppFont.monoSmall)
                        .foregroundColor(.xauTextTertiary)
                }
                Spacer()
                HStack(spacing: 6) {
                    Circle()
                        .fill(account.connected ? Color.xauProfit : Color.xauLoss)
                        .frame(width: 8, height: 8)
                    Text(account.connected ? "Connected" : "Disconnected")
                        .font(AppFont.labelMedium)
                        .foregroundColor(account.connected ? .xauProfit : .xauLoss)
                }
            }

            Divider().background(Color.xauBorder)

            HStack(spacing: AppSpacing.xl) {
                accountStat("Balance",   AppFormat.usd(account.balance))
                accountStat("Equity",    AppFormat.usd(account.equity))
                accountStat("Leverage",  "1:\(account.leverage)")
                if let latency = account.latencyMs {
                    accountStat("Latency", "\(latency) ms",
                                color: latency < 100 ? .xauProfit : latency < 300 ? .xauWarning : .xauLoss)
                }
            }

            HStack {
                infoTag(account.server)
                infoTag(account.currency)
                Spacer()
            }
        }
        .padding(AppSpacing.cardPadding)
        .background(
            LinearGradient(
                colors: [Color.xauCard, Color.xauGold.opacity(0.05)],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.xl))
        .overlay(
            RoundedRectangle(cornerRadius: AppRadius.xl)
                .strokeBorder(Color.xauGold.opacity(0.3), lineWidth: 1)
        )
        .cardShadow()
    }

    private func accountStat(_ label: String, _ value: String, color: Color = .xauTextPrimary) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(AppFont.labelSmall)
                .foregroundColor(.xauTextTertiary)
            Text(value)
                .font(AppFont.monoSmall)
                .foregroundColor(color)
        }
    }

    private func infoTag(_ text: String) -> some View {
        Text(text)
            .font(AppFont.labelSmall)
            .foregroundColor(.xauTextTertiary)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.xauBorder, in: Capsule())
    }

    // MARK: - Balance Breakdown

    private func balanceBreakdown(_ account: AccountInfo) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            sectionHeader("Margin", icon: "chart.pie.fill")

            HStack {
                marginRow("Free Margin",  AppFormat.usd(account.freeMargin), color: .xauProfit)
                Spacer()
                marginRow("Used Margin",  AppFormat.usd(account.margin), color: .xauWarning)
                Spacer()
                if let ml = account.marginLevel {
                    marginRow("Margin Level", String(format: "%.1f%%", ml),
                              color: ml > 500 ? .xauProfit : ml > 200 ? .xauWarning : .xauLoss)
                }
            }

            // Margin usage bar
            if let ml = account.marginLevel {
                let usage = min(1.0, account.margin / max(1, account.equity))
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.xauBorder).frame(height: 6)
                        Capsule()
                            .fill(ml > 500 ? Color.xauProfit : ml > 200 ? Color.xauWarning : Color.xauLoss)
                            .frame(width: geo.size.width * usage, height: 6)
                    }
                }
                .frame(height: 6)
            }
        }
        .padding(AppSpacing.cardPadding)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
            .strokeBorder(Color.xauBorder, lineWidth: 0.5))
    }

    private func marginRow(_ label: String, _ value: String, color: Color) -> some View {
        VStack(alignment: .center, spacing: 2) {
            Text(label).font(AppFont.labelSmall).foregroundColor(.xauTextTertiary)
            Text(value).font(AppFont.monoSmall).foregroundColor(color)
        }
    }

    // MARK: - No Account Card

    private var noAccountCard: some View {
        VStack(spacing: AppSpacing.md) {
            Image(systemName: "xmark.circle")
                .font(.system(size: 40))
                .foregroundColor(.xauNeutral)
            Text("No Account Connected")
                .font(AppFont.headlineSmall)
                .foregroundColor(.xauTextSecondary)
            Text("Add a broker account to enable live trading.")
                .font(AppFont.bodySmall)
                .foregroundColor(.xauTextTertiary)
                .multilineTextAlignment(.center)
            Button {
                vm.showAddAccount = true
            } label: {
                Label("Add Account", systemImage: "plus")
            }
            .buttonStyle(GoldButtonStyle())
        }
        .padding(AppSpacing.xxxl)
        .frame(maxWidth: .infinity)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.xl))
        .overlay(RoundedRectangle(cornerRadius: AppRadius.xl)
            .strokeBorder(Color.xauBorder, lineWidth: 0.5))
    }

    // MARK: - Account List

    private var accountListSection: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            sectionHeader("Saved Accounts", icon: "person.2.fill")
            ForEach(vm.accounts, id: \.self) { accountId in
                HStack {
                    Text(accountId)
                        .font(AppFont.bodySmall)
                        .foregroundColor(.xauTextPrimary)
                    Spacer()
                    Button {
                        Task { await vm.reconnect(id: accountId) }
                    } label: {
                        Text("Connect")
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauGold)
                    }
                    Button {
                        vm.accountToDisconnect = accountId
                        vm.showDisconnectConfirm = true
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 14))
                            .foregroundColor(.xauLoss)
                    }
                }
                .padding(AppSpacing.cardPadding)
                .background(Color.xauCard)
                .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))
            }
        }
    }

    // MARK: - Add Account Sheet

    private var addAccountSheet: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                VStack(spacing: AppSpacing.md) {
                    accountField("Broker Server", binding: $vm.newServer, placeholder: "e.g. MetaQuotes-Demo")
                    accountField("Account Number", binding: $vm.newLogin, placeholder: "e.g. 123456", keyboard: .numberPad)
                    accountField("Password", binding: $vm.newPassword, placeholder: "Trader password", isSecure: true)

                    Spacer()

                    Button {
                        Task { await vm.addAccount() }
                    } label: {
                        HStack {
                            Image(systemName: "plus.circle.fill")
                            Text("Add Account")
                        }
                        .font(AppFont.headlineSmall)
                        .foregroundColor(.black)
                        .frame(maxWidth: .infinity)
                        .padding(AppSpacing.md)
                        .background(LinearGradient.goldGradient)
                        .clipShape(Capsule())
                    }
                    .disabled(vm.newLogin.isEmpty || vm.newPassword.isEmpty || vm.newServer.isEmpty)
                    .padding(.horizontal, AppSpacing.screenPadding)
                }
                .padding(.top, AppSpacing.lg)
            }
            .navigationTitle("Add Account")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { vm.showAddAccount = false }
                        .foregroundColor(.xauTextSecondary)
                }
            }
        }
    }

    private func accountField(_ label: String, binding: Binding<String>,
                               placeholder: String, keyboard: UIKeyboardType = .default, isSecure: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(AppFont.labelMedium)
                .foregroundColor(.xauTextTertiary)
                .padding(.horizontal, AppSpacing.screenPadding)
            Group {
                if isSecure {
                    SecureField(placeholder, text: binding)
                } else {
                    TextField(placeholder, text: binding)
                        .keyboardType(keyboard)
                }
            }
            .font(AppFont.bodySmall)
            .foregroundColor(.xauTextPrimary)
            .padding(AppSpacing.cardPadding)
            .background(Color.xauCard)
            .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
            .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
                .strokeBorder(Color.xauBorder, lineWidth: 0.5))
            .padding(.horizontal, AppSpacing.screenPadding)
        }
    }

    // MARK: - Helpers

    private func sectionHeader(_ title: String, icon: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon).foregroundColor(.xauGold)
            Text(title).font(AppFont.headlineSmall).foregroundColor(.xauTextSecondary)
        }
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button { vm.showAddAccount = true } label: {
                Image(systemName: "plus.circle.fill").foregroundColor(.xauGold)
            }
        }
        ToolbarItem(placement: .topBarTrailing) {
            Button { Task { await vm.load() } } label: {
                Image(systemName: "arrow.clockwise").foregroundColor(.xauTextSecondary)
            }
            .disabled(vm.isLoading)
        }
    }
}

// MARK: - AccountViewModel

@MainActor
final class AccountViewModel: ObservableObject {
    @Published var currentAccount: AccountInfo?
    @Published var accounts: [String] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var showAddAccount = false
    @Published var showDisconnectConfirm = false
    @Published var accountToDisconnect: String?

    // Add form fields
    @Published var newServer = ""
    @Published var newLogin = ""
    @Published var newPassword = ""

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            currentAccount = try await APIClient.shared.request(Endpoint.accountInfo)
        } catch {
            // Not fatal — may just mean no account connected
        }
    }

    func addAccount() async {
        do {
            let payload: [String: String] = [
                "server": newServer,
                "login": newLogin,
                "password": newPassword
            ]
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.addAccount(payload: payload)
            )
            newServer = ""; newLogin = ""; newPassword = ""
            showAddAccount = false
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func reconnect(id: String) async {
        do {
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.reconnectAccount(id: id)
            )
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteAccount(id: String) async {
        do {
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.deleteAccount(id: id)
            )
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
