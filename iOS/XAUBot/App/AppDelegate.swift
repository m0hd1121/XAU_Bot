// AppDelegate.swift
// XAUBot – UIApplicationDelegate for push notifications & APNs
// iOS 17+  |  Swift 5.9

import UIKit
import UserNotifications
import os.log

final class AppDelegate: NSObject, UIApplicationDelegate {

    private let logger = Logger(subsystem: "com.xaubot.app", category: "AppDelegate")

    // MARK: - Application Lifecycle

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        configureNotifications(application)
        configureAppearance()
        return true
    }

    // MARK: - Push Notification Registration

    private func configureNotifications(_ application: UIApplication) {
        UNUserNotificationCenter.current().delegate = self

        // Define notification categories & actions
        let closeAction = UNNotificationAction(
            identifier: "CLOSE_TRADE",
            title: "Close Trade",
            options: [.authenticationRequired, .destructive]
        )
        let viewAction = UNNotificationAction(
            identifier: "VIEW_DETAIL",
            title: "View Detail",
            options: .foreground
        )
        let dismissAction = UNNotificationAction(
            identifier: "DISMISS",
            title: "Dismiss",
            options: .destructive
        )

        let tradeCategory = UNNotificationCategory(
            identifier: "TRADE",
            actions: [viewAction, closeAction],
            intentIdentifiers: [],
            options: .customDismissAction
        )
        let alertCategory = UNNotificationCategory(
            identifier: "ALERT",
            actions: [viewAction, dismissAction],
            intentIdentifiers: [],
            options: .customDismissAction
        )
        let botCategory = UNNotificationCategory(
            identifier: "BOT",
            actions: [viewAction],
            intentIdentifiers: [],
            options: []
        )

        UNUserNotificationCenter.current().setNotificationCategories(
            [tradeCategory, alertCategory, botCategory]
        )
    }

    // MARK: - APNs Token Registration

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        let tokenString = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        logger.info("APNs device token registered: \(tokenString)")
        Task {
            await NotificationService.shared.registerDeviceToken(tokenString)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        logger.error("Failed to register for remote notifications: \(error.localizedDescription)")
    }

    // MARK: - Background Fetch

    func application(
        _ application: UIApplication,
        performFetchWithCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void
    ) {
        Task {
            do {
                let _: DashboardSnapshot = try await APIClient.shared.request(Endpoint.dashboardSnapshot)
                completionHandler(.newData)
            } catch {
                completionHandler(.failed)
            }
        }
    }

    // MARK: - Scene Configuration

    func application(
        _ application: UIApplication,
        configurationForConnecting connectingSceneSession: UISceneSession,
        options: UIScene.ConnectionOptions
    ) -> UISceneConfiguration {
        UISceneConfiguration(name: "Default Configuration", sessionRole: connectingSceneSession.role)
    }

    // MARK: - Appearance

    private func configureAppearance() {
        // Navigation bar
        let navBarAppearance = UINavigationBarAppearance()
        navBarAppearance.configureWithOpaqueBackground()
        navBarAppearance.backgroundColor = UIColor(red: 0.04, green: 0.055, blue: 0.102, alpha: 1)
        navBarAppearance.titleTextAttributes = [
            .foregroundColor: UIColor.white,
            .font: UIFont.systemFont(ofSize: 17, weight: .semibold)
        ]
        navBarAppearance.largeTitleTextAttributes = [
            .foregroundColor: UIColor.white,
            .font: UIFont.systemFont(ofSize: 34, weight: .bold)
        ]
        UINavigationBar.appearance().standardAppearance   = navBarAppearance
        UINavigationBar.appearance().scrollEdgeAppearance = navBarAppearance
        UINavigationBar.appearance().compactAppearance    = navBarAppearance
        UINavigationBar.appearance().tintColor = UIColor(red: 0.831, green: 0.686, blue: 0.216, alpha: 1)

        // Tab bar
        let tabBarAppearance = UITabBarAppearance()
        tabBarAppearance.configureWithOpaqueBackground()
        tabBarAppearance.backgroundColor = UIColor(red: 0.04, green: 0.055, blue: 0.102, alpha: 1)
        UITabBar.appearance().standardAppearance   = tabBarAppearance
        UITabBar.appearance().scrollEdgeAppearance = tabBarAppearance
        UITabBar.appearance().tintColor = UIColor(red: 0.831, green: 0.686, blue: 0.216, alpha: 1)
    }
}

// MARK: - UNUserNotificationCenterDelegate

extension AppDelegate: UNUserNotificationCenterDelegate {

    // Called when notification arrives while app is in foreground
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        let userInfo = notification.request.content.userInfo
        logger.debug("Foreground notification received: \(userInfo)")

        // Show as banner + play sound in foreground
        completionHandler([.banner, .sound, .badge])

        // Also show in-app toast
        let content = notification.request.content
        Task { @MainActor in
            ToastManager.shared.show(content.body, type: .info)
        }
    }

    // Called when user taps on a notification
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        logger.info("Notification action: \(response.actionIdentifier)")

        switch response.actionIdentifier {
        case "CLOSE_TRADE":
            if let ticketStr = userInfo["ticket"] as? String, let ticket = Int(ticketStr) {
                Task {
                    do {
                        let _: EmptyResponse = try await APIClient.shared.request(
                            Endpoint.closeTrade(ticket: ticket)
                        )
                    } catch {
                        logger.error("Failed to close trade from notification: \(error)")
                    }
                }
            }
        case "VIEW_DETAIL":
            // Deep link handling – post notification for the UI layer
            NotificationCenter.default.post(
                name: .openTradeDetail,
                object: nil,
                userInfo: userInfo
            )
        default:
            break
        }

        completionHandler()
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let openTradeDetail = Notification.Name("openTradeDetail")
    static let openDashboard   = Notification.Name("openDashboard")
}
