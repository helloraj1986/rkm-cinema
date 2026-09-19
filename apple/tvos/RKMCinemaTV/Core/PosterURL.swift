import Foundation

/// Where a poster comes from — one rule, in one place, for every card in the app.
///
/// ⚠ **The app NEVER fetches artwork from the media server directly.** `GET /api/jellyfin/poster` is a
/// same-origin proxy that keeps the Jellyfin credential server-side (see
/// `backend/api/routes/jellyfin_poster.py`); the browser is only ever meant to hit `/api`. A native client
/// that went to Jellyfin itself would have to hold a Jellyfin token, which is the exact thing this app's
/// identity model exists to avoid — so it does not.
///
/// ⚠⚠ **SESSION-SCOPED, WHICH IS WHY THIS IS A FUNCTION AND NOT A STRING.** The proxy resolves *whose*
/// library to read from the session, so the request must carry the session cookie. `AsyncImage` uses
/// `URLSession.shared`, whose cookie store is the same one `POST /api/auth/login` populated, so the
/// cheapest thing to try first is the thing that should simply work. It is not proven on tvOS — no
/// SwiftUI or `URLSession` behaviour can be exercised in this sandbox — and **a poster wall with no
/// posters looks identical to a broken screen**, so `PosterLoader` (the SwiftUI half, Phase B2) logs the
/// HTTP status of every failed image rather than painting an empty rectangle in silence.
///
/// Pure `Foundation`, no SwiftUI: so the URL this builds is typechecked and asserted on Linux
/// (`apple/scripts/check-apple-typecheck.sh`) before any Mac round, and the web app's own builder
/// (`frontend/src/features/library/lib.ts::posterUrl`) is the description it mirrors.
enum PosterURL {

    /// ⚠ Matches the web app's `width=500`. The server accepts 16…2000 and **422s outside that range**, so
    /// an out-of-range value is a failed round rather than a degraded image: `clamped(_:)` is the only way
    /// a width enters a URL.
    static let defaultWidth = 500

    /// The proxy's own ceiling and floor (`Query(default=500, ge=16, le=2000)`).
    static let widthRange = 16...2000

    /// `/api/jellyfin/poster?id=…&width=…`, relative to the stored server address — the same form
    /// `APIClient` builds its paths from, so there is one convention for "where the api is".
    ///
    /// Returns `nil` for an empty id rather than a URL that would 404: an item with no id is not a
    /// resumable/missing-poster distinction, it is a broken row, and the caller should draw nothing.
    static func path(itemID: String, width: Int = defaultWidth) -> String? {
        guard !itemID.isEmpty else { return nil }
        var components = URLComponents()
        components.path = "api/jellyfin/poster"
        components.queryItems = [
            URLQueryItem(name: "id", value: itemID),
            URLQueryItem(name: "width", value: String(clamped(width))),
        ]
        return components.string
    }

    /// An absolute URL against the address a human typed on screen #0.
    ///
    /// ⚠ Built by mutating the base's components rather than by `appendingPathComponent(_:)`: that method
    /// percent-escapes the whole argument, so a query string appended through it arrives as part of the
    /// path and the server answers a 404 on a poster that exists.
    static func url(base: URL, itemID: String, width: Int = defaultWidth) -> URL? {
        guard !itemID.isEmpty,
              var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else { return nil }
        let root = components.path.hasSuffix("/") ? String(components.path.dropLast()) : components.path
        components.path = root + "/api/jellyfin/poster"
        // `URLComponents` percent-encodes each value, so a Jellyfin item id with a `+` or `/` in it is
        // sent as data rather than being read as part of the query.
        components.queryItems = [
            URLQueryItem(name: "id", value: itemID),
            URLQueryItem(name: "width", value: String(clamped(width))),
        ]
        return components.url
    }

    /// Keep a width inside the range the server documents, so a wrong constant is a visibly wrong size
    /// rather than a 422 with no picture.
    static func clamped(_ width: Int) -> Int {
        min(max(width, widthRange.lowerBound), widthRange.upperBound)
    }
}
