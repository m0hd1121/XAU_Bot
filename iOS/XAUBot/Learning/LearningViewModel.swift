// LearningViewModel.swift
// XAUBot – Fetches learning stats, patterns, validation. Polls every 60s.
// iOS 17+  |  Swift 5.9

import Foundation
import SwiftUI

@MainActor
final class LearningViewModel: ObservableObject {

    @Published private(set) var stats:              LearningStats?
    @Published private(set) var patterns:           [PatternStat]    = []
    @Published private(set) var validationResults:  [ValidationResult] = []
    @Published private(set) var recentEvents:       [LearningEvent]  = []
    @Published private(set) var regimeStats:        [RegimeStat]     = []

    @Published private(set) var isLoading           = true
    @Published private(set) var errorMessage:       String?
    @Published private(set) var lastRefreshTime:    String = "—"

    private var pollTask: Task<Void, Never>?

    // MARK: - Load

    func load() async {
        isLoading    = true
        errorMessage = nil
        do {
            async let statsResult:    LearningStats  = APIClient.shared.request(Endpoint.learningStats)
            async let regimesResult:  [RegimeStat]   = APIClient.shared.request(Endpoint.analyticsRegimes)

            let (s, r) = try await (statsResult, regimesResult)
            stats             = s
            patterns          = s.patterns.sorted { $0.expectancy > $1.expectancy }
            validationResults = s.validationHistory
            recentEvents      = s.recentEvents
            regimeStats       = r

            let f = DateFormatter()
            f.timeStyle = .short
            lastRefreshTime = f.string(from: Date())
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    // MARK: - Polling

    func startPolling() {
        pollTask?.cancel()
        pollTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 60_000_000_000)   // 60s
                guard !Task.isCancelled else { break }
                await load()
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    // MARK: - Computed

    var tradesAnalyzed: String {
        stats.map { "\($0.tradesAnalyzed)" } ?? "—"
    }

    var validationStatusColor: Color {
        switch stats?.validationStatus {
        case "passed":  return .xauProfit
        case "failed":  return .xauLoss
        case "pending": return .xauWarning
        default:        return .xauNeutral
        }
    }

    var confidenceHistory: [ConfidencePoint] {
        stats?.confidenceHistory ?? []
    }
}
