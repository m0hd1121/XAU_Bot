// DashboardViewModel.swift
// XAUBot – Dashboard ViewModel: WebSocket subscription, metric publishing, refresh
// iOS 17+  |  Swift 5.9

import Foundation
import Combine
import SwiftUI

@MainActor
final class DashboardViewModel: ObservableObject {

    // MARK: - Published Metrics

    @Published private(set) var botStatus:      BotStatus?
    @Published private(set) var accountInfo:    AccountInfo?
    @Published private(set) var openTrades:     [TradeRecord] = []

    @Published private(set) var balance:         String = "—"
    @Published private(set) var equity:          String = "—"
    @Published private(set) var marginLevel:     String = "—"
    @Published private(set) var dailyPnl:        String = "—"
    @Published private(set) var weeklyPnl:       String = "—"
    @Published private(set) var monthlyPnl:      String = "—"
    @Published private(set) var unrealizedPnl:   String = "—"
    @Published private(set) var openTradeCount:  String = "—"

    @Published private(set) var dailyPnlChange:  Double? = nil
    @Published private(set) var equityChange:    Double? = nil

    @Published private(set) var sessionQuality:  String = "—"
    @Published private(set) var lastSyncTime:    String = "—"
    @Published private(set) var isLoading        = true
    @Published private(set) var errorMessage:    String?

    @Published private(set) var connectionState: WSConnectionState = .disconnected

    // MARK: - Private

    private var cancellables = Set<AnyCancellable>()
    private let wsClient     = WebSocketClient.shared

    // MARK: - Init

    init() {
        subscribeToWebSocket()
    }

    // MARK: - WebSocket Subscription

    private func subscribeToWebSocket() {
        wsClient.dashboardPublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] snapshot in
                self?.apply(snapshot)
            }
            .store(in: &cancellables)

        wsClient.$connectionState
            .receive(on: DispatchQueue.main)
            .assign(to: &$connectionState)
    }

    // MARK: - Manual Refresh

    func refresh() async {
        isLoading     = true
        errorMessage  = nil
        do {
            let snapshot: DashboardSnapshot = try await APIClient.shared.request(Endpoint.dashboardSnapshot)
            apply(snapshot)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    // MARK: - Apply Snapshot

    private func apply(_ snapshot: DashboardSnapshot) {
        botStatus   = snapshot.botStatus
        accountInfo = snapshot.accountInfo
        openTrades  = snapshot.openTrades

        let acc = snapshot.accountInfo
        balance        = AppFormat.usd(acc.balance)
        equity         = AppFormat.usd(acc.equity)
        marginLevel    = acc.marginLevel.map { AppFormat.pct($0) } ?? "N/A"
        dailyPnl       = formatPnl(snapshot.dailyPnl)
        weeklyPnl      = formatPnl(snapshot.weeklyPnl)
        monthlyPnl     = formatPnl(snapshot.monthlyPnl)
        unrealizedPnl  = formatPnl(snapshot.unrealizedPnl)
        openTradeCount = "\(snapshot.openTrades.count)"
        sessionQuality = snapshot.sessionQuality.capitalized

        // Compute change indicator vs previous equity
        if let prevEquity = equityChangeBase {
            equityChange = ((acc.equity - prevEquity) / max(abs(prevEquity), 1)) * 100
        }
        equityChangeBase = acc.equity

        let formatter  = DateFormatter()
        formatter.timeStyle = .medium
        lastSyncTime   = "Last sync: \(formatter.string(from: Date()))"
        isLoading      = false
    }

    private var equityChangeBase: Double? = nil

    private func formatPnl(_ value: Double) -> String {
        let sign = value >= 0 ? "+" : ""
        return "\(sign)\(AppFormat.usd(value))"
    }
}
