import Foundation
import Combine
import RKMServerKit

/// **The player's state — everything the screen shows, and every decision the screen does not make.**
///
/// ⚠⚠ **NO AVFOUNDATION IN THIS FILE, DELIBERATELY.** `AVPlayer` is the one thing this sandbox cannot
/// compile, so the store holds *facts and decisions* — which mode, which URL, which track, which cues,
/// what to report — while `Player/PlayerView.swift` does the three things that genuinely need
/// `AVPlayer` (create the item, seek it, play it) and reports time back here. That split is what keeps
/// the unverifiable surface as small as the plan promised.
///
/// ⚠⚠ **THE WRITES ARE RE-READ, NOT TRUSTED.** `POST /api/jellyfin/progress` answers `204`, and this repo
/// has twice been burnt by a `204` that stored nothing (Jellyfin's `/Sessions/Playing*`; `/Users/Password`
/// with `ResetPassword: true`, which answered `204`, set nothing and CLEARED a password). So `saveState`
/// exists: after a write the store asks the server what it now holds and says so on screen. ⚠ A failed
/// self-check NEVER blocks playback — it is a sentence, not a gate.
final class PlaybackStore: ObservableObject {

    // MARK: - Types

    enum Load: Equatable {
        case loading
        case ready
        /// ⚠ A sentence a viewer can read, never "error 404".
        case failed(String)
    }

    /// What the position write was last seen to do. ⚠ **Tri-state on purpose** (`ARCHITECTURE.md` §11 /
    /// the advisory-check rule): "we could not check" is NOT "it failed", and a screen that conflated
    /// them would tell him his position was lost when it had been saved.
    enum SaveState: Equatable {
        case idle
        case saving
        case verified(Double)
        case refused(String)
        case unavailable(String)
    }

    /// Which overlay is open. ⚠ One value, not three booleans — three flags is how two panels end up
    /// open over a film.
    enum Panel: Equatable {
        case none
        case info
        case settings
    }

    // MARK: - Identity (fixed for the life of the store)

    let itemID: String
    /// The detail snapshot the player was opened with — the top bar's title/year, the synopsis, and the
    /// RESUME POSITION all come from it, so the player makes no second fetch for metadata the screen
    /// behind it already has.
    let detail: ItemDetail?

    private let client: APIClient
    private var correlation = CorrelationID.next()

    // MARK: - Published state

    @Published private(set) var load: Load = .loading
    @Published private(set) var info: PlaybackInfo?
    @Published private(set) var mode: PlaybackRules.StreamMode = .direct
    /// ⚠ The URL `AVPlayer` is given. A CHANGE here means "rebuild the item and seek back" — that is how
    /// a quality, track or mode change takes effect, and it is the only signal the view needs.
    @Published private(set) var url: URL?

    @Published private(set) var duration: Double = 0
    @Published private(set) var position: Double = 0
    @Published private(set) var resumePosition: Double = 0
    @Published var isPlaying: Bool = false
    @Published var isScrubbing: Bool = false
    @Published private(set) var isSwitching: Bool = false

    @Published private(set) var rate: Double = PlaybackRules.defaultRate
    @Published private(set) var picture: PlaybackRules.PictureMode = .fit
    @Published private(set) var quality: String = PlaybackRules.defaultQualityLabel
    @Published private(set) var audioIndex: Int?
    @Published private(set) var subtitleIndex: Int?

    @Published private(set) var subtitleRows: [SubtitleRow] = []
    @Published private(set) var subtitleSearchEnabled: Bool = false
    @Published private(set) var subtitleWarning: String = ""
    @Published private(set) var remainingDownloads: Int?
    @Published private(set) var isSearchingSubtitles: Bool = false
    private var cues: [PlaybackRules.Cue] = []
    @Published private(set) var cueText: String?

    @Published var panel: Panel = .none
    @Published var category: PlaybackRules.SettingsCategory = .picture
    @Published private(set) var toast: String?
    @Published private(set) var saveState: SaveState = .idle

    /// ⚠ The player's own failure sentence for a stream that will not start — the visible failure mode
    /// the plan asked for (`docs/TVOS_PLAYER_PLAN.md` §3): a black screen with nothing on it is the
    /// outcome this app refuses to ship.
    @Published private(set) var playbackFailure: String?

    private var lastReportAt: Date?
    private var toastTask: Task<Void, Never>?

    // MARK: - Init

    init(client: APIClient, itemID: String, detail: ItemDetail?) {
        self.client = client
        self.itemID = itemID
        self.detail = detail
        let resume = detail.map { PlaybackRules.seconds(fromTicks: $0.play.resumeTicks) } ?? 0
        self.resumePosition = max(0, resume)
        self.position = self.resumePosition
        self.duration = detail.map { Double($0.runtime ?? 0) } ?? 0
    }

    // MARK: - Derived labels (the top bar and the drawer)

    var title: String { detail?.name ?? "This title" }

    /// ⚠ The badge is derived from the mode the app actually chose — never a fixed string. A badge that
    /// said "Remux · HLS" while the stream was a direct play is exactly the kind of lie the app's rule
    /// against offering what the server will refuse exists to prevent.
    var modeBadge: String { PlaybackRules.badgeText(mode) }

    var metaLine: String {
        let active = (audioIndex.flatMap { index in
            info?.audio.first { $0.index == index }
        }) ?? info?.audio.first
        return PlaybackRules.languageLine(
            activeAudioLanguage: active?.language,
            subtitleLanguages: (info?.subtitles ?? []).map(\.language))
    }

    var trackSummary: String {
        PlaybackRules.trackSummary(audioCount: info?.audio.count ?? 0,
                                   subtitleCount: info?.subtitles.count ?? 0)
    }

    var progressFraction: Double {
        PlaybackRules.progressFraction(position: position, total: duration)
    }

    var elapsedLabel: String { PlaybackRules.fmtTime(position) }
    var durationLabel: String { PlaybackRules.fmtTime(duration) }

    var qualityCaption: String { PlaybackRules.qualityCaption(for: quality) }
    var pictureCaption: String { picture.caption }

    /// The subtitle row the picker should show as selected, or `nil` for "Off".
    var subtitleSelectionLabel: String {
        guard let subtitleIndex else { return "Off" }
        return info?.subtitles.first { $0.index == subtitleIndex }?.name ?? "Off"
    }

    /// ⚠ True when the item's facts could not be read at all — the screen's ONE question about the load state
    /// (a view comparing against `.failed("")` would be inventing a sentence to test against).
    var hasFailed: Bool {
        if case .failed = load { return true }
        return false
    }

    /// The way out's own words. ⚠ It names the destination, because a bare chevron on a screen that fills a
    /// television does not say where it goes.
    var backLabel: String { "Back to \(detail?.name ?? "the title")" }

    /// The top bar's meta row, as PARTS so each one can be separated by a dot.
    ///
    /// ⚠⚠ **IT IS `PlaybackRules.languageLine` SPLIT, not a second implementation of it.** The rule — the
    /// active audio language, then the subtitle languages or "No subtitles" — lives in one place; this only
    /// says how the screen separates the pieces. (Two copies of one rule is this repo's most-repeated defect,
    /// and a meta row is exactly the kind of small thing that grows one.)
    var metaParts: [String] {
        PlaybackRules.languageLine(activeAudioLanguage: activeAudioLanguage,
                                  subtitleLanguages: subtitleLanguages)
            .components(separatedBy: " · ")
    }

    /// The active audio track's language — the one the route decision is built on, so the top bar and the
    /// mode badge can never disagree about which track is playing.
    var activeAudioLanguage: String? {
        let active = (audioIndex.flatMap { index in info?.audio.first { $0.index == index } })
            ?? info?.audio.first
        return active?.language
    }

    var subtitleLanguages: [String] { (info?.subtitles ?? []).map(\.language) }

    /// The clock in his prototype's top-right corner. ⚠ A tvOS app CAN show the time, and a viewer who has
    /// lost track of the evening appreciates it — but it is the SYSTEM's format, not a pinned one.
    var clockText: String {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        formatter.dateStyle = .none
        return formatter.string(from: Date())
    }

    var overview: String? {
        guard let text = detail?.overview, !text.isEmpty else { return nil }
        return text
    }

    /// The info panel's tags — year, genres, the run time, and an episode's own `S1E4`.
    ///
    /// ⚠ Every one is a real field: his file hardcodes `1975 · Action · Drama · 3h 24m · Part 1 of 2`, and a
    /// tag the server did not send is simply absent rather than blank.
    var infoTags: [String] {
        var tags: [String] = []
        if let year = detail?.year { tags.append(String(year)) }
        tags += (detail?.genres ?? []).prefix(2)
        if let runtime = detail?.runtime, runtime > 0 { tags.append(HomeRules.runtimeText(runtime)) }
        if let season = detail?.season, let episode = detail?.episode {
            tags.append("S\(season)E\(episode)")
        }
        return tags
    }

    /// ⚠⚠ **THE ONE SENTENCE THAT MAKES A WRITE VISIBLE — and it is deliberately TRI-STATE.** A position write
    /// answers `204`, and this repo has twice been burnt by a `204` that stored nothing. So the store re-reads
    /// what the server holds and says which of the three things happened: saved, refused, or *could not check*.
    /// ⚠ Folding "could not check" into "failed" would tell a viewer their place was lost when it was not.
    var saveSentence: String? {
        switch saveState {
        case .idle:
            return nil
        case .saving:
            return "Saving position…"
        case .verified(let seconds):
            return "Position saved · \(PlaybackRules.fmtTime(seconds))"
        case .refused(let sentence):
            return "Not saved — \(sentence)"
        case .unavailable(let sentence):
            return "Could not check the saved position — \(sentence)"
        }
    }

    /// The audio tracks the drawer lists — the SERVER's, never a fixed vocabulary (his prototype's four rows
    /// are a mock's).
    var audioRows: [PlaybackTrack] { info?.audio ?? [] }

    /// ⚠ The api's own default: `AudioStreamIndex` is forwarded only when it is `> 0`, so "no choice" and
    /// "index 0" are the same thing — which is why `nil` means the FIRST track on both sides.
    func isSelectedAudio(_ track: PlaybackTrack) -> Bool {
        let chosen = audioIndex ?? info?.audio.first?.index
        return track.index == chosen
    }

    /// The item's own subtitle tracks — already filtered by the api to TEXT streams, so nothing here can offer
    /// a subtitle that cannot render.
    var localSubtitleRows: [PlaybackTrack] { info?.subtitles ?? [] }

    /// OpenSubtitles results, when the server's search half is enabled.
    var remoteSubtitleRows: [SubtitleRow] { subtitleRows.filter { !$0.local } }

    // MARK: - Load

    /// The one call the player cannot start without: it decides the mode, and therefore the URL.
    func load() async {
        load = .loading
        playbackFailure = nil
        correlation = CorrelationID.next()
        do {
            let info = try await client.playbackInfo(itemID: itemID, correlation: correlation)
            self.info = info
            // ⚠ A stored choice is resolved to a CURRENT index by the SERVER, and the resolve is by
            // IDENTITY then LANGUAGE — see `PlaybackRules.resolveActiveSubtitle`. Assigned here so the
            // first frame already has the right subtitle rather than the second one.
            self.subtitleIndex = PlaybackRules.resolveActiveSubtitle(
                tracks: info.subtitles,
                preferredDisplayTitle: info.preferredSubtitle?.displayTitle,
                preferredLanguage: info.preferredSubtitle?.language)
            self.audioIndex = info.audio.first.map { $0.index == 0 ? nil : $0.index } ?? nil
            recomputeRoute(reason: "loaded")
            load = .ready
            RKMLog.info("player: \(info.audio.count) audio · \(info.subtitles.count) sub tracks; "
                        + "mode \(mode.rawValue) (container \(info.container ?? "?"), "
                        + "video \(info.video?.codec ?? "?"))",
                        category: .app, correlation: correlation)
            await loadSubtitleTextIfChosen()
            await loadSubtitleChoices()
        } catch let error as APIError {
            load = .failed(error.errorDescription ?? "This title cannot be played right now.")
            RKMLog.error("player: playback-info failed — \(error.errorDescription ?? "")",
                         category: .app, correlation: correlation)
        } catch {
            load = .failed("This title cannot be played right now.")
        }
    }

    /// The mode + URL, from the facts. ⚠ ONE function, called by every control that can change them
    /// (quality, audio track, mode escalation), so a control cannot move the mode without moving the URL.
    private func recomputeRoute(reason: String) {
        let video = info?.video
        let chosen = PlaybackRules.pickStreamMode(
            quality: quality,
            container: info?.container,
            videoCodec: video?.codec,
            videoProfile: video?.profile,
            videoBitDepth: video?.bitDepth,
            activeAudioCodec: PlaybackRules.audioCodecFor(index: audioIndex, tracks: info?.audio ?? []),
            forceNonDirect: PlaybackRules.choosingATrackForcesNonDirect(audioIndex: audioIndex),
            codecs: .tvOS)
        mode = chosen
        url = PlaybackURLs.playbackURL(base: client.address.url,
                                      itemID: itemID,
                                      mode: chosen,
                                      audioIndex: audioIndex,
                                      maxBitrate: PlaybackRules.maxBitrate(for: quality))
        RKMLog.info("player: route \(reason) → \(chosen.rawValue) (\(PlaybackRules.streamModeLabel(chosen)))",
                    category: .app, correlation: correlation)
    }

    // MARK: - Transport (the view drives the player; the store holds the decisions)

    /// Called by the view's periodic observer. ⚠ It does TWO things and they are different: it keeps the
    /// screen's clock honest, and it reports progress on the web's own 5-second cadence — never once per
    /// frame, which would be thousands of Jellyfin writes per film.
    func tick(position newPosition: Double, duration newDuration: Double, playing: Bool) {
        if newDuration.isFinite && newDuration > 0 { duration = newDuration }
        if !isScrubbing { position = max(0, newPosition) }
        cueText = PlaybackRules.activeCue(cues, position: position)
        if playing {
            let now = Date()
            let elapsed = now.timeIntervalSince(lastReportAt ?? .distantPast)
            if PlaybackRules.shouldReport(elapsedSinceLastReport: elapsed) {
                lastReportAt = now
                Task { await report(.timeupdate) }
            }
        }
    }

    /// ⚠ **The BUFFERING signal, and it is real rather than decorative**: `PlaybackRules.shouldHideChrome`
    /// keeps the controls on screen while a stream is switching, and the view reports the player's own
    /// `timeControlStatus`. Without a setter this was a flag nothing ever set — a rule reading a constant.
    func setSwitching(_ value: Bool) {
        if isSwitching != value { isSwitching = value }
    }

    func play() {
        isPlaying = true
        Task { await report(.start) }
    }

    func pause() { isPlaying = false }

    func togglePlay() { isPlaying ? pause() : play() }

    /// ⚠ One entry point for BOTH skip verbs and the scrubber, so `clampSeek` cannot be forgotten by one
    /// of them — `skipTarget` is the rule, and a delta of `±10` is the two buttons while `±30` is the jog.
    func seek(to seconds: Double) {
        position = PlaybackRules.clampSeek(seconds, total: duration)
        cueText = PlaybackRules.activeCue(cues, position: position)
    }

    func skip(by delta: Double) { seek(to: PlaybackRules.skipTarget(from: position, by: delta, total: duration)) }

    func setRate(_ newRate: Double) {
        rate = newRate
        showToast("Speed \(PlaybackRules.rateLabel(newRate))")
    }

    func setPicture(_ newPicture: PlaybackRules.PictureMode) {
        picture = newPicture
        showToast(newPicture == .fill ? "Fill" : "Fit")
    }

    func setQuality(_ label: String) {
        quality = label
        recomputeRoute(reason: "quality \(label)")
        showToast("Quality \(label)")
    }

    /// ⚠⚠ **CHANGING THE AUDIO TRACK MOVES THE MODE, NOT JUST A PARAMETER.** Jellyfin ignores
    /// `AudioStreamIndex` under `Static=true`, so a chosen track forces a remux — and that is why this
    /// goes through `recomputeRoute` rather than touching `url` directly.
    func setAudioIndex(_ index: Int?) {
        audioIndex = index
        recomputeRoute(reason: "audio track")
        let name = info?.audio.first { $0.index == index }?.name ?? "Default"
        showToast("Audio \(name)")
    }

    /// The mode ladder's next step, for a stream that fails to play. ⚠ The web's own order
    /// (`PlaybackRules.hlsLadder`) — audio-aware, so an EAC3 title that came out of a copy-copy remux
    /// goes to `transcode_audio` rather than retrying the same thing.
    func escalateMode() {
        guard let next = PlaybackRules.nextHLSMode(after: mode) else {
            playbackFailure = "This title could not be played. The server refused every mode this app can ask for."
            return
        }
        quality = PlaybackRules.defaultQualityLabel  // ⚠ a quality cap already forces `transcode`.
        mode = next
        url = PlaybackURLs.playbackURL(base: client.address.url, itemID: itemID, mode: next,
                                      audioIndex: audioIndex,
                                      maxBitrate: PlaybackRules.maxBitrate(for: quality))
        RKMLog.error("player: streaming failed — escalating to \(next.rawValue)",
                     category: .app, correlation: correlation)
        showToast("Trying \(PlaybackRules.streamModeLabel(next))…")
    }

    func reportPlaybackFailure(_ sentence: String) {
        playbackFailure = sentence
    }

    // MARK: - Progress writes (and the re-read that makes them evidence)

    /// Send one progress report, then — for the events that CLAIM something — ask the server what it now
    /// holds. ⚠ `timeupdate` is a heartbeat and is not verified (that would double the request count for
    /// no information); `stopped` is the one that decides resume-vs-watched, so it IS verified.
    func report(_ event: PlaybackRules.ProgressEvent) async {
        let body = JellyfinProgressRequest(
            itemID: itemID,
            positionTicks: PlaybackRules.ticks(fromSeconds: position),
            isPaused: !isPlaying,
            event: event.rawValue,
            playMethod: PlaybackRules.playMethod(mode),
            runtimeTicks: PlaybackRules.ticks(fromSeconds: duration))
        do {
            try await client.reportProgress(body, correlation: correlation)
            guard event == .stopped else { return }
            await verifySave()
        } catch let error as APIError {
            if event == .stopped {
                saveState = .refused(error.errorDescription ?? "The position could not be saved.")
            }
            RKMLog.error("player: progress (\(event.rawValue)) failed — \(error.errorDescription ?? "")",
                         category: .app, correlation: correlation)
        } catch {
            if event == .stopped { saveState = .refused("The position could not be saved.") }
        }
    }

    /// ⚠⚠ **THE POINT OF THIS FUNCTION IS THAT A `204` IS NOT SUCCESS.** It asks `GET /api/jellyfin/detail`
    /// what the item's position/played state is NOW and reports one of three answers — verified, refused,
    /// or *we could not check* — because telling a viewer their position was lost when the check merely
    /// failed is the false-negative this repo has already been burnt by twice.
    private func verifySave() async {
        saveState = .saving
        do {
            let fresh = try await client.itemDetail(itemID: itemID, correlation: correlation)
            let stored = PlaybackRules.seconds(fromTicks: fresh.play.resumeTicks)
            let played = fresh.play.played
            if played && PlaybackRules.finished(positionTicks: PlaybackRules.ticks(fromSeconds: position),
                                                runtimeTicks: PlaybackRules.ticks(fromSeconds: duration)) {
                saveState = .verified(stored)
                showToast("Marked as watched")
            } else if abs(stored - position) <= 2 {
                saveState = .verified(stored)
                showToast("Saved \(PlaybackRules.fmtTime(stored))")
            } else {
                saveState = .refused("The server is holding \(PlaybackRules.fmtTime(stored)) rather than "
                                     + "\(PlaybackRules.fmtTime(position)).")
                showToast("Position did not save")
            }
        } catch let error as APIError {
            saveState = .unavailable(error.errorDescription ?? "Could not check the saved position.")
        } catch {
            saveState = .unavailable("Could not check the saved position.")
        }
    }

    /// ⚠ **Called when the screen is left.** One report, one check — and it is fired by the view's
    /// `onDisappear` as well as by `Back`, because a viewer who presses the remote's Home button instead
    /// of Back must not lose their place in a three-hour film.
    func finish() async {
        isPlaying = false
        await report(.stopped)
    }

    func retrySave() async {
        await report(.stopped)
    }

    // MARK: - Subtitles

    /// The picker's rows: the item's own tracks, then OpenSubtitles when the server says it can.
    func loadSubtitleChoices() async {
        do {
            let search = try await client.searchSubtitles(itemID: itemID, correlation: correlation)
            subtitleRows = search.results
            subtitleSearchEnabled = search.enabled
            remainingDownloads = search.remainingDownloads
            subtitleWarning = search.warning
        } catch let error as APIError {
            // ⚠ A failed SEARCH must not disturb playback: the local tracks are already on screen from
            // `playback-info`, and the picker degrades to them. (The api's own rule: only the search half
            // degrades.)
            subtitleWarning = error.errorDescription ?? ""
            RKMLog.info("player: subtitle search unavailable — \(error.errorDescription ?? "")",
                           category: .app, correlation: correlation)
        } catch {
            subtitleWarning = ""
        }
    }

    func searchSubtitles(language: String = "") async {
        isSearchingSubtitles = true
        defer { isSearchingSubtitles = false }
        await loadSubtitleChoices()
    }

    /// Choose a LOCAL track (already attached to the item).
    func chooseLocalSubtitle(index: Int?) async {
        subtitleIndex = index
        await loadSubtitleTextIfChosen()
        showToast(index == nil ? "Subtitles off" : "Subtitle \(subtitleSelectionLabel)")
    }

    /// Choose a REMOTE result: the server downloads, attaches and remembers it, then reports the refreshed
    /// track list — which is the only honest source for the index afterwards.
    func chooseRemoteSubtitle(_ row: SubtitleRow) async {
        guard let fileID = row.fileID else { return }
        isSearchingSubtitles = true
        defer { isSearchingSubtitles = false }
        do {
            let result = try await client.selectSubtitle(
                SubtitleSelectRequest(itemID: itemID, fileID: fileID, language: row.language,
                                      displayTitle: row.displayTitle, provider: row.provider),
                correlation: correlation)
            remainingDownloads = result.remainingDownloads
            // ⚠ The store re-reads rather than assuming the attachment worked: the refreshed track list
            // comes from the server, and the index is looked up in THAT.
            await load()
            if let preferred = result.preferredSubtitle {
                subtitleIndex = PlaybackRules.resolveActiveSubtitle(
                    tracks: result.subtitles,
                    preferredDisplayTitle: preferred.displayTitle,
                    preferredLanguage: preferred.language) ?? preferred.index
            }
            await loadSubtitleTextIfChosen()
            showToast(result.reused ? "Subtitle already downloaded" : "Subtitle downloaded")
        } catch let error as APIError {
            showToast(error.errorDescription ?? "Could not get that subtitle")
        } catch {
            showToast("Could not get that subtitle")
        }
    }

    /// Turn subtitles off — as a WRITE, because the choice is remembered server-side and a local "off"
    /// would be undone by the next load.
    func disableSubtitles() async {
        do {
            try await client.disableSubtitle(itemID: itemID, correlation: correlation)
            subtitleIndex = nil
            cues = []
            cueText = nil
            // ⚠ A `2xx` is not evidence; the check is what the server now reports as preferred.
            let fresh = try await client.playbackInfo(itemID: itemID, correlation: correlation)
            info = fresh
            if fresh.preferredSubtitle != nil {
                showToast("Subtitles are still on the server")
            } else {
                showToast("Subtitles off")
            }
        } catch let error as APIError {
            showToast(error.errorDescription ?? "Could not turn subtitles off")
        } catch {
            showToast("Could not turn subtitles off")
        }
    }

    /// Fetch the chosen track's WebVTT and parse it. ⚠ Its own path: the subtitle stream is a separate
    /// request the player makes, and a failure here simply means no captions — never a stopped film.
    private func loadSubtitleTextIfChosen() async {
        guard let index = subtitleIndex, let source = info?.mediaSourceID else {
            cues = []
            cueText = nil
            return
        }
        guard let url = PlaybackURLs.absolute(
            base: client.address.url,
            path: PlaybackURLs.subtitle(),
            query: PlaybackURLs.subtitleQuery(itemID: itemID, mediaSourceID: source, index: index)) else {
            cues = []
            return
        }
        do {
            let text = try await client.subtitleText(url: url, correlation: correlation)
            cues = PlaybackRules.parseVTT(text)
            cueText = PlaybackRules.activeCue(cues, position: position)
            RKMLog.info("player: \(cues.count) subtitle cue(s) loaded", category: .app,
                        correlation: correlation)
        } catch {
            cues = []
            cueText = nil
            RKMLog.info("player: subtitle text unavailable — \(error)", category: .app,
                           correlation: correlation)
        }
    }

    // MARK: - Panels and toasts

    func toggleInfo() { panel = panel == .info ? .none : .info }

    func openSettings() {
        panel = .settings
        category = .picture
    }

    func closePanel() { panel = .none }

    func selectCategory(_ next: PlaybackRules.SettingsCategory) { category = next }

    /// ⚠ The toast is his prototype's own feedback element, and it carries the SERVER's sentence when
    /// there is one — a toast that says "Done" over a refused write is worse than no toast.
    func showToast(_ message: String) {
        toast = message
        toastTask?.cancel()
        toastTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 2_200_000_000)
            guard !Task.isCancelled else { return }
            self?.toast = nil
        }
    }
}
