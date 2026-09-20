import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import RKMServerKit

// The player's calls — typed, in one place, so no view ever spells a path.
//
// ⚠ Every path literal below is checked against the frozen contract by `apple/scripts/check-tvos-models.py`
// (R4), and the two that `AVPlayer` fetches itself (the stream and the HLS master) are built by
// `Core/PlaybackURLs.swift` — a `Foundation`-only file, so ITS rule (a query is never part of a path) is
// executed in the sandbox rather than discovered on a TV.
//
// ⚠⚠ **THE THREE WRITES HERE ARE WRITES, AND THIS REPO HAS PAID TWICE FOR TRUSTING ONE.** A `204` that
// stores nothing is not success: Jellyfin's `/Sessions/Playing*` answers `204` and stores nothing, and
// `/Users/Password` with `ResetPassword: true` answered `204`, set nothing, and CLEARED a password. So
// **nothing in this file reports success** — `PlaybackStore` re-reads the state it claims to have changed
// (`GET /api/jellyfin/detail` for the position, `playback-info` for the subtitle choice) and the screen
// shows what came back.

extension APIClient {

    /// `GET /api/jellyfin/playback-info?id=` — the item's audio + text-subtitle tracks, its media source
    /// and its first video stream's facts.
    ///
    /// ⚠⚠ **ONE CALL, AND THE PLAYER CANNOT START WITHOUT IT.** The container, the video codec and the
    /// active audio codec are the three facts `PlaybackRules.pickStreamMode` decides from — so "should
    /// this be a direct play or a remux" is answered by the SERVER's own description of the file rather
    /// than by a guess. The api degrades a provider failure to `404 "No playback info"`, which the store
    /// maps to a sentence rather than to a black screen.
    func playbackInfo(itemID: String, correlation: CorrelationID = .next()) async throws -> PlaybackInfo {
        try await get("api/jellyfin/playback-info",
                      query: [URLQueryItem(name: "id", value: itemID)],
                      correlation: correlation)
    }

    /// `POST /api/jellyfin/progress` — resume + watched. **Answers `204` with no body** (so the call
    /// ignores it), and the server owns the "was that finished?" question (`FINISHED_FRACTION = 0.95`).
    func reportProgress(_ body: JellyfinProgressRequest,
                        correlation: CorrelationID = .next()) async throws {
        try await postIgnoringBody("api/jellyfin/progress", body: body, correlation: correlation)
    }

    /// `GET /api/jellyfin/subtitle-search?id=&language=` — local tracks, then ranked remote results.
    ///
    /// ⚠ `enabled: false` is a NORMAL answer (no OpenSubtitles key configured server-side), not a
    /// failure — the api's own startup log says the search half is optional and only it degrades.
    func searchSubtitles(itemID: String, language: String = "",
                         correlation: CorrelationID = .next()) async throws -> SubtitleSearch {
        var query = [URLQueryItem(name: "id", value: itemID)]
        if !language.isEmpty { query.append(URLQueryItem(name: "language", value: language)) }
        return try await get("api/jellyfin/subtitle-search", query: query, correlation: correlation)
    }

    /// `POST /api/jellyfin/subtitle-select` — download, attach and REMEMBER one remote subtitle.
    ///
    /// ⚠ The response's `subtitles` is the REFRESHED track list, and it is the only honest source for
    /// the picker afterwards: the newly attached stream has no index until this call has run.
    func selectSubtitle(_ body: SubtitleSelectRequest,
                        correlation: CorrelationID = .next()) async throws -> SubtitleSelection {
        try await post("api/jellyfin/subtitle-select", body: body, correlation: correlation)
    }

    /// `POST /api/jellyfin/subtitle-disable` — turn subtitles off while KEEPING the choice.
    ///
    /// ⚠ It is a POST and not a local toggle on purpose: a client-side "off" would be undone by the next
    /// load, and the viewer would watch the app re-apply a subtitle they had turned off. ⚠ Its body is
    /// ignored — the store re-reads `playback-info` to see that the choice really is off, because a `2xx`
    /// is not evidence (see the header).
    func disableSubtitle(itemID: String, correlation: CorrelationID = .next()) async throws {
        try await postIgnoringBody("api/jellyfin/subtitle-disable",
                                   body: SubtitleDisableRequest(itemID: itemID),
                                   correlation: correlation)
    }

    /// `GET`/`POST /api/jellyfin/subtitle-settings` — the auto-pick's switch + exclusion.
    ///
    /// ⚠⚠ **THE SERVER OWNS THIS STATE, AND THAT IS THE POINT.** It is read by the tvOS drawer and the
    /// web panel both, so a client that kept its own copy would be a client that could disagree with the
    /// other about whether subtitles are being applied by themselves.
    func subtitleSettings(correlation: CorrelationID = .next()) async throws
        -> SubtitleSettingsResponse {
        try await get("api/jellyfin/subtitle-settings", correlation: correlation)
    }

    /// Change the auto-pick settings — ⚠ **a PARTIAL update**: a field left `nil` is left ALONE in the
    /// store, so this screen cannot reset the web panel's control (or its own) by sending a whole block.
    func updateSubtitleSettings(_ body: SubtitleSettingsRequest,
                                correlation: CorrelationID = .next()) async throws
        -> SubtitleSettingsResponse {
        try await post("api/jellyfin/subtitle-settings", body: body, correlation: correlation)
    }

    /// `POST /api/jellyfin/subtitle-auto` — **ask the api to choose and apply the top-ranked subtitle**
    /// for a title it has never been given one for (his decision, 2026-09-21).
    ///
    /// ⚠⚠ **EVERY DECISION IS THE SERVER'S** — the language, the ranking, the switch, the exclusions and
    /// the quota — so this request cannot ask for a subtitle the server's own rule would refuse.
    /// ⚠ It is asked ONCE per play, and a refusal is a `200` carrying `decision` + `reason`: a viewer who
    /// never asked for the download must never see it fail as an error.
    func autoPickSubtitle(itemID: String, correlation: CorrelationID = .next()) async throws
        -> SubtitleAutoOutcome {
        try await post("api/jellyfin/subtitle-auto",
                       body: SubtitleAutoRequest(itemID: itemID), correlation: correlation)
    }

    /// Fetch a subtitle stream as text (the api converts it to WebVTT).
    ///
    /// ⚠⚠ **DELIBERATELY NOT `AVPlayer`'s LEGIBLE MEDIA.** The api hands over an EXTERNAL WebVTT stream
    /// for one chosen track (`GET /api/jellyfin/subtitle`), while `AVPlayer`'s legible-media selection
    /// works on what the HLS playlist itself declares — a different mechanism, and one whose behaviour
    /// with a sidecar/remote track is a platform claim this repo could not measure before building. So the
    /// text is fetched and drawn by the app (`PlaybackRules.parseVTT` + `activeCue`, both gated), which
    /// also keeps the picker's stored choice in charge of what is on screen. ⚠ Recorded as a deliberate
    /// choice in `docs/TVOS_PLAYER_PLAN.md`, with the alternative noted rather than argued.
    func subtitleText(url: URL, correlation: CorrelationID = .next()) async throws -> String {
        var request = URLRequest(url: url)
        request.timeoutInterval = 45  // Jellyfin converts an embedded track to VTT on first request.
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let data: Data
        do {
            (data, _) = try await URLSession.shared.data(for: request)
        } catch {
            throw APIError.transport(String(describing: error))
        }
        return String(data: data, encoding: .utf8) ?? ""
    }
}
