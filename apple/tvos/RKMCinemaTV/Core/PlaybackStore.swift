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
    ///
    /// ⚠ **IT IS OPTIONAL, AND MUTABLE, BECAUSE THE PLAYER IS REACHED FROM TWO KINDS OF SCREEN.** The detail
    /// screen hands one over; the Home's hero has only a `MediaItem` (a row), so it passes `facts` and `load()`
    /// refines them from `GET /jellyfin/detail` — which is where the exact `resumeTicks` live.
    private(set) var detail: ItemDetail?

    /// What the player knows about the title when nobody handed it an `ItemDetail`.
    ///
    /// ⚠⚠ **WHY THIS TYPE EXISTS: the Home's hero has a Play button** (`HomeRules.heroPrimaryLabel`'s verb) and
    /// a row, not a detail payload. Pressing it is his round-3 report — *"when i tried to play from the title
    /// from continue watching section in home screen, i cant play it"*. ⚠ Both numbers are in SECONDS on this
    /// wire: the api converts `PlaybackPositionTicks` and `RunTimeTicks` with `_ticks_to_sec` before a row is
    /// ever sent (`backend/services/library/jellyfin.py:469`), which is why this is not a ticks conversion.
    struct PlaybackFacts: Equatable {
        let title: String
        let runtimeSeconds: Double
        let resumeSeconds: Double

        static let unknown = PlaybackFacts(title: "", runtimeSeconds: 0, resumeSeconds: 0)

        /// ⚠ From a Home/Browse row — the title the ROW shows (an episode's own title, not its series', which
        /// is the hero's choice and not the player's).
        static func from(_ item: MediaItem) -> PlaybackFacts {
            PlaybackFacts(title: item.title,
                          runtimeSeconds: Double(item.runtime ?? 0),
                          resumeSeconds: Double(item.playbackPosition ?? 0))
        }

        /// ⚠⚠ **FROM AN EPISODE, WHICH IS WHAT UP NEXT HANDS OVER** — and it is a second initialiser rather
        /// than a generalised one because the two rows are different types with different key spellings
        /// (`MediaItem.playbackPosition` comes off a library row; `EpisodeItem.playbackPosition` off the
        /// episode list). A protocol to unify them would be one more thing to keep true for four fields.
        static func from(_ episode: EpisodeItem) -> PlaybackFacts {
            PlaybackFacts(title: episode.name,
                          runtimeSeconds: Double(episode.runtime),
                          resumeSeconds: Double(episode.playbackPosition))
        }
    }

    /// The row's facts, kept so a failed detail fetch still leaves a titled, resumable player.
    let facts: PlaybackFacts

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

    /// ⚠⚠ **HOW FAR UP THE MODE LADDER THIS SESSION HAS CLIMBED** (`PlaybackRules.hlsLadder`). 0 means no
    /// escalation has happened. It exists so the notice can say *"Tried 3 of 3"* rather than the same
    /// sentence twice — and so a round can read the escalation off the HUD without guessing which mode failed.
    @Published private(set) var escalationAttempt: Int = 0

    /// ⚠⚠ **A TOKEN THE VIEW WATCHES TO RE-REQUEST THE SAME URL.** `url` is `Equatable` and re-assigning an
    /// equal value fires no `onChange`, so without this a *Try again* on a transient network failure would
    /// return a promise of an action and do exactly nothing — the worst kind of control on a TV.
    @Published private(set) var reloadToken: Int = 0

    // MARK: - Up Next (the next episode)

    /// The series' own episode list, fetched ONCE, and only for an episode. ⚠ Soft: a failure here means no
    /// Up Next card and a film that plays normally.
    @Published private(set) var episodes: [EpisodeItem] = []
    /// The episode after this one, from the server's own order (`PlaybackRules.nextEpisode`). `nil` for a
    /// film, for the last episode of a series, and for an item the list does not contain.
    @Published private(set) var nextEpisode: EpisodeItem?
    /// ⚠ The countdown, in whole seconds, or `nil` while there is no card. **Published**, not computed: a
    /// computed property reading `Date()` changes without telling SwiftUI, so a card built on one would tick
    /// only when something else happened to redraw the screen.
    @Published private(set) var upNextSecondsLeft: Int?
    /// ⚠ The episode to hand to `AppModel`, set once the countdown expires or *Play now* is pressed. ⚠⚠ **The
    /// store CANNOT open the player itself** — it has no `AppModel` and must not grow one — so it publishes
    /// the intent and the VIEW performs it. That is also what keeps the position write and the hand-off in a
    /// defined order.
    @Published private(set) var upNextHandoff: EpisodeItem?

    private var upNextDeadline: Date?
    /// ⚠ A viewer who pressed *Cancel* is not asked again — the trigger is the POSITION, which stays past
    /// `finishFraction` for the rest of the film, so without this the card would reappear on the next tick.
    private var upNextDeclined = false
    /// ⚠⚠ **AND THE SAME IS TRUE OF ONE THAT HAS ALREADY BEEN HANDED OVER.** `clearUpNextHandoff()` is called
    /// by the view when it has performed the hand-off, and clearing only the published value would leave the
    /// deadline nil and `hasFinished` true — so the very next tick would start the countdown again and the
    /// tick after that would hand the same episode over a second time. ⚠ In practice the old screen is
    /// re-identified away first (`.id(playback.itemID)` in `AppRootView`), which is exactly why this is a
    /// guard and not a load-bearing line: a state machine whose correctness depends on the view being torn
    /// down in time is a state machine that is wrong somewhere else too.
    private var upNextHandedOff = false

    private var lastReportAt: Date?
    private var toastTask: Task<Void, Never>?
    /// ⚠ **D6 — the stop write happens ONCE.** Two callers fire it (`Back`, and the screen's `onDisappear`) and
    /// the platform does not promise which is first, so the guard belongs here rather than at either call site.
    private var didFinish = false

    // MARK: - Init

    init(client: APIClient, itemID: String, detail: ItemDetail?,
         facts: PlaybackFacts = .unknown) {
        self.client = client
        self.itemID = itemID
        self.detail = detail
        self.facts = facts
        let resume = detail.map { PlaybackRules.seconds(fromTicks: $0.play.resumeTicks) }
            ?? max(0, facts.resumeSeconds)
        self.resumePosition = max(0, resume)
        self.position = self.resumePosition
        self.duration = detail.map { Double($0.runtime ?? 0) } ?? max(0, facts.runtimeSeconds)
    }

    // MARK: - Derived labels (the top bar and the drawer)

    /// ⚠ The `ItemDetail`'s name when there is one, else the ROW's title, else a neutral sentence — never an
    /// empty bar over the film.
    var title: String {
        if let name = detail?.name, !name.isEmpty { return name }
        return facts.title.isEmpty ? "This title" : facts.title
    }

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
    var hasFailed: Bool { failureSentence != nil }

    /// **The one sentence that says why nothing is playing**, from either source: a stream that died
    /// mid-film (`playbackFailure`) or facts that could not be read at all (`load == .failed`).
    ///
    /// ⚠⚠ **IT EXISTS SO THE VIEW DOES NOT HAVE TO PATTERN-MATCH.** The first draft asked the screen to write
    /// `else if case .failed(let sentence) = store.load` inside a `ViewBuilder` — a construct with its own
    /// rules about what an `if` may look like in a result builder, in a file no compiler here can check. The
    /// store owns the enum, so the store reduces it to a `String?` and the screen only asks for it.
    var failureSentence: String? {
        if let playbackFailure, !playbackFailure.isEmpty { return playbackFailure }
        if case .failed(let sentence) = load { return sentence }
        return nil
    }

    /// The way out's own words. ⚠ It names the destination, because a bare chevron on a screen that fills a
    /// television does not say where it goes.
    var backLabel: String { "Back to \(detail?.name ?? "the title")" }

    /// ⚠ The origin the player's ARTWORK is fetched from — the Up Next card's own still (P7).
    ///
    /// ⚠ It is exposed rather than threaded through the view hierarchy because it is **the same address every
    /// playback URL is already built against** (`recomputeRoute`), and it is not a secret: artwork rides the
    /// API's poster proxy, which is exactly the rule `ARCHITECTURE.md` §2's third principle exists for — no
    /// media-server URL and no credential ever reaches a client.
    var baseURL: URL { client.address.url }

    /// The series an episode belongs to — **P8's eyebrow**, and `nil` for a film.
    ///
    /// ⚠ It exists because `"Chapter 4"` is the whole top bar for an episode otherwise: the item's own name
    /// names nothing a viewer browsing a series recognises. The name is already decoded in the same
    /// `ItemDetail` (`detail.series.name`) and this screen simply never read it.
    var seriesName: String? {
        guard let name = detail?.series?.name, !name.isEmpty else { return nil }
        return name
    }

    /// `S2E5` for an episode, `nil` for a film — ⚠ through `DetailRules.episodeCode`, the app's ONE episode
    /// code, so the top bar and the title screen cannot spell it two ways.
    var episodeCode: String? {
        guard let season = detail?.season, let episode = detail?.episode else { return nil }
        return DetailRules.episodeCode(season: season, episode: episode)
    }

    /// ⚠ **TRUE WHEN THE SERVER'S OWN THRESHOLD SAYS THIS TITLE IS FINISHED** — the same `finishFraction`
    /// (0.95) the server uses to mark it played, read from the same constant rather than restated here.
    var hasFinished: Bool {
        PlaybackRules.finished(positionTicks: PlaybackRules.ticks(fromSeconds: position),
                               runtimeTicks: PlaybackRules.ticks(fromSeconds: duration))
    }

    /// The Up Next card's caption: `S2E5 · The Reckoning`. ⚠ `nil` when there is no card to draw.
    var upNextLabel: String? {
        guard let nextEpisode else { return nil }
        return PlaybackRules.upNextLabel(season: nextEpisode.season,
                                         episode: nextEpisode.episode,
                                         name: nextEpisode.name)
    }

    /// The card's own countdown line. ⚠ It reads the PUBLISHED seconds, so the number on screen and the
    /// number the rule computed are the same number.
    var upNextCountdownLabel: String? {
        guard let upNextSecondsLeft else { return nil }
        return "Playing in \(upNextSecondsLeft)s"
    }

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

        // ⚠⚠ **THE FACTS ARE REFINED, NOT DEMANDED.** Arrived from the Home? There is no `ItemDetail` — so ask
        // for it once, and treat a failure as SOFT: the row's own facts still open a titled, resumable player,
        // and the position it starts from is the row's own. ⚠ This is what makes the Home's hero Play button
        // honest rather than a second, thinner playback path.
        if detail == nil {
            if let fresh = try? await client.itemDetail(itemID: itemID, correlation: correlation) {
                detail = fresh
                duration = Double(fresh.runtime ?? 0)
                resumePosition = max(0, PlaybackRules.seconds(fromTicks: fresh.play.resumeTicks))
                position = resumePosition
                RKMLog.info("player: facts refined from the detail payload", category: .app,
                            correlation: correlation)
            } else {
                RKMLog.info("player: opened without a detail payload — using the row's own facts "
                            + "(resume \(Int(facts.resumeSeconds))s of \(Int(facts.runtimeSeconds))s)",
                            category: .app, correlation: correlation)
            }
        }

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
            // ⚠⚠ **AFTER THE FILM IS PLAYABLE, NEVER BEFORE** — Up Next is a courtesy at the END of an
            // episode, so nothing about it may stand between the viewer and the first frame. A failure here
            // is soft by construction (`loadNextEpisode` catches): no card, and the episode plays anyway.
            await loadNextEpisode()
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
        // ⚠⚠ **THE UP NEXT CLOCK IS DRIVEN BY THE VIEW'S ALWAYS-ON TICKER, NOT FROM HERE.** `AVPlayer`'s
        // periodic observer STOPS FIRING when playback pauses or reaches the end — and the end of the film is
        // exactly when Up Next must count down. So the countdown hangs off the 0.5 s `Timer` instead
        // (`tickUpNext()`), and this method stays only what it says: the position and the progress write.
    }

    /// ⚠ **The buffering signal, and it is real rather than decorative**: `PlaybackRules.shouldHideChrome`
    /// keeps the controls on screen while a stream is switching, and the view reports the player's own
    /// `timeControlStatus`. Without a setter this was a flag nothing ever set — a rule reading a constant.
    func setSwitching(_ value: Bool) {
        if isSwitching != value { isSwitching = value }
    }

    /// ⚠ Called by the view when `AVPlayerItem.status` becomes `.failed` — **the one failure that produces a
    /// silent black screen**, and the reason it goes through the same funnel as the notification.
    func reportItemFailed() {
        reportPlaybackFailure(PlaybackRules.failedToStartSentence)
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

    /// ⚠⚠ **D2 — the scrub row's own verb, which existed only as a comment until Phase P.** A left/right press
    /// with the track focused jogs the playhead instead of moving focus, exactly as his prototype's `moveItem`
    /// does on row 1. ⚠ It goes through the SAME `seek` as the scrubber and the ±10 s buttons, so the bar, the
    /// store's position and the player cannot disagree about where the playhead is.
    func jog(direction: Int) {
        seek(to: PlaybackRules.jogTarget(from: position, direction: direction, total: duration))
    }

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
    ///
    /// ⚠⚠ **THIS FUNCTION HAD NO CALLER UNTIL PHASE P (D3).** The ladder, its order and its audio-awareness
    /// were built, pinned and documented in `TVOS_PLAYER_PLAN.md` §C2 — and nothing invoked it, so a failed
    /// direct play reported a sentence and stopped. It is now the funnel through `reportPlaybackFailure`.
    ///
    /// ⚠ Returns **whether it climbed**, so the caller decides what to say: `false` means the ladder is
    /// exhausted and the failure is real, not transient.
    @discardableResult
    func escalateMode() -> Bool {
        guard let next = PlaybackRules.nextHLSMode(after: mode) else { return false }
        quality = PlaybackRules.defaultQualityLabel  // ⚠ a quality cap already forces `transcode`.
        mode = next
        escalationAttempt = PlaybackRules.ladderStep(next)
        // ⚠ The failure is cleared BEFORE the new item is attached: a notice left on screen while a stream is
        // being retried tells the viewer the retry already failed.
        playbackFailure = nil
        url = PlaybackURLs.playbackURL(base: client.address.url, itemID: itemID, mode: next,
                                      audioIndex: audioIndex,
                                      maxBitrate: PlaybackRules.maxBitrate(for: quality))
        RKMLog.error("player: streaming failed — escalating to \(next.rawValue) "
                     + "(attempt \(escalationAttempt) of \(PlaybackRules.ladderLength))",
                     category: .app, correlation: correlation)
        showToast(PlaybackRules.attemptSentence(next))
        return true
    }

    /// **P1 — *Try again* on the failure notice, and it is the only control on it.**
    ///
    /// ⚠ It climbs the ladder when there is a rung left, and otherwise re-requests **the same URL** — the
    /// common cause of a mid-film failure is a transient network drop, where the same request is exactly the
    /// right thing to send again. ⚠⚠ The reload token is what makes that second case real: `url` is
    /// `Equatable`, so re-assigning an identical value fires no `onChange` in the view and a "retry" that
    /// changed nothing would look identical to a broken button.
    func retryPlayback() {
        playbackFailure = nil
        if escalateMode() { return }
        reloadToken &+= 1
        showToast("Trying again…")
    }

    /// ⚠⚠ **THE ONE FUNNEL FOR "THIS STREAM IS NOT PLAYING", AND IT ESCALATES BEFORE IT REPORTS.**
    ///
    /// Every failure path lands here — the `AVPlayerItemFailedToPlayToEndTime` notification (a stream that
    /// died mid-film) and `reportItemFailed()` (a stream whose item status went `.failed`, i.e. the black
    /// screen) — so the two cannot disagree about whether the app has tried everything it can.
    ///
    /// ⚠ It TERMINATES: `nextHLSMode` returns `nil` at the last rung, so the app can climb at most three times
    /// and then says so rather than looping.
    func reportPlaybackFailure(_ sentence: String) {
        if escalateMode() { return }
        playbackFailure = sentence
        RKMLog.error("player: giving up after \(escalationAttempt) escalation(s) — \(sentence)",
                     category: .app, correlation: correlation)
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
    ///
    /// ⚠⚠ **D6 — IDEMPOTENT, AND THIS IS WHERE THE GUARD BELONGS.** Both callers are legitimate: `Back` runs
    /// before the screen tears down, and `onDisappear` runs after, and tvOS does not promise which order they
    /// arrive in. Before this guard, one press of `Back` sent two `stopped` reports and two verification reads,
    /// and the two save toasts raced each other. A guard at either CALL SITE would be wrong the moment the
    /// other one fires first.
    func finish() async {
        guard !didFinish else { return }
        didFinish = true
        isPlaying = false
        await report(.stopped)
    }

    /// ⚠ The viewer's own re-try of the position write, from the drawer's footer — deliberately NOT guarded by
    /// `didFinish`: this exists precisely because the automatic write did not land, so running it again is the
    /// whole point of the control.
    func retrySave() async {
        await report(.stopped)
    }

    // MARK: - Up Next

    /// Fetch the series' episode list — **once, and only when this item IS an episode.**
    ///
    /// ⚠⚠ **A FILM ASKS FOR NOTHING.** `detail.series` is present only on an Episode (`ItemDetail`), so a film
    /// costs no request at all — and a series' own detail page (which is what the title screen shows for a
    /// series) never reaches the player in the first place.
    ///
    /// ⚠ **SOFT BY CONSTRUCTION**: any failure here means no Up Next card. A courtesy at the end of an episode
    /// must never be able to stop the episode.
    private func loadNextEpisode() async {
        guard let seriesID = detail?.series?.id, !seriesID.isEmpty else { return }
        do {
            let list = try await client.seriesEpisodes(seriesID: seriesID,
                                                      correlation: correlation).episodes
            episodes = list
            nextEpisode = PlaybackRules.nextEpisode(after: itemID, in: list)
            RKMLog.info("player: Up Next — \(list.count) episode(s) reported; next is "
                        + (nextEpisode.map { "\($0.name) (\($0.id.prefix(8)))" } ?? "none (this is the last)"),
                        category: .app, correlation: correlation)
        } catch let error as APIError {
            nextEpisode = nil
            RKMLog.info("player: episode list unavailable — \(error.errorDescription ?? "")",
                        category: .app, correlation: correlation)
        } catch {
            nextEpisode = nil
        }
    }

    /// ⚠⚠ **THE COUNTDOWN'S WHOLE STATE MACHINE, IN ONE PLACE, DRIVEN BY THE VIEW'S ALWAYS-ON TICKER.**
    /// Three states and no fourth: no card · a card counting down · a hand-off on its way.
    ///
    /// ⚠ It is called from the 0.5 s `Timer` and NOT from the time observer, because `AVPlayer`'s periodic
    /// observer stops firing when playback ends — which is exactly when this must start.
    func tickUpNext() {
        guard !upNextDeclined, !upNextHandedOff, upNextHandoff == nil, nextEpisode != nil else { return }

        if upNextDeadline == nil {
            // ⚠ `duration > 0` as well as `hasFinished`: with an unknown runtime the finish fraction is not a
            // statement about anything (`PlaybackRules.finished` returns false for one, and this is the belt
            // to that braces).
            guard hasFinished, duration > 0 else { return }
            upNextDeadline = Date().addingTimeInterval(PlaybackRules.upNextSeconds)
            RKMLog.info("player: Up Next — this episode is finished; counting "
                        + "\(Int(PlaybackRules.upNextSeconds))s before \(nextEpisode?.name ?? "")",
                        category: .app, correlation: correlation)
        }
        guard let deadline = upNextDeadline else { return }
        let left = PlaybackRules.upNextRemaining(deadline: deadline.timeIntervalSinceReferenceDate,
                                                now: Date().timeIntervalSinceReferenceDate)
        if upNextSecondsLeft != left { upNextSecondsLeft = left }
        if left == 0 { requestNextEpisode() }
    }

    /// ⚠⚠ **THE HAND-OFF ITSELF — AND SETTING THE PUBLISHED EPISODE IS THE WHOLE ACTION.** The store has no
    /// `AppModel` and must not grow one: the VIEW performs the hand-off, which is also what keeps the order
    /// (this episode's `stopped` write, then the next episode's screen) in a place that can be read.
    private func requestNextEpisode() {
        guard let next = nextEpisode, !upNextHandedOff else { return }
        upNextSecondsLeft = nil
        upNextDeadline = nil
        upNextHandedOff = true
        upNextHandoff = next
        RKMLog.info("player: Up Next — handing over to \(next.name) (\(next.id.prefix(8)))",
                    category: .app, correlation: correlation)
    }

    /// *Play now* — the countdown's own action, and where focus lands when the card appears.
    func playNextNow() { requestNextEpisode() }

    /// *Cancel* — and ⚠⚠ **IT IS REMEMBERED, WHICH IS THE WHOLE POINT.** The trigger is the POSITION, and the
    /// position stays past `finishFraction` for the rest of the film, so a dismissal that only cleared the
    /// countdown would see the card return on the very next tick — a control that visibly does not work.
    func cancelUpNext() {
        upNextDeclined = true
        upNextDeadline = nil
        upNextSecondsLeft = nil
        upNextHandoff = nil
        RKMLog.info("player: Up Next — cancelled by the viewer", category: .app, correlation: correlation)
    }

    /// Called by the view once it has really handed the episode over, so a redraw cannot hand it over twice.
    func clearUpNextHandoff() { upNextHandoff = nil }

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
