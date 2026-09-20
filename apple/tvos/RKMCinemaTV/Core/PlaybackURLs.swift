import Foundation

/// **Every URL the player hands to `AVPlayer` — built in one place, in a file that can be RUN here.**
///
/// ⚠⚠ **WHY THE PLAYER'S URLs ARE NOT SPELLED IN THE VIEW, OR IN `PlaybackAPI`.** Two measured traps
/// live in exactly this code path, and both fail the same silent way:
///
///  1. **The query turned into a path.** `URL.appendingPathComponent(_:)` percent-escapes its whole
///     argument, so `"api/jellyfin/hls/\(id)/master.m3u8?mode=remux"` becomes `…/master.m3u8%3Fmode=remux`
///     and the api answers **404** — on screen, a film that "cannot be played". This is `RequestURL`'s
///     finding (B4) and `PosterURL`'s before it; the player is the THIRD caller, which is why the paths
///     below are literals with the query kept OUT of them and every parameter travels as a
///     `URLQueryItem`.
///  2. **`AVPlayer`'s sub-requests are not made by `URLSession`.** A URL built here is what `AVPlayer`
///     fetches *itself*, so a mistake is not visible to any of this app's own logging — there is no
///     request line for it. A wrong URL is a black screen and nothing else. That is the strongest
///     argument in this repo for building them where a test can.
///
/// ⚠ **`PlaybackAPI` (which imports `RKMServerKit`) cannot be executed in the sandbox; this file can** —
/// `apple/scripts/check-tvos-core.py` compiles and runs it, so the two traps above are pinned by a
/// mutation rather than by a comment.
enum PlaybackURLs {

    // R4 in `check-tvos-models.py` checks every one of these literals against `openapi.v1.json`, where an
    // interpolation becomes exactly ONE path component: a typo in the static parts still fails the gate.

    /// `GET /api/jellyfin/hls/{item_id}/master.m3u8` — the HLS master for a non-direct mode.
    static func hlsMaster(itemID: String) -> String {
        "api/jellyfin/hls/\(itemID)/master.m3u8"
    }

    /// `GET /api/jellyfin/stream/{item_id}` — the progressive path, used ONLY for a direct play.
    ///
    /// ⚠ A direct play is a `Static=true` byte-range file: AVPlayer seeks it natively and Jellyfin
    /// ignores `AudioStreamIndex`/`MaxStreamingBitrate` under it, which is why a chosen track or a
    /// quality pushes the decision to a non-direct mode in the first place (`PlaybackRules`).
    static func stream(itemID: String) -> String {
        "api/jellyfin/stream/\(itemID)"
    }

    /// `GET /api/jellyfin/subtitle` — the WebVTT proxy for one text subtitle stream.
    static func subtitle() -> String {
        "api/jellyfin/subtitle"
    }

    /// The query for `hlsMaster` / `stream`.
    ///
    /// ⚠⚠ **`audio_stream_index` AND `max_bitrate` ARE HONOURED ONLY ON A NON-DIRECT MODE** — measured
    /// live and recorded in `backend/api/routes/jellyfin_stream.py`: *"Jellyfin **ignores**
    /// `AudioStreamIndex`/`MaxStreamingBitrate` here"* under `Static=true`. So they are emitted only when
    /// the mode can actually use them, rather than sent as parameters the server will drop (which would
    /// make a track choice look applied while the wrong track kept playing).
    static func streamQuery(mode: PlaybackRules.StreamMode,
                            audioIndex: Int?,
                            maxBitrate: Int) -> [URLQueryItem] {
        var items: [URLQueryItem] = [URLQueryItem(name: "mode", value: mode.rawValue)]
        guard mode != .direct else { return items }
        if let audioIndex, audioIndex > 0 {
            items.append(URLQueryItem(name: "audio_stream_index", value: String(audioIndex)))
        }
        if maxBitrate > 0 {
            items.append(URLQueryItem(name: "max_bitrate", value: String(maxBitrate)))
        }
        return items
    }

    /// The query for `subtitle()` — the item, its media source and the stream index.
    ///
    /// ⚠ `ms` (the media source) falls back to the item id server-side for a single-source item, but the
    /// player HAS the source from `playback-info`, so it passes the real one.
    static func subtitleQuery(itemID: String, mediaSourceID: String, index: Int) -> [URLQueryItem] {
        [URLQueryItem(name: "id", value: itemID),
         URLQueryItem(name: "ms", value: mediaSourceID.isEmpty ? itemID : mediaSourceID),
         URLQueryItem(name: "index", value: String(index))]
    }

    /// The absolute URL for a path + query — **through the ONE builder**, so the player cannot grow its
    /// own escaping rule. (Same function `APIClient` uses for every JSON call.)
    static func absolute(base: URL, path: String, query: [URLQueryItem]) -> URL? {
        RequestURL.url(base: base, path: path, query: query)
    }

    /// The URL `AVPlayer` is given, for the mode that was chosen.
    ///
    /// ⚠ It is a function of the mode and NOT a property, because the two modes are two different
    /// endpoints: a direct play rides the byte-rangeable stream route and everything else rides HLS. A
    /// single "the URL" would have to guess which one this is.
    static func playbackURL(base: URL,
                            itemID: String,
                            mode: PlaybackRules.StreamMode,
                            audioIndex: Int?,
                            maxBitrate: Int) -> URL? {
        let path = PlaybackRules.usesHLS(mode) ? hlsMaster(itemID: itemID) : stream(itemID: itemID)
        return absolute(base: base,
                        path: path,
                        query: streamQuery(mode: mode, audioIndex: audioIndex, maxBitrate: maxBitrate))
    }
}
