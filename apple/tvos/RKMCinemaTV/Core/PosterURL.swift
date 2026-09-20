import Foundation

/// Where artwork comes from — one rule, in one place, for every card and every hero band in the app.
///
/// ⚠ **The app NEVER fetches artwork from the media server directly.** `/api/jellyfin/poster` and
/// `/api/jellyfin/backdrop` are same-origin proxies that keep the Jellyfin credential server-side (see
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
/// ⚠⚠ **TWO ROUTES, ONE BUILDER — and that is deliberate.** Phase U3's hero band needs the 16:9 *backdrop*
/// (`/api/jellyfin/backdrop`, the web's `backdropUrl`) beside the 2:3 poster the cards use. Both routes take
/// `id` and `width`, both clamp, both refuse an empty id, and both have the SAME trap
/// (`appendingPathComponent(_:)` escapes a query into the PATH — see `url(base:itemID:width:route:)`), so
/// they are one builder with a ``Route`` rather than two files whose rules drift apart. The two differ ONLY
/// in the route word and the width limits, which is exactly what ``Route`` carries.
///
/// Pure `Foundation`, no SwiftUI: so the URLs this builds are typechecked and asserted on Linux
/// (`apple/scripts/check-apple-typecheck.sh`) before any Mac round, and the web app's own builders
/// (`frontend/src/features/library/lib.ts::posterUrl` / `backdropUrl`) are the descriptions it mirrors.
enum PosterURL {

    /// One artwork proxy route, with its own server-side width limits.
    ///
    /// ⚠ **The limits are the SERVER's, read from `jellyfin_poster.py`:** `poster` is
    /// `Query(default=500, ge=16, le=2000)` and `backdrop` is `Query(default=1600, ge=16, le=4000)`. A value
    /// outside its range is a `422`, not a smaller image — so the clamp is per route, and getting it wrong
    /// looks like a missing picture rather than a wrong number.
    ///
    /// ⚠⚠ **The raw values ARE the contract paths, and that is deliberate rather than tidy.** R4 of
    /// `apple/scripts/check-tvos-models.py` checks every tvOS string literal beginning `api/` against the
    /// frozen contract — so both routes are verified by the gate, character for character, instead of being
    /// assembled at runtime where nothing can see them. `path` adds the leading slash the URL builder drops.
    enum Route: String {
        case poster = "api/jellyfin/poster"
        case backdrop = "api/jellyfin/backdrop"

        var path: String { "/" + rawValue }

        var defaultWidth: Int { self == .poster ? 500 : 1600 }

        var widthRange: ClosedRange<Int> { self == .poster ? 16...2000 : 16...4000 }
    }

    /// ⚠ Matches the web app's `width=500` for a poster (`lib.ts::posterUrl`), and its `width=1600` for a
    /// backdrop (`lib.ts::backdropUrl`).
    static let defaultWidth = Route.poster.defaultWidth

    /// The poster route's ceiling and floor. ⚠ Kept as the default route's range for the callers that only
    /// ever make posters; a route-aware caller asks `Route.widthRange`.
    static let widthRange = Route.poster.widthRange

    /// `/api/jellyfin/poster?id=…&width=…` (or the backdrop route), relative to the stored server address —
    /// the same form `APIClient` builds its paths from, so there is one convention for "where the api is".
    ///
    /// Returns `nil` for an empty id rather than a URL that would 404: an item with no id is not a
    /// resumable/missing-poster distinction, it is a broken row, and the caller should draw nothing.
    static func path(itemID: String, width: Int? = nil, route: Route = .poster) -> String? {
        guard !itemID.isEmpty else { return nil }
        var components = URLComponents()
        components.path = String(route.path.dropFirst())   // URLComponents takes no leading slash
        components.queryItems = [
            URLQueryItem(name: "id", value: itemID),
            URLQueryItem(name: "width", value: String(clamped(width ?? route.defaultWidth, route: route))),
        ]
        return components.string
    }

    /// An absolute URL against the address a human typed on screen #0.
    ///
    /// ⚠⚠ Built by mutating the base's components rather than by `appendingPathComponent(_:)`: that method
    /// percent-escapes the whole argument, so a query string appended through it arrives as part of the
    /// path and the server answers a 404 on a poster that exists. **This is the rule the whole file exists
    /// for**, and it is why `path`/`url` are two functions rather than one string built by a caller.
    static func url(base: URL, itemID: String, width: Int? = nil, route: Route = .poster) -> URL? {
        guard !itemID.isEmpty,
              var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else { return nil }
        let root = components.path.hasSuffix("/") ? String(components.path.dropLast()) : components.path
        components.path = root + route.path
        // `URLComponents` percent-encodes each value, so a Jellyfin item id with a `+` or `/` in it is
        // sent as data rather than being read as part of the query.
        components.queryItems = [
            URLQueryItem(name: "id", value: itemID),
            URLQueryItem(name: "width", value: String(clamped(width ?? route.defaultWidth, route: route))),
        ]
        return components.url
    }

    /// Keep a width inside the range the server documents **for that route**, so a wrong constant is a
    /// visibly wrong size rather than a 422 with no picture.
    static func clamped(_ width: Int, route: Route = .poster) -> Int {
        min(max(width, route.widthRange.lowerBound), route.widthRange.upperBound)
    }
}
