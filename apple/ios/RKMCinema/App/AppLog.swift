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

    /// The debug overlay's remembered state. Off by default (`LOGGING.md` §4); once he turns it
    /// on it stays on across launches, because hunting for the toggle before every screenshot is
    /// friction. Also settable from a scheme launch argument — `-RKMDebugHUD YES` — because
    /// `UserDefaults` reads `-Key Value` arguments automatically.
    static let hudDefaultsKey = "RKMDebugHUD"

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
