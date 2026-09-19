import Foundation
// ⚠ Linux and Darwin disagree about where `HTTPCookie` lives: swift-corelibs-foundation puts it in
// `FoundationNetworking`, and Apple's SDK has no such module (there, `Foundation` already has it). Without
// this the file does not compile here, leaves the gate, and becomes a rule nobody has ever run — which is the
// one outcome this file exists to avoid.
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// How the player gets the credential `AVPlayer` cannot get from `URLSession` — one rule, in one place, and
/// pure `Foundation` so it can be **RUN on Linux** (`apple/scripts/check-tvos-core.py`) instead of being
/// discovered on a TV in another room.
///
/// ⚠⚠ **WHY THIS FILE EXISTS.** `Core/APIClient.swift` authenticates every REST call for free: it uses
/// `URLSession.shared`, whose cookie store already holds the session cookie the api sets at sign-in. Playback
/// is different — `AVPlayer`'s media-playlist and segment requests are not made by our `URLSession`, so the
/// cookie that makes every other call work is simply not on them.
///
/// The carrier is the cookie the app **already has**, handed to the asset explicitly. Nothing new is minted,
/// nothing is stored twice, and **no backend change is needed** — which is the whole reason this phase is
/// ordered to measure before it builds: whether the cookie reaches a *segment* is a fact about Apple's
/// platform, settled by the round's falsifier, not by an argument here.
///
/// ⚠⚠ **AND WHY IT IS `Foundation`-ONLY.** The moment this file imports AVFoundation it stops compiling on
/// Linux, leaves the gate, and becomes "a tool that has never been executed". So the AVFoundation key the
/// options dictionary is built under is a **parameter**, supplied by the Mac-only call site — where a
/// misspelled or absent key is a **compile error**, i.e. the visible failure this repo insists on over a
/// silent one. See `assetOptions(cookieKey:cookie:)`.
///
/// ⚠ The four predicates in `applies(_:to:)` each have a way of being wrong that looks exactly like "playback
/// is broken", which is why they are pinned individually rather than as one check.
enum PlaybackAuth {

    /// The cookie the api sets at sign-in (`backend/services/auth.py::SESSION_COOKIE`).
    ///
    /// ⚠ It carries the app's **opaque session id** — never the Jellyfin token, which by
    /// `backend/api/routes/auth.py`'s own stated rule never reaches a client at all, in a body, a log line or a
    /// cookie.
    static let sessionCookieName = "rkm_session"

    /// What the player says when there is no session cookie to play with.
    ///
    /// ⚠ **A REFUSAL, not a fallback** — the client-side echo of `api/session.py`'s identity rail, which exists
    /// because *a silent fallback is worse than an error*. An unauthenticated `AVPlayer` load does not fail
    /// cleanly: the api answers `401`, the player draws a black screen, and "it just doesn't play" is the least
    /// diagnosable bug a TV can produce. Naming the missing credential turns it into one sentence.
    static let missingSessionSentence = "Not signed in on this TV. Sign in again, then play."

    // MARK: - Which cookie

    /// The session cookie to play with, or `nil` when this app holds none that covers `origin`.
    ///
    /// ⚠ `nil` is a real answer and the caller must say so (`missingSessionSentence`). It is deliberately
    /// **not** satisfied by "some cookie": returning an unrelated cookie for the same host sends a credential
    /// that cannot work and hides why.
    static func sessionCookie(for origin: URL, in cookies: [HTTPCookie]) -> HTTPCookie? {
        cookies.first { applies($0, to: origin) }
    }

    /// Does `cookie` cover a request to `origin`?
    ///
    /// Four predicates, and each is a separate way to be wrong: the wrong cookie (another app on the same
    /// host), a cookie belonging to a different host, an expired session, or a cookie scoped to a path this
    /// app does not use.
    static func applies(_ cookie: HTTPCookie, to origin: URL) -> Bool {
        guard cookie.name == sessionCookieName else { return false }
        guard let host = origin.host?.lowercased(), !host.isEmpty else { return false }
        guard domainCovers(cookie.domain, host: host) else { return false }
        if let expires = cookie.expiresDate, expires <= Date() { return false }
        let requestPath = origin.path.isEmpty ? "/" : origin.path
        return pathCovers(cookie.path, requestPath: requestPath)
    }

    /// A host-only cookie matches its exact host; a domain cookie (written with a leading dot) also covers
    /// subdomains.
    ///
    /// ⚠ The suffix test is on `"." + domain`, never on `domain` alone — otherwise `notrkm-hp.ts.net` would
    /// satisfy a cookie for `rkm-hp.ts.net` and a cookie would be handed to a host it was never issued for.
    static func domainCovers(_ cookieDomain: String, host: String) -> Bool {
        let domain = cookieDomain.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        guard !domain.isEmpty else { return false }
        if host == domain { return true }
        guard cookieDomain.hasPrefix(".") else { return false }
        return host.hasSuffix("." + domain)
    }

    /// A cookie path covers its own path and everything beneath it.
    ///
    /// ⚠ The `"/"`-suffix handling is the whole rule: `"/api"` must cover `/api/x` but **not** `/apix`.
    static func pathCovers(_ cookiePath: String, requestPath: String) -> Bool {
        let base = cookiePath.isEmpty ? "/" : cookiePath
        if base == "/" { return true }
        if requestPath == base { return true }
        return requestPath.hasPrefix(base.hasSuffix("/") ? base : base + "/")
    }

    // MARK: - Handing it to the asset

    /// The options dictionary an `AVURLAsset` needs, under the key the **caller** supplies.
    ///
    /// ⚠⚠ **The key is a parameter on purpose, and the reason is structural, not stylistic.**
    /// `AVURLAssetHTTPCookiesKey` is AVFoundation; naming it here would take this whole file out of the Linux
    /// gate. The Mac-only call site passes it instead — and that site is compiled against the real header, so a
    /// wrong or non-existent key fails the **build**, visibly, in one line.
    ///
    /// ⚠ Returns `nil` for an empty key rather than an options dictionary keyed on `""`: a bogus key is
    /// silently ignored by the framework, which would turn "we configured the wrong thing" into "the cookie
    /// didn't work" — the exact confusion this phase is trying to avoid.
    static func assetOptions(cookieKey: String, cookie: HTTPCookie) -> [String: Any]? {
        guard !cookieKey.isEmpty else { return nil }
        return [cookieKey: [cookie]]
    }

    // MARK: - Logging

    /// A description of the cookie that is **safe to log**.
    ///
    /// ⚠ The value is a bearer credential — `services/auth.py::SessionStore` stores only its **sha256**, so a
    /// reader of the store file gets no usable session and a reader of a LOG must certainly not get one either.
    /// `RKMLog`'s redactor handles URLs; this handles the one credential the player is handed directly, which
    /// the redactor never sees.
    static func loggable(_ cookie: HTTPCookie?) -> String {
        guard let cookie else { return "no session cookie" }
        return "session cookie for \(cookie.domain)\(cookie.path) (value withheld)"
    }
}
