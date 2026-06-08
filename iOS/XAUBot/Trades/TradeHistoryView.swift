// TradeHistoryView.swift
// XAUBot – Paginated trade history with search, filters, stats summary
// iOS 17+  |  Swift 5.9

import SwiftUI

struct TradeHistoryView: View {
    @StateObject private var vm = TradesViewModel()
    @State private var showFilters = false
    @State private var selectedTrade: TradeRecord?

    var body: some View {
        ZStack {
            Color.xauPrimary.ignoresSafeArea()

            VStack(spacing: 0) {
                // Search bar
                searchBar

                // Filter chips
                filterChips

                // Summary stats
                summaryStats

                // Trade list
                if vm.historyLoading && vm.historyTrades.isEmpty {
                    loadingPlaceholder
                } else if vm.historyTrades.isEmpty {
                    EmptyStateView(
                        icon: "clock.arrow.circlepath",
                        title: "No Trade History",
                        subtitle: "Closed trades will appear here.",
                        actionTitle: "Refresh"
                    ) { Task { await vm.loadHistory(reset: true) } }
                } else {
                    tradeList
                }
            }
        }
        .sheet(item: $selectedTrade) { trade in
            NavigationStack {
                TradeDetailView(ticket: trade.ticket)
            }
        }
        .task { await vm.loadHistory(reset: true) }
        .refreshable { await vm.loadHistory(reset: true) }
    }

    // MARK: - Search Bar

    private var searchBar: some View {
        HStack(spacing: AppSpacing.sm) {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.xauTextTertiary)
            TextField("Search symbol, ticket…", text: $vm.searchText)
                .font(AppFont.bodyMedium)
                .foregroundColor(.xauTextPrimary)
                .autocorrectionDisabled()
            if !vm.searchText.isEmpty {
                Button { vm.searchText = "" } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.xauTextTertiary)
                }
            }
        }
        .padding(AppSpacing.md)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))
        .padding(.horizontal, AppSpacing.screenPadding)
        .padding(.vertical, AppSpacing.sm)
    }

    // MARK: - Filter Chips

    private var filterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppSpacing.sm) {
                filterChip("All", isSelected: vm.filterResult == nil) {
                    vm.filterResult = nil
                    Task { await vm.loadHistory(reset: true) }
                }
                filterChip("Wins", isSelected: vm.filterResult == "win") {
                    vm.filterResult = "win"
                    Task { await vm.loadHistory(reset: true) }
                }
                filterChip("Losses", isSelected: vm.filterResult == "loss") {
                    vm.filterResult = "loss"
                    Task { await vm.loadHistory(reset: true) }
                }
                filterChip("BE", isSelected: vm.filterResult == "be") {
                    vm.filterResult = "be"
                    Task { await vm.loadHistory(reset: true) }
                }

                Divider().frame(height: 20)

                ForEach(["london", "ny", "tokyo"], id: \.self) { session in
                    filterChip(session.uppercased(), isSelected: vm.filterSession == session) {
                        vm.filterSession = vm.filterSession == session ? nil : session
                        Task { await vm.loadHistory(reset: true) }
                    }
                }

                if vm.filterResult != nil || vm.filterSession != nil {
                    Button("Reset") { vm.resetFilters() }
                        .font(AppFont.labelLarge)
                        .foregroundColor(.xauLoss)
                }
            }
            .padding(.horizontal, AppSpacing.screenPadding)
        }
        .padding(.vertical, AppSpacing.xs)
    }

    private func filterChip(_ label: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(AppFont.labelLarge)
                .foregroundColor(isSelected ? .black : .xauTextSecondary)
                .padding(.horizontal, AppSpacing.md)
                .padding(.vertical, AppSpacing.xs)
                .background(isSelected ? Color.xauGold : Color.xauCard)
                .clipShape(Capsule())
        }
    }

    // MARK: - Summary Stats

    private var summaryStats: some View {
        HStack {
            Text("\(vm.totalHistoryTrades) trades")
                .font(AppFont.labelLarge)
                .foregroundColor(.xauTextSecondary)
            Spacer()
            Text("Win rate: \(AppFormat.pct(vm.filteredWinRate))")
                .font(AppFont.labelLarge)
                .foregroundColor(vm.filteredWinRate >= 50 ? .xauProfit : .xauLoss)
        }
        .padding(.horizontal, AppSpacing.screenPadding)
        .padding(.vertical, AppSpacing.sm)
    }

    // MARK: - Trade List

    private var tradeList: some View {
        ScrollView {
            LazyVStack(spacing: AppSpacing.xs) {
                ForEach(vm.historyTrades) { trade in
                    HistoryTradeRow(trade: trade)
                        .onTapGesture { selectedTrade = trade }
                        .onAppear { Task { await vm.loadMoreIfNeeded(trade: trade) } }
                        .padding(.horizontal, AppSpacing.screenPadding)
                }

                if vm.historyLoading {
                    ProgressView().tint(.xauGold).padding()
                } else if !vm.canLoadMore {
                    Text("All \(vm.totalHistoryTrades) trades loaded")
                        .font(AppFont.caption)
                        .foregroundColor(.xauTextTertiary)
                        .padding(.vertical, AppSpacing.xl)
                }

                Color.clear.frame(height: AppSpacing.huge)
            }
        }
    }

    // MARK: - Loading Placeholder

    private var loadingPlaceholder: some View {
        ScrollView {
            VStack(spacing: AppSpacing.sm) {
                ForEach(0..<8, id: \.self) { _ in
                    RoundedRectangle(cornerRadius: AppRadius.md)
                        .fill(Color.xauCard)
                        .frame(height: 70)
                        .shimmer()
                        .padding(.horizontal, AppSpacing.screenPadding)
                }
            }
        }
    }
}

// MARK: - HistoryTradeRow

struct HistoryTradeRow: View {
    let trade: TradeRecord

    private var resultColor: Color {
        if trade.pnl > 0 { return .xauProfit }
        if trade.pnl < 0 { return .xauLoss }
        return .xauNeutral
    }

    private var resultLabel: String {
        if trade.pnl > 1 { return "W" }
        if trade.pnl < -1 { return "L" }
        return "BE"
    }

    private var duration: String {
        guard let open  = ISO8601DateFormatter().date(from: trade.openTime),
              let close = trade.closeTime.flatMap({ ISO8601DateFormatter().date(from: $0) }) else { return "—" }
        let s = close.timeIntervalSince(open)
        let h = Int(s / 3600)
        let m = Int((s.truncatingRemainder(dividingBy: 3600)) / 60)
        return h > 0 ? "\(h)h \(m)m" : "\(m)m"
    }

    var body: some View {
        HStack(spacing: AppSpacing.md) {
            // Result badge
            Text(resultLabel)
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(.white)
                .frame(width: 28, height: 28)
                .background(resultColor)
                .clipShape(Circle())

            // Direction + symbol
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: AppSpacing.xs) {
                    Text(trade.direction)
                        .font(AppFont.labelMedium)
                        .foregroundColor(trade.direction == "BUY" ? .xauProfit : .xauLoss)
                    Text(trade.symbol)
                        .font(AppFont.headlineSmall)
                        .foregroundColor(.xauTextPrimary)
                }
                HStack(spacing: AppSpacing.sm) {
                    if let session = trade.session {
                        Text(session.uppercased())
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauGold)
                    }
                    Text(duration)
                        .font(AppFont.labelSmall)
                        .foregroundColor(.xauTextTertiary)
                }
            }

            Spacer()

            // P&L
            VStack(alignment: .trailing, spacing: 2) {
                Text(AppFormat.usd(trade.pnl))
                    .font(AppFont.monoSmall)
                    .foregroundColor(resultColor)
                if let rr = trade.rr {
                    Text(AppFormat.r(rr))
                        .font(AppFont.labelSmall)
                        .foregroundColor(resultColor.opacity(0.7))
                }
            }
        }
        .padding(AppSpacing.md)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))
    }
}
