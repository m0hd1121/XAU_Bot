// TradesViewModel.swift
// XAUBot – Manages live trades and history with pagination, filtering, search
// iOS 17+  |  Swift 5.9

import Foundation
import Combine
import SwiftUI

@MainActor
final class TradesViewModel: ObservableObject {

    // MARK: - Live Trades

    @Published private(set) var liveTrades:      [TradeRecord] = []
    @Published private(set) var liveLoading      = false

    // MARK: - Trade History

    @Published private(set) var historyTrades:   [TradeRecord] = []
    @Published private(set) var historyLoading   = false
    @Published private(set) var canLoadMore      = true
    @Published private(set) var totalHistoryTrades = 0
    @Published private(set) var filteredWinRate:  Double = 0

    // MARK: - Filters

    @Published var searchText    = ""
    @Published var filterResult: String?      // nil = all, "win", "loss", "be"
    @Published var filterSession: String?
    @Published var filterMinRR:   Double?
    @Published var filterStartDate: String?
    @Published var filterEndDate:   String?

    // MARK: - Private

    private var currentPage     = 1
    private let pageSize        = 25
    private var cancellables    = Set<AnyCancellable>()
    private var searchDebounce: Task<Void, Never>?
    private var liveRefreshTask: Task<Void, Never>?

    // MARK: - Init

    init() {
        setupSearchDebounce()
        setupWebSocket()
    }

    // MARK: - Live Trades

    func loadLiveTrades() async {
        liveLoading = true
        do {
            liveTrades = try await APIClient.shared.request(Endpoint.openTrades)
        } catch {
            ToastManager.shared.show(error.localizedDescription, type: .error)
        }
        liveLoading = false
    }

    func startLiveRefresh() {
        liveRefreshTask?.cancel()
        liveRefreshTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 5_000_000_000)   // 5s
                guard !Task.isCancelled else { break }
                await loadLiveTrades()
            }
        }
    }

    func stopLiveRefresh() {
        liveRefreshTask?.cancel()
        liveRefreshTask = nil
    }

    // MARK: - History

    func loadHistory(reset: Bool = false) async {
        if reset {
            currentPage    = 1
            historyTrades  = []
            canLoadMore    = true
        }
        guard canLoadMore else { return }
        historyLoading = true

        let filters = TradeFilters(
            result:    filterResult,
            session:   filterSession,
            minRR:     filterMinRR,
            startDate: filterStartDate,
            endDate:   filterEndDate
        )

        do {
            let response: TradeHistory = try await APIClient.shared.request(
                Endpoint.tradeHistory(page: currentPage, pageSize: pageSize, filters: filters)
            )
            if reset {
                historyTrades = response.trades
            } else {
                historyTrades.append(contentsOf: response.trades)
            }
            totalHistoryTrades = response.total
            filteredWinRate    = response.winRate
            canLoadMore        = currentPage < response.totalPages
            currentPage       += 1
        } catch {
            ToastManager.shared.show(error.localizedDescription, type: .error)
        }
        historyLoading = false
    }

    func loadMoreIfNeeded(trade: TradeRecord) async {
        guard let last = historyTrades.last, last.id == trade.id else { return }
        await loadHistory()
    }

    // MARK: - Actions

    func closeTrade(_ ticket: Int) async {
        do {
            let _: ActionResponse = try await APIClient.shared.request(Endpoint.closeTrade(ticket: ticket))
            ToastManager.shared.show("Trade #\(ticket) closed.", type: .success)
            await loadLiveTrades()
        } catch {
            ToastManager.shared.show("Failed to close trade: \(error.localizedDescription)", type: .error)
        }
    }

    func closeTradePartial(_ ticket: Int, percent: Double) async {
        do {
            let _: ActionResponse = try await APIClient.shared.request(
                Endpoint.closeTradePartial(ticket: ticket, percent: percent)
            )
            ToastManager.shared.show("Trade #\(ticket) partially closed.", type: .success)
            await loadLiveTrades()
        } catch {
            ToastManager.shared.show("Failed: \(error.localizedDescription)", type: .error)
        }
    }

    func modifyTrade(_ ticket: Int, stopLoss: Double?, takeProfit: Double?) async {
        let req = ModifyTradeRequest(stopLoss: stopLoss, takeProfit: takeProfit)
        do {
            let _: ActionResponse = try await APIClient.shared.request(
                Endpoint.modifyTrade(ticket: ticket, request: req)
            )
            ToastManager.shared.show("Trade #\(ticket) modified.", type: .success)
            await loadLiveTrades()
        } catch {
            ToastManager.shared.show("Failed: \(error.localizedDescription)", type: .error)
        }
    }

    // MARK: - Filter Reset

    func resetFilters() {
        filterResult    = nil
        filterSession   = nil
        filterMinRR     = nil
        filterStartDate = nil
        filterEndDate   = nil
        Task { await loadHistory(reset: true) }
    }

    // MARK: - Computed Filtered Trades (for search on live trades)

    var filteredLiveTrades: [TradeRecord] {
        guard !searchText.isEmpty else { return liveTrades }
        return liveTrades.filter {
            $0.symbol.localizedCaseInsensitiveContains(searchText) ||
            "\($0.ticket)".contains(searchText)
        }
    }

    // MARK: - Private Helpers

    private func setupSearchDebounce() {
        $searchText
            .debounce(for: .milliseconds(400), scheduler: DispatchQueue.main)
            .sink { [weak self] _ in
                guard let self else { return }
                Task { await self.loadHistory(reset: true) }
            }
            .store(in: &cancellables)
    }

    private func setupWebSocket() {
        WebSocketClient.shared.tradePublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] trades in
                self?.liveTrades = trades
            }
            .store(in: &cancellables)
    }
}
