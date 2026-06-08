// XAUBotApp.swift
// XAUBot – SwiftUI app entry point
// iOS 17+  |  Swift 5.9

import SwiftUI
import UserNotifications

@main
struct XAUBotApp: App {

    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    // Persisted across launches – set to true after the user completes onboarding
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

    @StateObject private var authService   = AuthService.shared
    @StateObject private var wsClient      = WebSocketClient.shared
    @StateObject private var toastManager  = ToastManager.shared

    // MARK: - Scene

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authService)
                .environmentObject(wsClient)
                .environmentObject(toastManager)
                .onReceive(authService.$isAuthenticated) { authenticated in
                    if authenticated {
                        wsClient.connect()
                    } else {
                        wsClient.disconnect()
                    }
                }
                .overlay(alignment: .top) {
                    ToastView()
                        .environmentObject(toastManager)
                        .ignoresSafeArea(edges: .top)
                }
        }
        .backgroundTask(.appRefresh("com.xaubot.dashboard-refresh")) {
            await handleBackgroundRefresh()
        }
    }

    // MARK: - Background Refresh

    private func handleBackgroundRefresh() async {
        guard authService.isAuthenticated else { return }
        do {
            let snapshot: DashboardSnapshot = try await APIClient.shared.request(Endpoint.dashboardSnapshot)
            if snapshot.botStatus.emergencyStopped {
                await NotificationService.shared.scheduleLocalNotification(
                    title: "Emergency Stop Active",
                    body: "The trading bot has been emergency stopped.",
                    category: "bot_stopped"
                )
            }
        } catch {
            // Silent failure – background refresh is best-effort
        }
    }
}
