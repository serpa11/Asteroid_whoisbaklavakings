import Foundation

final class SettingsStore: ObservableObject {
    @Published var apiKey: String {
        didSet { UserDefaults.standard.set(apiKey, forKey: "siri_api_key") }
    }
    @Published var model: String {
        didSet { UserDefaults.standard.set(model, forKey: "siri_model") }
    }

    init() {
        apiKey = UserDefaults.standard.string(forKey: "siri_api_key") ?? ""
        model = UserDefaults.standard.string(forKey: "siri_model") ?? "gpt-4o"
    }
}