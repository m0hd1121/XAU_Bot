// BotControlView.swift
// XAUBot – Full bot control panel with animations, confirmations, activity log
// iOS 17+  |  Swift 5.9

import SwiftUI

struct BotControlView: View {
    @StateObject private var vm = BotControlViewModel()

    var body: some View {
        ZStack {
            Color.xauPrimary.ignoresSafeArea()

            ScrollView {
                VStack(spacing: AppSpacing.sectionSpacing) {
                    // Big status indicator
                    statusHero

                    // Primary controls
                    primaryControls

                    // Mode selector
                    modeSelector

                    // Mode toggles
                    modeToggles

                    // Service restarts
                    serviceRestarts

                    // Activity log
                    activityLog

                    Color.clear.frame(height: AppSpacing.huge)
                }
                .padding(.horizontal, AppSpacing.screenPadding)
                .padding(.top, AppSpacing.lg)
            }
            .refreshable { await vm.load() }
            .loadingOverlay(vm.isLoading, message: "Executing…")
        }
        .navigationTitle("Bot Control")
        .navigationBarTitleDisplayMode(.large)
        .confirmationAlert(config: $vm.confirmationConfig)
        .task { await vm.load() }
    }

    // MARK: - Status Hero

    private var statusHero: some View {
        VStack(spacing: AppSpacing.lg) {
            ZStack {
                Circle()
                    .fill(statusColor.opacity(0.08))
                    .frame(width: 140, height: 140)
                Circle()
                    .fill(statusColor.opacity(0.04))
                    .frame(width: 170, height: 170)

                if let status = vm.botStatus {
                    PulsingDot(status: status.pulseStatus, size: 20)
                } else {
                    ProgressView().scaleEffect(1.3)
                }
            }

            VStack(spacing: AppSpacing.xs) {
                Text(vm.botStatus?.statusLabel ?? "Loading…")
                    .font(AppFont.displaySmall)
                    .foregroundColor(.xauTextPrimary)
                    .contentTransition(.interpolate)

                if let status = vm.botStatus {
                    Text("Mode: \(status.mode.uppercased()) | PID: \(status.pid.map(String.init) ?? "—")")
                        .font(AppFont.caption)
                        .foregroundColor(.xauTextTertiary)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, AppSpacing.xl)
    }

    // MARK: - Primary Controls

    private var primaryControls: some View {
        VStack(spacing: AppSpacing.md) {
            sectionTitle("Controls")

            let isRunning = vm.botStatus?.running ?? false
            let isPaused  = vm.botStatus?.paused  ?? false

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())],
                      spacing: AppSpacing.md) {

                controlButton("Start",   icon: "play.fill",         color: .xauProfit,  enabled: !isRunning)   { vm.requestStart() }
                controlButton("Stop",    icon: "stop.fill",          color: .xauLoss,    enabled: isRunning)    { vm.requestStop() }
                controlButton("Restart", icon: "arrow.clockwise",    color: .xauWarning, enabled: isRunning)    { vm.requestRestart() }
                controlButton(isPaused ? "Resume" : "Pause",
                              icon: isPaused ? "play.fill" : "pause.fill",
                              color: .xauInfo, enabled: isRunning)                                              { vm.requestPause() }
            }

            // Emergency Stop – full width, prominent
            Button {
                vm.requestEmergencyStop()
            } label: {
                HStack(spacing: AppSpacing.sm) {
                    Image(systemName: "exclamationmark.octagon.fill")
                        .font(.title3)
                    Text("EMERGENCY STOP")
                        .font(AppFont.headlineSmall)
                        .tracking(1)
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, AppSpacing.lg)
                .background(
                    LinearGradient(
                        colors: [Color.xauLoss, Color(red: 0.7, green: 0, blue: 0.1)],
                        startPoint: .leading, endPoint: .trailing
                    )
                )
                .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))
                .appShadow(AppShadow.lossGlow)
            }
        }
    }

    // MARK: - Mode Selector

    private let botModes = ["backtest", "paper", "live"]

    private var modeSelector: some View {
        let isRunning   = vm.botStatus?.running ?? false
        let currentMode = vm.botStatus?.mode.lowercased() ?? "paper"

        return VStack(spacing: AppSpacing.md) {
            sectionTitle("Operating Mode")

            VStack(spacing: AppSpacing.sm) {
                Picker("Mode", selection: Binding<String>(
                    get: { currentMode },
                    set: { newMode in
                        if newMode != currentMode {
                            vm.requestSetMode(newMode)
                        }
                    }
                )) {
                    Text("Backtest").tag("backtest")
                    Text("Paper").tag("paper")
                    Text("Live").tag("live")
                }
                .pickerStyle(.segmented)
                .disabled(isRunning)

                if isRunning {
                    Text("Stop the bot to change mode")
                        .font(AppFont.caption)
                        .foregroundColor(.xauTextTertiary)
                        .frame(maxWidth: .infinity, alignment: .center)
                } else {
                    Text(modeSublabel(currentMode))
                        .font(AppFont.caption)
                        .foregroundColor(.xauTextTertiary)
                        .frame(maxWidth: .infinity, alignment: .center)
                }
            }
            .padding(AppSpacing.lg)
            .background(Color.xauCard)
            .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
            .overlay(
                RoundedRectangle(cornerRadius: AppRadius.lg)
                    .strokeBorder(Color.xauBorder, lineWidth: 0.5)
            )
        }
    }

    private func modeSublabel(_ mode: String) -> String {
        switch mode {
        case "backtest": return "Replay historical data — no real-time execution"
        case "paper":    return "Simulated trading on live prices — no real funds"
        case "live":     return "Real execution via connected broker — use with caution"
        default:         return ""
        }
    }

    // MARK: - Mode Toggles

    private var modeToggles: some View {
        VStack(spacing: AppSpacing.md) {
            sectionTitle("Modes")

            VStack(spacing: 1) {
                toggleRow(
                    "Learning Engine",
                    icon: "brain.head.profile",
                    color: .xauGold,
                    isOn: vm.botStatus?.learningEnabled ?? false
                ) { vm.requestToggleLearning() }

                Divider().background(Color.xauBorder)

                toggleRow(
                    "Maintenance Mode",
                    icon: "wrench.and.screwdriver.fill",
                    color: .xauWarning,
                    isOn: vm.botStatus?.maintenanceMode ?? false
                ) { vm.requestToggleMaintenance() }
            }
            .background(Color.xauCard)
            .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
            .overlay(
                RoundedRectangle(cornerRadius: AppRadius.lg)
                    .strokeBorder(Color.xauBorder, lineWidth: 0.5)
            )
        }
    }

    // MARK: - Service Restarts

    private var serviceRestarts: some View {
        VStack(spacing: AppSpacing.md) {
            sectionTitle("Services")

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())],
                      spacing: AppSpacing.sm) {
                serviceButton("Bot",     name: "xaubot")
                serviceButton("API",     name: "xaubot-api")
                serviceButton("Worker",  name: "xaubot-worker")
            }
        }
    }

    // MARK: - Activity Log

    private var activityLog: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            sectionTitle("Recent Activity")

            if vm.recentActions.isEmpty {
                Text("No recent actions")
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextTertiary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, AppSpacing.xl)
            } else {
                ForEach(vm.recentActions.prefix(10)) { log in
                    HStack(spacing: AppSpacing.sm) {
                        Image(systemName: log.success ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .foregroundColor(log.success ? .xauProfit : .xauLoss)
                            .font(.callout)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(log.action)
                                .font(AppFont.bodySmall)
                                .foregroundColor(.xauTextPrimary)
                            Text(log.result)
                                .font(AppFont.caption)
                                .foregroundColor(.xauTextTertiary)
                        }
                        Spacer()
                        Text(timeAgo(log.timestamp))
                            .font(AppFont.caption)
                            .foregroundColor(.xauTextTertiary)
                    }
                    .padding(AppSpacing.md)
                    .background(Color.xauCard)
                    .clipShape(RoundedRectangle(cornerRadius: AppRadius.sm))
                }
            }
        }
    }

    // MARK: - Sub-components

    private func sectionTitle(_ title: String) -> some View {
        Text(title)
            .font(AppFont.headlineSmall)
            .foregroundColor(.xauTextSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func controlButton(_ title: String, icon: String, color: Color,
                                enabled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: AppSpacing.sm) {
                Image(systemName: icon)
                    .font(.title2)
                Text(title)
                    .font(AppFont.labelLarge)
            }
            .foregroundColor(enabled ? color : Color.xauTextTertiary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, AppSpacing.xl)
            .background(enabled ? color.opacity(0.1) : Color.xauSurface)
            .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
            .overlay(
                RoundedRectangle(cornerRadius: AppRadius.lg)
                    .strokeBorder(enabled ? color.opacity(0.3) : Color.xauBorder, lineWidth: 1)
            )
        }
        .disabled(!enabled)
    }

    private func toggleRow(_ title: String, icon: String, color: Color,
                            isOn: Bool, action: @escaping () -> Void) -> some View {
        HStack(spacing: AppSpacing.lg) {
            Image(systemName: icon)
                .foregroundColor(color)
                .frame(width: 24)
            Text(title)
                .font(AppFont.bodyMedium)
                .foregroundColor(.xauTextPrimary)
            Spacer()
            Toggle("", isOn: Binding(
                get:  { isOn },
                set:  { _ in action() }
            ))
            .tint(color)
        }
        .padding(AppSpacing.lg)
    }

    private func serviceButton(_ displayName: String, name: String) -> some View {
        Button {
            vm.requestRestartService(name, displayName: displayName)
        } label: {
            HStack(spacing: AppSpacing.sm) {
                Image(systemName: "arrow.clockwise")
                    .font(.callout)
                Text(displayName)
                    .font(AppFont.labelLarge)
            }
            .foregroundColor(.xauWarning)
            .frame(maxWidth: .infinity)
            .padding(.vertical, AppSpacing.md)
            .background(Color.xauWarning.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))
            .overlay(
                RoundedRectangle(cornerRadius: AppRadius.md)
                    .strokeBorder(Color.xauWarning.opacity(0.3), lineWidth: 1)
            )
        }
    }

    private var statusColor: Color {
        guard let s = vm.botStatus else { return .xauNeutral }
        return s.pulseStatus.color
    }

    private func timeAgo(_ date: Date) -> String {
        let interval = Date().timeIntervalSince(date)
        if interval < 60    { return "just now" }
        if interval < 3600  { return "\(Int(interval/60))m ago" }
        if interval < 86400 { return "\(Int(interval/3600))h ago" }
        return "\(Int(interval/86400))d ago"
    }
}
