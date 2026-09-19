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

// MARK: - Report

print("")
if failures.isEmpty {
    print("PASS — \(checks) checks, 0 failures")
    exit(0)
}
print("FAIL — \(checks) checks, \(failures.count) failure(s):")
for failure in failures { print("  · \(failure)") }
exit(1)
