import Foundation

// The tvOS Browse screen's RULES — pure, so they are RUN on Linux (`apple/scripts/check-tvos-core.py`)
// rather than discovered on a TV.
//
// ⚠⚠ **MIRRORED FROM THE WEB APP, NOT INVENTED.** Sources named at each rule:
// `frontend/src/features/library/lib.ts` (`libraryIconFor`, `libraryByFolderId`, `libraryNavEntries`,
// `folderCountLabel`, and the mounting constants), which is what the sidebar ✓, the phone's library bar ✓
// and the folder page ✓ already render from. A TV that decides differently is a second product.
//
// ⚠⚠ **WHAT IS *NOT* HERE, DELIBERATELY — the 2-D focus grid itself.** The plan said the grid "needs
// row/column memory so moving down from the middle of a row stays in the same column". That was checked
// against how tvOS actually works, and it is the same finding as B2's `RailFocus`: **a `LazyVGrid` of
// focusable `Button`s gets column memory and reveal-scrolling from the platform's focus engine for free**,
// and hand-rolling it would fight the engine. What the app DOES have to own is **how much it draws** —
// which is exactly what `libraryMountPlan` below is, and it is a real cost on a 140-title folder.
// ⚠ This is a claim about the platform that could NOT be exercised from the sandbox; the round is what
// settles it. Falsifier: if the grid loses its column when moving down a row, that is a real defect and the
// fix goes in the view (a `@FocusState` + index map), not in this file.

/// `lib.ts::libraryIconFor` — the icon a library's row shows, from its server collection type.
enum LibraryIcon: String, Equatable {
    case film
    case tv
    case folder

    /// ⚠ Anything unrecognised becomes a folder rather than nothing: an icon is a hint, and a missing one
    /// must not make a library look broken.
    static func forCollectionType(_ collectionType: String) -> LibraryIcon {
        switch collectionType.lowercased() {
        case "movies": return .film
        case "tvshows", "tv": return .tv
        default: return .folder
        }
    }

    /// The SF Symbol a screen draws for this icon.
    ///
    /// ⚠ **ONE RULE, ONE PLACE, and it was moved here in U3 for that reason.** `BrowseView` had this mapping
    /// as a private function, and the Home's poster badge needed the same three names — a second switch would
    /// have been this repo's most-repeated defect (and a `String`, so it stays in the Foundation-only file and
    /// can still be checked on Linux without SwiftUI).
    var systemImage: String {
        switch self {
        case .film: return "film"
        case .tv: return "tv"
        case .folder: return "folder"
        }
    }
}

/// `lib.ts::LibraryNavEntry` — one library, ready to render as navigation.
struct LibraryNavEntry: Identifiable, Equatable {
    /// Stable identity: the resolved folder, or the NAME for an unresolved library (`lib.ts::key`).
    let id: String
    let name: String
    let icon: LibraryIcon
    /// The folder this row opens, or `nil` when the server could not resolve it.
    let folderID: String?
    /// Why it is unavailable — shown on the row, never hidden.
    let warning: String

    var isOpenable: Bool { folderID != nil }
}

enum BrowseRules {

    // ---------------------------------------------------------------- the library list

    /// `lib.ts::libraryByFolderId` — the library a folder belongs to, for the folder's own title.
    static func libraryByFolderID(_ libraries: [ConfiguredLibrary], folderID: String?) -> ConfiguredLibrary? {
        guard let folderID, !folderID.isEmpty else { return nil }
        return libraries.first { $0.folderID == folderID }
    }

    /// `lib.ts::libraryNavEntries` — **the ONE place that decides what the Browse list contains.**
    ///
    /// ⚠⚠ **THE RULE THIS MIRRORS WAS PAID FOR, AND THE TV MUST NOT RE-BREAK IT.** His iPad report,
    /// 2026-09-14:
    ///
    /// > *"even though raj profile have access to all three libraries..only two can be seen at the
    /// > bottom… the ui needs a bit of work to make sure all the libraries are accessible"*
    ///
    /// The desktop sidebar listed **every** library and greyed the unresolved ones; the mobile bar applied
    /// `ok && folder_id` and therefore **dropped** them — so a library with a stale path was explained on a
    /// big screen and *silently absent* on a phone. **An unresolved library keeps its row, its icon and its
    /// warning, on every surface.** A TV is not a place to find out your library "disappeared", so this is
    /// one rule, one copy, and it is the reachable-by-design half of the server's own enforcement
    /// (`docs/ARCHITECTURE.md` §11: never OFFER what the server will refuse — and never hide what it allows).
    static func libraryNavEntries(_ libraries: [ConfiguredLibrary]?) -> [LibraryNavEntry] {
        (libraries ?? []).map { lib in
            let resolved = lib.ok && !(lib.folderID ?? "").isEmpty
            let folderID = resolved ? lib.folderID : nil
            return LibraryNavEntry(
                id: resolved ? "folder:\(folderID ?? "")" : "unresolved:\(lib.name)",
                name: lib.name,
                icon: LibraryIcon.forCollectionType(lib.collectionType),
                folderID: folderID,
                warning: lib.warning.isEmpty ? "Library unavailable" : lib.warning
            )
        }
    }

    /// ⚠ **The server's own folders are the fallback ONLY when there are no configured libraries at all**,
    /// and that is new for tvOS — recorded rather than assumed. `LibrariesResponse` carries both lists
    /// (`libraries` = the `.env`-configured ones, `folders` = what the media server exposes), and the web
    /// sidebar always renders the configured ones. On a TV there is no `.env` to go and check, so an
    /// unconfigured server would otherwise Browse to an empty screen with no explanation; the server's
    /// folders are then the honest thing to show. When libraries ARE configured (his server has them) this
    /// branch never runs, so the TV and the phone cannot disagree today.
    static func browseEntries(libraries: [ConfiguredLibrary]?, serverFolders: [LibraryFolder]?) -> [LibraryNavEntry] {
        let configured = libraryNavEntries(libraries)
        if !configured.isEmpty { return configured }
        return (serverFolders ?? []).map { folder in
            LibraryNavEntry(id: "folder:\(folder.id)",
                            name: folder.name,
                            icon: LibraryIcon.forCollectionType(folder.collectionType),
                            folderID: folder.id,
                            warning: "")
        }
    }

    // ---------------------------------------------------------------- the top bar's tabs (ONE rule)

    /// ⚠⚠ **WHERE THE CURRENT SCREEN IS, as a value — the input to ``tabPlan(entries:current:)``.**
    enum LibraryTabTarget: Equatable {
        case home
        /// The Browse screen with no folder open — the library LIST.
        case browse
        /// One folder's wall.
        case folder(String)
    }

    /// One tab of the top bar, as a VALUE (no closures), so "which tabs exist and which one is current" is a
    /// rule a machine can check.
    struct LibraryTabPlan: Equatable, Identifiable {
        enum Kind: Equatable { case home, browse, library }

        /// ⚠ Stable identity: `"home"` / `"browse"`, or the entry's own id (`"folder:<id>"` /
        /// `"unresolved:<name>"` — `libraryNavEntries`' rule).
        let id: String
        let kind: Kind
        let title: String
        /// The folder this tab opens — `nil` for Home and for the Browse fallback.
        let folderID: String?
        /// True for the tab the viewer is on — the prototype's `[aria-current="true"]`.
        let isCurrent: Bool
        /// False for a library the server could not resolve: it keeps its tab and its warning and simply
        /// cannot be selected (`browseEntries`' rule, on the bar as well as in the list).
        let isEnabled: Bool
        let warning: String
    }

    /// ⚠⚠ **THE TOP BAR'S TABS, EXTRACTED SO THERE IS ONE COPY OF THEM.** `HomeView` built this row inline
    /// until Phase V, and the Library screen needs the same row with a different tab marked current — which
    /// is exactly the shape of this repo's most-repeated defect ("one rule in two places"), the one that put
    /// the `Add profile` tile off the edge of his screenshot and the one `TopBar`'s own header warns about
    /// (*"the tabs are this profile's libraries, not a literal list"*). So the DECISION moved here — pure,
    /// run in the harness — and both screens map it to `TopBarTab`s with their own closures.
    ///
    /// ⚠ **`Home` is always first, and the `Browse` tab exists ONLY when there are no libraries at all.**
    /// That fallback is not cosmetic: without it a profile with no libraries would have an empty bar and **no
    /// way into the one screen that explains the empty config**. It is never offered beside real tabs,
    /// because then it would duplicate them.
    static func tabPlan(entries: [LibraryNavEntry], current: LibraryTabTarget) -> [LibraryTabPlan] {
        var tabs: [LibraryTabPlan] = [
            LibraryTabPlan(id: "home", kind: .home, title: "Home", folderID: nil,
                           isCurrent: current == .home, isEnabled: true, warning: ""),
        ]

        if entries.isEmpty {
            tabs.append(LibraryTabPlan(id: "browse", kind: .browse, title: "Browse", folderID: nil,
                                       isCurrent: current == .browse, isEnabled: true, warning: ""))
            return tabs
        }

        tabs.append(contentsOf: entries.map { entry in
            var isCurrent = false
            if case .folder(let open) = current, let folderID = entry.folderID {
                isCurrent = folderID == open
            }
            return LibraryTabPlan(id: entry.id, kind: .library, title: entry.name, folderID: entry.folderID,
                                  isCurrent: isCurrent, isEnabled: entry.isOpenable, warning: entry.warning)
        })
        return tabs
    }

    /// `lib.ts::folderCountLabel` — `"6 titles"` / `"1 title"`. Plural, always.
    static func folderCountLabel(_ count: Int) -> String {
        "\(count) title\(count == 1 ? "" : "s")"
    }

    // ---------------------------------------------------------------- the poster wall

    /// The wall's rows: drop anything without an id, because a row with no id cannot be opened and has no
    /// poster — the same rule the web's rails apply (`recentlyAddedItems`), reused rather than restated.
    static func wallItems(_ items: [MediaItem]?) -> [MediaItem] {
        (items ?? []).filter { !$0.itemID.isEmpty }
    }

    /// `lib.ts::FIRST_PAINT_CARDS` / `MOUNT_STEP` — **48 and 48, and they are the web app's numbers.**
    ///
    /// ⚠ These exist because a folder can hold hundreds of titles. The web pins them for the same reason:
    /// `FIRST_PAINT_CARDS = 48` is "past the fold" on every surface it renders on, and each later step is
    /// small enough that one step cannot be a long task. ⚠ On a TV the cost profile is *worse* per item
    /// (each card starts an image request and joins the focus engine), so this app takes the same shape and
    /// **caps growth the same way** — it does not mount a 400-title wall in one go.
    enum Mount {
        static let firstPaint = 48
        static let step = 48

        /// What the first paint mounts for a list of `total` rows.
        static func firstCount(_ total: Int, first: Int = firstPaint) -> Int {
            min(max(total, 0), max(first, 0))
        }

        /// How many rows are mounted for `total` rows with `extra` grown so far.
        static func mountedCount(_ total: Int, extra: Int, first: Int = firstPaint) -> Int {
            firstCount(total, first: first) + min(max(max(total, 0) - firstCount(total, first: first), 0),
                                                  max(extra, 0))
        }

        /// The next `extra` value — the growth loop's own arithmetic.
        static func nextExtra(_ extra: Int, total: Int, first: Int = firstPaint, step: Int = step) -> Int {
            let room = max(max(total, 0) - firstCount(total, first: first), 0)
            return min(room, max(extra, 0) + max(step, 0))
        }

        /// Anything left to mount? The growth loop's stopping rule.
        static func needsMore(shown: Int, total: Int) -> Bool {
            max(shown, 0) < max(total, 0)
        }
    }
}

// MARK: - The screen's states

/// The Browse list's own outcome. ⚠ Separate from `RailOutcome` because the payload is folders, not items —
/// but the same three-state discipline: **loaded, or failed with a sentence.** A folder list that quietly
/// comes back empty and a folder list that could not be fetched must not look the same.
enum FoldersOutcome: Equatable {
    case loaded([LibraryNavEntry])
    case failed(String)

    var entries: [LibraryNavEntry] {
        if case .loaded(let entries) = self { return entries }
        return []
    }

    var failedMessage: String? {
        if case .failed(let message) = self { return message }
        return nil
    }
}

/// The wall's outcome for ONE folder.
enum WallOutcome: Equatable {
    case loaded([MediaItem])
    case failed(String)

    var items: [MediaItem] {
        if case .loaded(let items) = self { return items }
        return []
    }

    var failedMessage: String? {
        if case .failed(let message) = self { return message }
        return nil
    }
}
