// MetricCard.swift
// XAUBot – Reusable metric card with shimmer loading, change indicator, glassmorphism
// iOS 17+  |  Swift 5.9

import SwiftUI

struct MetricCard: View {
    let title:      String
    let value:      String
    var subtitle:   String?
    var change:     Double?      // positive = up, negative = down, nil = no change
    var isLoading:  Bool = false
    var tintColor:  Color = .xauTextPrimary
    var action:     (() -> Void)? = nil

    var body: some View {
        Button {
            action?()
        } label: {
            cardContent
        }
        .buttonStyle(.plain)
        .disabled(action == nil)
    }

    private var cardContent: some View {
        VStack(alignment: .leading, spacing: AppSpacing.sm) {
            // Title
            Text(title)
                .font(AppFont.labelLarge)
                .foregroundColor(.xauTextSecondary)
                .lineLimit(1)

            // Value
            Group {
                if isLoading {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.xauBorder)
                        .frame(height: 28)
                        .shimmer()
                } else {
                    Text(value)
                        .font(AppFont.monoMedium)
                        .foregroundColor(tintColor)
                        .lineLimit(1)
                        .minimumScaleFactor(0.6)
                        .contentTransition(.numericText())
                        .animation(AppAnimation.springNormal, value: value)
                }
            }

            // Subtitle / Change
            if isLoading {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.xauBorder)
                    .frame(height: 14)
                    .shimmer()
            } else if let change {
                HStack(spacing: 2) {
                    Image(systemName: change >= 0 ? "arrow.up.right" : "arrow.down.right")
                        .font(.system(size: 10, weight: .bold))
                    Text(String(format: "%+.2f%%", change))
                        .font(AppFont.labelMedium)
                }
                .foregroundColor(change >= 0 ? .xauProfit : .xauLoss)
            } else if let subtitle {
                Text(subtitle)
                    .font(AppFont.caption)
                    .foregroundColor(.xauTextTertiary)
                    .lineLimit(1)
            }
        }
        .padding(AppSpacing.cardPadding)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            ZStack {
                RoundedRectangle(cornerRadius: AppRadius.lg)
                    .fill(Color.xauCard)
                RoundedRectangle(cornerRadius: AppRadius.lg)
                    .strokeBorder(Color.xauBorder, lineWidth: 0.5)
                // Subtle top gradient highlight
                LinearGradient(
                    colors: [Color.white.opacity(0.04), Color.clear],
                    startPoint: .top, endPoint: .center
                )
                .clipShape(RoundedRectangle(cornerRadius: AppRadius.lg))
            }
        )
        .cardShadow()
    }
}
