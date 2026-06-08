// AnalyticsViewModel.swift
// XAUBot – Fetches and prepares analytics data for Swift Charts
// iOS 17+  |  Swift 5.9

import Foundation
import SwiftUI

@MainActor
final class AnalyticsViewModel: ObservableObject {

    @Published private(set) var overview:         AnalyticsOverview?
    @Published private(set) var equityCurve:      [EquityPoint]    = []
    @Published private(set) var dailyReturns:     [DailyReturn]    = []
    @Published private(set) var monthlyReturns:   [MonthlyReturn]  = []
    @Published private(set) var drawdown:         [DrawdownPoint]  = []
    @Published private(set) var sessionStats:     [SessionStat]    = []
    @Published private(set) var regimeStats:      [RegimeStat]     = []

    @Published private(set) var isLoading        = true
    @Published private(set) var errorMessage:    String?

    @Published var selectedDays: Int = 90   // default lookback

    // MARK: - KPI Strings

    var winRateStr:      String { overview.map { AppFormat.pct($0.winRate) } ?? "—" }
    var profitFactorStr: String { overview.map { String(format: "%.2f", $0.profitFactor) } ?? "—" }
    var expectancyStr:   String { overview.map { AppFormat.usd($0.expectancy) } ?? "—" }
    var sharpeStr:       String { overview.map { String(format: "%.2f", $0.sharpeRatio) } ?? "—" }
    var calmarStr:       String { overview.map { String(format: "%.2f", $0.calmarRatio) } ?? "—" }
    var maxDDStr:        String { overview.map { "\(AppFormat.pct($0.maxDrawdownPct, decimals: 1))" } ?? "—" }
    var totalPnlStr:     String { overview.map { AppFormat.usd($0.totalPnl) } ?? "—" }
    var avgRRStr:        String { overview.map { String(format: "%.2f", $0.avgRR) } ?? "—" }

    // MARK: - Load

    func load() async {
        isLoading    = true
        errorMessage = nil
        do {
            let data: AnalyticsData = try await APIClient.shared.request(
                Endpoint.fullAnalytics(days: selectedDays)
            )
            overview       = data.overview
            equityCurve    = data.equityCurve
            dailyReturns   = data.dailyReturns
            monthlyReturns = data.monthlyReturns
            drawdown       = data.drawdown
            sessionStats   = data.sessionStats
            regimeStats    = data.regimeStats
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    // MARK: - Equity Curve Helpers

    var equityMin:  Double { equityCurve.map(\.equity).min() ?? 0 }
    var equityMax:  Double { equityCurve.map(\.equity).max() ?? 1 }

    // MARK: - Daily Returns Color

    func returnColor(_ ret: DailyReturn) -> Color {
        ret.pnl >= 0 ? .xauProfit : .xauLoss
    }

    // MARK: - Monthly Heatmap

    var monthlyHeatmapData: [[MonthlyReturn?]] {
        // 12 months x N years grid, nil = no data
        let months = Array(1...12)
        let years  = Array(Set(monthlyReturns.map(\.year))).sorted()
        return months.map { month in
            years.map { year in
                monthlyReturns.first { $0.year == year && $0.month == month }
            }
        }
    }

    func heatmapColor(for ret: MonthlyReturn?) -> Color {
        guard let ret else { return Color.xauBorder }
        let maxAbs = monthlyReturns.map { abs($0.pct) }.max() ?? 1
        let intensity = abs(ret.pct) / max(maxAbs, 1)
        return ret.pct >= 0
            ? Color.xauProfit.opacity(0.2 + intensity * 0.8)
            : Color.xauLoss.opacity(0.2 + intensity * 0.8)
    }
}
