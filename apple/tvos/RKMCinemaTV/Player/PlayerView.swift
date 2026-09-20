import SwiftUI
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
    @State private var lastInteraction = Date()
    @State private var now = Date()
    @State private var drawerFocus: DrawerFocus?
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

            if let failure = store.playbackFailure {
                failureNotice(failure)
            } else if case .failed(let sentence) = store.load {
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
        .onDisappear { Task { await store.finish() } }
        // ⚠ `Back` on the remote leaves the player. It is the ONE way out that must never be missing: a
        // screen you cannot leave is a dead end, which `ARCHITECTURE.md` ranks above any cosmetic rule.
        .onExitCommand { leave() }
        .onPlayPauseCommand { togglePlay() }
        .onReceive(ticker) { date in
            now = date
            pushPlayerTime()
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
        RKMLog.info("player: attaching item (\(reason)) \(LogRedactor.redact(url: url))",
                    category: .app)
        let wasPlaying = store.isPlaying
        player.replaceCurrentItem(with: AVPlayerItem(url: url))
        player.rate = Float(store.rate)
        seekPlayer(to: store.position, resume: wasPlaying)
        installTimeObserver()
        observeItemFailures()
    }

    private func start() {
        if let url = store.url {
            RKMLog.info("player: opening \(store.title)", category: .app)
            player.replaceCurrentItem(with: AVPlayerItem(url: url))
            player.rate = Float(store.rate)
            seekPlayer(to: store.position, resume: store.isPlaying)
        }
        installTimeObserver()
        observeItemFailures()
        Task { await store.load() }
    }

    /// One observer for the whole screen: it keeps the store's clock honest and drives the chrome's auto-hide.
    private func installTimeObserver() {
        guard timeObserver == nil else { return }
        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserver = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { time in
            let seconds = time.seconds.isFinite ? time.seconds : 0
            let duration = player.currentItem?.duration.seconds ?? 0
            store.tick(position: seconds,
                       duration: duration.isFinite ? duration : store.duration,
                       playing: player.rate > 0)
        }
    }

    /// A stream that will not play has to SAY so. ⚠⚠ This is the phase's chosen visible failure mode
    /// (`docs/TVOS_PLAYER_PLAN.md` §3): a black screen with nothing on it is the outcome this app refuses to
    /// ship, and the escalation ladder (`PlaybackRules.hlsLadder`) is what the app does about it — once.
    private func observeItemFailures() {
        guard let item = player.currentItem else { return }
        NotificationCenter.default.addObserver(
            forName: .AVPlayerItemFailedToPlayToEndTime, object: item, queue: .main) { _ in
                store.reportPlaybackFailure("This stream stopped unexpectedly.")
            }
        let url = item.asset as? AVURLAsset
        if let url, url.url.path.contains("/hls/") {
            RKMLog.verbose("player: HLS item for \(LogRedactor.redact(url: url.url))", category: .app)
        }
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
            failed: store.playbackFailure != nil || store.hasFailed,
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
