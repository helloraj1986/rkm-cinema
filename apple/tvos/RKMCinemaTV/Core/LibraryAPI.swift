import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import RKMServerKit

// The Home's two calls — typed, in one place, so no view ever spells a path.
//
// ⚠ Every path literal below is checked against the frozen contract by
// `apple/scripts/check-tvos-models.py` (R4), so a typo is a failed round here rather than a 404 on a TV.
//
// ⚠ **These are PASSIVE LISTINGS, and the api already degrades them** (`docs/ARCHITECTURE.md`: a provider
// failure comes back as `provider: null` with an empty list, never a 500). So a thrown error from these
// two functions means the transport or the session failed — not that a row is empty. The distinction is
// what `RailOutcome` exists to keep: empty and failed must not reach the screen looking the same.

extension APIClient {

    /// `GET /api/library/continue-watching` — in-progress titles, most recent first.
    func continueWatching(correlation: CorrelationID = .next()) async throws -> LibraryItemsResponse {
        try await get("api/library/continue-watching", correlation: correlation)
    }

    /// `GET /api/library/recently-watched` — finished titles, most recently played first.
    func recentlyWatched(correlation: CorrelationID = .next()) async throws -> LibraryItemsResponse {
        try await get("api/library/recently-watched", correlation: correlation)
    }

    /// `GET /api/library/folders` — the libraries a profile may see, plus the server's own folders.
    ///
    /// ⚠ **`libraries` is a SERVER-DECIDED list, and this app never filters it.** See
    /// `BrowseRules.libraryNavEntries` — his iPad report of 2026-09-14 is the reason that rule exists, and
    /// the TV must not reintroduce the second, silently-narrower filter the mobile bar used to apply.
    /// ⚠ From Phase U3 this response has TWO consumers on one screen: the Browse list and the HOME TOP BAR's
    /// tabs — both through `BrowseRules.browseEntries`, so the two cannot come to differ.
    func libraryFolders(correlation: CorrelationID = .next()) async throws -> LibrariesResponse {
        try await get("api/library/folders", correlation: correlation)
    }

    /// `GET /api/library` — the legacy Home read: the recently-added ordering (`recent`, capped
    /// server-side at 8) plus the counts.
    ///
    /// ⚠ Phase U3 added this for the HERO's second tier (`pickHomeHero`'s `recentlyAdded`), and U4 wires the
    /// same response into the Recently Added rail — one fetch, two consumers, which is why it is here rather
    /// than in either phase's view.
    func libraryRecent(correlation: CorrelationID = .next()) async throws -> LibraryRecentResponse {
        try await get("api/library", correlation: correlation)
    }

    /// `GET /api/library/items` — the whole library as a poster wall, and the **hero's last tier**
    /// (`pickHomeHero`'s `all`: "the first item of the library").
    ///
    /// ⚠⚠ It is the only request in this app that exists PURELY to serve one fallback branch of one rule, and
    /// that is a deliberate, recorded cost (`HomeStore.load`'s note): the alternative was to let the TV pick a
    /// hero the phone would not pick, which is a second implementation of a rule rather than one extra call.
    /// ⚠ The route has no response_model in the api (`backend/api/routes/library.py`), so its shape comes from
    /// the frontend's own `LibraryItemsShape` — the same second source `LibraryItemsResponse` already uses.
    func libraryItems(correlation: CorrelationID = .next()) async throws -> LibraryItemsResponse {
        try await get("api/library/items", correlation: correlation)
    }

    /// `GET /api/library/folders/{id}/items` — ONE folder's poster wall.
    ///
    /// ⚠ The path is INTERPOLATED, and that is deliberate: `check-tvos-models.py` (R4) turns a literal with
    /// an interpolation into `.../folders/[^/]+/items` and requires it to match a real contract path
    /// exactly, so a typo in the static parts still fails the round. (Before B3 there was no parameterised
    /// endpoint in this app at all; `POST /api/jellyfin/hls/{id}/master.m3u8` arrives in Phase C and gets
    /// the same treatment.)
    func folderItems(folderID: String, correlation: CorrelationID = .next()) async throws -> FolderItemsResponse {
        try await get("api/library/folders/\(folderID)/items", correlation: correlation)
    }

    /// `GET /api/jellyfin/detail?id=` — ONE item's preplay metadata (Phase B4).
    ///
    /// ⚠⚠ **The path literal carries NO query string — the id travels as a real query item.** Two reasons
    /// and both bite: `appendingPathComponent(_:)` would escape the `?` into the path (see
    /// `Core/RequestURL.swift`), and R4 in `check-tvos-models.py` matches this literal against the
    /// contract's path list EXACTLY — `"api/jellyfin/detail?id="` would not match `/api/jellyfin/detail`.
    ///
    /// ⚠ The api answers **404** for an id it has no detail for, and that is a CONTENT answer, not a
    /// transport failure — `DetailStore` maps it to `DetailState.notFound` rather than to a network-error
    /// sentence.
    func itemDetail(itemID: String, correlation: CorrelationID = .next()) async throws -> ItemDetail {
        try await get("api/jellyfin/detail",
                      query: [URLQueryItem(name: "id", value: itemID)],
                      correlation: correlation)
    }

    /// `GET /api/library/series/{id}/episodes` — one series' episodes (Phase B4).
    ///
    /// ⚠ The second PARAMETERISED endpoint in this app; R4's pattern rule (B3) covers it. The server's order
    /// is preserved all the way to the screen — `DetailRules.groupBySeason` sorts the season NUMBERS and
    /// never the episodes inside a season.
    func seriesEpisodes(seriesID: String, correlation: CorrelationID = .next()) async throws -> EpisodesResponse {
        try await get("api/library/series/\(seriesID)/episodes", correlation: correlation)
    }
}

// ⚠ The failure COPY is not here. `RowFailureKind` and `HomeRowFailure` live in `HomeRails.swift` on
// purpose: this file imports `RKMServerKit` (for `CorrelationID`), which keeps it out of the file set
// `check-tvos-core.py` can COMPILE AND RUN — and a rule that cannot be executed is a rule that drifts. The
// five-line `APIError` → kind switch that needs this file's error type sits in `HomeStore`.
