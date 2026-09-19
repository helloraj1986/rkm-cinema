import Foundation

// The wire models for ONE item's detail screen — Phase B4.
//
// ⚠⚠ **THE SOURCE OF TRUTH IS NOT THE CONTRACT, for the same reason as `LibraryModels.swift`** (read that
// file's header first — it holds the measurement and the B0 decision). `GET /api/jellyfin/detail` has **no
// documented 200 schema at all** in `docs/api/openapi.v1.json`, and the contract is deliberately NOT being
// extended. So these models declare a **shape source**: a TypeScript interface in
// `frontend/src/lib/api/client.ts`, which is the description the app has actually been reading in
// production on his phone, desktop and iPad.
//
// `apple/scripts/check-tvos-models.py` R6/R7 checks these against those interfaces:
//
//   R6  every JSON key decoded here is a property of that interface;
//   R7  a non-optional property here must be non-optional there too.
//
// ⚠ **WHAT R6/R7 DO NOT PROVE:** that either side agrees with the SERVER. Nothing in the sandbox can
// (no Docker daemon, no signed-in session). The producer was read by hand for the fixtures below
// (`backend/services/library/jellyfin.py::_detail_from_item` + `_detail_people`, 2026-09-19), and that
// reading is what the fixtures in `tvos-core-tests/main.swift` are shaped like — but it is a reading, not
// a gate.
//
// ⚠ Deliberately a SUBSET where a field is not needed — `libraryByFolderId`-style accessors aside, nothing
// here is invented, and nothing this file claims to read may vanish from the interface.

// MARK: - The item itself

/// `frontend/src/lib/api/client.ts` → `ItemDetail` — `GET /api/jellyfin/detail?id=`.
///
/// ⚠ Produced by `JellyfinLibraryService._detail_from_item()`, which maps Jellyfin's `Movie`/`Series`/
/// `Episode` onto `"movie"`/`"tv"`/`"episode"` and returns `None` for anything else — so a `404` from the
/// route means "no detail for this item", which the screen has its own state for (`DetailState.notFound`).
///
/// ⚠ `type` is a `String`, not an enum, exactly as the interface has it: a device that refused to decode a
/// value it did not know would show an empty screen for no reason. Read it through
/// ``DetailRules/isSeries(_:)`` when the distinction matters.
struct ItemDetail: Decodable, Equatable {

    /// `"movie"` | `"tv"` | `"episode"`.
    let type: String
    /// ⚠ `item_id`, not `id` — the same identity key every library payload uses. (See `MediaItem`'s header
    /// for the trap this repo has already paid for: global-search rows carry `id`.)
    let itemID: String
    /// ⚠ `name`, not `title`. A detail payload is a *Jellyfin item*, not a library row.
    let name: String

    let year: Int?
    /// Seconds — **0 for a Series record**, because Jellyfin stores a series' runtime as 0. A series' meta
    /// line reads its season count instead (`DetailRules.metaBits`), which is the web app's own rule.
    let runtime: Int?
    /// The same runtime in Jellyfin's 10ms ticks. Decoded, never used for display: `runtime` is the
    /// ergonomic field, and the play state carries its own `resume_ticks`.
    let runtimeTicks: Int?
    let overview: String?
    let genres: [String]?
    /// Jellyfin's community rating on a 0–10 scale (e.g. `7.473`). `null` when the server has none —
    /// ⚠ the key is PRESENT and null, which is why this is `Double?` and not `Double`.
    let communityRating: Double?
    /// e.g. `"AU-MA 15+"`. Present-and-null when absent.
    let officialRating: String?
    let studios: [String]?
    let people: DetailPeople?
    let hasBackdrop: Bool?
    /// Poster aspect ratio (a 2:3 poster ≈ `0.667`); present-and-null when the server does not report one.
    let primaryAspect: Double?
    /// ⚠ **NOT optional**, and that is the interface's promise: every detail payload carries a play state,
    /// so a payload without one is a shape violation rather than a title that has never been watched.
    let play: DetailPlay

    /// Present only for an Episode item.
    let series: DetailSeriesContext?
    let seasonID: String?
    let season: Int?
    let episode: Int?

    /// ⚠ Explicit on every key — the mapping must be visible at the property, because `item_id` vs `id` and
    /// `name` vs `title` are precisely the mistakes this file exists to make impossible to type by accident.
    private enum CodingKeys: String, CodingKey {
        case type
        case itemID = "item_id"
        case name
        case year
        case runtime
        case runtimeTicks = "runtime_ticks"
        case overview
        case genres
        case communityRating = "community_rating"
        case officialRating = "official_rating"
        case studios
        case people
        case hasBackdrop = "has_backdrop"
        case primaryAspect = "primary_aspect"
        case play
        case series
        case seasonID = "season_id"
        case season
        case episode
    }
}

/// `frontend/src/lib/api/client.ts` → `DetailPlay` — the play state in the detail payload.
///
/// ⚠ Every property is non-optional **because the interface says so**: an absent `play_count` and a
/// never-played title must not be the same thing to the screen.
struct DetailPlay: Decodable, Equatable {
    let played: Bool
    /// Raw Jellyfin ticks (`PlaybackPositionTicks`).
    let resumeTicks: Int
    /// ⚠ The same position in SECONDS — the server does the ticks/1e7 arithmetic
    /// (`_ticks_to_sec()`), so no view ever does. `Int`: the server sends an integer.
    let resume: Int
    let playCount: Int

    private enum CodingKeys: String, CodingKey {
        case played
        case resumeTicks = "resume_ticks"
        case resume
        case playCount = "play_count"
    }
}

/// `ItemDetail.series` — the series context an Episode's detail carries (INLINE in the interface, so its
/// shape source is the dotted path `ItemDetail.series`).
struct DetailSeriesContext: Decodable, Equatable {
    let id: String
    let name: String

    private enum CodingKeys: String, CodingKey {
        case id
        case name
    }
}

// MARK: - Cast and credits

/// `client.ts` → `DetailPerson` — one cast/credit entry.
///
/// ⚠ `role` is the character (actors) or the credit role, and it is **non-optional in the interface** while
/// the server can send an empty string for it — which is why the screen drops an empty one rather than
/// rendering a blank line under a name (see `DetailRules.creditsLine`).
struct DetailPerson: Decodable, Equatable {
    let id: String
    let name: String
    let role: String
    /// ⚠ `has_image`, **not** `hasImage`: Jellyfin reports a headshot tag, and people without one 404 on the
    /// proxy — so the flag exists to let a UI skip a request that would fail. tvOS does not use it yet
    /// (Phase B draws no headshots), but the key is decoded because it is part of the shape.
    let hasImage: Bool

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case role
        case hasImage = "has_image"
    }
}

/// `client.ts` → `DetailPeople`. ⚠ The three groups are non-optional arrays: `_detail_people()` always
/// emits all three (possibly empty), so a payload missing one is a shape violation, not an empty cast.
struct DetailPeople: Decodable, Equatable {
    let actors: [DetailPerson]
    let directors: [DetailPerson]
    let writers: [DetailPerson]

    private enum CodingKeys: String, CodingKey {
        case actors
        case directors
        case writers
    }
}
