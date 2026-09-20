import SwiftUI
import Foundation
// ⚠⚠ **COMBINE IS NOT RE-EXPORTED BY SWIFTUI ANY MORE** — the same thing `App/AppModel.swift`'s header
// records for `ObservableObject`, and it cost THIS FILE the phase's first Mac round (2026-09-20):
// `PlayerView.swift:33: error: instance method 'autoconnect()' is not available due to missing import of
// defining module 'Combine'`. The `Timer.publish(...).autoconnect()` ticker below is the Combine API; the
// `.publisher(for:)` subscription is the second. ⚠ The sandbox gate could not see it — see
// `apple/scripts/check-imports.py`'s PATTERN_RULES, which now can.
import Combine
import AVFoundation
import UIKit
import RKMServerKit

/// **The player screen.**
///
/// ⚠⚠ **THIS FILE IS THE PART OF PHASE C THAT NO GATE ON THIS MACHINE CAN COMPILE.** It is SwiftUI +
/// `AVPlayer`, so `check-tvos-core.py`, `check-apple-typecheck.sh` and `check-tvos-models.py` all stop at its
/// edge (the typecheck script says so in its own footer). Everything decidable was pushed into
/// `Core/PlaybackRules.swift`, `Core/PlaybackURLs.swift` and `Core/PlaybackStore.swift`, which ARE compiled and
/// run; what is left here is deliberately only the three things that genuinely need a television — create the
/// item, seek it, play it — plus the layout his prototype specifies.
///
/// ⚠⚠ **WHAT IT DOES NOT DO, AND WHY THAT IS THE DESIGN:** it does not hand-roll focus movement, scrolling or
/// reveal maths. His prototype's JavaScript does all three (`moveRow`/`moveItem`/`paint`/`scrollIntoView`) and
/// this repo has paid for that mistake twice (`RailFocus.swift`, written then deleted; B3's 2-D grid,
/// predicted to be "the ONE case the platform does not solve" and it was). The platform's focus engine moves
/// focus; this screen says only WHERE FOCUS STARTS (`.play`, his own decision) and what each control does.
struct PlayerView: View {

    @ObservedObject var store: PlaybackStore
    @ObservedObject var app: AppModel

    @State private var player = AVPlayer()
    @State private var timeObserver: Any?
    /// ⚠ The resume target, held until the item says it is ready — see `applyPendingSeekIfReady`.
    @State private var pendingSeek: Double?
    @State private var lastInteraction = Date()
    @State private var now = Date()
    @FocusState private var drawerFocus: DrawerFocus?
    @State private var pulseCounter = 0
    @FocusState private var focus: PlayerFocus?

    private let ticker = Timer.publish(every: 0.5, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack(alignment: .topLeading) {
            Color.black.ignoresSafeArea()

            PlayerSurface(player: player, gravity: gravity)
                .ignoresSafeArea()

            scrims

            // ⚠ The caption strip sits ABOVE the transport region so the two never overlap, and it is drawn
            // whether or not the chrome is visible — a subtitle does not hide because the controls did.
            VStack {
                Spacer(minLength: 0)
                PlayerCueStrip(text: store.cueText)
                    .padding(.bottom, TVTokens.Player.cueBottom)
            }

            chrome
                .opacity(chromeVisible ? 1 : 0)
                .animation(.timingCurve(0.22, 0.61, 0.36, 1, duration: 0.35), value: chromeVisible)

            overlayPanels

            // ⚠ One source for "why is this not playing", from the store — see `failureSentence`.
            // ⚠⚠ **THE TOAST IS PLACED HERE, AND IT WAS DECLARED AND FORGOTTEN UNTIL ROUND 2** — the store's
            // feedback (a saved position, a track change, a refused write) had nowhere to appear. His
            // prototype's `.toast` sits at `bottom:6%`, centred, above the transport row.
            if let toast = store.toast {
                VStack {
                    Spacer(minLength: 0)
                    PlayerToast(text: toast)
                        .padding(.bottom, TVTokens.Player.toastBottom)
                }
                .allowsHitTesting(false)
                .transition(.opacity)
            }

            if let sentence = store.failureSentence {
                failureNotice(sentence)
            } else if store.load == .loading {
                loadingNotice
            }

            centrePulse
        }
        // ⚠⚠ **THE DEFAULT FOCUS, AND IT IS THE PROTOTYPE'S OWN DECISION** — *"let r = 2, i = 2; // default
        // focus: play/pause"*. `.defaultFocus` is the PLATFORM's way to say it (the focus engine then owns
        // every move from there); nothing here computes a neighbour.
        .defaultFocus($focus, .play)
        .onAppear { start() }
        .onDisappear {
            // ⚠ The time observer is REMOVED here, and that is not tidiness: an observer added to the player
            // and never removed keeps the player (and this view's closure) alive for the app's lifetime, and a
            // film's worth of those is a leak nobody sees on a simulator round.
            if let timeObserver { player.removeTimeObserver(timeObserver) }
            timeObserver = nil
            Task { await store.finish() }
        }
        // ⚠ A stream that dies mid-film has to say so — the visible failure mode this phase chose. As a
        // PUBLISHER rather than an `addObserver` token: one subscription, torn down with the screen.
        .onReceive(NotificationCenter.default.publisher(for: .AVPlayerItemFailedToPlayToEndTime)) { _ in
            store.reportPlaybackFailure("This stream stopped unexpectedly.")
        }
        // ⚠ `Back` on the remote leaves the player. It is the ONE way out that must never be missing: a
        // screen you cannot leave is a dead end, which `ARCHITECTURE.md` ranks above any cosmetic rule.
        .onExitCommand { leave() }
        .onPlayPauseCommand { togglePlay() }
        // ⚠ The 0.5 s tick exists for the CHROME's idle clock (`PlaybackRules.shouldHideChrome` reads it) and
        // to force a re-render so the top bar's clock and the save line update. The PLAYHEAD is the time
        // observer's job (`installTimeObserver`) — one clock each, so neither can drift the other.
        .onReceive(ticker) { date in
            now = date
            applyPendingSeekIfReady()
        }
        // ⚠⚠ **`AVPlayer`'S OWN REQUESTS ARE NOT THIS APP'S REQUESTS, SO NOTHING ELSE CAN LOG THEM.** Every
        // JSON call goes through `APIClient` (which logs and redacts); the HLS playlist and its segments are
        // fetched by AVFoundation itself, so a `401` there is invisible unless the item's own error log is read
        // — and that is exactly the `401` on a `…/hls/…` URL F2 is about. ⚠ `errorStatusCode` is HTTP's, so a
        // 401 here is the answer, and no cookie/token ever appears in `uri` (the api strips `api_key`, and this
        // app puts the credential in a HEADER).
        .onReceive(NotificationCenter.default.publisher(for: .AVPlayerItemNewErrorLogEntry)) { note in
            guard let item = note.object as? AVPlayerItem,
                  let event = item.errorLog()?.events.last else { return }
            RKMLog.error("player: AVPlayer's own request failed — status=\(event.errorStatusCode) "
                         + "uri=\(LogRedactor.redact(text: event.uri ?? "")) "
                         + "\(event.errorComment ?? "")", category: .net)
        }
        .onChange(of: store.url) { _, _ in attachItem(reason: "route changed") }
        .onChange(of: store.isPlaying) { _, playing in
            playing ? player.play() : player.pause()
        }
        .onChange(of: store.rate) { _, rate in
            if store.isPlaying { player.rate = Float(rate) }
        }
        .onChange(of: store.quality) { _, _ in seekPlayer(to: store.position) }
        .onChange(of: store.audioIndex) { _, _ in seekPlayer(to: store.position) }
    }

    // MARK: - Composition

    private var scrims: some View {
        VStack(spacing: 0) {
            LinearGradient(colors: [RKMColour.background.opacity(0.72), .clear],
                           startPoint: .top, endPoint: .bottom)
                .frame(height: 1080 * TVTokens.Player.scrimTopFraction)
            Spacer(minLength: 0)
            LinearGradient(colors: [.clear, RKMColour.background.opacity(0.86)],
                           startPoint: .top, endPoint: .bottom)
                .frame(height: 1080 * TVTokens.Player.scrimBottomFraction)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }

    private var chrome: some View {
        VStack(spacing: 0) {
            PlayerTopBar(store: store, focus: $focus) { leave() }
            Spacer(minLength: 0)
            VStack(spacing: TVTokens.Player.paneGap) {
                PlayerScrubber(store: store, focus: $focus) { target in seek(target) }
                PlayerControlsRow(store: store,
                                  focus: $focus,
                                  onTogglePlay: { togglePlay() },
                                  onSkip: { delta in skip(delta) })
            }
            .padding(.horizontal, TVTokens.Player.barPaddingH)
            .padding(.bottom, TVTokens.Player.barPaddingBottom)
        }
    }

    @ViewBuilder
    private var overlayPanels: some View {
        switch store.panel {
        case .none:
            EmptyView()
        case .info:
            VStack(spacing: 0) {
                Spacer(minLength: 0)
                PlayerInfoPanel(store: store)
            }
            .ignoresSafeArea()
            .transition(.opacity)
        case .settings:
            HStack(spacing: 0) {
                Spacer(minLength: 0)
                PlayerSettingsPanel(store: store, focus: $drawerFocus) { closePanel() }
            }
            .ignoresSafeArea()
        }
    }

    private var centrePulse: some View {
        Group {
            if pulseCounter > 0 {
                Image(systemName: store.isPlaying ? "pause.fill" : "play.fill")
                    .font(.system(size: TVTokens.Player.pulseGlyph, weight: .bold))
                    .foregroundStyle(RKMColour.primary)
                    .frame(width: TVTokens.Player.pulseSize, height: TVTokens.Player.pulseSize)
                    .background(Circle().fill(RKMColour.background.opacity(0.55)))
                    .id(pulseCounter)
                    .transition(.scale(scale: 0.72).combined(with: .opacity))
                    .allowsHitTesting(false)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func failureNotice(_ sentence: String) -> some View {
        VStack(spacing: TVTokens.Player.paneGap) {
            Text(sentence)
                .font(.system(size: TVTokens.Player.infoBodySize, weight: .semibold))
                .multilineTextAlignment(.center)
                .foregroundStyle(RKMColour.primary)
                .frame(maxWidth: TVTokens.Player.infoMeasure)
            Text("Press Back to return.")
                .font(.system(size: TVTokens.Player.paneDescSize))
                .foregroundStyle(RKMColour.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(RKMColour.background.opacity(0.72))
    }

    private var loadingNotice: some View {
        VStack(spacing: TVTokens.Player.paneGap) {
            ProgressView()
            Text("Preparing \(store.title)…")
                .font(.system(size: TVTokens.Player.infoBodySize, weight: .medium))
                .foregroundStyle(RKMColour.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(RKMColour.background.opacity(0.55))
    }

    // MARK: - The player plumbing (the only AVFoundation in the app)

    /// ⚠ `.resizeAspect` / `.resizeAspectFill` — his Fit / Fill, and the ONLY thing "Picture" changes.
    private var gravity: AVLayerVideoGravity {
        store.picture == .fill ? .resizeAspectFill : .resizeAspect
    }

    /// ⚠⚠ **THE ITEM IS REBUILT WHEN THE URL CHANGES, AND THE POSITION IS RESTORED — that is how a quality,
    /// audio-track or mode change takes effect.** `AVPlayer` cannot change the mode of a stream it is already
    /// playing, so the app hands it a new item and seeks back to where the viewer was; the visible cost is a
    /// brief re-buffer, and the alternative (silently keeping the old stream) would make the drawer's controls
    /// look applied while nothing changed.
    private func attachItem(reason: String) {
        guard let url = store.url else { return }
        // ⚠⚠ **THE LOG LINE F2 IS ANSWERED FROM.** It says which route was chosen, the position the player
        // intends to resume at, and — the part that was missing until his round-3 report — whether a session
        // cookie was handed to the asset.
        let cookies = HTTPCookieStorage.shared.cookies(for: url) ?? []
        let session = PlaybackAuth.sessionCookie(for: url, in: cookies)
        RKMLog.info("player: attaching item (\(reason)) mode=\(store.mode.rawValue) "
                    + "resume=\(Int(store.position))s "
                    + "credential=\(session == nil ? "MISSING" : "handed to the asset") "
                    + \(LogRedactor.redact(url: url)), category: .app)
        let wasPlaying = store.isPlaying
        player.replaceCurrentItem(with: AVPlayerItem(asset: makeAsset(url: url, session: session)))
        player.rate = Float(store.rate)
        // ⚠⚠ **THE SEEK IS DEFERRED UNTIL THE ITEM IS READY.** `AVPlayer.seek` issued before an item has
        // loaded is routinely DROPPED for an HLS stream (there is no playlist to seek inside yet) — which is
        // how "the player opens but it never resumes" happens with nothing in the log. So the target is
        // remembered and applied by the ticker the moment `status == .readyToPlay`.
        pendingSeek = store.position
        seekPlayer(to: store.position, resume: wasPlaying)
        installTimeObserver()
    }

    /// ⚠⚠ **THE MAC-ONLY CALL SITE `Core/PlaybackAuth.swift` HAS BEEN WAITING FOR SINCE C1.** That file decides
    /// WHICH cookie may be handed over and what the refusal says; it deliberately does not name an AVFoundation
    /// symbol, because it is compiled and RUN on Linux. This is the one place the credential meets `AVURLAsset`
    /// — and until 2026-09-20 it did not exist at all: the player handed `AVPlayer` a bare URL, the api answered
    /// `401` on its session-scoped HLS route, and the screen opened onto a film that never started.
    ///
    /// ⚠ **`AVURLAssetHTTPCookiesKey` IS USED AS A SYMBOL ON PURPOSE.** It is AVFoundation's documented key for
    /// exactly this, and a wrong or missing symbol must be a COMPILE error on the Mac rather than a silent no-op
    /// — because a silent no-op here would poison the phase's own measurement: we would conclude *"the cookie
    /// does not reach a segment"* when in truth we never sent one.
    private func makeAsset(url: URL, session: HTTPCookie?) -> AVURLAsset {
        guard let session else {
            // ⚠ A refusal, not a fallback (see `PlaybackAuth.missingSessionSentence`): an unauthenticated load
            // does not fail cleanly — it draws a black screen, which is the least diagnosable bug a TV has.
            store.reportPlaybackFailure(PlaybackAuth.missingSessionSentence)
            return AVURLAsset(url: url)
        }
        return AVURLAsset(url: url, options: [AVURLAssetHTTPCookiesKey: [session]])
    }

    private func start() {
        if let url = store.url {
            RKMLog.info("player: opening \(store.title)", category: .app)
            player.replaceCurrentItem(with: AVPlayerItem(url: url))
            player.rate = Float(store.rate)
            seekPlayer(to: store.position, resume: store.isPlaying)
        }
        installTimeObserver()
        Task { await store.load() }
    }

    /// One observer for the whole screen: it keeps the store's clock honest and drives the chrome's auto-hide.
    private func installTimeObserver() {
        guard timeObserver == nil else { return }
        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserver = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { time in
            let seconds = time.seconds.isFinite ? time.seconds : 0
            let duration = player.currentItem?.duration.seconds ?? 0
            store.setSwitching(player.timeControlStatus == .waitingToPlayAtSpecifiedRate)
            store.tick(position: seconds,
                       duration: duration.isFinite ? duration : store.duration,
                       playing: player.rate > 0)
        }
    }

    /// ⚠ The deferred half of the resume: a seek is only honoured once there is a playlist to seek inside.
    private func applyPendingSeekIfReady() {
        guard let target = pendingSeek, player.currentItem?.status == .readyToPlay else { return }
        pendingSeek = nil
        RKMLog.info("player: item ready — resuming at \(PlaybackRules.fmtTime(target))", category: .app)
        seekPlayer(to: target, resume: store.isPlaying)
    }

    /// Push the store's own position into the player when the app — not the viewer — moved it.
    private func seekPlayer(to seconds: Double, resume: Bool = false) {
        let time = CMTime(seconds: max(0, seconds), preferredTimescale: 600)
        player.seek(to: time, toleranceBefore: .zero, toleranceAfter: .zero) { _ in
            if resume { player.play() }
        }
        lastInteraction = Date()
    }

    // MARK: - The five verbs his prototype's Enter key performs

    private func togglePlay() {
        // ⚠ Before the stream exists the app has nothing to pause, so the press starts the load instead of
        // flipping a flag that does nothing.
        guard store.url != nil else { return }
        if store.isPlaying {
            store.pause()
        } else {
            store.play()
        }
        pulseCounter &+= 1
        lastInteraction = Date()
    }

    private func skip(_ delta: Double) {
        store.skip(by: delta)
        seekPlayer(to: store.position)
        lastInteraction = Date()
    }

    /// ⚠ A scrub is BOTH a store change (the bar redraws immediately) and a player seek — one function, so the
    /// two cannot disagree about where the playhead is.
    private func seek(_ seconds: Double) {
        store.seek(to: seconds)
        seekPlayer(to: store.position)
        lastInteraction = Date()
    }

    private func closePanel() {
        store.closePanel()
        focus = .play
    }

    private func leave() {
        // ⚠ The position write is fired and awaited by the store's `finish()`; the SCREEN closes at once so a
        // slow network cannot trap a viewer on a black frame.
        let leaving = store
        app.closePlayer()
        Task { await leaving.finish() }
    }

    // MARK: - Chrome visibility (the rule is `PlaybackRules`', the clock is this view's)

    private var chromeVisible: Bool {
        !PlaybackRules.shouldHideChrome(
            playing: store.isPlaying,
            switching: store.isSwitching,
            failed: store.hasFailed,
            hoveringChrome: false,
            panelOpen: store.panel != .none || isAnythingFocused,
            idleSeconds: now.timeIntervalSince(lastInteraction))
    }

    /// ⚠⚠ **A FOCUSED CONTROL KEEPS THE CHROME ON — and this is the one tvOS-specific addition to the web's
    /// rule.** The web's version watches the POINTER (`hoverChrome`); a television has no pointer, and its
    /// equivalent is that somebody is standing on a control. Without this, a viewer who paused on "Forward 10s"
    /// and thought about it would watch the row fade out from under the focus ring.
    private var isAnythingFocused: Bool {
        focus != nil || drawerFocus != nil
    }
}

// MARK: - The video surface

/// A bare `AVPlayerLayer` — **no system controls, on purpose.**
///
/// ⚠ `AVPlayerViewController` (and SwiftUI's `VideoPlayer`) bring tvOS's own transport UI with them: a
/// scrubber, a title bar and a menu button that would sit under this screen's chrome and answer the same
/// remote presses. His prototype specifies every control, so the app draws them and the surface stays a
/// surface. `videoGravity` is the only property it needs.
struct PlayerSurface: UIViewRepresentable {

    let player: AVPlayer
    let gravity: AVLayerVideoGravity

    func makeUIView(context: Context) -> PlayerLayerView {
        let view = PlayerLayerView()
        view.playerLayer.player = player
        view.playerLayer.videoGravity = gravity
        view.backgroundColor = .black
        return view
    }

    func updateUIView(_ view: PlayerLayerView, context: Context) {
        view.playerLayer.player = player
        view.playerLayer.videoGravity = gravity
    }
}

/// The `UIView` whose backing layer IS the player layer.
final class PlayerLayerView: UIView {

    override class var layerClass: AnyClass { AVPlayerLayer.self }

    var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
}
