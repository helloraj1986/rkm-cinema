import SwiftUI
import RKMServerKit

/// `@main` — and the only place the process is set up before a view exists.
///
/// ⚠ **No `AppDelegate`, unlike the iOS target.** iOS needed one so the WebView's cookie store and the
/// background download `URLSession` could be reached before the UI existed (background-session events
/// can arrive before any view). A native client with no WebView has no such requirement, so this stays a
/// plain SwiftUI `App` — one less file that only exists on the Mac.
@main
struct RKMCinemaTVApp: App {

    @StateObject private var app = AppModel()
    @Environment(\.scenePhase) private var scenePhase

    init() {
        // ⚠ Before any view: the launch banner is the first thing in the log, and it is what makes a
        // round diagnosable — build, OS, whether the ATS declaration landed, and where the file is.
        AppLog.bootstrap()
    }

    var body: some Scene {
        WindowGroup {
            AppRootView()
                .environmentObject(app)
                .onAppear {
                    // A stored address is checked after the first frame, so screen #0 is never blank
                    // while the network is asked. A no-op unless there IS a stored address.
                    // ⚠ `.onAppear` rather than `.task`: both are correct, but `onAppear` is the older and
                    // therefore safer availability claim, and this app has one launch action, not a
                    // lifecycle-scoped async context to cancel.
                    Task { await app.startFromStoredAddress() }
                }
        }
        .onChange(of: scenePhase) { phase in
            // ⚠ The one lifecycle hook that matters: `os_log` `.debug` is never persisted and `.info`
            // only flushes when something collects it, so the FILE is the durable record — and leaving
            // the foreground is the last moment the app is known to be alive.
            switch phase {
            case .background: AppLog.wentToBackground()
            case .active: AppLog.cameToForeground()
            default: break
            }
        }
    }
}
