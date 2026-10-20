import Foundation

struct ChatMessage: Identifiable {
    let id = UUID()
    let role: Role
    let text: String
    let card: MessageCard?

    enum Role {
        case user
        case assistant
    }
}

struct MessageCard: Identifiable {
    let id = UUID()
    let title: String
    let lines: [String]
    let imageSystemName: String
}