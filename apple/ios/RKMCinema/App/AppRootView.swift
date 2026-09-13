import SwiftUI
import RKMServerKit

/// Routing: no usable address → the setup screen; an address → the web shell.
///
/// ⚠ The overlay states (unreachable, debug HUD) sit **above** whichever screen is showing, so a
/// failure is never a dead end and the HUD can be photographed over the real thing.
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
                    DebugHUD(shell: app.shell)
                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
                .transition(.opacity)
            }
        }
        .overlay(alignment: .topLeading) {
            // Drawn last so it is above the overlay's own corner. When the HUD is visible its ⚙
            // (top-right of the panel) is clear of this square, and when it is hidden this is the
            // only way back in.
            HUDToggleHotspot { app.toggleHUD() }
        }
        .background(ShakeToToggle { app.toggleHUD() })
    }

    @ViewBuilder
    private var content: some View {
        switch app.phase {
        case .setup:
            ServerSetupView()

        case .shell:
            if let shell = app.shell {
                WebShellView(model: shell)
                    // ⚠ A different address must produce a different web view. Without an explicit
                    // identity SwiftUI would reuse the existing one — still pointed at the old
                    // server — and changing servers would appear to do nothing.
                    .id(shell.address.displayString)
                    // The keyboard must not resize a page that is meant to be a full-screen shell.
                    .ignoresSafeArea(.keyboard)
            } else {
                ProgressView()
            }
        }
    }
}
