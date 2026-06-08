// NotificationPreferencesView.swift
// XAUBot – Push Notification Preferences
// iOS 17+  |  Swift 5.9

import Combine
import SwiftUI

struct NotificationPreferencesView: View {

    @StateObject private var vm = NotificationPreferencesViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                content
            }
            .navigationTitle("Notifications")
            .navigationBarTitleDisplayMode(.large)
            .toolbar { toolbarContent }
            .alert("Error", isPresented: .init(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.errorMessage = nil }
            } message: { Text(vm.errorMessage ?? "") }
            .overlay { if vm.isSaving { LoadingOverlayView(message: "Saving…") } }
        }
        .task { await vm.load() }
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if vm.isLoading {
            ProgressView("Loading preferences…").tint(.xauGold)
        } else if let prefs = vm.prefs {
            ScrollView {
                VStack(spacing: AppSpacing.sectionSpacing) {
                    apnsStatusCard
                    prefGroup("Trade Events", icon: "chart.line.uptrend.xyaxis") {
                        prefRow("Trade Opened",  push: binding(prefs, for: \.tradeOpened))
                        prefRow("Trade Closed",  push: binding(prefs, for: \.tradeClosed))
                        prefRow("Daily Summary", push: binding(prefs, for: \.dailySummary))
                    }
                    prefGroup("Risk Alerts", icon: "exclamationmark.shield.fill") {
                        prefRowWithThreshold("Drawdown Warning", push: binding(prefs, for: \.drawdownWarning),
                                             threshold: thresholdBinding(prefs, for: \.drawdownWarning))
                        prefRow("Risk Limit Hit",   push: binding(prefs, for: \.riskLimit))
                        prefRow("Critical Errors",  push: binding(prefs, for: \.criticalErrors))
                    }
                    prefGroup("System Events", icon: "server.rack") {
                        prefRow("VPS Offline",         push: binding(prefs, for: \.vpsOffline))
                        prefRow("Broker Disconnected", push: binding(prefs, for: \.brokerDisconnected))
                        prefRow("Bot Stopped",         push: binding(prefs, for: \.botStopped))
                        prefRow("Learning Completed",  push: binding(prefs, for: \.learningCompleted))
                    }
                    saveButton
                    Color.clear.frame(height: AppSpacing.huge)
                }
                .padding(.horizontal, AppSpacing.screenPadding)
                .padding(.top, AppSpacing.lg)
            }
        } else {
            EmptyStateView(icon: "bell.slash", title: "Preferences Unavailable",
                           subtitle: vm.errorMessage ?? "Could not load notification settings.",
                           actionTitle: "Retry",
                           action: { Task { await vm.load() } })
        }
    }

    // MARK: - APNs Status Card

    private var apnsStatusCard: some View {
        HStack(spacing: AppSpacing.md) {
            Image(systemName: vm.apnsRegistered ? "checkmark.seal.fill" : "xmark.seal.fill")
                .font(.system(size: 28))
                .foregroundColor(vm.apnsRegistered ? .xauProfit : .xauLoss)

            VStack(alignment: .leading, spacing: 2) {
                Text("Push Notifications")
                    .font(AppFont.headlineSmall)
                    .foregroundColor(.xauTextPrimary)
                Text(vm.apnsRegistered ? "Device registered for push" : "Device not registered")
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextTertiary)
            }

            Spacer()

            if !vm.apnsRegistered {
                Button("Enable") {
                    Task { await NotificationService.shared.requestAuthorization() }
                }
                .buttonStyle(GoldButtonStyle())
            }
        }
        .padding(AppSpacing.cardPadding)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
            .strokeBorder(Color.xauBorder, lineWidth: 0.5))
    }

    // MARK: - Pref Group

    private func prefGroup<Content: View>(_ title: String, icon: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.sm) {
            HStack(spacing: 6) {
                Image(systemName: icon).foregroundColor(.xauGold)
                Text(title).font(AppFont.headlineSmall).foregroundColor(.xauTextSecondary)
            }
            VStack(spacing: 0) {
                content()
            }
            .background(Color.xauCard)
            .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
            .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
                .strokeBorder(Color.xauBorder, lineWidth: 0.5))
        }
    }

    private func prefRow(_ label: String, push: Binding<Bool>) -> some View {
        HStack {
            Text(label)
                .font(AppFont.bodySmall)
                .foregroundColor(.xauTextPrimary)
            Spacer()
            Toggle("", isOn: push)
                .tint(.xauGold)
                .labelsHidden()
                .onChange(of: push.wrappedValue) { vm.markDirty() }
        }
        .padding(.horizontal, AppSpacing.cardPadding)
        .padding(.vertical, AppSpacing.sm)
        .overlay(alignment: .bottom) { Divider().background(Color.xauBorder) }
    }

    private func prefRowWithThreshold(_ label: String, push: Binding<Bool>, threshold: Binding<String>) -> some View {
        VStack(spacing: 0) {
            prefRow(label, push: push)
            if push.wrappedValue {
                HStack {
                    Text("Threshold %")
                        .font(AppFont.labelSmall)
                        .foregroundColor(.xauTextTertiary)
                    Spacer()
                    TextField("e.g. 5.0", text: threshold)
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.trailing)
                        .font(AppFont.monoSmall)
                        .foregroundColor(.xauGold)
                        .frame(width: 80)
                        .onChange(of: threshold.wrappedValue) { vm.markDirty() }
                }
                .padding(.horizontal, AppSpacing.cardPadding)
                .padding(.vertical, AppSpacing.sm)
                .background(Color.xauGold.opacity(0.05))
                .overlay(alignment: .bottom) { Divider().background(Color.xauBorder) }
            }
        }
    }

    // MARK: - Save Button

    private var saveButton: some View {
        Button {
            Task { await vm.save() }
        } label: {
            Text("Save Preferences")
                .font(AppFont.headlineSmall)
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .padding(AppSpacing.md)
                .background(vm.isDirty ? LinearGradient.goldGradient : LinearGradient(colors: [.xauNeutral], startPoint: .leading, endPoint: .trailing))
                .clipShape(Capsule())
        }
        .disabled(!vm.isDirty || vm.isSaving)
    }

    // MARK: - Bindings

    private func binding(_ prefs: NotificationPrefs, for kp: WritableKeyPath<NotificationPrefs, NotificationPrefs.NotifPref>) -> Binding<Bool> {
        Binding(
            get: { vm.prefs?[keyPath: kp].pushEnabled ?? false },
            set: { vm.updatePref(kp, pushEnabled: $0) }
        )
    }

    private func thresholdBinding(_ prefs: NotificationPrefs, for kp: WritableKeyPath<NotificationPrefs, NotificationPrefs.NotifPref>) -> Binding<String> {
        Binding(
            get: {
                if let t = vm.prefs?[keyPath: kp].threshold { return String(format: "%.1f", t) }
                return ""
            },
            set: { vm.updatePrefThreshold(kp, threshold: Double($0)) }
        )
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button { Task { await vm.load() } } label: {
                Image(systemName: "arrow.clockwise").foregroundColor(.xauTextSecondary)
            }
        }
    }
}

// MARK: - ViewModel

@MainActor
final class NotificationPreferencesViewModel: ObservableObject {
    @Published var prefs: NotificationPrefs?
    @Published var isLoading = false
    @Published var isSaving = false
    @Published var errorMessage: String?
    @Published var isDirty = false

    var apnsRegistered: Bool {
        UserDefaults.standard.string(forKey: "apnsToken") != nil
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            prefs = try await APIClient.shared.request(Endpoint.getNotificationPrefs)
            isDirty = false
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func save() async {
        guard let p = prefs else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.updateNotificationPrefs(prefs: p)
            )
            isDirty = false
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func markDirty() { isDirty = true }

    func updatePref(_ kp: WritableKeyPath<NotificationPrefs, NotificationPrefs.NotifPref>, pushEnabled: Bool) {
        prefs?[keyPath: kp].pushEnabled = pushEnabled
        isDirty = true
    }

    func updatePrefThreshold(_ kp: WritableKeyPath<NotificationPrefs, NotificationPrefs.NotifPref>, threshold: Double?) {
        prefs?[keyPath: kp].threshold = threshold
        isDirty = true
    }
}
