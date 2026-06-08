// TradeDetailView.swift
// XAUBot – Full trade detail with AI explanation and action buttons
// iOS 17+  |  Swift 5.9

import SwiftUI

struct TradeDetailView: View {
    let ticket: Int

    @State private var trade:           TradeRecord?
    @State private var isLoading        = true
    @State private var showModify       = false
    @State private var confirmationConfig: ConfirmationConfig?
    @Environment(\.dismiss) private var dismiss

    private let vm = TradesViewModel()

    var body: some View {
        ZStack {
            Color.xauPrimary.ignoresSafeArea()

            if isLoading {
                ProgressView("Loading trade…")
                    .tint(.xauGold)
            } else if let trade {
                ScrollView {
                    VStack(spacing: AppSpacing.sectionSpacing) {
                        // Header card
                        tradeHeader(trade)

                        // Key metrics
                        metricsGrid(trade)

                        // AI explanation card
                        if let explanation = trade.aiExplanation {
                            aiCard(explanation, trade: trade)
                        }

                        // Action buttons (only for open trades)
                        if trade.status == "open" {
                            actionButtons(trade)
                        }

                        Color.clear.frame(height: AppSpacing.huge)
                    }
                    .padding(.horizontal, AppSpacing.screenPadding)
                    .padding(.top, AppSpacing.lg)
                }
            } else {
                EmptyStateView(
                    icon: "exclamationmark.triangle",
                    title: "Trade Not Found",
                    subtitle: "Trade #\(ticket) could not be loaded."
                )
            }
        }
        .navigationTitle("Trade #\(ticket)")
        .navigationBarTitleDisplayMode(.inline)
        .confirmationAlert(config: $confirmationConfig)
        .sheet(isPresented: $showModify) {
            if let t = trade {
                ModifyTradeSheet(trade: t) { sl, tp in
                    Task { await vm.modifyTrade(t.ticket, stopLoss: sl, takeProfit: tp) }
                }
            }
        }
        .task { await loadTrade() }
    }

    // MARK: - Header

    private func tradeHeader(_ trade: TradeRecord) -> some View {
        VStack(spacing: AppSpacing.lg) {
            HStack(spacing: AppSpacing.md) {
                Text(trade.direction)
                    .font(AppFont.headlineLarge)
                    .foregroundColor(.white)
                    .padding(.horizontal, AppSpacing.xl)
                    .padding(.vertical, AppSpacing.md)
                    .background(trade.direction == "BUY" ? Color.xauProfit : Color.xauLoss)
                    .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))

                VStack(alignment: .leading, spacing: 4) {
                    Text(trade.symbol)
                        .font(AppFont.headlineLarge)
                        .foregroundColor(.xauTextPrimary)
                    HStack(spacing: AppSpacing.sm) {
                        Text(String(format: "%.2f lots", trade.lots))
                            .font(AppFont.bodySmall)
                            .foregroundColor(.xauTextSecondary)
                        if let session = trade.session {
                            Text(session.uppercased())
                                .font(AppFont.labelMedium)
                                .foregroundColor(.xauGold)
                        }
                    }
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    Text(AppFormat.usd(trade.pnl))
                        .font(AppFont.monoLarge)
                        .foregroundColor(Color.pnlColor(trade.pnl))
                    if let rr = trade.rr {
                        Text(AppFormat.r(rr))
                            .font(AppFont.monoSmall)
                            .foregroundColor(Color.pnlColor(rr))
                    }
                }
            }

            // Status badge
            HStack {
                Text(trade.status.uppercased())
                    .font(AppFont.labelMedium)
                    .foregroundColor(trade.status == "open" ? .xauProfit : .xauTextSecondary)
                    .padding(.horizontal, AppSpacing.md)
                    .padding(.vertical, AppSpacing.xs)
                    .background(
                        (trade.status == "open" ? Color.xauProfit : Color.xauNeutral).opacity(0.15)
                    )
                    .clipShape(Capsule())
                Spacer()
            }
        }
        .padding(AppSpacing.xl)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.xl))
    }

    // MARK: - Metrics Grid

    private func metricsGrid(_ trade: TradeRecord) -> some View {
        LazyVGrid(
            columns: [GridItem(.flexible()), GridItem(.flexible())],
            spacing: AppSpacing.sm
        ) {
            detailRow("Entry Price",  String(format: "%.5f", trade.openPrice))
            if let curr = trade.currentPrice {
                detailRow("Current Price", String(format: "%.5f", curr))
            }
            if let close = trade.closePrice {
                detailRow("Exit Price",  String(format: "%.5f", close))
            }
            if let sl = trade.stopLoss {
                detailRow("Stop Loss",   String(format: "%.5f", sl))
            }
            if let tp = trade.takeProfit {
                detailRow("Take Profit", String(format: "%.5f", tp))
            }
            if let pips = trade.pips {
                detailRow("Pips", AppFormat.pips(pips))
            }
            detailRow("Commission", AppFormat.usd(trade.commission))
            detailRow("Swap",       AppFormat.usd(trade.swap))
            detailRow("Open Time",  formatTime(trade.openTime))
            if let closeTime = trade.closeTime {
                detailRow("Close Time", formatTime(closeTime))
            }
        }
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(AppFont.labelMedium)
                .foregroundColor(.xauTextTertiary)
            Text(value)
                .font(AppFont.monoSmall)
                .foregroundColor(.xauTextPrimary)
        }
        .padding(AppSpacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))
    }

    // MARK: - AI Card

    private func aiCard(_ explanation: String, trade: TradeRecord) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            HStack(spacing: AppSpacing.sm) {
                Image(systemName: "brain.head.profile")
                    .foregroundColor(.xauGold)
                Text("AI Analysis")
                    .font(AppFont.headlineSmall)
                    .foregroundColor(.xauGold)
            }

            Text(explanation)
                .font(AppFont.bodySmall)
                .foregroundColor(.xauTextSecondary)
                .fixedSize(horizontal: false, vertical: true)

            Divider().background(Color.xauBorder)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())],
                      spacing: AppSpacing.sm) {
                if let conf = trade.confidence {
                    aiMetric("Confidence", String(format: "%.0f%%", conf * 100))
                }
                if let zone = trade.zoneQuality {
                    aiMetric("Zone Quality", String(format: "%.0f%%", zone * 100))
                }
                if let sweep = trade.sweepDetected {
                    aiMetric("Sweep", sweep ? "Yes" : "No")
                }
                if let trigger = trade.triggerType {
                    aiMetric("Trigger", trigger)
                }
                if let regime = trade.regime {
                    aiMetric("Regime", regime)
                }
            }
        }
        .padding(AppSpacing.xl)
        .background(
            ZStack {
                Color.xauCard
                LinearGradient(
                    colors: [Color.xauGold.opacity(0.05), Color.clear],
                    startPoint: .topLeading, endPoint: .bottomTrailing
                )
            }
        )
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.xl))
        .overlay(
            RoundedRectangle(cornerRadius: AppRadius.xl)
                .strokeBorder(Color.xauGold.opacity(0.2), lineWidth: 1)
        )
    }

    private func aiMetric(_ label: String, _ value: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(AppFont.monoSmall)
                .foregroundColor(.xauTextPrimary)
            Text(label)
                .font(AppFont.labelSmall)
                .foregroundColor(.xauTextTertiary)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Action Buttons

    private func actionButtons(_ trade: TradeRecord) -> some View {
        VStack(spacing: AppSpacing.md) {
            Button {
                confirmationConfig = ConfirmationConfig(
                    title: "Close Trade #\(trade.ticket)",
                    message: "This will fully close the position at market price. Current P&L: \(AppFormat.usd(trade.pnl))",
                    actionLabel: "Close Full",
                    isDestructive: true,
                    action: {
                        await vm.closeTrade(trade.ticket)
                        dismiss()
                    }
                )
            } label: {
                Label("Close Full", systemImage: "xmark.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(DestructiveButtonStyle())

            HStack(spacing: AppSpacing.md) {
                Button {
                    confirmationConfig = ConfirmationConfig(
                        title: "Close 50%",
                        message: "Half the position will be closed at market price.",
                        actionLabel: "Close 50%",
                        isDestructive: false,
                        action: { await vm.closeTradePartial(trade.ticket, percent: 0.5) }
                    )
                } label: {
                    Label("Close 50%", systemImage: "divide.circle")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(OutlineButtonStyle(color: .xauWarning))

                Button { showModify = true } label: {
                    Label("Modify", systemImage: "pencil.circle")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(OutlineButtonStyle())
            }
        }
    }

    // MARK: - Load

    private func loadTrade() async {
        isLoading = true
        do {
            trade = try await APIClient.shared.request(Endpoint.tradeDetail(ticket: ticket))
        } catch {
            ToastManager.shared.show(error.localizedDescription, type: .error)
        }
        isLoading = false
    }

    private func formatTime(_ isoString: String) -> String {
        let f = ISO8601DateFormatter()
        guard let date = f.date(from: isoString) else { return isoString }
        let out = DateFormatter()
        out.dateStyle = .short
        out.timeStyle = .short
        return out.string(from: date)
    }
}
