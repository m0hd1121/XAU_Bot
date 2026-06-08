import SwiftUI

struct MetricCard: View {
    let title:     String
    let value:     String
    var change:    Double? = nil
    var subtitle:  String? = nil
    var icon:      String? = nil
    var color:     Color   = .goldAccent
    var onTap:     (() -> Void)? = nil

    @State private var isPressed = false

    var body: some View {
        Button {
            onTap?()
        } label: {
            VStack(alignment: .leading, spacing: AppSpacing.sm) {
                HStack {
                    if let icon {
                        Image(systemName: icon)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(color)
                    }
                    Text(title)
                        .font(AppFont.caption1())
                        .foregroundColor(.textSecondary)
                        .lineLimit(1)
                    Spacer()
                    if let change {
                        changeLabel(change)
                    }
                }
                Text(value)
                    .font(AppFont.monoMedium())
                    .foregroundColor(.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                if let sub = subtitle {
                    Text(sub)
                        .font(AppFont.caption2())
                        .foregroundColor(.textTertiary)
                }
            }
            .padding(AppSpacing.lg)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.appCard)
            .cornerRadius(AppRadius.lg)
            .overlay(
                RoundedRectangle(cornerRadius: AppRadius.lg)
                    .stroke(Color.borderColor, lineWidth: 0.5)
            )
            .cardShadow()
            .scaleEffect(isPressed ? 0.97 : 1.0)
        }
        .buttonStyle(.plain)
        .simultaneousGesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in withAnimation(.spring(response: 0.2)) { isPressed = true } }
                .onEnded   { _ in withAnimation(.spring(response: 0.3)) { isPressed = false } }
        )
    }

    private func changeLabel(_ val: Double) -> some View {
        HStack(spacing: 2) {
            Image(systemName: val >= 0 ? "arrow.up" : "arrow.down")
            Text(String(format: "%.1f%%", abs(val)))
        }
        .font(AppFont.caption2())
        .foregroundColor(val >= 0 ? .profitGreen : .lossRed)
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background((val >= 0 ? Color.profitGreen : Color.lossRed).opacity(0.12))
        .cornerRadius(AppRadius.sm)
    }
}
