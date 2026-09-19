import Foundation

// The wire models for Phase B — Home, Browse and item detail. ***THE SOURCE OF TRUTH IS NOT THE CONTRACT.***
//
// ⚠⚠ READ THIS BEFORE EDITING ANYTHING HERE. `docs/api/openapi.v1.json` does NOT describe the item shape.
// Measured 2026-09-19 (`docs/TVOS_LIBRARY_PLAN.md` §0):
//
//   · `FolderItemsResponse.items` and `LibraryResponse.recent` are `array` of `object` with
//     `additionalProperties: true` — an item is *anything*;
//   · `/api/library/continue-watching`, `/recently-watched`, `/series/{id}/episodes`, `/api/jellyfin/detail`
//     and `/api/jellyfin/poster` have **no documented 200 schema at all**;
//   · there is no `Item`/`MediaItem` schema anywhere among the contract's 58 schemas.
//
// Extending the contract was considered and **rejected deliberately** (decision B0, 2026-09-19) — see the
// plan's §5 for why. So these models are checked against the *second* description of the same bytes:
//
//   frontend/src/lib/api/client.ts — `MediaItem` · `EpisodeShape` · and the response envelopes
//
// That is the description this app has actually been reading in production on his phone, desktop and iPad,
// and it is the closest thing to a verified wire format this repo has outside the contract.
//
// ⚠ `apple/scripts/check-tvos-models.py` RUNS ON LINUX AND FAILS THE ROUND IF EITHER SIDE DRIFTS:
//
//   R6  every JSON key decoded here is a property of that TypeScript interface. Not pedantry — a mistyped
//       key does NOT fail at runtime, it silently decodes to nil/0/false, which is the exact class of bug a
//       TV in another room makes undiagnosable;
//   R7  every property that is **not optional here** must be non-optional in the interface too, i.e. if
//       the contract is not going to promise a field, the interface has to. `item_id` is promised;
//       `thumb` is not, and so it is optional below.
//
// ⚠⚠ THE TRAP THIS SHAPE CARRIES, and the reason a gate is worth having at all: **library rows use
// `item_id`, while the global-search rows in the same repo use `id`.** Same-looking payloads, different
// key. Guessing wrong compiles, ships, and shows a blank card with nothing in any log.
//
// ⚠ Deliberately a SUBSET where a field is not needed: a property the interface has and this file does not
// decode is not drift (same rule as `AuthModels.swift`). The check is one-directional — nothing may be
// invented here, and nothing we claim to read may vanish from the interface.

// MARK: - One item (a poster card, a rail entry, a resume row)

/// `frontend/src/lib/api/client.ts` → `MediaItem` — the shape of every item route in Phase B.
///
/// ⚠ Produced server-side by `backend/services/library/jellyfin.py::_item_public()` (7 call sites) and,
/// for episode resume rows, by `_episode_resume_public()`. The Continue-Watching path adds the two facets
/// at the bottom (`kind`, `episode`) on top of the same 13 core fields — `CONTINUE_WATCHING_EPISODES_PLAN`
/// Option A, where "the endpoint stays free-form — no contract change".
struct MediaItem: Decodable, Equatable, Identifiable {

    let title: String
    let itemID: String

    let year: Int?
    /// `"tv"` | `"movie"` | `"episode"` in practice, but the interface types it as `string`, so this does
    /// not enum-ify it: a device that refuses to decode an unknown value would show an empty wall for no
    /// reason. Read it through ``kind`` when the distinction matters.
    let type: String?
    let thumb: String?

    /// ⚠ A plain web URL for the media server's own page. The app does not open it (tvOS has no browser);
    /// it is decoded because it is part of the shape, and `R6` requires every key to be accounted for.
    let jellyfinURL: String?

    let played: Bool?
    /// Seconds. `_ticks_to_sec()` returns an **Int**, so this is `Int` and not `Double` — a JSON number
    /// decoded into the wrong numeric type throws rather than defaulting, which is loud and therefore fine.
    let playbackPosition: Int?
    let runtime: Int?
    let playCount: Int?
    let lastPlayed: String?
    let genres: [String]?
    /// `DateCreated`, ISO-8601 — what the "recently added" ordering is built from.
    let added: String?

    /// The Continue-Watching facet: `"movie"` | `"show"` | `"episode"`.
    let kind: String?
    /// Present when ``kind`` is `"episode"` — the series context a Continue-Watching card needs to say
    /// *what* is half-watched rather than just *that* something is.
    let episode: EpisodeContext?

    /// `Identifiable` for `ForEach`. ⚠ Computed, therefore not a decoded key — a stored `id` here would be
    /// an invented field, and R6 would (correctly) fail it.
    var id: String { itemID }

    /// ⚠ Explicit on every key, not relying on `convertFromSnakeCase`: a decoder-wide strategy makes the
    /// mapping invisible at the property, and `item_id` vs `id` is exactly the mistake that has to be
    /// visible. A `CodingKeys` case with no matching property fails the round (R2b).
    private enum CodingKeys: String, CodingKey {
        case title
        case itemID = "item_id"
        case year
        case type
        case thumb
        case jellyfinURL = "jellyfin_url"
        case played
        case playbackPosition = "playback_position"
        case runtime
        case playCount = "play_count"
        case lastPlayed = "last_played"
        case genres
        case added
        case kind
        case episode
    }

    /// True when there is genuinely something to resume — the same rule the web app uses
    /// (`features/library/lib.ts`), so a card cannot disagree with the phone about the same title.
    var isResumable: Bool {
        guard !itemID.isEmpty else { return false }
        return (playbackPosition ?? 0) > 0 || (played ?? false)
    }

    /// Progress as a 0…1 fraction, or `nil` when it cannot be stated honestly (no runtime, or an item
    /// that is finished). ⚠ `nil` rather than `0`: a full bar and "no idea" must not render the same.
    var progressFraction: Double? {
        guard let runtime, runtime > 0, let position = playbackPosition, position > 0 else { return nil }
        return min(1, Double(position) / Double(runtime))
    }
}

/// `frontend/src/lib/api/client.ts` → `MediaItem.episode` — inline in the interface, so the shape source
/// is the dotted path `MediaItem.episode`.
struct EpisodeContext: Decodable, Equatable {
    let number: Int
    let season: Int
    let seriesID: String
    let seriesName: String

    private enum CodingKeys: String, CodingKey {
        case number
        case season
        case seriesID = "series_id"
        case seriesName = "series_name"
    }
}

// MARK: - One episode

/// `frontend/src/lib/api/client.ts` → `EpisodeShape` — one row of `/api/library/series/{id}/episodes`.
///
/// ⚠ Note the key difference from ``MediaItem``: an episode row's identity is **`id`**, not `item_id`, and
/// the human-readable field is **`name`**, not `title`. Two shapes, one letter apart — which is why both
/// live in this file, next to each other, with their sources named.
struct EpisodeItem: Decodable, Equatable, Identifiable {
    let id: String
    let name: String
    let season: Int
    let episode: Int
    let played: Bool
    let playbackPosition: Int
    let runtime: Int
    let thumb: String?

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case season
        case episode
        case played
        case playbackPosition = "playback_position"
        case runtime
        case thumb
    }
}

// MARK: - Response envelopes

/// `LibraryItemsShape` — `GET /api/library/continue-watching` and `/api/library/recently-watched`.
struct LibraryItemsResponse: Decodable, Equatable {
    let provider: String?
    let items: [MediaItem]

    private enum CodingKeys: String, CodingKey {
        case provider
        case items
    }
}

/// `FolderItemsShape` — `GET /api/library/folders/{id}/items`, the poster wall.
///
/// ⚠ **This one IS a contract schema** (`#/components/schemas/FolderItemsResponse`), so R1-R3 check it
/// against the contract rather than the interface — the contract wins by design, and it is the more
/// authoritative source when it has something to say. What it does not have is a *typed* `items`
/// (`array` of `object`, `additionalProperties: true`), which is the whole reason the item shape needed
/// `MediaItem`'s second source in the first place.
///
/// ⚠ `folder_id` is non-optional in both. **`items` is optional here and that is not a shortcut:** the
/// contract lists it as neither `required` nor defaulted (the server's pydantic model uses a list
/// factory, which OpenAPI cannot express as a `default`), so R3 requires the optional. The route does
/// always send it — `get_folder_items` constructs `items=payload.get("items") or []` — but "the server
/// currently does" and "the server promised" are different claims, and this app decodes the second one.
/// `rows` is the call site's way out: no screen has to spell `?? []` and forget a log line.
struct FolderItemsResponse: Decodable, Equatable {
    let provider: String?
    let folderID: String
    let items: [MediaItem]?

    private enum CodingKeys: String, CodingKey {
        case provider
        case folderID = "folder_id"
        case items
    }

    /// ⚠ An absent `items` and an empty one look the same on screen, so the difference is logged at the
    /// call site (same rule as `ProfilesResponse.profiles`) rather than swallowed here.
    var rows: [MediaItem] { items ?? [] }
}

/// `LibraryRecentShape` — `GET /api/library`: the legacy Home read, still the one source of the
/// **recently-added** ordering (`recent`, capped server-side) plus the counts the app can show.
struct LibraryRecentResponse: Decodable, Equatable {
    let provider: String?
    let available: Bool
    let counts: [String: Int]
    let recent: [MediaItem]
    let server: String?
    let urls: [String: String]?

    private enum CodingKeys: String, CodingKey {
        case provider
        case available
        case counts
        case recent
        case server
        case urls
    }
}

/// `EpisodesShape` — `GET /api/library/series/{id}/episodes`.
struct EpisodesResponse: Decodable, Equatable {
    let provider: String?
    let episodes: [EpisodeItem]

    private enum CodingKeys: String, CodingKey {
        case provider
        case episodes
    }
}
