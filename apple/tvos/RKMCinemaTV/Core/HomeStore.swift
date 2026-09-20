import Foundation
// ⚠ Combine, not SwiftUI — `ObservableObject`/`@Published` are Combine's and SwiftUI stopped re-exporting
// it with the iOS 26 SDK. The missing-import failure (`does not conform to protocol 'ObservableObject'`)
// is invisible to the Linux typecheck because `TVStubs.swift` declares the protocol in the same module —
// `check-imports.py` is the gate that catches it. Both gates, one blind spot each.
import Combine
import RKMServerKit

/// The Home's state: it fetches the screen's rows (five small requests — see `load`) and publishes what the
/// screen should be.
///
/// ⚠ **The screen's shape is decided in `HomeRails.swift` (pure, tested); this type only does I/O and
/// error classification.** That split is the whole point: what Home shows is a value a test can build,
/// and everything left here is a request and a `switch`.
///
/// ⚠ `Foundation` + `Combine` + `RKMServerKit` only — no SwiftUI — so it is compiled on Linux before a Mac
/// round is spent on it.
final class HomeStore: ObservableObject {

    /// ⚠ Starts at `HomeSnapshot.empty` — both rows *loaded and empty*, not *failed*. A screen that has not
    /// asked yet has no failure to report, and treating "not asked" as "failed" would flash an error
    /// sentence on every single launch before the first byte arrives.
    @Published private(set) var snapshot: HomeSnapshot = .empty

    /// True while the two requests are in flight. The view uses it for its spinner and nothing else.
    @Published private(set) var isLoading = false

    /// True once a load has produced an answer — so the view can tell "still the initial value" from
    /// "asked, and this is the answer".
    @Published private(set) var hasLoaded = false

    private let client: APIClient

    init(client: APIClient) {
        self.client = client
    }

    /// Fetch every row and publish the snapshot. Safe to call again (it is the screen's Retry).
    ///
    /// ⚠⚠ **FIVE SMALL REQUESTS, SEQUENTIALLY — and the fifth one is worth knowing about.** The Home's rails
    /// are Continue Watching and Recently Played; the top bar's tabs are `GET /api/library/folders`; the hero
    /// is picked from three lists (`GET /api/library`, `GET /api/library/items`) exactly as `useHomeRows`
    /// picks it on the web. So one screen = five round trips, where before U3 it was two.
    ///
    /// ⚠ **Sequential on purpose, and this is the Phase B2 note unchanged:** two requests could run
    /// concurrently and on a slow tailnet that would be faster — but `async let` here would put the store's
    /// `self` into child tasks, and the strict-concurrency diagnostics that follow depend on the language mode
    /// his Xcode picks, which cannot be reproduced from this sandbox. Five small calls in sequence is the
    /// version that cannot fail to build on the Mac for a reason nobody can see here. ⚠ If the round ever
    /// shows the Home slow to paint, THIS is the line to revisit — not the rails' rules.
    func load() async {
        isLoading = true
        defer { isLoading = false }

        let continueWatching = await row("continue-watching") { client in
            try await client.continueWatching().items
        }
        let recentlyPlayed = await row("recently-watched") { client in
            try await client.recentlyWatched().items
        }
        // ⚠ `GET /api/library` — the recently-added ordering. It makes the hero's SECOND TIER in U3 and the
        // third rail in U4; one fetch, both consumers.
        let libraryRecent = await row("library") { client in
            try await client.libraryRecent().recent
        }
        // ⚠ `GET /api/library/items` — the whole library, and it exists ONLY for `pickHomeHero`'s last tier
        // ("the first item of the library" when nothing is in progress and nothing is recent). A tenth of a
        // second on a LAN; recorded so the day somebody asks "why five?" the answer is on the line.
        let libraryItems = await row("library-items") { client in
            try await client.libraryItems().items
        }
        let nav = await navRow()

        snapshot = HomeSnapshot.make(continueWatching: continueWatching,
                                     recentlyPlayed: recentlyPlayed,
                                     nav: nav,
                                     libraryRecent: libraryRecent,
                                     libraryItems: libraryItems)
        hasLoaded = true
    }

    // MARK: - One row

    /// One request, turned into an outcome. ⚠ It never throws: a row's failure is a VALUE here, because
    /// the screen has to render the other row regardless.
    private func row(_ label: String,
                     _ call: (APIClient) async throws -> [MediaItem]) async -> RailOutcome {
        let correlation = CorrelationID.next()
        do {
            let items = try await call(client)
            RKMLog.info("home: \(label) loaded \(items.count) item(s)", category: .net,
                        correlation: correlation)
            return .loaded(items)
        } catch let error as APIError {
            let message = HomeRowFailure.message(for: Self.kind(of: error))
            // ⚠ Logged at error level with the server's own sentence, because a row that quietly did not
            // load is the state this whole type exists to stop being invisible.
            RKMLog.error("home: \(label) FAILED — \(error.errorDescription ?? message)", category: .net,
                         correlation: correlation)
            return .failed(message)
        } catch {
            RKMLog.error("home: \(label) FAILED — \(error)", category: .net, correlation: correlation)
            return .failed(HomeRowFailure.message(for: .unknown))
        }
    }

    /// The top bar's tabs — `GET /api/library/folders`, turned into navigation by the **same rule Browse
    /// uses**.
    ///
    /// ⚠⚠ **ONE RULE, ONE COPY.** `BrowseRules.browseEntries` is documented as the ONE place that decides what
    /// the library list contains (his iPad report of 2026-09-14 is why it exists). The top bar reads THAT and
    /// never a literal array — a second list here would be this repo's most-repeated defect, and the buildspec
    /// literally asks for one (`Home · Movies Kids · Movies · TV Shows · Watchlist · Discover · Suggest`),
    /// which is why the plan rejects it in writing.
    ///
    /// ⚠ It never throws: the tab row's failure is a VALUE like a rail's, because the rest of the screen has
    /// to render regardless.
    private func navRow() async -> NavOutcome {
        let correlation = CorrelationID.next()
        do {
            let response = try await client.libraryFolders(correlation: correlation)
            let entries = BrowseRules.browseEntries(libraries: response.libraryRows,
                                                    serverFolders: response.folderRows)
            RKMLog.info("home: \(entries.count) tab(s) from \(response.libraryRows.count) configured"
                            + " + \(response.folderRows.count) server", category: .net,
                        correlation: correlation)
            return .loaded(entries)
        } catch let error as APIError {
            let message = HomeRowFailure.message(for: Self.kind(of: error))
            RKMLog.error("home: tabs FAILED — \(error.errorDescription ?? message)", category: .net,
                         correlation: correlation)
            return .failed(message)
        } catch {
            RKMLog.error("home: tabs FAILED — \(error)", category: .net, correlation: correlation)
            return .failed(HomeRowFailure.message(for: .unknown))
        }
    }

    /// ⚠ The one place `APIError` becomes a `RowFailureKind`. Kept next to the row loop rather than in the
    /// pure file so that file stays free of `APIError` and can be run without a transport.
    private static func kind(of error: APIError) -> RowFailureKind {
        switch error {
        case .transport:
            return .transport
        case .decoding:
            return .decoding
        case .http(let status, _, _):
            switch status {
            case 401: return .unauthorized
            case 403: return .forbidden
            default: return .server(status)
            }
        }
    }
}
