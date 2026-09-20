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

    /// ⚠⚠ **THE SCRUB ROW'S OWN VERB — and until Phase P it had none.** His prototype's row 1 is the whole
    /// track, and a left/right press INSIDE it does not move focus: `moveItem` jogs time
    /// (`rkm-cinema-tvos-player.html:573`: `cur + dir*30`), which is why the row is one focusable control
    /// rather than seven. ⚠ The screen's comment claimed *"left/right JOG the position … which the screen
    /// wires up"* and **nothing wired it**: `jogSeconds` was read by no file, the track's `Button` had an
    /// empty action, and a left/right press on a focused track fell through to the focus engine, which found
    /// no neighbour and did nothing. This is the rule that was missing.
    ///
    /// ⚠ It COMPOSES `skipTarget` rather than repeating the clamp — one clamp, two callers, which is the
    /// difference between naming a verb and growing a second copy of a rule.
    ///
    /// ⚠ `step` defaults to his file's 30 s, so a SINGLE press is exactly the prototype's `dir*30`; the
    /// acceleration below is what a viewer gets for pressing repeatedly.
    static func jogTarget(from position: Double, direction: Int, total: Double,
                          step: Double = jogSeconds) -> Double {
        skipTarget(from: position, by: Double(direction) * step, total: total)
    }

    // MARK: - The jog's acceleration (⚠ the app's own; his file has one step)

    /// ⚠⚠ **WHY THERE IS MORE THAN ONE STEP, AND IT IS HIS ROUND THAT ASKED FOR IT.** His report:
    /// *"there is oonly 10 second back and forth control, i cant use touch control … to move forward or
    /// backward wherever i want"*. At a flat 30 s a two-and-a-half hour film is **320 presses** end to end,
    /// which is not "wherever I want" — it is a control that technically reaches every position and
    /// practically reaches none.
    ///
    /// ⚠ **NOT FROM HIS FILE**: it specifies one 30 s step, and this ladder is the app's own addition,
    /// declared as such in `docs/TVOS_PLAYER_POLISH_PLAN.md` §6. The FIRST step is still his 30 s, so a
    /// single press behaves exactly as the prototype does; only the repeated ones grow.
    static let jogSteps: [Double] = [jogSeconds, 60, 120, 300, 600]

    /// ⚠ How long a gap between presses still counts as "the same scrub". Faster than this and the step
    /// grows; slower and it starts again at 30 s — so a viewer who paused to think about what they were
    /// doing is never surprised by a five-minute jump.
    static let jogAccelerationWindow: Double = 1.2

    /// The repeat counter after a gap: inside the window the ladder CONTINUES, outside it restarts at 1.
    static func jogRepeats(current: Int, gapSinceLastJog: Double) -> Int {
        gapSinceLastJog <= jogAccelerationWindow ? current + 1 : 1
    }

    /// The distance the `repeats`-th press of a run moves the playhead.
    /// ⚠ Clamped at the ladder's own end rather than allowed to run off it, so the step can never be
    /// `jogSteps[99]` and a longer ladder is a change to ONE array.
    static func jogStep(repeats: Int) -> Double {
        guard repeats > 0 else { return jogSteps[0] }
        return jogSteps[min(repeats - 1, jogSteps.count - 1)]
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

    // MARK: - The one line that says who decides whether the film is running

    /// ⚠⚠ **THE RATE `AVPlayer` IS GIVEN FOR A STORE STATE — AND IT EXISTS BECAUSE OF HIS BUG 1.**
    ///
    /// **The domain fact the whole defect turned on: `rate = 1` IS `play()`.** `AVPlayer` has no separate
    /// play/pause call in this screen's plumbing — the rate *is* the transport — so a line that sets a rate
    /// sets the film running, whether or not anybody meant it to. `attachItem` did exactly that
    /// (`player.rate = Float(store.rate)`) while `isPlaying` said `false`, and the result was a transport
    /// offering *Play* over a moving picture, a first press that did nothing, and a second that paused.
    ///
    /// ⇒ **A paused film is given `0`, not its speed.** ⚠ Returns `Float` because that is `AVPlayer`'s own
    /// type — and it is named here so the two call sites that set a rate cannot disagree about the rule
    /// (that duplication is how the original defect survived: the rate was set in two places, and neither
    /// consulted the flag).
    static func playerRate(isPlaying: Bool, rate: Double) -> Float {
        isPlaying ? Float(rate) : 0
    }

    /// The escalation order on a fatal HLS error. ⚠ Audio-aware: a copy-copy remux of an EAC3 title
    /// keeps `ec-3` in the playlist, so a client that cannot decode it must go to `transcode_audio`
    /// next rather than retrying the same thing.
    static let hlsLadder: [StreamMode] = [.remux, .transcodeAudio, .transcode]

    static func nextHLSMode(after mode: StreamMode) -> StreamMode? {
        if mode == .direct { return hlsLadder.first }
        guard let index = hlsLadder.firstIndex(of: mode) else { return nil }
        return index < hlsLadder.count - 1 ? hlsLadder[index + 1] : nil
    }

    /// The ladder's length — ⚠ the number in the sentence below is DERIVED from it, never typed twice.
    static let ladderLength = hlsLadder.count

    /// ⚠⚠ **WHOSE FAULT AN ESCALATION IS, AND THE ONE MODE THAT IS NOT ON THE LADDER.** `direct` is not a
    /// rung: it is where every session starts, and a direct play that fails escalates to `hlsLadder.first`
    /// (`nextHLSMode`'s first line). So `direct` is step **0** — *"before the ladder"* — and the three HLS
    /// modes are steps 1…3. ⚠ Written as a rule rather than as a `+ 1` in a view because the step is what the
    /// viewer is told, and an off-by-one in a progress sentence is the kind of thing that reads as a bug.
    static func ladderStep(_ mode: StreamMode) -> Int {
        guard let index = hlsLadder.firstIndex(of: mode) else { return 0 }
        return index + 1
    }

    /// The sentence an escalation shows. ⚠ It names **where the session now is on the ladder**, because a
    /// viewer who sees a stream fail twice deserves to know the app is changing something and not just
    /// retrying the same request — and a silent retry loop is indistinguishable from a broken app.
    static func attemptSentence(_ mode: StreamMode) -> String {
        let step = ladderStep(mode)
        return "Trying \(streamModeLabel(mode)) (\(step) of \(ladderLength))…"
    }

    /// ⚠ **THE SENTENCE FOR AN ITEM THAT NEVER STARTED** — `AVPlayerItem.status == .failed`. It is one string
    /// in one place so the notification path (a stream that died mid-film) and the status path (a stream that
    /// never began) cannot end up telling the viewer two different stories about the same black screen.
    static let failedToStartSentence =
        "This stream would not start. The server refused every mode this app can ask for."

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

    // MARK: - Up Next (the next episode of a series)

    /// How long the Up Next card counts down before it plays.
    ///
    /// ⚠⚠ **A NUMBER THE APP CHOSE, SAID SO OUT LOUD — his prototype has no Up Next at all.** The platform's
    /// own apps sit in the 10–20 s band; 15 s is long enough to read a card and reach the remote, short enough
    /// that a viewer who wants the next episode is not made to wait. ⚠ It is ONE token on purpose: if his
    /// round says it feels wrong, the answer is this number and not the card's layout.
    static let upNextSeconds: Double = 15

    /// ⚠ The card's remaining seconds, **rounded UP**, so the last second reads `1` rather than `0` while the
    /// countdown is still running — a card that shows `0` and does not act is a card that looks broken.
    static func upNextRemaining(deadline: Double, now: Double) -> Int {
        let left = deadline - now
        if left <= 0 { return 0 }
        return Int(left.rounded(.up))
    }

    /// **The next episode, BY POSITION IN THE SERVER'S OWN LIST.**
    ///
    /// ⚠⚠ **WHY NOT `episode + 1`, AND THIS IS THE WHOLE RULE.** A season boundary (`S1E10` → `S2E1`), a
    /// special slotted mid-season, a gap in Jellyfin's numbering, and a multi-season list all break
    /// arithmetic — and the list is already in hand, so there is nothing to guess. The server's order is the
    /// authority on what comes next; the app's job is to find ONE element in it and step to the next.
    ///
    /// ⚠ Three separate answers, and the screen needs all three: the current episode is not in the list
    /// (`nil` — the app cannot say what follows), it is the LAST one (`nil` — **this is P-F9**, and it is why
    /// this returns an optional rather than a wrapped index), or there is a next one.
    static func nextEpisode(after episodeID: String, in episodes: [EpisodeItem]) -> EpisodeItem? {
        guard let index = episodes.firstIndex(where: { $0.id == episodeID }) else { return nil }
        let next = index + 1
        return next < episodes.count ? episodes[next] : nil
    }

    /// The card's caption: `S2E5 · The Reckoning`.
    ///
    /// ⚠⚠ **IT CALLS `DetailRules.episodeCode` — IT DOES NOT SPELL `"S\(season)E\(episode)"` AGAIN.** The title
    /// screen already has that rule, already pinned, and a second copy of one small string is precisely the
    /// defect this repo keeps paying for (`ARCHITECTURE.md` §0's first rule). What is new here is only the
    /// caption's SHAPE; the code itself is borrowed.
    static func upNextLabel(season: Int, episode: Int, name: String) -> String {
        "\(DetailRules.episodeCode(season: season, episode: episode)) · \(name)"
    }

    // MARK: - The subtitles pane (his round: "i click on subtitles all the other control vanishes")

    /// ⚠⚠ **HOW MANY REMOTE RESULTS THE PANE HOLDS — AND IT IS A GUARD, NOT THE DISPLAY LIMIT.**
    ///
    /// His report, with the screenshot: *"i click on subtitles all the other control vanishes.. i only see"* —
    /// followed by **nineteen** rows of OpenSubtitles release names (`.The.Mummy.1999.1080p.BluRay.x264.AC3-ETRG
    /// · EN`, …). ⚠ `subtitle-search` had been fetched on LOAD with no language filter, so every result the
    /// provider had was already in the pane before the viewer asked for anything, and the pane drew all of them.
    ///
    /// ⚠⚠ **WHAT THE LIST MAY NOT DO IS DECIDE THE PANEL'S HEIGHT** — see `settingsPanelFits`, which puts the
    /// defect on the record as arithmetic: **19 rows was 1875.2 pt of panel on a 1080 pt screen.**
    /// ⇒ The VIEWPORT is bounded (and scrolls), which is what makes the panel fit at ANY count; this constant
    /// is the second line of defence, against a provider answering with hundreds.
    static let subtitleResultLimit = 20

    /// ⚠⚠ **THE REMOTE RESULTS ARE NOT SHOWN UNTIL THE VIEWER ASKS FOR THEM.**
    ///
    /// His prototype's Subtitles pane is *`Off` · the item's own tracks · "Search OpenSubtitles…"* — a list of
    /// the tracks the film HAS, plus an ACTION. It has no results in it, because a search has not been run.
    /// ⚠ The app fetched and drew them anyway, which is why a viewer who opened the drawer to turn subtitles
    /// OFF was met with nineteen release names instead of the one row he wanted.
    ///
    /// ⚠ `hasSearched` is the store's, and it is set by `searchSubtitles()` — the ACTION — and by nothing else.
    static func subtitleRemoteRows(_ rows: [SubtitleRow], hasSearched: Bool,
                                   limit: Int = subtitleResultLimit) -> [SubtitleRow] {
        guard hasSearched else { return [] }
        return Array(rows.prefix(max(0, limit)))
    }

    /// **The provider's own popularity, in the words a viewer can read at three metres.**
    ///
    /// `312 downloads` · `42.4k downloads` · `1.2M downloads` — and **`""` for a row the provider sent no
    /// count for**, because a row that prints `0 downloads` is claiming a fact the app does not have.
    /// ⚠ The rounding is the POINT at a distance: `42,412` is a string nobody reads across a lounge room,
    /// and `42.4k` is the same fact in four characters. One decimal below 100k, none above it.
    static func downloadsLabel(_ count: Int) -> String {
        guard count > 0 else { return "" }
        if count < 1_000 { return "\(count) download" + (count == 1 ? "" : "s") }
        let thousands = Double(count) / 1_000
        if thousands < 100 {
            // ⚠ The tenth is ROUNDED BY HAND before it is formatted, and that is not tidiness: `%.1f` on a
            // binary double rounds 84.05 DOWN to `84.0`, which reads as a truncation rather than a rounding.
            return String(format: "%.1fk downloads", (thousands * 10).rounded() / 10)
        }
        if count < 1_000_000 {
            return String(format: "%.0fk downloads", thousands)
        }
        return String(format: "%.1fM downloads", (Double(count) / 1_000_000 * 10).rounded() / 10)
    }

    /// **OUR** count — how many times this exact release has been chosen, here. `""` when it never has.
    ///
    /// ⚠ It is deliberately a different sentence from `downloadsLabel`: one says how popular the release is
    /// with the world, the other says how often the viewer has picked it, and a viewer who reads them as one
    /// number would think a first-time choice was a well-used one.
    static func usedTimesLabel(_ count: Int) -> String {
        guard count > 0 else { return "" }
        return count == 1 ? "used once" : "used \(count)×"
    }

    /// The badge on the row the auto-pick would take — and ⚠ **WHICH** fact put it there.
    ///
    /// `"used-before"` → *Your pick before*; `"most-downloaded"` → *Most downloaded*. Two different claims,
    /// because our usage count outranks the provider's popularity in the ranking: a row can be first for a
    /// reason that has nothing to do with how popular it is, and calling that "most downloaded" would be
    /// false — on the one line a viewer uses to decide whether to trust the default.
    static func autoPickBadge(basis: String) -> String {
        switch basis {
        case "used-before": return "Your pick before"
        case "most-downloaded": return "Most downloaded"
        default: return ""
        }
    }

    /// **The one sentence the Subtitles pane prints about the auto-pick — and only when he can act on it.**
    ///
    /// ⚠⚠ The api answers a CODE for every outcome, and its sentence for each. Three of them describe states
    /// the viewer created and can SEE in the rows above (a stored choice, a per-title `Off`, the switch) —
    /// printing those would put a line under every title he has ever watched. What is left is the set where
    /// the rule tried and could not: no quota, an unknown quota, no candidate, an unreachable vendor, no key.
    /// ⚠ `quota_unknown` is the important one: it is the answer an anonymous OpenSubtitles setup gets, and its
    /// sentence names the fix — a silent no-op would read as a broken feature.
    static func autoPickNotice(decision: String, reason: String) -> String? {
        let actionable: Set<String> = ["quota_unknown", "quota_exhausted", "no_candidate",
                                       "unavailable", "not_configured", "no_search_terms"]
        guard actionable.contains(decision) else { return nil }
        let text = reason.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }

    /// The auto-pick row's own value: `Most downloaded (en)` / `Off` — the state, and the language it acts in.
    static func autoPickSettingLabel(settings: SubtitleAutoPickSettings, language: String) -> String {
        guard settings.autoPick else { return "Off" }
        let code = language.trimmingCharacters(in: .whitespaces)
        return code.isEmpty ? "Most downloaded" : "Most downloaded (\(code))"
    }

    /// The exclusion row's value: which languages the auto-pick stays out of — `None` · `English audio`.
    ///
    /// ⚠ It names the languages it is excluding rather than counting them: "1 language" is a setting nobody
    /// can check, and the whole point of this control is being able to tell whether it is doing what he wants.
    static func autoPickSkipLabel(codes: [String]) -> String {
        let named = codes.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        guard !named.isEmpty else { return "None" }
        return named.map { languageName($0) }.joined(separator: ", ")
    }

    /// `en` → `English`, and anything unrecognised back unchanged (⚠ uppercase kept: `HI` is a language
    /// code, and lower-casing an unknown code would invent a word that is not one).
    static func languageName(_ code: String) -> String {
        let key = code.trimmingCharacters(in: .whitespaces).lowercased()
        return subtitleLanguageNames[key] ?? code
    }

    /// The languages this app can NAME. ⚠ Not a translation table — a display table, and small on purpose:
    /// an unknown code is shown as itself, which is honest, rather than guessed at.
    static let subtitleLanguageNames: [String: String] = [
        "en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu", "ml": "Malayalam",
        "kn": "Kannada", "bn": "Bengali", "mr": "Marathi", "pa": "Punjabi", "ur": "Urdu",
        "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
        "nl": "Dutch", "ru": "Russian", "ar": "Arabic", "zh": "Chinese", "ja": "Japanese",
        "ko": "Korean", "tr": "Turkish", "pl": "Polish", "sv": "Swedish", "no": "Norwegian",
        "da": "Danish", "fi": "Finnish", "el": "Greek", "he": "Hebrew", "th": "Thai",
        "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay",
    ]

    /// The remote row's SECOND line: the facts that tell two results apart when the first line is a release
    /// name. ⚠ Every part is a field the server sent (`SubtitleRow`), and an absent one is left out rather
    /// than rendered blank.
    ///
    /// ⚠⚠ **THE POPULARITY NUMBER IS HERE BECAUSE HE ASKED FOR IT** (2026-09-21: *"adding the no of times a
    /// subtitle is being downloaded … to better inform me the user"*), and so is **ours** — the two facts a
    /// viewer chooses between are "how good is this release" and "have I used it before".
    ///
    /// ⚠⚠ **`SDH`, NOT `HI`.** The web panel made this call first and the reason is in its comment: **`HI` is
    /// the language code for Hindi**, so a bare `HI` marker reads as a language on a Hindi subtitle — and a
    /// Hindi row would have read `HI · srt · opensubtitles · HI`. Phase P3 shipped `HI` on both rows; this is
    /// that defect, corrected.
    static func subtitleRowDetail(_ row: SubtitleRow) -> String {
        var parts: [String] = []
        let language = row.language.trimmingCharacters(in: .whitespaces).uppercased()
        if !language.isEmpty { parts.append(language) }
        let format = row.format.trimmingCharacters(in: .whitespaces).lowercased()
        if !format.isEmpty { parts.append(format) }
        let provider = row.provider.trimmingCharacters(in: .whitespaces)
        if !provider.isEmpty { parts.append(provider) }
        let downloads = downloadsLabel(row.downloadCount)
        if !downloads.isEmpty { parts.append(downloads) }
        let used = usedTimesLabel(row.usedCount)
        if !used.isEmpty { parts.append(used) }
        if row.hearingImpaired { parts.append("SDH") }
        return parts.joined(separator: " · ")
    }

    /// `Showing 8 of 19` — or `nil` when nothing was held back, because a line that says "Showing 8 of 8" is
    /// noise. ⚠ It is what stops a capped list from being a SILENT truncation.
    static func subtitleShownLine(shown: Int, total: Int) -> String? {
        guard total > shown, shown >= 0 else { return nil }
        return "Showing \(shown) of \(total) results"
    }

    /// The height a two-line result row draws at. ⚠ Both line boxes are charged
    /// `Metric.lineHeightRatio`, the same ratio every page budget uses.
    static func subtitleRowHeight() -> CGFloat {
        TVTokens.Player.listItemSize * TVTokens.Metric.lineHeightRatio
            + TVTokens.Player.subtitleRowGap
            + TVTokens.Player.subtitleDetailSize * TVTokens.Metric.lineHeightRatio
            + 2 * TVTokens.Player.listItemPaddingV
    }

    /// The list region's height — **capped**, which is the whole point: the list is what varies, and it is the
    /// only term that may not push the panel off the screen.
    /// ⚠ It serves BOTH list panes (Subtitles and Audio Track): its rows are measured at the TWO-LINE worst
    /// case, so an audio pane's shorter rows simply leave air rather than overrunning the bound.
    static func paneListHeight(rowCount: Int) -> CGFloat {
        min(paneListUnboundedHeight(rowCount: rowCount),
            TVTokens.Player.subtitleListMaxHeight)
    }

    /// ⚠ The SAME list with nothing holding it back — the term that made his panel 1875.2 pt. ⚠ It is a
    /// separate function rather than a flag, so the drawing path has no way to reach it by accident.
    static func paneListUnboundedHeight(rowCount: Int) -> CGFloat {
        guard rowCount > 0 else { return 0 }
        return CGFloat(rowCount) * subtitleRowHeight()
            + CGFloat(rowCount - 1) * TVTokens.Player.listGap
    }

    /// How many result rows the bounded region can show — ⚠ derived from the tokens, so the ceiling and the
    /// drawn width cannot drift apart.
    static func paneRowsThatFit() -> Int {
        let step = subtitleRowHeight() + TVTokens.Player.listGap
        guard step > 0 else { return 1 }
        let usable = TVTokens.Player.subtitleListMaxHeight + TVTokens.Player.listGap
        return max(1, Int((usable / step).rounded(.down)))
    }

    /// **The drawer's whole height, with the list BOUNDED** — which is how the panel is drawn now.
    ///
    /// ⚠ `paneListHeight` caps the list, so this function can no longer exceed the screen at any row count.
    /// ⚠⚠ **That is exactly why the defect needs its own function below** — a budget that can never fail cannot
    /// report the failure it was written to prevent.
    static func settingsPanelHeight(listRows: Int) -> CGFloat {
        fixedHeight() + paneListHeight(rowCount: listRows)
    }

    /// ⚠⚠ **THE HEIGHT THE PANEL WAS — WITH THE LIST UNBOUNDED, WHICH IS THE DEFECT ITSELF.**
    ///
    /// **His round: *"i click on subtitles all the other control vanishes.. i only see"* nineteen rows.** With
    /// nothing bounding the list, the panel came to **1875.2 pt on a 1080 pt screen** — and because a child
    /// taller than its container overflows in BOTH directions, **~398 pt of the panel was drawn ABOVE the top
    /// edge**: the "PLAYER SETTINGS" header, the pane's title, the first rows, and **all five rail items**. He
    /// was stranded in Subtitles with no way back, and that is what the screenshot shows.
    ///
    /// ⚠ Eight result rows fitted (**1033.4 pt**); **nine did not (1109.9)**. The threshold is 8, and the pane
    /// drew 19 — which is why the same drawer looked correct in every other pane and in this one did not.
    static func settingsPanelUnboundedHeight(listRows: Int) -> CGFloat {
        fixedHeight() + paneListUnboundedHeight(rowCount: listRows)
    }

    static func settingsPanelFits(listRows: Int) -> Bool {
        settingsPanelHeight(listRows: listRows) <= TVTokens.Metric.screenHeight
    }

    /// ⚠ The converse: what the panel would have been without the bound. **The falsifier this whole fix is
    /// measured against** — `settingsPanelFitsUnbounded(listRows: 19)` must be FALSE, and today it is.
    static func settingsPanelFitsUnbounded(listRows: Int) -> Bool {
        settingsPanelUnboundedHeight(listRows: listRows) <= TVTokens.Metric.screenHeight
    }

    /// ⚠⚠ **EVERY TERM OF THE PANEL THAT IS NOT THE LIST, IN ONE PLACE.** Both heights above are this plus their
    /// own list term, so the two cannot drift apart — and W3's lesson (`PROGRESS.md`, round 10: *"a budget that
    /// lives in a pure file and a view that decides what the budget is about are two halves no gate joins"*) is
    /// why every term here is a TOKEN the view also draws with, not a number copied into a test.
    static func fixedHeight() -> CGFloat {
        let padding = TVTokens.Player.settingsTopPad + TVTokens.Player.settingsBottomPad
        let header = TVTokens.Player.settingsHeaderTop
            + TVTokens.Player.settingsHeaderSize * TVTokens.Metric.lineHeightRatio
        let paneTitle = TVTokens.Player.paneTitleSize * TVTokens.Metric.lineHeightRatio
            + TVTokens.Player.contentGap
        // ⚠ The footer at its WORST — three lines: the badge row, a save line and a subtitle warning. Budgeting
        // its best case would under-count by two lines and let the panel overflow in exactly the state he hit.
        let footer = TVTokens.Player.footerTopPad
            + 3 * TVTokens.Player.footerSize * TVTokens.Metric.lineHeightRatio
            + TVTokens.Player.contentGap
        return padding + header + paneTitle + footer
    }

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

    /// ⚠⚠ **WHAT MAY PIN THE CHROME — AND "SOMETHING IS FOCUSED" IS DELIBERATELY NOT ONE OF THEM.**
    ///
    /// His file's rule, verbatim (`…player.html:706`): *`if(isPlaying && !settingsOpen && !infoOpen)`* — a
    /// draw, an info panel, or nothing. ⚠⚠ **THE APP GOT THIS WRONG TWICE OVER, AND HIS ROUND FOUND IT:**
    ///
    ///  1. the web rule watches the POINTER (`hoverChrome`), and the tvOS "equivalent" this screen took was
    ///     *"somebody is standing on a control"* — the `isAnythingFocused` its `PlayerView` passed as
    ///     `panelOpen`. ⚠⚠ **THAT IS ALWAYS TRUE ON A TELEVISION.** The focus engine guarantees a ring is on
    ///     something from the moment the screen opens (`.defaultFocus($focus, .play)`), so a rule that reads
    ///     it can never let the chrome hide, on any screen, for any viewer, ever;
    ///  2. and it never mattered, because `isPlaying` was `false` while the film played (see the store), so
    ///     `!playing` returned first.
    ///
    /// ⇒ **His words: *"the controls never auto hide and always on the screen"*.** What pins the chrome is a
    /// MODE — a drawer, or the Up Next card — because each is a question with NO TIMEOUT. Recency of INPUT is
    /// the idle clock's job (`PlayerView.lastInteraction`), and his file resets that on **every keydown**
    /// (`…player.html:721`). ⚠ Two jobs, two mechanisms; conflating them is what this function exists to stop.
    static func chromePinned(panelOpen: Bool, upNextCardVisible: Bool) -> Bool {
        panelOpen || upNextCardVisible
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
