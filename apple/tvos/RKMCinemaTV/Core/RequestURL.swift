import Foundation

/// How every native request's URL is built — one rule, in one place, **and pure `Foundation` so it can be
/// RUN on Linux** (`apple/scripts/check-tvos-core.py`) instead of discovered on a TV.
///
/// ⚠⚠ **WHY THIS IS ITS OWN FILE, AND IT IS THE SAME REASON `PosterURL` IS.** The rule it holds is the
/// single most expensive silent mistake in this app's transport: **`URL.appendingPathComponent(_:)`
/// percent-escapes its WHOLE argument**, so appending `"api/jellyfin/detail?id=X"` sends
/// `…/detail%3Fid=X` — the query becomes part of the PATH and the server answers `404` for an item that
/// exists. The screen would show "we couldn't find that title in the library", which is the app's own
/// `notFound` copy, i.e. a transport bug wearing a content bug's clothes.
///
/// `PosterURL` already carries this finding for the artwork proxy. Phase B4 needed the same thing for a
/// JSON request, and the choice was: duplicate the builder inside `APIClient` (which imports
/// `RKMServerKit`, so nothing in the sandbox can execute it) or extract it here, where a test can. It is
/// here.
///
/// ⚠ **The no-query case is deliberately unchanged**: it still goes through `appendingPathComponent`, which
/// is what every round so far has exercised, and there is nothing to escape when there is no query.
enum RequestURL {

    /// The absolute URL for `path` against a stored server address, optionally with query items.
    ///
    /// Returns `nil` when a URL cannot be assembled at all — the caller turns that into a transport failure
    /// rather than a request to a half-built address.
    static func url(base: URL, path: String, query: [URLQueryItem] = []) -> URL? {
        guard !query.isEmpty else { return base.appendingPathComponent(path) }
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else { return nil }
        let root = components.path.hasSuffix("/") ? String(components.path.dropLast()) : components.path
        components.path = root + "/" + path
        // ⚠ `URLComponents` escapes each VALUE, so an id containing `+`, `&`, `/` or a space is sent as data
        // rather than read as query syntax — the same rule `PosterURL` applies to a poster id.
        components.queryItems = query
        return components.url
    }
}
