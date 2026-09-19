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
}

// ⚠ The failure COPY is not here. `RowFailureKind` and `HomeRowFailure` live in `HomeRails.swift` on
// purpose: this file imports `RKMServerKit` (for `CorrelationID`), which keeps it out of the file set
// `check-tvos-core.py` can COMPILE AND RUN — and a rule that cannot be executed is a rule that drifts. The
// five-line `APIError` → kind switch that needs this file's error type sits in `HomeStore`.
