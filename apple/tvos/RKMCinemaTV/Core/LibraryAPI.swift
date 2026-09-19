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
    func libraryFolders(correlation: CorrelationID = .next()) async throws -> LibrariesResponse {
        try await get("api/library/folders", correlation: correlation)
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
}

// ⚠ The failure COPY is not here. `RowFailureKind` and `HomeRowFailure` live in `HomeRails.swift` on
// purpose: this file imports `RKMServerKit` (for `CorrelationID`), which keeps it out of the file set
// `check-tvos-core.py` can COMPILE AND RUN — and a rule that cannot be executed is a rule that drifts. The
// five-line `APIError` → kind switch that needs this file's error type sits in `HomeStore`.
