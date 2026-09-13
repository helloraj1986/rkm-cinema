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
            // ⚠⚠ The frame and the offset below place the visible **mark** only. It is shifted up
            // because the overlay's top-leading corner is the *safe area's* — ~59pt below the top of
            // the display — which is the measurement that explains the original bug.
            //
            // ⚠ The **touch target** is not here at all: `HUDCornerToggleView` installs its gesture
            // recognisers on the window, limited to a 110pt corner. That separation is the fix for
            // the second failure — an offset moves what is *drawn* without promising to move where
            // the app *listens*, so the mark sat in the corner while the tap target stayed 59pt
            // lower, and a click on the glyph itself did nothing.
            HUDCornerToggle { app.toggleHUD() }
                .frame(width: HUDCornerToggle.size.width, height: HUDCornerToggle.size.height)
                .offset(y: HUDCornerToggle.upwardShift)
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
