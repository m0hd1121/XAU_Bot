// MainTabView.swift
// XAUBot – Main tab bar after authentication
// iOS 17+  |  Swift 5.9

import SwiftUI

struct MainTabView: View {
    @EnvironmentObject private var wsClient: WebSocketClient
    @State private var selectedTab: Tab = .dashboard
    @State private var showMoreSheet  = false

    enum Tab: Int {
        case dashboard, trades, analytics, learning, more
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            DashboardView()
                .tabItem { Label("Dashboard", systemImage: "house.fill") }
                .tag(Tab.dashboard)

            TradesRootView()
                .tabItem { Label("Trades", systemImage: "arrow.left.arrow.right.circle.fill") }
                .tag(Tab.trades)

            AnalyticsView()
                .tabItem { Label("Analytics", systemImage: "chart.xyaxis.line") }
                .tag(Tab.analytics)

            LearningDashboardView()
                .tabItem { Label("Learning", systemImage: "brain.head.profile") }
                .tag(Tab.learning)

            MoreView()
                .tabItem { Label("More", systemImage: "ellipsis.circle.fill") }
                .tag(Tab.more)
        }
        .tint(.xauGold)
        .overlay(alignment: .top) {
            connectionBanner
        }
    }

    // MARK: - Connection Banner

    @ViewBuilder
    private var connectionBanner: some View {
        if !wsClient.connectionState.isConnected {
            HStack(spacing: AppSpacing.sm) {
                if case .reconnecting(let n) = wsClient.connectionState {
                    ProgressView().scaleEffect(0.7)
                    Text("Reconnecting… (attempt \(n))")
                } else if wsClient.connectionState == .connecting {
                    ProgressView().scaleEffect(0.7)
                    Text("Connecting…")
                } else {
                    Image(systemName: "wifi.slash")
                    Text("Disconnected")
                }
            }
            .font(AppFont.labelMedium)
            .foregroundColor(.white)
            .padding(.horizontal, AppSpacing.lg)
            .padding(.vertical, AppSpacing.xs)
            .background(Color.xauWarning)
            .clipShape(Capsule())
            .padding(.top, 4)
            .transition(.move(edge: .top).combined(with: .opacity))
            .animation(AppAnimation.springNormal, value: wsClient.connectionState)
        }
    }
}

// MARK: - Trades Root (Live + History tabs)

struct TradesRootView: View {
    var body: some View {
        NavigationStack {
            TradesHostView()
                .navigationTitle("Trades")
                .navigationBarTitleDisplayMode(.large)
        }
    }
}

struct TradesHostView: View {
    @State private var tab: TradeTab = .live

    enum TradeTab { case live, history }

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $tab) {
                Text("Live").tag(TradeTab.live)
                Text("History").tag(TradeTab.history)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.vertical, AppSpacing.sm)

            switch tab {
            case .live:    LiveTradesView()
            case .history: TradeHistoryView()
            }
        }
    }
}

// MARK: - More View

struct MoreView: View {
    @EnvironmentObject private var authService: AuthService
    @State private var destination: MoreDestination?

    enum MoreDestination: Identifiable, Hashable {
        case botControl, config, vps, logs, backup, account, settings, notifications
        var id: Self { self }
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Bot") {
                    moreRow("Bot Control",     icon: "play.slash.fill",    color: .xauProfit,  dest: .botControl)
                    moreRow("Configuration",   icon: "slider.horizontal.3",color: .xauGold,    dest: .config)
                }
                Section("System") {
                    moreRow("VPS Monitor",     icon: "server.rack",        color: .xauInfo,    dest: .vps)
                    moreRow("Logs",            icon: "doc.text.fill",      color: .xauNeutral, dest: .logs)
                    moreRow("Backup",          icon: "externaldrive.fill",  color: .xauWarning, dest: .backup)
                }
                Section("Account") {
                    moreRow("Trading Account", icon: "creditcard.fill",    color: .xauGold,    dest: .account)
                    moreRow("Notifications",   icon: "bell.fill",          color: .xauInfo,    dest: .notifications)
                    moreRow("Settings",        icon: "gearshape.fill",     color: .xauNeutral, dest: .settings)
                }
                Section {
                    Button(role: .destructive) {
                        Task { await authService.logout() }
                    } label: {
                        Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                }
            }
            .listStyle(.insetGrouped)
            .scrollContentBackground(.hidden)
            .background(Color.xauPrimary)
            .navigationTitle("More")
            .navigationDestination(item: $destination) { dest in
                switch dest {
                case .botControl:    BotControlView()
                case .config:        ConfigurationView()
                case .vps:           VPSView()
                case .logs:          LogsView()
                case .backup:        BackupView()
                case .account:       AccountView()
                case .settings:      AppSettingsView()
                case .notifications: NotificationPreferencesView()
                }
            }
        }
        .tint(.xauGold)
    }

    private func moreRow(_ title: String, icon: String, color: Color, dest: MoreDestination) -> some View {
        Button {
            destination = dest
        } label: {
            HStack(spacing: AppSpacing.lg) {
                ZStack {
                    RoundedRectangle(cornerRadius: AppRadius.sm)
                        .fill(color.opacity(0.15))
                        .frame(width: 34, height: 34)
                    Image(systemName: icon)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(color)
                }
                Text(title)
                    .foregroundColor(.xauTextPrimary)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.xauTextTertiary)
            }
        }
        .listRowBackground(Color.xauCard)
    }
}
