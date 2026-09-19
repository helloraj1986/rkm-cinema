import Foundation
// ⚠ Combine, not SwiftUI — `ObservableObject`/`@Published` are Combine's and SwiftUI stopped re-exporting
// it with the iOS 26 SDK. The missing-import failure (`does not conform to protocol 'ObservableObject'`)
// is invisible to the Linux typecheck because `TVStubs.swift` declares the protocol in the same module —
// `check-imports.py` is the gate that catches it. Both gates, one blind spot each.
import Combine
import RKMServerKit

/// The Home's state: it fetches two rows and publishes what the screen should be.
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

    /// Fetch both rows and publish the snapshot. Safe to call again (it is the screen's Retry).
    ///
    /// ⚠ **Sequential on purpose.** Two requests could run concurrently, and on a slow tailnet that would
    /// be marginally faster — but `async let` here would put the store's `self` into two child tasks, and
    /// the strict-concurrency diagnostics that follow depend on the language mode his Xcode picks, which
    /// cannot be reproduced from this sandbox. Two small calls in sequence is the version that cannot fail
    /// to build on the Mac for a reason nobody can see here.
    func load() async {
        isLoading = true
        defer { isLoading = false }

        let continueWatching = await row("continue-watching") { client in
            try await client.continueWatching().items
        }
        let recentlyPlayed = await row("recently-watched") { client in
            try await client.recentlyWatched().items
        }

        snapshot = HomeSnapshot.make(continueWatching: continueWatching,
                                    recentlyPlayed: recentlyPlayed)
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
