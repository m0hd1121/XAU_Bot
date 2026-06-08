// ConfirmationAlert.swift
// XAUBot – ViewModifier for confirmation alerts used in bot control actions
// iOS 17+  |  Swift 5.9

import SwiftUI

// MARK: - ConfirmationConfig

struct ConfirmationConfig {
    let title:         String
    let message:       String
    let actionLabel:   String
    let isDestructive: Bool
    let action:        () async -> Void
}

// MARK: - ViewModifier

struct ConfirmationAlertModifier: ViewModifier {
    @Binding var config: ConfirmationConfig?

    func body(content: Content) -> some View {
        content
            .alert(
                config?.title ?? "",
                isPresented: Binding(
                    get:  { config != nil },
                    set:  { if !$0 { config = nil } }
                ),
                presenting: config
            ) { cfg in
                Button(
                    cfg.actionLabel,
                    role: cfg.isDestructive ? .destructive : nil
                ) {
                    let c = cfg
                    Task { await c.action() }
                    config = nil
                }
                Button("Cancel", role: .cancel) { config = nil }
            } message: { cfg in
                Text(cfg.message)
            }
    }
}

extension View {
    func confirmationAlert(config: Binding<ConfirmationConfig?>) -> some View {
        modifier(ConfirmationAlertModifier(config: config))
    }
}
