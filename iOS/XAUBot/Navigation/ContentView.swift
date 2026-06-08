// ContentView.swift
// XAUBot – Root view: routes between LoginView and MainTabView based on auth state
// iOS 17+  |  Swift 5.9

import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var authService: AuthService
    @EnvironmentObject private var wsClient:    WebSocketClient

    var body: some View {
        Group {
            if authService.isAuthenticated {
                MainTabView()
                    .transition(.opacity)
            } else {
                LoginView()
                    .transition(.opacity)
            }
        }
        .animation(AppAnimation.easeInOut, value: authService.isAuthenticated)
        .preferredColorScheme(.dark)
        .onChange(of: authService.isAuthenticated) { _, authenticated in
            if authenticated {
                wsClient.connect()
                Task { await NotificationService.shared.checkCurrentPermission() }
            } else {
                wsClient.disconnect()
            }
        }
    }
}
