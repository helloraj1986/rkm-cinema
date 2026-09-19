import SwiftUI
import RKMServerKit

/// Routing: screen #0 → `connecting` → sign in → who's watching → **Home**.
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
///
/// ⚠ **Phase B2 replaced the placeholder with `HomeView`.** Phase A's `SessionReadyView` — the screen his
/// simulator round accepted — is GONE rather than kept beside the new one, and nothing it proved was lost:
/// the session readout it carried (`signed in as` / `watching as` / `profile selected`) is now the Home
/// header's, and the address and profile are on the debug HUD. A second screen that displays the same
/// facts is a second place for them to disagree.
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
                // ⚠ The panel is a READOUT and takes no focus (`DebugHUD`'s header explains why that is
                // load-bearing on tvOS): every focusable view in the hierarchy joins the focus engine, so a
                // control up here fights the app's own arrows. It is switched on with `-RKMDebugHUD YES`
                // and off by relaunching without it.
                VStack(alignment: .leading, spacing: 0) {
                    DebugHUD(session: app.session)
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
            // ⚠ Both must exist for the Home to be showable: the store is built when the app ENTERS the
            // library (`AppModel.enterLibrary`), and the origin the poster URLs are built against comes from
            // the session's address. Falling back to `ConnectingView` — rather than to an empty Home — is
            // what keeps this a state with a way out instead of a blank screen.
            if let home = app.home, let session = app.session {
                HomeView(store: home, base: session.address.url)
            } else {
                ConnectingView()
            }
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
