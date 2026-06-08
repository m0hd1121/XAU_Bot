// ToastView.swift
// XAUBot – Toast notification overlay with auto-dismiss and slide-in animation
// iOS 17+  |  Swift 5.9

import Combine
import SwiftUI

// MARK: - Toast Type

enum ToastType {
    case success, error, info, warning

    var icon: String {
        switch self {
        case .success: return "checkmark.circle.fill"
        case .error:   return "xmark.circle.fill"
        case .info:    return "info.circle.fill"
        case .warning: return "exclamationmark.triangle.fill"
        }
    }

    var color: Color {
        switch self {
        case .success: return .xauProfit
        case .error:   return .xauLoss
        case .info:    return .xauInfo
        case .warning: return .xauWarning
        }
    }
}

// MARK: - ToastItem

struct ToastItem: Identifiable {
    let id        = UUID()
    let message:  String
    let type:     ToastType
    var duration: Double = 3.0
}

// MARK: - ToastManager

@MainActor
final class ToastManager: ObservableObject {
    static let shared = ToastManager()

    @Published private(set) var currentToast: ToastItem?
    private var dismissTask: Task<Void, Never>?

    private init() {}

    func show(_ message: String, type: ToastType = .info, duration: Double = 3.0) {
        dismissTask?.cancel()
        currentToast = ToastItem(message: message, type: type, duration: duration)
        dismissTask  = Task {
            try? await Task.sleep(nanoseconds: UInt64(duration * 1_000_000_000))
            guard !Task.isCancelled else { return }
            withAnimation(AppAnimation.easeOut) { currentToast = nil }
        }
    }

    func dismiss() {
        dismissTask?.cancel()
        withAnimation(AppAnimation.easeOut) { currentToast = nil }
    }
}

// MARK: - ToastView

struct ToastView: View {
    @EnvironmentObject var toastManager: ToastManager

    var body: some View {
        VStack {
            if let toast = toastManager.currentToast {
                HStack(spacing: AppSpacing.sm) {
                    Image(systemName: toast.type.icon)
                        .foregroundColor(toast.type.color)
                        .font(.system(size: 16, weight: .semibold))

                    Text(toast.message)
                        .font(AppFont.bodySmall)
                        .foregroundColor(.xauTextPrimary)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)

                    Spacer(minLength: 0)

                    Button {
                        toastManager.dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.xauTextTertiary)
                    }
                }
                .padding(.horizontal, AppSpacing.lg)
                .padding(.vertical, AppSpacing.md)
                .background(
                    RoundedRectangle(cornerRadius: AppRadius.md)
                        .fill(Color.xauCard)
                        .overlay(
                            RoundedRectangle(cornerRadius: AppRadius.md)
                                .strokeBorder(toast.type.color.opacity(0.4), lineWidth: 1)
                        )
                )
                .cardShadow()
                .padding(.horizontal, AppSpacing.xl)
                .padding(.top, 8)
                .transition(.move(edge: .top).combined(with: .opacity))
                .onTapGesture { toastManager.dismiss() }
            }
            Spacer()
        }
        .animation(AppAnimation.springNormal, value: toastManager.currentToast?.id)
    }
}
