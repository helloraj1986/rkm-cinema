// ⚠ NOT SHIPPED AND NOT COMPILED INTO THE APP — this file only ever exists inside the scratch copy
// `apple/scripts/check-apple-typecheck.sh` builds. It is the "mimic the overloads" technique from
// `apple/WORKFLOW.md` §5 scaled up: the smallest stand-ins whose SHAPES match the Apple APIs the iOS
// sources call, so `swiftc` can check the parts that are ours — types, argument labels, optionality,
// protocol conformance — without a Mac.
//
// ⚠⚠ WHAT IT CANNOT DO, and the reason the script reports per file: it has no UIKit, no WebKit, no
// Combine, and two `URLSessionConfiguration` members are Darwin-only. Those show up as errors and are
// filtered by name. Everything else is a real error in the real source.
import Foundation

#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

// MARK: - Combine stand-ins

protocol ObservableObject: AnyObject {}

@propertyWrapper
struct Published<Value> {
    var wrappedValue: Value
    init(wrappedValue: Value) { self.wrappedValue = wrappedValue }
    var projectedValue: Published<Value> { self }
}

// MARK: - UIKit stand-ins

typealias UIBackgroundTaskIdentifier = Int

extension Int {
    static var invalid: Int { -1 }
}

final class UIApplication {
    static let shared = UIApplication()
    func beginBackgroundTask(withName: String?, expirationHandler: (() -> Void)?) -> UIBackgroundTaskIdentifier {
        _ = expirationHandler
        _ = withName
        return 0
    }
    func endBackgroundTask(_ identifier: UIBackgroundTaskIdentifier) { _ = identifier }
}

// MARK: - WebKit stand-in (only the slice `OfflineAPI` touches)

final class CookieMirror {
    var summary: String { "stub" }
    func start() {}
    func stop() {}
    func headerOutcome(for url: URL, now: Date = Date()) -> CookieHeaderOutcome {
        CookieHeader.evaluate(cookies: [], url: url, now: now)
    }
}
