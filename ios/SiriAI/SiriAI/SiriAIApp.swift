import SwiftUI
import UIKit

@main
struct SiriAIApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}

struct RootView: View {
    @Environment(\.colorScheme) private var colorScheme
    @StateObject private var settings = SettingsStore()

    var body: some View {
        ContentView()
            .environmentObject(settings)
            .onAppear { updateIcon() }
            .onChange(of: colorScheme) { _, _ in updateIcon() }
    }

    private func updateIcon() {
        let iconName = colorScheme == .dark ? "Siri_2026_dark" : "Siri_2026"
        UIApplication.shared.setAlternateIconName(iconName) { error in
            if let error {
                print("[SiriAI] icon switch failed: \(error.localizedDescription)")
            }
        }
    }
}