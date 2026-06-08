// ConfigurationView.swift
// XAUBot – Strategy Configuration Editor
// iOS 17+  |  Swift 5.9

import SwiftUI

struct ConfigurationView: View {

    @StateObject private var vm = ConfigurationViewModel()
    @State private var showSaveConfirm = false
    @State private var showDiscardConfirm = false
    @State private var showResetConfirm = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color.xauPrimary.ignoresSafeArea()
                configContent
            }
            .navigationTitle("Configuration")
            .navigationBarTitleDisplayMode(.large)
            .toolbar { toolbarContent }
            .alert("Save Changes", isPresented: $showSaveConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Save", role: .destructive) { Task { await vm.saveConfig() } }
            } message: {
                Text("Apply configuration changes? The bot will use these settings from the next evaluation cycle.")
            }
            .alert("Discard Changes", isPresented: $showDiscardConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Discard", role: .destructive) { vm.discardChanges() }
            } message: { Text("Discard all unsaved changes?") }
            .alert("Reset to Defaults", isPresented: $showResetConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Reset", role: .destructive) {
                    Task {
                        let _: MessageResponse? = try? await APIClient.shared.request(Endpoint.resetConfigToDefaults)
                        await vm.loadConfig()
                    }
                }
            } message: { Text("Reset ALL configuration to factory defaults? This cannot be undone.") }
            .alert("Error", isPresented: .init(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.errorMessage = nil }
            } message: { Text(vm.errorMessage ?? "") }
            .overlay { if vm.isSaving { LoadingOverlayView(message: "Saving…") } }
        }
        .task { await vm.loadConfig() }
    }

    // MARK: - Content

    @ViewBuilder
    private var configContent: some View {
        if vm.isLoading && vm.config == nil {
            ProgressView("Loading configuration…").tint(.xauGold)
        } else if vm.config != nil {
            VStack(spacing: 0) {
                sectionPicker
                if vm.hasUnsavedChanges { unsavedBanner }
                sectionScrollView
            }
        } else {
            EmptyStateView(icon: "gearshape.2", title: "Config Unavailable",
                           subtitle: vm.errorMessage ?? "Could not load configuration.",
                           actionTitle: "Retry",
                           action: { Task { await vm.loadConfig() } })
        }
    }

    // MARK: - Section Picker

    private var sectionPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppSpacing.sm) {
                ForEach(ConfigurationViewModel.ConfigSection.allCases) { section in
                    Button {
                        if vm.hasUnsavedChanges { showDiscardConfirm = true }
                        else { vm.selectedSection = section }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: section.icon).font(.system(size: 12))
                            Text(section.rawValue).font(AppFont.labelMedium)
                        }
                        .foregroundColor(vm.selectedSection == section ? .xauGold : .xauTextTertiary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(
                            vm.selectedSection == section ? Color.xauGold.opacity(0.15) : Color.xauCard,
                            in: Capsule()
                        )
                        .overlay(Capsule().strokeBorder(
                            vm.selectedSection == section ? Color.xauGold.opacity(0.4) : Color.xauBorder,
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

    // MARK: - Unsaved Banner

    private var unsavedBanner: some View {
        HStack {
            Image(systemName: "pencil.circle.fill").foregroundColor(.xauWarning)
            Text("Unsaved changes").font(AppFont.labelMedium).foregroundColor(.xauWarning)
            Spacer()
            Button("Discard") { showDiscardConfirm = true }
                .font(AppFont.labelSmall).foregroundColor(.xauLoss)
            Button("Save") { showSaveConfirm = true }
                .font(AppFont.captionBold).foregroundColor(.xauProfit)
        }
        .padding(.horizontal, AppSpacing.screenPadding)
        .padding(.vertical, AppSpacing.sm)
        .background(Color.xauWarning.opacity(0.1))
    }

    // MARK: - Section Scroll View

    private var sectionScrollView: some View {
        ScrollView {
            VStack(spacing: AppSpacing.sectionSpacing) {
                safetyReminder
                switch vm.selectedSection {
                case .risk:       riskSection
                case .strategy:   strategySection
                case .psychology: psychologySection
                case .learning:   learningSection
                case .sessions:   sessionsSection
                case .execution:  executionSection
                }
                Color.clear.frame(height: AppSpacing.huge)
            }
            .padding(.horizontal, AppSpacing.screenPadding)
            .padding(.top, AppSpacing.lg)
        }
        .background(Color.xauPrimary)
        .refreshable { await vm.loadConfig() }
    }

    // MARK: - Safety Reminder

    private var safetyReminder: some View {
        HStack(spacing: AppSpacing.sm) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.xauWarning)
            Text("Applies from next candle evaluation. Bot does NOT stop on config change.")
                .font(AppFont.labelSmall)
                .foregroundColor(.xauWarning)
        }
        .padding(AppSpacing.md)
        .background(Color.xauWarning.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: AppRadius.sm))
    }

    // MARK: - Risk Section

    @ViewBuilder
    private var riskSection: some View {
        if let r = Binding($vm.riskDraft) {
            configGroup("Position Sizing") {
                decimalField("Risk Per Trade", value: r.riskPerTrade,
                             hint: "0.01 = 1% of account balance")
                decimalField("Max Risk Per Trade", value: r.maxRiskPerTrade,
                             hint: "Hard ceiling, overrides learned sizing")
                intField("Max Open Trades", value: r.maxOpenTrades,
                         hint: "Simultaneous open positions")
            }
            configGroup("Drawdown Limits") {
                decimalField("Daily Loss Limit", value: r.maxDailyLoss,
                             hint: "Halt trading after this % daily loss")
                decimalField("Daily Drawdown Limit", value: r.dailyDrawdownLimit,
                             hint: "Account drawdown halt threshold")
            }
        }
    }

    // MARK: - Strategy Section

    @ViewBuilder
    private var strategySection: some View {
        if let s = Binding($vm.strategyDraft) {
            configGroup("Entry Filters") {
                decimalField("Min Confidence", value: s.minConfidence,
                             hint: "0.0–1.0; below this → setup skipped")
                decimalField("Min Zone Quality", value: s.minZoneQuality,
                             hint: "0.0–1.0; below this → zone ignored")
                toggleField("Require Sweep", value: s.requireSweep,
                            hint: "Only enter after liquidity sweep")
            }
            configGroup("Execution") {
                textField("Primary Timeframe", value: s.timeframePrimary,
                          hint: "e.g. 1H, 4H, 1D")
                toggleField("Use Market Orders", value: Binding($vm.executionDraft)?.useMarketOrders ?? .constant(false),
                            hint: "Market vs limit order placement")
            }
        }
    }

    // MARK: - Psychology Section

    @ViewBuilder
    private var psychologySection: some View {
        if let p = Binding($vm.psychologyDraft) {
            configGroup("Loss Streak") {
                intField("Max Consecutive Losses", value: p.maxConsecutiveLosses,
                         hint: "Trigger cooldown after N losses")
                intField("Cooldown (minutes)", value: p.cooldownMinutes,
                         hint: "Wait this long after max losses")
                intField("Max Daily Trades", value: p.maxDailyTrades,
                         hint: "Hard cap on trades per day")
            }
            configGroup("Trade Management") {
                decimalField("Break-Even After R", value: p.breakEvenAfterR,
                             hint: "Move SL to BE when unrealized R ≥ this")
                toggleField("Trailing Stop Enabled", value: p.trailingStopEnabled,
                            hint: "Trail SL after break-even is hit")
            }
        }
    }

    // MARK: - Learning Section

    @ViewBuilder
    private var learningSection: some View {
        if let l = Binding($vm.learningDraft) {
            configGroup("Learning Engine") {
                toggleField("Enabled", value: l.enabled,
                            hint: "Activate adaptive confidence filtering")
                intField("Min Samples", value: l.minSamples,
                         hint: "Patterns with fewer samples are ignored")
                intField("Retrain Interval (hours)", value: l.retrainInterval,
                         hint: "Re-run full analysis every N hours")
                intField("Validation Folds", value: l.validationFolds,
                         hint: "Cross-validation fold count")
                decimalField("Min Win Rate Threshold", value: l.minWinRateThreshold,
                             hint: "0.0–1.0; patterns below this are discarded")
            }
        }
    }

    // MARK: - Sessions Section

    @ViewBuilder
    private var sessionsSection: some View {
        if let s = Binding($vm.sessionsDraft) {
            configGroup("Active Sessions") {
                toggleField("London (07:00–12:00 UTC)", value: s.london, hint: "")
                toggleField("New York (13:00–17:00 UTC)", value: s.newYork, hint: "")
                toggleField("Tokyo (00:00–06:00 UTC)", value: s.tokyo, hint: "Low weight — range-bound")
                toggleField("Sydney (21:00–06:00 UTC)", value: s.sydney, hint: "")
                toggleField("Overlap (13:00–15:00 UTC)", value: s.overlap, hint: "Highest volatility window")
            }
        }
    }

    // MARK: - Execution Section

    @ViewBuilder
    private var executionSection: some View {
        if let e = Binding($vm.executionDraft) {
            configGroup("Spread & Slippage") {
                decimalField("Slippage (pips)", value: e.slippagePips,
                             hint: "Max allowed market order slippage")
                decimalField("Max Spread (pips)", value: e.maxSpreadPips,
                             hint: "Skip entry if spread exceeds this")
            }
            configGroup("Order Settings") {
                intField("Magic Number", value: e.magicNumber,
                         hint: "Unique identifier for this bot's orders")
                toggleField("Use Market Orders", value: e.useMarketOrders,
                            hint: "Market fills vs limit order placement")
            }
        }
    }

    // MARK: - Field Builders

    private func configGroup<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.sm) {
            Text(title)
                .font(AppFont.captionBold)
                .foregroundColor(.xauTextTertiary)
                .textCase(.uppercase)
                .padding(.leading, 4)
            VStack(spacing: 0) { content() }
                .background(Color.xauCard)
                .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
                .overlay(RoundedRectangle(cornerRadius: AppRadius.lg)
                    .strokeBorder(Color.xauBorder, lineWidth: 0.5))
        }
    }

    private func decimalField(_ label: String, value: Binding<Double>, hint: String) -> some View {
        fieldRow(label: label, hint: hint) {
            TextField("0.0", value: value, format: .number.precision(.fractionLength(0...4)))
                .keyboardType(.decimalPad)
                .multilineTextAlignment(.trailing)
                .font(AppFont.monoSmall)
                .foregroundColor(.xauGold)
                .frame(width: 100)
                .onChange(of: value.wrappedValue) { _ in vm.markChanged() }
        }
    }

    private func intField(_ label: String, value: Binding<Int>, hint: String) -> some View {
        fieldRow(label: label, hint: hint) {
            TextField("0", value: value, format: .number)
                .keyboardType(.numberPad)
                .multilineTextAlignment(.trailing)
                .font(AppFont.monoSmall)
                .foregroundColor(.xauGold)
                .frame(width: 80)
                .onChange(of: value.wrappedValue) { _ in vm.markChanged() }
        }
    }

    private func textField(_ label: String, value: Binding<String>, hint: String) -> some View {
        fieldRow(label: label, hint: hint) {
            TextField(hint, text: value)
                .multilineTextAlignment(.trailing)
                .font(AppFont.monoSmall)
                .foregroundColor(.xauGold)
                .frame(width: 80)
                .onChange(of: value.wrappedValue) { _ in vm.markChanged() }
        }
    }

    private func toggleField(_ label: String, value: Binding<Bool>, hint: String) -> some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(label).font(AppFont.bodySmall).foregroundColor(.xauTextPrimary)
                    if !hint.isEmpty {
                        Text(hint).font(.system(size: 11)).foregroundColor(.xauTextTertiary)
                    }
                }
                Spacer()
                Toggle("", isOn: value)
                    .tint(.xauGold)
                    .labelsHidden()
                    .onChange(of: value.wrappedValue) { _ in vm.markChanged() }
            }
            .padding(.horizontal, AppSpacing.cardPadding)
            .padding(.vertical, AppSpacing.sm)
            Divider().background(Color.xauBorder)
        }
    }

    private func fieldRow<Control: View>(label: String, hint: String, @ViewBuilder control: () -> Control) -> some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(label).font(AppFont.bodySmall).foregroundColor(.xauTextPrimary)
                    if !hint.isEmpty {
                        Text(hint).font(.system(size: 11)).foregroundColor(.xauTextTertiary)
                    }
                }
                Spacer()
                control()
            }
            .padding(.horizontal, AppSpacing.cardPadding)
            .padding(.vertical, AppSpacing.sm)
            Divider().background(Color.xauBorder)
        }
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Menu {
                Button("Reset to Defaults", role: .destructive) { showResetConfirm = true }
            } label: {
                Image(systemName: "ellipsis.circle").foregroundColor(.xauTextSecondary)
            }
        }
        ToolbarItemGroup(placement: .topBarTrailing) {
            if vm.hasUnsavedChanges {
                Button("Save") { showSaveConfirm = true }
                    .font(AppFont.headlineSmall).foregroundColor(.xauProfit)
            }
            Button { Task { await vm.loadConfig() } } label: {
                Image(systemName: "arrow.clockwise").foregroundColor(.xauTextSecondary)
            }
            .disabled(vm.isLoading)
        }
    }
}
