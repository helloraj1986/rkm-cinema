import Foundation

// The Phase B gate that runs WITHOUT a Mac.
//
// ⚠ Why this exists rather than a Mac round: `apple/WORKFLOW.md` §5. Everything SwiftUI is Mac business,
// but the two things Phase B is built on are pure — the **URL every poster card is loaded from**, and the
// **wire models** that decide whether a title, a thumbnail and a resume position survive the trip. Neither
// needs a screen to be wrong, and both are wrong *silently*: a poster URL that 404s and a poster wall that
// cannot decode look exactly like an empty library.
//
// So they are `Foundation`-only and they are EXECUTED here, against fixtures shaped like the real
// payloads — compiled and run by `apple/scripts/check-tvos-core.py`, which falsifies every rule below by
// reverting it and requiring the matching check to fail. These are the same sources the tvOS target
// compiles, not a copy.
//
// ⚠⚠ THE ONE TRAP THIS FILE EXISTS TO PIN, and it is a real one in this repo: **library rows carry
// `item_id`; global-search rows carry `id`.** Same-looking payloads, different key. The check at
// "item_id is the identity key, not id" is the tripwire.

// MARK: - Tiny assertion kit

var checks = 0
var failures: [String] = []
var currentSection = "?"

func section(_ name: String) {
    currentSection = name
    print("\n-- \(name)")
}

func check(_ condition: Bool, _ label: String, _ detail: @autoclosure () -> String = "") {
    checks += 1
    if condition {
        print("   ok   \(label)")
    } else {
        let extra = detail()
        let line = extra.isEmpty ? label : "\(label) — \(extra)"
        print("   FAIL \(line)")
        failures.append("[\(currentSection)] \(line)")
    }
}

func checkEqual<T: Equatable>(_ got: T, _ want: T, _ label: String) {
    check(got == want, label, "got \(got), want \(want)")
}

// MARK: - Fixtures, shaped like the payloads the api actually returns

let movieID = "f3c1a9e04b8d4e0a9b7c2d5e6f8a1b3c"
let seriesID = "0b7e4d1c93a24f5e8c6d2b9a4e1f7c30"

/// A complete Continue-Watching movie row (`_item_public` + the `kind` facet).
let movieRow = #"""
{
  "title": "Sholay",
  "year": 1975,
  "type": "movie",
  "thumb": "http://rkm-hp.tail8d5e8.ts.net:8124/api/jellyfin/Items/f3c1/Images/Primary",
  "item_id": "f3c1a9e04b8d4e0a9b7c2d5e6f8a1b3c",
  "jellyfin_url": "http://rkm-hp.tail8d5e8.ts.net:8098/web/index.html#/details?id=f3c1",
  "played": false,
  "playback_position": 620,
  "runtime": 7200,
  "play_count": 1,
  "last_played": "2026-09-18T10:00:00.0000000Z",
  "genres": ["Action", "Drama"],
  "added": "2026-08-01T00:00:00.0000000Z",
  "kind": "movie"
}
"""#

/// The same item with EVERY optional key absent — the absent-value case the decoder must survive.
let minimalRow = #"""
{ "title": "Sholay", "item_id": "f3c1a9e04b8d4e0a9b7c2d5e6f8a1b3c" }
"""#

/// ⚠ A GLOBAL-SEARCH row, not a library row: it carries `id`. This is the fixture that proves the two
/// shapes are not interchangeable.
let searchRow = #"""
{ "id": "f3c1a9e04b8d4e0a9b7c2d5e6f8a1b3c", "title": "Sholay", "kind": "movie" }
"""#

/// A half-watched EPISODE from `/Users/{uid}/Items/Resume` — the shape with the episode facet.
let episodeResumeRow = #"""
{
  "title": "The Reckoning",
  "item_id": "1a2b3c4d5e6f708192a3b4c5d6e7f809",
  "type": "episode",
  "kind": "episode",
  "played": false,
  "playback_position": 1200,
  "runtime": 2700,
  "play_count": 0,
  "episode": { "number": 3, "season": 1, "series_id": "0b7e4d1c93a24f5e8c6d2b9a4e1f7c30", "series_name": "Some Show" }
}
"""#

func decodeItem(_ json: String) -> MediaItem? {
    try? JSONDecoder().decode(MediaItem.self, from: Data(json.utf8))
}

// MARK: - The poster URL

section("the poster URL")

checkEqual(PosterURL.path(itemID: movieID),
           "api/jellyfin/poster?id=\(movieID)&width=500",
           "a poster path is the proxy route with the id and the default width")

check(PosterURL.path(itemID: "") == nil, "an empty id builds no URL at all")

// ⚠ The server declares `width: int = Query(default=500, ge=16, le=2000)` and 422s outside that range, so
// a width that is out of range must be clamped HERE rather than sent and refused.
checkEqual(PosterURL.clamped(0), 16, "a width below the server's floor is raised to it")
checkEqual(PosterURL.clamped(99_999), 2000, "a width above the server's ceiling is lowered to it")
checkEqual(PosterURL.clamped(500), 500, "a width inside the range is left alone")
check(PosterURL.path(itemID: movieID, width: 0)?.hasSuffix("width=16") ?? false,
      "an out-of-range width is clamped into the URL")

let base = URL(string: "http://rkm-hp.tail8d5e8.ts.net:8124")!
let trailing = URL(string: "http://rkm-hp.tail8d5e8.ts.net:8124/")!

checkEqual(PosterURL.url(base: base, itemID: movieID)?.absoluteString,
           "http://rkm-hp.tail8d5e8.ts.net:8124/api/jellyfin/poster?id=\(movieID)&width=500",
           "an absolute poster URL is the stored address plus the proxy path")
checkEqual(PosterURL.url(base: trailing, itemID: movieID)?.absoluteString,
           "http://rkm-hp.tail8d5e8.ts.net:8124/api/jellyfin/poster?id=\(movieID)&width=500",
           "one slash between the base and the path, whether or not the address ends in one")
check(PosterURL.url(base: base, itemID: "") == nil, "an empty id builds no absolute URL either")

// ⚠ The query must survive as a QUERY. Building this URL by appending the path as one string escapes the
// `?` and the server answers a 404 on a poster that exists — so the id is round-tripped out of the URL
// rather than compared against an assumed encoding.
let awkwardID = "a+b c/d&e"
if let url = PosterURL.url(base: base, itemID: awkwardID),
   let components = URLComponents(url: url, resolvingAgainstBaseURL: false) {
    checkEqual(components.queryItems?.first(where: { $0.name == "id" })?.value, awkwardID,
               "an id with a space, a plus, a slash and an ampersand survives the round trip")
    check(!url.path.contains(awkwardID), "the id is in the query, not in the path")
} else {
    check(false, "an id with a space, a plus, a slash and an ampersand survives the round trip")
}

// MARK: - Decoding an item

section("decoding an item")

let movie = decodeItem(movieRow)
check(movie != nil, "a real Continue-Watching row decodes")
checkEqual(movie?.title, "Sholay", "the title survives")
checkEqual(movie?.itemID, movieID, "item_id is the identity key, not id")
checkEqual(movie?.year, 1975, "the year survives")
checkEqual(movie?.playbackPosition, 620, "the resume position survives, in seconds")
checkEqual(movie?.runtime, 7200, "the runtime survives, in seconds")
checkEqual(movie?.genres, ["Action", "Drama"], "the genre names survive")
checkEqual(movie?.kind, "movie", "the Continue-Watching facet survives")

// ⚠ The absent-value case. Every one of these keys is optional in the shape source, and a decoder that
// required one would turn an omission into a failed screen — not a missing detail.
check(decodeItem(minimalRow) != nil, "a missing thumb does not fail the decode")
checkEqual(decodeItem(minimalRow)?.title, "Sholay", "a row with nothing but title and id still reads")
checkEqual(decodeItem(minimalRow)?.playbackPosition, nil, "an absent resume position is nil, not zero")
checkEqual(decodeItem(minimalRow)?.year, nil, "an absent year is nil")

// ⚠⚠ The tripwire. A search row is NOT a library row; if this ever decodes, the two shapes have been
// conflated and every card built from both is one bug away from showing the wrong title.
check(decodeItem(searchRow) == nil, "a global-search row (id, not item_id) does NOT decode as a library item")

// ⚠ A wrong-typed number is loud, and it must stay loud: JSONDecoder throws rather than defaulting.
check(decodeItem(#"{ "title": "Sholay", "item_id": "x", "runtime": "7200" }"#) == nil,
      "a number sent as a string fails the decode rather than defaulting")

let episode = decodeItem(episodeResumeRow)
checkEqual(episode?.kind, "episode", "an episode resume row carries its kind")
checkEqual(episode?.episode?.seriesName, "Some Show", "the episode facet carries the series name")
checkEqual(episode?.episode?.seriesID, seriesID, "the episode facet carries the series id")
checkEqual(episode?.episode?.season, 1, "the episode facet carries the season")
checkEqual(episode?.episode?.number, 3, "the episode facet carries the episode number")

// MARK: - Resume facts

section("resume facts")

checkEqual(movie?.progressFraction, 620.0 / 7200.0, "progress is the resume position over the runtime")
checkEqual(decodeItem(minimalRow)?.progressFraction, nil, "no runtime means no progress claim")
checkEqual(decodeItem(#"{ "title": "S", "item_id": "x", "playback_position": 0, "runtime": 7200 }"#)?.progressFraction,
           nil, "a position of zero means no progress claim")
checkEqual(decodeItem(#"{ "title": "S", "item_id": "x", "playback_position": 7200, "runtime": 7200 }"#)?.progressFraction,
           1.0, "a full position is a full bar")
checkEqual(decodeItem(#"{ "title": "S", "item_id": "x", "playback_position": 8000, "runtime": 7200 }"#)?.progressFraction,
           1.0, "a position past the end is still one bar, never more")

checkEqual(movie?.isResumable, true, "a half-watched title is resumable")
checkEqual(decodeItem(minimalRow)?.isResumable, false, "a never-played item is not resumable")
checkEqual(decodeItem(#"{ "title": "S", "item_id": "", "playback_position": 10, "runtime": 100 }"#)?.isResumable,
           false, "a row with no id is never resumable")
checkEqual(decodeItem(#"{ "title": "S", "item_id": "x", "played": true }"#)?.isResumable, true,
           "a finished title is resumable (it can be replayed)")

// MARK: - Episodes

section("episodes")

// ⚠ A different shape from `MediaItem` on purpose: `id`, not `item_id`, and `name`, not `title`.
let episodeRow = #"""
{
  "id": "1a2b3c4d5e6f708192a3b4c5d6e7f809",
  "name": "The Reckoning",
  "season": 1,
  "episode": 3,
  "played": false,
  "playback_position": 1200,
  "runtime": 2700,
  "thumb": "http://rkm-hp.tail8d5e8.ts.net:8124/api/jellyfin/Items/1a2b/Images/Primary"
}
"""#
let fallback = #"{ "provider": null, "episodes": [] }"#

if let payload = try? JSONDecoder().decode(EpisodesResponse.self, from: Data(fallback.utf8)) {
    checkEqual(payload.provider, nil, "an empty episodes payload decodes with a null provider")
    checkEqual(payload.episodes.count, 0, "and no episodes")
} else {
    check(false, "an empty episodes payload decodes with a null provider")
}

if let payload = try? JSONDecoder().decode(EpisodesResponse.self, from: Data(episodeRow.utf8)) {
    check(false, "a bare episode row is not an EpisodesResponse — the envelope is required")
} else {
    check(true, "a bare episode row is not an EpisodesResponse — the envelope is required")
}

if let payload = try? JSONDecoder().decode(EpisodesResponse.self,
                                          from: Data(#"{ "provider": "jellyfin", "episodes": [\#(episodeRow)] }"#.utf8)) {
    checkEqual(payload.episodes.count, 1, "one episode decodes inside its envelope")
    checkEqual(payload.episodes.first?.id, "1a2b3c4d5e6f708192a3b4c5d6e7f809", "an episode's identity is id")
    checkEqual(payload.episodes.first?.name, "The Reckoning", "an episode's name is name, not title")
    checkEqual(payload.episodes.first?.season, 1, "the season survives")
    checkEqual(payload.episodes.first?.episode, 3, "the episode number survives")
    checkEqual(payload.episodes.first?.played, false, "the played flag survives")
    checkEqual(payload.episodes.first?.playbackPosition, 1200, "the resume position survives")
    checkEqual(payload.episodes.first?.runtime, 2700, "the runtime survives")
} else {
    check(false, "one episode decodes inside its envelope")
}

// MARK: - Envelopes

section("envelopes")

if let payload = try? JSONDecoder().decode(LibraryItemsResponse.self,
                                           from: Data(#"{ "provider": null, "items": [] }"#.utf8)) {
    checkEqual(payload.provider, nil, "an empty Continue Watching payload decodes")
    checkEqual(payload.items.count, 0, "with no items")
} else {
    check(false, "an empty Continue Watching payload decodes")
}

// ⚠ The Continue-Watching envelope DOES promise `items`, so a payload without one is a shape violation
// rather than an empty row — and this is what makes that difference visible.
if (try? JSONDecoder().decode(LibraryItemsResponse.self, from: Data(#"{ "provider": null }"#.utf8))) != nil {
    check(false, "Continue Watching's items are promised, so their absence is a shape violation")
} else {
    check(true, "Continue Watching's items are promised, so their absence is a shape violation")
}

// ⚠ The folder wall's envelope does NOT promise `items` in the contract (a list factory is not a
// `default` in OpenAPI), so an absent one is an EMPTY WALL and not a failed screen.
if let payload = try? JSONDecoder().decode(FolderItemsResponse.self,
                                           from: Data(#"{ "provider": "jellyfin", "folder_id": "abc" }"#.utf8)) {
    checkEqual(payload.folderID, "abc", "a folder payload keeps its folder id")
    checkEqual(payload.rows.count, 0, "an absent items coalesces to an empty wall")
} else {
    check(false, "an absent items coalesces to an empty wall")
}

if let payload = try? JSONDecoder().decode(FolderItemsResponse.self,
                                           from: Data(#"{ "provider": "jellyfin", "folder_id": "abc", "items": [\#(minimalRow)] }"#.utf8)) {
    checkEqual(payload.rows.count, 1, "a present items survives the coalescing")
    checkEqual(payload.rows.first?.itemID, movieID, "and keeps its rows")
} else {
    check(false, "a present items survives the coalescing")
}

if (try? JSONDecoder().decode(FolderItemsResponse.self, from: Data(#"{ "items": [] }"#.utf8))) != nil {
    check(false, "a folder payload without a folder id is refused")
} else {
    check(true, "a folder payload without a folder id is refused")
}

let recent = #"""
{ "provider": null, "available": true, "counts": { "movies": 412, "series": 63 },
  "recent": [ { "title": "Sholay", "item_id": "f3c1a9e04b8d4e0a9b7c2d5e6f8a1b3c" } ],
  "server": "jellyfin", "urls": { "web": "http://rkm-hp:8098" } }
"""#
if let payload = try? JSONDecoder().decode(LibraryRecentResponse.self, from: Data(recent.utf8)) {
    checkEqual(payload.available, true, "the library payload's availability survives")
    checkEqual(payload.counts["movies"], 412, "the counts survive")
    checkEqual(payload.server, "jellyfin", "the server name survives")
    checkEqual(payload.urls?["web"], "http://rkm-hp:8098", "the server urls survive")
    checkEqual(payload.recent.count, 1, "the recently-added rows survive")
} else {
    check(false, "the library payload's availability survives")
}

// ⚠⚠ A HAZARD, pinned deliberately rather than discovered on a TV later. One malformed row fails the
// WHOLE envelope — so a single bad item in the library means no Home screen at all, not a missing card.
// That is the correct reading of the shape (both `title` and `item_id` are promised), but it is a
// property a caller should know it is relying on before it builds a screen out of one decode.
if (try? JSONDecoder().decode(LibraryRecentResponse.self,
                              from: Data(#"{ "provider": null, "available": true, "counts": {}, "recent": [ {} ] }"#.utf8))) != nil {
    check(false, "one malformed row fails the whole envelope, not just its own card")
} else {
    check(true, "one malformed row fails the whole envelope, not just its own card")
}

// ⚠ An EMPTY id is different from an ABSENT one, and the shape allows the empty case: the frontend's own
// rail guard is `Boolean(item.item_id)`. So the model decodes it (never crashing) and the two guards a
// screen has — `isResumable`, and `PosterURL`'s refusal — are what stop a blank card being drawn.
checkEqual(decodeItem(#"{ "title": "S", "item_id": "" }"#)?.itemID, "",
           "a row with an EMPTY id decodes rather than crashing")
checkEqual(decodeItem(#"{ "title": "S", "item_id": "" }"#)?.isResumable, false,
           "and is never treated as resumable")
check(decodeItem(#"{ "item_id": "x" }"#) == nil, "an absent title is refused — the shape promises one")
check(decodeItem(#"{ "title": "S" }"#) == nil, "an absent id is refused — the shape promises one")

// MARK: - The Home's rules (Phase B2)

section("the home rules")

/// ⚠ A helper that builds a real item by DECODING it, not by a memberwise init — so a fixture can never
/// describe a shape the wire does not produce.
func item(_ id: String, _ extra: String = "") -> MediaItem? {
    decodeItem("{\"title\": \"Title \(id)\", \"item_id\": \"\(id)\"\(extra)}")
}

let manyRows = (1...20).compactMap { item("id\($0)") }
checkEqual(HomeRules.recentlyPlayedItems(manyRows).count, 14, "the Recently Played rail caps at 14")
checkEqual(HomeRules.recentlyAddedItems(manyRows).count, 16, "the Recently Added cap is 16, not 14")

// ⚠ His rule, and the one a wrong implementation gets silently wrong: an in-progress OR played row with a
// real id is Continue Watching. A row with no id cannot be opened, so it is not.
let cwCandidates = [
    item("a", ", \"playback_position\": 60, \"runtime\": 600"),
    item("b", ", \"played\": true"),
    item("c", ", \"playback_position\": 0"),
    item("", ", \"playback_position\": 30"),
    item("d"),
].compactMap { $0 }
checkEqual(HomeRules.continueWatchingItems(cwCandidates).map(\.itemID), ["a", "b"],
           "only in-progress or played rows WITH an id are Continue Watching")
checkEqual(HomeRules.continueWatchingItems(nil).count, 0, "no payload is no rows, not a crash")
checkEqual(HomeRules.continueWatchingItems(cwCandidates).first?.title, "Title a",
           "the rows keep the server's order, which is newest first")

// ⚠ The two rails are filtered differently ON PURPOSE (the web app's asymmetry, mirrored): Recently Played
// is only capped, Recently Added is capped AND id-filtered.
checkEqual(HomeRules.recentlyAddedItems([item("x"), item("")].compactMap { $0 }).count, 1,
           "the Recently Added rail drops a row with no id")
checkEqual(HomeRules.recentlyPlayedItems([item("x"), item("")].compactMap { $0 }).count, 2,
           "…while Recently Played is passed through (the card, not the rule, refuses the dead row)")

section("the card's facts")

// ⚠⚠ THE CARD'S FACTS LINE (U6's premium pass) — it REPLACES the mirrored `lib.ts::cardMetaLine` on his
// instruction (*"make it ultra premium with some additional relevant info … like duration, ratings"*), and the
// two things it does differently are both content decisions: duration FIRST, and it carries a genre and an
// episode's series name. ⚠ It is a LIST, not a joined string — the view owns the separator, because a narrow
// card draws the same facts as two chips.
checkEqual(HomeRules.cardFacts(movie!), ["2h", "1975", "Action"],
           "a film leads with its duration, then the year and a genre")
checkEqual(HomeRules.cardFacts(episode!), ["45m", "Some Show"],
           "an episode leads with its duration and names its series")
checkEqual(HomeRules.cardFacts(item("s", ", \"type\": \"tv\", \"year\": 2021, \"runtime\": 7200, \"play_count\": 3")!),
           ["2021", "3 plays"],
           "⚠ a SERIES never prints a runtime — Jellyfin's series runtime is not one episode's")
checkEqual(HomeRules.cardFacts(item("n", ", \"runtime\": 2700")!), ["45m"],
           "a fact with nothing beside it stands alone")
checkEqual(HomeRules.cardFacts(item("u", ", \"year\": 2020")!), ["2020"],
           "no duration known leaves the year leading, with no empty segment")
checkEqual(HomeRules.cardFacts(item("p", ", \"year\": 2001, \"play_count\": 1")!), ["2001"],
           "one play says nothing, so it is not shown")

section("the profile row's fit")

// ⚠⚠ **A RUNNABLE LAYOUT INVARIANT, WHICH IS THE ONLY KIND WORTH STATING.** His screenshot showed the
// `Add profile` tile hanging off the right edge of the Profile Switcher: the row was `5 × 13u + 4 × 2.6u =
// 75.4u` of tiles with the screen's `4.2u` margins on top, and a SECOND horizontal margin had been added on
// top of that. The numbers are the prototype's own (`TVTokens.Profile`), so the fit is arithmetic:
// ⚠ (One string, not two: Swift does not concatenate adjacent literals the way Python and C do — the first
// version of this line failed to compile, which is what the gate is for.)
check(TVTokens.Profile.rowWidthUnits + 2 * TVTokens.Profile.rowMarginUnits <= 100 - 2 * 6,
      "⚠ the profile row fits the screen with a whole margin (6u) to spare — a second margin anywhere is the defect that clipped the Add profile tile")

section("how long is left")

// ⚠⚠ The arithmetic the HERO and the CARD now SHARE (`HomeRules.minutesLeft`), with the series refusal that
// keeps both honest — and the one place they differ on purpose, which is episodes.
checkEqual(HomeRules.minutesLeft(movie!), "1h 50m", "a half-watched film has 1h 50m left")
checkEqual(HomeRules.minutesLeft(episode!), "25m",
           "⚠ an EPISODE answers — this is why the card needs its own countdown: the hero says nothing for one")
checkEqual(HomeRules.minutesLeft(item("s", ", \"type\": \"tv\", \"runtime\": 600, \"playback_position\": 30")!), "",
           "⚠ a SERIES has no countdown: its runtime is not one episode's")
checkEqual(HomeRules.minutesLeft(item("z", ", \"runtime\": 600")!), "",
           "an unstarted title has nothing left to lose")
checkEqual(HomeRules.heroRuntimeLeft(episode!), "",
           "⚠ the HERO still says nothing for an episode — the percentage is what it prints")

section("the card's state chip")

// ⚠⚠ ONE chip, TWO facts, in priority order: how much is left beats whether it is watched, and a title with a
// partial bar and no honest countdown gets nothing at all.
checkEqual(HomeRules.cardStateText(movie!), "1h 50m left", "a half-watched film says how much is left")
checkEqual(HomeRules.cardStateText(episode!), "25m left", "a half-watched episode says how much is left")
checkEqual(HomeRules.cardStateText(item("w", ", \"played\": true")!), "Watched",
           "a title marked watched says so")
checkEqual(HomeRules.cardStateText(item("f", ", \"played\": true, \"runtime\": 600, \"playback_position\": 600")!),
           "Watched",
           "⚠ a FINISHED title says Watched beside its full bar, not nothing at all")
checkEqual(HomeRules.cardStateText(item("s", ", \"type\": \"tv\", \"runtime\": 600, \"playback_position\": 30")!), "",
           "⚠ a part-watched SERIES gets no chip — the bar says in progress, and Watched would be a lie")
// ⚠⚠ **THE FIXTURE THAT MAKES THE `fraction < 1` BRANCH LOAD-BEARING.** With `played` false the check above
// passes whether the branch exists or not — which the falsification gate caught (the mutation reverting the
// branch stayed GREEN). A SERIES that Jellyfin marks PLAYED while an episode is part-watched is the real case:
// the fraction is partial, there is no honest countdown, and the branch is the only thing standing between it
// and a `Watched` chip sitting on a 5 % bar.
checkEqual(HomeRules.cardStateText(item("s2", ", \"type\": \"tv\", \"runtime\": 600, \"playback_position\": 30, \"played\": true")!), "",
           "⚠ a part-watched SERIES Jellyfin also marks played gets no chip either")
checkEqual(HomeRules.cardStateText(item("q", ", \"runtime\": 600")!), "",
           "a title nobody has started says nothing")

checkEqual(HomeRules.episodeItemCode(episode!), "S1E3", "an episode's code is S<season>E<number>")
checkEqual(HomeRules.episodeItemCode(movie!), nil, "a film has no episode code")

section("runtime text")

checkEqual(HomeRules.runtimeText(nil), "", "an unknown runtime says nothing")
checkEqual(HomeRules.runtimeText(0), "", "a zero runtime says nothing")
checkEqual(HomeRules.runtimeText(1), "1m", "a runtime under a minute still reads 1m, never 0m")
checkEqual(HomeRules.runtimeText(45), "1m", "45 seconds rounds up to a minute")
checkEqual(HomeRules.runtimeText(2700), "45m", "an hour-less runtime reads in minutes")
checkEqual(HomeRules.runtimeText(3600), "1h", "an exact hour drops the minutes")
checkEqual(HomeRules.runtimeText(7500), "2h 5m", "hours and minutes together")

// MARK: - The Home screen's states (Phase B2)

section("the home screen's states")

let cwRow = item("cw", ", \"playback_position\": 60, \"runtime\": 600")!
let playedRow = item("rp", ", \"played\": true")!

/// ⚠ U3's snapshot carries FIVE inputs; the state-table checks below are about the two RAILS, so they are
/// written against this shorthand — and the three new inputs default to EMPTY AND LOADED, which is exactly
/// what "not asked" means (`HomeSnapshot.empty`'s rule: never failed on a screen that has not asked).
/// ⚠ The shorthand lives HERE and not on `HomeSnapshot`, because `make` deliberately has no defaults: a
/// production caller that forgot the tab row must not get an empty one silently.
func snapshot(continueWatching cw: RailOutcome,
              recentlyPlayed played: RailOutcome,
              nav: NavOutcome = .loaded([]),
              libraryRecent: RailOutcome = .loaded([]),
              libraryItems: RailOutcome = .loaded([])) -> HomeSnapshot {
    HomeSnapshot.make(continueWatching: cw, recentlyPlayed: played, nav: nav,
                      libraryRecent: libraryRecent, libraryItems: libraryItems)
}

let nothing = snapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([]))
checkEqual(nothing.rails.count, 0, "an empty library renders no rails")
checkEqual(nothing.isEmpty, true, "…and says so")
checkEqual(nothing.allFailed, false, "an empty library is NOT a failure")
// ⚠⚠ THE LITERALS HERE ARE THE POINT. An earlier draft compared these against `HomeSnapshot.emptyTitle`
// and so on — a TAUTOLOGY: mutating the constant moved both sides and the check stayed green, which the
// falsification pass caught. The copy is a rule; it is pinned against the words, not against itself.
checkEqual(nothing.placeholder?.title, "Nothing to play yet", "the empty state has its own sentence")

// ⚠⚠ TWO in-progress rows, not one, and that is U3's doing: the HERO takes the first of them and
// `withoutHero` takes it out of the rail below, so a one-row fixture would leave no Continue Watching rail at
// all. That is the web app's behaviour and it is correct — the hero IS the continue-watching title, and the
// rail is what is LEFT (his de-duplication rule, 2026-09-17). The second row is what makes the rail exist.
let cwRow2 = item("cw2", ", \"playback_position\": 30, \"runtime\": 600")!
let content = snapshot(continueWatching: .loaded([cwRow, cwRow2]), recentlyPlayed: .loaded([playedRow]))
checkEqual(content.rails.map(\.id), [.continueWatching, .recentlyPlayed],
           "Continue Watching comes first, then Recently Played")
checkEqual(content.rails.first?.title, "Continue Watching",
           "the Continue Watching rail has the web app's own heading")
checkEqual(content.rails.last?.title, "Recently Played",
           "the Recently Played rail has the web app's own heading")
check(content.placeholder == nil, "a screen with content has no placeholder")

let oneEmpty = snapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([playedRow]))
checkEqual(oneEmpty.rails.map(\.id), [.recentlyPlayed],
           "a row that is empty does not render an empty band")
check(oneEmpty.placeholder == nil, "one working row is still a screen")

let oneFailed = snapshot(continueWatching: .failed("boom"), recentlyPlayed: .loaded([playedRow]))
checkEqual(oneFailed.rails.count, 1, "a failed row does not take a working one with it")
checkEqual(oneFailed.failedRowTitles, [HomeSnapshot.continueWatchingTitle],
           "…and the failure is named so it is not silent")
checkEqual(oneFailed.allFailed, false, "one failure is not two")
check(oneFailed.placeholder == nil, "a failed row does not blank a screen that has content")

// ⚠⚠ THE MIXED CASE, and the reason `placeholder` checks `rails.isEmpty && hasAnyFailure` rather than
// `allFailed`: one row failed and the other honestly answered "nothing". Falling through to the empty
// sentence would tell the viewer "Nothing to play yet" while half the answer never arrived.
let mixed = snapshot(continueWatching: .loaded([]), recentlyPlayed: .failed("boom"))
checkEqual(mixed.isEmpty, false, "a failure is not an empty library")
checkEqual(mixed.placeholder?.title, "Couldn't load your library",
           "with nothing to show, a failed row takes the screen rather than claiming the library is empty")

let bothFailed = snapshot(continueWatching: .failed("a"), recentlyPlayed: .failed("b"))
checkEqual(bothFailed.allFailed, true, "both rows failed")
checkEqual(bothFailed.rails.count, 0, "…so there are no rails")
checkEqual(bothFailed.failedRowTitles.count, 2, "…and both are named")
checkEqual(bothFailed.placeholder?.title, "Couldn't load your library", "…and the failure takes the screen")

// ⚠ The value the store starts from. Not asked is NOT failed — otherwise every launch would flash an
// error sentence before the first byte arrives.
checkEqual(HomeSnapshot.empty.allFailed, false, "the starting snapshot is empty, never failed")
checkEqual(snapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([])).placeholder?.sub,
           "Titles appear here as the library is watched and added.", "the empty state explains itself")

section("what a failed row says")

checkEqual(HomeRowFailure.message(for: .transport), "Couldn't reach the server.",
           "a transport failure says the server was not reached")
checkEqual(HomeRowFailure.message(for: .unauthorized), "Your session needs signing in again.",
           "a 401 names the session, not a sign-out")
checkEqual(HomeRowFailure.message(for: .forbidden), "This profile isn't allowed to see that.",
           "a 403 names the profile")
checkEqual(HomeRowFailure.message(for: .server(500)), "The server answered 500.",
           "another status carries the number the server sent")
checkEqual(HomeRowFailure.message(for: .decoding), "The server's answer couldn't be read.",
           "a decode failure says the answer could not be read")

let everyKind: [RowFailureKind] = [.transport, .unauthorized, .forbidden, .server(502), .decoding, .unknown]
let sentences = everyKind.map(HomeRowFailure.message(for:))
check(sentences.allSatisfy { !$0.isEmpty && $0.hasSuffix(".") },
      "every failure kind is a whole sentence")
checkEqual(Set(sentences).count, everyKind.count, "and no two kinds share a sentence")

// MARK: - Browse's rules (Phase B3)

section("the library list")

/// ⚠ Built by DECODING, so a fixture cannot describe a shape the wire does not produce — and it must carry
/// **every non-optional field**, which is what a real payload does. That is not pedantry: the contract
/// `default`s `path`, `ok`, `warning`, `collection_type`, R3 accepts them as non-optional for exactly that
/// reason, and Swift's synthesised `Decodable` does **not** apply a default from the contract — so a
/// fixture that omits one is a fixture the server could never send. (It failed here first, loudly, with a
/// `Fatal error: Unexpectedly found nil` on the force-unwrap below. Fix the fixture, not the model.)
func library(_ name: String, ok: Bool, folderID: String? = nil,
             collectionType: String = "movies", warning: String = "") -> ConfiguredLibrary? {
    var json = "{\"name\": \"\(name)\", \"path\": \"/media/movies\", \"ok\": \(ok), "
        + "\"collection_type\": \"\(collectionType)\", \"warning\": \"\(warning)\""
    if let folderID { json += ", \"folder_id\": \"\(folderID)\"" }
    json += "}"
    return try? JSONDecoder().decode(ConfiguredLibrary.self, from: Data(json.utf8))
}

let resolvedLib = library("Movies", ok: true, folderID: "abc")!
// ⚠⚠ THE FIXTURE THAT MAKES THE GATE PROVABLE. `ok` false but a folder id STILL PRESENT is the case the
// `ok &&` half exists for, and the first draft of this fixture omitted the id — so removing the gate changed
// nothing and the falsification pass reported the rule as unpinned. A fixture that cannot tell a rule from
// its absence tests nothing, which is exactly what `--falsify` is for.
let unresolvedLib = library("Old TV", ok: false, folderID: "ghost", collectionType: "tvshows",
                            warning: "Path not found on the server")!
// …and the plain case: no id at all.
let noFolderLib = library("Music", ok: false, folderID: nil)!

let navEntries = BrowseRules.libraryNavEntries([resolvedLib, unresolvedLib])
checkEqual(navEntries.count, 2, "both libraries get a row")
checkEqual(navEntries.first?.isOpenable, true, "a resolved library is openable")
checkEqual(navEntries.first?.folderID, "abc", "and carries its folder id")
checkEqual(navEntries.first?.icon, .film, "a `movies` library gets the film icon")
// ⚠⚠ THE RULE HIS iPAD REPORT BOUGHT (2026-09-14): an unresolved library is KEPT, with its warning — never
// dropped, which is how a library "disappears" on one surface and not another.
checkEqual(navEntries.last?.isOpenable, false, "an unresolved library is NOT openable")
checkEqual(navEntries.last?.folderID, nil,
           "…and has no folder to open, even though the payload carried one")
checkEqual(BrowseRules.libraryNavEntries([noFolderLib]).first?.folderID, nil,
           "a library with no folder id has none to open")
checkEqual(navEntries.last?.warning, "Path not found on the server", "…and keeps the server's own warning")
checkEqual(navEntries.last?.name, "Old TV", "…and is still listed by name")
check(navEntries.last?.id.hasPrefix("unresolved:") ?? false, "an unresolved row has its own stable identity")
checkEqual(BrowseRules.libraryNavEntries(nil).count, 0, "no libraries is no rows, not a crash")
let noWarning = BrowseRules.libraryNavEntries([library("Mystery", ok: false)!])
checkEqual(noWarning.first?.warning, "Library unavailable",
           "an unresolved library with no warning still says why")

checkEqual(LibraryIcon.forCollectionType("Movies"), .film, "Movies is the film icon")
checkEqual(LibraryIcon.forCollectionType("tvshows"), .tv, "tvshows is the tv icon")
checkEqual(LibraryIcon.forCollectionType("TV"), .tv, "the type match is case-insensitive")
checkEqual(LibraryIcon.forCollectionType("music"), .folder, "an unknown type falls back to a folder")
checkEqual(LibraryIcon.forCollectionType(""), .folder, "…and so does an empty one")

// ⚠ The server's own folders are the fallback ONLY when nothing is configured — a tvOS-only decision,
// recorded in `BrowseRules`. With libraries configured (his server), the TV and the phone agree exactly.
let serverFolder = try! JSONDecoder().decode(LibraryFolder.self,
                                            from: Data(#"{ "id": "srv1", "name": "Movies", "collection_type": "movies", "path": "/media/movies" }"#.utf8))
checkEqual(BrowseRules.browseEntries(libraries: [resolvedLib], serverFolders: [serverFolder]).first?.folderID,
           "abc", "configured libraries win when there are any")
checkEqual(BrowseRules.browseEntries(libraries: [], serverFolders: [serverFolder]).count, 1,
           "with nothing configured, the server's own folders are shown")
checkEqual(BrowseRules.browseEntries(libraries: nil, serverFolders: nil).count, 0,
           "with neither, there is nothing to show")
checkEqual(BrowseRules.libraryByFolderID([resolvedLib], folderID: "abc")?.name, "Movies",
           "a folder is titled by its library")
checkEqual(BrowseRules.libraryByFolderID([resolvedLib], folderID: nil)?.name, nil,
           "no folder id means no library name")

checkEqual(BrowseRules.folderCountLabel(0), "0 titles", "zero titles is plural")
checkEqual(BrowseRules.folderCountLabel(1), "1 title", "one title is singular")
checkEqual(BrowseRules.folderCountLabel(6), "6 titles", "six titles is plural")

section("the wall, and how much of it is drawn")

checkEqual(BrowseRules.wallItems([cwRow, item("")!]).count, 1, "a wall drops a row with no id")
checkEqual(BrowseRules.wallItems(nil).count, 0, "no payload is no rows")

// ⚠ 48 and 48 are the WEB APP's numbers (`FIRST_PAINT_CARDS` / `MOUNT_STEP`), mirrored. A 400-title wall
// must not be drawn in one go — on a TV every card also starts an image request and joins the focus engine.
checkEqual(BrowseRules.Mount.firstCount(10), 10, "a small wall mounts whole")
checkEqual(BrowseRules.Mount.firstCount(100), 48, "a big wall mounts the first paint only")
checkEqual(BrowseRules.Mount.firstCount(0), 0, "an empty wall mounts nothing")
checkEqual(BrowseRules.Mount.firstCount(-5), 0, "a nonsense total mounts nothing")

checkEqual(BrowseRules.Mount.mountedCount(100, extra: 0), 48, "nothing grown: the first paint")
checkEqual(BrowseRules.Mount.mountedCount(100, extra: 48), 96, "one step grown: 96 of 100")
checkEqual(BrowseRules.Mount.mountedCount(100, extra: 999), 100, "growth is capped at the wall's length")
checkEqual(BrowseRules.Mount.mountedCount(10, extra: 48), 10, "a small wall cannot be over-mounted")

checkEqual(BrowseRules.Mount.nextExtra(0, total: 100), 48, "the first growth step is a full step")
checkEqual(BrowseRules.Mount.nextExtra(48, total: 100), 52, "…and it stops at the room left, not past it")
checkEqual(BrowseRules.Mount.nextExtra(52, total: 100), 52, "…and then it is finished")
checkEqual(BrowseRules.Mount.nextExtra(0, total: 10), 0, "a wall already mounted has nothing to grow")

checkEqual(BrowseRules.Mount.needsMore(shown: 48, total: 100), true, "48 of 100 needs more")
checkEqual(BrowseRules.Mount.needsMore(shown: 100, total: 100), false, "100 of 100 needs nothing")
checkEqual(BrowseRules.Mount.needsMore(shown: 0, total: 0), false, "an empty wall needs nothing")

// MARK: - The request URL (Phase B4)

section("the request URL")

// ⚠⚠ THE TRAP THIS SECTION EXISTS FOR. `URL.appendingPathComponent(_:)` percent-escapes its whole argument,
// so a path carrying `?id=…` arrives as PART OF THE PATH and the api answers `404` on an item that exists —
// which on this screen wears the app's own "we couldn't find that title" copy, i.e. a transport bug
// presenting as a content bug. `PosterURL` carries the same finding; this is the JSON request's version.
checkEqual(RequestURL.url(base: base, path: "api/jellyfin/detail",
                          query: [URLQueryItem(name: "id", value: movieID)])?.absoluteString,
           "http://rkm-hp.tail8d5e8.ts.net:8124/api/jellyfin/detail?id=\(movieID)",
           "a parameterised request puts the parameter in the QUERY")
checkEqual(RequestURL.url(base: trailing, path: "api/jellyfin/detail",
                          query: [URLQueryItem(name: "id", value: movieID)])?.absoluteString,
           "http://rkm-hp.tail8d5e8.ts.net:8124/api/jellyfin/detail?id=\(movieID)",
           "an address ending in a slash does not double the slash")

// ⚠ The question mark must NOT be in the path — the guard is on the path itself, not on the whole string.
let detailURL = RequestURL.url(base: base, path: "api/jellyfin/detail",
                               query: [URLQueryItem(name: "id", value: movieID)])
checkEqual(detailURL?.path, "/api/jellyfin/detail", "the path is the route and nothing else")
if let detailURL, let components = URLComponents(url: detailURL, resolvingAgainstBaseURL: false) {
    checkEqual(components.queryItems?.first(where: { $0.name == "id" })?.value, movieID,
               "the id is the query's value")
} else {
    check(false, "the id is the query's value")
}

// ⚠ A Jellyfin id is hex, but the builder is not allowed to depend on that: a value with a space, a plus, a
// slash and an ampersand must survive as DATA rather than splitting the query.
if let awkward = RequestURL.url(base: base, path: "api/jellyfin/detail",
                               query: [URLQueryItem(name: "id", value: awkwardID)]),
   let components = URLComponents(url: awkward, resolvingAgainstBaseURL: false) {
    checkEqual(components.queryItems?.first(where: { $0.name == "id" })?.value, awkwardID,
               "an id with a space, a plus, a slash and an ampersand survives the round trip")
    check(!awkward.path.contains("+") && !awkward.path.contains("&"),
          "and does not leak into the path")
} else {
    check(false, "an id with a space, a plus, a slash and an ampersand survives the round trip")
}

// ⚠ NO query: the builder must behave EXACTLY as before (this is the path every earlier round exercised),
// including for the interpolated folder route.
checkEqual(RequestURL.url(base: base, path: "api/status")?.absoluteString,
           "http://rkm-hp.tail8d5e8.ts.net:8124/api/status",
           "a request with no parameters is the address plus the path")
checkEqual(RequestURL.url(base: base, path: "api/library/folders/abc/items")?.absoluteString,
           "http://rkm-hp.tail8d5e8.ts.net:8124/api/library/folders/abc/items",
           "…and an interpolated path still works without parameters")

// MARK: - The detail payload (Phase B4)

section("the detail payload")

/// ⚠ Built by DECODING, like every other fixture in this file, so a fixture cannot describe a shape the
/// wire does not produce. Shaped from `backend/services/library/jellyfin.py::_detail_from_item`
/// (read 2026-09-19): every key below is one that route actually sends.
let movieDetailJSON = #"""
{
  "type": "movie",
  "item_id": "f3c1a9e04b8d4e0a9b7c2d5e6f8a1b3c",
  "name": "Sholay",
  "year": 1975,
  "runtime": 7200,
  "runtime_ticks": 72000000000,
  "overview": "Two friends, a village and a bandit.",
  "genres": ["Action", "Drama"],
  "community_rating": 7.473,
  "official_rating": "AU-MA 15+",
  "studios": ["Sippy Films"],
  "people": {
    "actors": [
      { "id": "p1", "name": "Amitabh Bachchan", "role": "Jai", "has_image": true },
      { "id": "p2", "name": "Dharmendra", "role": "Veeru", "has_image": false }
    ],
    "directors": [ { "id": "p3", "name": "Ramesh Sippy", "role": "", "has_image": false } ],
    "writers": [ { "id": "p4", "name": "Salim Khan", "role": "Writer", "has_image": false } ]
  },
  "has_backdrop": true,
  "primary_aspect": 0.667,
  "play": { "played": false, "resume_ticks": 18000000000, "resume": 1800, "play_count": 1 }
}
"""#

/// ⚠ The PRESENT-AND-NULL case, which is what this api actually sends for a key it has no value for
/// (`_float` returns None). A model that required any of these would fail the whole screen for a title that
/// simply has no rating.
let nullsDetailJSON = #"""
{
  "type": "movie",
  "item_id": "f3c1a9e04b8d4e0a9b7c2d5e6f8a1b3c",
  "name": "Untitled",
  "year": null,
  "runtime": 0,
  "runtime_ticks": 0,
  "overview": "",
  "genres": [],
  "community_rating": null,
  "official_rating": null,
  "studios": [],
  "people": { "actors": [], "directors": [], "writers": [] },
  "has_backdrop": false,
  "primary_aspect": null,
  "play": { "played": false, "resume_ticks": 0, "resume": 0, "play_count": 0 }
}
"""#

let seriesDetailJSON = #"""
{
  "type": "tv",
  "item_id": "0b7e4d1c93a24f5e8c6d2b9a4e1f7c30",
  "name": "Some Show",
  "year": 2021,
  "runtime": 0,
  "runtime_ticks": 0,
  "overview": "A series.",
  "genres": ["Drama"],
  "community_rating": 8.0,
  "official_rating": "AU-M 15+",
  "studios": [],
  "people": { "actors": [], "directors": [], "writers": [] },
  "has_backdrop": true,
  "primary_aspect": 0.667,
  "play": { "played": false, "resume_ticks": 0, "resume": 0, "play_count": 0 }
}
"""#

/// An EPISODE's detail — the only one that carries the series context, and the only shape where
/// `season_id`/`season`/`episode` appear.
let episodeDetailJSON = #"""
{
  "type": "episode",
  "item_id": "1a2b3c4d5e6f708192a3b4c5d6e7f809",
  "name": "The Reckoning",
  "year": 2021,
  "runtime": 2700,
  "runtime_ticks": 27000000000,
  "overview": "",
  "genres": [],
  "community_rating": null,
  "official_rating": null,
  "studios": [],
  "people": { "actors": [], "directors": [], "writers": [] },
  "has_backdrop": false,
  "primary_aspect": null,
  "play": { "played": false, "resume_ticks": 12000000000, "resume": 1200, "play_count": 0 },
  "series": { "id": "0b7e4d1c93a24f5e8c6d2b9a4e1f7c30", "name": "Some Show" },
  "season_id": "aabbccddeeff00112233445566778899",
  "season": 1,
  "episode": 3
}
"""#

func detail(_ json: String) -> ItemDetail? {
    try? JSONDecoder().decode(ItemDetail.self, from: Data(json.utf8))
}

let movieDetail = detail(movieDetailJSON)
check(movieDetail != nil, "a real detail payload decodes")
checkEqual(movieDetail?.type, "movie", "the type survives")
checkEqual(movieDetail?.itemID, movieID, "item_id is the identity key, not id")
checkEqual(movieDetail?.name, "Sholay", "the name is `name`, not `title`")
checkEqual(movieDetail?.year, 1975, "the year survives")
checkEqual(movieDetail?.runtime, 7200, "the runtime survives")
checkEqual(movieDetail?.runtimeTicks, 72_000_000_000, "the raw ticks survive")
checkEqual(movieDetail?.genres, ["Action", "Drama"], "the genres survive")
checkEqual(movieDetail?.communityRating, 7.473, "the community rating survives")
checkEqual(movieDetail?.officialRating, "AU-MA 15+", "the certification survives")
checkEqual(movieDetail?.studios, ["Sippy Films"], "the studios survive")
checkEqual(movieDetail?.play.resume, 1800, "the resume position survives, in SECONDS")
checkEqual(movieDetail?.play.resumeTicks, 18_000_000_000, "…and in ticks")
checkEqual(movieDetail?.play.played, false, "the played flag survives")
checkEqual(movieDetail?.play.playCount, 1, "the play count survives")
checkEqual(movieDetail?.people?.actors.first?.name, "Amitabh Bachchan", "an actor's name survives")
checkEqual(movieDetail?.people?.actors.first?.role, "Jai", "an actor's character survives")
checkEqual(movieDetail?.people?.actors.first?.hasImage, true, "has_image survives")
checkEqual(movieDetail?.people?.writers.count, 1, "the writers group survives")

check(detail(nullsDetailJSON) != nil, "a payload of present-and-null values still decodes")
checkEqual(detail(nullsDetailJSON)?.year, nil, "a null year is nil, not zero")
checkEqual(detail(nullsDetailJSON)?.communityRating, nil, "a null rating is nil")
checkEqual(detail(nullsDetailJSON)?.officialRating, nil, "a null certification is nil")
checkEqual(detail(nullsDetailJSON)?.primaryAspect, nil, "a null aspect ratio is nil")
checkEqual(detail(nullsDetailJSON)?.runtime, 0, "a zero runtime is a number, not an absence")

// ⚠⚠ THE SAME TRIPWIRE AS `MediaItem`'s, on the detail payload: this one carries `id` instead of
// `item_id`, so it is a GLOBAL-SEARCH-shaped object and must not decode as a detail.
check(detail(#"{ "type": "movie", "id": "x", "name": "Sholay", "play": { "played": false, "resume_ticks": 0, "resume": 0, "play_count": 0 } }"#) == nil,
      "a payload with id instead of item_id does NOT decode")

// ⚠ `play` is PROMISED by the interface (non-optional), so its absence is a shape violation, not a title
// that has never been watched.
check(detail(#"{ "type": "movie", "item_id": "x", "name": "Sholay" }"#) == nil,
      "a detail payload without its play state is refused")
// …and so is a payload without a type or a name.
check(detail(#"{ "item_id": "x", "name": "Sholay" }"#) == nil, "a detail payload without a type is refused")
check(detail(#"{ "type": "movie", "item_id": "x" }"#) == nil, "a detail payload without a name is refused")
// ⚠ All three people groups are non-optional: the server always emits them, so a payload missing one is a
// shape violation rather than a title with no writers.
check(detail(#"{ "type": "movie", "item_id": "x", "name": "S", "people": { "actors": [], "directors": [] }, "play": { "played": false, "resume_ticks": 0, "resume": 0, "play_count": 0 } }"#) == nil,
      "a people object missing a group is refused")

let episodeDetail = detail(episodeDetailJSON)
checkEqual(episodeDetail?.type, "episode", "an episode's detail carries its type")
checkEqual(episodeDetail?.series?.id, seriesID, "an episode carries its series id")
checkEqual(episodeDetail?.series?.name, "Some Show", "…and its series name")
checkEqual(episodeDetail?.season, 1, "…and its season number")
checkEqual(episodeDetail?.episode, 3, "…and its episode number")
checkEqual(movieDetail?.series, nil, "a film carries no series context")

// MARK: - The detail's meta line and rating

section("the detail's meta line")

checkEqual(DetailRules.metaBits(movieDetail!, seasonCount: 0), ["1975", "2h", "AU-MA 15+"],
           "a film reads year · runtime · certification")
// ⚠ A series shows its SEASON COUNT and not its runtime, because Jellyfin stores a series' runtime as 0 —
// without this branch the segment would be dropped and a series would read "2021" alone.
checkEqual(DetailRules.metaBits(detail(seriesDetailJSON)!, seasonCount: 3),
           ["2021", "3 seasons", "AU-M 15+"], "a series reads its season count, not its runtime")
checkEqual(DetailRules.metaBits(detail(seriesDetailJSON)!, seasonCount: 1),
           ["2021", "1 season", "AU-M 15+"], "one season is singular")
checkEqual(DetailRules.metaBits(detail(seriesDetailJSON)!, seasonCount: 0), ["2021", "AU-M 15+"],
           "a series with no episodes drops the season segment rather than saying 0 seasons")
checkEqual(DetailRules.metaBits(detail(nullsDetailJSON)!, seasonCount: 0), [],
           "unknown values are dropped, so nothing is left to read")
checkEqual(DetailRules.seasonsText(6), "6 seasons", "six seasons is plural")
checkEqual(DetailRules.seasonsText(0), "", "no seasons says nothing")

section("the rating readout")

checkEqual(DetailRules.ratingText(7.473), "7.5", "a rating is one decimal")
checkEqual(DetailRules.ratingText(8.0), "8", "a whole rating drops the .0")
checkEqual(DetailRules.ratingText(9.96), "10", "a rating that rounds up to ten reads ten")
checkEqual(DetailRules.ratingText(0), "", "a zero rating says nothing")
checkEqual(DetailRules.ratingText(nil), "", "an absent rating says nothing")
checkEqual(DetailRules.ratingText(-1), "", "a nonsense rating says nothing")

// MARK: - The detail's play state

section("the detail's play state")

checkEqual(DetailRules.resumePercent(movieDetail!.play, runtimeSec: movieDetail!.runtime), 25,
           "a quarter watched is 25%")
checkEqual(DetailRules.resumePercent(movieDetail!.play, runtimeSec: 0), 0,
           "no runtime means no percentage")
checkEqual(DetailRules.resumePercent(nil, runtimeSec: 7200), 0, "no play state means no percentage")
checkEqual(DetailRules.resumePercent(DetailPlay(played: false, resumeTicks: 0, resume: 0, playCount: 1),
                                     runtimeSec: 7200), 0, "an untouched title has nothing to resume")
checkEqual(DetailRules.resumePercent(DetailPlay(played: true, resumeTicks: 18_000_000_000,
                                                resume: 1800, playCount: 1), runtimeSec: 7200), 0,
           "a finished title shows no resume bar")
checkEqual(DetailRules.resumePercent(DetailPlay(played: false, resumeTicks: 0, resume: 9999,
                                                playCount: 1), runtimeSec: 7200), 100,
           "a position past the end is still one bar, never more")

checkEqual(DetailRules.isInProgress(movieDetail!.play), true, "a half-watched film is in progress")
checkEqual(DetailRules.isInProgress(DetailPlay(played: true, resumeTicks: 0, resume: 1800, playCount: 1)),
           false, "a finished title is NOT in progress, even with a position on it")
checkEqual(DetailRules.isInProgress(nil), false, "no play state is not in progress")

checkEqual(DetailRules.primaryLabel(movieDetail!.play), "Resume", "mid-play the verb is Resume")
checkEqual(DetailRules.primaryLabel(nil), "Play", "otherwise it is Play")
checkEqual(DetailRules.primaryVerb(movieDetail!.play, runtimeSec: movieDetail!.runtime), "Resume (25%)",
           "the percentage rides on the verb — the web puts it there too")
checkEqual(DetailRules.primaryVerb(nil, runtimeSec: 7200), "Play", "an untouched title just says Play")

// MARK: - Episodes (Phase B4)

section("an episode's progress")

/// ⚠ Built by DECODING, so the fixture is the wire shape (`id`/`name`, `playback_position`).
func ep(_ season: Int, _ episode: Int, played: Bool = false, position: Int = 0,
        runtime: Int = 2700) -> EpisodeItem {
    // ⚠ Built with `JSONSerialization` from a DICTIONARY, not a hand-written JSON literal: the
    // fixture is still the wire shape (`id`/`name`, `playback_position`), and no string escaping sits
    // between the fixture and the model.
    let object: [String: Any] = [
        "id": "ep-S\(season)E\(episode)",
        "name": "Episode \(episode)",
        "season": season,
        "episode": episode,
        "played": played,
        "playback_position": position,
        "runtime": runtime,
    ]
    let data = try! JSONSerialization.data(withJSONObject: object)
    return try! JSONDecoder().decode(EpisodeItem.self, from: data)
}

checkEqual(DetailRules.episodeCode(ep(1, 4)), "S1E4", "an episode's code is S<season>E<number>")
// ⚠ The FIXTURE's own id, asserted: the builder interpolates it, and an escaping slip would ship a fixture
// whose ids are literally `ep-S\(season)E\(episode)` while every rule check still passed.
checkEqual(ep(1, 4).id, "ep-S1E4", "the fixture's id is built from the numbers")
checkEqual(DetailRules.episodeCode(season: 2, episode: 11), "S2E11",
           "…and it is built from the numbers, not the name")

let halfWatched = DetailRules.episodeProgress(ep(1, 3, position: 1200))
checkEqual(halfWatched.percent, 44, "1200 of 2700 seconds is 44%")
checkEqual(halfWatched.inProgress, true, "…and it is in progress")
checkEqual(halfWatched.remainingLabel, "25m left", "…with the time left, in the web's own words")
checkEqual(DetailRules.episodeProgress(ep(1, 3, played: true, position: 1200)).inProgress, false,
           "a watched episode is not in progress")
checkEqual(DetailRules.episodeProgress(ep(1, 3, played: true, position: 1200)).remainingLabel, "",
           "…and claims no time left")
// ⚠ `max(1, …)` floors the readout at a minute: an episode at its very end says "1m left", never an empty
// label, and never "0m left".
let atTheEnd = DetailRules.episodeProgress(ep(1, 3, position: 2700))
checkEqual(atTheEnd.percent, 100, "an episode at its end is 100%")
checkEqual(atTheEnd.remainingLabel, "1m left", "…and still reads 1m left")
// ⚠ The other half of that rule: no runtime means NO COUNTDOWN — a countdown against a length nobody knows
// reads as a bug on screen.
let noRuntime = DetailRules.episodeProgress(ep(1, 3, position: 500, runtime: 0))
checkEqual(noRuntime.percent, 0, "no runtime means no percentage")
checkEqual(noRuntime.remainingLabel, "", "…and no countdown")
checkEqual(DetailRules.playLabel(played: true, position: 0), "Replay", "a watched episode's verb is Replay")
checkEqual(DetailRules.playLabel(played: false, position: 60), "Resume", "a half-watched one resumes")
checkEqual(DetailRules.playLabel(played: false, position: 0), "Play", "an untouched one plays")

section("the next episode, and the seasons")

let seriesEpisodes = [ep(1, 1), ep(1, 2, position: 900), ep(1, 3), ep(2, 1)]
checkEqual(DetailRules.nextPlayableEpisode(seriesEpisodes)?.episode, 2,
           "a series mid-episode resumes THAT episode")
checkEqual(DetailRules.nextPlayableEpisode([ep(1, 1, played: true), ep(1, 2)])?.episode, 2,
           "with nothing in progress, the first unwatched episode is next")
checkEqual(DetailRules.nextPlayableEpisode([ep(1, 1, played: true), ep(1, 2, played: true)]), nil,
           "a fully watched series has no next episode")
// ⚠ Out-of-order arrival is the case the web's `sort` exists for, and it is the case a TV would otherwise
// resume the wrong episode on.
checkEqual(DetailRules.nextPlayableEpisode([ep(2, 1), ep(1, 1)])?.episode, 1,
           "the next episode is chosen by (season, episode), not by arrival order")

let grouped = DetailRules.groupBySeason([ep(2, 1), ep(1, 2), ep(1, 1), ep(2, 2)])
checkEqual(grouped.map(\.season), [1, 2], "seasons are ascending however the list arrives")
checkEqual(grouped.first?.episodes.map(\.episode), [2, 1],
           "…and the episodes INSIDE a season keep the server's order")
checkEqual(grouped.last?.episodes.map(\.episode), [1, 2], "…in every season")
checkEqual(DetailRules.groupBySeason([]).count, 0, "no episodes is no seasons")

checkEqual(DetailRules.seriesPlayLabel(target: ep(1, 2, position: 900), first: ep(1, 1)), "Resume S1E2",
           "a half-watched series resumes that episode by name")
checkEqual(DetailRules.seriesPlayLabel(target: ep(1, 2), first: ep(1, 1)), "Play S1E2",
           "an unwatched target plays that episode")
checkEqual(DetailRules.seriesPlayLabel(target: nil, first: ep(1, 1)), "Replay S1E1",
           "a finished series offers a replay of the first episode")
checkEqual(DetailRules.seriesPlayLabel(target: nil, first: nil), "Play",
           "with no episode list there is nothing to name — the screen says so separately")

// MARK: - The detail screen's value (Phase B4)

section("the detail screen's snapshot")

let movieSnapshot = DetailSnapshot(detail: movieDetail!, episodes: [], episodesFailed: false)
checkEqual(movieSnapshot.isSeries, false, "a film is not a series")
checkEqual(movieSnapshot.showsEpisodes, false, "…and has no episode list to draw")
checkEqual(movieSnapshot.metaBits, ["1975", "2h", "AU-MA 15+"], "the snapshot carries the meta line")
checkEqual(movieSnapshot.rating, "7.5", "…and the rating")
checkEqual(movieSnapshot.resumePercent, 25, "…and the resume percentage")
checkEqual(movieSnapshot.isInProgress, true, "…and the in-progress flag")
checkEqual(movieSnapshot.primaryVerb, "Resume (25%)", "…and the verb it will offer")
checkEqual(movieSnapshot.partialWarning, nil, "a film can never be partial — it asked for no episode list")
checkEqual(movieSnapshot.directorLine, "Director: Ramesh Sippy", "the director line reads the web's words")
checkEqual(movieSnapshot.writerLine, "Writer: Salim Khan", "…and so does the writer line")
checkEqual(movieSnapshot.studiosLine, "Sippy Films", "the studios are joined for one line")
checkEqual(movieSnapshot.cast.map(\.name), ["Amitabh Bachchan", "Dharmendra"],
           "the cast is the actors, in the server's order")
checkEqual(movieSnapshot.overview, "Two friends, a village and a bandit.", "the synopsis survives")

// ⚠ episodesFailed on a FILM is ignored on purpose: a film requests no episode list, so a warning about one
// would be a lie on every movie page.
checkEqual(DetailSnapshot(detail: movieDetail!, episodes: [], episodesFailed: true).partialWarning, nil,
           "a film with a failed episode list still shows no episode warning")

let seriesSnapshot = DetailSnapshot(detail: detail(seriesDetailJSON)!, episodes: seriesEpisodes,
                                    episodesFailed: false)
checkEqual(seriesSnapshot.isSeries, true, "a series is a series when the SERVER says so")
checkEqual(seriesSnapshot.showsEpisodes, true, "…and draws its episode list")
checkEqual(seriesSnapshot.seasons.count, 2, "…grouped into its seasons")
checkEqual(seriesSnapshot.primaryVerb, "Resume S1E2", "…and its verb names the next episode")
checkEqual(seriesSnapshot.partialWarning, nil, "a complete answer has no warning")

// ⚠⚠ THE PARTIAL CASE. A series whose episode list did not arrive must not look like a series with no
// episodes: the sentence is on the snapshot (and therefore on the screen) and the verb drops to "Play",
// because without the list the app does not know which episode.
let partial = DetailSnapshot(detail: detail(seriesDetailJSON)!, episodes: [], episodesFailed: true)
checkEqual(partial.showsEpisodes, true, "a failed episode list still draws the section")
checkEqual(partial.episodes.count, 0, "…with nothing in it")
checkEqual(partial.partialWarning, "Couldn't load the episode list.", "…and says so")
checkEqual(partial.primaryVerb, "Play", "…and does not invent an episode to resume")

checkEqual(DetailRules.castRows(detail(movieDetailJSON)!.people).count, 2, "the cast is the actors")
checkEqual(DetailRules.castRows(nil).count, 0, "no people is no cast")
// ⚠ The cap is the web's `slice(0, 10)`, and a rail that decides for itself is a rail nobody scrolls.
let manyPeople = (1...15).map { _ in DetailPerson(id: "p", name: "N", role: "r", hasImage: false) }
checkEqual(DetailRules.castRows(DetailPeople(actors: manyPeople, directors: [], writers: [])).count, 10,
           "the cast rail is capped at ten")
checkEqual(DetailRules.castRows(DetailPeople(actors: [DetailPerson(id: "p", name: "", role: "r",
                                                                   hasImage: false)],
                                             directors: [], writers: [])).count, 0,
           "a person with no name is not a cast member")
checkEqual(DetailRules.creditsLine(nil, kind: .directors), nil, "no people means no credits line")
checkEqual(DetailRules.creditsLine(DetailPeople(actors: [], directors: [DetailPerson(id: "a", name: "A",
                                                                                     role: "", hasImage: false),
                                                                           DetailPerson(id: "b", name: "B",
                                                                                        role: "", hasImage: false)],
                                              writers: []), kind: .directors),
           "Directors: A, B", "two directors are Directors")
checkEqual(DetailRules.studiosLine(["A", "", "B"]), "A · B", "an empty studio is not a segment")

section("the detail screen's copy")

// ⚠⚠ PINNED AGAINST THE LITERAL WORDS, never against the constant that produces them — a comparison against
// `DetailCopy.x` moves with the constant and stays green, which is the TAUTOLOGY the B2 falsification pass
// caught. Copy is a rule; it is checked against itself only by accident.
checkEqual(DetailCopy.notFoundTitle, "We couldn't find that title in the library.",
           "the not-found title is the web app's own sentence")
checkEqual(DetailCopy.notFoundSub, "It may have been removed or the link is stale.",
           "…and so is the sub-line")
checkEqual(DetailCopy.partialWarning, "Couldn't load the episode list.",
           "the partial warning names the part that failed")
checkEqual(DetailCopy.playPendingTitle, "Playback", "the placeholder is labelled Playback")
checkEqual(DetailCopy.playPendingSub, "Arrives with the tvOS player (Phase C).",
           "…and says where playback comes from, because this screen cannot play")
checkEqual(DetailCopy.nextUp("Resume S1E4"), "Next up: Resume S1E4",
           "the screen names the verb it WILL offer, in the phone's own words")
checkEqual(DetailCopy.watchedWord, "Watched", "a watched episode reads Watched")

let states: [DetailState] = [.loading, .notFound, .failed("boom"), .content(movieSnapshot)]
check(states.allSatisfy { $0.snapshot == nil || $0.snapshot == movieSnapshot },
      "only the content state carries a snapshot")
checkEqual(states.compactMap(\.failureMessage), ["boom"], "only the failed state carries a sentence")

// MARK: - The Profile Switcher's rules (Phase U2)

section("the profile tiles")

/// ⚠ Built by DECODING, like every other fixture here, so it cannot describe a shape the wire does not
/// produce — and `ProfileUser` carries no optional beyond its five required fields.
func profile(_ id: String, _ name: String, admin: Bool = false, password: Bool = false,
             disabled: Bool = false) -> ProfileUser? {
    let json = "{\"id\": \"\(id)\", \"name\": \"\(name)\", \"is_admin\": \(admin), "
        + "\"has_password\": \(password), \"disabled\": \(disabled), \"last_login\": \"\"}"
    return try? JSONDecoder().decode(ProfileUser.self, from: Data(json.utf8))
}

// ⚠⚠ THE AVATAR'S INITIALS. The buildspec's four examples (`ME`, `RA`, `RK`, `SH`) are all single names and
// are all first-two-letters; the multi-word branch is a NEW tvOS decision (stated in `ProfileRules`), so it is
// pinned here rather than left to a view.
checkEqual(ProfileRules.initials("meenu"), "ME", "meenu reads ME")
checkEqual(ProfileRules.initials("sharanya"), "SH", "sharanya reads SH")
checkEqual(ProfileRules.initials("Raj Kumar"), "RK", "a two-word name reads its two initials")
checkEqual(ProfileRules.initials("Raj  Kumar  Singh"), "RK", "a third word is not part of the initials")
checkEqual(ProfileRules.initials("   "), "?", "a name with nothing in it still draws something")
checkEqual(ProfileRules.initials("raj2"), "RA", "a digit is not an initial")

// ⚠⚠ THE WORDS. His decision, 2026-09-19: the APP's vocabulary wins and the buildspec's `"Profile · password"`
// set is not adopted (it cannot express the disabled case at all). Pinned against the literals, never against
// the expression that produces them — a comparison against `ProfileRules.subtitle` itself would be a TAUTOLOGY.
let plainProfile = profile("u1", "sharanya")!
let lockedProfile = profile("u2", "meenu", password: true)!
let adminProfile = profile("u3", "rkm", admin: true)!
let disabledProfile = profile("u4", "raj", disabled: true)!
checkEqual(ProfileRules.subtitle(plainProfile), "No password", "an open profile says No password")
checkEqual(ProfileRules.subtitle(lockedProfile), "Password protected", "a locked profile says Password protected")
checkEqual(ProfileRules.subtitle(adminProfile), "Administrator — asks for a password",
           "the administrator says what it will ask for")
// ⚠ DISABLED OUTRANKS EVERYTHING: a disabled administrator must not read "asks for a password", because it
// cannot be selected at all.
checkEqual(ProfileRules.subtitle(profile("u5", "raj", admin: true, disabled: true)!),
           "Disabled — cannot be selected", "a disabled administrator says it cannot be selected")

checkEqual(ProfileRules.accessibilityLabel(lockedProfile), "meenu, profile, password protected",
           "a locked tile reads its lock to a screen reader")
checkEqual(ProfileRules.accessibilityLabel(adminProfile), "rkm, administrator, password protected",
           "the administrator says so out loud")
checkEqual(ProfileRules.accessibilityLabel(plainProfile), "sharanya, profile, no password",
           "an open profile says it needs nothing")
checkEqual(ProfileRules.accessibilityLabel(disabledProfile), "raj, profile, disabled",
           "a disabled tile is not merely dimmed for a screen reader")

section("the profile eyebrow")

checkEqual(ProfileRules.eyebrow(profileCount: 4, signedInAs: "rkm"),
           "4 profiles on this server · Signed in as rkm", "the eyebrow counts the profiles and names the account")
checkEqual(ProfileRules.eyebrow(profileCount: 1, signedInAs: "rkm"),
           "1 profile on this server · Signed in as rkm", "one profile is singular")
checkEqual(ProfileRules.eyebrow(profileCount: 0, signedInAs: nil), "0 profiles on this server",
           "with no account name there is no dangling separator")
checkEqual(ProfileRules.eyebrow(profileCount: 2, signedInAs: "   "), "2 profiles on this server",
           "a blank account name is not a name")

section("who may administer")

let household = [plainProfile, lockedProfile, adminProfile]
// ⚠⚠ MATCHED BY ID, NOT BY NAME — and the fixture is built so the difference is VISIBLE: `lockedProfile` is
// the one named `meenu`, and a name match would make it the administrator. The name is what a rename changes;
// the buildspec's own example data (`rkm` looks like the administrator) is exactly this trap.
checkEqual(ProfileRules.isAdministrator(signedInUserID: "u3", profiles: household), true,
           "the signed-in administrator is recognised")
checkEqual(ProfileRules.isAdministrator(signedInUserID: "u2", profiles: household), false,
           "a member is not the administrator, whatever they are called")
checkEqual(ProfileRules.isAdministrator(signedInUserID: "nobody", profiles: household), false,
           "an id nobody matches is not an administrator")
checkEqual(ProfileRules.isAdministrator(signedInUserID: nil, profiles: household), false,
           "an unknown signed-in account is not an administrator")
checkEqual(ProfileRules.isAdministrator(signedInUserID: "", profiles: household), false,
           "an empty signed-in id is not an administrator")
checkEqual(ProfileRules.isAdministrator(signedInUserID: "u3", profiles: []), false,
           "no profiles means no administrator — the admin controls are not offered on a guess")

// MARK: - The backdrop route (Phase U3)

section("the backdrop URL")

// ⚠ The hero band needs 16:9 artwork beside the cards' 2:3 posters, and it is the SAME builder with the other
// route word — the trap the poster half pins (`appendingPathComponent(_:)` escaping a query into the PATH)
// applies here identically, which is the whole reason the two are one function.
checkEqual(PosterURL.path(itemID: movieID, route: .backdrop),
           "api/jellyfin/backdrop?id=\(movieID)&width=1600",
           "a backdrop path is the backdrop route at the backdrop width")
checkEqual(PosterURL.path(itemID: movieID), "api/jellyfin/poster?id=\(movieID)&width=500",
           "…and the default route is still the poster at 500")
check(PosterURL.path(itemID: "", route: .backdrop) == nil, "an empty id builds no backdrop either")
checkEqual(PosterURL.clamped(99_999, route: .backdrop), 4000,
           "a backdrop width above its own ceiling is lowered to it")
checkEqual(PosterURL.clamped(99_999), 2000, "…while the poster's ceiling is unchanged")
checkEqual(PosterURL.clamped(0, route: .backdrop), 16, "the backdrop's floor is the server's 16 as well")
checkEqual(PosterURL.url(base: trailing, itemID: movieID, route: .backdrop)?.absoluteString,
           "http://rkm-hp.tail8d5e8.ts.net:8124/api/jellyfin/backdrop?id=\(movieID)&width=1600",
           "a backdrop URL is the backdrop route")
checkEqual(PosterURL.url(base: base, itemID: movieID, width: 800, route: .backdrop)?.absoluteString,
           "http://rkm-hp.tail8d5e8.ts.net:8124/api/jellyfin/backdrop?id=\(movieID)&width=800",
           "a given backdrop width is carried")
check(PosterURL.url(base: base, itemID: "", route: .backdrop) == nil,
      "an empty id builds no absolute backdrop URL either")

// MARK: - The hero (Phase U3)

section("the hero's pick")

// ⚠⚠ MIRRORED from `lib.ts::pickHomeHero`, and the TIERS are the rule. `movie` (Sholay: in progress, 620 of
// 7200) and `episode` (1200 of 2700) are the fixtures decoded at the top of this file.
let finishedWithPosition = item("f1", ", \"played\": true, \"playback_position\": 100, \"runtime\": 1000")!
let inProgressShow = item("s1", ", \"type\": \"tv\", \"playback_position\": 30, \"runtime\": 600")!

checkEqual(HomeRules.homeHero(continueWatching: [episode!, movie!], recentlyAdded: [], all: [])?.itemID,
           movieID, "an in-progress MOVIE takes the hero before an episode")
checkEqual(HomeRules.homeHero(continueWatching: [episode!], recentlyAdded: [], all: [])?.itemID,
           "1a2b3c4d5e6f708192a3b4c5d6e7f809", "an episode takes the hero when no movie is in progress")
// ⚠⚠ A FINISHED title never takes the spotlight, even with a position left on it: a hero that says "Resume"
// over something already watched is a lie.
checkEqual(HomeRules.homeHero(continueWatching: [finishedWithPosition], recentlyAdded: [], all: []),
           nil, "a finished title never takes the hero")
checkEqual(HomeRules.homeHero(continueWatching: [], recentlyAdded: [item("r1")!], all: [])?.itemID, "r1",
           "the most recently added title takes the hero when nothing is in progress")
checkEqual(HomeRules.homeHero(continueWatching: [], recentlyAdded: [], all: [inProgressShow, item("a1")!])?.itemID,
           "a1", "the whole-library fallback prefers a film")
checkEqual(HomeRules.homeHero(continueWatching: [], recentlyAdded: [], all: [inProgressShow])?.itemID, "s1",
           "…and falls back to whatever there is")
checkEqual(HomeRules.homeHero(continueWatching: [], recentlyAdded: [], all: []), nil,
           "an empty library has no hero")
checkEqual(HomeRules.homeHero(continueWatching: [item("")!], recentlyAdded: [], all: []), nil,
           "a row with no id cannot be the hero")

section("the hero title and its exclusion")

// ⚠ HIS RULE (2026-09-17): the title the hero is showing is REMOVED from the rail below, or the same film
// appears twice on one page — once big at the top, once as the first card.
let heroRail = [item("a")!, item("b")!, item("c")!]
checkEqual(HomeRules.withoutHero(heroRail, hero: item("b")!).map(\.itemID), ["a", "c"],
           "the hero's title is excluded from the rail below it")
checkEqual(HomeRules.withoutHero(heroRail, hero: nil).count, 3, "no hero removes nothing")
// ⚠⚠ THE SENTINEL RULE: an id-less hero must not match an id-less row. `"" == ""` is true, and this repo has
// lost a bug to precisely that (`entryForHit` matched every live hit to the first id-less watchlist entry).
checkEqual(HomeRules.withoutHero([item("")!, item("a")!], hero: item("")!).count, 2,
           "a hero with no id removes nothing — never the first row with an empty id")

checkEqual(HomeRules.heroTitle(episode!), "Some Show", "an episode's hero is titled with its series")
checkEqual(HomeRules.heroTitle(movie!), "Sholay", "a film's hero is titled with the film")

section("the hero's copy and numbers")

checkEqual(HomeRules.heroEyebrow(continueWatching: true, isEpisode: false), "Continue Watching",
           "a continue-watching hero says Continue Watching")
checkEqual(HomeRules.heroEyebrow(continueWatching: true, isEpisode: true), "Continue episode",
           "an in-progress episode says Continue episode")
checkEqual(HomeRules.heroEyebrow(continueWatching: false, isEpisode: false), "Recently Added",
           "a hero that is not continue watching says Recently Added")

checkEqual(HomeRules.heroPrimaryLabel(isEpisode: false, episodeCode: "", isSeries: false, percent: 9),
           "Resume", "a part-watched film resumes")
checkEqual(HomeRules.heroPrimaryLabel(isEpisode: false, episodeCode: "", isSeries: false, percent: 0),
           "Play", "an unwatched film plays")
checkEqual(HomeRules.heroPrimaryLabel(isEpisode: false, episodeCode: "", isSeries: true, percent: 0),
           "Explore Episodes", "a series is explored, never played")
checkEqual(HomeRules.heroPrimaryLabel(isEpisode: true, episodeCode: "S1E3", isSeries: false, percent: 44),
           "Resume S1E3", "a half-watched episode names the episode it resumes")
checkEqual(HomeRules.heroPrimaryLabel(isEpisode: true, episodeCode: "S1E3", isSeries: false, percent: 0),
           "Play S1E3", "an unwatched episode names the episode it plays")
checkEqual(HomeRules.heroPrimaryLabel(isEpisode: true, episodeCode: "", isSeries: false, percent: 0),
           "Play", "an episode with no code does not leave a dangling space")

// ⚠ The hero's own meta format, `year · S1 E3 · genre · genre` — note the SPACE in `S1 E3`, which is NOT the
// card's `S1E3`. Both are the web app's, character for character.
checkEqual(HomeRules.heroMetaLine(movie!), "1975 · Action · Drama", "the hero's meta reads year and genres")
checkEqual(HomeRules.heroMetaLine(item("g", ", \"year\": 2001, \"genres\": [\"A\", \"B\", \"C\"]")!),
           "2001 · A · B", "the hero's meta keeps only two genres")
checkEqual(HomeRules.heroMetaLine(episode!), "S1 E3", "an episode's hero meta carries its code, spaced")
checkEqual(HomeRules.heroMetaLine(item("n")!), "", "a row with nothing to say says nothing")

checkEqual(HomeRules.heroPercent(movie!), 9, "the hero's percentage is rounded (620 of 7200 is 9%)")
checkEqual(HomeRules.heroPercent(episode!), 44, "…and 1200 of 2700 is 44%")
checkEqual(HomeRules.heroPercent(item("z")!), 0, "no runtime means no percentage")
checkEqual(HomeRules.heroPercent(item("z2", ", \"playback_position\": 10, \"runtime\": 0")!), 0,
           "a zero runtime means no percentage")

checkEqual(HomeRules.heroRuntimeLeft(movie!), "1h 50m", "a film counts down what is left")
checkEqual(HomeRules.heroRuntimeLeft(item("done", ", \"playback_position\": 600, \"runtime\": 600")!), "",
           "a finished film has no countdown")
// ⚠ The clause the falsification pass made load-bearing once the redundant `runtime > position` half went:
// without `position > 0` an unstarted film would read its WHOLE runtime as "time left".
checkEqual(HomeRules.heroRuntimeLeft(item("zero", ", \"playback_position\": 0, \"runtime\": 600")!), "",
           "an unstarted film has no countdown")
checkEqual(HomeRules.heroRuntimeLeft(inProgressShow), "", "a series measures episodes, not minutes")
checkEqual(HomeRules.heroRuntimeLeft(episode!), "", "an episode has its own code, not a countdown")
check(HomeRules.heroShowsProgress(movie!), "a film with progress draws the hero's bar")
check(HomeRules.heroShowsProgress(episode!), "an episode with progress draws the hero's bar")
check(!HomeRules.heroShowsProgress(inProgressShow), "a series draws no countdown bar")

checkEqual(HomeRules.typeIcon(inProgressShow), .tv, "a series gets the tv glyph")

// ⚠⚠ THE CARD'S BADGE (U6). The prototype puts a text chip on the artwork — `S2·E4` / `MOVIE` — and this is
// the rule that decides what it says. Pinned against the literal words, never against the expression.
checkEqual(HomeRules.badgeText(episode!), "S1E3", "an episode's badge is the app's own S1E3 code")
checkEqual(HomeRules.badgeText(movie!), "MOVIE", "a film's badge says MOVIE")
checkEqual(HomeRules.badgeText(inProgressShow), "SERIES", "a series with no episode badge says SERIES")
checkEqual(HomeRules.typeIcon(movie!), .film, "a film gets the film glyph")

// MARK: - The top bar's tabs (Phase U3)

section("the top bar's tabs")

let tabResolved = library("Movies", ok: true, folderID: "abc")!
let tabUnresolved = library("Old TV", ok: false, folderID: "ghost", collectionType: "tvshows",
                            warning: "Path not found on the server")!
let tabEntries = BrowseRules.browseEntries(libraries: [tabResolved, tabUnresolved], serverFolders: [])

// ⚠⚠ THE BUILDSPEC'S FIXED TAB LIST IS REJECTED IN WRITING, and this is the check that says so: the tabs come
// from `BrowseRules.browseEntries` — the SAME rule the Browse screen uses — so a profile's libraries and the
// Browse list can never disagree, and an unresolved library keeps its row and its warning.
checkEqual(tabEntries.count, 2, "the tabs are this profile's libraries, from the one rule")
checkEqual(tabEntries.first?.isOpenable, true, "a resolved library opens")
checkEqual(tabEntries.last?.isOpenable, false, "an unresolved library is a tab that explains itself")

let withTabs = snapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([playedRow]),
                        nav: .loaded(tabEntries))
checkEqual(withTabs.navEntries.count, 2, "the snapshot publishes the tabs the top bar draws")

// ⚠ A tab row that FAILED is named in the footer beside a rail that failed: a top bar with no tabs because
// the fetch died looks exactly like a profile with no libraries, and only one of those is worth acting on.
let withTabsFailed = snapshot(continueWatching: .failed("boom"), recentlyPlayed: .loaded([playedRow]),
                              nav: .failed("Couldn't reach the server."))
checkEqual(withTabsFailed.failedRowTitles, ["Continue Watching", "Libraries"],
           "a failed tab row is named in the footer, beside the rail that failed")

let navFailed = snapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([playedRow]),
                         nav: .failed("Couldn't reach the server."))
checkEqual(navFailed.navEntries.count, 0, "a failed tab row draws no tabs")
check(navFailed.placeholder == nil, "…but does not blank a screen that has content")
// ⚠ The mixed case again, one tier up: NOTHING to show AND a failed tab row must not read as an empty
// library — half the answer never arrived.
checkEqual(snapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([]),
                    nav: .failed("boom")).placeholder?.title, "Couldn't load your library",
           "with nothing to show, a failed tab row takes the screen rather than claiming the library is empty")

section("the hero in the snapshot")

// ⚠ The two sides of the exclusion, together: the hero is chosen from what was fetched, and the rail below it
// is built from the SAME snapshot with the hero taken out.
let heroSnapshot = snapshot(continueWatching: .loaded([movie!, playedRow]), recentlyPlayed: .loaded([]))
checkEqual(heroSnapshot.hero?.itemID, movieID, "the snapshot picks the hero from its own inputs")
checkEqual(heroSnapshot.heroIsContinueWatching, true, "…and says it came from Continue Watching")
checkEqual(heroSnapshot.rails.first?.items.map(\.itemID), [playedRow.itemID],
           "…and the rail below it excludes the hero")

let recentHero = snapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([]),
                          libraryRecent: .loaded([item("r1")!]))
checkEqual(recentHero.hero?.itemID, "r1", "a hero from the recently-added list is still a hero")
checkEqual(recentHero.heroIsContinueWatching, false, "…and does not claim to be Continue Watching")

let idlessHero = snapshot(continueWatching: .loaded([item("")!]), recentlyPlayed: .loaded([]),
                          libraryItems: .loaded([item("")!, item("a1")!]))
checkEqual(idlessHero.hero?.itemID, "", "an id-less fallback can still be the hero of an empty-ish library")
checkEqual(idlessHero.heroIsContinueWatching, false,
           "…and is never claimed to have come from Continue Watching (the empty-id sentinel)")

// MARK: - The third rail (Phase U4)

section("the third rail")

// ⚠⚠ **THE RULE AND THE CAP ARE B1's AND WERE UNUSED UNTIL U4** — `HomeRails`' own header said the third row
// *"lands with the rail it needs rather than being built dead now"*. These are the checks that only became
// true when it landed; the rule's own checks (`recentlyAddedItems` capped at 16 and id-filtered) are above.
let manyAdded = (1...20).compactMap { item("ra\($0)") }
let threeRails = snapshot(continueWatching: .loaded([cwRow, cwRow2]),
                          recentlyPlayed: .loaded([playedRow]),
                          libraryRecent: .loaded(manyAdded))
checkEqual(threeRails.rails.map(\.id), [.continueWatching, .recentlyPlayed, .recentlyAdded],
           "Recently Added is the THIRD rail")
checkEqual(threeRails.rails.last?.title, "Recently Added",
           "the third rail has the web app's own heading")
checkEqual(threeRails.rails.last?.items.count, 16, "the third rail is capped at 16, like the web's")
checkEqual(threeRails.rails.last?.items.first?.itemID, "ra1", "the third rail keeps the server's order")

checkEqual(snapshot(continueWatching: .loaded([]), recentlyPlayed: .loaded([]),
                    libraryRecent: .loaded([item("ra1")!, item("")!])).rails.last?.items.count, 1,
           "a Recently Added row with no id is dropped from the rail")

// ⚠⚠ THE EXCLUSION IS ONE-SIDED, and that is the web app's shape: `withoutHero` is applied to Continue
// Watching ONLY. A title can be the hero AND be the newest thing in the library — removing it from the added
// rail as well would hide it from the one row that says "this is new".
let heroIsNewest = snapshot(continueWatching: .loaded([movie!]), recentlyPlayed: .loaded([]),
                            libraryRecent: .loaded([movie!]))
checkEqual(heroIsNewest.rails.first?.id, .recentlyAdded, "the hero is excluded from Continue Watching…")
checkEqual(heroIsNewest.rails.first?.items.map(\.itemID), [movieID],
           "…and NOT from Recently Added")

checkEqual(snapshot(continueWatching: .loaded([cwRow, cwRow2]), recentlyPlayed: .loaded([]),
                    libraryRecent: .failed("boom")).failedRowTitles, ["Recently Added"],
           "a failed Recently Added fetch is named in the footer")

// ⚠ …and the fetch failing must not make the row look EMPTY: nothing renders, and the footer explains it.
checkEqual(snapshot(continueWatching: .loaded([cwRow, cwRow2]), recentlyPlayed: .loaded([]),
                    libraryRecent: .failed("boom")).rails.map(\.id), [.continueWatching],
           "a failed Recently Added fetch renders no third rail")

// MARK: - The library grid's rules (Phase V)

// ⚠⚠ EVERY ONE OF THESE IS A PORT OF `frontend/src/features/library/lib.ts`, which the desktop, the phone
// and the iPad already run. The tie-breaks are where a port goes silently wrong — each comparator falls back
// to `cmpRecentDesc`, and two of them have a leading rule of their own.

section("the library grid's chips")

let chipRows = [
    item("g1", ", \"genres\": [\"Action\", \"Drama\"]"),
    item("g2", ", \"genres\": [\"drama\", \"Drama\", \"\"]"),
    item("g3"),
]

// ⚠ The empty name and the duplicate both go; `Drama` sorts before `drama` because the web's sort is
// code-unit and this one must agree with it (localeCompare is explicitly NOT what the web uses here).
checkEqual(LibraryRules.genres(chipRows.compactMap { $0 }), ["Action", "Drama", "drama"],
           "genres are unique and code-unit sorted")
checkEqual(LibraryRules.genres([item("g4", ", \"genres\": [\"\", \"Action\"]")!]), ["Action"],
           "an empty genre name is dropped")

checkEqual(LibraryRules.chipTitles(genres: ["Action"]), ["All", "Action"], "All is the first chip")
check(LibraryRules.isSelected(chip: "All", genre: ""), "All is selected when nothing is filtered")
check(!LibraryRules.isSelected(chip: "Action", genre: ""), "no genre chip is selected while All is")
check(LibraryRules.isSelected(chip: "Action", genre: "Action"), "the active genre chip is the selected one")
check(!LibraryRules.isSelected(chip: "All", genre: "Action"), "All stops being selected once a genre filters")
checkEqual(LibraryRules.genre(forChip: "All"), "",
           "All clears the filter rather than filtering by the word 'All'")
checkEqual(LibraryRules.genre(forChip: "Drama"), "Drama", "a genre chip filters by its own name")

checkEqual(LibraryRules.countLabel(shown: 140, total: 140, genre: ""), "140 titles",
           "unfiltered count is the web's own line, not '140 of 140'")
checkEqual(LibraryRules.countLabel(shown: 1, total: 1, genre: ""), "1 title", "one title is singular")
checkEqual(LibraryRules.countLabel(shown: 12, total: 140, genre: "Action"), "12 titles in Action",
           "a filtered count names the genre")
checkEqual(LibraryRules.countLabel(shown: 1, total: 140, genre: "Drama"), "1 title in Drama",
           "a filtered count of one is singular")

section("the grid's arithmetic")

// ⚠⚠ THE CARD'S WIDTH IS AN INVARIANT, not a hope: `repeat(6, 1fr)` with a `64px` page margin and a `28px`
// column gap, pinned to the platform's 1920pt canvas. This is the same trade as the profile row's fit — the
// alternative is finding out on his television.
// ⚠⚠ **AND IT IS NOW BOUND TO `u`, WHICH IS HOW THE VIEW FINDS IT** (`BrowseView.cardWidth` uses
// `TVTokens.u * 100` instead of measuring a container). `u` is DEFINED as one percent of the screen's width,
// so "the canvas is 100u" is the identity that makes the constant below correct — and pinning it here is what
// stops the view's constant and this arithmetic from becoming one rule in two places.
check(abs(TVTokens.u * 100 - 1920) < 0.001,
      "the platform's canvas is 100u wide — the identity the grid's card width is derived from")
check(abs(LibraryRules.cardWidth(containerWidth: TVTokens.u * 100) - 263.72) < 0.01,
      "six columns at 1920pt are 263.72pt wide")
check(abs(LibraryRules.cardWidth(containerWidth: TVTokens.u * 100) * TVTokens.Grid.cardAspect - 395.58) < 0.01,
      "a 2:3 card at that width is 395.58pt tall")
check(abs(6 * LibraryRules.cardWidth(containerWidth: TVTokens.u * 100)
          + 5 * TVTokens.Grid.columnGap
          + 2 * LibraryRules.marginFromPrototype - 1920) < 0.01,
      "six cards, five gaps and two margins are exactly the screen")
check(abs(LibraryRules.marginFromPrototype - TVTokens.Metric.safeMargin) < 0.001,
      "the grid's margin IS the app's one margin")
checkEqual(LibraryRules.cardWidth(containerWidth: 1920, columns: 0), 0,
           "no columns is no width, not a crash")

section("the library's dates")

// ⚠ Jellyfin emits 7-digit fractional seconds, which some date parsers reject outright. Measured on this
// machine 2026-09-20: `ISO8601DateFormatter` ACCEPTS them (with `.withFractionalSeconds`) and REJECTS a
// timestamp with no fraction — so both forms are needed, and the second is what stops every fraction-less
// row sorting last.
check(LibraryRules.addedTime(item("d1", ", \"added\": \"2024-05-06T12:34:56.0000000Z\"")!) != nil,
      "a 7-digit fractional timestamp parses")
check(LibraryRules.addedTime(item("d2", ", \"added\": \"2024-05-06T12:34:56Z\"")!) != nil,
      "a timestamp with no fraction parses too")
check(LibraryRules.addedTime(item("d3", ", \"added\": \"not a date\"")!) == nil,
      "an unparseable date is nil, never a fabricated one")
check(LibraryRules.addedTime(item("d4")!) == nil, "a missing added date is nil")
checkEqual(LibraryRules.normaliseFractionalSeconds("2024-05-06T12:34:56.0000000Z"),
           "2024-05-06T12:34:56.000Z", "seven fraction digits are trimmed to three")
checkEqual(LibraryRules.normaliseFractionalSeconds("2024-05-06T12:34:56.123Z"),
           "2024-05-06T12:34:56.123Z", "three digits are left alone")
checkEqual(LibraryRules.normaliseFractionalSeconds("2024-05-06T12:34:56Z"),
           "2024-05-06T12:34:56Z", "no fraction is left alone")

section("the eight sorts")

let older = item("older", ", \"year\": 1999, \"runtime\": 7200, \"added\": \"2024-01-01T00:00:00.0000000Z\"")!
let newer = item("newer", ", \"year\": 2024, \"runtime\": 3600, \"added\": \"2025-01-01T00:00:00.0000000Z\"")!
// ⚠ No `added` at all — the row that must sort LAST and never first.
let nodate = item("nodate", ", \"year\": 2010, \"runtime\": 5400")!
// ⚠ Played AND carrying a resume position, because that is the only shape where the `progress` rule's
// `i.played` clause is observable: the real rule scores it 0, and a port that dropped `played` would sort it
// FIRST as 100 % watched.
let finished = item("played", ", \"played\": true, \"playback_position\": 3600, \"runtime\": 3600, \"added\": \"2024-06-01T00:00:00.0000000Z\"")!
let half = item("half", ", \"playback_position\": 300, \"runtime\": 600, \"added\": \"2024-07-01T00:00:00.0000000Z\"")!
let watched = item("watched", ", \"played\": true, \"last_played\": \"2025-06-01T00:00:00.0000000Z\"")!
// ⚠ A date but NOT played: the web's rule is `a.played && a.last_played`, so this row is never-played.
let stray = item("stray", ", \"last_played\": \"2025-12-01T00:00:00.0000000Z\"")!

let library = [older, newer, nodate, finished, half]

checkEqual(LibraryRules.filter(library, sort: .recent).map(\.itemID),
           ["newer", "half", "played", "older", "nodate"],
           "recent is newest first and puts the undated row last")
checkEqual(LibraryRules.filter(library, sort: .title).map(\.itemID),
           ["half", "newer", "nodate", "older", "played"],
           "title is A–Z, case-insensitively")
checkEqual(LibraryRules.filter(library, sort: .titleDesc).map(\.itemID),
           ["played", "older", "nodate", "newer", "half"],
           "title-desc is Z–A")
checkEqual(LibraryRules.filter(library, sort: .release).map(\.itemID),
           ["newer", "nodate", "older", "half", "played"],
           "release is the newest year first, with an unknown year last")
checkEqual(LibraryRules.filter([older, newer, nodate, finished, half, watched], sort: .runtime).map(\.itemID),
           ["older", "nodate", "newer", "played", "half", "watched"],
           "runtime is longest first, a tie falls back to recent, and an unknown runtime is last")
checkEqual(LibraryRules.filter(library, sort: .unwatched).map(\.itemID),
           ["newer", "half", "older", "nodate", "played"],
           "unwatched puts the unplayed first and keeps the recent order inside each group")
checkEqual(LibraryRules.filter(library, sort: .progress).map(\.itemID),
           ["half", "newer", "played", "older", "nodate"],
           "progress is the highest resume fraction first")
checkEqual(LibraryRules.resumeFraction(finished), 0,
           "a finished title scores zero, so it is not the most-watched thing in the library")

checkEqual(LibraryRules.filter([older, newer, nodate, finished, half, watched, stray], sort: .recentlyPlayed)
            .map(\.itemID),
           ["watched", "newer", "half", "played", "older", "nodate", "stray"],
           "recently played leads with a played row that has a date, and never-played comes last")

// ⚠⚠ STABILITY. JavaScript's `sort` has been stable since ES2019 and every comparator above depends on it:
// `cmpRecentDesc` returns 0 for two rows with no dates, so the SERVER'S order is what a viewer sees. Swift's
// `sorted(by:)` is not documented as stable, so the tie-break is written by hand — and this pair of checks is
// what proves it, in both directions.
let tieA = item("tieA")!
let tieB = item("tieB")!
checkEqual(LibraryRules.filter([tieA, tieB], sort: .recent).map(\.itemID), ["tieA", "tieB"],
           "two undated rows keep the server's order")
checkEqual(LibraryRules.filter([tieB, tieA], sort: .recent).map(\.itemID), ["tieB", "tieA"],
           "…and it really is the server's order, not the ids'")

section("the genre filter")

let actionRow = item("action", ", \"genres\": [\"Action\"]")!
let comedyRow = item("comedy", ", \"genres\": [\"Comedy\"]")!
let plainRow = item("none")!

checkEqual(LibraryRules.filter([actionRow, comedyRow, plainRow], genre: "Action").map(\.itemID), ["action"],
           "the genre filter is membership, not containment")
checkEqual(LibraryRules.filter([actionRow, comedyRow, plainRow], genre: "action").map(\.itemID), [],
           "…and it is case-sensitive, exactly as the web's Array.includes is")
checkEqual(LibraryRules.filter([actionRow, comedyRow, plainRow], genre: "").count, 3,
           "no genre is no filter")
checkEqual(LibraryRules.filter([actionRow, comedyRow], genre: "  ").count, 2,
           "a whitespace-only genre is no filter either")

section("the grid card's caption")

checkEqual(LibraryRules.cardMetaLine(item("c1", ", \"year\": 2021, \"runtime\": 6720")!),
           "2021 · 1h 52m",
           "the caption is year · runtime, through the app's ONE runtime formatter")
checkEqual(LibraryRules.cardMetaLine(item("c2", ", \"year\": 2021")!), "2021",
           "a row with no runtime reads its year alone, never '2021 · '")
checkEqual(LibraryRules.cardMetaLine(item("c3")!), "", "a row with neither reads nothing at all")

section("the top bar's tabs")

let navRows = [
    LibraryNavEntry(id: "folder:f1", name: "Movies", icon: .film, folderID: "f1", warning: ""),
    LibraryNavEntry(id: "unresolved:Kids", name: "Movies Kids", icon: .folder, folderID: nil,
                    warning: "Library unavailable"),
]

let homeTabs = BrowseRules.tabPlan(entries: navRows, current: .home)
checkEqual(homeTabs.map(\.title), ["Home", "Movies", "Movies Kids"],
           "Home is first, then this profile's own libraries")
checkEqual(homeTabs.map(\.isCurrent), [true, false, false], "on the Home screen only Home is current")
checkEqual(homeTabs.map(\.isEnabled), [true, true, false],
           "an unresolved library keeps its tab and cannot be selected")
checkEqual(homeTabs.map(\.warning), ["", "", "Library unavailable"],
           "…and it keeps its warning, on the bar as well as in the list")
checkEqual(homeTabs.map(\.id), ["home", "folder:f1", "unresolved:Kids"],
           "the tabs carry the entries' own identities")

let folderTabs = BrowseRules.tabPlan(entries: navRows, current: .folder("f1"))
checkEqual(folderTabs.map(\.isCurrent), [false, true, false],
           "on a folder's wall that folder's tab is the current one")

let emptyTabs = BrowseRules.tabPlan(entries: [], current: .browse)
checkEqual(emptyTabs.map(\.title), ["Home", "Browse"],
           "with no libraries at all the Browse fallback is the only way in")
checkEqual(emptyTabs.map(\.isCurrent), [false, true], "…and it is current on the Browse screen")
checkEqual(BrowseRules.tabPlan(entries: navRows, current: .browse).count, 3,
           "the fallback is never offered beside real libraries")

section("the cast avatars")

let personA = DetailPerson(id: "p1", name: "Brendan Fraser", role: "Rick O'Connell", hasImage: true)
let personAOther = DetailPerson(id: "p1", name: "Someone Else", role: "Rick O'Connell", hasImage: false)
let personB = DetailPerson(id: "p2", name: "Brendan Fraser", role: "Evelyn", hasImage: false)
let personNoID = DetailPerson(id: "", name: "Rachel Weisz", role: "Evelyn", hasImage: false)

checkEqual(DetailRules.castHue(personA), DetailRules.castHue(personAOther),
           "one person id is one colour, whatever else the row says")
check(DetailRules.castHue(personA) != DetailRules.castHue(personB),
      "two people are not forced to the same colour")
checkEqual(DetailRules.castHue(personNoID), DetailRules.castHue(personNoID),
           "a person with no id still has one stable colour")
check((0..<360).contains(Int(DetailRules.castHue(personB))), "the hue is a real hue")

// MARK: - Report

print("")
if failures.isEmpty {
    print("PASS — \(checks) checks, 0 failures")
    exit(0)
}
print("FAIL — \(checks) checks, \(failures.count) failure(s):")
for failure in failures { print("  · \(failure)") }
exit(1)
