// MetricGauge.swift
// XAUBot – Circular gauge using Canvas for CPU / RAM / Disk display
// iOS 17+  |  Swift 5.9

import SwiftUI

struct MetricGauge: View {
    let value:     Double    // 0.0 – 100.0
    let title:     String
    var thickness: CGFloat = 10
    var size:      CGFloat = 90

    private var fraction: Double { min(max(value / 100.0, 0), 1) }

    private var gaugeColor: Color {
        switch value {
        case 0..<60:  return .xauProfit
        case 60..<80: return .xauWarning
        default:      return .xauLoss
        }
    }

    var body: some View {
        VStack(spacing: AppSpacing.xs) {
            ZStack {
                // Track
                Circle()
                    .trim(from: 0, to: 0.75)
                    .stroke(Color.xauBorder, style: StrokeStyle(lineWidth: thickness, lineCap: .round))
                    .rotationEffect(.degrees(135))

                // Fill
                Circle()
                    .trim(from: 0, to: fraction * 0.75)
                    .stroke(
                        LinearGradient(
                            colors: [gaugeColor.opacity(0.7), gaugeColor],
                            startPoint: .leading, endPoint: .trailing
                        ),
                        style: StrokeStyle(lineWidth: thickness, lineCap: .round)
                    )
                    .rotationEffect(.degrees(135))
                    .animation(AppAnimation.springNormal, value: fraction)
                    .shadow(color: gaugeColor.opacity(0.4), radius: 4)

                // Center text
                VStack(spacing: 1) {
                    Text(String(format: "%.0f%%", value))
                        .font(.system(size: size * 0.2, weight: .bold, design: .monospaced))
                        .foregroundColor(.xauTextPrimary)
                        .contentTransition(.numericText())
                        .animation(AppAnimation.springNormal, value: value)
                }
            }
            .frame(width: size, height: size)

            Text(title)
                .font(AppFont.labelMedium)
                .foregroundColor(.xauTextSecondary)
        }
    }
}

#Preview {
    HStack(spacing: 24) {
        MetricGauge(value: 34, title: "CPU")
        MetricGauge(value: 67, title: "RAM")
        MetricGauge(value: 91, title: "Disk")
    }
    .padding(32)
    .background(Color.xauPrimary)
}
