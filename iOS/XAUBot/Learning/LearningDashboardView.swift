// LearningDashboardView.swift
// XAUBot – Learning engine dashboard: confidence chart, patterns, validation history
// iOS 17+  |  Swift 5.9

import SwiftUI
import Charts

struct LearningDashboardView: View {
    @StateObject private var vm = LearningViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()

                if vm.isLoading && vm.stats == nil {
                    ProgressView("Loading learning data…")
                        .tint(.xauGold)
                } else {
                    ScrollView {
                        VStack(spacing: AppSpacing.sectionSpacing) {
                            // Header summary
                            headerCard

                            // Confidence chart
                            if !vm.confidenceHistory.isEmpty {
                                confidenceChart
                            }

                            // Patterns
                            patternsList

                            // Validation history
                            validationSection

                            // Recent events
                            eventsTimeline

                            Color.clear.frame(height: AppSpacing.huge)
                        }
                        .padding(.horizontal, AppSpacing.screenPadding)
                        .padding(.top, AppSpacing.lg)
                    }
                    .refreshable {
                        await vm.load()
                    }
                }
            }
            .navigationTitle("Learning Engine")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Text("Refreshed: \(vm.lastRefreshTime)")
                        .font(AppFont.caption)
                        .foregroundColor(.xauTextTertiary)
                }
            }
            .task {
                await vm.load()
                vm.startPolling()
            }
            .onDisappear { vm.stopPolling() }
        }
    }

    // MARK: - Header Card

    private var headerCard: some View {
        HStack(spacing: AppSpacing.xl) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Trades Analyzed")
                    .font(AppFont.labelMedium)
                    .foregroundColor(.xauTextTertiary)
                Text(vm.tradesAnalyzed)
                    .font(AppFont.monoMedium)
                    .foregroundColor(.xauTextPrimary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 4) {
                Text("Validation")
                    .font(AppFont.labelMedium)
                    .foregroundColor(.xauTextTertiary)
                HStack(spacing: 6) {
                    Circle()
                        .fill(vm.validationStatusColor)
                        .frame(width: 8, height: 8)
                    Text((vm.stats?.validationStatus ?? "—").capitalized)
                        .font(AppFont.headlineSmall)
                        .foregroundColor(vm.validationStatusColor)
                }
            }
        }
        .padding(AppSpacing.xl)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.xl))
        .overlay(
            RoundedRectangle(cornerRadius: AppRadius.xl)
                .strokeBorder(Color.xauGold.opacity(0.2), lineWidth: 0.5)
        )
    }

    // MARK: - Confidence Chart

    private var confidenceChart: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            Text("Confidence Evolution")
                .font(AppFont.headlineSmall)
                .foregroundColor(.xauTextSecondary)

            Chart(vm.confidenceHistory) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Confidence", point.confidence)
                )
                .foregroundStyle(Color.xauGold)
                .lineStyle(StrokeStyle(lineWidth: 2))

                AreaMark(
                    x: .value("Date", point.date),
                    y: .value("Confidence", point.confidence)
                )
                .foregroundStyle(
                    LinearGradient(
                        colors: [Color.xauGold.opacity(0.25), Color.xauGold.opacity(0.02)],
                        startPoint: .top, endPoint: .bottom
                    )
                )
            }
            .chartYScale(domain: 0...1)
            .chartYAxis {
                AxisMarks(values: [0, 0.25, 0.5, 0.75, 1.0]) { value in
                    AxisGridLine().foregroundStyle(Color.xauBorder)
                    AxisValueLabel {
                        if let v = value.as(Double.self) {
                            Text(AppFormat.pctOfOne(v))
                                .font(AppFont.monoTiny)
                                .foregroundColor(.xauTextTertiary)
                        }
                    }
                }
            }
            .chartXAxis { AxisMarks { AxisValueLabel().foregroundStyle(Color.xauTextTertiary) } }
            .frame(height: 180)
            .padding(AppSpacing.md)
            .background(Color.xauCard)
            .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        }
    }

    // MARK: - Patterns List

    private var patternsList: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            Text("Significant Patterns")
                .font(AppFont.headlineSmall)
                .foregroundColor(.xauTextSecondary)

            if vm.patterns.isEmpty {
                Text("No patterns discovered yet.")
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextTertiary)
                    .padding()
            } else {
                ForEach(vm.patterns) { pattern in
                    patternRow(pattern)
                }
            }
        }
    }

    private func patternRow(_ p: PatternStat) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.sm) {
            HStack {
                Text(p.description)
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextPrimary)
                    .lineLimit(2)
                Spacer()
                Text("\(p.sampleCount) samples")
                    .font(AppFont.labelSmall)
                    .foregroundColor(.xauTextTertiary)
            }

            HStack(spacing: AppSpacing.xl) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Win Rate")
                        .font(AppFont.labelSmall)
                        .foregroundColor(.xauTextTertiary)
                    Text(AppFormat.pct(p.winRate))
                        .font(AppFont.monoSmall)
                        .foregroundColor(p.winRate >= 50 ? .xauProfit : .xauLoss)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text("Expectancy")
                        .font(AppFont.labelSmall)
                        .foregroundColor(.xauTextTertiary)
                    Text(AppFormat.usd(p.expectancy))
                        .font(AppFont.monoSmall)
                        .foregroundColor(Color.pnlColor(p.expectancy))
                }
                Spacer()
            }

            // Wilson CI bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.xauBorder)
                        .frame(height: 4)
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.xauGold)
                        .frame(width: geo.size.width * p.winRate / 100, height: 4)
                }
            }
            .frame(height: 4)

            Text("Wilson CI: \(AppFormat.pct(p.wilsonLower)) – \(AppFormat.pct(p.wilsonUpper))")
                .font(AppFont.caption)
                .foregroundColor(.xauTextTertiary)
        }
        .padding(AppSpacing.lg)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
    }

    // MARK: - Validation Section

    private var validationSection: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            Text("Walk-Forward Validation")
                .font(AppFont.headlineSmall)
                .foregroundColor(.xauTextSecondary)

            if vm.validationResults.isEmpty {
                Text("No validation runs yet.")
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextTertiary)
                    .padding()
            } else {
                ForEach(vm.validationResults) { result in
                    validationRow(result)
                }
            }
        }
    }

    private func validationRow(_ r: ValidationResult) -> some View {
        HStack(spacing: AppSpacing.md) {
            Image(systemName: r.passed ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundColor(r.passed ? .xauProfit : .xauLoss)
                .font(.title3)

            VStack(alignment: .leading, spacing: 2) {
                Text(r.runDate)
                    .font(AppFont.labelLarge)
                    .foregroundColor(.xauTextPrimary)
                Text("\(r.foldCount) folds | Sharpe: \(String(format: "%.2f", r.sharpe)) | WR: \(AppFormat.pct(r.winRate))")
                    .font(AppFont.caption)
                    .foregroundColor(.xauTextSecondary)
            }

            Spacer()

            Text(r.passed ? "PASS" : "FAIL")
                .font(AppFont.labelMedium)
                .foregroundColor(r.passed ? .xauProfit : .xauLoss)
                .padding(.horizontal, AppSpacing.sm)
                .padding(.vertical, 3)
                .background((r.passed ? Color.xauProfit : Color.xauLoss).opacity(0.15))
                .clipShape(Capsule())
        }
        .padding(AppSpacing.md)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.md))
    }

    // MARK: - Events Timeline

    private var eventsTimeline: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            Text("Recent Events")
                .font(AppFont.headlineSmall)
                .foregroundColor(.xauTextSecondary)

            ForEach(vm.recentEvents.prefix(10)) { event in
                HStack(alignment: .top, spacing: AppSpacing.md) {
                    VStack {
                        Circle()
                            .fill(Color.xauGold)
                            .frame(width: 8, height: 8)
                            .padding(.top, 6)
                        Rectangle()
                            .fill(Color.xauBorder)
                            .frame(width: 1)
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text(event.eventType)
                            .font(AppFont.labelLarge)
                            .foregroundColor(.xauGold)
                        Text(event.description)
                            .font(AppFont.bodySmall)
                            .foregroundColor(.xauTextSecondary)
                        Text(event.timestamp)
                            .font(AppFont.caption)
                            .foregroundColor(.xauTextTertiary)
                    }
                    Spacer()
                }
            }
        }
    }
}
