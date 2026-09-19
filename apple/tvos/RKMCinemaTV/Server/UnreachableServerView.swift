import SwiftUI
import RKMServerKit

/// The state that stops a wrong address bricking the app.
///
/// ⚠ On iOS this view had two ways in: a failed check on screen #0, and a **WebView navigation
/// failure**. tvOS has no WebView, so there is one way in — a failed check — and one way it must never
/// happen: a TV stuck on "Can't reach this server" with no control that has focus. **Both buttons below
/// are focusable, and `Change server` is always present**, which is the requirement.
struct UnreachableServerView: View {

    @EnvironmentObject private var app: AppModel
    let info: UnreachableInfo

    @State private var confirmForget = false

    var body: some View {
        ZStack {
            Color.black.opacity(0.94)

            VStack(spacing: 20) {
                Image(systemName: "wifi.exclamationmark")
                    .font(.system(size: 64))
                    .foregroundStyle(.orange)

                Text("Can’t reach this server")
                    .font(.system(size: 42, weight: .bold))

                Text(info.address.displayString)
                    .font(.system(size: 24, design: .monospaced))

                Text(info.detail)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 900)
                    .fixedSize(horizontal: false, vertical: true)

                hints

                HStack(spacing: 20) {
                    Button {
                        Task { await app.retry() }
                    } label: {
                        HStack(spacing: 10) {
                            if app.isConnecting { ProgressView() }
                            Text(app.isConnecting ? "Trying…" : "Try again")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(app.isConnecting)

                    // Always available — this button is the requirement.
                    Button("Change server") { app.changeServer() }
                        .buttonStyle(.bordered)
                }
                .padding(.top, 6)

                Button("Forget this address") { confirmForget = true }
                    .font(.footnote)
            }
            .padding(60)
        }
        .confirmationDialog("Forget the saved address?",
                            isPresented: $confirmForget,
                            titleVisibility: .visible) {
            Button("Forget", role: .destructive) { app.forgetSavedAddress() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("The app will open on the address screen next time.")
        }
    }

    /// ⚠ The hints name the two things the app genuinely cannot fix for itself: the network is the
    /// **client device's** problem (an Apple TV cannot route to a tailnet on its own — the Tailscale app
    /// has to be running on it, or on the router), and a LAN address only works on the home network.
    @ViewBuilder
    private var hints: some View {
        VStack(alignment: .leading, spacing: 10) {
            if info.address.isLikelyTailscale {
                Label("This is a Tailscale address — the Apple TV itself must be on the tailnet.",
                      systemImage: "shield.lefthalf.filled")
            }
            if info.address.isLikelyOnLocalNetwork {
                Label("This is a local address — the Apple TV must be on the same network as the server.",
                      systemImage: "wifi")
            }
            Label("Check the server is running on the machine at home.", systemImage: "server.rack")
        }
        .font(.callout)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: 900, alignment: .leading)
    }
}
