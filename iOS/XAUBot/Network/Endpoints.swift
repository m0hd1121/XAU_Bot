// Endpoints.swift
// XAUBot – All API endpoints as typed enum cases
// iOS 17+  |  Swift 5.9

import Foundation

// MARK: - Endpoint

enum Endpoint {

    // ── Auth ─────────────────────────────────────────────────────────────────
    case login(request: LoginRequest)
    case biometricLogin(request: BiometricLoginRequest)
    case refreshToken(request: RefreshRequest)
    case logout
    case me
    case changePassword(request: ChangePasswordRequest)

    // ── Dashboard ────────────────────────────────────────────────────────────
    case dashboardSnapshot
    case botStatus

    // ── Bot Control ──────────────────────────────────────────────────────────
    case startBot
    case stopBot
    case restartBot
    case pauseBot
    case resumeBot
    case emergencyStop
    case enableLearning
    case disableLearning
    case enableMaintenance
    case disableMaintenance
    case restartService(name: String)
    case setBotMode(mode: String)

    // ── Trades ───────────────────────────────────────────────────────────────
    case openTrades
    case tradeHistory(page: Int, pageSize: Int, filters: TradeFilters?)
    case tradeDetail(ticket: Int)
    case closeTrade(ticket: Int)
    case closeTradePartial(ticket: Int, percent: Double)
    case modifyTrade(ticket: Int, request: ModifyTradeRequest)

    // ── Analytics ────────────────────────────────────────────────────────────
    case analyticsOverview
    case analyticsEquityCurve(days: Int)
    case analyticsDailyReturns(days: Int)
    case analyticsMonthlyReturns
    case analyticsDrawdown(days: Int)
    case analyticsSessions
    case analyticsRegimes
    case fullAnalytics(days: Int)

    // ── Learning ─────────────────────────────────────────────────────────────
    case learningStats
    case learningPatterns
    case learningValidation
    case learningEvents(limit: Int)
    case learningRegimeHistory

    // ── Configuration ────────────────────────────────────────────────────────
    case getConfig
    case updateConfig(config: ConfigModel)
    case resetConfigToDefaults
    case validateConfig(config: ConfigModel)

    // ── VPS ──────────────────────────────────────────────────────────────────
    case vpsStats
    case serviceStatus
    case restartServiceById(name: String)

    // ── Logs ─────────────────────────────────────────────────────────────────
    case logs(type: String, level: String?, search: String?, page: Int, pageSize: Int)
    case exportLogs(type: String)

    // ── Backup ───────────────────────────────────────────────────────────────
    case listBackups
    case createBackup(request: CreateBackupRequest)
    case downloadBackup(filename: String)
    case restoreBackup(filename: String)
    case deleteBackup(filename: String)
    case exportTrades(format: String)
    case exportAnalytics

    // ── Notifications ────────────────────────────────────────────────────────
    case registerDevice(request: RegisterDeviceRequest)
    case unregisterDevice(token: String)
    case getNotificationPrefs
    case updateNotificationPrefs(prefs: NotificationPrefs)

    // ── Account ──────────────────────────────────────────────────────────────
    case accountInfo
    case accountList
    case addAccount(payload: [String: String])
    case deleteAccount(id: String)
    case reconnectAccount(id: String)
}

// MARK: - TradeFilters

struct TradeFilters {
    var result:     String?    // "win" | "loss" | "be"
    var session:    String?
    var minRR:      Double?
    var startDate:  String?
    var endDate:    String?
}

// MARK: - URLRequest Building

extension Endpoint {

    /// Builds a URLRequest from the endpoint, injecting the base URL from Keychain.
    func urlRequest() throws -> URLRequest {
        guard let baseURLString = KeychainService.shared.retrieveString(for: .serverURL),
              let baseURL = URL(string: baseURLString) else {
            throw APIError.noBaseURL
        }

        let fullURL = baseURL.appendingPathComponent(path)

        var components = URLComponents(url: fullURL, resolvingAgainstBaseURL: true)!
        components.queryItems = queryItems.isEmpty ? nil : queryItems

        guard let url = components.url else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30

        // Default headers
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("XAUBot-iOS/1.0", forHTTPHeaderField: "User-Agent")

        // Request body
        if let body = body {
            request.httpBody = try JSONEncoder().encode(body)
        }

        return request
    }

    // MARK: - Path

    var path: String {
        switch self {
        // Auth
        case .login:                           return "/api/v1/auth/login"
        case .biometricLogin:                  return "/api/v1/auth/biometric-login"
        case .refreshToken:                    return "/api/v1/auth/refresh"
        case .logout:                          return "/api/v1/auth/logout"
        case .me:                              return "/api/v1/auth/me"
        case .changePassword:                  return "/api/v1/auth/change-password"

        // Dashboard
        case .dashboardSnapshot:               return "/api/v1/dashboard/snapshot"
        case .botStatus:                       return "/api/v1/dashboard/bot-status"

        // Bot Control
        case .startBot:                        return "/api/v1/bot/start"
        case .stopBot:                         return "/api/v1/bot/stop"
        case .restartBot:                      return "/api/v1/bot/restart"
        case .pauseBot:                        return "/api/v1/bot/pause"
        case .resumeBot:                       return "/api/v1/bot/resume"
        case .emergencyStop:                   return "/api/v1/bot/emergency-stop"
        case .enableLearning:                  return "/api/v1/bot/learning/enable"
        case .disableLearning:                 return "/api/v1/bot/learning/disable"
        case .enableMaintenance:               return "/api/v1/bot/maintenance/enable"
        case .disableMaintenance:              return "/api/v1/bot/maintenance/disable"
        case .restartService(let name):        return "/api/v1/bot/services/\(name)/restart"
        case .setBotMode:                      return "/api/v1/bot/mode"

        // Trades
        case .openTrades:                      return "/api/v1/trades/open"
        case .tradeHistory:                    return "/api/v1/trades/history"
        case .tradeDetail(let ticket):         return "/api/v1/trades/\(ticket)"
        case .closeTrade(let ticket):          return "/api/v1/trades/\(ticket)/close"
        case .closeTradePartial(let ticket, _): return "/api/v1/trades/\(ticket)/close-partial"
        case .modifyTrade(let ticket, _):      return "/api/v1/trades/\(ticket)/modify"

        // Analytics
        case .analyticsOverview:               return "/api/v1/analytics/overview"
        case .analyticsEquityCurve:            return "/api/v1/analytics/equity-curve"
        case .analyticsDailyReturns:           return "/api/v1/analytics/daily-returns"
        case .analyticsMonthlyReturns:         return "/api/v1/analytics/monthly-returns"
        case .analyticsDrawdown:               return "/api/v1/analytics/drawdown"
        case .analyticsSessions:               return "/api/v1/analytics/sessions"
        case .analyticsRegimes:                return "/api/v1/analytics/regimes"
        case .fullAnalytics:                   return "/api/v1/analytics/full"

        // Learning
        case .learningStats:                   return "/api/v1/learning/stats"
        case .learningPatterns:                return "/api/v1/learning/patterns"
        case .learningValidation:              return "/api/v1/learning/validation"
        case .learningEvents:                  return "/api/v1/learning/events"
        case .learningRegimeHistory:           return "/api/v1/learning/regime-history"

        // Configuration
        case .getConfig:                       return "/api/v1/config"
        case .updateConfig:                    return "/api/v1/config"
        case .resetConfigToDefaults:           return "/api/v1/config/reset"
        case .validateConfig:                  return "/api/v1/config/validate"

        // VPS
        case .vpsStats:                        return "/api/v1/vps/stats"
        case .serviceStatus:                   return "/api/v1/vps/services"
        case .restartServiceById(let name):    return "/api/v1/vps/services/\(name)/restart"

        // Logs
        case .logs:                            return "/api/v1/logs"
        case .exportLogs(let type):            return "/api/v1/logs/export/\(type)"

        // Backup
        case .listBackups:                     return "/api/v1/backups"
        case .createBackup:                    return "/api/v1/backups"
        case .downloadBackup(let filename):    return "/api/v1/backups/\(filename)/download"
        case .restoreBackup(let filename):     return "/api/v1/backups/\(filename)/restore"
        case .deleteBackup(let filename):      return "/api/v1/backups/\(filename)"
        case .exportTrades(let format):        return "/api/v1/backups/export/trades/\(format)"
        case .exportAnalytics:                 return "/api/v1/backups/export/analytics"

        // Notifications
        case .registerDevice:                  return "/api/v1/notifications/register-device"
        case .unregisterDevice:                return "/api/v1/notifications/unregister-device"
        case .getNotificationPrefs:            return "/api/v1/notifications/preferences"
        case .updateNotificationPrefs:         return "/api/v1/notifications/preferences"

        // Account
        case .accountInfo:                     return "/api/v1/account/current"
        case .accountList:                     return "/api/v1/account/list"
        case .addAccount:                      return "/api/v1/account/add"
        case .deleteAccount(let id):           return "/api/v1/account/\(id)"
        case .reconnectAccount(let id):        return "/api/v1/account/\(id)/reconnect"
        }
    }

    // MARK: - HTTP Method

    var method: String {
        switch self {
        case .login, .biometricLogin, .refreshToken,
             .startBot, .stopBot, .restartBot, .pauseBot, .resumeBot,
             .emergencyStop, .enableLearning, .disableLearning,
             .enableMaintenance, .disableMaintenance,
             .restartService, .restartServiceById, .setBotMode,
             .createBackup, .restoreBackup, .registerDevice,
             .addAccount, .reconnectAccount, .validateConfig,
             .closeTradePartial, .closeTrade:
            return "POST"

        case .logout, .deleteBackup, .deleteAccount, .unregisterDevice:
            return "DELETE"

        case .updateConfig, .updateNotificationPrefs:
            return "PUT"

        case .modifyTrade:
            return "PATCH"

        default:
            return "GET"
        }
    }

    // MARK: - Query Items

    var queryItems: [URLQueryItem] {
        switch self {
        case .tradeHistory(let page, let pageSize, let filters):
            var items: [URLQueryItem] = [
                .init(name: "page",      value: "\(page)"),
                .init(name: "page_size", value: "\(pageSize)")
            ]
            if let f = filters {
                if let result    = f.result    { items.append(.init(name: "result",     value: result)) }
                if let session   = f.session   { items.append(.init(name: "session",    value: session)) }
                if let minRR     = f.minRR     { items.append(.init(name: "min_rr",     value: "\(minRR)")) }
                if let startDate = f.startDate { items.append(.init(name: "start_date", value: startDate)) }
                if let endDate   = f.endDate   { items.append(.init(name: "end_date",   value: endDate)) }
            }
            return items

        case .logs(let type, let level, let search, let page, let pageSize):
            var items: [URLQueryItem] = [
                .init(name: "type",      value: type),
                .init(name: "page",      value: "\(page)"),
                .init(name: "page_size", value: "\(pageSize)")
            ]
            if let level  = level  { items.append(.init(name: "level",  value: level)) }
            if let search = search { items.append(.init(name: "search", value: search)) }
            return items

        case .analyticsEquityCurve(let days):
            return [.init(name: "days", value: "\(days)")]
        case .analyticsDailyReturns(let days):
            return [.init(name: "days", value: "\(days)")]
        case .analyticsDrawdown(let days):
            return [.init(name: "days", value: "\(days)")]
        case .fullAnalytics(let days):
            return [.init(name: "days", value: "\(days)")]
        case .learningEvents(let limit):
            return [.init(name: "limit", value: "\(limit)")]
        case .closeTradePartial(_, let percent):
            return [.init(name: "percent", value: "\(percent)")]
        case .unregisterDevice(let token):
            return [.init(name: "token", value: token)]

        default:
            return []
        }
    }

    // MARK: - Body (returns AnyEncodable)

    var body: (any Encodable)? {
        switch self {
        case .login(let request):             return request
        case .biometricLogin(let request):    return request
        case .refreshToken(let request):      return request
        case .changePassword(let request):    return request
        case .updateConfig(let config):       return config
        case .validateConfig(let config):     return config
        case .createBackup(let request):      return request
        case .registerDevice(let request):    return request
        case .updateNotificationPrefs(let p): return p
        case .modifyTrade(_, let request):    return request
        case .addAccount(let payload):        return payload
        case .setBotMode(let mode):           return SetModePayload(mode: mode)
        default:                              return nil
        }
    }
}

// MARK: - SetModePayload

private struct SetModePayload: Encodable {
    let mode: String
}
