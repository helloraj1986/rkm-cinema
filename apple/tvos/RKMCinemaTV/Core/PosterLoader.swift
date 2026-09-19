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
    let url: URL?

    private let timeout: TimeInterval
    private var started = false

    init(base: URL, itemID: String, width: Int = PosterURL.defaultWidth, timeout: TimeInterval = 20) {
        self.itemID = itemID
        self.url = PosterURL.url(base: base, itemID: itemID, width: width)
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
                RKMLog.error("poster \(Self.short(itemID)) -> \(status) — session-cookie="
                                + "\(hasSession ? "present" : "ABSENT"), cached-before=\(alreadyCached)",
                             category: .net, correlation: correlation)
                state = .failed(message)
                return
            }
            RKMLog.info("poster \(Self.short(itemID)) -> \(status), \(data.count) bytes, "
                            + "session-cookie=\(hasSession ? "present" : "absent"), "
                            + "cached-before=\(alreadyCached)",
                        category: .net, correlation: correlation)
            state = .loaded(data)
        } catch {
            let nsError = error as NSError
            RKMLog.error("poster \(Self.short(itemID)) FAILED — \(nsError.domain) \(nsError.code) · "
                            + "session-cookie=\(hasSession ? "present" : "absent")",
                         category: .net, correlation: correlation)
            state = .failed("\(nsError.domain) \(nsError.code)")
        }
    }

    /// ⚠ The first 8 characters only. A Jellyfin id is 32 hex characters and the HUD is a fixed-width
    /// readout; a full id per poster would push the status off the line, which is the part being read.
    private static func short(_ itemID: String) -> String {
        String(itemID.prefix(8))
    }
}
