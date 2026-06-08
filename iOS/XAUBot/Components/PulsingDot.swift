// PulsingDot.swift
// XAUBot – Reusable pulsing status indicator dot
// iOS 17+  |  Swift 5.9

import SwiftUI

struct PulsingDot: View {

    enum StatusColor {
        case active, stopped, paused, warning, unknown

        var color: Color {
            switch self {
            case .active:  return .xauProfit
            case .stopped: return .xauLoss
            case .paused:  return .xauInfo
            case .warning: return .xauWarning
            case .unknown: return .xauNeutral
            }
        }

        var shouldPulse: Bool { self == .active || self == .paused || self == .warning }
    }

    let status: StatusColor
    var size: CGFloat = 12

    @State private var isPulsing = false

    var body: some View {
        ZStack {
            if status.shouldPulse {
                Circle()
                    .fill(status.color.opacity(0.3))
                    .frame(width: size * 2.2, height: size * 2.2)
                    .scaleEffect(isPulsing ? 1.0 : 0.5)
                    .opacity(isPulsing ? 0 : 0.6)
                    .animation(
                        .easeOut(duration: 1.4).repeatForever(autoreverses: false),
                        value: isPulsing
                    )
            }
            Circle()
                .fill(status.color)
                .frame(width: size, height: size)
                .shadow(color: status.color.opacity(0.6), radius: size * 0.4)
        }
        .onAppear { isPulsing = true }
    }
}

extension BotStatus {
    var pulseStatus: PulsingDot.StatusColor {
        if emergencyStopped { return .stopped }
        if maintenanceMode  { return .warning }
        if paused           { return .paused }
        if running          { return .active }
        return .unknown
    }

    var statusLabel: String {
        if emergencyStopped { return "Emergency Stop" }
        if maintenanceMode  { return "Maintenance" }
        if paused           { return "Paused" }
        if running          { return "Running" }
        return "Stopped"
    }
}
