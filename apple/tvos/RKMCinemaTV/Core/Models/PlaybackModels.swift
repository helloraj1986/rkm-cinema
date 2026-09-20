import Foundation

// The player's wire shapes, in one place.
//
// ⚠⚠ **WHY SOME OF THESE ARE CONTRACT MODELS AND SOME ARE NOT — and how each one is checked.**
// `apple/scripts/check-tvos-models.py` splits them, and the split is measured rather than chosen:
//
//  * **The three REQUEST bodies are contract schemas.** `JellyfinProgressRequest`,
//    `SubtitleSelectRequest` and `SubtitleDisableRequest` are all in `docs/api/openapi.v1.json`, so
//    their key sets are checked against it exactly (R1–R3).
//  * **Every RESPONSE here has NO 200 schema in the contract** — Phase C's plan measured that
//    (`docs/TVOS_PLAYER_PLAN.md` §1: five player routes answer with `{}` documented), so each model
//    declares a **shape source** instead: the frontend's own TypeScript interface in
//    `frontend/src/lib/api/client.ts`, which is the description the web player has actually been
//    reading in production. R6/R7 then check these keys against that interface.
//    ⚠ **What that does and does not prove:** it proves the Swift and the TypeScript agree. It does NOT
//    prove either agrees with the server — nothing in this sandbox can, with no Docker daemon and no
//    signed-in session. The TypeScript is the closest thing to a production-verified description this
//    repo has outside the contract, and saying so is the point.
//
// ⚠ Every one of these is registered in `NON_CONTRACT_MODELS` with its reason, so the exemption is a
// deliberate act rather than "a model that happens to share a name with an interface".

// MARK: - Tracks

/// One audio or subtitle track of the item — `PlaybackTrack` in the frontend's `client.ts`.
///
/// ⚠ `index` is the Jellyfin `MediaStream.Index`, and it is **POSITIONAL**: adding or removing a track
/// shifts every index after it. That is why the stored subtitle choice is an IDENTITY resolved to a
/// current index per load (see `PlaybackRules.resolveActiveSubtitle`) and never a remembered number.
struct PlaybackTrack: Decodable, Equatable {

    /// ⚠ Non-optional, and it is non-optional in the interface too: a track with no index cannot be
    /// asked for, so a row without one is not a row this app can use.
    let index: Int
    let name: String
    let language: String
    /// Audio codec (`"eac3"`, `"aac"`, …) — drives the transcode decision. ⚠ Absent on a subtitle row.
    let codec: String?

    enum CodingKeys: String, CodingKey {
        case index, name, language, codec
    }
}

/// The first video stream's facts — `PlaybackVideo` in `client.ts`.
///
/// ⚠⚠ **USED BY `PlaybackRules.pickStreamMode`, WHICH IS THE WHOLE REASON `bit_depth` AND `profile` ARE
/// HERE**: a High-10 H.264 stream decodes as a black screen on clients that advertise `h264`, and the
/// web app learnt that the hard way (`videoNeedsTranscode` is conservative about it). Every field is
/// optional — a stream that did not report a fact is UNKNOWN, and unknown means "attempt it".
struct PlaybackVideoFacts: Decodable, Equatable {
    let codec: String?
    let profile: String?
    /// ⚠ `bit_depth` is snake_case on the wire and camelCase in the interface — the ONE place the two
    /// spellings differ, and `check-tvos-models.py` (R6) reads the interface, so it is `bit_depth` here.
    let bitDepth: Int?
    let width: Int?
    let height: Int?
    let bitRate: Int?

    enum CodingKeys: String, CodingKey {
        case codec, profile
        case bitDepth = "bit_depth"
        case width, height
        case bitRate = "bit_rate"
    }
}

/// The viewer's stored subtitle choice, already resolved to a CURRENT stream index by the server —
/// `PreferredSubtitle` in `client.ts`.
///
/// ⚠ The server resolves it (not this app) because stream indices are positional and the store keeps
/// the identity: `services/subtitle_store.py` matches it against the tracks Jellyfin reports TODAY.
struct PreferredSubtitle: Decodable, Equatable {
    let subtitleID: String
    let provider: String
    let language: String
    let displayTitle: String
    let index: Int
    let usedCount: Int

    enum CodingKeys: String, CodingKey {
        case subtitleID = "subtitle_id"
        case provider, language
        case displayTitle = "display_title"
        case index
        case usedCount = "used_count"
    }
}

/// `GET /api/jellyfin/playback-info` — the tracks + media source the player's pickers are built from.
/// Shape source: `PlaybackInfo` in `frontend/src/lib/api/client.ts`.
///
/// ⚠⚠ **IT IS ALSO WHERE THE MODE DECISION COMES FROM.** `container` + `video` + the active audio
/// codec are exactly the three facts `pickStreamMode` needs, which is why the player makes this one
/// call before it can start anything: without it there is no honest answer to "should this be a direct
/// play or a remux".
struct PlaybackInfo: Decodable, Equatable {
    let mediaSourceID: String
    /// Original container (`"mkv"`, `"mp4"`) — a non-MP4 container needs a remux to be indexable.
    let container: String?
    /// `nil` for an audio-only source.
    let video: PlaybackVideoFacts?
    let audio: [PlaybackTrack]
    /// ⚠ **TEXT subtitles only** — the api filters `IsTextSubtitleStream`, because an image/PGS track
    /// cannot be drawn by the client. The picker therefore never offers a subtitle that cannot render.
    let subtitles: [PlaybackTrack]
    /// ⚠ `nil` means "no choice, or disabled, or the identity no longer matches a track" — three
    /// different situations the picker treats the same way: open with nothing selected.
    let preferredSubtitle: PreferredSubtitle?

    enum CodingKeys: String, CodingKey {
        case mediaSourceID = "media_source_id"
        case container, video, audio, subtitles
        case preferredSubtitle = "preferred_subtitle"
    }
}

// MARK: - Subtitles (local tracks + OpenSubtitles)

/// One row of the subtitle picker — a LOCAL track or an OpenSubtitles result. Shape source:
/// `SubtitleRow` in `client.ts`.
///
/// ⚠ `index` is `nil` for a REMOTE result: it gains a stream index only once it has been downloaded and
/// attached to the item, which is what `subtitle-select` does. A view that assumed every row had one
/// would offer a selection it cannot make.
struct SubtitleRow: Decodable, Equatable {
    /// Our identity (`"os:<file_id>"`); empty for a local track.
    let subtitleID: String
    let fileID: Int?
    /// `"local"` | `"opensubtitles"`.
    let provider: String
    let language: String
    let displayTitle: String
    let index: Int?
    let usedCount: Int
    let lastUsed: String
    let downloadCount: Int
    let hearingImpaired: Bool
    let format: String
    let vendorFormat: String
    let year: Int?
    let active: Bool
    let local: Bool

    enum CodingKeys: String, CodingKey {
        case subtitleID = "subtitle_id"
        case fileID = "file_id"
        case provider, language
        case displayTitle = "display_title"
        case index
        case usedCount = "used_count"
        case lastUsed = "last_used"
        case downloadCount = "download_count"
        case hearingImpaired = "hearing_impaired"
        case format
        case vendorFormat = "vendor_format"
        case year, active, local
    }
}

/// `GET /api/jellyfin/subtitle-search` — local tracks first, then ranked remote results.
/// Shape source: `SubtitleSearchShape` in `client.ts`.
///
/// ⚠⚠ **`enabled == false` IS A NORMAL ANSWER, NOT A FAILURE.** The api logs it at startup: with no
/// OpenSubtitles key configured the remote half is switched off and only the local half degrades *by
/// design* (`backend/api/main.py`: "the subtitle SEARCH section degrades"). So the "Search
/// OpenSubtitles…" row is drawn from THIS flag — a control the server would refuse is a control that
/// must not be offered.
struct SubtitleSearch: Decodable, Equatable {
    let itemID: String
    let enabled: Bool
    let language: String
    let languages: [String]
    let results: [SubtitleRow]
    let localCount: Int
    let remoteCount: Int
    let preferredSubtitle: PreferredSubtitle?
    let disabled: Bool
    /// Downloads left today as the API reported it; `nil` until it is known.
    let remainingDownloads: Int?
    /// Why the remote half degraded — never a reason to stop local playback.
    let warning: String

    enum CodingKeys: String, CodingKey {
        case itemID = "item_id"
        case enabled, language, languages, results
        case localCount = "local_count"
        case remoteCount = "remote_count"
        case preferredSubtitle = "preferred_subtitle"
        case disabled
        case remainingDownloads = "remaining_downloads"
        case warning
    }
}

/// `POST /api/jellyfin/subtitle-select` — the choice has been delivered and attached.
/// Shape source: `SubtitleSelectResult` in `client.ts`.
struct SubtitleSelection: Decodable, Equatable {
    let ok: Bool
    /// The server's own word for how it delivered the file.
    let delivered: String
    let reused: Bool
    /// ⚠ The REFRESHED track list — the newly attached track only has an index after this call, and
    /// the screen must draw the list the server now reports rather than the one it had.
    let subtitles: [PlaybackTrack]
    let usedCount: Int
    let remainingDownloads: Int?
    let preferredSubtitle: PreferredSubtitle?

    enum CodingKeys: String, CodingKey {
        case ok, delivered, reused, subtitles
        case usedCount = "used_count"
        case remainingDownloads = "remaining_downloads"
        case preferredSubtitle = "preferred_subtitle"
    }
}

// MARK: - Requests (CONTRACT schemas — checked against `docs/api/openapi.v1.json`)

/// `POST /api/jellyfin/progress` — the body of a progress report.
///
/// ⚠⚠ **THE KEY IT MUST NOT HAVE IS `media_source_id`: this is the item-scoped write**, and the api's
/// own docstring records why it is not Jellyfin's `/Sessions/Playing*` endpoint — those "answer 204 and
/// store nothing" because in-app playback is never a live Jellyfin device session. Every default below
/// is the contract's own default.
struct JellyfinProgressRequest: Encodable {

    let itemID: String
    /// Jellyfin 10 ms ticks (seconds × 1e7).
    let positionTicks: Int
    let isPaused: Bool
    /// `start` | `timeupdate` | `stopped`.
    let event: String
    /// `DirectPlay` | `DirectStream` | `Transcode` — from `PlaybackRules.playMethod`.
    let playMethod: String
    let runtimeTicks: Int

    enum CodingKeys: String, CodingKey {
        case itemID = "item_id"
        case positionTicks = "position_ticks"
        case isPaused = "is_paused"
        case event
        case playMethod = "play_method"
        case runtimeTicks = "runtime_ticks"
    }
}

/// `POST /api/jellyfin/subtitle-select` — choose a remote subtitle (the api downloads and attaches it).
struct SubtitleSelectRequest: Encodable {
    let itemID: String
    let fileID: Int
    let language: String
    let displayTitle: String
    let provider: String

    enum CodingKeys: String, CodingKey {
        case itemID = "item_id"
        case fileID = "file_id"
        case language
        case displayTitle = "display_title"
        case provider
    }
}

/// `POST /api/jellyfin/subtitle-disable` — turn subtitles off WITHOUT forgetting the choice.
///
/// ⚠ The api's own description: *"Turn subtitles off for an item without forgetting which one was
/// chosen."* That is why "Off" is a POST and not a local toggle — a client-side "off" would be undone
/// by the next load, and the viewer would watch the app re-apply a subtitle they had turned off.
struct SubtitleDisableRequest: Encodable {
    let itemID: String

    enum CodingKeys: String, CodingKey {
        case itemID = "item_id"
    }
}
