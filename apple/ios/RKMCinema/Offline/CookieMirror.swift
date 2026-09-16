import Foundation
import WebKit
import RKMServerKit

/// The web view's cookies, made available to the NATIVE side.
///
/// ⚠⚠ **This is a hard prerequisite, not a nicety** (`NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.4 option 1):
/// a native `URLSession` has **no cookie jar of its own**, and every `/api/offline/*` route is
/// session-scoped (`RKM_AUTH_REQUIRED=true` — measured, B1's step-5 probe answered `401
/// {"detail":"Sign in to use this app"}`). So a download either carries the shell's session cookie or it
/// fails. The cookie is the page's: it is set when the *page* signs in (`POST /api/auth/login`), inside
/// `WKWebsiteDataStore.default()`, and this type is how it gets out.
///
/// The mechanism, in order, because it matters which part is trusted:
///
/// 1. **`WKHTTPCookieStoreObserver`** — the store tells us when cookies change, so signing in, signing
///    out and a session refresh all re-mirror **with no page changes at all**. Polling this was the
///    alternative and it is strictly worse: a poll can miss the one moment it matters.
/// 2. **The values never leave this type** — `OfflineAPI` asks for a header, and the header is built by
///    `CookieHeader` (Linux-tested: domain/path/expiry/Secure rules, CRLF injection, duplicates). What
///    is logged is a NAME SUMMARY, through the same redactor the shell already uses.
/// 3. **Nothing is written to `HTTPCookieStorage.shared`.** Tempting, and it is what a browser would do,
///    but a background `URLSession` is documented to use the shared cookie store *inconsistently*
///    (cookies lost on redirects — a known Apple bug, r.16,852,027), and a silent cookie loss is a
///    mystery `401`. The downloader therefore sets the `Cookie:` header **explicitly** on every request
///    and the session is configured not to add or accept cookies of its own. One source of cookies, one
///    place that decides which ones go out.
final class CookieMirror: NSObject, WKHTTPCookieStoreObserver {

    private let store: WKWebsiteDataStore
    private let lock = NSLock()

    /// ⚠ `HTTPCookie` is not `Sendable` and WebKit's callbacks arrive on a private queue; the snapshot
    /// array is the boundary, guarded by `lock`.
    private var snapshots: [CookieSnapshot] = []

    /// The same string the shell's HUD shows, so a screenshot and the log agree (`LOGGING.md` §2).
    private(set) var summary: String = "unknown"

    /// Called on the main queue after every change, so the HUD can refresh.
    var onChange: ((String) -> Void)?

    init(store: WKWebsiteDataStore = .default()) {
        self.store = store
        super.init()
    }

    // MARK: - Lifecycle

    /// Registers for change notifications and takes the first snapshot. Idempotent.
    func start() {
        store.httpCookieStore.add(self)
        refresh(announce: true)
    }

    func stop() {
        store.httpCookieStore.remove(self)
    }

    // MARK: - The observer callback

    func cookiesDidChange(in cookieStore: WKHTTPCookieStore) {
        // ⚠ The reason the observer is worth its complexity: this fires when the PAGE signs in, so the
        // native side learns about a new session without the page telling it anything.
        refresh(announce: true)
    }

    // MARK: - Reading

    /// Copies WebKit's cookies into the value type the rules are written against.
    func refresh(announce: Bool = false) {
        store.httpCookieStore.getAllCookies { [weak self] cookies in
            guard let self else { return }
            let mirrored = cookies.map(Self.snapshot)
            let names = mirrored.map(\.name).sorted()
            let summary = LogRedactor.redact(cookieNames: names)

            self.lock.lock()
            self.snapshots = mirrored
            let changed = self.summary != summary
            self.summary = summary
            self.lock.unlock()

            if announce || changed {
                // ⚠ Count and names only, never values (`LOGGING.md` §6).
                RKMLog.info("offline cookie mirror: \(summary) — native downloads will carry "
                            + "\(mirrored.isEmpty ? "no session" : "the session")", category: .offline)
            }
            DispatchQueue.main.async { self.onChange?(summary) }
        }
    }

    /// What is available right now, for a header decision.
    func cookieSnapshots() -> [CookieSnapshot] {
        lock.lock()
        defer { lock.unlock() }
        return snapshots
    }

    /// The `Cookie:` header for one URL, and what was skipped — the diagnosis for a mystery 401.
    func headerOutcome(for url: URL, now: Date = Date()) -> CookieHeaderOutcome {
        CookieHeader.evaluate(cookies: cookieSnapshots(), url: url, now: now)
    }

    var isEmpty: Bool {
        lock.lock()
        defer { lock.unlock() }
        return snapshots.isEmpty
    }

    // MARK: - Bridging

    /// ⚠ `isSessionOnly` is deliberately NOT `expiresDate == nil` alone: WebKit sets `isSessionOnly`
    /// for a cookie with no expiry, and the two can disagree on a cookie the server sent with both.
    /// `CookieHeader` only needs "does it have an expiry, and has it passed".
    static func snapshot(_ cookie: HTTPCookie) -> CookieSnapshot {
        CookieSnapshot(
            name: cookie.name,
            value: cookie.value,
            domain: cookie.domain,
            path: cookie.path.isEmpty ? "/" : cookie.path,
            expiresAt: cookie.isSessionOnly ? nil : cookie.expiresDate,
            isSecure: cookie.isSecure,
            isHTTPOnly: cookie.isHTTPOnly
        )
    }
}
