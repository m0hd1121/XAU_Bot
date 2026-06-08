// APIModels.swift
// XAUBot – All Codable structs for API request/response communication
// iOS 17+  |  Swift 5.9

import Foundation

// MARK: - Auth

struct AuthTokens: Codable {
    let accessToken:  String
    let refreshToken: String
    let tokenType:    String

    enum CodingKeys: String, CodingKey {
        case accessToken  = "access_token"
        case refreshToken = "refresh_token"
        case tokenType    = "token_type"
    }
}

struct LoginRequest: Codable {
    let username: String
    let password: String
    let totpCode: String?

    enum CodingKeys: String, CodingKey {
        case username
        case password
        case totpCode = "totp_code"
    }
}

struct BiometricLoginRequest: Codable {
    let biometricToken: String
    let deviceId: String

    enum CodingKeys: String, CodingKey {
        case biometricToken = "biometric_token"
        case deviceId       = "device_id"
    }
}

struct RefreshRequest: Codable {
    let refreshToken: String

    enum CodingKeys: String, CodingKey {
        case refreshToken = "refresh_token"
    }
}

struct UserProfile: Codable, Identifiable {
    let id: Int
    let username: String
    let role: String
    let isActive: Bool
    let twoFaEnabled: Bool
    let createdAt: String
    let lastLogin: String?
    let lastPasswordChange: String?

    enum CodingKeys: String, CodingKey {
        case id
        case username
        case role
        case isActive            = "is_active"
        case twoFaEnabled        = "two_fa_enabled"
        case createdAt           = "created_at"
        case lastLogin           = "last_login"
        case lastPasswordChange  = "last_password_change"
    }
}

struct ChangePasswordRequest: Codable {
    let currentPassword: String
    let newPassword: String

    enum CodingKeys: String, CodingKey {
        case currentPassword = "current_password"
        case newPassword     = "new_password"
    }
}

// MARK: - Dashboard

struct DashboardSnapshot: Codable {
    let botStatus:     BotStatus
    let accountInfo:   AccountInfo
    let openTrades:    [TradeRecord]
    let dailyPnl:      Double
    let weeklyPnl:     Double
    let monthlyPnl:    Double
    let unrealizedPnl: Double
    let sessionQuality: String   // "excellent" | "good" | "fair" | "poor"
    let timestamp:     String

    enum CodingKeys: String, CodingKey {
        case botStatus      = "bot_status"
        case accountInfo    = "account_info"
        case openTrades     = "open_trades"
        case dailyPnl       = "daily_pnl"
        case weeklyPnl      = "weekly_pnl"
        case monthlyPnl     = "monthly_pnl"
        case unrealizedPnl  = "unrealized_pnl"
        case sessionQuality = "session_quality"
        case timestamp
    }
}

// MARK: - Bot Status

struct BotStatus: Codable {
    let running:          Bool
    let paused:           Bool
    let maintenanceMode:  Bool
    let emergencyStopped: Bool
    let learningEnabled:  Bool
    let pid:              Int?
    let mode:             String  // "backtest" | "paper" | "live"
    let lastHeartbeat:    String?
    let lastTradeAt:      String?
    let openTradesCount:  Int
    let dailyPnl:         Double
    let equity:           Double
    let updatedAt:        String

    enum CodingKeys: String, CodingKey {
        case running
        case paused
        case maintenanceMode  = "maintenance_mode"
        case emergencyStopped = "emergency_stopped"
        case learningEnabled  = "learning_enabled"
        case pid
        case mode
        case lastHeartbeat    = "last_heartbeat"
        case lastTradeAt      = "last_trade_at"
        case openTradesCount  = "open_trades_count"
        case dailyPnl         = "daily_pnl"
        case equity
        case updatedAt        = "updated_at"
    }

    var statusLabel: String {
        if emergencyStopped { return "Emergency Stop" }
        if maintenanceMode  { return "Maintenance" }
        if paused           { return "Paused" }
        if running          { return "Running" }
        return "Stopped"
    }
}

// MARK: - Account Info

struct AccountInfo: Codable {
    let accountNumber: String
    let broker:        String
    let server:        String
    let currency:      String
    let leverage:      Int
    let balance:       Double
    let equity:        Double
    let margin:        Double
    let freeMargin:    Double
    let marginLevel:   Double?
    let connected:     Bool
    let latencyMs:     Int?

    enum CodingKeys: String, CodingKey {
        case accountNumber = "account_number"
        case broker
        case server
        case currency
        case leverage
        case balance
        case equity
        case margin
        case freeMargin    = "free_margin"
        case marginLevel   = "margin_level"
        case connected
        case latencyMs     = "latency_ms"
    }
}

// MARK: - Trade Record

struct TradeRecord: Codable, Identifiable {
    let id:            Int        // ticket number
    var ticket:        Int { id }
    let symbol:        String
    let direction:     String     // "BUY" | "SELL"
    let lots:          Double
    let openPrice:     Double
    let currentPrice:  Double?
    let stopLoss:      Double?
    let takeProfit:    Double?
    let openTime:      String
    let closeTime:     String?
    let closePrice:    Double?
    let pnl:           Double
    let pips:          Double?
    let commission:    Double
    let swap:          Double
    let session:       String?    // "london" | "ny" | "tokyo" | "sydney"
    let regime:        String?
    let confidence:    Double?
    let triggerType:   String?
    let sweepDetected: Bool?
    let zoneQuality:   Double?
    let rr:            Double?
    let status:        String     // "open" | "closed" | "pending"
    let aiExplanation: String?

    enum CodingKeys: String, CodingKey {
        case id            = "ticket"
        case symbol
        case direction
        case lots
        case openPrice     = "open_price"
        case currentPrice  = "current_price"
        case stopLoss      = "stop_loss"
        case takeProfit    = "take_profit"
        case openTime      = "open_time"
        case closeTime     = "close_time"
        case closePrice    = "close_price"
        case pnl
        case pips
        case commission
        case swap
        case session
        case regime
        case confidence
        case triggerType   = "trigger_type"
        case sweepDetected = "sweep_detected"
        case zoneQuality   = "zone_quality"
        case rr
        case status
        case aiExplanation = "ai_explanation"
    }
}

// MARK: - Trade History

struct TradeHistory: Codable {
    let trades:     [TradeRecord]
    let total:      Int
    let page:       Int
    let pageSize:   Int
    let totalPages: Int
    let winRate:    Double
    let totalPnl:   Double

    enum CodingKeys: String, CodingKey {
        case trades
        case total
        case page
        case pageSize   = "page_size"
        case totalPages = "total_pages"
        case winRate    = "win_rate"
        case totalPnl   = "total_pnl"
    }
}

// MARK: - Analytics

struct AnalyticsData: Codable {
    let overview:       AnalyticsOverview
    let equityCurve:    [EquityPoint]
    let dailyReturns:   [DailyReturn]
    let monthlyReturns: [MonthlyReturn]
    let drawdown:       [DrawdownPoint]
    let sessionStats:   [SessionStat]
    let regimeStats:    [RegimeStat]

    enum CodingKeys: String, CodingKey {
        case overview
        case equityCurve    = "equity_curve"
        case dailyReturns   = "daily_returns"
        case monthlyReturns = "monthly_returns"
        case drawdown
        case sessionStats   = "session_stats"
        case regimeStats    = "regime_stats"
    }
}

struct AnalyticsOverview: Codable {
    let totalTrades:    Int
    let winRate:        Double
    let profitFactor:   Double
    let expectancy:     Double
    let sharpeRatio:    Double
    let calmarRatio:    Double
    let maxDrawdown:    Double
    let maxDrawdownPct: Double
    let avgWin:         Double
    let avgLoss:        Double
    let bestTrade:      Double
    let worstTrade:     Double
    let totalPnl:       Double
    let avgRR:          Double

    enum CodingKeys: String, CodingKey {
        case totalTrades    = "total_trades"
        case winRate        = "win_rate"
        case profitFactor   = "profit_factor"
        case expectancy
        case sharpeRatio    = "sharpe_ratio"
        case calmarRatio    = "calmar_ratio"
        case maxDrawdown    = "max_drawdown"
        case maxDrawdownPct = "max_drawdown_pct"
        case avgWin         = "avg_win"
        case avgLoss        = "avg_loss"
        case bestTrade      = "best_trade"
        case worstTrade     = "worst_trade"
        case totalPnl       = "total_pnl"
        case avgRR          = "avg_rr"
    }
}

struct EquityPoint: Codable, Identifiable {
    let id = UUID()
    let date:   String
    let equity: Double
    let balance: Double

    enum CodingKeys: String, CodingKey {
        case date
        case equity
        case balance
    }
}

struct DailyReturn: Codable, Identifiable {
    let id = UUID()
    let date:   String
    let pnl:    Double
    let pct:    Double

    enum CodingKeys: String, CodingKey {
        case date
        case pnl
        case pct
    }
}

struct MonthlyReturn: Codable, Identifiable {
    let id = UUID()
    let year:  Int
    let month: Int
    let pnl:   Double
    let pct:   Double

    enum CodingKeys: String, CodingKey {
        case year
        case month
        case pnl
        case pct
    }
}

struct DrawdownPoint: Codable, Identifiable {
    let id = UUID()
    let date:     String
    let drawdown: Double  // negative value or 0

    enum CodingKeys: String, CodingKey {
        case date
        case drawdown
    }
}

struct SessionStat: Codable, Identifiable {
    let id = UUID()
    let session:    String
    let trades:     Int
    let winRate:    Double
    let totalPnl:   Double
    let avgRR:      Double

    enum CodingKeys: String, CodingKey {
        case session
        case trades
        case winRate  = "win_rate"
        case totalPnl = "total_pnl"
        case avgRR    = "avg_rr"
    }
}

struct RegimeStat: Codable, Identifiable {
    let id = UUID()
    let regime:     String
    let trades:     Int
    let winRate:    Double
    let totalPnl:   Double
    let expectancy: Double

    enum CodingKeys: String, CodingKey {
        case regime
        case trades
        case winRate    = "win_rate"
        case totalPnl   = "total_pnl"
        case expectancy
    }
}

// MARK: - Learning

struct LearningStats: Codable {
    let tradesAnalyzed:   Int
    let validationStatus: String    // "passed" | "failed" | "pending"
    let lastAnalysisTime: String?
    let confidenceHistory:[ConfidencePoint]
    let patterns:         [PatternStat]
    let recentEvents:     [LearningEvent]
    let validationHistory:[ValidationResult]

    enum CodingKeys: String, CodingKey {
        case tradesAnalyzed    = "trades_analyzed"
        case validationStatus  = "validation_status"
        case lastAnalysisTime  = "last_analysis_time"
        case confidenceHistory = "confidence_history"
        case patterns
        case recentEvents      = "recent_events"
        case validationHistory = "validation_history"
    }
}

struct ConfidencePoint: Codable, Identifiable {
    let id = UUID()
    let date:       String
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case date
        case confidence
    }
}

struct PatternStat: Codable, Identifiable {
    let id = UUID()
    let patternId:    String
    let description:  String
    let sampleCount:  Int
    let winRate:      Double
    let expectancy:   Double
    let wilsonLower:  Double
    let wilsonUpper:  Double
    let avgConfidence: Double

    enum CodingKeys: String, CodingKey {
        case patternId     = "pattern_id"
        case description
        case sampleCount   = "sample_count"
        case winRate       = "win_rate"
        case expectancy
        case wilsonLower   = "wilson_lower"
        case wilsonUpper   = "wilson_upper"
        case avgConfidence = "avg_confidence"
    }
}

struct LearningEvent: Codable, Identifiable {
    let id = UUID()
    let timestamp:   String
    let eventType:   String
    let description: String
    let impact:      Double?

    enum CodingKeys: String, CodingKey {
        case timestamp
        case eventType   = "event_type"
        case description
        case impact
    }
}

struct ValidationResult: Codable, Identifiable {
    let id = UUID()
    let runDate:    String
    let foldCount:  Int
    let passed:     Bool
    let sharpe:     Double
    let winRate:    Double
    let notes:      String?

    enum CodingKeys: String, CodingKey {
        case runDate   = "run_date"
        case foldCount = "fold_count"
        case passed
        case sharpe
        case winRate   = "win_rate"
        case notes
    }
}

// MARK: - VPS Stats

struct VPSStats: Codable {
    let cpuPct:      Double
    let ramPct:      Double
    let diskPct:     Double
    let networkIn:   Double    // KB/s
    let networkOut:  Double    // KB/s
    let uptimeSeconds: Int
    let osVersion:   String
    let pythonVersion: String
    let botVersion:  String
    let services:    [ServiceStatus]
    let loadAverage: [Double]  // 1m, 5m, 15m
    let totalRamGb:  Double
    let usedRamGb:   Double
    let totalDiskGb: Double
    let usedDiskGb:  Double

    enum CodingKeys: String, CodingKey {
        case cpuPct      = "cpu_pct"
        case ramPct      = "ram_pct"
        case diskPct     = "disk_pct"
        case networkIn   = "network_in"
        case networkOut  = "network_out"
        case uptimeSeconds = "uptime_seconds"
        case osVersion   = "os_version"
        case pythonVersion = "python_version"
        case botVersion  = "bot_version"
        case services
        case loadAverage = "load_average"
        case totalRamGb  = "total_ram_gb"
        case usedRamGb   = "used_ram_gb"
        case totalDiskGb = "total_disk_gb"
        case usedDiskGb  = "used_disk_gb"
    }
}

struct ServiceStatus: Codable, Identifiable {
    let id = UUID()
    let name:        String
    let displayName: String
    let status:      String    // "active" | "inactive" | "failed" | "unknown"
    let pid:         Int?
    let uptime:      String?
    let memoryMb:    Double?
    let canRestart:  Bool

    enum CodingKeys: String, CodingKey {
        case name
        case displayName = "display_name"
        case status
        case pid
        case uptime
        case memoryMb    = "memory_mb"
        case canRestart  = "can_restart"
    }
}

// MARK: - Configuration

struct ConfigModel: Codable {
    var risk:       RiskConfig
    var strategy:   StrategyConfig
    var psychology: PsychologyConfig
    var learning:   LearningConfig
    var sessions:   SessionsConfig
    var execution:  ExecutionConfig

    struct RiskConfig: Codable {
        var riskPerTrade:      Double
        var maxRiskPerTrade:   Double
        var dailyDrawdownLimit: Double
        var maxOpenTrades:     Int
        var maxDailyLoss:      Double

        enum CodingKeys: String, CodingKey {
            case riskPerTrade      = "risk_per_trade"
            case maxRiskPerTrade   = "max_risk_per_trade"
            case dailyDrawdownLimit = "daily_drawdown_limit"
            case maxOpenTrades     = "max_open_trades"
            case maxDailyLoss      = "max_daily_loss"
        }
    }

    struct StrategyConfig: Codable {
        var minConfidence:   Double
        var minZoneQuality:  Double
        var requireSweep:    Bool
        var timeframePrimary: String
        var symbols:         [String]

        enum CodingKeys: String, CodingKey {
            case minConfidence    = "min_confidence"
            case minZoneQuality   = "min_zone_quality"
            case requireSweep     = "require_sweep"
            case timeframePrimary = "timeframe_primary"
            case symbols
        }
    }

    struct PsychologyConfig: Codable {
        var maxConsecutiveLosses: Int
        var cooldownMinutes:      Int
        var breakEvenAfterR:      Double
        var trailingStopEnabled:  Bool
        var maxDailyTrades:       Int

        enum CodingKeys: String, CodingKey {
            case maxConsecutiveLosses = "max_consecutive_losses"
            case cooldownMinutes      = "cooldown_minutes"
            case breakEvenAfterR      = "break_even_after_r"
            case trailingStopEnabled  = "trailing_stop_enabled"
            case maxDailyTrades       = "max_daily_trades"
        }
    }

    struct LearningConfig: Codable {
        var enabled:          Bool
        var minSamples:       Int
        var retrainInterval:  Int    // hours
        var validationFolds:  Int
        var minWinRateThreshold: Double

        enum CodingKeys: String, CodingKey {
            case enabled
            case minSamples          = "min_samples"
            case retrainInterval     = "retrain_interval"
            case validationFolds     = "validation_folds"
            case minWinRateThreshold = "min_win_rate_threshold"
        }
    }

    struct SessionsConfig: Codable {
        var london:   Bool
        var newYork:  Bool
        var tokyo:    Bool
        var sydney:   Bool
        var overlap:  Bool

        enum CodingKeys: String, CodingKey {
            case london
            case newYork  = "new_york"
            case tokyo
            case sydney
            case overlap
        }
    }

    struct ExecutionConfig: Codable {
        var slippagePips:      Double
        var maxSpreadPips:     Double
        var magicNumber:       Int
        var comment:           String
        var useMarketOrders:   Bool

        enum CodingKeys: String, CodingKey {
            case slippagePips    = "slippage_pips"
            case maxSpreadPips   = "max_spread_pips"
            case magicNumber     = "magic_number"
            case comment
            case useMarketOrders = "use_market_orders"
        }
    }
}

// MARK: - Log Entry

struct LogEntry: Codable, Identifiable {
    let id = UUID()
    let timestamp: String
    let level:     String    // "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL"
    let logger:    String
    let message:   String
    let extra:     [String: String]?

    enum CodingKeys: String, CodingKey {
        case timestamp
        case level
        case logger
        case message
        case extra
    }
}

struct LogsResponse: Codable {
    let logs:       [LogEntry]
    let total:      Int
    let page:       Int
    let pageSize:   Int
    let totalPages: Int

    enum CodingKeys: String, CodingKey {
        case logs
        case total
        case page
        case pageSize   = "page_size"
        case totalPages = "total_pages"
    }
}

// MARK: - Notification Preferences

struct NotificationPrefs: Codable {
    var tradeOpened:    NotifPref
    var tradeClosed:    NotifPref
    var dailySummary:   NotifPref
    var vpsOffline:     NotifPref
    var brokerDisconnected: NotifPref
    var drawdownWarning:   NotifPref
    var riskLimit:      NotifPref
    var botStopped:     NotifPref
    var learningCompleted: NotifPref
    var criticalErrors: NotifPref

    struct NotifPref: Codable {
        var pushEnabled: Bool
        var inAppEnabled: Bool
        var threshold:   Double?

        enum CodingKeys: String, CodingKey {
            case pushEnabled  = "push_enabled"
            case inAppEnabled = "in_app_enabled"
            case threshold
        }
    }

    enum CodingKeys: String, CodingKey {
        case tradeOpened       = "trade_opened"
        case tradeClosed       = "trade_closed"
        case dailySummary      = "daily_summary"
        case vpsOffline        = "vps_offline"
        case brokerDisconnected = "broker_disconnected"
        case drawdownWarning   = "drawdown_warning"
        case riskLimit         = "risk_limit"
        case botStopped        = "bot_stopped"
        case learningCompleted = "learning_completed"
        case criticalErrors    = "critical_errors"
    }
}

// MARK: - Backup

struct BackupRecord: Codable, Identifiable {
    let id:             Int
    let filename:       String
    let sizeBytes:      Int
    let includesDb:     Bool
    let includesConfig: Bool
    let includesLogs:   Bool
    let createdBy:      String?
    let notes:          String?
    let checksumSha256: String?
    let restoredAt:     String?
    let createdAt:      String

    enum CodingKeys: String, CodingKey {
        case id
        case filename
        case sizeBytes      = "size_bytes"
        case includesDb     = "includes_db"
        case includesConfig = "includes_config"
        case includesLogs   = "includes_logs"
        case createdBy      = "created_by"
        case notes
        case checksumSha256 = "checksum_sha256"
        case restoredAt     = "restored_at"
        case createdAt      = "created_at"
    }
}

struct BackupsResponse: Codable {
    let backups: [BackupRecord]
    let total:   Int
}

struct CreateBackupRequest: Codable {
    let includeLogs: Bool
    let notes:       String?

    enum CodingKeys: String, CodingKey {
        case includeLogs = "include_logs"
        case notes
    }
}

// MARK: - Shared / Utility

struct EmptyResponse: Codable {}

struct MessageResponse: Codable {
    let message: String
    let success: Bool?
}

struct ActionResponse: Codable {
    let success: Bool
    let message: String
    let data:    AnyCodable?
}

// AnyCodable wrapper for heterogeneous JSON values
struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let int = try? container.decode(Int.self)        { value = int; return }
        if let double = try? container.decode(Double.self)  { value = double; return }
        if let bool = try? container.decode(Bool.self)      { value = bool; return }
        if let string = try? container.decode(String.self)  { value = string; return }
        value = NSNull()
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let int as Int:       try container.encode(int)
        case let double as Double: try container.encode(double)
        case let bool as Bool:     try container.encode(bool)
        case let string as String: try container.encode(string)
        default:                   try container.encodeNil()
        }
    }
}

// MARK: - Modify Trade Request

struct ModifyTradeRequest: Codable {
    let stopLoss:   Double?
    let takeProfit: Double?

    enum CodingKeys: String, CodingKey {
        case stopLoss   = "stop_loss"
        case takeProfit = "take_profit"
    }
}

struct CloseTradeRequest: Codable {
    let ticket:  Int
    let percent: Double   // 1.0 = full, 0.5 = half

    enum CodingKeys: String, CodingKey {
        case ticket
        case percent
    }
}

// MARK: - Device Registration

struct RegisterDeviceRequest: Codable {
    let deviceToken: String
    let deviceName:  String
    let osVersion:   String
    let appVersion:  String

    enum CodingKeys: String, CodingKey {
        case deviceToken = "device_token"
        case deviceName  = "device_name"
        case osVersion   = "os_version"
        case appVersion  = "app_version"
    }
}

// MARK: - WebSocket Message

struct WebSocketMessage: Codable {
    let type:    String
    let payload: AnyCodable?

    enum MessageType: String {
        case auth           = "auth"
        case dashboard      = "dashboard"
        case trade          = "trade"
        case log            = "log"
        case botStatus      = "bot_status"
        case error          = "error"
        case ping           = "ping"
        case pong           = "pong"
    }
}
