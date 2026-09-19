import Foundation
import RKMServerKit

/// Wiring the log up at launch, and the banner that makes a log self-describing.
///
/// ⚠ **This is a port of `apple/ios/RKMCinema/App/AppLog.swift`, and the two differences are the whole
/// story of the tvOS platform:**
///
/// 1. **There is no `UIDevice` on tvOS.** `ProcessInfo.operatingSystemVersionString` gives the OS, and
///    the simulator's model comes from `SIMULATOR_MODEL_IDENTIFIER` — a real Apple TV reports neither, so
///    the log says `Apple TV` and the OS version, which is all that is knowable from here.
/// 2. **There is no shake and no bezel to triple-tap.** On iOS the overlay has three routes in (a corner
///    gesture, a shake, and a launch argument). On a TV the remote has no shake, so the routes are the
///    launch argument `-RKMDebugHUD YES` and the **Debug chip on screen #0** — a focusable control, so it
///    is reachable with the d-pad and *visible*, which is the property both iOS failures lacked.
///
/// ⚠ **`Foundation` + `RKMServerKit` only — no SwiftUI, no UIKit.** That is not tidiness: it is what lets
/// `apple/scripts/check-apple-typecheck.sh` compile this file on Linux, so the launch banner is verified
/// before a Mac round rather than during one.
enum AppLog {

    /// The debug overlay's remembered state.
    ///
    /// ⚠⚠ **A Debug build starts CLEAN — hidden.** The iOS app learned this on 2026-09-19: the panel is
    /// large and sits over the middle of the screen, so a build that opened with it on covered a
    /// session-check spinner and read as *"a blank app"*, which cost a device round. His instruction then
    /// was *"disable the debug overlay … enable it later whenever we need it"*, and tvOS inherits it.
    ///
    /// ⚠ The STORED value is deliberately ignored in a Debug build rather than merely defaulted:
    /// honouring it is how the overlay became effectively permanent (one session toggles it on, the value
    /// persists, and every launch afterwards opens with it). A Release build reads the stored value.
    static let hudDefaultsKey = "RKMDebugHUD"

    static var hudStartsVisible: Bool {
        #if DEBUG
        // ⚠ The ARGUMENT domain on its own. `UserDefaults.bool(forKey:)` folds the argument and stored
        // domains together, which would make a deliberate per-launch override indistinguishable from a
        // persisted setting — the exact distinction this whole comment is about.
        let argument = UserDefaults.standard.volatileDomain(forName: UserDefaults.argumentDomain)
        if let flag = argument[hudDefaultsKey] as? Bool { return flag }
        if let text = argument[hudDefaultsKey] as? String {
            return ["YES", "TRUE", "1"].contains(text.uppercased())
        }
        return false
        #else
        return UserDefaults.standard.bool(forKey: hudDefaultsKey)
        #endif
    }

    /// The same fact as a value, so the launch banner can say *why* it starts visible rather than leaving
    /// it to be inferred from the build.
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
            let directory = try RollingFileLog.defaultDirectory(appFolder: "RKMCinemaTV")
            fileLog = try RollingFileLog(directory: directory, policy: .init(baseName: "rkm-tvos.log"))
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

        RKMLog.info("RKMCinemaTV \(version) (\(build)) · \(Bundle.main.bundleIdentifier ?? "?")", category: .app)
        RKMLog.info(
            "device \(modelName) · \(ProcessInfo.processInfo.operatingSystemVersionString)"
                + " · locale \(Locale.current.identifier) · tz \(TimeZone.current.identifier)",
            category: .app
        )
        RKMLog.info("log level \(level.name) · subsystem \(RKMLog.subsystem)", category: .app)
        RKMLog.info(
            "debug overlay: starts \(hudStartsVisible ? "VISIBLE" : "hidden")"
                + " (Debug: hidden unless `-RKMDebugHUD YES` — the stored value is ignored on purpose);"
                + " stored value \(UserDefaults.standard.bool(forKey: hudDefaultsKey));"
                + " to show it: the Debug chip on screen #0, or `-RKMDebugHUD YES`"
                + " (there is no shake and no triple-tap on a TV)",
            category: .app
        )

        if let url = RKMLog.shared.fileURL {
            RKMLog.info("file log: \(url.path)", category: .app)
        } else {
            RKMLog.error("no file log — \(fileProblem ?? "unknown reason")", category: .app)
        }

        // ⚠ This line earns its place: it is the proof that `INFOPLIST_FILE` is pointed at our
        // `Config/Info.plist`. If it is not, these read false/false and a plain-`http://` address is
        // blocked — a failure that otherwise presents as "the app is broken".
        let ats = info["NSAppTransportSecurity"] as? [String: Any]
        let arbitraryLoads = ats?["NSAllowsArbitraryLoads"] as? Bool ?? false
        let localNetworking = ats?["NSAllowsLocalNetworking"] as? Bool ?? false
        RKMLog.info("ATS declared: arbitraryLoads=\(arbitraryLoads) localNetworking=\(localNetworking)",
                    category: .app)

        let store = ServerStore()
        if let address = store.address {
            RKMLog.info(
                "stored address: \(address.displayString)"
                    + " (scheme \(address.hadExplicitScheme ? "typed by hand" : "assumed by the app"))",
                category: .app
            )
        } else if store.hasInvalidStoredValue {
            RKMLog.error("stored address will not parse: \"\(store.rawValue ?? "")\" — ignoring it",
                         category: .app)
        } else {
            RKMLog.info("no stored address — screen #0 opens pre-filled with \(ServerDefaults.address)",
                        category: .app)
        }
    }

    /// tvOS reports no model, so the simulator is the only case where an identifier exists. Saying
    /// `Apple TV` rather than guessing a generation is the honest answer: the OS version is logged
    /// beside it and that is what a deployment-target question actually needs.
    private static var modelName: String {
        if let simulated = ProcessInfo.processInfo.environment["SIMULATOR_MODEL_IDENTIFIER"] {
            return "\(simulated) (simulator)"
        }
        return "Apple TV"
    }

    /// ⚠ Flushing the file log is the ONE lifecycle hook worth having, and tvOS reaches it through
    /// SwiftUI's `scenePhase` rather than a `UIApplication` notification (there is no `UIApplication`
    /// delegate in this app). `os_log` `.debug` is never persisted and `.info` is only flushed when
    /// something collects it, so the file is the durable record — and the last moment the app is known to
    /// be alive is when it leaves the foreground.
    static func wentToBackground() {
        RKMLog.info("scene background — flushing the file log", category: .app)
        RKMLog.shared.flush()
    }

    static func cameToForeground() {
        RKMLog.info("scene foreground", category: .app)
    }
}
