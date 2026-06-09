// LogsViewModel.swift
// XAUBot – Log Viewer ViewModel
// iOS 17+  |  Swift 5.9

import Combine
import Foundation
import SwiftUI

@MainActor
final class LogsViewModel: ObservableObject {

    // MARK: - Published state

    @Published var logs: [LogEntry] = []
    @Published var isLoading = false
    @Published var isLoadingMore = false
    @Published var errorMessage: String?

    @Published var selectedLogType = "bot"
    @Published var selectedLevel: String? = nil
    @Published var searchText = ""
    @Published var currentPage = 1
    @Published var totalPages = 1
    @Published var totalEntries = 0

    @Published var isStreaming = false

    let logTypes  = ["bot", "api", "trades"]
    let logLevels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    // MARK: - Load

    func load() async {
        isLoading = true
        currentPage = 1
        logs = []
        defer { isLoading = false }
        await fetchPage(1)
    }

    func loadNextPage() async {
        guard currentPage < totalPages, !isLoadingMore else { return }
        isLoadingMore = true
        defer { isLoadingMore = false }
        await fetchPage(currentPage + 1)
    }

    private func fetchPage(_ page: Int) async {
        do {
            let response: LogsResponse = try await APIClient.shared.request(
                Endpoint.logs(
                    type: selectedLogType,
                    level: selectedLevel,
                    search: searchText.isEmpty ? nil : searchText,
                    page: page,
                    pageSize: 50
                )
            )
            if page == 1 {
                logs = response.logs
            } else {
                logs.append(contentsOf: response.logs)
            }
            currentPage  = response.page
            totalPages   = response.totalPages
            totalEntries = response.total
            errorMessage = nil
        } catch is CancellationError {
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Filter helpers

    func applyFilters() async { await load() }

    func clearFilters() {
        selectedLevel = nil
        searchText = ""
        Task { await load() }
    }

    // MARK: - Display helpers

    func levelColor(_ level: String) -> Color {
        switch level.uppercased() {
        case "DEBUG":    return .logDebug
        case "INFO":     return .logInfo
        case "WARNING":  return .logWarning
        case "ERROR":    return .logError
        case "CRITICAL": return .logCritical
        default:         return .xauNeutral
        }
    }

    func levelIcon(_ level: String) -> String {
        switch level.uppercased() {
        case "DEBUG":    return "ant.fill"
        case "INFO":     return "info.circle.fill"
        case "WARNING":  return "exclamationmark.triangle.fill"
        case "ERROR":    return "xmark.circle.fill"
        case "CRITICAL": return "flame.fill"
        default:         return "circle.fill"
        }
    }
}
