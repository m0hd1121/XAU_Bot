// APIClient.swift
// XAUBot – Async/await REST client: auth injection, JWT refresh, retry, cert pinning
// iOS 17+  |  Swift 5.9

import Foundation
import CryptoKit
import os.log

// MARK: - API Errors

enum APIError: LocalizedError {
    case noBaseURL
    case invalidURL
    case unauthorized
    case forbidden
    case notFound
    case serverError(Int, String)
    case decodingError(Error)
    case networkError(Error)
    case tokenRefreshFailed
    case certificatePinningFailed
    case rateLimited(retryAfter: Int?)
    case requestFailed(Int)
    case unknown

    var errorDescription: String? {
        switch self {
        case .noBaseURL:                 return "Server URL not configured. Open Settings to set your server."
        case .invalidURL:                return "Invalid URL."
        case .unauthorized:              return "Session expired. Please sign in again."
        case .forbidden:                 return "You don't have permission for this action."
        case .notFound:                  return "Resource not found."
        case .serverError(let c, let m): return "Server error \(c): \(m)"
        case .decodingError(let e):      return "Data parse error: \(e.localizedDescription)"
        case .networkError(let e):       return "Network error: \(e.localizedDescription)"
        case .tokenRefreshFailed:        return "Failed to refresh session. Please sign in again."
        case .certificatePinningFailed:  return "Certificate validation failed."
        case .rateLimited(let r):        return "Too many requests. Retry after \(r.map { "\($0)s" } ?? "a moment")."
        case .requestFailed(let c):      return "Request failed (\(c))."
        case .unknown:                   return "An unknown error occurred."
        }
    }
}

// MARK: - Login Response (intermediate type for 2FA flow)

struct LoginResponse: Decodable {
    let accessToken:  String?
    let refreshToken: String?
    let tokenType:    String?
    let requires2FA:  Bool

    enum CodingKeys: String, CodingKey {
        case accessToken  = "access_token"
        case refreshToken = "refresh_token"
        case tokenType    = "token_type"
        case requires2FA  = "requires_2fa"
    }

    init(from decoder: Decoder) throws {
        let c         = try decoder.container(keyedBy: CodingKeys.self)
        accessToken  = try c.decodeIfPresent(String.self,  forKey: .accessToken)
        refreshToken = try c.decodeIfPresent(String.self,  forKey: .refreshToken)
        tokenType    = try c.decodeIfPresent(String.self,  forKey: .tokenType)
        requires2FA  = (try? c.decode(Bool.self, forKey: .requires2FA)) ?? false
    }
}

// MARK: - APIClient

@MainActor
final class APIClient: NSObject {

    static let shared = APIClient()

    private let logger = Logger(subsystem: "com.xaubot.app", category: "APIClient")

    private var baseURL: String = ""

    /// Called by AuthViewModel after user enters / saves server URL
    func updateBaseURL(_ url: String) {
        var clean = url.trimmingCharacters(in: .whitespacesAndNewlines)
        if clean.last == "/" { clean = String(clean.dropLast()) }
        baseURL = clean
        KeychainService.shared.store(clean, for: .serverURL)
    }

    private var pinnedPublicKeyHashes: Set<String> = []

    private lazy var session: URLSession = {
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest  = 30
        cfg.timeoutIntervalForResource = 60
        cfg.urlCache                   = nil
        cfg.requestCachePolicy         = .reloadIgnoringLocalCacheData
        return URLSession(configuration: cfg, delegate: self, delegateQueue: nil)
    }()

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    private let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        return e
    }()

    private var refreshTask: Task<AuthTokens, Error>?

    private override init() {
        super.init()
        baseURL = KeychainService.shared.retrieveString(for: .serverURL) ?? ""
    }

    // MARK: - Login (special-cased: no auth header needed)

    func login(username: String, password: String, totpCode: String?) async throws -> LoginResponse {
        guard !baseURL.isEmpty, let url = URL(string: "\(baseURL)/api/v1/auth/login") else {
            throw APIError.noBaseURL
        }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = LoginRequest(username: username, password: password, totpCode: totpCode)
        req.httpBody = try encoder.encode(body)

        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw APIError.unknown }

        switch http.statusCode {
        case 200...299:
            return try decoder.decode(LoginResponse.self, from: data)
        case 401:
            throw APIError.unauthorized
        case 422:
            let msg = extractMessage(from: data)
            if msg.lowercased().contains("totp") || msg.lowercased().contains("2fa") {
                // Encode as a 422 that the VM can interpret as requires2FA
                return LoginResponse.requiresTwoFA
            }
            throw APIError.serverError(http.statusCode, msg)
        case 429:
            throw APIError.rateLimited(retryAfter: nil)
        default:
            throw APIError.serverError(http.statusCode, extractMessage(from: data))
        }
    }

    // MARK: - Generic Request

    func request<T: Decodable>(_ endpoint: Endpoint) async throws -> T {
        try await perform(endpoint, retryCount: 0)
    }

    private func perform<T: Decodable>(_ endpoint: Endpoint, retryCount: Int) async throws -> T {
        var urlReq = try endpoint.urlRequest(baseURL: resolvedBaseURL())
        injectAuth(&urlReq)

        do {
            let (data, response) = try await session.data(for: urlReq)
            guard let http = response as? HTTPURLResponse else { throw APIError.unknown }

            logger.debug("[\(urlReq.httpMethod ?? "?") \(urlReq.url?.path ?? "")] \(http.statusCode)")

            switch http.statusCode {
            case 200...299:
                if T.self == EmptyResponse.self { return EmptyResponse() as! T }
                do { return try decoder.decode(T.self, from: data) }
                catch { throw APIError.decodingError(error) }

            case 401:
                if retryCount == 0 {
                    try await refreshTokens()
                    return try await perform(endpoint, retryCount: 1)
                }
                await AuthService.shared.handleSessionExpiry()
                throw APIError.unauthorized

            case 403: throw APIError.forbidden
            case 404: throw APIError.notFound
            case 429:
                let retry = (response as? HTTPURLResponse)?
                    .value(forHTTPHeaderField: "Retry-After").flatMap(Int.init)
                throw APIError.rateLimited(retryAfter: retry)
            case 500...599:
                throw APIError.serverError(http.statusCode, extractMessage(from: data))
            default:
                throw APIError.requestFailed(http.statusCode)
            }

        } catch let error as APIError { throw error }
        catch let urlError as URLError {
            if retryCount < 3, isRetryable(urlError) {
                let delay = pow(2.0, Double(retryCount)) * 0.5
                try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                return try await perform(endpoint, retryCount: retryCount + 1)
            }
            throw APIError.networkError(urlError)
        }
        catch { throw APIError.networkError(error) }
    }

    // MARK: - Helpers

    private func resolvedBaseURL() throws -> String {
        if !baseURL.isEmpty { return baseURL }
        let stored = KeychainService.shared.retrieveString(for: .serverURL) ?? ""
        if !stored.isEmpty { baseURL = stored; return stored }
        throw APIError.noBaseURL
    }

    private func injectAuth(_ req: inout URLRequest) {
        if let token = KeychainService.shared.retrieveString(for: .accessToken) {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
    }

    private func refreshTokens() async throws {
        if let existing = refreshTask { _ = try await existing.value; return }
        let task = Task<AuthTokens, Error> {
            defer { Task { @MainActor in self.refreshTask = nil } }
            guard let rt = KeychainService.shared.retrieveString(for: .refreshToken) else {
                throw APIError.tokenRefreshFailed
            }
            guard let url = URL(string: "\(baseURL)/api/v1/auth/refresh") else {
                throw APIError.noBaseURL
            }
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try encoder.encode(RefreshRequest(refreshToken: rt))
            let (data, res) = try await session.data(for: req)
            guard (res as? HTTPURLResponse)?.statusCode == 200 else { throw APIError.tokenRefreshFailed }
            let tokens = try decoder.decode(AuthTokens.self, from: data)
            KeychainService.shared.store(tokens.accessToken,  for: .accessToken)
            KeychainService.shared.store(tokens.refreshToken, for: .refreshToken)
            return tokens
        }
        refreshTask = task
        _ = try await task.value
    }

    private func extractMessage(from data: Data) -> String {
        if let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let d = j["detail"] as? String { return d }
        return String(data: data, encoding: .utf8) ?? "Unknown error"
    }

    private func isRetryable(_ error: URLError) -> Bool {
        [.timedOut, .networkConnectionLost, .notConnectedToInternet,
         .cannotConnectToHost, .cannotFindHost].contains(error.code)
    }

    // MARK: - Certificate Pinning

    func setPinnedHashes(_ hashes: Set<String>) { pinnedPublicKeyHashes = hashes }
}

// MARK: - LoginResponse static helper

private extension LoginResponse {
    static var requiresTwoFA: LoginResponse {
        // Synthesize a "requires 2FA" response when the server returns 422 with TOTP message
        struct Wrapper: Encodable { let requires2FA = true; enum CodingKeys: String, CodingKey { case requires2FA = "requires_2fa" } }
        let data = (try? JSONEncoder().encode(Wrapper())) ?? Data()
        return (try? JSONDecoder().decode(LoginResponse.self, from: data)) ?? LoginResponse._empty
    }

    static var _empty: LoginResponse {
        let data = Data(#"{"requires_2fa":true}"#.utf8)
        return (try? JSONDecoder().decode(LoginResponse.self, from: data))!
    }
}

// MARK: - URLSessionDelegate (Certificate Pinning)

extension APIClient: URLSessionDelegate {

    nonisolated func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard !pinnedPublicKeyHashes.isEmpty else {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        var cfError: CFError?
        guard SecTrustEvaluateWithError(trust, &cfError) else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        for i in 0..<SecTrustGetCertificateCount(trust) {
            if let cert = SecTrustGetCertificateAtIndex(trust, i) {
                let hash = publicKeyHash(for: cert)
                if pinnedPublicKeyHashes.contains(hash) {
                    completionHandler(.useCredential, URLCredential(trust: trust))
                    return
                }
            }
        }
        completionHandler(.cancelAuthenticationChallenge, nil)
    }

    private nonisolated func publicKeyHash(for cert: SecCertificate) -> String {
        guard let key = SecCertificateCopyKey(cert),
              let keyData = SecKeyCopyExternalRepresentation(key, nil) as Data? else { return "" }
        var header = Data([
            0x30, 0x82, 0x01, 0x22, 0x30, 0x0D, 0x06, 0x09,
            0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01,
            0x01, 0x05, 0x00, 0x03, 0x82, 0x01, 0x0F, 0x00
        ])
        header.append(keyData)
        return Data(SHA256.hash(data: header)).base64EncodedString()
    }
}

// MARK: - Endpoint URL building (extension)

extension Endpoint {
    func urlRequest(baseURL: String) throws -> URLRequest {
        guard !baseURL.isEmpty, let base = URL(string: baseURL) else { throw APIError.noBaseURL }
        let full = base.appendingPathComponent(path)
        var components = URLComponents(url: full, resolvingAgainstBaseURL: true)!
        components.queryItems = queryItems.isEmpty ? nil : queryItems
        guard let url = components.url else { throw APIError.invalidURL }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = 30
        req.setValue("application/json",  forHTTPHeaderField: "Content-Type")
        req.setValue("application/json",  forHTTPHeaderField: "Accept")
        req.setValue("XAUBot-iOS/1.0",    forHTTPHeaderField: "User-Agent")
        if let body = body { req.httpBody = try JSONEncoder().encode(body) }
        return req
    }
}
