// DashboardView.swift
// XAUBot – Main dashboard: metrics grid, bot status, live updates, quick actions
// iOS 17+  |  Swift 5.9

import SwiftUI

struct DashboardView: View {
    @StateObject private var vm = DashboardViewModel()

    private let columns = [
        GridItem(.flexible(), spacing: AppSpacing.gridSpacing),
        GridItem(.flexible(), spacing: AppSpacing.gridSpacing)
    ]

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AppSpacing.sectionSpacing) {
                        // Status header
                        statusHeader

                        // Metrics grid
                        LazyVGrid(columns: columns, spacing: AppSpacing.gridSpacing) {
                            MetricCard(title: "Balance",
                                       value: vm.balance,
                                       isLoading: vm.isLoading)

                            MetricCard(title: "Equity",
                                       value: vm.equity,
                                       change: vm.equityChange,
                                       isLoading: vm.isLoading)

                            MetricCard(title: "Margin Level",
                                       value: vm.marginLevel,
                                       isLoading: vm.isLoading)

                            MetricCard(title: "Open Trades",
                                       value: vm.openTradeCount,
                                       isLoading: vm.isLoading)

                            MetricCard(title: "Daily P&L",
                                       value: vm.dailyPnl,
                                       tintColor: pnlTint(vm.dailyPnl),
                                       isLoading: vm.isLoading)

                            MetricCard(title: "Weekly P&L",
                                       value: vm.weeklyPnl,
                                       tintColor: pnlTint(vm.weeklyPnl),
                                       isLoading: vm.isLoading)

                            MetricCard(title: "Monthly P&L",
                                       value: vm.monthlyPnl,
                                       tintColor: pnlTint(vm.monthlyPnl),
                                       isLoading: vm.isLoading)

                            MetricCard(title: "Unrealized P&L",
                                       value: vm.unrealizedPnl,
                                       tintColor: pnlTint(vm.unrealizedPnl),
                                       isLoading: vm.isLoading)
                        }
                        .padding(.horizontal, AppSpacing.screenPadding)

                        // Session quality + sync
                        sessionInfo

                        // Quick-action buttons
                        if let status = vm.botStatus {
                            quickActions(status: status)
                        }

                        // Open trades mini-list
                        if !vm.openTrades.isEmpty {
                            openTradesSection
                        }

                        Color.clear.frame(height: AppSpacing.huge)
                    }
                    .padding(.top, AppSpacing.md)
                }
                .refreshable { await vm.refresh() }
            }
            .navigationTitle("Dashboard")
            .navigationBarTitleDisplayMode(.large)
            .task { await vm.refresh() }
            .overlay(alignment: .top) {
                if let error = vm.errorMessage {
                    errorBanner(error)
                }
            }
        }
    }

    // MARK: - Status Header

    private var statusHeader: some View {
        HStack(spacing: AppSpacing.md) {
            if let status = vm.botStatus {
                PulsingDot(status: status.pulseStatus, size: 14)
                VStack(alignment: .leading, spacing: 2) {
                    Text(status.statusLabel)
                        .font(AppFont.headlineSmall)
                        .foregroundColor(.xauTextPrimary)
                    Text("Mode: \(status.mode.uppercased())")
                        .font(AppFont.labelMedium)
                        .foregroundColor(.xauGold)
                }
            } else if vm.isLoading {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.xauBorder)
                    .frame(width: 120, height: 20)
                    .shimmer()
            }

            Spacer()

            // Connection state
            HStack(spacing: 4) {
                Circle()
                    .fill(vm.connectionState.isConnected ? Color.xauProfit : Color.xauWarning)
                    .frame(width: 8, height: 8)
                Text(vm.connectionState.displayLabel)
                    .font(AppFont.labelMedium)
                    .foregroundColor(.xauTextSecondary)
            }
        }
        .padding(.horizontal, AppSpacing.screenPadding)
    }

    // MARK: - Session Info

    private var sessionInfo: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Session Quality")
                    .font(AppFont.labelMedium)
                    .foregroundColor(.xauTextTertiary)
                Text(vm.sessionQuality)
                    .font(AppFont.headlineSmall)
                    .foregroundColor(sessionQualityColor(vm.sessionQuality))
            }
            Spacer()
            Text(vm.lastSyncTime)
                .font(AppFont.caption)
                .foregroundColor(.xauTextTertiary)
        }
        .padding(.horizontal, AppSpacing.screenPadding)
    }

    // MARK: - Quick Actions

    private func quickActions(status: BotStatus) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            Text("Quick Actions")
                .font(AppFont.headlineSmall)
                .foregroundColor(.xauTextSecondary)
                .padding(.horizontal, AppSpacing.screenPadding)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: AppSpacing.sm) {
                    if !status.running {
                        quickActionBtn("Start", icon: "play.fill",   color: .xauProfit)   { }
                    } else {
                        quickActionBtn("Stop",  icon: "stop.fill",   color: .xauLoss)     { }
                        quickActionBtn(status.paused ? "Resume" : "Pause",
                                       icon: status.paused ? "play.fill" : "pause.fill",
                                       color: .xauInfo)                                  { }
                    }
                    quickActionBtn("Restart", icon: "arrow.clockwise", color: .xauWarning) { }
                    NavigationLink(destination: BotControlView()) {
                        Label("Full Control", systemImage: "slider.horizontal.3")
                            .font(AppFont.labelLarge)
                            .foregroundColor(.xauGold)
                            .padding(.horizontal, AppSpacing.lg)
                            .padding(.vertical, AppSpacing.sm)
                            .overlay(
                                Capsule().strokeBorder(Color.xauGold.opacity(0.5), lineWidth: 1)
                            )
                    }
                }
                .padding(.horizontal, AppSpacing.screenPadding)
            }
        }
    }

    private func quickActionBtn(_ title: String, icon: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: icon)
                .font(AppFont.labelLarge)
                .foregroundColor(color)
                .padding(.horizontal, AppSpacing.lg)
                .padding(.vertical, AppSpacing.sm)
                .background(color.opacity(0.1))
                .clipShape(Capsule())
                .overlay(Capsule().strokeBorder(color.opacity(0.3), lineWidth: 1))
        }
    }

    // MARK: - Open Trades Mini-List

    private var openTradesSection: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            HStack {
                Text("Open Positions")
                    .font(AppFont.headlineSmall)
                    .foregroundColor(.xauTextSecondary)
                Spacer()
                Text("Unrealized: \(vm.unrealizedPnl)")
                    .font(AppFont.labelLarge)
                    .foregroundColor(pnlTint(vm.unrealizedPnl))
            }
            .padding(.horizontal, AppSpacing.screenPadding)

            ForEach(vm.openTrades.prefix(3)) { trade in
                TradeRowMini(trade: trade)
                    .padding(.horizontal, AppSpacing.screenPadding)
            }

            if vm.openTrades.count > 3 {
                Text("+ \(vm.openTrades.count - 3) more…")
                    .font(AppFont.caption)
                    .foregroundColor(.xauTextTertiary)
                    .padding(.horizontal, AppSpacing.screenPadding)
            }
        }
    }

    // MARK: - Error Banner

    private func errorBanner(_ msg: String) -> some View {
        Text(msg)
            .font(AppFont.caption)
            .foregroundColor(.white)
            .padding(.horizontal, AppSpacing.lg)
            .padding(.vertical, AppSpacing.xs)
            .background(Color.xauLoss)
            .clipShape(Capsule())
            .padding(.top, 4)
            .transition(.move(edge: .top).combined(with: .opacity))
    }

    // MARK: - Helpers

    private func pnlTint(_ value: String) -> Color {
        if value.hasPrefix("+") { return .xauProfit }
        if value.hasPrefix("-") { return .xauLoss }
        return .xauTextPrimary
    }

    private func sessionQualityColor(_ quality: String) -> Color {
        switch quality.lowercased() {
        case "excellent": return .xauProfit
        case "good":      return .xauProfit.opacity(0.7)
        case "fair":      return .xauWarning
        default:          return .xauLoss
        }
    }
}

// MARK: - TradeRowMini

private struct TradeRowMini: View {
    let trade: TradeRecord

    var body: some View {
        HStack(spacing: AppSpacing.md) {
            // Direction badge
            Text(trade.direction)
                .font(AppFont.labelMedium)
                .foregroundColor(trade.direction == "BUY" ? .xauProfit : .xauLoss)
                .padding(.horizontal, AppSpacing.sm)
                .padding(.vertical, 3)
                .background(
                    (trade.direction == "BUY" ? Color.xauProfit : Color.xauLoss).opacity(0.12)
                )
                .clipShape(Capsule())

            Text(trade.symbol)
                .font(AppFont.labelLarge)
                .foregroundColor(.xauTextPrimary)

            Spacer()

            Text(AppFormat.usd(trade.pnl))
                .font(AppFont.monoSmall)
                .foregroundColor(Color.pnlColor(trade.pnl))
        }
        .padding(AppSpacing.md)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))
    }
}
