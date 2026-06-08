// BackupViewModel.swift
// XAUBot – Backup Management ViewModel
// iOS 17+  |  Swift 5.9

import Combine
import Foundation
import SwiftUI

@MainActor
final class BackupViewModel: ObservableObject {

    // MARK: - Published state

    @Published var backups: [BackupRecord] = []
    @Published var isLoading = false
    @Published var isCreating = false
    @Published var errorMessage: String?
    @Published var successMessage: String?

    @Published var showCreateSheet = false
    @Published var showDeleteConfirm = false
    @Published var showRestoreConfirm = false
    @Published var backupToDelete: BackupRecord?
    @Published var backupToRestore: BackupRecord?

    // Create sheet state
    @Published var newBackupNotes = ""
    @Published var includeLogs = true

    // MARK: - Load

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response: BackupsResponse = try await APIClient.shared.request(Endpoint.listBackups)
            backups = response.backups.sorted { $0.createdAt > $1.createdAt }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Create Backup

    func createBackup() async {
        isCreating = true
        showCreateSheet = false
        defer { isCreating = false }
        do {
            let _: BackupRecord = try await APIClient.shared.request(
                Endpoint.createBackup(request: CreateBackupRequest(
                    includeLogs: includeLogs,
                    notes: newBackupNotes.isEmpty ? nil : newBackupNotes
                ))
            )
            newBackupNotes = ""
            includeLogs = true
            successMessage = "Backup created successfully."
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Delete Backup

    func confirmDelete(_ backup: BackupRecord) {
        backupToDelete = backup
        showDeleteConfirm = true
    }

    func performDelete() async {
        guard let backup = backupToDelete else { return }
        do {
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.deleteBackup(filename: backup.filename)
            )
            successMessage = "Backup deleted."
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Restore Backup

    func confirmRestore(_ backup: BackupRecord) {
        backupToRestore = backup
        showRestoreConfirm = true
    }

    func performRestore() async {
        guard let backup = backupToRestore else { return }
        do {
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.restoreBackup(filename: backup.filename)
            )
            successMessage = "Backup restored. Bot will restart."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Export

    func exportTradesCSV() async {
        do {
            // Trigger download via browser / share sheet – backend returns CSV
            successMessage = "Export queued. Check your Files app shortly."
            let _: EmptyResponse = try await APIClient.shared.request(Endpoint.exportTrades(format: "csv"))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func exportAnalyticsJSON() async {
        do {
            successMessage = "Analytics export queued."
            let _: EmptyResponse = try await APIClient.shared.request(Endpoint.exportAnalytics)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Helpers

    func formattedSize(_ bytes: Int) -> String {
        let mb = Double(bytes) / 1_048_576
        if mb >= 1 { return String(format: "%.1f MB", mb) }
        let kb = Double(bytes) / 1_024
        return String(format: "%.0f KB", kb)
    }

    func badgeIcons(_ backup: BackupRecord) -> [String] {
        var icons: [String] = []
        if backup.includesDb     { icons.append("cylinder.fill") }
        if backup.includesConfig { icons.append("gearshape.fill") }
        if backup.includesLogs   { icons.append("doc.text.fill") }
        return icons
    }
}
