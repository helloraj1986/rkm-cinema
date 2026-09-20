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
// ⚠⚠ **PHASE P: `MPNowPlayingInfoCenter` (P5).** The system's own "what's playing", the Siri Remote's
// play/pause when this app is not frontmost, and *"Hey Siri, pause"* all read from it — and a native tvOS
// player is expected to publish it. ⚠ `MediaPlayer` is now a rule in `apple/scripts/check-imports.py`, added
// in the same commit, because a framework the app uses and no gate watches is a blind spot by construction.
import MediaPlayer
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

    /// ⚠⚠ **P4 — THE SCREEN'S OWN LIFECYCLE.** Before Phase P the app read `scenePhase` only to write a log
    /// line, so pressing HOME on the Siri Remote left the film **playing behind the tvOS Home screen** — audio
    /// included.
    @Environment(\.scenePhase) private var scenePhase
    /// ⚠ P3 — the pulse is the screen's one large animation, and it is the one reduced motion must remove.
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

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
                // ⚠⚠ **AND WHILE THE NOTICE IS UP THE CHROME IS OUT OF THE FOCUS CHAIN — that is the
                // `ProfilesView` #17 lesson, applied before it can happen here.** The notice fills the screen,
                // so a ring that could still move onto the transport *behind* it would be a control the viewer
                // cannot see standing on a control they can — with the notice's own `Try again` one random
                // direction away. ⚠ `.disabled` rather than hiding the chrome: the transport stays readable
                // under the dim, which is what tells the viewer their film is still there.
                .disabled(store.hasFailed)

            overlayPanels
                // ⚠ The same rule as the chrome above: a drawer left open over the notice would keep its own
                // rows in the focus chain, behind a surface the viewer is now looking at.
                .disabled(store.hasFailed)

            // ⚠⚠ **P7 — UP NEXT, ON THE RIGHT EDGE, BECAUSE THE BAR AND THE TRANSPORT OWN THE OTHER TWO
            // BANDS.** Vertically centred: a `ZStack` with `.trailing` alignment would put the card at the
            // top-right corner, under the top bar, so the placement is the middle band and nothing else.
            if store.upNextSecondsLeft != nil, !store.hasFailed {
                HStack(spacing: 0) {
                    Spacer(minLength: 0)
                    PlayerUpNextCard(store: store, focus: $focus, base: store.baseURL,
                                     onPlayNow: { store.playNextNow() },
                                     onCancel: {
                                         store.cancelUpNext()
                                         focus = .play
                                     })
                        .padding(.trailing, TVTokens.Player.upNextTrailing)
                }
                .transition(.move(edge: .trailing).combined(with: .opacity))
            }

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

            // ⚠⚠ **P2 — A STALL SAYS SO.** It is drawn UNDER the notice and only when the film is otherwise
            // fine: a stall during an escalation would otherwise hide the toast that says which mode is
            // being tried, and a stall after a failure would be a second explanation of the first one.
            if store.isSwitching, !store.hasFailed, store.load == .ready {
                PlayerStallIndicator()
                    .transition(.opacity)
            }

            if store.failureSentence != nil {
                // ⚠⚠ **P1 — THE NOTICE IS A CONTROL SURFACE NOW**, not two `Text`s: `Try again` retries the
                // stream (climbing the ladder when there is a rung left), and the notice says where the ring
                // is and that MENU leaves. A failure state with nothing focusable is a dead end, which is the
                // one thing this app's own architecture ranks above any cosmetic rule.
                PlayerFailureNotice(store: store, focus: $focus) { store.retryPlayback() }
                    .background(RKMColour.background.opacity(0.72))
            } else if store.load == .loading {
                loadingNotice
            }

            centrePulse
        }
        // ⚠⚠ **THE DEFAULT FOCUS, AND IT IS THE PROTOTYPE'S OWN DECISION** — *"let r = 2, i = 2; // default
        // focus: play/pause"*. `.defaultFocus` is the PLATFORM's way to say it (the focus engine then owns
        // every move from there); nothing here computes a neighbour. ⚠⚠ **And since Phase P it READS the rule
        // instead of restating it**: `PlaybackRules.defaultFocusIsPlayPause` was a constant nothing consumed,
        // so the rule and the screen could have disagreed without a single gate noticing.
        .defaultFocus($focus, PlaybackRules.defaultFocusIsPlayPause ? .play : .back)
        .onAppear { start() }
        .onDisappear {
            // ⚠ The time observer is REMOVED here, and that is not tidiness: an observer added to the player
            // and never removed keeps the player (and this view's closure) alive for the app's lifetime, and a
            // film's worth of those is a leak nobody sees on a simulator round.
            if let timeObserver { player.removeTimeObserver(timeObserver) }
            timeObserver = nil
            // ⚠⚠ **D7 — THE PLAYER IS STOPPED, NOT MERELY UNOBSERVED.** Removing the observer used to leave
            // the item attached and the `AVPlayer` decoding: audio kept playing behind whatever screen came
            // next, and the item held the player alive. One `pause()` and one `replaceCurrentItem(with: nil)`
            // is the whole fix — tvOS has no `AVPlayerViewController` here to do it for us.
            player.pause()
            player.replaceCurrentItem(with: nil)
            // ⚠ P5 — and the system's now-playing panel must not go on advertising a film this app has left.
            MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
            Task { await store.finish() }
        }
        // ⚠ A stream that dies mid-film has to say so — the visible failure mode this phase chose. As a
        // PUBLISHER rather than an `addObserver` token: one subscription, torn down with the screen.
        .onReceive(NotificationCenter.default.publisher(for: .AVPlayerItemFailedToPlayToEndTime)) { _ in
            store.reportPlaybackFailure("This stream stopped unexpectedly.")
        }
        // ⚠⚠ **MENU CLOSES THE TOPMOST THING — NOT THE FILM.** It is the ONE way out that must never be
        // missing, **and the one that must not overshoot**: his report, 2026-09-21 — *"once the headphone icon is
        // clicked and overlay opens how does the user comes out of it, the back button should close it
        // automatically"*. Before this it went straight to `leave()`, so MENU with the drawer open left the
        // film and every control the drawer holds was a press away from unreachable. The ladder itself is
        // `PlaybackRules.menuTarget` (pinned); this only carries it out.
        .onExitCommand { handleExit() }
        .onPlayPauseCommand { togglePlay() }
        // ⚠ The 0.5 s tick exists for the CHROME's idle clock (`PlaybackRules.shouldHideChrome` reads it) and
        // to force a re-render so the top bar's clock and the save line update. The PLAYHEAD is the time
        // observer's job (`installTimeObserver`) — one clock each, so neither can drift the other.
        .onReceive(ticker) { date in
            now = date
            applyPendingSeekIfReady()
            // ⚠⚠ **P4 — THE ONE PLACE A STREAM THAT NEVER STARTED IS CAUGHT.** `AVPlayerItemFailedToPlayToEndTime`
            // (below) is a stream that died MID-FILM; an item whose `status` went `.failed` is the classic
            // **silent black screen**, and it fires no notification this screen can subscribe to. So it is
            // POLLED — on the clock that already runs — and reported through the same store funnel.
            // ⚠ The `!store.hasFailed` guard is what stops a report every half-second once the app has given up.
            if player.currentItem?.status == .failed, !store.hasFailed {
                RKMLog.error("player: item status failed — the stream never started", category: .app)
                store.reportItemFailed()
            }
            // ⚠⚠ **P7 — THE UP NEXT COUNTDOWN HANGS OFF THIS TIMER, NOT OFF THE TIME OBSERVER.** `AVPlayer`'s
            // periodic observer stops firing when playback ends, which is precisely when the countdown starts.
            store.tickUpNext()
            // ⚠ P5 — the system's own now-playing panel, kept honest on the same clock as everything else.
            publishNowPlaying()
        }
        // ⚠⚠ **P1 — A RETRY THAT RE-REQUESTS THE SAME URL IS INVISIBLE TO `onChange(of: store.url)`**, because
        // the URL is unchanged. The store's reload token is the second signal, and it is the only reason the
        // notice's `Try again` works for a transient failure rather than appearing to do nothing.
        .onChange(of: store.reloadToken) { _, _ in attachItem(reason: "retry") }
        // ⚠⚠ **P7 — THE HAND-OFF, AND IT IS THE VIEW'S JOB BECAUSE THE STORE HAS NO `AppModel`.** The order is
        // deliberate: the CURRENT episode's position write is started first (it is the one thing that must not
        // be lost), then the next episode's screen replaces this one — and `.id(playback.itemID)` on the
        // routing view is what makes that a real re-entry rather than a silent store swap.
        .onChange(of: store.upNextHandoff) { _, item in
            guard let item else { return }
            store.clearUpNextHandoff()
            handOff(to: item)
        }
        // ⚠⚠ **P1 — THE RING MOVES ONTO THE NOTICE WHEN IT APPEARS.** Without this the notice is focusable but
        // nobody is standing on it: the screen's focus would be wherever it was, and the one control that can
        // fix the failure would be a press away with no indication which way.
        .onChange(of: store.hasFailed) { _, failed in
            if failed {
                // ⚠ And the drawer is CLOSED, not merely disabled: the notice is what this screen is about
                // until the viewer answers it, and the audio/subtitle rows are reachable again the moment the
                // stream plays.
                store.closePanel()
                focus = .noticeRetry
            }
        }
        // ⚠ **P7 — AND ONTO *Play now* WHEN THE CARD APPEARS.** The platform's own behaviour for a
        // time-limited control, and the only sane default on one that expires. ⚠ Only on the TRANSITION, so a
        // viewer who has moved to *Cancel* is not dragged back every half-second.
        .onChange(of: store.upNextSecondsLeft) { old, new in
            if old == nil, new != nil { focus = .upNextPlay }
        }
        // ⚠⚠ **P4 — LEAVING THE FOREGROUND PAUSES THE FILM.** The `pause()` goes through the store, so the
        // `onChange(of: store.isPlaying)` below is what actually stops the player — one path, not two.
        .onChange(of: scenePhase) { _, phase in
            guard phase != .active else { return }
            guard store.isPlaying else { return }
            RKMLog.info("player: leaving the foreground — pausing", category: .app)
            store.pause()
        }
        // ⚠⚠ **P2 (his round) — EVERY INPUT RESTARTS THE CHROME'S CLOCK.** Three handlers, because on tvOS a
        // remote press reaches the app by one of exactly three routes and no single one covers all of them:
        //   · it MOVED the ring            → `onChange(of: focus)`
        //   · it moved the drawer's ring   → `onChange(of: drawerFocus)`
        //   · it moved neither (the ring is at the end of a row, so the focus engine had nowhere to put it)
        //                                  → the root `onMoveCommand`, which is called for exactly the presses
        //                                    the engine could not consume
        // ⚠ Together they are his file's `resetIdle()` on `keydown`, and without them the 4 s timer would hide
        // the controls out from under a viewer who is using them.
        .onChange(of: focus) { _, _ in noteInput() }
        .onChange(of: drawerFocus) { _, _ in noteInput() }
        .onMoveCommand { _ in noteInput() }
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
            // ⚠⚠ **`player.play()` / `player.pause()` ARE NOT USED HERE, AND THAT IS THE SPEED FEATURE.**
            // `play()` sets the rate to `1` whatever the viewer chose — so a film at 1.5× that was paused and
            // resumed would silently come back at 1×. All three places that start or stop this player now go
            // through the ONE rule (here, `attachItem`, and the speed change below), which is exactly what the
            // two-answers shape of bug 1 was.
            player.rate = PlaybackRules.playerRate(isPlaying: playing, rate: store.rate)
        }
        .onChange(of: store.rate) { _, rate in
            // ⚠ The same rule as `attachItem` — one function, so the speed change and the attach cannot
            // disagree about what a rate MEANS (bug 1's shape was two call sites, two answers).
            player.rate = PlaybackRules.playerRate(isPlaying: store.isPlaying, rate: rate)
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
                // ⚠⚠ **D2 — THE JOG IS WIRED HERE, WHICH IS THE LINE THE OLD COMMENT CLAIMED AND NO CODE DID.**
                // A left/right press with the track focused now moves the playhead — by `PlaybackRules.jogSeconds`
                // on a single press, accelerating while the presses keep coming — through the store, and the
                // player follows it in `jog(_:)` below. One path, so the bar and the film cannot disagree about
                // where the playhead is.
                PlayerScrubber(store: store, focus: $focus) { direction in jog(direction) }
                PlayerControlsRow(store: store,
                                  focus: $focus,
                                  onTogglePlay: { togglePlay() },
                                  onSkip: { delta in skip(delta) },
                                  onOpenSettings: { openSettings() })
            }
            .padding(.horizontal, TVTokens.Player.barPaddingH)
            .padding(.bottom, TVTokens.Player.barPaddingBottom)
            // ⚠⚠ **THE TRACK AND THE TRANSPORT ARE ONE FOCUS SECTION — AND SPLITTING THEM IS A DEFECT THIS
            // PHASE UNDID.** Phase P gave the transport row a section of its own and left the track outside it;
            // round 12's lesson is that the engine prefers targets INSIDE the section the ring is in, so a row
            // that is a section can hold the ring and make `Up` do nothing — killing the ONE gesture that
            // reaches the scrubber, which is the control his round went looking for. Both together: `Up` from
            // `Play` reaches the track, `Down` from the track returns. ⚠ Hypothesis (falsifier **P2-F3**);
            // no focus engine runs on Linux.
            .frame(maxWidth: .infinity, alignment: .leading)
            .focusSection()
        }
    }

    /// ⚠⚠ **OPENING THE DRAWER IS TWO THINGS, AND ONE OF THEM WAS MISSING — HIS BUG 4.**
    ///
    /// `store.openSettings()` only sets the panel's state. **An `.overlay` is VISUAL ONLY** (the lesson
    /// `KNOWN_ISSUES` #17 already bought on the profile picker): the panel appeared on top of the transport
    /// without the transport leaving the focus chain, so the ring stayed on the headphone button *behind* the
    /// panel. The viewer then pressed a direction and either nothing moved or the ring went somewhere invisible
    /// — a drawer that looks right and cannot be used.
    ///
    /// ⚠ So the screen claims the drawer's focus in the SAME action that opens it, on the category the store
    /// actually selected (`.picture`, which is what `openSettings()` sets) rather than a hardcoded one.
    private func openSettings() {
        store.openSettings()
        drawerFocus = .category(store.category)
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
            // ⚠⚠ **`alignment: .top` IS NOT COSMETIC — IT IS THE OTHER HALF OF HIS BUG 4.**
            //
            // `HStack`'s default alignment is `.center`. A child TALLER than its container therefore overflows
            // **equally at the top and the bottom** — and the top of this panel is the "PLAYER SETTINGS" header
            // and all five rail items. His 19-result pane was 1875.2 pt on a 1080 pt screen, so ≈398 pt was
            // drawn ABOVE the top edge: *"i click on subtitles all the other control vanishes"*, exactly.
            //
            // ⚠ `.top` means an overflow can only ever go DOWNWARD, so the drawer's own controls are never the
            // part that is lost. ⚠ It is a second line of defence, not the fix — the list is bounded now
            // (`PlaybackRules.paneListHeight`) so that nothing overflows at all — but a layout that loses its
            // navigation when its content grows is the defect, not the symptom.
            HStack(alignment: .top, spacing: 0) {
                Spacer(minLength: 0)
                PlayerSettingsPanel(store: store, focus: $drawerFocus)
                    // ⚠ …and the panel is pinned inside its own slot for the same reason.
                    .frame(maxHeight: .infinity, alignment: .top)
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
                    // ⚠ P3 — the screen's one large animation: under reduced motion the glyph still appears and
                    // still changes shape, it simply does not spring into place.
                    .transition(reduceMotion ? .opacity
                                             : .scale(scale: 0.72).combined(with: .opacity))
                    .allowsHitTesting(false)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
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
                    + LogRedactor.redact(url: url), category: .app)
        let wasPlaying = store.isPlaying
        player.replaceCurrentItem(with: AVPlayerItem(asset: makeAsset(url: url, session: session)))
        // ⚠⚠ **THE PLAYER'S RATE NOW COMES FROM THE STORE'S FLAG, AND THAT IS THE STRUCTURAL HALF OF BUG 1.**
        // It used to be a bare `player.rate = Float(store.rate)` — **`rate = 1` is `play()`**, so this line
        // STARTED the film whatever the store believed, and the flag and the picture could never be reconciled.
        // A route change (quality, audio track, an escalation) while paused must also STAY paused, which this
        // is the only line that can express. ⚠ One source of truth, and it is the store's.
        player.rate = PlaybackRules.playerRate(isPlaying: store.isPlaying, rate: store.rate)
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

    /// ⚠⚠ **D5 — `start()` NO LONGER ATTACHES AN ITEM ITSELF, AND THAT IS THE FIX.** It used to call
    /// `player.replaceCurrentItem(with: AVPlayerItem(url: url))` — a bare URL, evaluated before the
    /// credential-bearing `makeAsset(url:session:)` path exists. That is **round 4's defect class kept alive as
    /// a second attach path**, and it was inert only by luck (`store.url` is `nil` at `onAppear`, because the
    /// load that produces it has not run). One attach path means the credential cannot be forgotten by one of
    /// two.
    ///
    /// ⚠ What is left is exactly the three things a television needs: make the clock, start the load, and let
    /// the URL's own `onChange` attach the item when it exists.
    private func start() {
        RKMLog.info("player: opening \(store.title) — \(store.itemID.prefix(8))", category: .app)
        installTimeObserver()
        Task {
            await store.load()
            // ⚠⚠ **THE AUTO-PICK'S HOOK, AND IT IS DELIBERATELY *AFTER* THE LOAD** (his decision,
            // 2026-09-21): `load()` is what reads the stored choice, and a subtitle the viewer already
            // chose must beat the rule — asking first would spend a download on a title that has one.
            // ⚠ The SERVER decides everything here (the switch, the language, the exclusions, the quota),
            // and a refusal is a 200 whose sentence the Subtitles pane draws. The film is never blocked.
            await store.runAutoPick()
        }
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

    /// ⚠⚠ **D2 — THE SCRUB ROW'S JOG, AND IT IS BOTH A STORE CHANGE AND A PLAYER SEEK.** The store's position
    /// moves first (so the bar, the tooltip and the elapsed readout redraw immediately), then the player is
    /// seeked to the position the store now holds — one function, so the two cannot disagree about where the
    /// playhead is. ⚠ The distance is NOT here: `PlaybackRules.jogSeconds` owns it, and the view passes a
    /// direction.
    private func jog(_ direction: Int) {
        store.jog(direction: direction)
        seekPlayer(to: store.position)
        lastInteraction = Date()
    }

    /// Close the drawer and **put the ring back where the hand was**.
    ///
    /// ⚠⚠ It is `.audio` — the headphone button that OPENED the drawer — and not `.play`: a control that
    /// returns focus to the far end of the transport after every visit makes re-opening the drawer a journey,
    /// and the platform's own sheets return focus to the control that presented them. ⚠ `drawerFocus` is
    /// cleared first, so the drawer's stale row index cannot be restored into a pane that has closed.
    private func closePanel() {
        store.closePanel()
        drawerFocus = nil
        focus = .audio
    }

    /// **What MENU does, in the ladder's order** — the rule is `PlaybackRules.menuTarget`, pinned in the
    /// harness; this is only the carrying out.
    ///
    /// ⚠⚠ **HIS REPORT, 2026-09-21: *"once the headphone icon is clicked and overlay opens how does the user
    /// comes out of it, the back button should close it automatically"*.** ⚠ The panel's own `onClose` closure
    /// was **never called by anything**, so the drawer had no exit of its own and MENU skipped straight to
    /// leaving the film — the one press a viewer is most likely to try, doing the most destructive thing
    /// available.
    ///
    /// ⚠ **AMENDMENT TO FALSIFIER P-F10** (*"MENU still leaves the player from every state"*): from an open
    /// drawer it now takes **two presses** — the first closes the drawer, the second leaves. From every other
    /// state one press still leaves, so the dead end that rule exists to close is still closed.
    private func handleExit() {
        switch PlaybackRules.menuTarget(panelOpen: store.panel != .none,
                                        upNextCardVisible: store.upNextSecondsLeft != nil) {
        case .panel:
            closePanel()
        case .upNextCard:
            // ⚠ A CANCEL, not a leave: the card is a countdown, and MENU is how a viewer says "not this one".
            // The ring goes back to the transport, which is where it was before the card appeared.
            store.cancelUpNext()
            focus = .play
        case .leave:
            leave()
        }
    }

    /// ⚠⚠ **P7 — UP NEXT'S HAND-OFF, AND THE ORDER IS THE WHOLE OF IT.** The current episode's position write
    /// is started FIRST (`finish()` is idempotent, so the `onDisappear` that is about to fire will not repeat
    /// it), and the next episode's screen is entered second. ⚠ `detail: nil` is deliberate: the new store
    /// refines its own facts from `GET /jellyfin/detail` on load, which is where the exact `resumeTicks` live —
    /// exactly the path the Home's hero already uses.
    private func handOff(to episode: EpisodeItem) {
        RKMLog.info("player: Up Next — opening \(episode.name) (\(episode.id.prefix(8)))", category: .app)
        let leaving = store
        app.openPlayer(itemID: episode.id,
                       detail: nil,
                       facts: PlaybackStore.PlaybackFacts.from(episode))
        Task { await leaving.finish() }
    }

    private func leave() {
        // ⚠ The position write is fired and awaited by the store's `finish()`; the SCREEN closes at once so a
        // slow network cannot trap a viewer on a black frame. ⚠ `finish()` is IDEMPOTENT (D6), so the
        // `onDisappear` that follows this does not send a second `stopped` report for the same exit.
        let leaving = store
        app.closePlayer()
        Task { await leaving.finish() }
    }

    // MARK: - Now Playing (⚠ P5 — a tvOS addition)

    /// ⚠⚠ **PUBLISHES WHAT IS PLAYING TO THE SYSTEM, WHICH IS WHAT THE TV's OWN SURFACES READ.**
    /// The system's "what's playing" panel, the Siri Remote's play/pause while this app is not frontmost, and
    /// *"Hey Siri, pause"* all come from `MPNowPlayingInfoCenter` — and a bare `AVPlayerLayer` (which is what
    /// this screen draws, on purpose) publishes **nothing** on its own. `AVPlayerViewController` would do this
    /// for free; this app does not use it, so it does it here.
    ///
    /// ⚠ It is called from the 0.5 s ticker, not from the time observer: elapsed time and rate have to stay
    /// right on a PAUSED film too, and `AVPlayer`'s periodic observer stops firing when playback stops.
    /// ⚠ Nothing here is a claim: `duration`, `elapsed` and `rate` are the player's own, and a value the
    /// player has not reported yet is simply left out rather than defaulted to zero.
    private func publishNowPlaying() {
        guard player.currentItem != nil else { return }
        var info: [String: Any] = [:]
        info[MPMediaItemPropertyTitle] = store.title
        if let series = store.seriesName { info[MPMediaItemPropertyAlbumTitle] = series }
        let elapsed = player.currentTime().seconds
        if elapsed.isFinite, elapsed >= 0 { info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = elapsed }
        let duration = player.currentItem?.duration.seconds ?? 0
        let total = duration.isFinite && duration > 0 ? duration : store.duration
        if total > 0 { info[MPMediaItemPropertyPlaybackDuration] = total }
        info[MPNowPlayingInfoPropertyPlaybackRate] = player.rate
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    // MARK: - Chrome visibility (the rule is `PlaybackRules`', the clock is this view's)

    private var chromeVisible: Bool {
        !PlaybackRules.shouldHideChrome(
            playing: store.isPlaying,
            switching: store.isSwitching,
            failed: store.hasFailed,
            hoveringChrome: false,
            // ⚠⚠ **BUG 2, AND THIS LINE IS HALF OF IT.** It used to pass
            // `store.panel != .none || isAnythingFocused || store.upNextSecondsLeft != nil` — and on a
            // television `isAnythingFocused` is **always true** (the focus engine puts a ring on something the
            // instant the screen opens), so the rule could never let the chrome go. It now asks
            // `PlaybackRules.chromePinned`, which is his own file's condition (`!settingsOpen && !infoOpen`)
            // plus the one mode the file does not have.
            panelOpen: PlaybackRules.chromePinned(panelOpen: store.panel != .none,
                                                  upNextCardVisible: store.upNextSecondsLeft != nil),
            idleSeconds: now.timeIntervalSince(lastInteraction))
    }

    /// ⚠⚠ **EVERY REMOTE INPUT RESTARTS THE CHROME'S CLOCK — AND THAT IS HIS FILE'S OWN RULE, VERBATIM.**
    /// `…player.html:721`: `document.addEventListener('keydown', (e)=>{ dismissHint(); resetIdle(); … })` —
    /// **every key**, whatever it does, and it is what makes the 4 s timer safe to have.
    ///
    /// ⚠⚠ **THE APP HAD NO EQUIVALENT AT ALL.** `lastInteraction` was written only by `togglePlay`, `skip`
    /// and `jog` — so a viewer who pressed Up, Down, Left or Right across the transport would not have touched
    /// it, and (once the `isAnythingFocused` bug stopped hiding the fault) the controls would have vanished
    /// while they were using them. Falsifier **P2-F2**.
    ///
    /// ⚠ The FOCUS changes are the reliable half — a directional press that moves the ring changes `focus`,
    /// and one that cannot (a press at the end of a row) is caught by the root's `onMoveCommand`. Between them
    /// no remote input can fail to restart the clock.
    private func noteInput() { lastInteraction = Date() }
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
