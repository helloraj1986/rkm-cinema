import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import Combine
import RKMServerKit

/// What one poster's load is doing. `Data`, not an image — ⚠ deliberately, because that is what makes this
/// file compile on Linux: the SwiftUI card turns the bytes into an `Image`, and everything about *fetching*
/// them is checked here before a Mac round is spent on it.
enum PosterState: Equatable {
    case idle
    case loading
    case loaded(Data)
    /// Why there is no picture. ⚠ Never empty: an empty poster and a broken poster must not be the same
    /// thing to the card, and the card shows this in the debug HUD rather than as a silent grey rectangle.
    case failed(String)
}

/// Loads ONE poster, with the one diagnostic that matters.
///
/// ⚠⚠ **THE QUESTION THIS FILE EXISTS TO ANSWER, and why `AsyncImage` was not used.** `GET
/// /api/jellyfin/poster` is **session-scoped** — the api resolves *whose* library to read from the session
/// cookie — so an image request that does not carry that cookie answers `401` and the wall comes up empty.
/// `AsyncImage` shares `URLSession.shared` too, so it would *probably* work; what it cannot do is tell
/// anyone. On a TV there is no Web Inspector and no console: **a poster wall with no posters looks exactly
/// like an empty library**, and the two need opposite fixes.
///
/// So this loader logs, per poster: whether a session cookie was attached to the request, the HTTP status,
/// the byte count, and whether the answer came from the cache. `session-cookie=absent` on a `401` is the
/// entire diagnosis for the failure this phase could not rule out from the sandbox, and it is read off the
/// debug HUD without a Mac.
///
/// ⚠ **The cookie value is never logged** — names only, the same rule as `SessionStore.logCookieState` and
/// for the same reason (`LogRedactor` exists to make that structural rather than remembered).
///
/// ⚠ Caching is left to `URLSession.shared` (`useProtocolCachePolicy`) on purpose: the api serves artwork
/// with `max-age=604800, stale-while-revalidate=604800` **plus** `ETag`/`Last-Modified`, and artwork is
/// immutable for a given `(item id, kind, width)` — so a revisit is a bodiless `304` and there is nothing
/// for this file to cache itself. A second cache of the same bytes is the thing that drifts.
final class PosterLoader: ObservableObject {

    @Published private(set) var state: PosterState = .idle

    let itemID: String
    /// ⚠ `private(set) var`, not `let`: U6's fallback chain re-points it at the poster when a backdrop is
    /// missing (see ``fallBackToPoster``).
    private(set) var url: URL?
    /// ⚠ Which artwork route this loader is fetching — `poster` for the 2:3 card of old, `backdrop` for the
    /// 16:9 card and the hero band (U6). It is carried so the LOG LINES name it: a `401` on a backdrop and a
    /// `401` on a poster are the same defect, but only one of them is on screen when somebody reports "the
    /// hero is empty".
    private(set) var route: PosterURL.Route
    /// The width this loader was asked for, so the fallback rebuilds the URL with the SAME width.
    private let width: Int?

    private let base: URL
    private let timeout: TimeInterval
    private var started = false
    /// ⚠ Guards the fallback: **one** step, and it never runs back the other way.
    private var fellBack = false

    init(base: URL, itemID: String, width: Int? = nil, route: PosterURL.Route = .poster,
         timeout: TimeInterval = 20) {
        self.itemID = itemID
        self.route = route
        self.width = width
        self.base = base
        self.url = PosterURL.url(base: base, itemID: itemID, width: width, route: route)
        self.timeout = timeout
    }

    /// Fetch once. ⚠ Guarded rather than cancelled-and-restarted: a card that re-enters the screen must not
    /// re-request an immutable image, and `state` is what the card renders from either way.
    func load() async {
        guard !started else { return }
        started = true

        guard let url else {
            // ⚠ A row with no id is a broken row, not a missing poster — `PosterURL` refused to build a
            // URL, and saying so is better than a request that would 404.
            state = .failed("no item id")
            return
        }

        state = .loading
        let correlation = CorrelationID.next()

        // ⚠ Cookies are read for the URL we are ABOUT to request, by name only.
        let cookieNames = (HTTPCookieStorage.shared.cookies(for: url) ?? []).map(\.name)
        let hasSession = cookieNames.contains(SessionStore.sessionCookieName)
        let alreadyCached = URLCache.shared.cachedResponse(for: URLRequest(url: url)) != nil

        var request = URLRequest(url: url, cachePolicy: .useProtocolCachePolicy, timeoutInterval: timeout)
        request.setValue("image/*", forHTTPHeaderField: "Accept")

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard (200..<300).contains(status) else {
                let message = status == 401
                    ? "not authorised — the session cookie did not reach the image request"
                    : "the server answered \(status)"
                RKMLog.error("\(route.rawValue) \(Self.short(itemID)) -> \(status) — session-cookie="
                                + "\(hasSession ? "present" : "ABSENT"), cached-before=\(alreadyCached)",
                             category: .net, correlation: correlation)
                // ⚠ A missing BACKDROP is not a broken card: fall back to the poster, exactly as the web
                // app's own hero does, and only report a failure once BOTH routes are exhausted.
                if await fallBackToPoster(correlation: correlation) { return }
                state = .failed(message)
                return
            }
            RKMLog.info("\(route.rawValue) \(Self.short(itemID)) -> \(status), \(data.count) bytes, "
                            + "session-cookie=\(hasSession ? "present" : "absent"), "
                            + "cached-before=\(alreadyCached)",
                        category: .net, correlation: correlation)
            state = .loaded(data)
        } catch {
            let nsError = error as NSError
            RKMLog.error("\(route.rawValue) \(Self.short(itemID)) FAILED — \(nsError.domain) \(nsError.code) · "
                            + "session-cookie=\(hasSession ? "present" : "absent")",
                         category: .net, correlation: correlation)
            state = .failed("\(nsError.domain) \(nsError.code)")
        }
    }

    /// ⚠⚠ **THE WEB'S OWN FALLBACK CHAIN, and the reason U6 needs it: a 16:9 card cannot be filled by a
    /// 2:3 poster.** The prototype draws every card as 16:9 keyart, which is what Jellyfin's *Backdrop*
    /// image is — but not every item has one, and the api answers a plain **404** for a missing image
    /// (`jellyfin_poster.py::_proxy_image`: *"A MISSING image is never cached"*). Without this step a library
    /// full of poster-only titles would draw a wall of "no photo" marks — the exact failure this file's
    /// header exists to make visible, arriving by design.
    ///
    /// So a failed BACKDROP is retried ONCE as the item's POSTER, which is the artwork every item is
    /// guaranteed to have (the whole app was built on that), and the web's hero does the same thing
    /// (`LibraryHomeView.tsx`: backdrop → poster → seeded art).
    ///
    /// ⚠ Returns true when it took over — i.e. when the caller should NOT write its own failure state. It
    /// never runs twice (`fellBack`), never runs for a poster request (there is nothing below a poster), and
    /// **never runs on a TRANSPORT error**: a network that went away is not a missing image, and retrying it
    /// would double the load for every dead request.
    @discardableResult
    private func fallBackToPoster(correlation: CorrelationID) async -> Bool {
        guard route == .backdrop, !fellBack else { return false }
        fellBack = true
        route = .poster
        url = PosterURL.url(base: base, itemID: itemID, width: width, route: .poster)
        RKMLog.info("artwork \(Self.short(itemID)) — no backdrop; falling back to the poster",
                    category: .net, correlation: correlation)
        // ⚠ `started` is cleared so `load()`'s own guard lets the retry through — the guard exists to stop a
        // card re-requesting an immutable image, not to stop this deliberate second request.
        started = false
        await load()
        return true
    }

    /// ⚠ The first 8 characters only. A Jellyfin id is 32 hex characters and the HUD is a fixed-width
    /// readout; a full id per poster would push the status off the line, which is the part being read.
    private static func short(_ itemID: String) -> String {
        String(itemID.prefix(8))
    }
}
