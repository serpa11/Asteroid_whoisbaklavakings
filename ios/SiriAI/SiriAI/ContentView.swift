import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var settings: SettingsStore
    @State private var showChat = false
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color(.systemBackground).ignoresSafeArea()

                VStack(spacing: 24) {
                    Spacer()
                    Image(systemName: "infinity")
                        .font(.system(size: 64, weight: .light))
                        .foregroundStyle(.secondary)
                    Text("No Conversations")
                        .font(.title2.weight(.semibold))
                    Spacer()
                }

                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        Button {
                            showSettings = true
                        } label: {
                            Image(systemName: "gearshape")
                        }
                        .buttonStyle(GlassCircleButtonStyle())
                        .padding(.trailing, 24)
                        .padding(.top, 24)
                    }
                }

                VStack {
                    Spacer()
                    HStack {
                        Button {
                            // Search is a placeholder in the reference UI.
                        } label: {
                            Image(systemName: "magnifyingglass")
                        }
                        .buttonStyle(GlassCircleButtonStyle())

                        Spacer()

                        Button {
                            showChat = true
                        } label: {
                            Image(systemName: "square.and.pencil")
                        }
                        .buttonStyle(GlassCircleButtonStyle())
                    }
                    .padding(.horizontal, 24)
                    .padding(.bottom, 24)
                }
            }
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(isPresented: $showChat) {
                ChatView()
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(SettingsStore())
}