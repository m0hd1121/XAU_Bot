// AnalyticsView.swift
// XAUBot – Analytics dashboard with Swift Charts equity curve, heatmap, sessions, regimes
// iOS 17+  |  Swift 5.9

import SwiftUI
import Charts

struct AnalyticsView: View {
    @StateObject private var vm = AnalyticsViewModel()

    enum AnalyticsTab: String, CaseIterable {
        case overview = "Overview"
        case charts   = "Charts"
        case sessions = "Sessions"
        case regimes  = "Regimes"
    }

    @State private var selectedTab: AnalyticsTab = .overview

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Tab picker
                    Picker("", selection: $selectedTab) {
                        ForEach(AnalyticsTab.allCases, id: \.self) { tab in
                            Text(tab.rawValue).tag(tab)
                        }
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal, AppSpacing.screenPadding)
                    .padding(.vertical, AppSpacing.sm)

                    ScrollView {
                        VStack(spacing: AppSpacing.sectionSpacing) {
                            switch selectedTab {
                            case .overview: overviewTab
                            case .charts:   chartsTab
                            case .sessions: sessionsTab
                            case .regimes:  regimesTab
                            }
                            Color.clear.frame(height: AppSpacing.huge)
                        }
                        .padding(.horizontal, AppSpacing.screenPadding)
                        .padding(.top, AppSpacing.md)
                    }
                    .refreshable { await vm.load() }
                }
            }
            .navigationTitle("Analytics")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        ForEach([30, 60, 90, 180, 365], id: \.self) { days in
                            Button("\(days) days") {
                                vm.selectedDays = days
                                Task { await vm.load() }
                            }
                        }
                    } label: {
                        Label("\(vm.selectedDays)d", systemImage: "calendar")
                            .font(AppFont.labelLarge)
                    }
                }
            }
            .task { await vm.load() }
            .loadingOverlay(vm.isLoading)
        }
    }

    // MARK: - Overview Tab

    private var overviewTab: some View {
        let cols = [GridItem(.flexible()), GridItem(.flexible())]
        return LazyVGrid(columns: cols, spacing: AppSpacing.gridSpacing) {
            kpiCard("Win Rate",       vm.winRateStr,      icon: "percent",                color: .xauProfit)
            kpiCard("Profit Factor",  vm.profitFactorStr, icon: "multiply.square.fill",  color: .xauGold)
            kpiCard("Expectancy",     vm.expectancyStr,   icon: "arrow.up.right.circle", color: .xauProfit)
            kpiCard("Sharpe Ratio",   vm.sharpeStr,       icon: "waveform.path.ecg",     color: .xauInfo)
            kpiCard("Calmar Ratio",   vm.calmarStr,       icon: "gauge.with.needle",     color: .xauWarning)
            kpiCard("Max Drawdown",   vm.maxDDStr,        icon: "arrow.down.circle",     color: .xauLoss)
            kpiCard("Total P&L",      vm.totalPnlStr,     icon: "banknote.fill",         color: .xauProfit)
            kpiCard("Avg R:R",        vm.avgRRStr,        icon: "scale.3d",              color: .xauGold)
        }
    }

    private func kpiCard(_ title: String, _ value: String, icon: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.sm) {
            HStack {
                Image(systemName: icon)
                    .foregroundColor(color)
                    .font(.callout)
                Spacer()
            }
            Text(value)
                .font(AppFont.monoMedium)
                .foregroundColor(.xauTextPrimary)
                .minimumScaleFactor(0.6)
                .lineLimit(1)
            Text(title)
                .font(AppFont.caption)
                .foregroundColor(.xauTextTertiary)
        }
        .padding(AppSpacing.lg)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        .overlay(
            RoundedRectangle(cornerRadius: AppRadius.lg)
                .strokeBorder(color.opacity(0.2), lineWidth: 0.5)
        )
    }

    // MARK: - Charts Tab

    private var chartsTab: some View {
        VStack(spacing: AppSpacing.sectionSpacing) {
            // Equity Curve
            chartSection("Equity Curve") {
                equityCurveChart
            }

            // Daily Returns
            chartSection("Daily Returns") {
                dailyReturnsChart
            }

            // Drawdown
            chartSection("Drawdown") {
                drawdownChart
            }
        }
    }

    private func chartSection<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            Text(title)
                .font(AppFont.headlineSmall)
                .foregroundColor(.xauTextSecondary)
            content()
                .frame(height: 200)
                .padding(AppSpacing.md)
                .background(Color.xauCard)
                .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        }
    }

    private var equityCurveChart: some View {
        Chart(vm.equityCurve) { point in
            AreaMark(
                x: .value("Date", point.date),
                y: .value("Equity", point.equity)
            )
            .foregroundStyle(
                LinearGradient(
                    colors: [Color.xauGold.opacity(0.4), Color.xauGold.opacity(0.05)],
                    startPoint: .top, endPoint: .bottom
                )
            )
            LineMark(
                x: .value("Date", point.date),
                y: .value("Equity", point.equity)
            )
            .foregroundStyle(Color.xauGold)
            .lineStyle(StrokeStyle(lineWidth: 2))
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                    .foregroundStyle(Color.xauBorder)
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(AppFormat.shortNumber(v))
                            .font(AppFont.monoTiny)
                            .foregroundColor(.xauTextTertiary)
                    }
                }
            }
        }
        .chartXAxis { AxisMarks { AxisValueLabel().foregroundStyle(Color.xauTextTertiary) } }
        .chartYScale(domain: vm.equityMin * 0.99 ... vm.equityMax * 1.01)
    }

    private var dailyReturnsChart: some View {
        Chart(vm.dailyReturns) { ret in
            BarMark(
                x: .value("Date", ret.date),
                y: .value("P&L", ret.pnl)
            )
            .foregroundStyle(vm.returnColor(ret))
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine().foregroundStyle(Color.xauBorder)
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(AppFormat.shortNumber(v))
                            .font(AppFont.monoTiny)
                            .foregroundColor(.xauTextTertiary)
                    }
                }
            }
        }
        .chartXAxis { AxisMarks { AxisValueLabel().foregroundStyle(Color.xauTextTertiary) } }
    }

    private var drawdownChart: some View {
        Chart(vm.drawdown) { point in
            AreaMark(
                x: .value("Date", point.date),
                yStart: .value("DD", point.drawdown),
                yEnd:   .value("Zero", 0)
            )
            .foregroundStyle(
                LinearGradient(
                    colors: [Color.xauLoss.opacity(0.05), Color.xauLoss.opacity(0.3)],
                    startPoint: .top, endPoint: .bottom
                )
            )
            LineMark(
                x: .value("Date", point.date),
                y: .value("DD", point.drawdown)
            )
            .foregroundStyle(Color.xauLoss)
            .lineStyle(StrokeStyle(lineWidth: 1.5))
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine().foregroundStyle(Color.xauBorder)
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(AppFormat.pct(v, decimals: 1))
                            .font(AppFont.monoTiny)
                            .foregroundColor(.xauTextTertiary)
                    }
                }
            }
        }
        .chartXAxis { AxisMarks { AxisValueLabel().foregroundStyle(Color.xauTextTertiary) } }
    }

    // MARK: - Sessions Tab

    private var sessionsTab: some View {
        VStack(spacing: AppSpacing.md) {
            if vm.sessionStats.isEmpty {
                EmptyStateView(icon: "clock", title: "No Session Data", subtitle: "")
            } else {
                Chart(vm.sessionStats) { stat in
                    BarMark(
                        x: .value("Session", stat.session.uppercased()),
                        y: .value("P&L", stat.totalPnl)
                    )
                    .foregroundStyle(stat.totalPnl >= 0 ? Color.xauProfit : Color.xauLoss)

                    PointMark(
                        x: .value("Session", stat.session.uppercased()),
                        y: .value("Win Rate", stat.winRate)
                    )
                    .foregroundStyle(Color.xauGold)
                    .symbolSize(50)
                }
                .frame(height: 220)
                .padding()
                .background(Color.xauCard)
                .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))

                ForEach(vm.sessionStats) { stat in
                    sessionRow(stat)
                }
            }
        }
    }

    private func sessionRow(_ stat: SessionStat) -> some View {
        HStack {
            Text(stat.session.uppercased())
                .font(AppFont.labelLarge)
                .foregroundColor(.xauGold)
                .frame(width: 60, alignment: .leading)

            VStack(alignment: .leading, spacing: 2) {
                Text("\(stat.trades) trades | WR: \(AppFormat.pct(stat.winRate))")
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextSecondary)
            }

            Spacer()

            Text(AppFormat.usd(stat.totalPnl))
                .font(AppFont.monoSmall)
                .foregroundColor(Color.pnlColor(stat.totalPnl))
        }
        .padding(AppSpacing.md)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))
    }

    // MARK: - Regimes Tab

    private var regimesTab: some View {
        VStack(spacing: AppSpacing.md) {
            if vm.regimeStats.isEmpty {
                EmptyStateView(icon: "chart.bar.xaxis", title: "No Regime Data", subtitle: "")
            } else {
                ForEach(vm.regimeStats) { stat in
                    regimeRow(stat)
                }
            }
        }
    }

    private func regimeRow(_ stat: RegimeStat) -> some View {
        HStack(spacing: AppSpacing.md) {
            VStack(alignment: .leading, spacing: 4) {
                Text(stat.regime)
                    .font(AppFont.headlineSmall)
                    .foregroundColor(.xauTextPrimary)
                Text("\(stat.trades) trades | WR: \(AppFormat.pct(stat.winRate))")
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextSecondary)
                Text("Expectancy: \(AppFormat.usd(stat.expectancy))")
                    .font(AppFont.caption)
                    .foregroundColor(.xauTextTertiary)
            }
            Spacer()
            Text(AppFormat.usd(stat.totalPnl))
                .font(AppFont.monoSmall)
                .foregroundColor(Color.pnlColor(stat.totalPnl))
        }
        .padding(AppSpacing.lg)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
    }
}
