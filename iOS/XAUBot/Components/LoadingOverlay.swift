// LoadingOverlay.swift
// XAUBot – Full-screen loading overlay ViewModifier
// iOS 17+  |  Swift 5.9

import SwiftUI

// MARK: - LoadingOverlayView

struct LoadingOverlayView: View {
    var message: String = "Loading…"

    var body: some View {
        ZStack {
            Color.black.opacity(0.5)
                .ignoresSafeArea()
                .blur(radius: 2)

            VStack(spacing: AppSpacing.lg) {
                ProgressView()
                    .progressViewStyle(CircularProgressViewStyle(tint: .xauGold))
                    .scaleEffect(1.4)

                Text(message)
                    .font(AppFont.bodyMedium)
                    .foregroundColor(.xauTextSecondary)
            }
            .padding(AppSpacing.xxxl)
            .background(Color.xauCard)
            .clipShape(RoundedRectangle(cornerRadius: AppRadius.xl))
            .cardShadow()
        }
    }
}

// MARK: - ViewModifier

struct LoadingOverlayModifier: ViewModifier {
    let isLoading: Bool
    let message:   String

    func body(content: Content) -> some View {
        ZStack {
            content
            if isLoading {
                LoadingOverlayView(message: message)
                    .transition(.opacity)
            }
        }
        .animation(AppAnimation.easeOut, value: isLoading)
    }
}

extension View {
    func loadingOverlay(_ isLoading: Bool, message: String = "Loading…") -> some View {
        modifier(LoadingOverlayModifier(isLoading: isLoading, message: message))
    }
}
