// BotControlViewModel.swift
// XAUBot – ViewModel for bot control panel: actions, confirmation, status
// iOS 17+  |  Swift 5.9

import Combine
import Foundation
import SwiftUI

@MainActor
final class BotControlViewModel: ObservableObject {

    @Published private(set) var botStatus:       BotStatus?
    @Published private(set) var isLoading        = false
    @Published private(set) var recentActions:   [ActionLog] = []
    @Published var confirmationConfig:           ConfirmationConfig?
    @Published private(set) var errorMessage:    String?

    struct ActionLog: Identifiable {
        let id        = UUID()
        let timestamp = Date()
        let action:   String
        let result:   String
        let success:  Bool
    }

    // MARK: - Load

    func load() async {
        isLoading = true
        do {
            botStatus = try await APIClient.shared.request(Endpoint.botStatus)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    // MARK: - Actions with Confirmation

    func requestStart() {
        confirmationConfig = ConfirmationConfig(
            title: "Start Bot",
            message: "The trading bot will begin scanning for opportunities and executing trades.",
            actionLabel: "Start",
            isDestructive: false,
            action: { [weak self] in await self?.performAction("Start", endpoint: Endpoint.startBot) }
        )
    }

    func requestStop() {
        confirmationConfig = ConfirmationConfig(
            title: "Stop Bot",
            message: "The bot will stop scanning. Open positions will remain open.",
            actionLabel: "Stop",
            isDestructive: true,
            action: { [weak self] in await self?.performAction("Stop", endpoint: Endpoint.stopBot) }
        )
    }

    func requestRestart() {
        confirmationConfig = ConfirmationConfig(
            title: "Restart Bot",
            message: "The bot will be stopped and restarted. This may take a few seconds.",
            actionLabel: "Restart",
            isDestructive: false,
            action: { [weak self] in await self?.performAction("Restart", endpoint: Endpoint.restartBot) }
        )
    }

    func requestPause() {
        let isPaused = botStatus?.paused ?? false
        confirmationConfig = ConfirmationConfig(
            title: isPaused ? "Resume Bot" : "Pause Bot",
            message: isPaused ? "The bot will resume scanning for trades."
                              : "The bot will pause. Existing positions remain open, no new trades will be opened.",
            actionLabel: isPaused ? "Resume" : "Pause",
            isDestructive: false,
            action: { [weak self] in
                let ep = isPaused ? Endpoint.resumeBot : Endpoint.pauseBot
                await self?.performAction(isPaused ? "Resume" : "Pause", endpoint: ep)
            }
        )
    }

    func requestEmergencyStop() {
        confirmationConfig = ConfirmationConfig(
            title: "⚠️ Emergency Stop",
            message: "This will immediately halt ALL trading activity and attempt to close all open positions. Use only in emergencies.",
            actionLabel: "EMERGENCY STOP",
            isDestructive: true,
            action: { [weak self] in await self?.performAction("Emergency Stop", endpoint: Endpoint.emergencyStop) }
        )
    }

    func requestToggleLearning() {
        let enabled = botStatus?.learningEnabled ?? false
        confirmationConfig = ConfirmationConfig(
            title: enabled ? "Disable Learning" : "Enable Learning",
            message: enabled ? "The learning engine will stop updating trading parameters."
                             : "The learning engine will analyze trades and adjust parameters.",
            actionLabel: enabled ? "Disable" : "Enable",
            isDestructive: enabled,
            action: { [weak self] in
                let ep = enabled ? Endpoint.disableLearning : Endpoint.enableLearning
                await self?.performAction(enabled ? "Disable Learning" : "Enable Learning", endpoint: ep)
            }
        )
    }

    func requestToggleMaintenance() {
        let inMaintenance = botStatus?.maintenanceMode ?? false
        confirmationConfig = ConfirmationConfig(
            title: inMaintenance ? "Disable Maintenance Mode" : "Enable Maintenance Mode",
            message: inMaintenance ? "Normal operation will resume."
                                   : "The bot will enter maintenance mode. No trades will be executed.",
            actionLabel: inMaintenance ? "Disable" : "Enable",
            isDestructive: false,
            action: { [weak self] in
                let ep = inMaintenance ? Endpoint.disableMaintenance : Endpoint.enableMaintenance
                await self?.performAction(inMaintenance ? "Disable Maintenance" : "Enable Maintenance", endpoint: ep)
            }
        )
    }

    func requestSetMode(_ mode: String) {
        let label = mode.capitalized
        confirmationConfig = ConfirmationConfig(
            title: "Switch to \(label) Mode",
            message: "The bot mode will be changed to \(label). You will need to restart the bot for the change to take effect.",
            actionLabel: "Set \(label)",
            isDestructive: false,
            action: { [weak self] in
                await self?.performAction("Set Mode: \(label)", endpoint: Endpoint.setBotMode(mode: mode))
            }
        )
    }

    func requestRestartService(_ name: String, displayName: String) {
        confirmationConfig = ConfirmationConfig(
            title: "Restart \(displayName)",
            message: "The \(displayName) service will be restarted. This may cause a brief interruption.",
            actionLabel: "Restart",
            isDestructive: false,
            action: { [weak self] in
                await self?.performAction("Restart \(displayName)", endpoint: Endpoint.restartService(name: name))
            }
        )
    }

    // MARK: - Perform Action

    private func performAction(_ name: String, endpoint: Endpoint) async {
        isLoading    = true
        errorMessage = nil
        do {
            let _: ActionResponse = try await APIClient.shared.request(endpoint)
            logAction(name, result: "Success", success: true)
            ToastManager.shared.show("\(name) executed successfully.", type: .success)
            await load()    // refresh status
        } catch {
            logAction(name, result: error.localizedDescription, success: false)
            errorMessage = error.localizedDescription
            ToastManager.shared.show("Failed: \(error.localizedDescription)", type: .error)
        }
        isLoading = false
    }

    private func logAction(_ action: String, result: String, success: Bool) {
        let entry = ActionLog(action: action, result: result, success: success)
        recentActions.insert(entry, at: 0)
        if recentActions.count > 50 { recentActions.removeLast() }
    }
}
