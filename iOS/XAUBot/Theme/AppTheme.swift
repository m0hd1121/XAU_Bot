// AppTheme.swift
// XAUBot – Complete design system: colors, typography, spacing, shadows, animations
// iOS 17+  |  Swift 5.9

import SwiftUI

// MARK: - Color Palette

extension Color {

    // ── Brand (raw values – adaptive via dark mode) ──────────────────────────
    /// Primary dark background #0A0E1A
    static let xauPrimary       = Color(red: 0.039, green: 0.055, blue: 0.102)
    /// Slightly elevated surface #0F1525
    static let xauSurface       = Color(red: 0.059, green: 0.082, blue: 0.145)
    /// Card background #141A2E
    static let xauCard          = Color(red: 0.078, green: 0.102, blue: 0.180)
    /// Border/separator #1E2640
    static let xauBorder        = Color(red: 0.118, green: 0.149, blue: 0.251)

    // ── Gold Accent ───────────────────────────────────────────────────────────
    /// Gold primary #D4AF37
    static let xauGold          = Color(red: 0.831, green: 0.686, blue: 0.216)
    /// Gold light #E8CB5A
    static let xauGoldLight     = Color(red: 0.910, green: 0.796, blue: 0.353)
    /// Gold dark #A88820
    static let xauGoldDark      = Color(red: 0.659, green: 0.533, blue: 0.125)

    // ── Semantic ──────────────────────────────────────────────────────────────
    /// Profit / success #00C896
    static let xauProfit        = Color(red: 0.000, green: 0.784, blue: 0.588)
    /// Loss / danger #FF3B5C
    static let xauLoss          = Color(red: 1.000, green: 0.231, blue: 0.361)
    /// Warning / paused #FF9F0A
    static let xauWarning       = Color(red: 1.000, green: 0.624, blue: 0.039)
    /// Info / accent blue #0A84FF
    static let xauInfo          = Color(red: 0.039, green: 0.518, blue: 1.000)
    /// Neutral/unknown grey #8E8EA0
    static let xauNeutral       = Color(red: 0.557, green: 0.557, blue: 0.627)

    // ── Text ──────────────────────────────────────────────────────────────────
    static let xauTextPrimary   = Color.white
    static let xauTextSecondary = Color(red: 0.639, green: 0.667, blue: 0.737)
    static let xauTextTertiary  = Color(red: 0.400, green: 0.420, blue: 0.490)

    // ── System adaptive ───────────────────────────────────────────────────────
    static let xauBackground        = Color(uiColor: .systemBackground)
    static let xauGroupedBackground = Color(uiColor: .systemGroupedBackground)
    static let xauFill              = Color(uiColor: .systemFill)

    // ── Log level colors ──────────────────────────────────────────────────────
    static let logDebug    = Color(red: 0.557, green: 0.557, blue: 0.627)
    static let logInfo     = Color(red: 0.039, green: 0.518, blue: 1.000)
    static let logWarning  = Color(red: 1.000, green: 0.624, blue: 0.039)
    static let logError    = Color(red: 1.000, green: 0.231, blue: 0.361)
    static let logCritical = Color(red: 0.800, green: 0.000, blue: 0.200)

    // ── Convenience: PnL colorizer ────────────────────────────────────────────
    static func pnlColor(_ value: Double) -> Color {
        if value > 0 { return .xauProfit }
        if value < 0 { return .xauLoss }
        return .xauTextSecondary
    }

    // ── Hex initializer ───────────────────────────────────────────────────────
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: .alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = Double((int & 0xFF0000) >> 16) / 255
        let g = Double((int & 0x00FF00) >> 8)  / 255
        let b = Double( int & 0x0000FF)         / 255
        self.init(red: r, green: g, blue: b)
    }
}

// MARK: - Typography

enum AppFont {
    // ── Display ──────────────────────────────────────────────────────────────
    static let displayLarge  = Font.system(size: 40, weight: .bold,        design: .rounded)
    static let displayMedium = Font.system(size: 32, weight: .bold,        design: .rounded)
    static let displaySmall  = Font.system(size: 26, weight: .semibold,    design: .rounded)

    // ── Headline ─────────────────────────────────────────────────────────────
    static let headlineLarge  = Font.system(size: 22, weight: .bold)
    static let headlineMedium = Font.system(size: 18, weight: .semibold)
    static let headlineSmall  = Font.system(size: 15, weight: .semibold)

    // ── Body ─────────────────────────────────────────────────────────────────
    static let bodyLarge   = Font.system(size: 17, weight: .regular)
    static let bodyMedium  = Font.system(size: 15, weight: .regular)
    static let bodySmall   = Font.system(size: 13, weight: .regular)

    // ── Label ────────────────────────────────────────────────────────────────
    static let labelLarge  = Font.system(size: 13, weight: .medium)
    static let labelMedium = Font.system(size: 11, weight: .medium)
    static let labelSmall  = Font.system(size: 10, weight: .medium)

    // ── Monospaced (prices & numbers) ────────────────────────────────────────
    static let monoLarge   = Font.system(size: 28, weight: .bold,      design: .monospaced)
    static let monoMedium  = Font.system(size: 20, weight: .semibold,  design: .monospaced)
    static let monoSmall   = Font.system(size: 14, weight: .regular,   design: .monospaced)
    static let monoTiny    = Font.system(size: 11, weight: .regular,   design: .monospaced)

    // ── Caption ──────────────────────────────────────────────────────────────
    static let caption     = Font.system(size: 12, weight: .regular)
    static let captionBold = Font.system(size: 12, weight: .semibold)

    // MARK: Function-style aliases (to match original linter output format)
    static func largeTitle()  -> Font { .system(size: 34, weight: .bold,    design: .rounded) }
    static func title1()      -> Font { .system(size: 28, weight: .bold,    design: .rounded) }
    static func title2()      -> Font { .system(size: 22, weight: .semibold,design: .rounded) }
    static func title3()      -> Font { .system(size: 20, weight: .semibold,design: .rounded) }
    static func headline()    -> Font { .system(size: 17, weight: .semibold) }
    static func body()        -> Font { .system(size: 17, weight: .regular)  }
    static func subheadline() -> Font { .system(size: 15, weight: .regular)  }
    static func footnote()    -> Font { .system(size: 13, weight: .regular)  }
    static func caption1()    -> Font { .system(size: 12, weight: .regular)  }
    static func caption2()    -> Font { .system(size: 11, weight: .regular)  }
    static func monoLargeF()  -> Font { .system(size: 28, weight: .bold,    design: .monospaced) }
    static func monoMediumF() -> Font { .system(size: 18, weight: .semibold,design: .monospaced) }
    static func monoSmallF()  -> Font { .system(size: 13, weight: .medium,  design: .monospaced) }
}

// MARK: - Number Formatting

enum AppFormat {
    static let currencyFormatter: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle           = .currency
        f.currencyCode          = "USD"
        f.maximumFractionDigits = 2
        f.minimumFractionDigits = 2
        return f
    }()

    static func usd(_ value: Double) -> String {
        currencyFormatter.string(from: NSNumber(value: value)) ?? "$0.00"
    }

    static func pct(_ value: Double, decimals: Int = 2) -> String {
        String(format: "%.\(decimals)f%%", value)
    }

    static func pctOfOne(_ value: Double) -> String {
        String(format: "%.2f%%", value * 100)
    }

    static func r(_ value: Double) -> String {
        String(format: "%+.2fR", value)
    }

    static func shortNumber(_ value: Double) -> String {
        switch abs(value) {
        case 1_000_000...: return String(format: "%.1fM", value / 1_000_000)
        case 1_000...:     return String(format: "%.1fK", value / 1_000)
        default:           return String(format: "%.2f", value)
        }
    }

    static func pips(_ value: Double) -> String {
        String(format: "%.1f pips", value)
    }

    static func uptime(seconds: Int) -> String {
        let d = seconds / 86_400
        let h = (seconds % 86_400) / 3_600
        let m = (seconds % 3_600) / 60
        if d > 0 { return "\(d)d \(h)h \(m)m" }
        if h > 0 { return "\(h)h \(m)m" }
        return "\(m)m"
    }
}

// MARK: - Spacing

enum AppSpacing {
    static let xxs: CGFloat =  2
    static let xs:  CGFloat =  4
    static let sm:  CGFloat =  8
    static let md:  CGFloat = 12
    static let lg:  CGFloat = 16
    static let xl:  CGFloat = 20
    static let xxl: CGFloat = 24
    static let xxxl: CGFloat = 32
    static let huge: CGFloat = 48

    static let screenPadding:  CGFloat = 16
    static let cardPadding:    CGFloat = 16
    static let sectionSpacing: CGFloat = 24
    static let listRowSpacing: CGFloat = 8
    static let gridSpacing:    CGFloat = 12
}

// MARK: - Corner Radius

enum AppRadius {
    static let xs:   CGFloat =  4
    static let sm:   CGFloat =  8
    static let md:   CGFloat = 12
    static let lg:   CGFloat = 16
    static let xl:   CGFloat = 20
    static let xxl:  CGFloat = 24
    static let full: CGFloat = 1_000
    static let pill: CGFloat = 50
}

// MARK: - Shadow

struct AppShadow {
    let color: Color
    let radius: CGFloat
    let x: CGFloat
    let y: CGFloat

    static let card      = AppShadow(color: .black.opacity(0.4),          radius: 12, x: 0, y: 4)
    static let button    = AppShadow(color: .black.opacity(0.3),          radius: 8,  x: 0, y: 2)
    static let overlay   = AppShadow(color: .black.opacity(0.6),          radius: 24, x: 0, y: 8)
    static let goldGlow  = AppShadow(color: Color.xauGold.opacity(0.35),  radius: 16, x: 0, y: 0)
    static let profitGlow = AppShadow(color: Color.xauProfit.opacity(0.3), radius: 12, x: 0, y: 0)
    static let lossGlow  = AppShadow(color: Color.xauLoss.opacity(0.3),   radius: 12, x: 0, y: 0)
}

extension View {
    func appShadow(_ style: AppShadow) -> some View {
        shadow(color: style.color, radius: style.radius, x: style.x, y: style.y)
    }

    func cardShadow() -> some View {
        shadow(color: .black.opacity(0.3), radius: 8, x: 0, y: 4)
    }

    func subtleShadow() -> some View {
        shadow(color: .black.opacity(0.15), radius: 4, x: 0, y: 2)
    }
}

// MARK: - Animation

enum AppAnimation {
    static let fast:     Double = 0.15
    static let normal:   Double = 0.25
    static let slow:     Double = 0.40
    static let verySlow: Double = 0.60

    static let springFast   = Animation.spring(response: 0.3,  dampingFraction: 0.7)
    static let springNormal = Animation.spring(response: 0.5,  dampingFraction: 0.75)
    static let springBouncy = Animation.spring(response: 0.4,  dampingFraction: 0.6)
    static let easeInOut    = Animation.easeInOut(duration: normal)
    static let easeOut      = Animation.easeOut(duration: normal)
    static let pulse        = Animation.easeInOut(duration: 1.2).repeatForever(autoreverses: true)
}

// MARK: - Card ViewModifier

struct CardStyle: ViewModifier {
    var padding: CGFloat = AppSpacing.cardPadding
    var cornerRadius: CGFloat = AppRadius.lg

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(Color.xauCard)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .strokeBorder(Color.xauBorder, lineWidth: 0.5)
            )
            .cardShadow()
    }
}

extension View {
    func cardStyle(padding: CGFloat = AppSpacing.cardPadding,
                   cornerRadius: CGFloat = AppRadius.lg) -> some View {
        modifier(CardStyle(padding: padding, cornerRadius: cornerRadius))
    }
}

// MARK: - Glassmorphism

struct GlassCard: ViewModifier {
    var cornerRadius: CGFloat = AppRadius.lg

    func body(content: Content) -> some View {
        content
            .background(
                ZStack {
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .fill(.ultraThinMaterial)
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .fill(Color.xauCard.opacity(0.5))
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .strokeBorder(Color.xauBorder, lineWidth: 0.5)
                }
            )
            .cardShadow()
    }
}

extension View {
    func glassCard(cornerRadius: CGFloat = AppRadius.lg) -> some View {
        modifier(GlassCard(cornerRadius: cornerRadius))
    }
}

// MARK: - Button Styles

struct GoldButtonStyle: ButtonStyle {
    var isFullWidth: Bool = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(AppFont.headlineSmall)
            .foregroundColor(.black)
            .padding(.horizontal, AppSpacing.xl)
            .padding(.vertical, AppSpacing.md)
            .frame(maxWidth: isFullWidth ? .infinity : nil)
            .background(
                LinearGradient(
                    colors: [Color.xauGoldLight, Color.xauGold, Color.xauGoldDark],
                    startPoint: .topLeading, endPoint: .bottomTrailing
                )
            )
            .clipShape(Capsule())
            .appShadow(AppShadow.goldGlow)
            .scaleEffect(configuration.isPressed ? 0.96 : 1.0)
            .animation(AppAnimation.springFast, value: configuration.isPressed)
    }
}

struct DestructiveButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(AppFont.headlineSmall)
            .foregroundColor(.white)
            .padding(.horizontal, AppSpacing.xl)
            .padding(.vertical, AppSpacing.md)
            .background(Color.xauLoss)
            .clipShape(Capsule())
            .appShadow(AppShadow.lossGlow)
            .scaleEffect(configuration.isPressed ? 0.96 : 1.0)
            .animation(AppAnimation.springFast, value: configuration.isPressed)
    }
}

struct OutlineButtonStyle: ButtonStyle {
    var color: Color = .xauGold

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(AppFont.headlineSmall)
            .foregroundColor(color)
            .padding(.horizontal, AppSpacing.xl)
            .padding(.vertical, AppSpacing.md)
            .overlay(Capsule().strokeBorder(color, lineWidth: 1.5))
            .scaleEffect(configuration.isPressed ? 0.96 : 1.0)
            .animation(AppAnimation.springFast, value: configuration.isPressed)
    }
}

// MARK: - Shimmer Effect

struct ShimmerModifier: ViewModifier {
    @State private var phase: CGFloat = 0

    func body(content: Content) -> some View {
        content
            .overlay(
                LinearGradient(
                    gradient: Gradient(stops: [
                        .init(color: .clear,               location: phase - 0.3),
                        .init(color: .white.opacity(0.15), location: phase),
                        .init(color: .clear,               location: phase + 0.3)
                    ]),
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .mask(content)
            .onAppear {
                withAnimation(Animation.linear(duration: 1.5).repeatForever(autoreverses: false)) {
                    phase = 1.3
                }
            }
    }
}

extension View {
    func shimmer() -> some View { modifier(ShimmerModifier()) }
}

// MARK: - Gradient Helpers

extension LinearGradient {
    static let goldGradient = LinearGradient(
        colors: [Color.xauGoldLight, Color.xauGold],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )
    static let profitGradient = LinearGradient(
        colors: [Color.xauProfit, Color.xauProfit.opacity(0.7)],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )
    static let lossGradient = LinearGradient(
        colors: [Color.xauLoss, Color.xauLoss.opacity(0.7)],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )
}
