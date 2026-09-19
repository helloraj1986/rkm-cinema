import Foundation

// The tvOS Home's composition RULES — pure, so they are RUN on Linux before a Mac round
// (`apple/scripts/check-tvos-core.py`) rather than discovered on a TV.
//
// ⚠⚠ **THESE ARE THE WEB APP'S RULES, MIRRORED — NOT RE-INVENTED.** The source is
// `frontend/src/features/library/useHomeRows.ts` + `features/library/lib.ts`, which are what the phone,
// tablet and desktop Homes already render, so the TV cannot disagree with them about which title counts
// as "continue watching" or what a card says underneath. Where a rule is copied, the TS function it came
// from is named at the rule. Where something is NEW for tvOS, it says so.
//
// ⚠ **The Home hero LANDED in Phase U3** — this paragraph used to say it was deliberately absent (Phase B's
// plan specified two rows and no hero). It is here now, and `withoutHero` came with it as the same paragraph
// said it would: *"that pair is one decision, not two"*. Both are `lib.ts`'s rules, mirrored.
//
// ⚠ **Recently Added is here as of Phase U4** — the third rail `useHomeRows` has composed on the web since
// M3, built from the same `GET /api/library` response U3 added for the hero's second tier. ⚠ The rule and the
// cap were already written and UNUSED (`HomeRules.recentlyAddedItems`, `HomeRailLimit.recentlyAdded = 16`);
// U4 wired them rather than inventing them, exactly as this header said it would.

/// A rail's identity — `id` is for `ForEach`, `title` is what the viewer reads.
enum HomeRailID: String, Equatable {
    case continueWatching = "continue-watching"
    case recentlyPlayed = "recently-played"
}

/// How many posters a rail shows.
///
/// ⚠ **These two numbers are named in the web app for a reason** (`useHomeRows.ts`): they were literals
/// inside a view (`.slice(0, 14)` / `.slice(0, 16)`), and a rail length is a *decision* — the two rails are
/// deliberately different lengths. Only the played one is used on this screen today; both are carried so
/// the next rail cannot invent a third number.
enum HomeRailLimit {
    static let recentlyPlayed = 14
    static let recentlyAdded = 16
}

/// The client-side mirror of `features/library/lib.ts`. Nothing here fetches; it decides what the fetched
/// rows mean.
enum HomeRules {

    /// `lib.ts::continueWatchingItems` — the Continue Watching SET, as one rule.
    ///
    /// ⚠⚠ **This is NOT a second implementation of the rule — it calls `MediaItem.isResumable`.** The web
    /// app's `isContinueWatching` and this model's `isResumable` are the *same* predicate
    /// (`item_id` present AND (position > 0 OR played)), which is exactly the shape of the defect this
    /// repo keeps re-learning: ONE RULE IN TWO PLACES. The model owns the arithmetic; this name is the
    /// vocabulary the Home speaks. If the definition ever changes, it changes in one place.
    static func isContinueWatching(_ item: MediaItem) -> Bool {
        item.isResumable
    }

    /// `lib.ts::continueWatchingItems` — filter, never re-order: the server's order is the order.
    static func continueWatchingItems(_ items: [MediaItem]?) -> [MediaItem] {
        (items ?? []).filter(isContinueWatching)
    }

    /// The Recently Played rail: capped, and **not** id-filtered.
    ///
    /// ⚠ The asymmetry is the web app's, and it is mirrored rather than "fixed": `useHomeRows` filters
    /// Continue Watching and Recently ADDED by `item_id`, but passes `/recently-watched` through with only
    /// a `slice`. A row without an id on this rail would draw a card with no poster that cannot be opened —
    /// so the card itself refuses to render one (see `RailView`'s id guard) rather than this rule quietly
    /// dropping it and the two tiers disagreeing about what "recently played" contains.
    static func recentlyPlayedItems(_ items: [MediaItem]?) -> [MediaItem] {
        Array((items ?? []).prefix(HomeRailLimit.recentlyPlayed))
    }

    /// `lib.ts::recentlyAddedItems`.
    static func recentlyAddedItems(_ items: [MediaItem]?) -> [MediaItem] {
        Array((items ?? []).filter { !$0.itemID.isEmpty }.prefix(HomeRailLimit.recentlyAdded))
    }

    /// `lib.ts::isSeries` — drives the card's meta line and, later, Play vs Episodes.
    static func isSeries(_ item: MediaItem) -> Bool {
        ["tv", "show", "series"].contains(item.type ?? "")
    }

    /// `lib.ts::LibraryIcon` selection — the card's top-left type glyph.
    ///
    /// ⚠ **The buildspec asks for a WORD here (`MOVIE`)**, and this is the glyph the web app already draws on
    /// every poster instead (`MediaCard.tsx`: the `tv`/`film` icon, replaced by the episode code when there is
    /// one). The app's own vocabulary wins, exactly as it does for the profile subtitles — a word badge on the
    /// TV and a glyph on the phone would be a second vocabulary for one fact. ⚠ `LibraryIcon` is reused rather
    /// than a new enum, so the card, the Browse rows and the library tabs cannot disagree about which icon
    /// means "series".
    static func typeIcon(_ item: MediaItem) -> LibraryIcon {
        isSeries(item) ? .tv : .film
    }

    /// `lib.ts::isEpisodeItem`.
    static func isEpisodeItem(_ item: MediaItem) -> Bool {
        item.kind == "episode" || item.type == "episode"
    }

    /// `lib.ts::episodeItemCode` — `"S1E4"`, or nil when this is not an episode with a facet.
    static func episodeItemCode(_ item: MediaItem) -> String? {
        guard isEpisodeItem(item), let facet = item.episode else { return nil }
        return "S\(facet.season)E\(facet.number)"
    }

    /// `lib.ts::fmtRuntime` — `"2h 5m"`, `"1h"`, `"45m"`, and **`""` for zero or unknown**.
    ///
    /// ⚠ The empty string is the point: the meta line joins segments and drops the empty ones, so a
    /// title with no runtime reads `"2021 · TV"` rather than `"2021 · TV · "`.
    static func runtimeText(_ seconds: Int?) -> String {
        let total = max(0, seconds ?? 0)
        if total <= 0 { return "" }
        let hours = total / 3600
        let minutes = Int((Double(total % 3600) / 60).rounded())
        if hours > 0 {
            return minutes > 0 ? "\(hours)h \(minutes)m" : "\(hours)h"
        }
        return "\(max(1, minutes))m"
    }

    /// `lib.ts::cardMetaLine` — the ONE line under a card's title, shared by every card on every screen.
    ///
    /// ⚠ An episode reads `S1E4 · Series name`; anything else reads year, then `TV` or its runtime, then a
    /// play count **only when it says something** (>1). Absent fields are dropped, never left as an empty
    /// segment. At three metres this is the only text on the card a viewer can read, which is why it is a
    /// rule with a test rather than a string built in a view.
    static func cardMetaLine(_ item: MediaItem) -> String {
        if isEpisodeItem(item) {
            return [episodeItemCode(item), item.episode?.seriesName]
                .compactMap { $0 }
                .filter { !$0.isEmpty }
                .joined(separator: " · ")
        }
        let plays = (item.playCount ?? 0) > 1 ? "\(item.playCount ?? 0) plays" : ""
        return [
            item.year.map(String.init) ?? "",
            isSeries(item) ? "TV" : runtimeText(item.runtime),
            plays,
        ]
        .filter { !$0.isEmpty }
        .joined(separator: " · ")
    }

    // ------------------------------------------------ the Home HERO (Phase U3)

    /// `lib.ts::pickHomeHero` — the one title the hero band features, or nil.
    ///
    /// ⚠⚠ **MIRRORED, NOT INVENTED, and the ORDER is the whole rule:** a continue-watching **movie** first (a
    /// clean "Resume"), then any other in-progress title (episodes included), then the most recently added,
    /// then the first item of the library — and **finished rows never take the hero's spotlight**
    /// (`!played`), because a hero that says "Resume" over something already watched is a lie.
    ///
    /// ⚠ `recentlyAdded` is passed in ALREADY filtered through ``recentlyAddedItems``, exactly as
    /// `useHomeRows` does (`pickHomeHero(cwAll, recentlyAddedAll, all)`), so the TV and the phone cannot pick
    /// different heroes from the same library.
    static func homeHero(continueWatching: [MediaItem]?,
                         recentlyAdded: [MediaItem]?,
                         all: [MediaItem]?) -> MediaItem? {
        let resume = (continueWatching ?? []).filter {
            !$0.itemID.isEmpty && !($0.played ?? false) && ($0.playbackPosition ?? 0) > 0
        }
        if let movie = resume.first(where: { !isSeries($0) && !isEpisodeItem($0) }) { return movie }
        if let first = resume.first { return first }
        if let added = (recentlyAdded ?? []).first(where: { !$0.itemID.isEmpty }) { return added }
        return (all ?? []).first { !isSeries($0) } ?? (all ?? []).first
    }

    /// `lib.ts::withoutHero` — **his decision, 2026-09-17, and it is a RULE rather than a view's preference.**
    ///
    /// Before it, the rail rendered every Continue-Watching title INCLUDING the one the hero was showing, so
    /// the same film appeared twice on one page: once big at the top, once as the first card below. His
    /// wording: *"exclude the hero title from the rail … matches the standard pattern"*.
    ///
    /// ⚠ **Matched by ITEM ID, never by position** (his own note): the hero is chosen from a different list
    /// than the rail is built from, so a positional exclusion would drop the wrong card the moment the two
    /// lists disagree. ⚠ A nil hero removes nothing, and neither does a hero with no id.
    static func withoutHero(_ items: [MediaItem]?, hero: MediaItem?) -> [MediaItem] {
        guard let hero, !hero.itemID.isEmpty else { return items ?? [] }
        return (items ?? []).filter { $0.itemID != hero.itemID }
    }

    /// `lib.ts::heroEyebrow` — the small gold line above the hero's title.
    static func heroEyebrow(continueWatching: Bool, isEpisode: Bool) -> String {
        if !continueWatching { return "Recently Added" }
        return isEpisode ? "Continue episode" : "Continue Watching"
    }

    /// `lib.ts::heroPrimaryLabel` — the hero's primary button, in the app's own words:
    /// an episode resumes ITSELF by code, a series is explored rather than played, and any progress at all
    /// makes the verb a Resume.
    static func heroPrimaryLabel(isEpisode: Bool, episodeCode: String, isSeries: Bool, percent: Int) -> String {
        if isEpisode {
            let verb = percent > 0 ? "Resume" : "Play"
            return episodeCode.isEmpty ? verb : "\(verb) \(episodeCode)"
        }
        if isSeries { return "Explore Episodes" }
        return percent > 0 ? "Resume" : "Play"
    }

    /// `lib.ts::isEpisodeItem`-aware title: an episode's hero is titled with its **series**, because
    /// "The Reckoning" means nothing on a couch.
    static func heroTitle(_ item: MediaItem) -> String {
        if isEpisodeItem(item), let series = item.episode?.seriesName, !series.isEmpty { return series }
        return item.title
    }

    /// `LibraryHomeView.tsx`'s hero meta line — `year · S1 E3 · genre · genre`.
    ///
    /// ⚠ Note the SPACE in `S1 E3`, which is the hero's own format and NOT the card's `S1E3`
    /// (`episodeItemCode`). Both are the web app's, character for character; "fixing" either one here would
    /// make the TV disagree with the phone about the same episode.
    static func heroMetaLine(_ item: MediaItem) -> String {
        var parts: [String] = []
        if let year = item.year { parts.append(String(year)) }
        if isEpisodeItem(item), let episode = item.episode {
            parts.append("S\(episode.season) E\(episode.number)")
        }
        parts.append(contentsOf: (item.genres ?? []).prefix(2))
        return parts.joined(separator: " · ")
    }

    /// `lib.ts::resumePercent` — 0…100, rounded, and **0 when nothing can be stated honestly** (no runtime,
    /// no position). ⚠ The card's bar uses ``MediaItem/progressFraction`` (0…1) because that is what a bar
    /// needs; the hero needs the NUMBER because it prints it, and both come from the same two fields.
    static func heroPercent(_ item: MediaItem) -> Int {
        guard let runtime = item.runtime, runtime > 0,
              let position = item.playbackPosition, position > 0 else { return 0 }
        return min(100, Int((Double(position) / Double(runtime) * 100).rounded()))
    }

    /// `"1h 04m left"`-style text under the hero's progress bar, or `""` — never `"0m left"`, and never a
    /// countdown for a SERIES (which measures episodes, not minutes) or an EPISODE (which has its own code).
    static func heroRuntimeLeft(_ item: MediaItem) -> String {
        guard !isSeries(item), !isEpisodeItem(item) else { return "" }
        guard let runtime = item.runtime, let position = item.playbackPosition,
              position > 0, runtime > position else { return "" }
        return runtimeText(runtime - position)
    }

    /// The hero's progress bar is drawn only when it can say something: a percentage alone, or an episode
    /// (whose remainder is not a countdown).
    static func heroShowsProgress(_ item: MediaItem) -> Bool {
        let percent = heroPercent(item)
        return percent > 0 && (!heroRuntimeLeft(item).isEmpty || isEpisodeItem(item))
    }

}

// MARK: - What one row's fetch produced

/// One row's outcome. ⚠ **A row is allowed to FAIL without taking the screen with it.**
///
/// The api already degrades a passive listing server-side (a provider failure comes back as
/// `provider: null` with an empty list, never an error — `docs/ARCHITECTURE.md`). What it cannot do is
/// decide what the *screen* does when the network itself fails for one of two requests, which is the case
/// this type exists for: on a TV, one dead row must not erase a working one, and it must not vanish
/// silently either — a missing row and a failed row look identical, and only one of them is worth acting
/// on.
enum RailOutcome: Equatable {
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

/// One rendered rail.
struct HomeRail: Identifiable, Equatable {
    let id: HomeRailID
    let title: String
    let items: [MediaItem]
}

/// The TOP BAR's tabs, as an outcome. ⚠ A separate type from `RailOutcome` for the same reason
/// `FoldersOutcome` is: the payload is libraries, not items — and the three-state discipline is identical,
/// because a tab row that quietly came back EMPTY and one that could not be fetched must not look alike.
enum NavOutcome: Equatable {
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

/// The whole Home, decided from its responses — so the screen's states are a value that can be tested,
/// not a tree of conditionals inside a `body`.
struct HomeSnapshot: Equatable {

    /// The rail headings. ⚠ The web app's own strings (`SectionHeader title="…"` in
    /// `ContinueWatchingRow.tsx` and `LibraryHomeView.tsx`) — a TV reading a different heading for the same
    /// rail is a second vocabulary for one idea.
    static let continueWatchingTitle = "Continue Watching"
    static let recentlyPlayedTitle = "Recently Played"
    /// What the footer calls the TAB ROW when its fetch failed. ⚠ Not a rail heading — the tabs are the top
    /// bar's — but the failure has to be named, and "Libraries" is the word the web's own sidebar group uses.
    static let tabsLabel = "Libraries"

    /// Shown when both requests failed. ⚠ NEW for tvOS: the web Home turns a failed query into its
    /// "no media server connected" state, which is a *configuration* sentence. On a TV this is usually a
    /// network that went away, so the copy names that instead of sending the viewer to a `.env` file.
    static let allFailedTitle = "Couldn't load your library"
    static let allFailedSub = "The server didn't answer. Check the connection and try again."

    /// Shown when both requests SUCCEEDED and there is genuinely nothing in either row.
    /// ⚠ NEW for tvOS — the web Home simply renders no sections, which reads as a broken page on a TV with
    /// nothing else on it. This is the sentence that keeps an empty library from looking like a fault.
    static let emptyTitle = "Nothing to play yet"
    static let emptySub = "Titles appear here as the library is watched and added."

    let continueWatching: RailOutcome
    let recentlyPlayed: RailOutcome

    /// The top bar's tabs — **this profile's libraries**, from `BrowseRules.libraryNavEntries` (Phase U3).
    /// ⚠ The buildspec's fixed tab list (`Home · Movies Kids · Movies · TV Shows · …`) is deliberately NOT
    /// used: libraries are per-profile and dynamic, and the rule is already ported (`BrowseRules`). A literal
    /// array here would be the third copy of a rule this repo has consolidated twice.
    let nav: NavOutcome

    /// `GET /api/library` — the recently-added ordering. ⚠ It has TWO consumers: the **hero's second tier**
    /// (U3) and the **Recently Added rail** (U4), which is why the fetch landed with U3 and the rail with U4.
    let libraryRecent: RailOutcome

    /// `GET /api/library/items` — the whole library, which the hero's LAST tier needs
    /// (`pickHomeHero`'s `all`). ⚠ It is the fifth request this screen makes and it exists ONLY for that
    /// tier — recorded because it is the kind of cost somebody later wonders about.
    let libraryItems: RailOutcome

    /// ⚠ Built ONCE here, and empty rails are dropped: `useHomeRows`' `hasCwRail`/`hasRecentlyPlayed`
    /// flags exist precisely so a section that has nothing does not render as an empty band.
    ///
    /// ⚠⚠ **THE HERO IS EXCLUDED FROM THE CONTINUE WATCHING RAIL** — `withoutHero`, his decision of
    /// 2026-09-17. U3 landed the hero, so this exclusion landed with it: the two are one decision.
    var rails: [HomeRail] {
        var out: [HomeRail] = []
        let cw = HomeRules.withoutHero(HomeRules.continueWatchingItems(continueWatching.items), hero: hero)
        if !cw.isEmpty {
            out.append(HomeRail(id: .continueWatching, title: Self.continueWatchingTitle, items: cw))
        }
        let played = HomeRules.recentlyPlayedItems(recentlyPlayed.items)
        if !played.isEmpty {
            out.append(HomeRail(id: .recentlyPlayed, title: Self.recentlyPlayedTitle, items: played))
        }
        return out
    }

    /// The title the hero band features, or nil — `HomeRules.homeHero`, fed from all three lists the way
    /// `useHomeRows` feeds it (`pickHomeHero(cwAll, recentlyAddedAll, all)`).
    var hero: MediaItem? {
        HomeRules.homeHero(continueWatching: continueWatching.items,
                           recentlyAdded: HomeRules.recentlyAddedItems(libraryRecent.items),
                           all: libraryItems.items)
    }

    /// Whether the hero's title came from Continue Watching — the eyebrow's `cw` flag, mirroring
    /// `useHomeRows.heroIsCw`.
    ///
    /// ⚠⚠ **Guarded on a non-empty id, which the web app's own version is not.** This repo has lost a bug to
    /// exactly this: `entryForHit` matched every live hit to the first id-less watchlist entry, because
    /// `"" === ""` is true. A hero with no id cannot have "come from" a list of ids, so the answer is false
    /// rather than "the first row with an empty id matches".
    var heroIsContinueWatching: Bool {
        guard let hero, !hero.itemID.isEmpty else { return false }
        return continueWatching.items.contains { $0.itemID == hero.itemID }
    }

    /// The tabs the top bar draws. ⚠ Named accessor rather than reaching into `nav` from the view, so the
    /// tvOS screen always goes through `BrowseRules`' rule.
    var navEntries: [LibraryNavEntry] { nav.entries }

    /// The titles of the parts that FAILED, in screen order — the view shows these as one short note under
    /// the rails that did render, so a failure is not silent.
    ///
    /// ⚠ The tab row is included: a top bar with no tabs because the fetch failed looks exactly like a
    /// profile with no libraries, and only one of those is worth acting on.
    var failedRowTitles: [String] {
        var out: [String] = []
        if continueWatching.failedMessage != nil { out.append(Self.continueWatchingTitle) }
        if recentlyPlayed.failedMessage != nil { out.append(Self.recentlyPlayedTitle) }
        if nav.failedMessage != nil { out.append(Self.tabsLabel) }
        return out
    }

    /// Both requests failed — the case that definitely takes the whole screen.
    var allFailed: Bool {
        continueWatching.failedMessage != nil && recentlyPlayed.failedMessage != nil
    }

    /// At least one row failed. ⚠ Separate from `allFailed` because it decides the placeholder as well as
    /// the footer — see `placeholder`.
    var hasAnyFailure: Bool { !failedRowTitles.isEmpty }

    /// No rails, and no failure to explain them — a real answer that must read as one.
    var isEmpty: Bool { rails.isEmpty && !hasAnyFailure }

    /// What the screen says when there is nothing to show, or nil when there are rails.
    ///
    /// ⚠⚠ **THE ORDER OF THESE TWO BRANCHES IS THE POINT, and it was wrong in the first draft.** The
    /// obvious version checked `allFailed` and then `isEmpty` — which left the mixed case (one row failed,
    /// the other answered with nothing) falling through to `isEmpty` and telling the viewer "Nothing to play
    /// yet". That is a claim the app cannot make: half its answer never arrived. So `rails.isEmpty` plus
    /// ANY failure takes the failure copy, whatever the other row did. A state table with a hole in it is
    /// exactly what a pure, tested snapshot is for.
    var placeholder: (title: String, sub: String)? {
        if rails.isEmpty && hasAnyFailure { return (Self.allFailedTitle, Self.allFailedSub) }
        if isEmpty { return (Self.emptyTitle, Self.emptySub) }
        return nil
    }

    /// The starting value, before any request has answered.
    /// ⚠ Every list is `loaded([])` rather than failed: a screen that has not asked yet has no failure to
    /// report, and treating "not asked" as "failed" would flash an error on every launch.
    static let empty = HomeSnapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([]),
                                    nav: .loaded([]), libraryRecent: .loaded([]), libraryItems: .loaded([]))

    /// ⚠ The one place the responses become a screen. ⚠ **No default values on purpose** — a defaulted
    /// `nav` would let a caller forget the tab row and get an empty one silently, which is the "silent
    /// default is worse than an absent value" rule this app's auth models already carry.
    static func make(continueWatching: RailOutcome,
                     recentlyPlayed: RailOutcome,
                     nav: NavOutcome,
                     libraryRecent: RailOutcome,
                     libraryItems: RailOutcome) -> HomeSnapshot {
        HomeSnapshot(continueWatching: continueWatching,
                     recentlyPlayed: recentlyPlayed,
                     nav: nav,
                     libraryRecent: libraryRecent,
                     libraryItems: libraryItems)
    }
}

// MARK: - What a failed row says

/// A failed row, reduced to what the *copy* needs — Foundation only, so the sentences can be asserted on
/// Linux without an `APIError` and without a network.
///
/// ⚠ The reduction lives here and the mechanical `APIError` → kind switch lives in `HomeStore`. That split
/// is deliberate: the mapping is five lines a compiler can check, while the SENTENCES are the part that
/// drifts, and they are the part a test can pin. (This block began life in `LibraryAPI.swift` and moved
/// here the moment that stop it being executable — a rule that cannot be RUN is a rule that will drift.)
enum RowFailureKind: Equatable {
    /// DNS, refused connection, TLS, timeout — the server was never reached.
    case transport
    /// `401` — the session is gone, or the profile changed.
    case unauthorized
    /// `403` — the server answered, and said no.
    case forbidden
    /// Any other HTTP status the server chose to send.
    case server(Int)
    /// The server answered, and the body could not be read as the promised shape.
    case decoding
    case unknown
}

/// The one sentence a failed Home row shows.
///
/// ⚠ **NEW copy for tvOS.** The web Home has no per-row failure state — a failed query collapses the whole
/// page into its "no media server connected" screen, which is a *configuration* sentence. On a TV the
/// honest case is "one row could not load", and that is not a `.env` problem, so these sentences say what
/// happened instead of sending the viewer to a file they cannot open from the sofa.
enum HomeRowFailure {

    static func message(for kind: RowFailureKind) -> String {
        switch kind {
        case .transport:
            return "Couldn't reach the server."
        case .unauthorized:
            // ⚠ Not "sign out": the server's 401 taxonomy marks an expired session as "switch profile"
            // (`APIError.authProblem`), and this row cannot tell the two apart. Naming the milder one is
            // the honest choice — `Change profile` is one press away on the same screen either way.
            return "Your session needs signing in again."
        case .forbidden:
            return "This profile isn't allowed to see that."
        case .server(let status):
            return "The server answered \(status)."
        case .decoding:
            return "The server's answer couldn't be read."
        case .unknown:
            return "Something went wrong loading this row."
        }
    }
}
