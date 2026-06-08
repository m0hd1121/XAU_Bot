// WebSocketClient.swift
// XAUBot – URLSessionWebSocketTask-based client with reconnection, auth, heartbeat
// iOS 17+  |  Swift 5.9

import Foundation
import Combine
import os.log

// MARK: - WebSocket Connection State

enum WSConnectionState: Equatable {
    case disconnected
    case connecting
    case connected
    case reconnecting(attempt: Int)

    var displayLabel: String {
        switch self {
        case .disconnected:         return "Disconnected"
        case .connecting:           return "Connecting…"
        case .connected:            return "Live"
        case .reconnecting(let n):  return "Reconnecting (\(n))…"
        }
    }

    var isConnected: Bool {
        if case .connected = self { return true }
        return false
    }
}

// MARK: - WebSocket Message Envelope

enum WSInboundMessage {
    case dashboard(DashboardSnapshot)
    case botStatus(BotStatus)
    case tradeUpdate([TradeRecord])
    case logEntry(LogEntry)
    case error(String)
    case pong
    case raw(Data)
}

// MARK: - WebSocketClient

@MainActor
final class WebSocketClient: NSObject, ObservableObject {

    static let shared = WebSocketClient()

    // MARK: Published State

    @Published private(set) var connectionState: WSConnectionState = .disconnected

    // MARK: Combine Publishers

    let messagePublisher     = PassthroughSubject<WSInboundMessage, Never>()
    let dashboardPublisher   = PassthroughSubject<DashboardSnapshot, Never>()
    let botStatusPublisher   = PassthroughSubject<BotStatus, Never>()
    let tradePublisher       = PassthroughSubject<[TradeRecord], Never>()
    let logPublisher         = PassthroughSubject<LogEntry, Never>()

    // MARK: Private

    private let logger = Logger(subsystem: "com.xaubot.app", category: "WebSocket")

    private var webSocketTask: URLSessionWebSocketTask?
    private var session: URLSession?

    private var heartbeatTask: Task<Void, Never>?
    private var receiveTask:   Task<Void, Never>?
    private var reconnectTask: Task<Void, Never>?

    private var reconnectAttempt  = 0
    private let maxReconnectDelay: Double = 30
    private var isManuallyDisconnected = false

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    private override init() {
        super.init()
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 10
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }

    // MARK: - Public Interface

    func connect() {
        guard connectionState == .disconnected else { return }
        isManuallyDisconnected = false
        reconnectAttempt = 0
        establishConnection()
    }

    func disconnect() {
        isManuallyDisconnected = true
        reconnectTask?.cancel()
        reconnectTask = nil
        closeSocket(code: .normalClosure)
        connectionState = .disconnected
    }

    // MARK: - Connection Establishment

    private func establishConnection() {
        guard let baseURLString = KeychainService.shared.retrieveString(for: .serverURL),
              let base = URL(string: baseURLString) else {
            logger.error("No server URL configured")
            connectionState = .disconnected
            return
        }

        // Build WebSocket URL  ws:// or wss://
        var wsURL = base
        if base.scheme == "https" {
            wsURL = URL(string: "wss://\(base.host!)\(base.port.map { ":\($0)" } ?? "")/api/v1/ws/dashboard")!
        } else {
            wsURL = URL(string: "ws://\(base.host!)\(base.port.map { ":\($0)" } ?? "")/api/v1/ws/dashboard")!
        }

        connectionState = reconnectAttempt > 0 ? .reconnecting(attempt: reconnectAttempt) : .connecting
        logger.info("Connecting to WebSocket: \(wsURL.absoluteString)")

        var request = URLRequest(url: wsURL)
        request.timeoutInterval = 10

        webSocketTask = session?.webSocketTask(with: request)
        webSocketTask?.resume()

        // Send auth token as first message
        Task { await sendAuthMessage() }

        // Start receive loop
        startReceiving()
        startHeartbeat()
    }

    // MARK: - Auth Handshake

    private func sendAuthMessage() async {
        guard let token = KeychainService.shared.retrieveString(for: .accessToken) else {
            logger.error("No access token for WebSocket auth")
            return
        }
        let authPayload = #"{"type":"auth","token":"\#(token)"}"#
        do {
            try await webSocketTask?.send(.string(authPayload))
            logger.debug("Auth message sent")
        } catch {
            logger.error("Failed to send auth message: \(error)")
        }
    }

    // MARK: - Receive Loop

    private func startReceiving() {
        receiveTask?.cancel()
        receiveTask = Task {
            while !Task.isCancelled {
                guard let task = webSocketTask else { break }
                do {
                    let message = try await task.receive()
                    connectionState = .connected
                    reconnectAttempt = 0
                    await handleMessage(message)
                } catch {
                    if Task.isCancelled { break }
                    logger.warning("WebSocket receive error: \(error)")
                    if !isManuallyDisconnected {
                        scheduleReconnect()
                    }
                    break
                }
            }
        }
    }

    // MARK: - Message Handling

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) async {
        let data: Data
        switch message {
        case .string(let str):
            guard let d = str.data(using: .utf8) else { return }
            data = d
        case .data(let d):
            data = d
        @unknown default:
            return
        }

        do {
            // Peek at the "type" field first
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let type = json["type"] as? String else { return }

            let payloadData: Data
            if let payload = json["payload"] {
                payloadData = try JSONSerialization.data(withJSONObject: payload)
            } else {
                payloadData = data
            }

            switch type {
            case "dashboard":
                let snapshot = try decoder.decode(DashboardSnapshot.self, from: payloadData)
                messagePublisher.send(.dashboard(snapshot))
                dashboardPublisher.send(snapshot)

            case "bot_status":
                let status = try decoder.decode(BotStatus.self, from: payloadData)
                messagePublisher.send(.botStatus(status))
                botStatusPublisher.send(status)

            case "trade":
                let trades = try decoder.decode([TradeRecord].self, from: payloadData)
                messagePublisher.send(.tradeUpdate(trades))
                tradePublisher.send(trades)

            case "log":
                let entry = try decoder.decode(LogEntry.self, from: payloadData)
                messagePublisher.send(.logEntry(entry))
                logPublisher.send(entry)

            case "pong":
                messagePublisher.send(.pong)

            case "error":
                let msg = json["message"] as? String ?? "Unknown WebSocket error"
                logger.error("Server WS error: \(msg)")
                messagePublisher.send(.error(msg))

            default:
                logger.debug("Unknown WS message type: \(type)")
                messagePublisher.send(.raw(data))
            }

        } catch {
            logger.error("WS message decode error: \(error)")
        }
    }

    // MARK: - Heartbeat

    private func startHeartbeat() {
        heartbeatTask?.cancel()
        heartbeatTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000) // 30s
                guard !Task.isCancelled else { break }
                do {
                    try await webSocketTask?.send(.string(#"{"type":"ping"}"#))
                } catch {
                    logger.warning("Heartbeat send failed: \(error)")
                }
            }
        }
    }

    // MARK: - Reconnection

    private func scheduleReconnect() {
        connectionState = .reconnecting(attempt: reconnectAttempt + 1)
        closeSocket(code: .abnormalClosure)

        reconnectTask?.cancel()
        reconnectTask = Task {
            let delay = min(maxReconnectDelay, pow(2.0, Double(reconnectAttempt)) * 1.0)
            logger.info("Reconnecting in \(delay)s (attempt \(reconnectAttempt + 1))")
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled, !isManuallyDisconnected else { return }
            reconnectAttempt += 1
            connectionState = .disconnected
            establishConnection()
        }
    }

    // MARK: - Close

    private func closeSocket(code: URLSessionWebSocketTask.CloseCode) {
        heartbeatTask?.cancel()
        receiveTask?.cancel()
        webSocketTask?.cancel(with: code, reason: nil)
        webSocketTask = nil
    }

    // MARK: - Manual Send

    func send(type: String, payload: [String: Any] = [:]) async {
        var dict: [String: Any] = ["type": type]
        dict.merge(payload) { _, new in new }
        guard let data = try? JSONSerialization.data(withJSONObject: dict),
              let str  = String(data: data, encoding: .utf8) else { return }
        do {
            try await webSocketTask?.send(.string(str))
        } catch {
            logger.error("WS send error: \(error)")
        }
    }
}

// MARK: - URLSessionWebSocketDelegate

extension WebSocketClient: URLSessionWebSocketDelegate {

    nonisolated func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didOpenWithProtocol protocol: String?
    ) {
        Task { @MainActor in
            logger.info("WebSocket connected")
            connectionState = .connected
            reconnectAttempt = 0
        }
    }

    nonisolated func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
        reason: Data?
    ) {
        let reasonStr = reason.flatMap { String(data: $0, encoding: .utf8) } ?? ""
        Task { @MainActor in
            logger.info("WebSocket closed: \(closeCode.rawValue) \(reasonStr)")
            if !isManuallyDisconnected {
                scheduleReconnect()
            } else {
                connectionState = .disconnected
            }
        }
    }

    nonisolated func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didCompleteWithError error: Error?
    ) {
        guard let error else { return }
        Task { @MainActor in
            logger.error("WebSocket task error: \(error)")
            if !isManuallyDisconnected {
                scheduleReconnect()
            }
        }
    }
}
