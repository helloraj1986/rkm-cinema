import Foundation

/// **Everything about playback that can be decided without AVFoundation.**
///
/// ⚠⚠ **WHY THESE RULES LIVE IN THEIR OWN FILE.** The player screen is SwiftUI and `AVPlayer` is
/// AVFoundation — neither exists on Linux, so nothing about that screen can be executed here: it is
/// written, then verified on his Mac in one round. Everything that DECIDES something is therefore
/// pushed out to this file, which is `Foundation`-only, compiled AND RUN by
/// `apple/scripts/check-tvos-core.py` on every gate run, and pinned mutation by mutation.
///
/// The rules are **ports, not inventions** — their source is the web player that has been running in
/// production (`frontend/src/features/playback/lib.ts`, 771 lines) plus the tvOS player prototype
/// (`tvos_ux/3. MediaPlayerUx/rkm-cinema-tvos-player.html`). Where this file DIVERGES from the web,
/// the divergence is stated with its reason, because "the same rule written twice differently" is this
/// repo's most-repeated defect.
enum PlaybackRules {

    // MARK: - Time and ticks

    /// ⚠ **Jellyfin ticks are 10 ms — i.e. 10,000,000 per second** — and they are the unit of every
    /// position on the wire (`position_ticks`, `runtime_ticks`, `resumeTicks`). Seconds are the unit of
    /// the screen. One conversion, here, so no view ever divides by a magic number.
    static let ticksPerSecond: Double = 10_000_000

    static func seconds(fromTicks ticks: Int) -> Double {
        Double(ticks) / ticksPerSecond
    }

    static func ticks(fromSeconds seconds: Double) -> Int {
        Int((max(0, isFiniteNumber(seconds) ? seconds : 0) * ticksPerSecond).rounded())
    }

    /// ⚠ A duration off the wire can be absent, and JS distinguishes that from `0` — `Infinity`/`NaN`/
    /// null all mean "unknown", never "zero-length". Swift has no `NaN` coming from JSON, but it does
    /// have `.nan` from an arithmetic result, so the guard is the same rule with a different spelling.
    static func isFiniteNumber(_ value: Double?) -> Bool {
        guard let value else { return false }
        return value.isFinite
    }

    static func isFiniteDuration(_ value: Double?) -> Bool {
        guard let value, value.isFinite else { return false }
        return value > 0
    }

    /// The web's own `fmtTime`: `m:ss`, or `h:mm:ss` past an hour; null/NaN/negative → `0:00`.
    ///
    /// ⚠ Ported line for line, including `Math.floor` (a 2:40:02.9 reads `2:40:02`, never `2:40:03`) —
    /// his prototype's own `fmt` rounds instead, and rounding a clock forward is how a scrubber in the
    /// last second of a film shows a time the film does not reach. The web's behaviour wins.
    static func fmtTime(_ totalSeconds: Double?) -> String {
        let raw = isFiniteNumber(totalSeconds) ? (totalSeconds ?? 0) : 0
        let seconds = Int(max(0, raw).rounded(.down))
        let hours = seconds / 3600
        let minutes = (seconds % 3600) / 60
        let secs = seconds % 60
        let ss = String(format: "%02d", secs)
        if hours > 0 {
            return "\(hours):\(String(format: "%02d", minutes)):\(ss)"
        }
        return "\(minutes):\(ss)"
    }

    /// The bar's authoritative total: the stream's own duration once it is finite, else the API's
    /// runtime hint — so the bar and the total are right from the FIRST frame, before any metadata
    /// arrives. (Port of `barTotal`; the same reason it exists on the web applies here, where the
    /// index for an MKV can take a moment.)
    static func barTotal(streamDuration: Double?, runtimeHint: Double?) -> Double {
        if isFiniteDuration(streamDuration) { return streamDuration ?? 0 }
        let hint = isFiniteNumber(runtimeHint) ? (runtimeHint ?? 0) : 0
        return max(0, hint.rounded(.down))
    }

    /// ⚠ `total == 0` steps FORWARD only — a zero total means "not known yet", and clamping to it would
    /// pin the playhead at 0 while the video is already playing.
    static func clampSeek(_ target: Double, total: Double) -> Double {
        if total > 0 { return min(max(0, target), total) }
        return max(0, target)
    }

    /// ⚠ `Back 10s` / `Forward 10s`, and the scrubber's own jog, in ONE rule — his prototype's two
    /// verbs (`cur - 10` / `cur + 10`) and its 30-second track jog, all through `clampSeek`.
    static let skipSeconds: Double = 10
    static let jogSeconds: Double = 30

    static func skipTarget(from position: Double, by delta: Double, total: Double) -> Double {
        clampSeek(position + delta, total: total)
    }

    /// One second of playhead for one second of media — the progress bar's own arithmetic, extracted
    /// because BOTH the scrubber's fill and its tooltip position need it and they must not drift.
    /// ⚠ Returns `0` for an unknown total rather than a division by zero.
    static func progressFraction(position: Double, total: Double) -> Double {
        guard total > 0 else { return 0 }
        return min(max(0, position / total), 1)
    }

    // MARK: - Stream routing (ported from the web app's `pickStreamMode`)

    /// How Jellyfin should serve this item. The four strings ARE the query values the api accepts
    /// (`backend/api/routes/jellyfin_stream.py`), so this enum is the single place they are spelled —
    /// and R4 in `check-tvos-models.py` checks the endpoints that carry them.
    enum StreamMode: String, CaseIterable {
        /// Static file, HTTP-range seekable.
        case direct
        /// Copy/copy into MP4 — for a container this client cannot index up-front.
        case remux
        /// Video copied, audio → AAC (EAC3/AC3/DTS/TrueHD the client cannot decode).
        case transcodeAudio = "transcode_audio"
        /// H.264 + AAC — unwelcome video codec, or a lower bitrate was asked for.
        case transcode
    }

    /// ⚠⚠ **WHICH CODECS *THIS* CLIENT DECODES — THE ONE PARAMETER THAT MAKES ROUTING HONEST.**
    /// The web decides "does the audio need transcoding?" against a **browser's** capability set, and a
    /// television's is different. The plan's rule (`docs/TVOS_PLAYER_PLAN.md` §3, C2) is that this is a
    /// *parameter*, never a hardcoded "Apple = remux": a second client must be able to bring its own
    /// answer, and the round must be able to prove this one wrong.
    struct PlaybackCodecs {
        /// Containers this client can index up-front (duration + byte-range seeking).
        let directContainers: Set<String>
        /// Video codecs decoded natively.
        let video: Set<String>
        /// Audio codecs decoded natively.
        let audio: Set<String>
        /// Whether a 10-bit H.264 stream is undecodable by this client.
        let refusesTenBitH264: Bool
        /// For the label only, so a log line says which set was applied.
        let name: String

        /// The web's own sets, transcribed: `DIRECT_CONTAINERS` + `SAFE_VIDEO_CODECS` + `BROWSER_SAFE_AUDIO`.
        static let webBrowser = PlaybackCodecs(
            directContainers: ["mp4", "m4v", "mov", "webm"],
            video: ["h264", "avc1", "vp9", "av01", "vp8", "theora"],
            audio: ["aac", "mp3", "opus", "vorbis", "flac",
                    "pcm_s16le", "pcm_s24le", "pcm_mulaw", "alac"],
            refusesTenBitH264: true,
            name: "web-browser")

        /// ⚠⚠ **THE tvOS SET, AND ITS HONEST STATUS: IT IS A [hypothesis].** Its source is
        /// `docs/APPLE_CLIENTS_PLAN.md` §4.3's record that Apple silicon decodes **HEVC** and **EAC3** in
        /// hardware — which is exactly the pair the web has to transcode, and the reason a tvOS client
        /// should be able to ask for `remux` far more often than Chrome can.
        /// ⚠ It is NOT measured here (no tvOS SDK in the sandbox), so the round falsifies it: if a
        /// `remux` of an HEVC/EAC3 title fails to play, the answer is to correct THIS SET — one value —
        /// and not to add a fallback ladder nobody asked for.
        /// ⚠ `mp4`-family stays the direct set: a `mov`/`m4v` is byte-range seekable on Apple platforms
        /// for the same reason it is in a browser, and `mp4` is the container Jellyfin's `Static=true`
        /// serves untouched.
        static let tvOS = PlaybackCodecs(
            directContainers: ["mp4", "m4v", "mov"],
            video: ["h264", "avc1", "hevc", "h265", "vp9", "av01"],
            audio: ["aac", "mp3", "opus", "flac", "alac", "eac3", "ac3", "pcm_s16le", "pcm_s24le"],
            // ⚠ Still refused: nothing in this repo's record says Apple silicon decodes H.264 High-10,
            // and being wrong here costs a transcode — being wrong the other way costs a black screen.
            refusesTenBitH264: true,
            name: "tvos")
    }

    /// True when the video stream must be re-encoded for this client. ⚠ **Unknown facts mean FALSE**
    /// (attempt it; the report is what tells us) — the web's own rule, and the reason a missing codec
    /// does not send every title through a transcode.
    static func videoNeedsTranscode(codec: String?, profile: String?, bitDepth: Int?,
                                    codecs: PlaybackCodecs) -> Bool {
        let codecValue = (codec ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        if !codecValue.isEmpty && !codecs.video.contains(codecValue) { return true }
        if codecValue == "h264" || codecValue == "avc1" {
            if (bitDepth ?? 0) >= 10 && codecs.refusesTenBitH264 { return true }
            let prof = (profile ?? "").lowercased()
            if prof.contains("10") { return true }
        }
        return false
    }

    static func audioCodecNeedsTranscode(codec: String?, codecs: PlaybackCodecs) -> Bool {
        let value = (codec ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        if value.isEmpty { return false }
        return !codecs.audio.contains(value)
    }

    /// The cheapest mode that will actually play. Ported from `pickStreamMode`, whose comment records
    /// the live measurement behind two of these lines: **Jellyfin IGNORES `AudioStreamIndex` and
    /// `MaxStreamingBitrate` under `Static=true`**, so asking for a track or a quality forces a
    /// non-direct mode.
    static func pickStreamMode(quality: String,
                               container: String?,
                               videoCodec: String?,
                               videoProfile: String?,
                               videoBitDepth: Int?,
                               activeAudioCodec: String?,
                               forceNonDirect: Bool = false,
                               codecs: PlaybackCodecs = .tvOS) -> StreamMode {
        if quality != defaultQualityLabel { return .transcode }
        if videoNeedsTranscode(codec: videoCodec, profile: videoProfile, bitDepth: videoBitDepth,
                              codecs: codecs) { return .transcode }
        if audioCodecNeedsTranscode(codec: activeAudioCodec, codecs: codecs) { return .transcodeAudio }
        let name = (container ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        if forceNonDirect || (!name.isEmpty && !codecs.directContainers.contains(name)) { return .remux }
        return .direct
    }

    /// The mode chip's words, ported from the web (`streamModeLabel`).
    static func streamModeLabel(_ mode: StreamMode) -> String {
        switch mode {
        case .direct: return "Direct play"
        case .remux: return "Remux"
        case .transcodeAudio: return "Transcode (audio)"
        case .transcode: return "Transcode"
        }
    }

    /// ⚠ **The badge in the player's top bar, and it is his prototype's spelling, not the web's.**
    /// `rkm-cinema-tvos-player.html` renders `<span class="badge">Remux · HLS</span>`; the web's
    /// `hlsModeLabel("remux")` says `Remux (HLS)`. Both are the same fact — this screen is the one
    /// being built, so its own file wins, and the divergence is recorded rather than invented.
    static func badgeText(_ mode: StreamMode) -> String {
        switch mode {
        case .direct: return "Direct play"
        case .remux: return "Remux · HLS"
        case .transcodeAudio: return "Transcode (audio) · HLS"
        case .transcode: return "Transcode · HLS"
        }
    }

    /// The Jellyfin `PlayMethod` reported with progress — `play_method` on the wire.
    static func playMethod(_ mode: StreamMode) -> String {
        switch mode {
        case .direct: return "DirectPlay"
        case .remux: return "DirectStream"
        case .transcodeAudio, .transcode: return "Transcode"
        }
    }

    /// ⚠ Everything non-direct rides the HLS transport; only a static MP4 is range-seekable.
    static func usesHLS(_ mode: StreamMode) -> Bool { mode != .direct }

    /// The escalation order on a fatal HLS error. ⚠ Audio-aware: a copy-copy remux of an EAC3 title
    /// keeps `ec-3` in the playlist, so a client that cannot decode it must go to `transcode_audio`
    /// next rather than retrying the same thing.
    static let hlsLadder: [StreamMode] = [.remux, .transcodeAudio, .transcode]

    static func nextHLSMode(after mode: StreamMode) -> StreamMode? {
        if mode == .direct { return hlsLadder.first }
        guard let index = hlsLadder.firstIndex(of: mode) else { return nil }
        return index < hlsLadder.count - 1 ? hlsLadder[index + 1] : nil
    }

    // MARK: - Quality

    /// A quality choice: a LABEL (what the viewer sees) and a bitrate (what the api is told), or `nil`
    /// for "Original", which means unthrottled.
    ///
    /// ⚠⚠ **THE LABELS AND THE BITRATES ARE THE WEB APP'S (`QUALITY_OPTIONS`), NOT THE PROTOTYPE'S.**
    /// His player file shows the same four labels but describes them with invented numbers
    /// (`Auto · 1080p · 4.2 Mbps`). A number on screen that the server was never asked for is a claim,
    /// so the caption is generated from THIS table instead.
    struct Quality: Equatable {
        let label: String
        let bitrate: Int?
    }

    static let defaultQualityLabel = "Original"

    static let qualities: [Quality] = [
        Quality(label: "Original", bitrate: nil),
        Quality(label: "1080p", bitrate: 8_000_000),
        Quality(label: "720p", bitrate: 5_000_000),
        Quality(label: "480p", bitrate: 2_500_000),
    ]

    static func quality(for label: String) -> Quality? {
        qualities.first { $0.label == label }
    }

    /// The bitrate the api is asked for, or `0` for "Original" (the api's own sentinel: *0 = original*).
    static func maxBitrate(for label: String) -> Int {
        quality(for: label)?.bitrate ?? 0
    }

    /// The caption under the Quality row — honest by construction: it names the bitrate the app will
    /// actually ask Jellyfin for, and nothing else.
    static func qualityCaption(for label: String) -> String {
        guard let quality = quality(for: label), let bitrate = quality.bitrate else {
            return "Original — no bitrate cap."
        }
        let mbps = Double(bitrate) / 1_000_000
        return "\(label) · capped at \(String(format: "%.1f", mbps)) Mbps on a transcode."
    }

    // MARK: - Playback speed

    /// ⚠ **His prototype's own five, and the web's `PLAYBACK_RATES` is the same five** — `[0.5, 1,
    /// 1.25, 1.5, 2]`. Client-side only (`AVPlayer.rate`), no server involvement.
    static let rates: [Double] = [0.5, 1, 1.25, 1.5, 2]
    static let defaultRate: Double = 1

    /// ⚠ `1×` and `2×` come from the prototype; `1.25×` loses its trailing zero — one place formats
    /// every rate so the row cannot show `1.250×` beside `1×`.
    static func rateLabel(_ rate: Double) -> String {
        var text = String(format: "%.2f", rate)
        while text.hasSuffix("0") { text.removeLast() }
        if text.hasSuffix(".") { text.removeLast() }
        return text + "×"
    }

    /// Fit / Fill — his prototype's segmented control, whose second caption is his own sentence.
    /// ⚠ This is `AVPlayerLayer.videoGravity` on the client; nothing here reaches the server.
    enum PictureMode: String, CaseIterable {
        case fit
        case fill

        var title: String {
            switch self {
            case .fit: return "Fit"
            case .fill: return "Fill"
            }
        }

        var caption: String {
            switch self {
            case .fit: return "Whole frame — bars where the screen is wider."
            case .fill: return "Edge to edge — the picture crops slightly to fill the screen."
            }
        }
    }

    // MARK: - Progress reporting

    /// The three events the api accepts (`_KNOWN_EVENTS` in `backend/api/routes/jellyfin_stream.py`).
    enum ProgressEvent: String {
        case start
        case timeupdate
        case stopped
    }

    /// ⚠⚠ **THE CLIENT DOES NOT DECIDE "WATCHED" — THE SERVER DOES.** `jellyfin_stream.py` marks an item
    /// played when a `stopped` report lands within `FINISHED_FRACTION = 0.95` of the runtime. This
    /// constant exists so the CLIENT can answer a different question — *should the next episode be
    /// offered* — with the same threshold the server uses, instead of a second, drifting one. Two
    /// copies of one rule is this repo's most-repeated defect; one constant read by both is not.
    static let finishFraction: Double = 0.95

    static func finished(positionTicks: Int, runtimeTicks: Int) -> Bool {
        guard runtimeTicks > 0 else { return false }
        return Double(positionTicks) >= Double(runtimeTicks) * finishFraction
    }

    /// ⚠ The web throttles `timeupdate` reports to **one every 5 seconds** (`Player.tsx`: *"if (now -
    /// lastReportRef.current < 5000) return"*). Same number here — the api writes on every call, and a
    /// report per frame would be thousands of Jellyfin writes per film.
    static let progressReportInterval: Double = 5

    static func shouldReport(elapsedSinceLastReport: Double) -> Bool {
        elapsedSinceLastReport >= progressReportInterval
    }

    /// How long a position is held before the save is considered failed on screen. ⚠ The screen's own
    /// threshold, not a server fact; it exists so a stalled write is visible rather than silent.
    static let saveHintDelay: Double = 2.5

    // MARK: - Tracks and subtitles (ported from the web's matcher)

    /// ISO-639-2/B → 639-1 exceptions. ⚠ Needed because the subtitle store holds `en` while a stream
    /// reports ffprobe's `eng` — a literal comparison never matches, and the auto-apply then does
    /// nothing *silently*, which is the failure mode this table exists to prevent.
    static let languageExceptions: [String: String] = [
        "ger": "de", "deu": "de", "fre": "fr", "fra": "fr", "dut": "nl", "nld": "nl", "cze": "cs",
        "ces": "cs", "gre": "el", "ell": "el", "rum": "ro", "ron": "ro", "slo": "sk", "slk": "sk",
        "chi": "zh", "zho": "zh", "may": "ms", "msa": "ms", "per": "fa", "fas": "fa", "alb": "sq",
        "sqi": "sq", "arm": "hy", "hye": "hy", "geo": "ka", "kat": "ka", "ice": "is", "isl": "is",
        "mac": "mk", "mkd": "mk", "mao": "mi", "mri": "mi", "wel": "cy", "cym": "cy", "bur": "my",
        "mya": "my", "tib": "bo", "bod": "bo", "scc": "sr", "srp": "sr", "swe": "sv",
    ]

    /// A comparable two-letter key: `eng`/`EN` → `en`, `pt-BR` → `pt`, `ger` → `de`.
    static func languageKey(_ value: String?) -> String {
        var text = (value ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        if text.isEmpty { return "" }
        if text.contains("-") || text.contains("_") {
            text = text.replacingOccurrences(of: "_", with: "-")
            text = String(text.split(separator: "-")[0])
        }
        if text.count == 3 {
            return languageExceptions[text] ?? String(text.prefix(2))
        }
        if text.count > 3 {
            let head = String(text.prefix(3))
            return languageExceptions[head] ?? String(text.prefix(2))
        }
        return text
    }

    /// Which local subtitle track a stored choice means, or `nil` for "off/none".
    ///
    /// ⚠⚠ Ported in the web's ORDER, and the order is the whole rule: an exact `display_title` match
    /// first (the store remembers the identity a human picked), then a LANGUAGE match (the same film,
    /// re-indexed), then nothing. ⚠ Stream indices are POSITIONAL, which is why the server resolves the
    /// stored identity to a current index and why this must not invent one.
    static func resolveActiveSubtitle(tracks: [PlaybackTrack],
                                      preferredDisplayTitle: String?,
                                      preferredLanguage: String?) -> Int? {
        guard !tracks.isEmpty else { return nil }
        let wanted = (preferredDisplayTitle ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        if !wanted.isEmpty {
            if let exact = tracks.first(where: {
                $0.name.trimmingCharacters(in: .whitespaces).lowercased() == wanted
            }) {
                return exact.index
            }
        }
        let language = languageKey(preferredLanguage)
        if !language.isEmpty {
            if let same = tracks.first(where: { languageKey($0.language) == language }) {
                return same.index
            }
        }
        return nil
    }

    /// The audio a chosen index means, or the FIRST track — the api's own default (`AudioStreamIndex`
    /// is only forwarded when it is `> 0`), so passing `0` and passing nil mean the same thing.
    static func audioCodecFor(index: Int?, tracks: [PlaybackTrack]) -> String? {
        guard !tracks.isEmpty else { return nil }
        guard let index, index > 0 else { return tracks.first?.codec }
        return tracks.first { $0.index == index }?.codec ?? tracks.first?.codec
    }

    /// ⚠ `AudioStreamIndex` is ONLY meaningful on a non-direct mode (Jellyfin ignores it under
    /// `Static=true`), so choosing a track has to force a remux. This is the api's rule, not a policy.
    static func choosingATrackForcesNonDirect(audioIndex: Int?) -> Bool { (audioIndex ?? 0) > 0 }

    /// `5 audio · 1 sub` — his prototype's footer, from the real counts.
    static func trackSummary(audioCount: Int, subtitleCount: Int) -> String {
        let audio = "\(audioCount) audio"
        let subs = "\(subtitleCount) sub" + (subtitleCount == 1 ? "" : "s")
        return "\(audio) · \(subs)"
    }

    /// `Hindi · English, Hindi subtitles` — his prototype's meta row, from the real tracks.
    ///
    /// ⚠ It is built from what the SERVER sent, never from a fixed sentence: the first part is the
    /// active audio track's language (absent when the server did not say), the second part lists the
    /// subtitle tracks' languages, and a film with none says so rather than leaving a dangling dot.
    static func languageLine(activeAudioLanguage: String?, subtitleLanguages: [String]) -> String {
        var parts: [String] = []
        let audio = titleCased(activeAudioLanguage)
        if !audio.isEmpty { parts.append(audio) }
        let languages = subtitleLanguages
            .map { titleCased($0) }
            .filter { !$0.isEmpty }
        if languages.isEmpty {
            parts.append("No subtitles")
        } else {
            parts.append(languages.joined(separator: ", ") + " subtitles")
        }
        return parts.joined(separator: " · ")
    }

    /// `en` → `En`, `eng` → `En`, `pt-br` → `Pt-br`. ⚠ Deliberately NOT a language-name table: a
    /// two-letter code the app cannot name is better on screen than an invented name it got wrong.
    static func titleCased(_ value: String?) -> String {
        let text = (value ?? "").trimmingCharacters(in: .whitespaces)
        if text.isEmpty { return "" }
        return text.prefix(1).uppercased() + text.dropFirst().lowercased()
    }

    // MARK: - The settings drawer (his prototype's five categories)

    /// One row of the drawer's left rail. ⚠ The ORDER is his file's, and it is the order a viewer's
    /// most-likely want sits in: picture, speed, quality, audio, subtitles.
    enum SettingsCategory: String, CaseIterable {
        case picture
        case speed
        case quality
        case audio
        case subtitles

        var title: String {
            switch self {
            case .picture: return "Picture"
            case .speed: return "Speed"
            case .quality: return "Quality"
            case .audio: return "Audio Track"
            case .subtitles: return "Subtitles"
            }
        }

        /// Which kind of control the pane draws. ⚠ It is a property of the CATEGORY rather than a
        /// switch inside the view, so a view cannot render the quality ladder as a segmented control or
        /// the speeds as a list.
        var pane: Pane {
            switch self {
            case .picture, .speed, .quality: return .segmented
            case .audio, .subtitles: return .list
            }
        }
    }

    enum Pane: Equatable {
        /// A row of small, mutually exclusive choices (Fit/Fill, the speeds, the quality ladder).
        case segmented
        /// A list of the item's own tracks, plus (for subtitles) the actions the api offers.
        case list
    }

    /// ⚠⚠ **THE DEFAULT FOCUS IS PLAY/PAUSE, AND IT IS HIS DESIGN'S.** His prototype's focus engine
    /// starts at row 2, index 2 (*"let r = 2, i = 2; // default focus: play/pause"*). What is NOT ported
    /// is its JavaScript: nearest-neighbour focus maths and `scrollIntoView` are exactly what tvOS's
    /// focus engine already does, twice paid for in this repo (`RailFocus.swift`, B3's grid). What IS
    /// ours is where focus STARTS — a design decision, expressed here so the view does not invent it.
    static let defaultFocusIsPlayPause = true

    /// ⚠⚠ **THE CHROME HIDES AFTER 4 SECONDS OF IDLE — HIS PROTOTYPE'S NUMBER, AND THE WEB'S IS 2.8.** A
    /// deliberate divergence, recorded so it is not "fixed" later: the web's rule is tuned for a
    /// POINTER (which moves the instant a hand does), and a tvOS remote is quiet while someone watches.
    /// The web's own condition set is ported in full — nothing hides while paused, while the stream is
    /// switching, on an error, or while the drawer or the info panel is open.
    static let chromeHideSeconds: Double = 4
    static let webChromeHideSeconds: Double = 2.8

    static func shouldHideChrome(playing: Bool,
                                 switching: Bool,
                                 failed: Bool,
                                 hoveringChrome: Bool,
                                 panelOpen: Bool,
                                 idleSeconds: Double) -> Bool {
        if panelOpen { return false }
        if !playing || switching || failed || hoveringChrome { return false }
        return idleSeconds >= chromeHideSeconds
    }

    // MARK: - Subtitles as text (WebVTT, ported from the web's parser)

    /// One subtitle cue: a time range and its text. ⚠ The text is PLAIN — the prototype and the api
    /// both hand over WebVTT that can carry `<i>`/`<b>` tags, and a TV showing raw markup is worse than
    /// showing nothing.
    struct Cue: Equatable {
        let start: Double
        let end: Double
        let text: String
    }

    /// `hh:mm:ss.mmm`, `mm:ss.mmm` or `mm:ss,mmm` → seconds. Unparseable → `0`, which is the web
    /// parser's own answer (and the only safe one: a cue that starts at an unknown time must not be
    /// shown at an invented one).
    static func vttTime(_ raw: String) -> Double {
        let text = raw.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return 0 }
        // The fraction separator is `.` in WebVTT and `,` in SRT — the api's upstream can be either.
        let separatorIndex = text.lastIndex(where: { $0 == "." || $0 == "," })
        guard let separatorIndex else { return 0 }
        let clock = String(text[text.startIndex..<separatorIndex])
        let fraction = String(text[text.index(after: separatorIndex)...])
        guard !clock.isEmpty, !fraction.isEmpty,
              fraction.count <= 3, fraction.allSatisfy({ $0.isNumber }) else { return 0 }
        let parts = clock.split(separator: ":", omittingEmptySubsequences: false).map(String.init)
        guard parts.count == 2 || parts.count == 3, parts.allSatisfy({ !$0.isEmpty }) else { return 0 }
        guard let seconds = Int(parts[parts.count - 1]), let minutes = Int(parts[parts.count - 2]) else {
            return 0
        }
        let hours = parts.count == 3 ? (Int(parts[0]) ?? 0) : 0
        let padded = fraction + String(repeating: "0", count: 3 - fraction.count)
        guard let millis = Int(padded) else { return 0 }
        return Double(hours * 3600 + minutes * 60 + seconds) + Double(millis) / 1000
    }

    /// Minimal WebVTT parser — enough for the api's `Stream.vtt`: timing lines (`start --> end
    /// [settings]`) plus multi-line text until a blank line; `NOTE`/`STYLE`/`REGION` blocks and inline
    /// tags are skipped. Ported from the web's `parseVtt`, including the two behaviours that matter:
    /// **an empty cue is dropped**, and the timing line's END token is the first whitespace-delimited
    /// word (a cue can carry `align:start position:10%` settings after the end time).
    static func parseVTT(_ text: String) -> [Cue] {
        var cues: [Cue] = []
        let lines = text.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n")
        var index = 0
        while index < lines.count {
            let line = lines[index].trimmingCharacters(in: .whitespaces)
            guard line.contains("-->") else {
                index += 1
                continue
            }
            let halves = line.components(separatedBy: "-->")
            let startToken = halves.first ?? ""
            let rest = halves.count > 1 ? halves[1] : ""
            let endToken = rest.trimmingCharacters(in: .whitespaces)
                .split(separator: " ", omittingEmptySubsequences: true)
                .first
                .map(String.init) ?? ""
            var textLines: [String] = []
            index += 1
            while index < lines.count && !lines[index].trimmingCharacters(in: .whitespaces).isEmpty {
                textLines.append(lines[index])
                index += 1
            }
            let clean = stripTags(textLines.joined(separator: "\n"))
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !clean.isEmpty {
                cues.append(Cue(start: vttTime(startToken), end: vttTime(endToken), text: clean))
            }
        }
        return cues
    }

    /// The cue active at `position` seconds (`start ≤ position < end`), or `nil`.
    ///
    /// ⚠ It walks in ORDER and returns the FIRST match — a cue that ends exactly where the next begins
    /// must not be replaced early, and the web's parser relies on the same half-open interval.
    static func activeCue(_ cues: [Cue], position: Double) -> String? {
        for cue in cues where position >= cue.start && position < cue.end {
            return cue.text
        }
        return nil
    }

    /// Drop inline markup (`<i>`, `<b>`, `<font …>`) from a cue's text.
    /// ⚠ Written as a scanner rather than a regex: no regex engine in a file whose whole point is to be
    /// runnable everywhere, and an unbalanced `<` must not swallow the rest of the subtitle.
    static func stripTags(_ text: String) -> String {
        var out = ""
        var inside = false
        for character in text {
            if character == "<" {
                inside = true
                continue
            }
            if character == ">" {
                inside = false
                continue
            }
            if !inside { out.append(character) }
        }
        return out
    }
}
