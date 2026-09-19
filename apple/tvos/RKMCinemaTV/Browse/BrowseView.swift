import SwiftUI
import RKMServerKit

/// Browse — the library screen. Phase B3's screen (screen #4 in the app's list), **redesigned in Phase V to
/// `tvos_ux/2. LibraryViewandItemDetailsView/library-view.html`**.
///
/// ⚠⚠ **TWO MODES, AND THEY ARE TWO DIFFERENT SCREENS.** With no folder open this is the LIBRARY LIST — every
/// library this profile may see, unresolved ones included and explaining themselves (`BrowseRules`' rule). With
/// a folder open it is the prototype's LIBRARY GRID: the filter row, then a wall of 2:3 posters.
///
/// ⚠ **The top bar is the app's own `Home/TopBar.swift`**, not a second bar: the prototype draws the same row
/// (wordmark + the library tabs) and the SAME WORDS ARE ON THE BACK BUTTON FROM HOME, so a second copy would be
/// two bars that drift. ⚠ Its tabs come from `BrowseRules.tabPlan` — **the ONE rule for which tabs exist and
/// which one is current**, extracted in this phase precisely so that this screen and the Home cannot disagree
/// (`TopBar`'s header warns about the literal list, and falsifier F3 of Phase U is what that risk is called).
///
/// ⚠ **Every decision this screen obeys is a PURE rule**: `BrowseRules` (which libraries exist, the wall's
/// mounting plan, the tab row) and `LibraryRules` (the genre chips, the filter, the eight sorts, the count line,
/// the grid's card width). Both are RUN on Linux. This type lays them out, and nothing else.
///
/// ⚠⚠ **NO FOCUS ARITHMETIC.** The spec asks for two things the platform already does — *"moving focus to a row
/// below the fold scrolls so it sits in the upper-middle third"* and *"filtering never moves focus off the
/// filter row"* — and its own JavaScript hand-rolls nearest-neighbour maths (lines 253-274) plus
/// `scrollIntoView`. **None of it is ported**: `RailFocus.swift` was written for exactly this and deleted, and
/// B3's grid got column memory for free. Falsifier **V-F4** is what settles it, and the fix, if it is needed,
/// belongs in this view one round later — not pre-emptively.
///
/// ⚠ **The filter state is the VIEW's, not the store's** (`@State`): it is a way of LOOKING at the wall, and the
/// wall itself is the server's. It resets with the screen, which is right — a genre filter from a different
/// library would hide rows for no visible reason. ⚠ The web app keeps it in the URL instead
/// (`?genre=&sort=`), because a browser has a Back button and a refresh; a TV has neither.
struct BrowseView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var store: BrowseStore
    let base: URL

    /// The active genre, or `""` for all of them. ⚠ `LibraryRules` owns every question asked of it.
    @State private var genre = ""
    @State private var sort: LibrarySortKey = LibraryRules.defaultSort

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            topBar

            Group {
                if let folderID = store.openFolderID {
                    wall(folderID: folderID)
                } else {
                    libraryList
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .task {
            // ⚠ Only once per question, the same rule as the Home: `.task` re-runs on re-appearance, and
            // neither list changes while the app is on screen.
            if !store.hasLoadedFolders {
                await store.loadFolders()
            }
            // ⚠ A folder can be open WITHOUT its wall having loaded — the top bar opens a library straight
            // from the Home (`AppModel.openLibrary`), which sets `phase` and starts the load, but a screen
            // that came back from the detail screen would otherwise sit on an empty wall that never asks.
            if store.openFolderID != nil, !store.hasLoadedWall {
                await store.loadWall()
            }
        }
    }

    // MARK: - The top bar

    private var topBar: some View {
        TopBar(tabs: tabs,
               initials: ProfileRules.initials(app.session?.currentProfile?.name ?? ""),
               // ⚠ `failedMessage` and not a bare failure flag: a list that failed and a profile with no
               // libraries look identical on screen, and only one of them is worth a Retry.
               failure: store.folders.failedMessage,
               onProfile: { Task { await app.changeProfile() } })
    }

    /// ⚠ Every decision here is `BrowseRules.tabPlan`'s; this only attaches the closures. The current tab is
    /// the OPEN FOLDER when there is one, and `Browse` when there is not.
    private var tabs: [TopBarTab] {
        // ⚠ Fully qualified inside `map`: the closure's result type is not otherwise pinned, and
        // `map { .folder($0) }` is the shape that makes the compiler ask for a contextual type it does not
        // have. The annotation pins the `??`; the explicit case pins the closure.
        let current: BrowseRules.LibraryTabTarget =
            store.openFolderID.map { BrowseRules.LibraryTabTarget.folder($0) } ?? .browse
        return BrowseRules.tabPlan(entries: store.folders.entries, current: current).map { plan in
            TopBarTab(id: plan.id,
                      title: plan.title,
                      isCurrent: plan.isCurrent,
                      isEnabled: plan.isEnabled,
                      warning: plan.warning,
                      action: { open(plan) })
        }
    }

    private func open(_ plan: BrowseRules.LibraryTabPlan) {
        switch plan.kind {
        case .home:
            app.showHome()
        case .browse:
            app.showBrowse()
        case .library:
            // ⚠ An unresolved library is `.disabled` in the bar (`isEnabled`), so this is only ever reached
            // with a real folder — the fallback keeps the branch total rather than force-unwrapping.
            if let folderID = plan.folderID {
                app.openLibrary(folderID: folderID)
            } else {
                app.showBrowse()
            }
        }
    }

    private var openFolderName: String {
        store.folders.entries.first { $0.folderID == store.openFolderID }?.name ?? "this library"
    }

    // MARK: - The library list

    @ViewBuilder
    private var libraryList: some View {
        if !store.hasLoadedFolders && store.isLoadingFolders {
            message("Loading your libraries…", "", retry: false)
        } else if let failure = store.folders.failedMessage {
            message("Couldn't load your libraries", failure, retry: true)
        } else if store.folders.entries.isEmpty {
            message("No libraries yet",
                    "No library is configured on the server, and it exposes no folders to this profile.",
                    retry: true)
        } else {
            ScrollView(.vertical, showsIndicators: false) {
                // ⚠ A `LazyVStack` rather than a `VStack`: a profile with many libraries should not build
                // every row to show six.
                LazyVStack(alignment: .leading, spacing: TVTokens.Grid.chipGap) {
                    ForEach(store.folders.entries) { entry in
                        libraryRow(entry)
                    }
                }
                .padding(.horizontal, LibraryRules.marginFromPrototype)
                .padding(.vertical, TVTokens.Grid.filterBottomPad)
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
                        .foregroundStyle(RKMColour.warning)
                        .lineLimit(2)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 16)
            .frame(maxWidth: 1400, alignment: .leading)
        }
        // ⚠ An unresolved library stays VISIBLE and is simply not openable — `.disabled` on tvOS also takes
        // it out of the focus chain, which is right: there is nothing to press.
        .disabled(!entry.isOpenable)
        .buttonStyle(.bordered)
    }

    // MARK: - One folder: the prototype's grid

    @ViewBuilder
    private func wall(folderID: String) -> some View {
        if !store.hasLoadedWall && store.isLoadingWall {
            skeletonGrid
        } else if let failure = store.wall.failedMessage {
            message("Couldn't load this library", failure, retry: true)
        } else if store.wall.items.isEmpty {
            // ⚠ A real answer, not a fault: an empty library is a library with nothing scanned into it yet.
            message(LibraryCopy.emptyTitle(""), LibraryCopy.emptyBody("", library: openFolderName), retry: false)
        } else {
            grid
        }
    }

    /// ⚠⚠ **THE FILTERED LIST IS DERIVED, NOT STORED, and the MOUNTING CAP still applies to it.** The server's
    /// list is held once (`store.wall.items`) and `BrowseRules.Mount` decides how much of it is DRAWN — a
    /// 713-title folder must not mount in one commit. ⚠ The cap is applied to the FILTERED rows, so a genre
    /// that matches 20 titles draws all 20 even on a wall whose first paint is 48.
    private var grid: some View {
        let items = store.wall.items
        let shown = LibraryRules.filter(items, genre: genre, sort: sort)

        return VStack(alignment: .leading, spacing: 0) {
            filterRow(total: items.count, shown: shown.count)

            // ⚠ The card's width is the grid's arithmetic and it needs the container's own width, so the
            // measuring happens here and the RESULT is handed to every card — one calculation, six columns,
            // and no card measuring itself (`LibraryRules.cardWidth` is RUN in the gate set).
            GeometryReader { geometry in
                let cardWidth = LibraryRules.cardWidth(containerWidth: geometry.size.width)

                ScrollView(.vertical, showsIndicators: false) {
                    VStack(alignment: .leading, spacing: TVTokens.Grid.gridTitleGap) {
                        Text(gridTitle)
                            .font(.system(size: TVTokens.Grid.gridTitleSize))
                            .foregroundStyle(RKMColour.secondary)

                        if shown.isEmpty {
                            emptyState
                        } else {
                            gridRows(shown, cardWidth: cardWidth)

                            if store.canMountMore {
                                Button("Load more titles") { store.mountMore() }
                                    .font(.system(size: TVTokens.Grid.emptyBodySize))
                                    .padding(.top, TVTokens.Grid.filterBottomPad)
                            }
                        }
                    }
                    .padding(.horizontal, LibraryRules.marginFromPrototype)
                    .padding(.bottom, TVTokens.Grid.gridBottomPad)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }

    /// `.grid { grid-template-columns: repeat(6, 1fr) }` — a FIXED six, which is also what gives the focus
    /// engine its column memory (the `.adaptive(minimum:)` this screen used before Phase V would re-flow the
    /// wall with the window width).
    private func gridRows(_ items: [MediaItem], cardWidth: CGFloat) -> some View {
        LazyVGrid(columns: gridColumns(cardWidth),
                  alignment: .leading,
                  spacing: TVTokens.Grid.rowGap) {
            ForEach(items.prefix(store.mountedCount)) { item in
                // ⚠ An explicit closure rather than `onSelect: open`: `open` is OVERLOADED on this screen
                // (a folder tab and an item), and passing an overloaded function as a value makes the
                // compiler infer a type it does not need to. This is the one place a round would find it.
                LibraryGridCard(item: item, base: base, width: cardWidth, onSelect: { open($0) })
            }
        }
    }

    private func gridColumns(_ cardWidth: CGFloat) -> [GridItem] {
        Array(repeating: GridItem(.fixed(cardWidth), spacing: TVTokens.Grid.columnGap),
              count: TVTokens.Grid.columns)
    }

    /// ⚠ `.grid-title { font-size:15px }` reads `Recently added` at rest and then **the genre's name** —
    /// `lib.ts::filterLibraryItems`' own behaviour, so the grid always says what it is showing.
    private var gridTitle: String {
        genre.trimmingCharacters(in: .whitespaces).isEmpty ? "Recently added" : genre
    }

    // MARK: - The filter row

    /// `.filterbar`: the chips scroll horizontally, the count sits hard right (`margin-left:auto`).
    ///
    /// ⚠ The chips are `All` plus **this library's own genres** (`LibraryRules.genres`), never the
    /// prototype's fixed fourteen — a chip no title in this folder carries would filter to the empty state on
    /// the first press. ⚠ The SORT control rides at the end of the same row and is deliberately NOT in the
    /// prototype's fixed list either: it offers the web app's eight sorts, and **no Rating**, because list
    /// items carry no rating (`LibraryRules`' header has the measurement).
    private func filterRow(total: Int, shown: Int) -> some View {
        HStack(spacing: TVTokens.Grid.countLeadIn) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: TVTokens.Grid.chipGap) {
                    ForEach(LibraryRules.chipTitles(genres: LibraryRules.genres(store.wall.items)), id: \.self) { chip in
                        FilterChip(title: chip,
                                   isSelected: LibraryRules.isSelected(chip: chip, genre: genre)) {
                            genre = LibraryRules.genre(forChip: chip)
                        }
                    }

                    // ⚠ One press = the next order. The prototype gives its sort control no markup at all
                    // (only the chips and the count are injected by its JavaScript), so the interaction is
                    // the app's — and the rule that decides WHICH order comes next is `LibraryRules.nextSort`,
                    // which wraps rather than stopping on the last one.
                    FilterChip(title: LibraryCopy.sortControl(LibraryRules.sortLabel(sort)),
                               isSelected: sort != LibraryRules.defaultSort) {
                        sort = LibraryRules.nextSort(after: sort)
                    }
                }
                .padding(.vertical, TVTokens.Grid.gridTopPad)
            }

            Text(LibraryRules.countLabel(shown: shown, total: total, genre: genre))
                .font(.system(size: TVTokens.Grid.countSize))
                .foregroundStyle(RKMColour.secondary)
                .lineLimit(1)
        }
        .padding(.horizontal, LibraryRules.marginFromPrototype)
        .padding(.bottom, TVTokens.Grid.filterBottomPad)
    }

    // MARK: - The empty result

    /// `LibraryFolderView.tsx`'s *"never a blank screen with nothing to land on"*, and the prototype's own
    /// `.empty-state`: a sentence, and **a focused way out of the state** — `Clear filter`.
    private var emptyState: some View {
        VStack(alignment: .leading, spacing: TVTokens.Grid.emptyGap) {
            Text(LibraryCopy.emptyTitle(genre))
                .font(.system(size: TVTokens.Grid.emptyTitleSize, weight: .semibold))
            Text(LibraryCopy.emptyBody(genre, library: openFolderName))
                .font(.system(size: TVTokens.Grid.emptyBodySize))
                .foregroundStyle(RKMColour.secondary)
            FilterChip(title: LibraryCopy.clearFilter, isSelected: false) { genre = "" }
        }
        .padding(.vertical, TVTokens.Grid.emptyPaddingV)
    }

    // MARK: - Loading

    /// The spec's own loading state: *"skeleton cards (flat surface-coloured blocks, **no shimmer animation**
    /// — motion is reserved for focus, per principle §4) in the exact grid position real posters will occupy,
    /// so layout never jumps."*
    ///
    /// ⚠ "The exact grid position" is why this shares `LibraryRules.cardWidth` and the same column count with
    /// the real grid: a skeleton laid out by its own arithmetic is a layout that jumps the moment the posters
    /// land, which is the one thing the state exists to prevent.
    private var skeletonGrid: some View {
        GeometryReader { geometry in
            let cardWidth = LibraryRules.cardWidth(containerWidth: geometry.size.width)

            ScrollView(.vertical, showsIndicators: false) {
                LazyVGrid(columns: gridColumns(cardWidth),
                          alignment: .leading,
                          spacing: TVTokens.Grid.rowGap) {
                    ForEach(0..<(TVTokens.Grid.columns * 2), id: \.self) { _ in
                        RoundedRectangle(cornerRadius: TVTokens.Grid.cardRadius, style: .continuous)
                            .fill(RKMColour.surface2)
                            .frame(width: cardWidth, height: cardWidth * TVTokens.Grid.cardAspect)
                    }
                }
                .padding(.horizontal, LibraryRules.marginFromPrototype)
                .padding(.vertical, TVTokens.Grid.filterBottomPad)
            }
        }
    }

    // MARK: - Shared

    /// ⚠ **A focusable way forward, always** (the Home rule): even the "nothing here" copy carries a control the
    /// remote can reach, so no state on this screen is a dead end.
    private func message(_ title: String, _ sub: String, retry: Bool) -> some View {
        VStack(alignment: .leading, spacing: TVTokens.Grid.emptyGap) {
            Text(title)
                .font(.system(size: TVTokens.Grid.emptyTitleSize, weight: .semibold))
            if !sub.isEmpty {
                Text(sub)
                    .font(.system(size: TVTokens.Grid.emptyBodySize))
                    .foregroundStyle(RKMColour.secondary)
            }
            HStack(spacing: TVTokens.Grid.chipGap) {
                if retry {
                    Button("Try again") { Task { await retryLoad() } }
                        .buttonStyle(.borderedProminent)
                }
                Button("Back to Home") { app.showHome() }
            }
            .font(.system(size: TVTokens.Grid.emptyBodySize))
            .padding(.top, TVTokens.Grid.gridTopPad)
        }
        .padding(.horizontal, LibraryRules.marginFromPrototype)
        .padding(.vertical, TVTokens.Grid.emptyPaddingV)
        .buttonStyle(.bordered)
    }

    /// ⚠ Which list to re-ask for is the STORE's state, not this screen's: a folder is open or it is not.
    private func retryLoad() async {
        if store.openFolderID != nil {
            await store.loadWall()
        } else {
            await store.loadFolders()
        }
    }

    /// ⚠ **Select opens the detail screen** (B4). A real Button whose press does nothing visible reads as a
    /// broken remote, so this goes where it says.
    private func open(_ item: MediaItem) {
        app.openDetail(itemID: item.itemID)
    }
}
