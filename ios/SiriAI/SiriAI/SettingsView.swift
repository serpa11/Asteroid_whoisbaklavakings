import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var settings: SettingsStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("API") {
                    SecureField("API Key", text: $settings.apiKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Text("Your key is stored on this device.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Model") {
                    Picker("Model", selection: $settings.model) {
                        Text("gpt-4o").tag("gpt-4o")
                        Text("gpt-4o-mini").tag("gpt-4o-mini")
                    }
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(SettingsStore())
}