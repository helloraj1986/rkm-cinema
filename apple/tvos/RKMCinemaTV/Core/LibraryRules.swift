import Foundation

// The tvOS LIBRARY GRID's rules — pure, so they are RUN on Linux (`apple/scripts/check-tvos-core.py`)
// rather than discovered on a TV.
//
// ⚠⚠ **MIRRORED FROM THE WEB APP, NOT INVENTED, AND THE WEB APP IS WHAT THE PHONE AND THE IPAD RENDER.**
// Source: `frontend/src/features/library/lib.ts` —
//
//   `libraryGenres` · `LIBRARY_SORT_OPTIONS` · `LIBRARY_SORT_KEYS` · `addedTime` · `filterLibraryItems`
//   and all eight comparators behind it (`cmpRecentDesc`, `cmpTitle`, `cmpReleaseDesc`,
//   `cmpRecentlyPlayedDesc`, `cmpProgressDesc`, `cmpRuntimeDesc`, `cmpUnwatched`)
//
// which is what `LibraryFolderView.tsx` (the desktop folder page) and the phone's folder view already run.
// A TV that filters or orders a library differently is a second product.
//
// ⚠⚠ **THE SORT LIST IS THE WEB'S EIGHT, NOT THE PROTOTYPE'S FOUR** — and this is the phase's clearest
// example of a design input being a SOURCE rather than a measurement. `tvos-library-view-spec.md` asks for
// *"Recently added / Title A–Z / Year / Rating"*. `lib.ts:170` says, in the repo's own words:
//
//   > *"Sort options offered by the folder toolbar (NEW_UX §16). Every key maps to a field the frozen
//   > /api/library payload truly carries (added/title/year/last_played/position/runtime) — **"Rating" is
//   > deliberately NOT offered here because list items have no community rating (only the detail fetch
//   > does)**."*
//
// So the web app already answered this question and **refused Rating**, and the producer agrees: the api's
// `_item_public()` (`backend/services/library/jellyfin.py:667`) returns thirteen keys and a rating is not
// among them. Offering a Rating sort would be a control that either lies or does nothing, which
// `docs/ARCHITECTURE.md` §11 forbids. The prototype's other three are all in the web's list.
//
// ⚠ **WHAT IS DELIBERATELY ABSENT: `q`.** `libraryFilterFromParams` ignores the query param — *"free-text
// search was removed from the folders (GLOBAL_SEARCH_PLAN) — the URL q= param is ignored so stale deep links
// don't silently filter"* — and tvOS has no search screen at all (`docs/TVOS_UX_PLAN.md` §5).

/// `lib.ts` → `LibrarySort`. ⚠ The RAW VALUES are the web's own keys, so a sort can be named in a log line
/// or a fixture exactly as the browser names it.
enum LibrarySortKey: String, CaseIterable, Equatable {
    case recent
    case title
    case titleDesc = "title-desc"
    case release
    case recentlyPlayed = "recently-played"
    case progress
    case runtime
    case unwatched
}

/// `lib.ts` → one entry of `LIBRARY_SORT_OPTIONS`.
struct LibrarySortOption: Equatable {
    let key: LibrarySortKey
    /// The web's own label, verbatim — a menu that words one order differently from the laptop's is a second
    /// vocabulary for one setting.
    let label: String
}

/// The library grid's sentences, in ONE place (the same discipline as `DetailCopy`).
enum LibraryCopy {
    /// The prototype's `.empty-state h3`, verbatim.
    static func emptyTitle(_ genre: String) -> String {
        genre.isEmpty ? "Nothing in this library yet" : "No titles in \(genre) yet"
    }

    /// The prototype's `.empty-state p`, with the library's real name where the prototype hard-codes
    /// *"Movies Kids"*.
    static func emptyBody(_ genre: String, library: String) -> String {
        let where_ = library.isEmpty ? "this library" : library
        return genre.isEmpty
            ? "Titles appear here once the media server has scanned them."
            : "Try a different genre, or clear the filter to see everything in \(where_)."
    }

    /// The prototype's `.empty-state .chip`, verbatim.
    static let clearFilter = "Clear filter"

    /// ⚠ The sort control's own label. The prototype draws a *"sort control"* in the filter row but its HTML
    /// renders no markup for one (only the genre chips and the count are injected by its JavaScript), so the
    /// wording here is the app's — and it says what pressing it will do next, which a bare "Sort" does not.
    static func sortControl(_ label: String) -> String { "Sort: \(label)" }
}

enum LibraryRules {

    // ---------------------------------------------------------------- the sort list

    /// `lib.ts::LIBRARY_SORT_OPTIONS` — the web's eight, in its order.
    static let sortOptions: [LibrarySortOption] = [
        LibrarySortOption(key: .recent, label: "Recently added"),
        LibrarySortOption(key: .title, label: "Title (A–Z)"),
        LibrarySortOption(key: .titleDesc, label: "Title (Z–A)"),
        LibrarySortOption(key: .release, label: "Release date"),
        LibrarySortOption(key: .recentlyPlayed, label: "Recently played"),
        LibrarySortOption(key: .progress, label: "Progress"),
        LibrarySortOption(key: .runtime, label: "Runtime"),
        LibrarySortOption(key: .unwatched, label: "Unwatched first"),
    ]

    /// `lib.ts::SORTERS`' fallback — `f.sort ?? "recent"`, and the value a bogus key never becomes.
    static let defaultSort: LibrarySortKey = .recent

    static func sortLabel(_ key: LibrarySortKey) -> String {
        sortOptions.first { $0.key == key }?.label ?? "Recently added"
    }

    /// The sort control's press behaviour: one press, the next order — the prototype's *"no confirm step"*
    /// applied to a control the spec gives no markup for. ⚠ It WRAPS, because a control that stops responding
    /// on its last value reads as a broken remote.
    static func nextSort(after key: LibrarySortKey) -> LibrarySortKey {
        let keys = sortOptions.map(\.key)
        guard let index = keys.firstIndex(of: key) else { return defaultSort }
        return keys[(index + 1) % keys.count]
    }

    // ---------------------------------------------------------------- the genre chips

    /// `lib.ts::libraryGenres` — *"Genre names present in a (kind-split) list, alphabetical, unique."*
    ///
    /// ⚠⚠ **DERIVED FROM THE ROWS, NEVER A LITERAL LIST.** The prototype draws a fixed fourteen-name list
    /// (All, Action, Adventure, … Science Fiction) — and that is a demo's list, standing in for one library's
    /// genres. A chip whose genre no title in THIS folder carries would filter the grid to the empty state on
    /// the viewer's first press, which is the same fault as a tab whose screen does not exist: the app must
    /// not offer what it cannot answer. ⚠ It is the rule `Home/TopBar.swift` already obeys for its tabs
    /// (`BrowseRules.browseEntries`, falsifier F3 of Phase U), on the filter row.
    ///
    /// ⚠ The web's own tie-break is kept: a plain code-unit sort, *"deterministic across engines
    /// (localeCompare is not for case-distinct names like \"Drama\" vs \"drama\")"* — which in Swift is
    /// `sorted()` on the raw `String`, and NOT a localized comparison.
    static func genres(_ items: [MediaItem]) -> [String] {
        var seen = Set<String>()
        for item in items {
            for genre in item.genres ?? [] where !genre.isEmpty {
                seen.insert(genre)
            }
        }
        return seen.sorted()
    }

    // ---------------------------------------------------------------- the dates

    /// `lib.ts::addedTime` — *"Epoch millis for an item's `added` (Jellyfin DateCreated ISO). Jellyfin emits
    /// 7-digit fractional seconds (\"...0000000Z\") which some engines' Date.parse rejects — normalise to
    /// milliseconds first. Unknown/malformed -> null (never a fabricated date; callers sort nulls last)."*
    ///
    /// ⚠⚠ **THE 7-DIGIT NORMALISATION IS NOT COSMETIC AND IT IS WHY THIS IS A RULE.** Measured here
    /// 2026-09-20: `ISO8601DateFormatter` with `.withFractionalSeconds` **does** accept
    /// `2024-05-06T12:34:56.0000000Z` and returns `1714998896.0` — from which it follows that the format is
    /// portable across the two platforms this repo builds on. It does **NOT** accept a payload with no
    /// fraction at all (`2024-05-06T12:34:56Z` → nil), so a second, fraction-less formatter is tried rather
    /// than making every such row sort last.
    ///
    /// ⚠ The return is SECONDS, not the web's milliseconds: every use below is a comparison between two of
    /// these, so the unit is invisible — but two orderings drifting by a factor of 1000 would be invisible too
    /// if one side ever mixed them, so the unit is stated once, here.
    static func addedTime(_ item: MediaItem) -> Double? {
        guard let raw = item.added, !raw.isEmpty else { return nil }
        return parseISO(normaliseFractionalSeconds(raw))
    }

    /// ⚠ Trims a fraction longer than three digits to exactly three (`".0000000Z"` → `".000Z"`), leaving a
    /// short or absent fraction alone. A hand-parser rather than a regex, because this file is compiled by
    /// `swiftc` on Linux as well as by Xcode, and it is four lines.
    static func normaliseFractionalSeconds(_ iso: String) -> String {
        guard let dot = iso.firstIndex(of: ".") else { return iso }
        var index = iso.index(after: dot)
        var digits = 0
        while index < iso.endIndex, iso[index].isNumber {
            digits += 1
            index = iso.index(after: index)
        }
        guard digits > 3 else { return iso }
        let keep = iso.index(iso.startIndex, offsetBy: iso.distance(from: iso.startIndex, to: dot) + 4)
        return String(iso[iso.startIndex..<keep]) + String(iso[index...])
    }

    private static let fractionalFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let plainFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    /// ⚠ Nil for anything unparseable — never `Date()` and never `0`, because a fabricated date would put an
    /// unknown row at the TOP of a "Recently added" wall (epoch 0 would put it at the bottom, which is the
    /// same lie the other way: "known" where the truth is "unknown").
    static func parseISO(_ text: String) -> Double? {
        if let date = fractionalFormatter.date(from: text) { return date.timeIntervalSince1970 }
        if let date = plainFormatter.date(from: text) { return date.timeIntervalSince1970 }
        return nil
    }

    // ---------------------------------------------------------------- the filter and the eight sorts

    /// `lib.ts::filterLibraryItems` — *"Search + genre filter + sort over a folder's (kind-split) items."*
    /// (the `q` half is dropped, see this file's header) — *"Pure — the folder views run this over the shared
    /// cache, so filtering needs no fetch."*
    ///
    /// ⚠⚠ **THE COMPARATORS ARE PORTS, AND THE TIE-BREAKS ARE THE POINT.** Every one of the web's sorters
    /// falls back to `cmpRecentDesc` when its own key ties, and two of them (`release`, `progress`) have a
    /// *leading* rule that is easy to drop:
    ///
    ///   · `release`  — year DESCENDING (newest first), unknown years last, then recent;
    ///   · `progress` — resume fraction DESCENDING, and **a played row, a zero runtime and a missing runtime
    ///                   all score `0`**, so "finished" sorts to the bottom beside "never started" instead of
    ///                   reading as the most-watched thing in the library;
    ///   · `runtime`  — longest first, unknown last, then recent;
    ///   · `unwatched`— unplayed first, then recent.
    ///
    /// ⚠ **Unknown dates sort LAST, never first** (`cmpRecentDesc`'s two `null` branches) — a library with one
    /// undated row must not open with it.
    ///
    /// ⚠ `title` is the web's `localeCompare` on lowercased titles; here it is Swift's own `<` on lowercased
    /// strings, which is **deterministic** whereas `localeCompare` is not — the web's own comment on
    /// `libraryGenres` argues for exactly that trade ("deterministic across engines").
    static func filter(_ items: [MediaItem], genre: String = "", sort: LibrarySortKey = .recent) -> [MediaItem] {
        let wanted = genre.trimmingCharacters(in: .whitespaces)
        let survivors = items.filter { item in
            guard !wanted.isEmpty else { return true }
            return (item.genres ?? []).contains(wanted)
        }
        return stableSorted(survivors, by: sort)
    }

    /// ⚠ **STABLE ON PURPOSE, and Swift's `sorted(by:)` is NOT documented as stable.** The web gets stability
    /// from JavaScript's `Array.prototype.sort` (ES2019+ guarantees it), and every one of these comparators
    /// RELIES on it: `cmpRecentDesc` returns `0` for two rows with the same unknown date *and* for two rows
    /// with identical dates, so the server's order is what the viewer sees for ties. A non-stable sort would
    /// shuffle those rows, on a different machine each time. Same technique as
    /// `DetailRules.nextPlayableEpisode`, and for the same reason: an ordering rule that only holds when the
    /// input happens to be sorted is not a rule.
    static func stableSorted(_ items: [MediaItem], by sort: LibrarySortKey) -> [MediaItem] {
        items.enumerated().sorted { left, right in
            let order = compare(left.element, right.element, by: sort)
            if order != 0 { return order < 0 }
            return left.offset < right.offset
        }.map(\.element)
    }

    /// One sort key's comparison, as a three-way result — the web's `SORTERS` table, one case per key.
    static func compare(_ a: MediaItem, _ b: MediaItem, by sort: LibrarySortKey) -> Int {
        switch sort {
        case .recent:
            return compareRecent(a, b)
        case .title:
            return compareTitle(a, b)
        case .titleDesc:
            return compareTitle(b, a)
        case .release:
            // `cmpReleaseDesc`: newest year first; unknown (`0`) last, then recent.
            let ya = a.year ?? 0
            let yb = b.year ?? 0
            if ya != yb { return yb - ya }
            return compareRecent(a, b)
        case .recentlyPlayed:
            return compareRecentlyPlayed(a, b)
        case .progress:
            let fa = resumeFraction(a)
            let fb = resumeFraction(b)
            if fa != fb { return fb < fa ? -1 : 1 }
            return compareRecent(a, b)
        case .runtime:
            let ra = a.runtime ?? 0
            let rb = b.runtime ?? 0
            if ra != rb { return rb - ra }
            return compareRecent(a, b)
        case .unwatched:
            let pa = a.played ?? false
            let pb = b.played ?? false
            if pa != pb { return pa ? 1 : -1 }
            return compareRecent(a, b)
        }
    }

    /// `cmpRecentDesc` — known dates before unknown, then descending.
    static func compareRecent(_ a: MediaItem, _ b: MediaItem) -> Int {
        let ta = addedTime(a)
        let tb = addedTime(b)
        switch (ta, tb) {
        case let (ta?, tb?): return ta == tb ? 0 : (tb < ta ? -1 : 1)
        case (.some, nil): return -1
        case (nil, .some): return 1
        case (nil, nil): return 0
        }
    }

    /// `cmpTitle` — case-insensitive, and (deliberately) not localized; see ``filter(_:genre:sort:)``.
    static func compareTitle(_ a: MediaItem, _ b: MediaItem) -> Int {
        let ta = a.title.lowercased()
        let tb = b.title.lowercased()
        if ta == tb { return 0 }
        return ta < tb ? -1 : 1
    }

    /// `cmpRecentlyPlayedDesc` — *"sorts by UserData LastPlayedDate; never-played last."*
    ///
    /// ⚠ **BOTH conditions are the web's**: `a.played && a.last_played` — a row with a date but not marked
    /// played is treated as never played, and falls to `cmpRecentDesc`. Dropping the `played` half would put a
    /// half-watched title above a finished one that was watched more recently.
    static func compareRecentlyPlayed(_ a: MediaItem, _ b: MediaItem) -> Int {
        let pa = (a.played ?? false) ? parseISO(a.lastPlayed ?? "") : nil
        let pb = (b.played ?? false) ? parseISO(b.lastPlayed ?? "") : nil
        switch (pa, pb) {
        case let (pa?, pb?): return pa == pb ? 0 : (pb < pa ? -1 : 1)
        case (.some, nil): return -1
        case (nil, .some): return 1
        case (nil, nil): return compareRecent(a, b)
        }
    }

    /// `cmpProgressDesc`'s `frac` — *"`i.played || !i.runtime || i.runtime <= 0 ? 0 : (Number(i.playback_position) || 0) / i.runtime`."*
    /// ⚠ A finished row scores `0`, exactly like an unstarted one, so the sort reads as "what am I in the
    /// middle of" rather than "what have I watched most".
    static func resumeFraction(_ item: MediaItem) -> Double {
        guard !(item.played ?? false), let runtime = item.runtime, runtime > 0 else { return 0 }
        return Double(item.playbackPosition ?? 0) / Double(runtime)
    }

    /// ⚠ The prototype's first chip, `All` — **a way of SAYING "no genre", not a genre**, which is why it is
    /// not part of ``genres(_:)``' result and why its selection test is the empty string.
    static let allChipTitle = "All"

    /// The filter row's chips: `All`, then this library's own genres.
    static func chipTitles(genres: [String]) -> [String] {
        [allChipTitle] + genres
    }

    /// The genre a chip selects — `All` clears the filter rather than filtering by the word "All".
    static func genre(forChip chip: String) -> String {
        chip == allChipTitle ? "" : chip
    }

    /// The prototype's `.chip.selected` — one chip, at most, and `All` is the one that means "everything".
    static func isSelected(chip: String, genre: String) -> Bool {
        let current = genre.trimmingCharacters(in: .whitespaces)
        return chip == allChipTitle ? current.isEmpty : chip == current
    }

    /// The grid card's caption line — the prototype's `.label .m` (`${year} · ${runtime}`).
    ///
    /// ⚠ **`HomeRules.runtimeText` IS the runtime formatter, not a second copy of it** — the web has one
    /// `fmtRuntime` and the TV has one implementation of it (`DetailRules`' header makes the same point).
    /// ⚠ A part that is unknowable is DROPPED rather than rendered as an empty half: a series' Jellyfin
    /// runtime is `0`, `runtimeText(0)` is `""`, so a series card reads just its year instead of `"2021 · "`.
    static func cardMetaLine(_ item: MediaItem) -> String {
        [item.year.map(String.init) ?? "", HomeRules.runtimeText(item.runtime)]
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }

    // ---------------------------------------------------------------- the count line and the card's box

    /// The filter row's live count, right-aligned in the prototype (`.meta-count { margin-left:auto }`).
    ///
    /// ⚠ **It is the prototype's LINE and the web's plural rule, and one part of the prototype's line is
    /// deliberately NOT reproduced.** His JavaScript writes `${shown} of ${TOTAL_LIBRARY_COUNT} titles` where
    /// `TOTAL_LIBRARY_COUNT = 140` is a hand-written demo constant standing in for a library that only has 12
    /// rows in the file. In the app the folder's rows ARE the library, so an unfiltered grid would read
    /// *"140 of 140 titles"* — a sentence that says nothing. Unfiltered therefore uses the web's own
    /// `folderCountLabel` (already mirrored as `BrowseRules.folderCountLabel`); filtered keeps the prototype's
    /// shape.
    static func countLabel(shown: Int, total: Int, genre: String) -> String {
        let wanted = genre.trimmingCharacters(in: .whitespaces)
        guard !wanted.isEmpty else { return BrowseRules.folderCountLabel(total) }
        return "\(shown) title\(shown == 1 ? "" : "s") in \(wanted)"
    }

    /// ⚠⚠ **THE GRID CARD'S WIDTH, AS ARITHMETIC THE HARNESS CAN RUN** — the same trade as
    /// `TVTokens.Profile.rowWidthUnits` and for the same reason: a fit that is only checked by looking at a
    /// television is a fit that is checked by HIM, on his Mac, after a round.
    ///
    /// `grid-template-columns: repeat(6, 1fr)` with `padding: 0 64px` and `gap: 0 28px` distributes the same
    /// way this function does. At the platform's own size — a 1920 pt wide screen, `TVTokens.Grid.margin`
    /// (80.64 pt) each side and `columnGap` (35.28 pt) between six cards — it returns **263.72 pt**, and the
    /// card is then `263.72 × 1.5 = 395.58 pt` tall (`.card { aspect-ratio: 2/3 }`).
    ///
    /// ⚠ **The focus lift is NOT subtracted from this**, deliberately: `cardFocusScale` grows the card INTO
    /// the column gap (which is why the prototype's gutter is `28px` and its scale is only `1.14`), and
    /// subtracting it would make the resting grid narrower than his file draws it. What the gap buys is
    /// headroom, not a smaller card.
    static func cardWidth(containerWidth: CGFloat,
                          columns: Int = TVTokens.Grid.columns,
                          margin: CGFloat = marginFromPrototype,
                          columnGap: CGFloat = TVTokens.Grid.columnGap) -> CGFloat {
        guard columns > 0 else { return 0 }
        let usable = containerWidth - 2 * margin - CGFloat(columns - 1) * columnGap
        return max(0, usable / CGFloat(columns))
    }

    /// `padding: 0 64px`, in the pinned unit — the same value as `TVTokens.Metric.safeMargin`, which is what
    /// §2 of the plan derives `px` from. ⚠ Kept as a named constant so the derivation is one line away.
    static let marginFromPrototype: CGFloat = TVTokens.px * 64
}
