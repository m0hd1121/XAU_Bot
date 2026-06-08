// VPSView.swift
// XAUBot – VPS Monitoring & Service Control
// iOS 17+  |  Swift 5.9

import SwiftUI

struct VPSView: View {

    @StateObject private var vm = VPSViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                content
            }
            .navigationTitle("VPS Monitor")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Text(vm.lastRefreshTime)
                        .font(AppFont.caption)
                        .foregroundColor(.xauTextTertiary)
                }
            }
            .task {
                await vm.load()
                vm.startAutoRefresh()
            }
            .onDisappear { vm.stopAutoRefresh() }
            .alert("Restart Service", isPresented: $vm.showRestartConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Restart", role: .destructive) {
                    Task { await vm.performRestart() }
                }
            } message: {
                Text("Restart \(vm.serviceToRestart?.displayName ?? "service")? It will be briefly unavailable.")
            }
            .alert("Error", isPresented: .init(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.errorMessage = nil }
            } message: { Text(vm.errorMessage ?? "") }
        }
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if vm.isLoading && vm.vpsStats == nil {
            ProgressView("Loading VPS stats…").tint(.xauGold)
        } else if let stats = vm.vpsStats {
            ScrollView {
                VStack(spacing: AppSpacing.sectionSpacing) {
                    resourceGauges(stats)
                    systemInfo(stats)
                    servicesSection
                    Color.clear.frame(height: AppSpacing.huge)
                }
                .padding(.horizontal, AppSpacing.screenPadding)
                .padding(.top, AppSpacing.lg)
            }
            .refreshable { await vm.load() }
        } else {
            EmptyStateView(
                icon: "server.rack",
                title: "VPS Unreachable",
                subtitle: vm.errorMessage ?? "Cannot connect to VPS.",
                actionTitle: "Retry",
                action: { Task { await vm.load() } }
            )
        }
    }

    // MARK: - Resource Gauges

    private func resourceGauges(_ stats: VPSStats) -> some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())],
                  spacing: AppSpacing.gridSpacing) {
            gaugeCard(label: "CPU", value: stats.cpuPct, unit: "%",
                      color: vm.gaugeColor(pct: stats.cpuPct), icon: "cpu")
            gaugeCard(label: "RAM", value: stats.ramPct, unit: "%",
                      color: vm.gaugeColor(pct: stats.ramPct), icon: "memorychip",
                      subtitle: "\(String(format: "%.1f", stats.usedRamGb)) / \(String(format: "%.1f", stats.totalRamGb)) GB")
            gaugeCard(label: "Disk", value: stats.diskPct, unit: "%",
                      color: vm.gaugeColor(pct: stats.diskPct), icon: "internaldrive",
                      subtitle: "\(String(format: "%.0f", stats.usedDiskGb)) / \(String(format: "%.0f", stats.totalDiskGb)) GB")
        }
    }

    private func gaugeCard(label: String, value: Double, unit: String,
                           color: Color, icon: String, subtitle: String? = nil) -> some View {
        VStack(spacing: AppSpacing.sm) {
            ZStack {
                Circle()
                    .stroke(Color.xauBorder, lineWidth: 4)
                Circle()
                    .trim(from: 0, to: max(0, min(1, value / 100)))
                    .stroke(color, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(AppAnimation.easeInOut, value: value)
                VStack(spacing: 0) {
                    Image(systemName: icon)
                        .font(.system(size: 12))
                        .foregroundColor(color)
                    Text(String(format: "%.0f%@", value, unit))
                        .font(AppFont.monoTiny)
                        .foregroundColor(.xauTextPrimary)
                }
            }
            .frame(width: 68, height: 68)
            Text(label)
                .font(AppFont.labelMedium)
                .foregroundColor(.xauTextTertiary)
            if let sub = subtitle {
                Text(sub)
                    .font(AppFont.labelSmall)
                    .foregroundColor(.xauTextTertiary)
                    .multilineTextAlignment(.center)
            }
        }
        .padding(AppSpacing.md)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
            .strokeBorder(Color.xauBorder, lineWidth: 0.5))
    }

    // MARK: - System Info

    private func systemInfo(_ stats: VPSStats) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            sectionHeader("System", icon: "info.circle.fill")

            infoRow("Uptime", AppFormat.uptime(seconds: stats.uptimeSeconds))
            Divider().background(Color.xauBorder)
            infoRow("OS", stats.osVersion)
            Divider().background(Color.xauBorder)
            infoRow("Python", stats.pythonVersion)
            Divider().background(Color.xauBorder)
            infoRow("Bot Version", stats.botVersion)
            Divider().background(Color.xauBorder)
            infoRow("Load Avg",
                    stats.loadAverage.prefix(3).map { String(format: "%.2f", $0) }.joined(separator: "  "))
            Divider().background(Color.xauBorder)
            HStack {
                infoCell("Net In",  "\(String(format: "%.1f", stats.networkIn)) KB/s")
                Spacer()
                infoCell("Net Out", "\(String(format: "%.1f", stats.networkOut)) KB/s")
            }
        }
        .padding(AppSpacing.cardPadding)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
            .strokeBorder(Color.xauBorder, lineWidth: 0.5))
    }

    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .font(AppFont.bodySmall)
                .foregroundColor(.xauTextTertiary)
            Spacer()
            Text(value)
                .font(AppFont.monoSmall)
                .foregroundColor(.xauTextPrimary)
        }
    }

    private func infoCell(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(AppFont.labelSmall).foregroundColor(.xauTextTertiary)
            Text(value).font(AppFont.monoSmall).foregroundColor(.xauTextPrimary)
        }
    }

    // MARK: - Services

    private var servicesSection: some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            sectionHeader("Services", icon: "gearshape.2.fill")

            if vm.services.isEmpty {
                Text("No services found.")
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextTertiary)
                    .padding()
            } else {
                ForEach(vm.services) { service in
                    serviceRow(service)
                    if service.id != vm.services.last?.id {
                        Divider().background(Color.xauBorder)
                    }
                }
            }
        }
        .padding(AppSpacing.cardPadding)
        .background(Color.xauCard)
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
        .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
            .strokeBorder(Color.xauBorder, lineWidth: 0.5))
    }

    private func serviceRow(_ service: ServiceStatus) -> some View {
        HStack(spacing: AppSpacing.md) {
            Image(systemName: vm.serviceIcon(service))
                .font(.system(size: 20))
                .foregroundColor(vm.serviceColor(service))
                .frame(width: 28)

            VStack(alignment: .leading, spacing: 2) {
                Text(service.displayName)
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextPrimary)
                HStack(spacing: AppSpacing.sm) {
                    Text(service.status.capitalized)
                        .font(AppFont.labelSmall)
                        .foregroundColor(vm.serviceColor(service))
                    if let uptime = service.uptime {
                        Text("• \(uptime)")
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauTextTertiary)
                    }
                    if let mem = service.memoryMb {
                        Text("• \(String(format: "%.0f", mem)) MB")
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauTextTertiary)
                    }
                }
            }

            Spacer()

            if service.canRestart {
                Button {
                    vm.confirmRestart(service)
                } label: {
                    if vm.restartingService == service.name {
                        ProgressView().tint(.xauGold).scaleEffect(0.7)
                    } else {
                        Image(systemName: "arrow.clockwise.circle.fill")
                            .font(.system(size: 22))
                            .foregroundColor(.xauGold)
                    }
                }
                .disabled(vm.restartingService != nil)
            }
        }
        .padding(.vertical, AppSpacing.xs)
    }

    // MARK: - Helpers

    private func sectionHeader(_ title: String, icon: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon).foregroundColor(.xauGold)
            Text(title).font(AppFont.headlineSmall).foregroundColor(.xauTextSecondary)
        }
    }
}
