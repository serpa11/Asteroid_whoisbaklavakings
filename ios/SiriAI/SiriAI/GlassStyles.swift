import SwiftUI

struct GlassCircleButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.title2)
            .foregroundStyle(Color.primary)
            .frame(width: 44, height: 44)
            .background(Color(.secondarySystemBackground))
            .clipShape(Circle())
            .scaleEffect(configuration.isPressed ? 0.94 : 1)
            .animation(.spring(response: 0.25), value: configuration.isPressed)
            .modifier(GlassSurfaceModifier(shape: Circle()))
    }
}

struct GlassMessageModifier: ViewModifier {
    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        content
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .modifier(GlassSurfaceModifier(shape: RoundedRectangle(cornerRadius: cornerRadius)))
    }
}

struct GlassSurfaceModifier: ViewModifier {
    let shape: AnyShape

    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.glassEffect(.regular, in: shape)
        } else {
            content
        }
    }
}

extension View {
    func glassSurface(_ shape: AnyShape) -> some View {
        modifier(GlassSurfaceModifier(shape: shape))
    }
}