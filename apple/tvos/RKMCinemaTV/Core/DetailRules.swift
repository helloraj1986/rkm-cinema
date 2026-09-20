import Foundation

// The tvOS detail screen's RULES — pure, so they are RUN on Linux (`apple/scripts/check-tvos-core.py`)
// rather than discovered on a TV.
//
// ⚠⚠ **MIRRORED FROM THE WEB APP, NOT INVENTED.** Sources named at each rule:
//
//   `frontend/src/features/library/lib.ts`    — `fmtRuntime` · `ratingText` · `detailResumePercent` ·
//                                               `detailInProgress` · `detailPrimaryLabel` ·
//                                               `seriesPlayLabel` · `detailMetaBits` · `episodeProgress` ·
//                                               and the three detail sentences
//   `frontend/src/features/playback/lib.ts`   — `episodeCode` · `playLabel` · `nextPlayableEpisode` ·
//                                               `groupBySeason`
//
// Those are what the desktop page and the phone's detail screen already render, so the TV cannot disagree
// with them about what "Resume S1E4" means, how many seasons a series has, or what an episode's progress
// row says.
//
// ⚠ **`fmtRuntime` is NOT re-implemented here — `HomeRules.runtimeText` IS it.** The web has one
// `fmtRuntime` and the TV has one implementation of it (B2, already tested). A second copy in this file
// would be this repo's repeating defect ("one rule in two places") landing in the tier nobody greps; the
// detail meta line calls the same function the cards do, so a runtime reads identically on both screens.
//
// ⚠ **WHAT IS DELIBERATELY NOT HERE: a Play verb that plays.** Phase B is read-only — the player is Phase
// C — so the screen shows the verb it WILL offer (`Resume S1E4` / `Resume (28%)` / `Play`, the phone's own
// words) as INFORMATION, and offers no control that cannot carry it out. A focusable Play button that
// apologises when pressed is a lie the viewer only discovers by pressing it; saying so up front is what
// the plan asks for ("the screen must say so rather than doing nothing"). The rule is still computed and
// tested here, so Phase C's button reads the same value.

/// `playback/lib.ts` → `EpisodeProgress`. ⚠ Same name and same three fields as the interface the phone's
/// episode row reads, so the two surfaces cannot word the same episode differently.
struct EpisodeProgress: Equatable {
    /// 0…100.
    let percent: Int
    let inProgress: Bool
    /// `"1h 04m left"`, or `""` — never `"0m left"`, and never a `"· left"` with nothing in front of it.
    let remainingLabel: String
}

/// `playback/lib.ts` → one entry of `groupBySeason`.
struct SeasonGroup: Equatable, Identifiable {
    let season: Int
    let episodes: [EpisodeItem]

    var id: Int { season }
}

enum DetailRules {

    // ---------------------------------------------------------------- the shape

    /// The detail's own type test. ⚠ `ItemDetail.type` is `"movie" | "tv" | "episode"` — a *different*
    /// vocabulary from a library row's `type` (`"tv" | "movie" | "episode"` in practice, typed `string`),
    /// which is why this is not `HomeRules.isSeries` with a different argument: that one has to tolerate the
    /// frontend's three spellings of a series (`tv`, `show`, `series`) because a *row* can be a show, while
    /// a detail payload is normalised to exactly three values by the server.
    static func isSeries(_ detail: ItemDetail) -> Bool {
        detail.type == "tv"
    }

    /// `ItemDetail.tsx`: `const tv = … || detail?.type === "tv"`.
    static func isEpisode(_ detail: ItemDetail) -> Bool {
        detail.type == "episode"
    }

    // ---------------------------------------------------------------- the meta line

    /// `lib.ts::detailMetaBits` — year · runtime (or season count) · certification, as PARTS.
    ///
    /// ⚠ Unknown values are DROPPED, never rendered as an empty separator: a title with no certification
    /// reads `"2014 · 1h 35m"`, not `"2014 · 1h 35m · "`. The view joins these with a dot.
    /// ⚠ A SERIES shows its season count and not its runtime, because Jellyfin stores a series' runtime as
    /// `0` — `runtimeText(0)` is `""`, so without this branch a series would read `"2021"` alone.
    static func metaBits(_ detail: ItemDetail, seasonCount: Int) -> [String] {
        [
            detail.year.map(String.init) ?? "",
            isSeries(detail) ? seasonsText(seasonCount) : HomeRules.runtimeText(detail.runtime),
            detail.officialRating ?? "",
        ]
        .filter { !$0.isEmpty }
    }

    /// `lib.ts::detailMetaBits`' own season fragment — `"3 seasons"` / `"1 season"`, and `""` for zero.
    static func seasonsText(_ count: Int) -> String {
        count > 0 ? "\(count) season\(count > 1 ? "s" : "")" : ""
    }

    /// `lib.ts::ratingText` — `7.473` → `"7.5"`, `8.0` → `"8"`, and `""` for zero, negative or unknown.
    ///
    /// ⚠ The `.0` strip is the whole reason this is a rule: the web renders a one-decimal score and hides
    /// a whole number's decimal, and a TV reading "8.0" where the laptop reads "8" is a second vocabulary
    /// for one number.
    static func ratingText(_ rating: Double?) -> String {
        guard let rating, rating.isFinite, rating > 0 else { return "" }
        let oneDecimal = String(format: "%.1f", (rating * 10).rounded() / 10)
        return oneDecimal.hasSuffix(".0") ? String(oneDecimal.dropLast(2)) : oneDecimal
    }

    // ---------------------------------------------------------------- the play state

    /// `lib.ts::detailResumePercent` — the detail overlay's bar, 0 when there is nothing to resume.
    static func resumePercent(_ play: DetailPlay?, runtimeSec: Int?) -> Int {
        guard let play, !play.played else { return 0 }
        let position = play.resume
        let runtime = runtimeSec ?? 0
        guard position > 0, runtime > 0 else { return 0 }
        return min(100, Int((Double(position) / Double(runtime) * 100).rounded()))
    }

    /// `lib.ts::detailInProgress` — mid-play AND not finished. ⚠ Two conditions, not one: a finished title
    /// carries a resume position too, and it must not read as "in progress".
    static func isInProgress(_ play: DetailPlay?) -> Bool {
        guard let play else { return false }
        return !play.played && play.resume > 0
    }

    /// `lib.ts::detailPrimaryLabel` — `"Resume"` mid-play, else `"Play"`.
    static func primaryLabel(_ play: DetailPlay?) -> String {
        isInProgress(play) ? "Resume" : "Play"
    }

    /// `ItemDetail.tsx`'s primary button text: `{label}{percent > 0 ? " (28%)" : ""}`.
    /// ⚠ The percentage is part of the VERB on the web, so it is part of it here.
    static func primaryVerb(_ play: DetailPlay?, runtimeSec: Int?) -> String {
        let label = primaryLabel(play)
        let percent = resumePercent(play, runtimeSec: runtimeSec)
        return percent > 0 ? "\(label) (\(percent)%)" : label
    }

    /// `playback/lib.ts::seriesPlayLabel` — `"Resume S1E4"` / `"Play S1E4"` / `"Replay S1E1"` / `"Play"`.
    ///
    /// ⚠ `target` is `nextPlayableEpisode`; `first` is the series' first episode. **`Replay S1E1` is the
    /// whole-series-watched case** — the one state where the button has to change its verb rather than its
    /// episode, and the reason `nextPlayableEpisode` returns nil for a finished series instead of the first
    /// episode.
    /// ⚠ When the episode list could not be fetched both are nil and this reads `"Play"` — honest: without
    /// the list the app does not know which episode, and the screen says so separately
    /// (`DetailSnapshot.partialWarning`).
    static func seriesPlayLabel(target: EpisodeItem?, first: EpisodeItem?) -> String {
        if let target {
            return "\(target.playbackPosition > 0 ? "Resume" : "Play") \(episodeCode(target))"
        }
        return first.map { "Replay \(episodeCode($0))" } ?? "Play"
    }

    // ---------------------------------------------------------------- episodes

    /// `playback/lib.ts::episodeCode` — `"S1E4"`.
    static func episodeCode(season: Int, episode: Int) -> String {
        "S\(season)E\(episode)"
    }

    /// `playback/lib.ts::episodeCode`, for an episode.
    static func episodeCode(_ episode: EpisodeItem) -> String {
        episodeCode(season: episode.season, episode: episode.episode)
    }

    /// `playback/lib.ts::episodeProgress` — percent, the in-progress flag, and the readout.
    ///
    /// ⚠ **TWO conditions on the readout, not one**, and this is the part that is easy to get subtly wrong:
    /// `max(1, …)` floors it at a minute (an episode two seconds from the end says "1m left", never
    /// "0m left"), and the `runtime > 0` test stops an episode whose runtime the server did not send from
    /// reading "0% watched · 1m left" — a countdown against a length nobody knows.
    static func episodeProgress(played: Bool, position: Int, runtime: Int) -> EpisodeProgress {
        let percent = runtime > 0 ? min(100, Int((Double(position) / Double(runtime) * 100).rounded())) : 0
        let inProgress = !played && position > 0
        let remainingLabel = (inProgress && runtime > 0)
            ? "\(HomeRules.runtimeText(max(1, runtime - position))) left"
            : ""
        return EpisodeProgress(percent: percent, inProgress: inProgress, remainingLabel: remainingLabel)
    }

    static func episodeProgress(_ episode: EpisodeItem) -> EpisodeProgress {
        episodeProgress(played: episode.played,
                        position: episode.playbackPosition,
                        runtime: episode.runtime)
    }

    /// `playback/lib.ts::playLabel` — an episode ROW's verb: `"Replay"` / `"Resume"` / `"Play"`.
    /// ⚠ Unused by Phase B's view — the row has no button until Phase C — but the rule is the phone's and it
    /// is RUN here, so the row's state caption and Phase C's button cannot drift apart when the button
    /// arrives. It is kept rather than written later for the reason `DetailRules`' header gives: a rule that
    /// is not computed and tested now is a rule invented under pressure later.
    static func playLabel(played: Bool, position: Int) -> String {
        if played { return "Replay" }
        return position > 0 ? "Resume" : "Play"
    }

    /// `playback/lib.ts::nextPlayableEpisode` — the first in-progress episode, else the first unwatched,
    /// else `nil` (the whole series is watched, and the caller offers a replay of S1E1).
    ///
    /// ⚠ **SORTED BY (season, episode), and STABLY.** The web does `[...episodes].sort((a, b) =>
    /// (a.season - b.season) || (a.episode - b.episode))` and relies on JavaScript's sort being stable
    /// (ES2019+). Swift's `sorted(by:)` is **not** documented as stable, so the enumerated comparison below
    /// restores the web's behaviour by construction and the rule is deterministic for a list with ties —
    /// which is exactly the kind of port that stays silent until a payload is out of order.
    /// ⚠ The server's list is *already* in order; this sorts anyway because the web does, and an ordering
    /// rule that only holds when the input happens to be sorted is not a rule.
    static func nextPlayableEpisode(_ episodes: [EpisodeItem]) -> EpisodeItem? {
        let ordered = episodes.enumerated().sorted { a, b in
            if a.element.season != b.element.season { return a.element.season < b.element.season }
            if a.element.episode != b.element.episode { return a.element.episode < b.element.episode }
            return a.offset < b.offset
        }.map(\.element)
        return ordered.first { !$0.played && $0.playbackPosition > 0 }
            ?? ordered.first { !$0.played }
    }

    /// `playback/lib.ts::groupBySeason` — seasons ascending, ⚠ **and the episodes inside a season keep the
    /// server's order.**
    ///
    /// ⚠⚠ THIS IS THE ONE REAL PORTING HAZARD IN THIS FILE, so it is written the long way on purpose. The
    /// JavaScript original builds a `Map` and sorts its KEYS, which preserves insertion order within each
    /// season; a Swift `[Int: [EpisodeItem]]` iterated with `for (season, eps) in map` has **no order at
    /// all**, so the obvious translation silently shuffles the episodes inside every season. The scan below
    /// appends in input order and sorts only the season NUMBERS, which is the web's behaviour exactly.
    static func groupBySeason(_ episodes: [EpisodeItem]) -> [SeasonGroup] {
        var seasonOrder: [Int] = []
        var bySeason: [Int: [EpisodeItem]] = [:]
        for episode in episodes {
            if bySeason[episode.season] == nil {
                seasonOrder.append(episode.season)
            }
            bySeason[episode.season, default: []].append(episode)
        }
        return seasonOrder.sorted().map { season in
            SeasonGroup(season: season, episodes: bySeason[season] ?? [])
        }
    }

    // ---------------------------------------------------------------- cast and credits

    /// `ItemDetail.tsx::creditsLine` — `"Director: X"` / `"Directors: X, Y"`, or `nil` when there is
    /// nobody to name. ⚠ `nil` rather than `""`: the view drops it entirely, and an empty string is a
    /// paragraph that occupies space and says nothing.
    static func creditsLine(_ people: DetailPeople?, kind: CreditKind) -> String? {
        let names = (kind == .directors ? people?.directors : people?.writers)?
            .map(\.name)
            .filter { !$0.isEmpty } ?? []
        guard !names.isEmpty else { return nil }
        let noun = kind == .directors ? "Director" : "Writer"
        return "\(noun)\(names.count > 1 ? "s" : ""): \(names.joined(separator: ", "))"
    }

    /// `ItemDetail.tsx`: `studios.join(" · ")`. ⚠ Returns `""` for no studios, and the view hides the line.
    static func studiosLine(_ studios: [String]?) -> String {
        (studios ?? []).filter { !$0.isEmpty }.joined(separator: " · ")
    }

    /// The cast rail's rows: people with a name, capped.
    ///
    /// ⚠ **The cap is 10 because `ItemDetail.tsx` writes `people.actors.slice(0, 10)`** — a named constant
    /// on the web side too, because a cast length is a decision. A Jellyfin item can carry fifty people, and
    /// the TV would otherwise build a rail nobody scrolls to the end of.
    /// ⚠ Drops an empty name (Jellyfin can send one) — a card with nothing on it is worse than a shorter
    /// rail — and then caps, in the web's order.
    static func castRows(_ people: DetailPeople?) -> [DetailPerson] {
        Array((people?.actors ?? []).filter { !$0.name.isEmpty }.prefix(Cast.limit))
    }

    enum Cast {
        /// `ItemDetail.tsx::people.actors.slice(0, 10)`.
        static let limit = 10
    }

    /// The hue of a cast avatar — **DERIVED from the person, never sent.**
    ///
    /// ⚠⚠ **WHY A DERIVATION AND NOT A COLOUR.** His prototype's `.avatar` is `hsl(${c.hue} 55% 62%)` with a
    /// hand-picked hue per demo person. The wire does not carry a colour and it must not: inventing one would
    /// be inventing data. What the design actually needs is that **the same person is always the same colour
    /// and two people in a row are usually different**, so the hue is a stable hash of the person's identity —
    /// the same trade `ProfileRules.initials` makes for a name.
    ///
    /// ⚠ The id is the key (Jellyfin's person id is stable for a person), with the NAME as a fallback: a
    /// payload without ids would otherwise give every avatar the same colour, which is the one visibly wrong
    /// answer. `id` and `name` are both non-optional in the interface, so the fallback is belt-and-braces
    /// rather than a case that normally happens.
    ///
    /// ⚠ djb2 over the key's UTF-8 bytes — a fixed, documented algorithm rather than `hashValue`, which is
    /// **seeded per process** in Swift and would therefore give one person two colours on two launches.
    static func castHue(_ person: DetailPerson) -> Double {
        let key = person.id.isEmpty ? person.name : person.id
        guard !key.isEmpty else { return 0 }
        var hash: UInt64 = 5381
        for byte in key.utf8 {
            hash = (hash &* 33) &+ UInt64(byte)
        }
        return Double(hash % 360)
    }
}

/// `ItemDetail.tsx::creditsLine`'s `kind` argument — only two of `DetailPeople`'s three groups have a
/// credit line; actors are the cast rail.
enum CreditKind: Equatable {
    case directors
    case writers
}

// MARK: - The screen's copy

/// The detail screen's sentences, in ONE place.
///
/// ⚠ **The first three are the WEB APP'S OWN WORDS** (`lib.ts`), and that is the point: `DETAIL_NOT_FOUND_*`
/// and `DETAIL_PARTIAL_WARNING` exist on the web precisely so that the desktop modal and the phone's screen
/// say the same thing about the same failure. The TV joins them, verbatim. The fourth is NEW for tvOS and is
/// marked as such, because the web has no equivalent — it can play.
enum DetailCopy {
    static let notFoundTitle = "We couldn't find that title in the library."
    static let notFoundSub = "It may have been removed or the link is stale."

    /// Shown when the DETAIL loaded but the EPISODE LIST did not. ⚠ The web's wording assumes a player
    /// ("playing still works"); on tvOS nothing plays yet, so the second sentence is re-worded while the
    /// first is kept — a partial failure must still read as the same failure the phone reports.
    static let partialWarning = "Couldn't load the episode list."

    // ⚠⚠ **THE WHOLE PLACEHOLDER VOCABULARY IS DELETED (2026-09-20), AND IT WENT IN TWO STEPS.**
    // `playPendingTitle`/`playPendingSub` said *"Arrives with the tvOS player (Phase C)."*; they were renamed
    // to `playReadyTitle`/`playReadySub` and rewritten the moment Phase C landed, to say where the control is.
    // ⚠⚠ Then his round-3 report showed the HOME's hero was still only printing that sentence —
    // *"when i tried to play from the title from continue watching section in home screen, i cant play it"* —
    // and the honest answer was not better copy: the hero's button plays now (`HomeView.play(_:)`).
    // **Copy that explains where a control is, when the control is right there, is the placeholder wearing a new
    // coat.** So these two and `nextUp(_:)` ("Next up: Resume S1E4", whose only renderer was the same notice)
    // are gone, with the harness's literal pins and the falsification entry that reverted `nextUp`. ⚠ Nothing
    // here is kept "in case": a constant nothing renders is a memento, and this file's own header says copy is
    // a rule.

    /// The seasons heading and the per-episode "watched" word — the web's own.
    static let watchedWord = "Watched"
}

// MARK: - The screen's states

/// The whole detail screen, decided from the two responses — a VALUE, so the states are testable rather
/// than a tree of conditionals inside a `body`. Same discipline as `HomeSnapshot`.
struct DetailSnapshot: Equatable {

    let detail: ItemDetail
    /// ⚠ Empty for a film, and empty for a series whose episode list failed — the two are told apart by
    /// ``episodesFailed``, never by the count.
    let episodes: [EpisodeItem]
    /// True when this IS a series and its episode list could not be fetched. The PARTIAL case.
    let episodesFailed: Bool

    var isSeries: Bool { DetailRules.isSeries(detail) }
    var isEpisode: Bool { DetailRules.isEpisode(detail) }

    /// ⚠ The season count the meta line reads is the number of GROUPS, not of episodes — three seasons is
    /// `"3 seasons"` whether there are 24 episodes or 60.
    var seasons: [SeasonGroup] { DetailRules.groupBySeason(episodes) }

    var metaBits: [String] { DetailRules.metaBits(detail, seasonCount: seasons.count) }
    var rating: String { DetailRules.ratingText(detail.communityRating) }
    var resumePercent: Int { DetailRules.resumePercent(detail.play, runtimeSec: detail.runtime) }
    var isInProgress: Bool { DetailRules.isInProgress(detail.play) }
    var studiosLine: String { DetailRules.studiosLine(detail.studios) }
    var genres: [String] { (detail.genres ?? []).filter { !$0.isEmpty } }
    var cast: [DetailPerson] { DetailRules.castRows(detail.people) }
    var directorLine: String? { DetailRules.creditsLine(detail.people, kind: .directors) }
    var writerLine: String? { DetailRules.creditsLine(detail.people, kind: .writers) }
    var overview: String { (detail.overview ?? "").trimmingCharacters(in: .whitespacesAndNewlines) }

    /// The verb this screen WILL offer once the player exists — the phone's own words.
    var primaryVerb: String {
        isSeries
            ? DetailRules.seriesPlayLabel(target: DetailRules.nextPlayableEpisode(episodes),
                                          first: episodes.first)
            : DetailRules.primaryVerb(detail.play, runtimeSec: detail.runtime)
    }

    /// The partial sentence, or nil. ⚠ Only a SERIES can be partial: a film has no episode list to fail,
    /// and showing a warning about a list that was never requested would be a lie on every movie page.
    var partialWarning: String? { episodesFailed && isSeries ? DetailCopy.partialWarning : nil }

    /// ⚠ The film case has no episode rows, and the view keys its episode section off this rather than off
    /// `episodes.isEmpty` — for the same reason the count cannot tell the two cases apart.
    var showsEpisodes: Bool { isSeries }
}

/// The screen's four states, as a value.
///
/// ⚠ **`notFound` is not a failure and must not read like one.** The api answers `404` for an id it has no
/// detail for (`jellyfin_detail.py`: "No detail for item"), and the web turns exactly that into
/// `DETAIL_NOT_FOUND_TITLE` — "this title is gone", not "the server is broken". A `503` (Jellyfin not
/// configured) lands in `failed` instead, because that one IS a server that could not answer.
enum DetailState: Equatable {
    case loading
    case content(DetailSnapshot)
    case notFound
    case failed(String)

    var snapshot: DetailSnapshot? {
        if case .content(let snapshot) = self { return snapshot }
        return nil
    }

    var failureMessage: String? {
        if case .failed(let message) = self { return message }
        return nil
    }
}
