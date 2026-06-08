// EmptyStateView.swift
// XAUBot – Reusable empty state with icon, title, subtitle, optional action
// iOS 17+  |  Swift 5.9

import SwiftUI

struct EmptyStateView: View {
    let icon:       String
    let title:      String
    let subtitle:   String
    var actionTitle: String?
    var action:     (() -> Void)?

    var body: some View {
        VStack(spacing: AppSpacing.xl) {
            Image(systemName: icon)
                .font(.system(size: 56))
                .foregroundStyle(
                    LinearGradient(
                        colors: [Color.xauGold.opacity(0.6), Color.xauGold.opacity(0.3)],
                        startPoint: .top, endPoint: .bottom
                    )
                )
                .padding(.bottom, AppSpacing.sm)

            VStack(spacing: AppSpacing.sm) {
                Text(title)
                    .font(AppFont.headlineMedium)
                    .foregroundColor(.xauTextPrimary)
                    .multilineTextAlignment(.center)

                Text(subtitle)
                    .font(AppFont.bodySmall)
                    .foregroundColor(.xauTextSecondary)
                    .multilineTextAlignment(.center)
                    .lineLimit(3)
            }

            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(OutlineButtonStyle())
            }
        }
        .padding(AppSpacing.xxxl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
