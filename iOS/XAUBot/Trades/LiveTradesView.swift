// LiveTradesView.swift
// XAUBot – List of active trades with real-time updates, swipe actions, empty state
// iOS 17+  |  Swift 5.9

import SwiftUI

struct LiveTradesView: View {
    @StateObject private var vm = TradesViewModel()
    @State private var selectedTrade: TradeRecord?
    @State private var showModifySheet = false
    @State private var modifyTarget: TradeRecord?

    var body: some View {
        ZStack {
            Color.xauPrimary.ignoresSafeArea()

            if vm.liveLoading && vm.liveTrades.isEmpty {
                loadingPlaceholder
            } else if vm.filteredLiveTrades.isEmpty {
                EmptyStateView(
                    icon: "arrow.left.arrow.right.circle",
                    title: "No Open Positions",
                    subtitle: "There are no active trades right now. The bot will open positions when conditions are met.",
                    actionTitle: "Refresh"
                ) { Task { await vm.loadLiveTrades() } }
            } else {
                tradeList
            }
        }
        .task {
            await vm.loadLiveTrades()
            vm.startLiveRefresh()
        }
        .onDisappear { vm.stopLiveRefresh() }
        .sheet(item: $selectedTrade) { trade in
            TradeDetailView(ticket: trade.ticket)
        }
        .sheet(item: $modifyTarget) { trade in
            ModifyTradeSheet(trade: trade) { sl, tp in
                Task { await vm.modifyTrade(trade.ticket, stopLoss: sl, takeProfit: tp) }
            }
        }
    }

    // MARK: - Trade List

    private var tradeList: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Header: total unrealized PnL
                let totalUnrealized = vm.filteredLiveTrades.reduce(0.0) { $0 + $1.pnl }
                HStack {
                    Text("\(vm.filteredLiveTrades.count) position\(vm.filteredLiveTrades.count == 1 ? "" : "s")")
                        .font(AppFont.bodySmall)
                        .foregroundColor(.xauTextSecondary)
                    Spacer()
                    Text("Unrealized: \(AppFormat.usd(totalUnrealized))")
                        .font(AppFont.monoSmall)
                        .foregroundColor(Color.pnlColor(totalUnrealized))
                }
                .padding(.horizontal, AppSpacing.screenPadding)
                .padding(.vertical, AppSpacing.md)

                ForEach(vm.filteredLiveTrades) { trade in
                    LiveTradeRow(trade: trade)
                        .onTapGesture { selectedTrade = trade }
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button(role: .destructive) {
                                Task { await vm.closeTrade(trade.ticket) }
                            } label: {
                                Label("Close", systemImage: "xmark.circle.fill")
                            }
                            Button {
                                modifyTarget = trade
                            } label: {
                                Label("Modify", systemImage: "pencil.circle.fill")
                            }
                            .tint(.xauInfo)
                        }
                        .padding(.horizontal, AppSpacing.screenPadding)
                        .padding(.vertical, AppSpacing.xs)
                }

                Color.clear.frame(height: AppSpacing.huge)
            }
        }
        .refreshable { await vm.loadLiveTrades() }
    }

    // MARK: - Loading Placeholder

    private var loadingPlaceholder: some View {
        VStack(spacing: AppSpacing.sm) {
            ForEach(0..<5, id: \.self) { _ in
                RoundedRectangle(cornerRadius: AppRadius.md)
                    .fill(Color.xauCard)
                    .frame(height: 90)
                    .shimmer()
                    .padding(.horizontal, AppSpacing.screenPadding)
            }
        }
        .padding(.top, AppSpacing.lg)
    }
}

// MARK: - LiveTradeRow

struct LiveTradeRow: View {
    let trade: TradeRecord

    var duration: String {
        guard let openTime = ISO8601DateFormatter().date(from: trade.openTime) else { return "—" }
        let interval = Date().timeIntervalSince(openTime)
        let h = Int(interval / 3600)
        let m = Int((interval.truncatingRemainder(dividingBy: 3600)) / 60)
        return h > 0 ? "\(h)h \(m)m" : "\(m)m"
    }

    var body: some View {
        HStack(spacing: AppSpacing.md) {
            // Direction badge
            VStack(spacing: 4) {
                Text(trade.direction)
                    .font(AppFont.labelMedium)
                    .foregroundColor(.white)
                    .padding(.horizontal, AppSpacing.sm)
                    .padding(.vertical, 3)
                    .background(trade.direction == "BUY" ? Color.xauProfit : Color.xauLoss)
                    .clipShape(Capsule())

                Text(duration)
                    .font(AppFont.labelSmall)
                    .foregroundColor(.xauTextTertiary)
            }

            // Trade info
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: AppSpacing.sm) {
                    Text(trade.symbol)
                        .font(AppFont.headlineSmall)
                        .foregroundColor(.xauTextPrimary)
                    Text("#\(trade.ticket)")
                        .font(AppFont.caption)
                        .foregroundColor(.xauTextTertiary)
                }

                HStack(spacing: AppSpacing.sm) {
                    Text(String(format: "%.5f", trade.openPrice))
                        .font(AppFont.monoTiny)
                        .foregroundColor(.xauTextSecondary)
                    Image(systemName: "arrow.right")
                        .font(.system(size: 9))
                        .foregroundColor(.xauTextTertiary)
                    if let curr = trade.currentPrice {
                        Text(String(format: "%.5f", curr))
                            .font(AppFont.monoTiny)
                            .foregroundColor(.xauTextSecondary)
                    }
                }

                HStack(spacing: AppSpacing.sm) {
                    if let sl = trade.stopLoss {
                        Label(String(format: "%.5f", sl), systemImage: "shield.lefthalf.filled")
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauLoss)
                    }
                    if let tp = trade.takeProfit {
                        Label(String(format: "%.5f", tp), systemImage: "flag.fill")
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauProfit)
                    }
                }
            }

            Spacer()

            // P&L
            VStack(alignment: .trailing, spacing: 4) {
                Text(AppFormat.usd(trade.pnl))
                    .font(AppFont.monoSmall)
                    .foregroundColor(Color.pnlColor(trade.pnl))
                    .contentTransition(.numericText())

                if let pips = trade.pips {
                    Text(AppFormat.pips(pips))
                        .font(AppFont.labelSmall)
                        .foregroundColor(.xauTextTertiary)
                }

                if let session = trade.session {
                    Text(session.uppercased())
                        .font(AppFont.labelSmall)
                        .foregroundColor(.xauGold)
                }
            }
        }
        .padding(AppSpacing.md)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        .overlay(
            RoundedRectangle(cornerRadius: AppRadius.lg)
                .strokeBorder(
                    trade.pnl >= 0 ? Color.xauProfit.opacity(0.2) : Color.xauLoss.opacity(0.2),
                    lineWidth: 0.5
                )
        )
    }
}

// MARK: - ModifyTradeSheet

struct ModifyTradeSheet: View {
    let trade:     TradeRecord
    let onConfirm: (Double?, Double?) -> Void

    @State private var slText = ""
    @State private var tpText = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Stop Loss") {
                    TextField(
                        trade.stopLoss.map { String(format: "%.5f", $0) } ?? "No stop loss",
                        text: $slText
                    )
                    .keyboardType(.decimalPad)
                    .font(AppFont.monoSmall)
                }
                Section("Take Profit") {
                    TextField(
                        trade.takeProfit.map { String(format: "%.5f", $0) } ?? "No take profit",
                        text: $tpText
                    )
                    .keyboardType(.decimalPad)
                    .font(AppFont.monoSmall)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Color.xauPrimary)
            .navigationTitle("Modify Trade #\(trade.ticket)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onConfirm(Double(slText), Double(tpText))
                        dismiss()
                    }
                }
            }
        }
    }
}
