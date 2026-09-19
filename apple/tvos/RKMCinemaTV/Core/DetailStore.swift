import Foundation
// ⚠ Combine, not SwiftUI — `ObservableObject`/`@Published` are Combine's (see `HomeStore`). The missing
// import is invisible to the Linux typecheck (TVStubs declares the protocol in the same module) and is
// caught by `check-imports.py`, which IS the gate that covers the views.
import Combine
import RKMServerKit

/// ONE item's detail screen's state: the detail payload, plus the episode list when the item is a series.
///
/// ⚠ **The decisions live in `DetailRules.swift` (pure, run, tested); this type only does I/O and error
/// classification** — the same split as `HomeStore` and `BrowseStore`.
///
/// ⚠⚠ **ONE STORE PER ITEM, BUILT WHEN THE ITEM IS OPENED, DROPPED WHEN IT IS LEFT.** On
/// `AppModel.openDetail` it is constructed with the item id; there is no "load a different item into the
/// same store". A store that could change which item it holds is a store that can show the previous
/// title's synopsis under the current title's poster while the new bytes are in flight — and on a TV
/// nobody can tell which of the two is stale.
///
/// ⚠ `Foundation` + `Combine` + `RKMServerKit` only — no SwiftUI — so it compiles on Linux before a Mac
/// round is spent on it.
final class DetailStore: ObservableObject {

    /// ⚠ Starts `.loading`, not `.failed`: the screen is opened *in order to* fetch, so "not asked yet" and
    /// "being asked" are the same moment here. (The Home's rule — "not asked is not failed" — still holds;
    /// this is the other side of it.)
    @Published private(set) var state: DetailState = .loading

    let itemID: String
    private let client: APIClient

    init(client: APIClient, itemID: String) {
        self.client = client
        self.itemID = itemID
    }

    /// Fetch the detail — and, for a series, the episode list. Safe to call again (the screen's Retry).
    ///
    /// ⚠ **Sequential on purpose, like `HomeStore`.** The episodes request needs the detail's `type` to
    /// know whether to happen at all, so there is nothing to parallelise — and two `async let`s would put
    /// `self` into child tasks whose strict-concurrency diagnostics depend on the language mode his Xcode
    /// picks, which cannot be reproduced in this sandbox.
    func load() async {
        state = .loading
        let correlation = CorrelationID.next()
        do {
            let detail = try await client.itemDetail(itemID: itemID, correlation: correlation)

            var episodes: [EpisodeItem] = []
            var episodesFailed = false
            if DetailRules.isSeries(detail) {
                do {
                    episodes = try await client.seriesEpisodes(seriesID: detail.itemID,
                                                              correlation: correlation).episodes
                } catch {
                    // ⚠ A series whose EPISODE LIST failed is the PARTIAL case, not a dead screen: the
                    // synopsis, the ratings and the cast all arrived, and the plan's own sentence for this
                    // is `DetailCopy.partialWarning`. It is a value on the snapshot, never an exception
                    // thrown away — a series that silently shows no episodes looks like a series with none.
                    episodesFailed = true
                    RKMLog.error("detail: episodes FAILED for series \(Self.short(detail.itemID)) — \(error)",
                                 category: .net, correlation: correlation)
                }
            }

            RKMLog.info("detail \(Self.short(itemID)) -> \(detail.type), \(episodes.count) episode(s)"
                            + (episodesFailed ? " (episodes FAILED)" : ""),
                        category: .net, correlation: correlation)
            state = .content(DetailSnapshot(detail: detail, episodes: episodes,
                                            episodesFailed: episodesFailed))
        } catch let error as APIError {
            // ⚠⚠ A 404 IS A CONTENT ANSWER, NOT A TRANSPORT FAILURE. `jellyfin_detail.py` answers 404 for
            // an id it has no detail for ("No detail for item"), and the web turns exactly that into
            // "We couldn't find that title in the library" — a sentence about the LIBRARY, because the
            // server is answering fine. Rendering it as "couldn't reach the server" would send the viewer
            // to check a connection that is working.
            if case .http(let status, _, _) = error, status == 404 {
                RKMLog.error("detail \(Self.short(itemID)) -> 404 (the server has no detail for this id)",
                             category: .net, correlation: correlation)
                state = .notFound
                return
            }
            let message = HomeRowFailure.message(for: Self.kind(of: error))
            RKMLog.error("detail \(Self.short(itemID)) FAILED — \(error.errorDescription ?? message)",
                         category: .net, correlation: correlation)
            state = .failed(message)
        } catch {
            RKMLog.error("detail \(Self.short(itemID)) FAILED — \(error)", category: .net, correlation: correlation)
            state = .failed(HomeRowFailure.message(for: .unknown))
        }
    }

    /// ⚠ The first 8 characters only, the same rule `PosterLoader` applies: a Jellyfin id is 32 hex
    /// characters, and a HUD line holds one status, not two ids.
    private static func short(_ itemID: String) -> String {
        String(itemID.prefix(8))
    }

    /// ⚠ The one place `APIError` becomes a `RowFailureKind` — the same five-line mapping the two other
    /// stores carry. It is deliberately duplicated rather than "shared": the alternative is a free function
    /// in a file that would then have to import `APIError` (i.e. `RKMServerKit`), which is what keeps
    /// `HomeRails.swift`'s sentences runnable on Linux.
    private static func kind(of error: APIError) -> RowFailureKind {
        switch error {
        case .transport: return .transport
        case .decoding: return .decoding
        case .http(let status, _, _):
            switch status {
            case 401: return .unauthorized
            case 403: return .forbidden
            default: return .server(status)
            }
        }
    }
}
