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
// ⚠ **Deliberately NOT here: the Home hero.** The web Home opens on a cinematic hero
// (`pickHomeHero`) and B1's `withoutHero` exists to keep it out of the rail below. **Phase B's plan
// specifies two rows and no hero** (`docs/TVOS_LIBRARY_PLAN.md` §B2), so this file composes exactly two
// rails and has no hero to de-duplicate. If a hero is ever added to the TV Home, `withoutHero`'s rule
// comes with it — that pair is one decision, not two.
//
// ⚠ **Also not here: Recently Added.** `useHomeRows` composes a third rail from `GET /api/library`
// (`LibraryRecentResponse`, modelled in B1). The plan names the two rows this screen has; a third row is a
// screen decision, not a defect, and it lands with the rail it needs rather than being built dead now.

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

/// The whole Home, decided from two responses — so the screen's states are a value that can be tested,
/// not a tree of conditionals inside a `body`.
struct HomeSnapshot: Equatable {

    /// The rail headings. ⚠ The web app's own strings (`SectionHeader title="…"` in
    /// `ContinueWatchingRow.tsx` and `LibraryHomeView.tsx`) — a TV reading a different heading for the same
    /// rail is a second vocabulary for one idea.
    static let continueWatchingTitle = "Continue Watching"
    static let recentlyPlayedTitle = "Recently Played"

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

    /// ⚠ Built ONCE here, and empty rails are dropped: `useHomeRows`' `hasCwRail`/`hasRecentlyPlayed`
    /// flags exist precisely so a section that has nothing does not render as an empty band.
    var rails: [HomeRail] {
        var out: [HomeRail] = []
        let cw = HomeRules.continueWatchingItems(continueWatching.items)
        if !cw.isEmpty {
            out.append(HomeRail(id: .continueWatching, title: Self.continueWatchingTitle, items: cw))
        }
        let played = HomeRules.recentlyPlayedItems(recentlyPlayed.items)
        if !played.isEmpty {
            out.append(HomeRail(id: .recentlyPlayed, title: Self.recentlyPlayedTitle, items: played))
        }
        return out
    }

    /// The titles of the rows that FAILED, in screen order — the view shows these as one short note under
    /// the rails that did render, so a failure is not silent.
    var failedRowTitles: [String] {
        var out: [String] = []
        if continueWatching.failedMessage != nil { out.append(Self.continueWatchingTitle) }
        if recentlyPlayed.failedMessage != nil { out.append(Self.recentlyPlayedTitle) }
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

    /// The starting value, before either request has answered.
    /// ⚠ Both rows are `loaded([])` rather than failed: a screen that has not asked yet has no failure to
    /// report, and treating "not asked" as "failed" would flash an error on every launch.
    static let empty = HomeSnapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([]))

    /// ⚠ The one place the two responses become a screen.
    static func make(continueWatching: RailOutcome, recentlyPlayed: RailOutcome) -> HomeSnapshot {
        HomeSnapshot(continueWatching: continueWatching, recentlyPlayed: recentlyPlayed)
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
