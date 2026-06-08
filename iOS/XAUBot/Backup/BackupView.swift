// BackupView.swift
// XAUBot – Backup & Export Center
// iOS 17+  |  Swift 5.9

import SwiftUI

struct BackupView: View {

    @StateObject private var vm = BackupViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                content
            }
            .navigationTitle("Backup & Export")
            .navigationBarTitleDisplayMode(.large)
            .toolbar { toolbarContent }
            .sheet(isPresented: $vm.showCreateSheet) { createSheet }
            .alert("Delete Backup", isPresented: $vm.showDeleteConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Delete", role: .destructive) {
                    Task { await vm.performDelete() }
                }
            } message: {
                Text("Permanently delete \(vm.backupToDelete?.filename ?? "this backup")?")
            }
            .alert("Restore Backup", isPresented: $vm.showRestoreConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Restore", role: .destructive) {
                    Task { await vm.performRestore() }
                }
            } message: {
                Text("Restore \(vm.backupToRestore?.filename ?? "backup")? The bot will restart and current state will be replaced.")
            }
            .alert("Error", isPresented: .init(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.errorMessage = nil }
            } message: { Text(vm.errorMessage ?? "") }
            .alert("Success", isPresented: .init(
                get: { vm.successMessage != nil },
                set: { if !$0 { vm.successMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.successMessage = nil }
            } message: { Text(vm.successMessage ?? "") }
        }
        .task { await vm.load() }
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if vm.isLoading && vm.backups.isEmpty {
            ProgressView("Loading backups…").tint(.xauGold)
        } else {
            ScrollView {
                VStack(spacing: AppSpacing.sectionSpacing) {
                    exportSection
                    backupsSection
                    Color.clear.frame(height: AppSpacing.huge)
                }
                .padding(.horizontal, AppSpacing.screenPadding)
                .padding(.top, AppSpacing.lg)
            }
            .refreshable { await vm.load() }
        }
    }

    // MARK: - Export Section

    private var exportSection: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            sectionHeader("Export Data", icon: "square.and.arrow.up.fill")

            HStack(spacing: AppSpacing.sm) {
                exportButton(title: "Trade History", subtitle: "CSV", icon: "chart.bar.doc.horizontal.fill") {
                    Task { await vm.exportTradesCSV() }
                }
                exportButton(title: "Analytics", subtitle: "JSON", icon: "chart.line.uptrend.xyaxis") {
                    Task { await vm.exportAnalyticsJSON() }
                }
            }
        }
    }

    private func exportButton(title: String, subtitle: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: AppSpacing.sm) {
                Image(systemName: icon)
                    .font(.system(size: 24))
                    .foregroundColor(.xauGold)
                Text(title)
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextPrimary)
                Text(subtitle)
                    .font(AppFont.labelSmall)
                    .foregroundColor(.xauTextTertiary)
            }
            .frame(maxWidth: .infinity)
            .padding(AppSpacing.xl)
            .background(Color.xauCard)
            .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
            .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
                .strokeBorder(Color.xauBorder, lineWidth: 0.5))
        }
    }

    // MARK: - Backups Section

    private var backupsSection: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            sectionHeader("Backups (\(vm.backups.count))", icon: "externaldrive.fill")

            if vm.backups.isEmpty {
                EmptyStateView(icon: "externaldrive", title: "No Backups",
                               subtitle: "Create your first backup using the button above.")
            } else {
                ForEach(vm.backups) { backup in
                    backupRow(backup)
                }
            }
        }
    }

    private func backupRow(_ backup: BackupRecord) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.sm) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(backup.filename)
                        .font(AppFont.bodySmall)
                        .foregroundColor(.xauTextPrimary)
                        .lineLimit(1)
                    HStack(spacing: AppSpacing.sm) {
                        Text(backup.createdAt)
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauTextTertiary)
                        Text("•")
                            .foregroundColor(.xauTextTertiary)
                        Text(vm.formattedSize(backup.sizeBytes))
                            .font(AppFont.monoTiny)
                            .foregroundColor(.xauTextTertiary)
                    }
                }
                Spacer()
                HStack(spacing: AppSpacing.sm) {
                    ForEach(vm.badgeIcons(backup), id: \.self) { icon in
                        Image(systemName: icon)
                            .font(.system(size: 11))
                            .foregroundColor(.xauGold.opacity(0.7))
                    }
                }
            }

            if let notes = backup.notes, !notes.isEmpty {
                Text(notes)
                    .font(AppFont.labelSmall)
                    .foregroundColor(.xauTextTertiary)
                    .lineLimit(2)
            }

            HStack(spacing: AppSpacing.sm) {
                actionButton("Restore", icon: "arrow.counterclockwise", color: .xauWarning) {
                    vm.confirmRestore(backup)
                }
                actionButton("Delete", icon: "trash.fill", color: .xauLoss) {
                    vm.confirmDelete(backup)
                }
                Spacer()
                if let restored = backup.restoredAt {
                    Text("Restored \(restored)")
                        .font(AppFont.labelSmall)
                        .foregroundColor(.xauProfit)
                }
            }
        }
        .padding(AppSpacing.cardPadding)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
            .strokeBorder(Color.xauBorder, lineWidth: 0.5))
    }

    private func actionButton(_ label: String, icon: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon).font(.system(size: 11))
                Text(label).font(AppFont.labelSmall)
            }
            .foregroundColor(color)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(color.opacity(0.12), in: Capsule())
        }
    }

    // MARK: - Create Sheet

    private var createSheet: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                VStack(spacing: AppSpacing.sectionSpacing) {
                    VStack(alignment: .leading, spacing: AppSpacing.md) {
                        Toggle(isOn: $vm.includeLogs) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Include Logs")
                                    .font(AppFont.bodySmall)
                                    .foregroundColor(.xauTextPrimary)
                                Text("Adds log files to the backup archive")
                                    .font(AppFont.labelSmall)
                                    .foregroundColor(.xauTextTertiary)
                            }
                        }
                        .tint(.xauGold)
                        .padding(AppSpacing.cardPadding)
                        .background(Color.xauCard)
                        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))

                        VStack(alignment: .leading, spacing: AppSpacing.sm) {
                            Text("Notes (optional)")
                                .font(AppFont.labelMedium)
                                .foregroundColor(.xauTextTertiary)
                            TextField("e.g. before config change", text: $vm.newBackupNotes)
                                .font(AppFont.bodySmall)
                                .foregroundColor(.xauTextPrimary)
                                .padding(AppSpacing.cardPadding)
                                .background(Color.xauCard)
                                .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
                                .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
                                    .strokeBorder(Color.xauBorder, lineWidth: 0.5))
                        }
                    }
                    .padding(.horizontal, AppSpacing.screenPadding)
                    .padding(.top, AppSpacing.lg)

                    Spacer()

                    Button {
                        Task { await vm.createBackup() }
                    } label: {
                        HStack {
                            Image(systemName: "externaldrive.badge.plus")
                            Text("Create Backup")
                        }
                        .font(AppFont.headlineSmall)
                        .foregroundColor(.black)
                        .frame(maxWidth: .infinity)
                        .padding(AppSpacing.md)
                        .background(LinearGradient.goldGradient)
                        .clipShape(Capsule())
                    }
                    .padding(.horizontal, AppSpacing.screenPadding)
                    .padding(.bottom, AppSpacing.xl)
                }
            }
            .navigationTitle("New Backup")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { vm.showCreateSheet = false }
                        .foregroundColor(.xauTextSecondary)
                }
            }
        }
    }

    // MARK: - Helpers

    private func sectionHeader(_ title: String, icon: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon).foregroundColor(.xauGold)
            Text(title).font(AppFont.headlineSmall).foregroundColor(.xauTextSecondary)
        }
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button {
                vm.showCreateSheet = true
            } label: {
                Label("New Backup", systemImage: "plus.circle.fill")
                    .foregroundColor(.xauGold)
            }
            .disabled(vm.isCreating)
        }
    }
}
