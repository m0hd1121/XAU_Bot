// VPSViewModel.swift
// XAUBot – VPS Monitoring ViewModel
// iOS 17+  |  Swift 5.9

import Foundation
import SwiftUI

@MainActor
final class VPSViewModel: ObservableObject {

    // MARK: - Published state

    @Published var vpsStats: VPSStats?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var restartingService: String?
    @Published var showRestartConfirm = false
    @Published var serviceToRestart: ServiceStatus?
    @Published var lastRefreshTime: String = "—"

    private var refreshTask: Task<Void, Never>?

    // MARK: - Auto-refresh

    func startAutoRefresh() {
        refreshTask?.cancel()
        refreshTask = Task {
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(for: .seconds(10))
            }
        }
    }

    func stopAutoRefresh() {
        refreshTask?.cancel()
        refreshTask = nil
    }

    // MARK: - Load

    func load() async {
        if vpsStats == nil { isLoading = true }
        defer { isLoading = false }
        do {
            vpsStats = try await APIClient.shared.request(Endpoint.vpsStats)
            errorMessage = nil
            let f = DateFormatter(); f.timeStyle = .short
            lastRefreshTime = f.string(from: Date())
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Service Restart

    func confirmRestart(_ service: ServiceStatus) {
        serviceToRestart = service
        showRestartConfirm = true
    }

    func performRestart() async {
        guard let service = serviceToRestart else { return }
        restartingService = service.name
        defer { restartingService = nil }
        do {
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.restartServiceById(name: service.name)
            )
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Computed helpers

    var services: [ServiceStatus] { vpsStats?.services ?? [] }

    func gaugeColor(pct: Double) -> Color {
        if pct > 90 { return .xauLoss }
        if pct > 70 { return .xauWarning }
        return .xauProfit
    }

    func serviceColor(_ s: ServiceStatus) -> Color {
        switch s.status {
        case "active":   return .xauProfit
        case "failed":   return .xauLoss
        case "inactive": return .xauNeutral
        default:         return .xauWarning
        }
    }

    func serviceIcon(_ s: ServiceStatus) -> String {
        switch s.status {
        case "active":   return "checkmark.circle.fill"
        case "failed":   return "xmark.circle.fill"
        case "inactive": return "pause.circle.fill"
        default:         return "questionmark.circle.fill"
        }
    }
}
