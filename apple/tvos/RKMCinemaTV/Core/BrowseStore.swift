import Foundation
// ⚠ Combine, not SwiftUI — `ObservableObject`/`@Published` are Combine's (see `HomeStore`). The missing
// import is invisible to the Linux typecheck (TVStubs declares the protocol in the same module) and is
// caught by `check-imports.py`, which IS the gate that covers the views.
import Combine
import RKMServerKit

/// Browse's state: the library list, and ONE folder's wall.
///
/// ⚠ **The decisions live in `BrowseRules.swift` (pure, run, tested); this type only does I/O and error
/// classification** — the same split as `HomeStore`. Every rule the screen obeys is a value a test can build.
///
/// ⚠ `Foundation` + `Combine` + `RKMServerKit` only — no SwiftUI — so it compiles on Linux before a Mac round.
final class BrowseStore: ObservableObject {

    /// ⚠ Starts `loaded([])` — not failed. "Not asked yet" is not a failure (the `HomeStore` rule).
    @Published private(set) var folders: FoldersOutcome = .loaded([])
    @Published private(set) var isLoadingFolders = false
    @Published private(set) var hasLoadedFolders = false

    /// The folder currently open, or `nil` for the library list. ⚠ ONE folder at a time on purpose: a TV
    /// has no back stack in this phase, and a store that held two walls would be the beginning of one.
    @Published private(set) var openFolderID: String?

    @Published private(set) var wall: WallOutcome = .loaded([])
    @Published private(set) var isLoadingWall = false
    @Published private(set) var hasLoadedWall = false

    /// How many extra rows past the first paint have been mounted (`BrowseRules.Mount`). ⚠ A COUNT, not a
    /// list: the wall's items come from the server once and the screen decides how much of them to draw.
    @Published private(set) var mountedExtra = 0

    private let client: APIClient

    init(client: APIClient) {
        self.client = client
    }

    /// The libraries this profile may browse. Safe to call again (the screen's Retry).
    func loadFolders() async {
        isLoadingFolders = true
        defer { isLoadingFolders = false }
        let correlation = CorrelationID.next()
        do {
            let response = try await client.libraryFolders(correlation: correlation)
            let entries = BrowseRules.browseEntries(libraries: response.libraryRows,
                                                    serverFolders: response.folderRows)
            // ⚠ The config warnings are logged rather than rendered as a banner: on a TV the row's own
            // warning is where a person can act, and a second copy at the top is noise.
            for warning in response.warningRows {
                RKMLog.info("browse: config warning — \(warning)", category: .net, correlation: correlation)
            }
            RKMLog.info("browse: \(entries.count) library row(s) from "
                            + "\(response.libraryRows.count) configured + \(response.folderRows.count) server",
                        category: .net, correlation: correlation)
            folders = .loaded(entries)
        } catch let error as APIError {
            let message = HomeRowFailure.message(for: Self.kind(of: error))
            RKMLog.error("browse: folders FAILED — \(error.errorDescription ?? message)", category: .net,
                         correlation: correlation)
            folders = .failed(message)
        } catch {
            RKMLog.error("browse: folders FAILED — \(error)", category: .net, correlation: correlation)
            folders = .failed(HomeRowFailure.message(for: .unknown))
        }
        hasLoadedFolders = true
    }

    /// Open one folder's wall.
    func openFolder(_ folderID: String) async {
        openFolderID = folderID
        // ⚠ Reset the mounting state with the wall: an extra 96 carried over from a 400-title folder would
        // make the next folder paint in two goes for no reason.
        mountedExtra = 0
        wall = .loaded([])
        hasLoadedWall = false
        await loadWall()
    }

    /// Back to the library list. ⚠ The wall is CLEARED rather than kept: a TV has one screen, and rows for
    /// a folder nobody is looking at are rows the memory could be using for posters.
    func closeFolder() {
        openFolderID = nil
        wall = .loaded([])
        hasLoadedWall = false
        mountedExtra = 0
    }

    func loadWall() async {
        guard let folderID = openFolderID else { return }
        isLoadingWall = true
        defer { isLoadingWall = false }
        let correlation = CorrelationID.next()
        do {
            let response = try await client.folderItems(folderID: folderID, correlation: correlation)
            let items = BrowseRules.wallItems(response.rows)
            RKMLog.info("browse: folder \(folderID.prefix(8)) -> \(items.count) title(s)", category: .net,
                        correlation: correlation)
            wall = .loaded(items)
        } catch let error as APIError {
            let message = HomeRowFailure.message(for: Self.kind(of: error))
            RKMLog.error("browse: wall FAILED — \(error.errorDescription ?? message)", category: .net,
                         correlation: correlation)
            wall = .failed(message)
        } catch {
            RKMLog.error("browse: wall FAILED — \(error)", category: .net, correlation: correlation)
            wall = .failed(HomeRowFailure.message(for: .unknown))
        }
        hasLoadedWall = true
    }

    /// Mount the next step of the wall. ⚠ Called by an explicit control, not by scrolling: on tvOS the
    /// scroll position is the focus engine's business, and "grow when the last card is focused" needs a
    /// focus signal this phase does not have. A button is honest, focusable and obvious — automatic growth
    /// is Phase D polish, and this is the seam it will use.
    func mountMore() {
        let total = wall.items.count
        mountedExtra = BrowseRules.Mount.nextExtra(mountedExtra, total: total)
    }

    /// How many rows the wall should draw right now.
    var mountedCount: Int {
        BrowseRules.Mount.mountedCount(wall.items.count, extra: mountedExtra)
    }

    var canMountMore: Bool {
        BrowseRules.Mount.needsMore(shown: mountedCount, total: wall.items.count)
    }

    /// ⚠ The one place `APIError` becomes a `RowFailureKind` (see `HomeStore` for why it lives here and not
    /// in the pure file).
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
