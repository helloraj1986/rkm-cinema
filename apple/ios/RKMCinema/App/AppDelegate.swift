import UIKit
import RKMServerKit

/// ⚠⚠ **A SwiftUI `@main` app has no application delegate unless one is adapted in — and iOS delivers
/// background-`URLSession` events to the APPLICATION DELEGATE only.**
///
/// This type exists for exactly one reason, and its absence is the failure mode the whole of Workstream B
/// is built to avoid: without it a download would keep running while the app was suspended (the system
/// does that part on its own) but the app would **never be told** it finished — no delegate callback, no
/// manifest update, no completion handler released. It presents as "the download only completes when I
/// open the app", which looks like a networking problem and is in fact a missing delegate method.
///
/// ⚠ `@UIApplicationDelegateAdaptor(AppDelegate.self)` in `RKMCinemaApp` is what installs it, and the
/// order there is load-bearing: SwiftUI reads that property from the `App` struct, so `App.init()` — and
/// therefore `AppLog.bootstrap()` — has already run by the time these methods can log anything.
final class AppDelegate: NSObject, UIApplicationDelegate {

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // ⚠ Touch the shared downloader HERE, on purpose. Creating the background session as early as the
        // process allows is what makes a relaunch's first delegate callbacks land: the system looks up a
        // session by identifier when the app starts, and a session built later in the launch (from a view
        // model, say) is a session whose first events have already been dropped.
        _ = OfflineDownloads.shared
        RKMLog.info("app delegate ready · background session \(OfflineDownloads.sessionIdentifier)",
                    category: .offline)
        return true
    }

    /// The system relaunched the app (or woke it) because a background transfer has events for us.
    ///
    /// ⚠ The completion handler is the whole point of this method existing, and it must eventually be
    /// CALLED: while it is outstanding, iOS keeps the session's background budget reserved and treats the
    /// app as busy. `OfflineDownloads.setBackgroundCompletionHandler` stores it and
    /// `urlSessionDidFinishEvents(forBackgroundURLSession:)` releases it.
    func application(
        _ application: UIApplication,
        handleEventsForBackgroundURLSession identifier: String,
        completionHandler: @escaping () -> Void
    ) {
        guard identifier == OfflineDownloads.sessionIdentifier else {
            // ⚠ An identifier we do not own means a session was created elsewhere with a different name
            // (or a build changed the identifier). The handler is called immediately so the system is
            // never left waiting on us — and it is logged loudly, because the alternative is a silent
            // hang of some other feature's background work.
            RKMLog.error("app delegate: background events for an UNKNOWN session \"\(identifier)\" — "
                         + "expected \"\(OfflineDownloads.sessionIdentifier)\"; releasing the handler",
                         category: .offline)
            completionHandler()
            return
        }
        OfflineDownloads.shared.setBackgroundCompletionHandler(completionHandler)
    }
}
