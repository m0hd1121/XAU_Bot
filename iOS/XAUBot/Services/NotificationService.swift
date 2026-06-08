// NotificationService.swift
// XAUBot – Push notification manager: permission, token, local notifications
// iOS 17+  |  Swift 5.9

import Combine
import Foundation
import UserNotifications
import UIKit
import os.log

// MARK: - NotificationService

@MainActor
final class NotificationService: ObservableObject {

    static let shared = NotificationService()

    @Published private(set) var permissionGranted = false
    @Published private(set) var deviceToken: String?

    private let logger = Logger(subsystem: "com.xaubot.app", category: "Notifications")
    private let keychain = KeychainService.shared

    private init() {
        Task { await checkCurrentPermission() }
    }

    // MARK: - Permission

    func requestPermission() async {
        do {
            let granted = try await UNUserNotificationCenter.current().requestAuthorization(
                options: [.alert, .badge, .sound, .criticalAlert]
            )
            permissionGranted = granted
            if granted {
                await registerForRemoteNotifications()
            }
            logger.info("Notification permission: \(granted)")
        } catch {
            logger.error("Permission request error: \(error)")
        }
    }

    func checkCurrentPermission() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        permissionGranted = settings.authorizationStatus == .authorized ||
                            settings.authorizationStatus == .provisional
    }

    // MARK: - Remote Notification Registration

    func registerForRemoteNotifications() async {
        await UIApplication.shared.registerForRemoteNotifications()
    }

    /// Called by AppDelegate when APNs token is received
    func registerDeviceToken(_ token: String) async {
        deviceToken = token
        guard AuthService.shared.isAuthenticated else { return }

        let request = RegisterDeviceRequest(
            deviceToken: token,
            deviceName:  UIDevice.current.name,
            osVersion:   UIDevice.current.systemVersion,
            appVersion:  Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        )

        do {
            let _: MessageResponse = try await APIClient.shared.request(
                Endpoint.registerDevice(request: request)
            )
            logger.info("Device token registered with backend")
        } catch {
            logger.error("Failed to register device token: \(error)")
        }
    }

    // MARK: - Notification Preferences

    func getPreferences() async throws -> NotificationPrefs {
        try await APIClient.shared.request(Endpoint.getNotificationPrefs)
    }

    func updatePreferences(_ prefs: NotificationPrefs) async throws {
        let _: MessageResponse = try await APIClient.shared.request(
            Endpoint.updateNotificationPrefs(prefs: prefs)
        )
    }

    // MARK: - Local Notifications (offline alerts)

    func scheduleLocalNotification(title: String, body: String, category: String, delay: TimeInterval = 0) async {
        let content          = UNMutableNotificationContent()
        content.title        = title
        content.body         = body
        content.categoryIdentifier = category
        content.sound        = .default

        let trigger = delay > 0
            ? UNTimeIntervalNotificationTrigger(timeInterval: delay, repeats: false)
            : nil

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: trigger
        )

        do {
            try await UNUserNotificationCenter.current().add(request)
        } catch {
            logger.error("Failed to schedule local notification: \(error)")
        }
    }

    func scheduleDailySummaryNotification(pnl: Double, trades: Int) async {
        let sign      = pnl >= 0 ? "+" : ""
        let body      = "Daily P&L: \(sign)$\(String(format: "%.2f", pnl)) | Trades: \(trades)"
        await scheduleLocalNotification(title: "XAUBot Daily Summary", body: body, category: "ALERT")
    }

    // MARK: - Badge

    func clearBadge() async {
        await UIApplication.shared.setBadgeCount(0)
    }
}
