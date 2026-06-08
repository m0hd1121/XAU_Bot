// LogsView.swift
// XAUBot – Log Viewer with Filtering
// iOS 17+  |  Swift 5.9

import SwiftUI

struct LogsView: View {

    @StateObject private var vm = LogsViewModel()
    @State private var showFilters = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                content
            }
            .navigationTitle("Logs")
            .navigationBarTitleDisplayMode(.large)
            .toolbar { toolbarContent }
            .searchable(text: $vm.searchText, prompt: "Search logs…")
            .onSubmit(of: .search) { Task { await vm.load() } }
            .task { await vm.load() }
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
        VStack(spacing: 0) {
            logTypePicker
            if showFilters { filterBar }
            if vm.isLoading && vm.logs.isEmpty {
                Spacer()
                ProgressView("Loading logs…").tint(.xauGold)
                Spacer()
            } else if vm.logs.isEmpty {
                Spacer()
                EmptyStateView(icon: "doc.text.magnifyingglass",
                               title: "No Logs Found",
                               subtitle: "Try changing the log type or clearing filters.",
                               actionTitle: "Clear Filters",
                               action: { vm.clearFilters() })
                Spacer()
            } else {
                logList
            }
        }
    }

    // MARK: - Log Type Picker

    private var logTypePicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppSpacing.sm) {
                ForEach(vm.logTypes, id: \.self) { type in
                    Button {
                        vm.selectedLogType = type
                        Task { await vm.load() }
                    } label: {
                        Text(type.capitalized)
                            .font(AppFont.labelMedium)
                            .foregroundColor(vm.selectedLogType == type ? .xauGold : .xauTextTertiary)
                            .padding(.horizontal, AppSpacing.md)
                            .padding(.vertical, AppSpacing.sm)
                            .background(
                                vm.selectedLogType == type ? Color.xauGold.opacity(0.15) : Color.xauCard,
                                in: Capsule()
                            )
                            .overlay(Capsule().strokeBorder(
                                vm.selectedLogType == type ? Color.xauGold.opacity(0.4) : Color.xauBorder,
                                lineWidth: 0.5
                            ))
                    }
                }
            }
            .padding(.horizontal, AppSpacing.screenPadding)
            .padding(.vertical, AppSpacing.sm)
        }
        .background(Color.xauSurface)
    }

    // MARK: - Filter Bar

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppSpacing.sm) {
                filterChip("All Levels", selected: vm.selectedLevel == nil) {
                    vm.selectedLevel = nil
                    Task { await vm.load() }
                }
                ForEach(vm.logLevels, id: \.self) { level in
                    filterChip(level, selected: vm.selectedLevel == level, color: vm.levelColor(level)) {
                        vm.selectedLevel = (vm.selectedLevel == level) ? nil : level
                        Task { await vm.load() }
                    }
                }
            }
            .padding(.horizontal, AppSpacing.screenPadding)
            .padding(.vertical, AppSpacing.sm)
        }
        .background(Color.xauSurface)
    }

    private func filterChip(_ label: String, selected: Bool, color: Color = .xauGold, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(AppFont.labelSmall)
                .foregroundColor(selected ? color : .xauTextTertiary)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(selected ? color.opacity(0.15) : Color.xauCard, in: Capsule())
                .overlay(Capsule().strokeBorder(selected ? color.opacity(0.5) : Color.xauBorder, lineWidth: 0.5))
        }
    }

    // MARK: - Log List

    private var logList: some View {
        List {
            Section {
                HStack {
                    Text("\(vm.totalEntries) entries")
                        .font(AppFont.labelSmall)
                        .foregroundColor(.xauTextTertiary)
                    Spacer()
                    if vm.selectedLevel != nil || !vm.searchText.isEmpty {
                        Button("Clear Filters") { vm.clearFilters() }
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauGold)
                    }
                }
                .listRowBackground(Color.xauSurface)
                .listRowSeparator(.hidden)
            }

            ForEach(vm.logs) { entry in
                logEntryRow(entry)
                    .listRowBackground(Color.xauCard)
                    .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                    .listRowSeparator(.hidden)
            }

            if vm.currentPage < vm.totalPages {
                Section {
                    Button {
                        Task { await vm.loadNextPage() }
                    } label: {
                        HStack {
                            Spacer()
                            if vm.isLoadingMore {
                                ProgressView().tint(.xauGold)
                            } else {
                                Text("Load More")
                                    .font(AppFont.bodySmall)
                                    .foregroundColor(.xauGold)
                            }
                            Spacer()
                        }
                        .padding(.vertical, AppSpacing.md)
                    }
                    .listRowBackground(Color.xauSurface)
                }
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(Color.xauPrimary)
        .refreshable { await vm.load() }
    }

    private func logEntryRow(_ entry: LogEntry) -> some View {
        HStack(alignment: .top, spacing: AppSpacing.sm) {
            Image(systemName: vm.levelIcon(entry.level))
                .font(.system(size: 12))
                .foregroundColor(vm.levelColor(entry.level))
                .frame(width: 16, alignment: .center)
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: AppSpacing.sm) {
                    Text(entry.timestamp)
                        .font(AppFont.monoTiny)
                        .foregroundColor(.xauTextTertiary)
                    Text(entry.level)
                        .font(AppFont.labelSmall)
                        .foregroundColor(vm.levelColor(entry.level))
                    if !entry.logger.isEmpty {
                        Text(entry.logger)
                            .font(AppFont.labelSmall)
                            .foregroundColor(.xauTextTertiary)
                            .lineLimit(1)
                    }
                }
                Text(entry.message)
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextPrimary)
                    .lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)
        }
        .padding(.horizontal, AppSpacing.screenPadding)
        .padding(.vertical, AppSpacing.sm)
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button {
                withAnimation(AppAnimation.easeInOut) { showFilters.toggle() }
            } label: {
                Image(systemName: showFilters ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle")
                    .foregroundColor(vm.selectedLevel != nil ? .xauGold : .xauTextSecondary)
            }
        }
        ToolbarItem(placement: .topBarTrailing) {
            Button { Task { await vm.load() } } label: {
                Image(systemName: "arrow.clockwise")
                    .foregroundColor(.xauTextSecondary)
            }
            .disabled(vm.isLoading)
        }
    }
}
