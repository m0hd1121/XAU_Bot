// ConfigurationViewModel.swift
// XAUBot – Strategy Configuration ViewModel
// iOS 17+  |  Swift 5.9

import Foundation
import SwiftUI

@MainActor
final class ConfigurationViewModel: ObservableObject {

    // MARK: - Published state

    @Published var config: ConfigModel?
    @Published var isLoading = false
    @Published var isSaving = false
    @Published var errorMessage: String?
    @Published var saveSuccess = false
    @Published var selectedSection: ConfigSection = .risk
    @Published var hasUnsavedChanges = false

    // Working copies of nested config sections
    @Published var riskDraft:       ConfigModel.RiskConfig?
    @Published var strategyDraft:   ConfigModel.StrategyConfig?
    @Published var psychologyDraft: ConfigModel.PsychologyConfig?
    @Published var learningDraft:   ConfigModel.LearningConfig?
    @Published var sessionsDraft:   ConfigModel.SessionsConfig?
    @Published var executionDraft:  ConfigModel.ExecutionConfig?

    // MARK: - Types

    enum ConfigSection: String, CaseIterable, Identifiable {
        case risk       = "Risk"
        case strategy   = "Strategy"
        case psychology = "Psychology"
        case learning   = "Learning"
        case sessions   = "Sessions"
        case execution  = "Execution"
        var id: String { rawValue }

        var icon: String {
            switch self {
            case .risk:       return "shield.fill"
            case .strategy:   return "chart.line.uptrend.xyaxis"
            case .psychology: return "brain.head.profile"
            case .learning:   return "sparkles"
            case .sessions:   return "clock.fill"
            case .execution:  return "arrow.triangle.2.circlepath"
            }
        }
    }

    // MARK: - Load

    func loadConfig() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            config = try await APIClient.shared.request(Endpoint.getConfig)
            resetDrafts()
            hasUnsavedChanges = false
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func resetDrafts() {
        guard let c = config else { return }
        riskDraft       = c.risk
        strategyDraft   = c.strategy
        psychologyDraft = c.psychology
        learningDraft   = c.learning
        sessionsDraft   = c.sessions
        executionDraft  = c.execution
    }

    // MARK: - Save

    func saveConfig() async {
        guard var updated = config,
              let r = riskDraft, let s = strategyDraft,
              let p = psychologyDraft, let l = learningDraft,
              let se = sessionsDraft, let e = executionDraft
        else { return }

        updated.risk       = r
        updated.strategy   = s
        updated.psychology = p
        updated.learning   = l
        updated.sessions   = se
        updated.execution  = e

        isSaving = true
        errorMessage = nil
        defer { isSaving = false }

        do {
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.updateConfig(config: updated)
            )
            saveSuccess = true
            hasUnsavedChanges = false
            await loadConfig()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func markChanged() { hasUnsavedChanges = true }

    func discardChanges() {
        resetDrafts()
        hasUnsavedChanges = false
    }
}
