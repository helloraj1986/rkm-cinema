import SwiftUI
import RKMServerKit

/// Browse — the library list, and one folder's poster wall. Phase B3's screen (screen #4 in the app's list).
///
/// ⚠ **THE WAYS OUT STAY, on both modes.** A TV screen with no focusable exit is a dead end, and a dead end
/// on a TV is a phone call — so `Home` (back), `Change profile`, `Sign out` and `Change server` are on this
/// screen exactly as they are on Home.
///
/// ⚠ **Every decision this screen obeys is in `BrowseRules.swift`** (which libraries exist, whether an
/// unresolved one is shown, how long a wall is, how much of it to draw). This type lays that out.
///
/// ⚠⚠ **THE GRID'S 2-D FOCUS IS THE PLATFORM'S, DELIBERATELY.** The plan expected the grid to need hand-rolled
/// row/column memory; a `LazyVGrid` of focusable `Button`s gets column memory and reveal-scrolling from the
/// tvOS focus engine, and a second implementation would fight it — the same finding as B2's deleted
/// `RailFocus`, and it is written up in `BrowseRules`'s header with the falsifier for the round.
struct BrowseView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var store: BrowseStore
    let base: URL

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header

            Group {
                if let folderID = store.openFolderID {
                    wall(folderID: folderID)
                } else {
                    libraryList
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

            footer
        }
        .task {
            // ⚠ Only once: `.task` re-runs on re-appearance, and the library list does not change while the
            // app is on screen. `Refresh` is the explicit way to re-ask.
            if !store.hasLoadedFolders {
                await store.loadFolders()
            }
        }
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(store.openFolderID == nil ? "Browse" : openFolderName)
                .font(.system(size: 44, weight: .bold))

            HStack(spacing: 18) {
                if store.openFolderID != nil {
                    Button("Libraries") { store.closeFolder() }
                }
                Button("Home") { app.showHome() }
                Button("Change profile") { Task { await app.changeProfile() } }
                Button("Sign out") { Task { await app.signOut() } }
                Button("Change server") { app.changeServer() }
                if store.openFolderID == nil {
                    Button("Refresh") { Task { await store.loadFolders() } }
                }
            }
            .font(.system(size: 22))
        }
        .padding(.horizontal, 60)
        .padding(.top, 44)
        .padding(.bottom, 10)
        .buttonStyle(.bordered)
    }

    private var openFolderName: String {
        store.folders.entries.first { $0.folderID == store.openFolderID }?.name ?? "Library"
    }

    // MARK: - The library list

    @ViewBuilder
    private var libraryList: some View {
        if !store.hasLoadedFolders && store.isLoadingFolders {
            message("Loading your libraries…", "")
        } else if let failure = store.folders.failedMessage {
            message("Couldn't load your libraries", failure)
        } else if store.folders.entries.isEmpty {
            message("No libraries yet",
                    "No library is configured on the server, and it exposes no folders to this profile.")
        } else {
            ScrollView(.vertical, showsIndicators: false) {
                // ⚠ A `LazyVStack` rather than a `VStack`: a profile with many libraries should not build
                // every row to show six.
                LazyVStack(alignment: .leading, spacing: 18) {
                    ForEach(store.folders.entries) { entry in
                        libraryRow(entry)
                    }
                }
                .padding(.horizontal, 60)
                .padding(.vertical, 20)
            }
        }
    }

    private func libraryRow(_ entry: LibraryNavEntry) -> some View {
        Button {
            if let folderID = entry.folderID {
                Task { await store.openFolder(folderID) }
            }
        } label: {
            HStack(spacing: 22) {
                // ⚠ `LibraryIcon.systemImage` — the ONE mapping, shared with the Home's card badge (U3).
                // It used to be a private function here, which is how the two would have drifted.
                Image(systemName: entry.icon.systemImage)
                    .font(.system(size: 30))
                    .frame(width: 44)
                Text(entry.name)
                    .font(.system(size: 30, weight: .medium))
                if !entry.warning.isEmpty {
                    // ⚠ The warning is RENDERED, not a focus-only tooltip: on a TV a viewer may never focus
                    // this row, and the whole point of `libraryNavEntries` is that an unusable library
                    // explains itself rather than disappearing.
                    Text(entry.warning)
                        .font(.system(size: 20))
                        .foregroundStyle(.orange)
                        .lineLimit(2)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 16)
            .frame(maxWidth: 1400, alignment: .leading)
        }
        // ⚠ An unresolved library stays VISIBLE and is simply not openable — `.disabled` on tvOS also takes
        // it out of the focus chain, which is right: there is nothing to press. It is not hidden, which is
        // the failure the rule exists to prevent.
        .disabled(!entry.isOpenable)
        .buttonStyle(.bordered)
    }

    // MARK: - One folder's wall

    @ViewBuilder
    private func wall(folderID: String) -> some View {
        if !store.hasLoadedWall && store.isLoadingWall {
            message("Loading \(openFolderName)…", "")
        } else if let failure = store.wall.failedMessage {
            message("Couldn't load this library", failure)
        } else if store.wall.items.isEmpty {
            // ⚠ A real answer, not a fault: an empty library is a library with nothing scanned into it yet.
            message("Nothing in \(openFolderName) yet",
                    "Titles appear here once the media server has scanned them.")
        } else {
            VStack(alignment: .leading, spacing: 10) {
                Text(BrowseRules.folderCountLabel(store.wall.items.count))
                    .font(.system(size: 24))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 60)

                ScrollView(.vertical, showsIndicators: false) {
                    // ⚠ `prefix(mountedCount)` is the whole mounting rule: the server's list is held once and
                    // this is how much of it is DRAWN. On a 400-title wall that is the difference between a
                    // grid that paints and a grid that stalls.
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 28)],
                              alignment: .leading,
                              spacing: 44) {
                        ForEach(store.wall.items.prefix(store.mountedCount)) { item in
                            PosterCard(item: item, base: base, onSelect: open)
                        }
                    }
                    .padding(.horizontal, 60)
                    .padding(.vertical, 26)

                    if store.canMountMore {
                        Button("Load more titles") { store.mountMore() }
                            .font(.system(size: 22))
                            .padding(.bottom, 40)
                    }
                }
            }
        }
    }

    // MARK: - Shared

    private func message(_ title: String, _ sub: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title)
                .font(.system(size: 36, weight: .semibold))
            if !sub.isEmpty {
                Text(sub)
                    .font(.system(size: 24))
                    .foregroundStyle(.secondary)
            }
            // ⚠ A focusable way forward, always (the Home rule): even the "nothing here" copy has a control
            // the remote can reach, so no state on this screen is a dead end.
            Button("Back to Home") { app.showHome() }
                .font(.system(size: 22))
                .padding(.top, 6)
        }
        .padding(60)
        .buttonStyle(.borderedProminent)
    }

    @ViewBuilder
    private var footer: some View {
        if !store.folders.entries.isEmpty, store.openFolderID == nil {
            Text("Choose a library")
                .font(.system(size: 20))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 60)
                .padding(.bottom, 30)
        }
    }

    /// ⚠ **The detail screen is B4, so Select opens it.** Until B4 this logged instead — a real Button whose
    /// press does nothing visible reads as a broken remote, so it said so; now it goes where it says.
    private func open(_ item: MediaItem) {
        app.openDetail(itemID: item.itemID)
    }
}
