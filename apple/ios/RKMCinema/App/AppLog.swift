import Foundation
import SwiftUI
import UIKit
import RKMServerKit

/// Wiring the log up at launch, and the banner that makes a log self-describing.
///
/// ⚠ The banner is not vanity. With development on Windows and testing on the Mac, the log file
/// is the only account of what the app thought it was doing — so it opens by recording every
/// fact whose absence would otherwise be guessed at: build, device, level, where the file is,
/// **whether the ATS declaration actually landed**, and which address is in use.
enum AppLog {

    /// The debug overlay's remembered state.
    ///
    /// ⚠⚠ **A Debug build opens with the overlay already ON, and that is now the primary route to
    /// it.** `LOGGING.md` §4 asked for "a build flag / triple-tap"; the triple-tap is gone (see
    /// `HUDCornerToggle` — it sat 59pt below the corner it was supposed to occupy, so it never fired
    /// once), and the build flag is what replaces it. The reason is the whole point of this
    /// document: dev happens on Windows, testing happens on the Mac, so **the overlay is the only
    /// way a screenshot and the file log can be joined** — and a diagnostic that depends on
    /// remembering a gesture is missing exactly when it is needed most, which is what happened.
    ///
    /// ⚠ It is still hideable for the session (the overlay's ⚙, or the corner chip), which is what
    /// keeps it possible to photograph the UI without it. What a Debug build does *not* do is start
    /// hidden because of a stale stored value — that stale value is what made "nothing comes up"
    /// look like a broken app. Release builds read the stored value, which defaults to off.
    ///
    /// ⚠ Also settable from a scheme launch argument — `-RKMDebugHUD YES` — because `UserDefaults`
    /// reads `-Key Value` arguments automatically. In a Release-style build that is the switch that
    /// needs no code change and no rebuild.
    static let hudDefaultsKey = "RKMDebugHUD"

    static var hudStartsVisible: Bool {
        #if DEBUG
        return true
        #else
        return UserDefaults.standard.bool(forKey: hudDefaultsKey)
        #endif
    }

    /// The same fact as a value, so the launch banner can say *why* it starts visible rather than
    /// leaving it to be inferred from the build.
    static var debugBuild: Bool {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }

    static func bootstrap() {
        let level = RKMLog.storedLevel(default: .verbose)

        var fileLog: RollingFileLog?
        var fileProblem: String?
        do {
            let directory = try RollingFileLog.defaultDirectory(appFolder: "RKMCinema")
            fileLog = try RollingFileLog(directory: directory, policy: .init(baseName: "rkm-ios.log"))
        } catch {
            // Not fatal: the ring buffer (and so the HUD) and os_log still get every line.
            fileProblem = String(describing: error)
        }

        RKMLog.shared.configure(level: level, fileLog: fileLog)
        logLaunchBanner(level: level, fileProblem: fileProblem)
    }

    private static func logLaunchBanner(level: LogLevel, fileProblem: String?) {
        let info = Bundle.main.infoDictionary ?? [:]
        let version = info["CFBundleShortVersionString"] as? String ?? "?"
        let build = info["CFBundleVersion"] as? String ?? "?"

        RKMLog.info("RKMCinema \(version) (\(build)) · \(Bundle.main.bundleIdentifier ?? "?")", category: .app)
        RKMLog.info(
            "device \(UIDevice.current.model) · iOS \(UIDevice.current.systemVersion)"
                + " · locale \(Locale.current.identifier) · tz \(TimeZone.current.identifier)",
            category: .app
        )
        RKMLog.info("log level \(level.name) · subsystem \(RKMLog.subsystem)", category: .app)

        // ⚠ The overlay's route is logged at launch, because on the first real run the only report
        // available was "nothing comes up" — and that was three different facts at once: where the
        // toggle is, whether it starts on, and whether the touch ever arrived. Two of the three are
        // settled by this line and the chip's own log lines; the third by tapping it.
        RKMLog.info(
            "debug overlay: starts \(hudStartsVisible ? "VISIBLE" : "hidden")"
                + " (\(debugBuild ? "Debug build — always visible at launch" : "Release build — stored setting"));"
                + " stored value \(UserDefaults.standard.bool(forKey: hudDefaultsKey));"
                + " toggle: the chip in the top-left corner (one tap, or press and hold)",
            category: .app
        )

        if let url = RKMLog.shared.fileURL {
            RKMLog.info("file log: \(url.path)", category: .app)
        } else {
            RKMLog.error("no file log — \(fileProblem ?? "unknown reason")", category: .app)
        }

        // ⚠ This line earns its place: it is the proof that `INFOPLIST_FILE` is pointed at our
        // Info.plist. If it, these read false/false and a plain-`http://` LAN address is blocked —
        // a failure that otherwise presents as "the app is broken" (plan §2.2).
        let ats = info["NSAppTransportSecurity"] as? [String: Any]
        let arbitraryLoads = ats?["NSAllowsArbitraryLoads"] as? Bool ?? false
        let localNetworking = ats?["NSAllowsLocalNetworking"] as? Bool ?? false
        RKMLog.info("ATS declared: arbitraryLoads=\(arbitraryLoads) localNetworking=\(localNetworking)", category: .app)

        let store = ServerStore()
        if let address = store.address {
            RKMLog.info(
                "stored address: \(address.displayString)"
                    + " (scheme \(address.hadExplicitScheme ? "typed by hand" : "assumed by the app"))",
                category: .app
            )
        } else if store.hasInvalidStoredValue {
            RKMLog.error("stored address will not parse: \"\(store.rawValue ?? "")\" — ignoring it", category: .app)
        } else {
            RKMLog.info("no stored address — the setup screen decides where to load from", category: .app)
        }
    }

    /// ⚠ `os_log` `.debug` is not persisted and `.info` is only flushed on collection, so the
    /// **file** is the durable record. Backgrounding is the last guaranteed moment before iOS may
    /// suspend or kill the app, so that is where the flush belongs — not on every line.
    static func wentToBackground() {
        RKMLog.info("scene background — flushing the file log", category: .app)
        RKMLog.shared.flush()
    }

    static func cameToForeground() {
        RKMLog.info("scene foreground", category: .app)
    }
}
