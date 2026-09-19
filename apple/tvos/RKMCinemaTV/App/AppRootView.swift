import SwiftUI
import RKMServerKit

/// Routing: screen #0 → `connecting` → sign in → who's watching → (Phase B: the library).
///
/// ⚠ **FOCUS IS THE DESIGN, not a polish pass.** tvOS has no pointer and no hover: everything reachable
/// must be reachable with four directions and Select. That is why there is no `NavigationStack` and no
/// back stack in this phase — each screen owns its own way forward and its own way out, and every one of
/// them has a visible exit (`Change server`), because a dead end on a TV is a phone call.
///
/// ⚠ The overlay states (unreachable, debug HUD) sit **above** whichever screen is showing, so a failure
/// is never a dead end and the HUD can be photographed over the real thing. On tvOS the HUD is not a
/// convenience — it is **the only diagnostic surface that exists** (no Safari Web Inspector, no console,
/// and no easy way to get a file off a TV).
struct AppRootView: View {

    @EnvironmentObject private var app: AppModel

    var body: some View {
        ZStack {
            content

            if let info = app.unreachable {
                UnreachableServerView(info: info)
                    .transition(.opacity)
            }

            if app.hudVisible {
                VStack(alignment: .leading, spacing: 0) {
                    DebugHUD(session: app.session, onHide: { app.setHUD(false) })
                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(28)
                .transition(.opacity)
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch app.phase {
        case .setup:
            ServerSetupView()

        case .connecting:
            ConnectingView()

        case .signIn:
            if let session = app.session {
                LoginView(session: session)
            } else {
                ConnectingView()
            }

        case .profiles:
            if let session = app.session {
                ProfilesView(session: session)
            } else {
                ConnectingView()
            }

        case .library:
            SessionReadyView()
        }
    }
}

/// The launch state. ⚠ It exists so a TV is never a black rectangle while the network is asked — and so
/// `Change server` is reachable from it. A screen with no focusable control cannot be escaped with a
/// remote, which is the failure this avoids.
struct ConnectingView: View {

    @EnvironmentObject private var app: AppModel

    var body: some View {
        VStack(spacing: 24) {
            ProgressView()
                .controlSize(.large)
            Text("Checking the server…")
                .font(.title3)
            Text(app.typedAddress)
                .font(.system(size: 24, design: .monospaced))
                .foregroundStyle(.secondary)
            if let session = app.session, session.busy {
                Text("Reading your session…")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            Button("Change server") { app.changeServer() }
                .buttonStyle(.bordered)
                .padding(.top, 8)
        }
        .padding(60)
    }
}

/// ⚠ **Phase A's acceptance screen, and it is deliberately honest about being a placeholder.** It proves
/// the three things this round is for — the address was reached, the session cookie was accepted, and a
/// profile was selected — and it carries the ways out that make the app navigable without a library.
/// Phase B replaces the middle of it; the header and the out-buttons stay.
struct SessionReadyView: View {

    @EnvironmentObject private var app: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text("RKMCinemaTV")
                .font(.system(size: 54, weight: .bold))
            Text("Phase A — the session works. The library arrives in the next round.")
                .font(.title3)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 8) {
                row("Server", app.session?.address.displayString ?? "—")
                row("Signed in as", app.session?.signedInUser?.name ?? "—")
                row("Watching as", app.session?.currentProfile?.name ?? "—")
                row("Profile selected", (app.session?.profileSelected ?? false) ? "yes" : "no")
            }
            .padding(.top, 4)

            if let warning = app.session?.warning, !warning.isEmpty {
                Text(warning)
                    .font(.callout)
                    .foregroundStyle(.orange)
            }

            HStack(spacing: 20) {
                Button("Change profile") { Task { await app.changeProfile() } }
                    .buttonStyle(.borderedProminent)
                Button("Sign out") { Task { await app.signOut() } }
                    .buttonStyle(.bordered)
                Button("Change server") { app.changeServer() }
                    .buttonStyle(.bordered)
            }
            .padding(.top, 10)
        }
        .padding(60)
        .frame(maxWidth: 1400, alignment: .leading)
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            Text(label)
                .font(.headline)
                .foregroundStyle(.secondary)
                .frame(width: 220, alignment: .leading)
            Text(value)
                .font(.system(size: 24, design: .monospaced))
        }
    }
}
