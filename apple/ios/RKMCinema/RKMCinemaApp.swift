import SwiftUI
import UIKit
import Combine
import RKMServerKit

/// ⚠ **The order inside `init` is load-bearing.** A `@StateObject` default value is evaluated
/// *before* this initialiser's body runs, so with `@StateObject private var app = AppModel()`
/// the model's first lines ("stored address loaded" / "no stored address") would be written
/// before a file sink existed — and the file log is meant to hold the whole run
/// (`apple/LOGGING.md` §9). Bootstrapping first and building the model second removes the race.
@main
struct RKMCinemaApp: App {

    @StateObject private var app: AppModel

    /// ⚠⚠ Phase B2 needs a real application delegate: iOS delivers background-`URLSession` events to the
    /// application delegate and nowhere else, and this SwiftUI `@main` app had none. See
    /// `App/AppDelegate.swift` for why that would have read as "downloads only finish when the app is
    /// open". ⚠ It is created by SwiftUI AFTER `init()` below has run, which is what keeps the log
    /// bootstrap ahead of the delegate's own lines.
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    init() {
        AppLog.bootstrap()
        _app = StateObject(wrappedValue: AppModel())
    }

    var body: some Scene {
        WindowGroup {
            AppRootView()
                .environmentObject(app)
                // ⚠ Not `@Environment(\.scenePhase)` + `onChange`: that modifier's one-argument
                // form is deprecated from iOS 17, and a deprecation warning in his build log is
                // noise he has to read past. Notifications are unambiguous at every version.
                .onReceive(NotificationCenter.default.publisher(for: UIApplication.didEnterBackgroundNotification)) { _ in
                    AppLog.wentToBackground()
                }
                .onReceive(NotificationCenter.default.publisher(for: UIApplication.willEnterForegroundNotification)) { _ in
                    AppLog.cameToForeground()
                }
        }
    }
}
