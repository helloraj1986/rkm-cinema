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
    /// ⚠ **The third rail, wired in Phase U4** — the screen decision `HomeRails`' header used to defer, using
    /// the rule and the cap that were already written for it (`recentlyAddedItems`,
    /// `HomeRailLimit.recentlyAdded`). `useHomeRows` has composed it on the web since M3.
    case recentlyAdded = "recently-added"
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

    /// `lib.ts::LibraryIcon` selection — kept because the Browse rows and the library tabs read it, and
    /// because the card's TYPE glyph was its first caller before U6 gave the card a text badge.
    ///
    /// ⚠ **The badge is now a WORD** (`MOVIE` / `SERIES`, from his prototype) and this is still the icon
    /// mapping the rest of the app shares. Both exist because they answer different questions: the icon says
    /// *what kind of library row is this*, the badge says *what am I looking at* on a poster at three metres.
    /// ⚠ `LibraryIcon` is reused rather than a new enum, so the card, the Browse rows and the tabs cannot
    /// disagree about which icon means "series".
    static func typeIcon(_ item: MediaItem) -> LibraryIcon {
        isSeries(item) ? .tv : .film
    }

    /// ⚠⚠ **THE CARD'S BADGE — `S2·E4` / `MOVIE` in his prototype, and the ONE word in it the app does not
    /// already own.** `rkm-cinema-tvos-concept.html` puts a text chip on the artwork's top-left corner:
    ///
    ///     <span class="card-badge">S2·E4</span>   ·   <span class="card-badge">MOVIE</span>
    ///
    /// ⚠ **The episode code is `episodeItemCode` — the app's own `S1E3`, NOT the prototype's `S1·E3`.** The
    /// prototype has no equivalent of the card's subtitle, and the app's card prints `S1E3 · Series name`
    /// underneath the artwork (the web's own `cardMetaLine`, shared with the phone). Rendering `S1·E3` above
    /// and `S1E3` below would be two spellings of one code ON THE SAME CARD — a worse fault than a missing
    /// middle dot, and the kind this file exists to prevent. ⚠ Say so if the dot matters: it is a one-line
    /// change in this function, and the mismatch it creates should be decided rather than unnoticed.
    ///
    /// ⚠ **`MOVIE` / `SERIES` are the prototype's own words** (it shows `MOVIE` on film cards; a series card
    /// in it always carries an episode code, so `SERIES` is this file's parallel for the case it leaves open)
    /// — and they replace the tv/film GLYPH the card used to draw. The badge is his element, so its words are
    /// his; the glyph stays in ``typeIcon`` for the screens that still read it.
    static func badgeText(_ item: MediaItem) -> String {
        if let code = episodeItemCode(item) { return code }
        return isSeries(item) ? "SERIES" : "MOVIE"
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

    /// ⚠⚠ **THE ONE LINE UNDER A CARD'S TITLE — AND IT IS THE TV CARD'S OWN, TWICE OVER.**
    ///
    /// It replaces the mirrored `lib.ts::cardMetaLine` (which read `1975 · 2h`, or `S1E4 · Series name`),
    /// because his instruction was to make the card *"ultra premium with some additional relevant info which
    /// the user would appreciate, like duration, ratings etc."* — so this is a **deliberate divergence from the
    /// web card, on his call**, and the two things it does differently are both content decisions:
    ///
    ///   1. **DURATION COMES FIRST.** At three metres (and with a remote in hand) "how long is this?" is the
    ///      fact a viewer looks for, and the web's order buried it behind the year.
    ///   2. **IT CARRIES MORE, from fields the wire already has** (`MediaItem`'s own: `runtime`, `genres`,
    ///      `year`, `play_count`, plus the episode facet's `series_name`) — a genre, and the series name on an
    ///      episode.
    ///
    /// ⚠ Absent facts are DROPPED, never left as an empty segment (the rule the mirrored version had).
    /// ⚠ `runtime` is **not** printed for a series: Jellyfin's series runtime is not any one episode's, so a
    /// number there would be a number that means nothing — the same reason `minutesLeft` refuses one.
    /// ⚠ It returns a LIST, not a joined string, so the view owns the separator (the card draws them as
    /// separate chips on a wide screen and as one dotted line on a narrow one) — the reason is the same as
    /// `heroMetaLine` being a string: that one has exactly one consumer with one layout.
    static func cardFacts(_ item: MediaItem) -> [String] {
        var facts: [String] = []

        if !isSeries(item) {
            let duration = runtimeText(item.runtime)
            if !duration.isEmpty { facts.append(duration) }
        }
        if let series = item.episode?.seriesName, !series.isEmpty {
            facts.append(series)
        }
        if let year = item.year {
            facts.append(String(year))
        }
        if let genre = (item.genres ?? []).first, !genre.isEmpty {
            facts.append(genre)
        }
        if let plays = item.playCount, plays > 1 {
            facts.append("\(plays) plays")
        }
        return facts
    }

    /// How long is left, for anything whose `runtime` IS one title's duration.
    ///
    /// ⚠⚠ **A SERIES IS REFUSED, and that is the same trap as the hero's countdown:** Jellyfin reports a
    /// series' cumulative runtime, so "3h 20m left" on a series card would be a confident number about nothing.
    /// A FILM and an EPISODE both answer honestly — and for an episode this is the most useful fact on the
    /// whole card (a viewer deciding whether to start an episode wants to know it is 19 minutes, not 44 %).
    ///
    /// ⚠ `""` means "cannot be stated", never "0 minutes": the view draws nothing rather than a zero.
    static func minutesLeft(_ item: MediaItem) -> String {
        guard !isSeries(item) else { return "" }
        guard let runtime = item.runtime, let position = item.playbackPosition,
              position > 0, runtime > position else { return "" }
        return runtimeText(runtime - position)
    }

    /// The state chip the card draws on the artwork's lower-left corner — `"38m left"`, `"Watched"`, or
    /// nothing at all.
    ///
    /// ⚠ **ONE chip, two facts, in priority order**, and the order is the point: a title that is half watched
    /// says how much is left (the progress bar says *that* it is half watched, not how long that is), and only
    /// a title with nothing left to say falls through to `"Watched"`.
    /// ⚠ A title with a position but an unknown runtime (a series) gets NOTHING here: the bar still shows the
    /// fraction, and a chip reading "Watched" over a half-watched bar would be a lie.
    static func cardStateText(_ item: MediaItem) -> String {
        let left = minutesLeft(item)
        if !left.isEmpty { return "\(left) left" }
        // ⚠ A PARTIAL BAR WITH NO HONEST COUNTDOWN GETS NO CHIP: that is the series-with-a-position case
        // (its runtime means nothing, so there is no countdown), and "Watched" printed beside a 5 % bar
        // would be a lie — the bar is already saying "in progress", which is all that can be said.
        if let fraction = item.progressFraction, fraction < 1 { return "" }
        // ⚠ A FINISHED title reaches here with a full bar (`fraction == 1`), and the web's own priority is
        // that a played title reads as watched — `lib.ts::playbackMarker` checks `played` FIRST for its
        // watched marker. Without this the card would show a 100 % bar and say nothing at all.
        if item.played ?? false { return "Watched" }
        return ""
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

    /// `"1h 50m left"`-style text under the hero's progress bar, or `""` — never `"0m left"`, and never a
    /// countdown for a SERIES (which measures episodes, not minutes) or an EPISODE (which has its own code).
    ///
    /// ⚠⚠ **A THIRD CLAUSE WAS WRITTEN HERE AND DELETED BY THE FALSIFICATION PASS, which is worth the ink:**
    /// the guard used to read `position > 0, runtime > position`. Reverting the second half changed NOTHING —
    /// `HomeRules.runtimeText` clamps a negative remainder with `max(0, …)` and returns `""` — so it was a
    /// clause no check could tell from its absence. **A rule that cannot be falsified is not a rule**, and the
    /// honest fix is to delete the code rather than to keep a mutation that only pretends to pin it.
    /// ⚠ What IS pinned: `!isSeries`/`!isEpisodeItem` (a series counts episodes) and `position > 0` (an
    /// unstarted film has no countdown to show).
    static func heroRuntimeLeft(_ item: MediaItem) -> String {
        // ⚠⚠ **THE HERO SPEAKS FOR FILMS ONLY, AND THE ARITHMETIC IS `minutesLeft`'s — ONE COPY.**
        // An EPISODE hero returns "" on purpose: the hero prints the episode's PERCENTAGE beside the bar, and
        // the countdown belongs on the card, where a viewer is choosing what to start (`HomeRules.minutesLeft`).
        // A SERIES returns "" from `minutesLeft` itself (its runtime is not one episode's).
        isEpisodeItem(item) ? "" : minutesLeft(item)
    }

    /// The hero's progress bar is drawn only when it can say something: a percentage alone, or an episode
    /// (whose remainder is not a countdown).
    static func heroShowsProgress(_ item: MediaItem) -> Bool {
        let percent = heroPercent(item)
        return percent > 0 && (!heroRuntimeLeft(item).isEmpty || isEpisodeItem(item))
    }

    // ------------------------------------------------ what FITS on the first screen

    /// ⚠⚠ **HOW TALL ONE RAIL IS — AND IT IS WHY HIS HERO GOT SHRUNK (W2, his report 2026-09-20).**
    ///
    /// His words: *"there also i can only see continue watching hero page and one title in continue watching"*.
    /// The arithmetic agrees with him exactly. A rail is its heading, the gap under it, and the track (the
    /// card plus the vertical room the focus lift needs — `RailView`'s own `trackPaddingV + titleGap` per
    /// side), and a card is a 16:9 band at `Shelf.cardWidth` plus its two caption lines:
    ///
    ///     heading   1.5u = 28.8 → a ~34.6 pt line
    ///     gap       1.1u = 21.1
    ///     card      19u wide → 16:9 = 205.2, + title 24.2 + gapTop 13.4 + facts 18.9 = 261.7
    ///     track pad 2 × (0.6u + 1.1u) = 65.3
    ///     ───────────────────────────────────────────────────────────────  ≈ 382.7 pt per rail
    static var railHeight: CGFloat {
        let heading = TVTokens.Shelf.titleSize * DetailRules.lineHeightRatio
        let card = cardHeight
        let trackPad = 2 * (TVTokens.Shelf.trackPaddingV + TVTokens.Shelf.titleGap)
        return heading + TVTokens.Shelf.titleGap + card + trackPad
    }

    /// One Home card: the 16:9 artwork plus the caption under it.
    static var cardHeight: CGFloat {
        let art = TVTokens.Shelf.cardWidth * 9 / 16
        let title = TVTokens.Shelf.cardTitleSize * DetailRules.lineHeightRatio
        let facts = TVTokens.Shelf.subSize * DetailRules.lineHeightRatio
        return art + TVTokens.Shelf.titleGapTop + title + TVTokens.Shelf.factsGapTop + facts
    }

    /// The vertical space the rails have: the screen, minus the top bar, minus the hero band, minus one
    /// section gap between each of them (`HomeView`'s `VStack(spacing: u * 2)`).
    static var homeScrollArea: CGFloat {
        TVTokens.Metric.screenHeight - TVTokens.Bar.clearance
    }

    /// ⚠⚠ **HOW MANY RAILS ARE WHOLLY ON THE FIRST SCREEN — THE NUMBER HIS REPORT WAS ABOUT.**
    ///
    /// ⚠ It is computed rather than tuned, so `TVTokens.Hero.minHeightFraction` can be moved and this answers
    /// what it bought. **A rail that merely PEEKS is not counted** (a half-card reads as a rendering fault);
    /// `HomeRules.firstScreenNextRailFraction` says how much of the next one is visible.
    ///
    /// ⚠⚠ **AND IT IS WORTH KNOWING WHAT THIS NUMBER CANNOT BE.** With the cards at `Shelf.cardWidth` and any
    /// hero band at all, the sum is `hero + gap + n × railHeight ≤ homeScrollArea` — so **two whole rails are
    /// the ceiling, and even those need the cards to shrink**: at `19u` a rail is 382.7 pt, and
    /// `2 × 382.7 + 3 × 38.4 = 880.6` against a scroll area of `964.8` leaves **84.2 pt for the hero**, whose
    /// own copy needs ~397. **Three rails do not fit at ANY hero height** (`2 × 38.4 + 3 × 382.7 = 1224.9`
    /// before the hero is counted). ⇒ **The levers are the hero's floor and `Shelf.cardWidth`** — both single
    /// tokens — and this rule is what makes the trade arithmetic instead of a matter of opinion.
    ///
    /// ⚠ The hero is counted at its FLOOR (`Hero.minHeight`), because the band is content-sized
    /// (`HeroBand`): on a two-line title it is taller and fewer rails fit, which is the honest reading.
    ///
    /// ⚠⚠ **The division is `(scrollArea − hero) / (rail + gap)`, and the `gap` belongs INSIDE the divisor:**
    /// `n` rails cost `n × rail + n × gap` (hero → gap → rail → gap → rail …), which is the shape the first
    /// version of this rule got wrong by one — it added a rail the screen cannot hold.
    static var firstScreenRails: Int {
        let available = homeScrollArea - TVTokens.Hero.minHeight
        guard available > 0, railHeight > 0 else { return 0 }
        return max(0, Int(available / (railHeight + TVTokens.u * 2)))
    }

    /// How much of the NEXT rail is on screen — `0` when the rails end exactly, `1` when a further whole rail
    /// would fit. ⚠ The fraction is of the RAIL, so `0.5` means half of that rail's card is visible.
    static var firstScreenNextRailFraction: CGFloat {
        let used = TVTokens.Hero.minHeight
            + CGFloat(firstScreenRails) * (railHeight + TVTokens.u * 2)
        let remaining = homeScrollArea - used
        guard remaining > 0 else { return 0 }
        return min(1, remaining / railHeight)
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
    /// ⚠ The web app's own heading (`LibraryHomeView.tsx:198`: `<SectionHeader title="Recently Added" />`),
    /// pinned by the harness against the literal words.
    static let recentlyAddedTitle = "Recently Added"

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
        // ⚠ U4's third rail. ⚠ `recentlyAddedItems` is the id-FILTERED one (unlike `recentlyPlayedItems`,
        // which is only capped) — the web app's asymmetry, mirrored: a recently-ADDED row with no id cannot be
        // opened and has no poster, so it never reaches the screen.
        let added = HomeRules.recentlyAddedItems(libraryRecent.items)
        if !added.isEmpty {
            out.append(HomeRail(id: .recentlyAdded, title: Self.recentlyAddedTitle, items: added))
        }
        return out
    }

    /// ⚠⚠ **THE CARD THE HOME OPENS ON — HIS DECISION, 2026-09-20: *"Home → first card in the first rail"*.**
    ///
    /// The screen's default focus used to be whatever the platform picks, and the platform's rule is
    /// *top-most, leading-most focusable* — which on this screen is **the top bar's first tab**, not the
    /// content. His instruction puts the ring on the first title instead, so the first press of the remote is
    /// `Select` on something to watch.
    ///
    /// ⚠⚠ **IT IS A PURE RULE ON THE SNAPSHOT, NOT A LINE IN THE VIEW, and that matters for the reason this
    /// repo keeps repeating: a SwiftUI view cannot be run here.** The rule has to skip a rail whose every row
    /// has an empty `itemID` — `RailView` renders NOTHING for such a rail (`cards.isEmpty` → `EmptyView`) — so a
    /// "first card" chosen without that filter is a card that is never drawn, and focus would fall back to the
    /// bar with nothing to explain why. ⇒ This walks the rails exactly as `RailView` does, and the harness pins
    /// it.
    var defaultFocusCardID: String? {
        for rail in rails {
            if let id = rail.items.first(where: { !$0.itemID.isEmpty })?.itemID {
                return id
            }
        }
        return nil
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
        // ⚠ The third rail's own fetch, from U4: the response that feeds it also feeds the hero's second tier,
        // so a failure here can take a whole row off the screen and must say so.
        if libraryRecent.failedMessage != nil { out.append(Self.recentlyAddedTitle) }
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
