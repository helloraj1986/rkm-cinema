import SwiftUI

// The player's chrome — the top bar, the scrubber, the transport row, the info panel, the caption strip and
// the toast. ⚠⚠ **TRANSCRIBED FROM HIS PROTOTYPE, METRIC BY METRIC** (`TVTokens.Player` names the line each
// number came from): `tvos_ux/3. MediaPlayerUx/rkm-cinema-tvos-player.html`. Three deliberate substitutions,
// each recorded rather than approximated:
//
//  1. **SF Symbols instead of his hand-drawn SVG glyphs.** His file carries inline `<svg><path>` icons
//     (a chevron, a speaker, two circular-arrow "±10s" marks, play/pause bars, an ⓘ). Those are the shapes a
//     tvOS app draws with the platform's own symbol set, which is also what the system's focus treatment is
//     designed around; a hand-traced path would be a second icon vocabulary in one app.
//  2. **The app's accent, not his `--gold`.** `#c9a227` is not the brand (`#ffc400`) — the third design input
//     in a row with a wrong gold, so the plan's palette table wins.
//  3. **No chapter ticks and no thumbnail preview** — neither exists on the wire (see `docs/TVOS_PLAYER_PLAN.md`
//     §7.3). The scrubber draws the time, which is real.

/// What can hold focus on the player. ⚠ **An enum rather than a `String`/`Int` index**, so a control cannot
/// exist without a case and a case cannot point at nothing; and ⚠⚠ **`.play` is the DEFAULT** — his prototype's
/// own decision (`let r = 2, i = 2; // default focus: play/pause`), which is the only part of its focus engine
/// this app takes (the maths itself is tvOS's).
///
/// ⚠⚠ **PHASE P ADDED THREE CASES, AND EACH ONE EXISTS BECAUSE ITS CONTROL IS THE ONLY WAY OUT OF A STATE:**
/// `noticeRetry` is the *Try again* on the failure notice (before it, a failed stream left NOTHING focusable
/// and MENU was the only key that did anything), and the two Up Next cases are the countdown's own controls —
/// the card counts down and acts on its own, so a viewer must be able to stop it and start it, and both by
/// focus alone.
enum PlayerFocus: Hashable {
    case back
    case scrubber
    case audio
    case back10
    case play
    case forward10
    case info
    /// ⚠ The failure notice's own control.
    case noticeRetry
    /// ⚠ The Up Next card's two controls.
    case upNextPlay
    case upNextCancel
}

/// What can hold focus in the settings drawer: its rail, or a row of the open pane.
enum DrawerFocus: Hashable {
    case category(PlaybackRules.SettingsCategory)
    case row(Int)
}

// MARK: - The top bar (`.topbar`)

/// `.topbar` — the way back, the film's name, the language/mode meta row and the clock.
///
/// ⚠⚠ **EVERY WORD IN THE META ROW IS DERIVED, NONE OF IT IS FIXED.** His file hardcodes
/// `Hindi · English, Hindi subtitles · Remux · HLS` for a specific film; here the languages come from the
/// tracks the SERVER sent and the badge from the mode the app actually chose (`PlaybackRules.languageLine` /
/// `badgeText`). A badge that said "Remux · HLS" over a direct play would be a claim the film itself
/// contradicts.
struct PlayerTopBar: View {

    @ObservedObject var store: PlaybackStore
    let focus: FocusState<PlayerFocus?>.Binding
    let onBack: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            HStack(alignment: .top, spacing: TVTokens.Player.backrowGap) {
                Button {
                    onBack()
                } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: TVTokens.Player.backGlyph, weight: .semibold))
                        .foregroundStyle(RKMColour.primary)
                }
                .buttonStyle(PlayerCircleButtonStyle(size: TVTokens.Player.backSize))
                .focused(focus, equals: .back)
                .accessibilityLabel(store.backLabel)

                VStack(alignment: .leading, spacing: TVTokens.Player.titleGap) {
                    // ⚠⚠ **P8 — THE SERIES' OWN NAME, ABOVE THE EPISODE'S.** Without it an episode's top bar
                    // reads `"Chapter 4"` and names nothing a viewer recognises; the name was already decoded
                    // in the same `ItemDetail` and this screen simply never read it. ⚠ It is drawn ONLY when
                    // there is one, so a film's bar is exactly the bar his round already accepted.
                    if let series = store.seriesName {
                        HStack(spacing: TVTokens.Player.metaGap) {
                            if let code = store.episodeCode {
                                Text(code)
                                    .font(.system(size: TVTokens.Player.eyebrowSize, weight: .bold))
                                    .foregroundStyle(RKMColour.accentHover)
                            }
                            Text(series)
                                .font(.system(size: TVTokens.Player.eyebrowSize, weight: .semibold))
                                .foregroundStyle(RKMColour.secondary)
                                .lineLimit(1)
                        }
                    }
                    Text(store.title)
                        .font(.system(size: TVTokens.Player.titleSize, weight: .medium, design: .serif))
                        .foregroundStyle(RKMColour.primary)
                        .lineLimit(2)
                    metaRow
                }
                .frame(maxWidth: TVTokens.Player.titleMaxWidth, alignment: .leading)
            }
            Spacer(minLength: 0)
            Text(store.clockText)
                .font(.system(size: TVTokens.Player.clockSize, weight: .semibold))
                .monospacedDigit()
                .foregroundStyle(RKMColour.secondary)
        }
        .padding(.horizontal, TVTokens.Player.barPaddingH)
        .padding(.top, TVTokens.Player.barPaddingTop)
        // ⚠⚠ **THE BAR IS ITS OWN SECTION, AND THE ORDER IS PART OF THE API** (`frame` THEN `focusSection`) —
        // his own round-12 confirmation of the title screen: a section is aimed at by its FRAME and *"has to
        // take up more space than its contents"*. Inside the frame it would be content-sized, which is exactly
        // the shape that failed there.
        .frame(maxWidth: .infinity, alignment: .leading)
        .focusSection()
    }

    /// The prototype's `.meta-row`: language · subtitles · the mode badge, small and quiet, with `·`
    /// separators drawn as dots so a viewer never mistakes one for punctuation in a language name.
    private var metaRow: some View {
        HStack(spacing: TVTokens.Player.metaGap) {
            let parts = store.metaParts
            ForEach(Array(parts.enumerated()), id: \.offset) { index, part in
                if index > 0 {
                    Circle()
                        .fill(RKMColour.muted)
                        .frame(width: TVTokens.Player.metaDot, height: TVTokens.Player.metaDot)
                }
                Text(part)
                    .font(.system(size: TVTokens.Player.metaSize, weight: .medium))
                    .foregroundStyle(RKMColour.secondary)
                    .lineLimit(1)
            }
            Text(store.modeBadge)
                .font(.system(size: TVTokens.Player.badgeSize, weight: .bold))
                .foregroundStyle(RKMColour.background)
                .padding(.horizontal, TVTokens.Player.badgePaddingH)
                .padding(.vertical, TVTokens.Player.badgePaddingV)
                .background(
                    RoundedRectangle(cornerRadius: TVTokens.Player.badgeRadius, style: .continuous)
                        .fill(RKMColour.accent)
                )
        }
    }
}

// MARK: - The scrubber (`.scrub-wrap`)

/// `.scrub-wrap` — the two times, the track, its fill, its playhead and the focused tooltip.
///
/// ⚠⚠ **THE WHOLE TRACK IS ONE FOCUSABLE CONTROL, AND THAT IS THE PROTOTYPE'S OWN MODEL** (its row 1 is the
/// track, and left/right JOG TIME BY 30 s rather than moving between elements). So when the track holds focus,
/// the app jogs the position itself — which is also why `PlaybackRules.jogTarget` exists.
///
/// ⚠⚠ **AND UNTIL PHASE P THE JOG WAS ONLY A COMMENT.** The `Button`'s action was empty, `onSeek` was never
/// called, and `jogSeconds` was read by no file in the project: a left/right press with the track focused fell
/// through to the focus engine, which found no neighbour to the right and did **nothing at all**. `onMoveCommand`
/// is what makes the row behave like the row his file draws.
struct PlayerScrubber: View {

    @ObservedObject var store: PlaybackStore
    let focus: FocusState<PlayerFocus?>.Binding
    /// ⚠⚠ **`onSeek` IS GONE, DELIBERATELY.** It was passed by the screen and never called: the prototype's
    /// row 1 does **nothing** on Enter (`if(r===2)` guards the transport verbs, and row 1 is not row 2). The
    /// track's only verbs are the jog, and a parameter nothing reads is the same class of dead code as
    /// `jogSeconds` was.
    /// ⚠ `-1`/`+1` — the direction, not a distance: the 30 s is `PlaybackRules.jogSeconds` and belongs in the
    /// rule, not in a call site.
    let onJog: (Int) -> Void

    var body: some View {
        VStack(spacing: TVTokens.Player.scrubTimesGap) {
            HStack {
                Text(store.elapsedLabel)
                Spacer(minLength: 0)
                Text(store.durationLabel)
            }
            .font(.system(size: TVTokens.Player.scrubTimesSize, weight: .medium))
            .monospacedDigit()
            .foregroundStyle(RKMColour.secondary)

            // ⚠ A `Button` only because that is how a tvOS view becomes FOCUSABLE at all — the track is the
            // prototype's focus row 1, and a press on it does what his own `Enter` on row 1 does: nothing.
            // Left/right JOG the position (`PlaybackRules.jogTarget`).
            Button {
            } label: {
                Color.clear.frame(height: TVTokens.Player.trackFocusHeight)
            }
            .buttonStyle(PlayerScrubStyle(fraction: store.progressFraction,
                                          previewLabel: store.elapsedLabel))
            .focused(focus, equals: .scrubber)
            // ⚠⚠ **ONLY LEFT AND RIGHT ARE CLAIMED.** Up and down are NOT handled here, so the focus engine
            // still moves the ring out of the row to the bar above and the transport below — a control that
            // swallowed all four directions would trap the viewer on the track.
            .onMoveCommand { direction in
                switch direction {
                case .left: onJog(-1)
                case .right: onJog(1)
                default: break
                }
            }
            .accessibilityLabel("Playback position")
            .accessibilityValue("\(store.elapsedLabel) of \(store.durationLabel)")
        }
        .padding(.top, TVTokens.Player.scrubTopPad)
    }

}

/// The track's own style, so the focus ring and the playhead are drawn **inside** the element that grows —
/// the U7/V lesson (`LibraryCardStyle`): a ring drawn on an unscaled label sits inside a card that has grown
/// past it, which is what his screenshot caught.
///
/// ⚠ It carries a `@FocusState` of its own rather than reading the screen's: the style is the only place that
/// knows whether THIS control is focused, and `@Environment(\.isFocused)` is not available to a `ButtonStyle`.
///
/// ⚠⚠ **THE TOOLTIP'S TIME IS PASSED IN, AND UNTIL PHASE P IT WAS THE LITERAL `fmtTime(0)`** — so the one
/// piece of the tooltip that carries information said `0:00` on every film, for every seek, forever. His
/// prototype writes the CURRENT time into it (`…html:518`: `tooltipTime.textContent = fmt(cur)`), which is
/// what the app now draws. ⚠ It is not the *target* time: the prototype jogs `cur` and then repaints, so the
/// tooltip and the elapsed readout above the bar are the same number by construction — and they still are,
/// because both come from `store.elapsedLabel`.
struct PlayerScrubStyle: ButtonStyle {

    let fraction: Double
    /// ⚠ `m:ss` / `h:mm:ss` — supplied by the caller so the style cannot invent one.
    let previewLabel: String

    func makeBody(configuration: Configuration) -> some View {
        ScrubChrome(configuration: configuration, fraction: fraction, previewLabel: previewLabel)
    }

    /// ⚠ NOT `Body` — every `Style` protocol declares an associatedtype requirement with that name, and
    /// `check-tvos-members.py` rule 4 refuses a nested `struct Body` (round 2's whole failure).
    private struct ScrubChrome: View {

        let configuration: ButtonStyle.Configuration
        let fraction: Double
        let previewLabel: String
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            ZStack(alignment: .leading) {
                GeometryReader { geometry in
                    let width = max(1, geometry.size.width)
                    // ⚠ The playhead's x, in ONE place: the fill's width, the playhead and the tooltip all
                    // read it, so a tooltip that drifted from the playhead under it is not a thing this
                    // screen can draw.
                    let head = width * fraction
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.white.opacity(0.16))
                        Capsule()
                            .fill(
                                LinearGradient(colors: [RKMColour.accent, RKMColour.accentHover],
                                               startPoint: .leading, endPoint: .trailing)
                            )
                            .frame(width: head)
                    }
                    .frame(height: isFocused ? TVTokens.Player.trackFocusHeight : TVTokens.Player.trackHeight)
                    .clipShape(Capsule())
                    .overlay(alignment: .leading) {
                        if isFocused {
                            Circle()
                                .fill(RKMColour.accentHover)
                                .frame(width: TVTokens.Player.playheadSize,
                                       height: TVTokens.Player.playheadSize)
                                .shadow(color: RKMColour.accent.opacity(TVTokens.Player.playheadRingOpacity),
                                        radius: TVTokens.Player.playheadRing)
                                .offset(x: head - TVTokens.Player.playheadSize / 2)
                        }
                    }
                    .overlay {
                        if isFocused {
                            Text(previewLabel)
                                .font(.system(size: TVTokens.Player.tooltipSize, weight: .bold))
                                .monospacedDigit()
                                .foregroundStyle(RKMColour.primary)
                                .fixedSize()
                                .padding(.horizontal, TVTokens.Player.tooltipPaddingH)
                                .padding(.vertical, TVTokens.Player.tooltipPaddingV)
                                .background(
                                    RoundedRectangle(cornerRadius: TVTokens.Player.tooltipRadius,
                                                     style: .continuous)
                                        .fill(RKMColour.background.opacity(0.86))
                                )
                                // ⚠⚠ **CENTRED ON THE PLAYHEAD, WHICH IS HIS `translate(-50%,-14px)`** — the
                                // old `offset(x: head)` hung the tooltip's LEFT edge on the playhead, so at the
                                // end of a film the whole label sat past the right edge of the screen.
                                .position(x: min(max(head, TVTokens.Player.tooltipPaddingH
                                                     + TVTokens.Player.tooltipSize),
                                                 width - TVTokens.Player.tooltipPaddingH
                                                     - TVTokens.Player.tooltipSize),
                                          y: -TVTokens.Player.tooltipLift)
                        }
                    }
                }
            }
            .frame(height: TVTokens.Player.trackFocusHeight)
            .animation(.timingCurve(0.22, 0.61, 0.36, 1, duration: 0.18), value: isFocused)
        }
    }
}

// MARK: - The transport row (`.controls`)

/// `.controls` — his five controls, each of which the store can actually honour:
/// Audio & Subtitles opens the drawer, ±10 s seeks (`PlaybackRules.skipSeconds`), Play/Pause is primary, and
/// Info opens the synopsis. ⚠ The row's ORDER and the SPACER's position are his.
struct PlayerControlsRow: View {

    @ObservedObject var store: PlaybackStore
    let focus: FocusState<PlayerFocus?>.Binding
    let onTogglePlay: () -> Void
    let onSkip: (Double) -> Void

    var body: some View {
        HStack(spacing: TVTokens.Player.controlGap) {
            control(.audio, glyph: "speaker.wave.2.fill", label: "Audio & Subtitles", primary: false) {
                store.openSettings()
            }
            control(.back10, glyph: "gobackward.10", label: "Back 10s", primary: false) {
                onSkip(-PlaybackRules.skipSeconds)
            }
            control(.play,
                    glyph: store.isPlaying ? "pause.fill" : "play.fill",
                    label: store.isPlaying ? "Pause" : "Play",
                    primary: true) {
                onTogglePlay()
            }
            control(.forward10, glyph: "goforward.10", label: "Forward 10s", primary: false) {
                onSkip(PlaybackRules.skipSeconds)
            }
            // ⚠ `.ctl-spacer { width:1.4em }` — the gap that pushes Info to the far end, transcribed rather
            // than replaced with a `Spacer()`, because the prototype's gap is a size and not a flex.
            Color.clear.frame(width: TVTokens.Player.controlSpacer, height: 1)
            control(.info, glyph: "info.circle", label: "Info", primary: false) {
                store.toggleInfo()
            }
        }
        // ⚠⚠ **THE TRANSPORT ROW IS ITS OWN SECTION — the same fix his round-12 confirmation bought on the
        // title screen** (`KNOWN_ISSUES` #15): a section is aimed at by its frame and *"has to take up more
        // space than its contents"*, so `.focusSection()` must come AFTER the `.frame(…)`. Without it the row's
        // section was content-sized around the five buttons, and a `Down` press from the track — or an `Up`
        // from a button — has no section to land in.
        .frame(maxWidth: .infinity, alignment: .leading)
        .focusSection()
    }

    private func control(_ slot: PlayerFocus, glyph: String, label: String, primary: Bool,
                         action: @escaping () -> Void) -> some View {
        Button {
            action()
        } label: {
            Image(systemName: glyph)
                .font(.system(size: primary ? TVTokens.Player.controlPrimaryGlyph
                                            : TVTokens.Player.controlGlyph,
                              weight: .semibold))
        }
        .buttonStyle(PlayerControlButtonStyle(primary: primary, label: label))
        .focused(focus, equals: slot)
        .accessibilityLabel(label)
    }
}

/// `.ctl-btn` / `.ctl-btn.primary` / `.ctl-btn.is-focused` — **and the style owns the whole box**, which is the
/// U7 structural fix: a caller supplies a glyph and a label and cannot put the ring in the wrong place,
/// because the ring, the fill, the padding and the lift are all drawn here.
struct PlayerControlButtonStyle: ButtonStyle {

    let primary: Bool
    let label: String

    func makeBody(configuration: Configuration) -> some View {
        ControlChrome(configuration: configuration, primary: primary, label: label)
    }

    private struct ControlChrome: View {

        let configuration: ButtonStyle.Configuration
        let primary: Bool
        let label: String
        @Environment(\.isFocused) private var isFocused
        /// ⚠⚠ **P3 — THE ONE ACCESSIBILITY AFFORDANCE HIS PROTOTYPE ACTUALLY NAMES**
        /// (`--focus-scale` is disabled under `prefers-reduced-motion`, spec §"Accessibility & robustness"),
        /// and until Phase P the app animated the focus lift unconditionally. ⚠ The RING, the FILL and the
        /// label still change on focus in every case — reduced motion removes the MOVEMENT, never the
        /// affordance: a viewer with it on must still be able to see where the ring is.
        @Environment(\.accessibilityReduceMotion) private var reduceMotion

        private var diameter: CGFloat {
            primary ? TVTokens.Player.controlPrimarySize : TVTokens.Player.controlSize
        }

        var body: some View {
            configuration.label
                .foregroundStyle(primary ? RKMColour.background : RKMColour.primary)
                .frame(width: diameter, height: diameter)
                .background(
                    Circle().fill(fill)
                )
                .overlay(
                    Circle().stroke(isFocused ? RKMColour.accentHover : Color.clear,
                                    lineWidth: TVTokens.Player.focusRingWidth)
                )
                .overlay(alignment: .top) {
                    // `.ctl-label` — the name of the control, shown only while it is focused, lifted above it.
                    if isFocused {
                        Text(label)
                            .font(.system(size: TVTokens.Player.controlLabelSize, weight: .semibold))
                            .foregroundStyle(RKMColour.primary)
                            .fixedSize()
                            .offset(y: -TVTokens.Player.controlLabelLift)
                    }
                }
                .scaleEffect(isFocused && !reduceMotion ? TVTokens.Player.focusScale : 1)
                .shadow(color: isFocused ? RKMColour.accent.opacity(0.9) : .clear, radius: 0)
                .animation(reduceMotion ? nil : .timingCurve(0.34, 1.56, 0.64, 1, duration: 0.3),
                           value: isFocused)
        }

        /// `.ctl-btn { background:var(--glass) }` at rest; on focus his rule is `rgba(28,28,30,.92)`, and the
        /// PRIMARY button is the near-white one in both states (`#fff` when focused).
        private var fill: Color {
            if primary {
                return isFocused ? .white : Color.white.opacity(TVTokens.Player.primaryFillOpacity)
            }
            return isFocused ? Color(white: 0.11).opacity(0.92)
                             : RKMColour.background.opacity(0.66)
        }
    }
}

/// `.backbtn` — the circle that takes you out, sharing the transport's ring but not its size.
struct PlayerCircleButtonStyle: ButtonStyle {

    let size: CGFloat

    func makeBody(configuration: Configuration) -> some View {
        CircleChrome(configuration: configuration, size: size)
    }

    private struct CircleChrome: View {

        let configuration: ButtonStyle.Configuration
        let size: CGFloat
        @Environment(\.isFocused) private var isFocused
        /// ⚠ P3 — the same reduced-motion rule as the transport's controls (see `ControlChrome`).
        @Environment(\.accessibilityReduceMotion) private var reduceMotion

        var body: some View {
            configuration.label
                .frame(width: size, height: size)
                .background(Circle().fill(RKMColour.background.opacity(0.66)))
                .overlay(
                    Circle().stroke(isFocused ? RKMColour.accentHover : Color.white.opacity(0.09),
                                    lineWidth: TVTokens.Player.focusRingWidth)
                )
                .scaleEffect(isFocused && !reduceMotion ? TVTokens.Player.focusScale : 1)
                .animation(reduceMotion ? nil : .timingCurve(0.34, 1.56, 0.64, 1, duration: 0.28),
                           value: isFocused)
        }
    }
}

// MARK: - The info panel (`.info-panel`)

/// `.info-panel` — the synopsis, over a scrim, with the film's own tags above it.
///
/// ⚠ His file's tags (`1975 · Action · Drama · 3h 24m · Part 1 of 2`) are hardcoded; here every tag is a real
/// field (`ItemDetail`), and a field the server did not send is simply absent rather than blank.
struct PlayerInfoPanel: View {

    @ObservedObject var store: PlaybackStore

    var body: some View {
        VStack(alignment: .leading, spacing: TVTokens.Player.infoGap) {
            if !store.infoTags.isEmpty {
                HStack(spacing: TVTokens.Player.tagGap) {
                    ForEach(Array(store.infoTags.enumerated()), id: \.offset) { _, tag in
                        Text(tag)
                            .font(.system(size: TVTokens.Player.tagSize, weight: .medium))
                            .foregroundStyle(RKMColour.muted)
                            .padding(.horizontal, TVTokens.Player.tagPaddingH)
                            .padding(.vertical, TVTokens.Player.tagPaddingV)
                            .overlay(
                                RoundedRectangle(cornerRadius: TVTokens.Player.tagRadius, style: .continuous)
                                    .stroke(Color.white.opacity(0.09), lineWidth: 1)
                            )
                    }
                }
            }
            if let overview = store.overview {
                Text(overview)
                    .font(.system(size: TVTokens.Player.infoBodySize))
                    .lineSpacing(TVTokens.Player.infoBodyLineSpacing)
                    .foregroundStyle(RKMColour.secondary)
                    .frame(maxWidth: TVTokens.Player.infoMeasure, alignment: .leading)
            } else {
                Text("No synopsis for this title.")
                    .font(.system(size: TVTokens.Player.infoBodySize))
                    .foregroundStyle(RKMColour.muted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, TVTokens.Player.barPaddingH)
        .padding(.bottom, TVTokens.Player.infoPaddingBottom)
        // `.info-panel`'s own gradient: transparent at its top edge, near-black at the bottom, so the text
        // sits on a surface that is always dark enough to read.
        .background(
            LinearGradient(colors: [.clear, RKMColour.background.opacity(0.94), RKMColour.background],
                           startPoint: .top, endPoint: .bottom)
        )
    }
}

// MARK: - The stall, the failure notice, and Up Next (⚠ all three are tvOS additions — Phase P)

/// ⚠⚠ **P2 — A STALL THAT SAYS SO.** `isSwitching` is the player's own `timeControlStatus ==
/// .waitingToPlayAtSpecifiedRate`, and before Phase P it was read by exactly one rule (the chrome's hide
/// condition) — so a transcode that stalled showed a **frozen frame with no explanation at all**, which on a
/// television is indistinguishable from a crashed app.
///
/// ⚠ It is deliberately the PLATFORM's spinner at `.controlSize(.large)`: a hand-drawn one would be a second
/// vocabulary, and the app already draws its own chrome everywhere else.
struct PlayerStallIndicator: View {

    var body: some View {
        VStack(spacing: TVTokens.Player.noticeGap) {
            ProgressView()
                .controlSize(.large)
            Text("Buffering…")
                .font(.system(size: TVTokens.Player.upNextBodySize, weight: .medium))
                .foregroundStyle(RKMColour.secondary)
        }
        .padding(TVTokens.Player.noticePadding * 0.6)
        .background(
            RoundedRectangle(cornerRadius: TVTokens.Player.noticeRadius, style: .continuous)
                .fill(RKMColour.background.opacity(0.72))
        )
        .allowsHitTesting(false)
    }
}

/// ⚠⚠ **P1 — THE FAILURE NOTICE, AND UNTIL PHASE P IT HAD NOTHING ON IT THAT COULD BE PRESSED.**
///
/// The old notice was two `Text`s. On a television the only input is the remote, so a screen whose one
/// actionable answer is "try that again" had no way to say it: the viewer's only key was MENU, and the app
/// never said so either. `ARCHITECTURE.md` ranks a dead end above any cosmetic rule — and this is the state a
/// viewer reaches exactly when something has already gone wrong.
///
/// ⚠ **`Try again` is `store.retryPlayback()`**, which climbs the mode ladder when there is a rung left and
/// otherwise re-requests the same URL (see its own comment). It is not a "reload the screen" button: the
/// screen's state — the position, the tracks, the drawer — is intact and only the stream failed.
struct PlayerFailureNotice: View {

    @ObservedObject var store: PlaybackStore
    let focus: FocusState<PlayerFocus?>.Binding
    let onRetry: () -> Void

    var body: some View {
        VStack(spacing: TVTokens.Player.noticeGap) {
            Text(store.failureSentence ?? "")
                .font(.system(size: TVTokens.Player.infoBodySize, weight: .semibold))
                .multilineTextAlignment(.center)
                .foregroundStyle(RKMColour.primary)
                .frame(maxWidth: TVTokens.Player.noticeMeasure)
                .fixedSize(horizontal: false, vertical: true)

            // ⚠ How hard the app already tried, in the ladder's own numbers. It appears only after an
            // escalation has actually happened, so a first-attempt failure does not read as a list of failures.
            if store.escalationAttempt > 0 {
                Text("Tried \(store.escalationAttempt) of \(PlaybackRules.ladderLength) streaming modes.")
                    .font(.system(size: TVTokens.Player.upNextBodySize))
                    .foregroundStyle(RKMColour.muted)
            }

            Button {
                onRetry()
            } label: {
                Text("Try again")
                    .font(.system(size: TVTokens.Player.upNextTitleSize, weight: .semibold))
            }
            .buttonStyle(PlayerNoticeButtonStyle(isPrimary: true))
            .focused(focus, equals: .noticeRetry)
            .accessibilityLabel("Try again")

            Text("Or press Menu to go back.")
                .font(.system(size: TVTokens.Player.upNextBodySize))
                .foregroundStyle(RKMColour.muted)
        }
        .padding(TVTokens.Player.noticePadding)
        .background(
            RoundedRectangle(cornerRadius: TVTokens.Player.noticeRadius, style: .continuous)
                .fill(RKMColour.background.opacity(0.92))
        )
        .overlay(
            RoundedRectangle(cornerRadius: TVTokens.Player.noticeRadius, style: .continuous)
                .stroke(Color.white.opacity(0.09), lineWidth: 1)
        )
        // ⚠⚠ A section, so the ring can BE moved onto the notice's control from wherever it was — the same
        // rule and the same order (`frame` then `focusSection`) as the bar and the transport row.
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .focusSection()
    }
}

/// The notice's button — the drawer's `.seg-btn`/primary treatment, so the app has one button vocabulary.
struct PlayerNoticeButtonStyle: ButtonStyle {

    let isPrimary: Bool

    func makeBody(configuration: Configuration) -> some View {
        NoticeChrome(configuration: configuration, isPrimary: isPrimary)
    }

    private struct NoticeChrome: View {

        let configuration: ButtonStyle.Configuration
        let isPrimary: Bool
        @Environment(\.isFocused) private var isFocused
        @Environment(\.accessibilityReduceMotion) private var reduceMotion

        var body: some View {
            configuration.label
                .foregroundStyle(isPrimary ? RKMColour.background : RKMColour.primary)
                .padding(.horizontal, TVTokens.Player.noticeButtonPaddingH)
                .padding(.vertical, TVTokens.Player.noticeButtonPaddingV)
                .background(
                    RoundedRectangle(cornerRadius: TVTokens.Player.noticeButtonRadius, style: .continuous)
                        .fill(isPrimary ? (isFocused ? RKMColour.accentHover : RKMColour.accent)
                                        : Color.white.opacity(0.1))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: TVTokens.Player.noticeButtonRadius, style: .continuous)
                        .stroke(isFocused ? RKMColour.accentHover : Color.clear,
                                lineWidth: TVTokens.Player.focusRingWidth)
                )
                .scaleEffect(isFocused && !reduceMotion ? TVTokens.Player.segFocusScale : 1)
                .animation(reduceMotion ? nil : .timingCurve(0.34, 1.56, 0.64, 1, duration: 0.22),
                           value: isFocused)
        }
    }
}

/// ⚠⚠ **P7 — UP NEXT: THE ONE THING THAT SEPARATES A PLAYER FROM A TV APP FOR SERIES VIEWING.**
///
/// Everything about WHEN this appears is `PlaybackStore.tickUpNext()`'s (the server's own 0.95 finish
/// fraction, the countdown, the hand-off); this view draws the card and owns nothing but its layout and its
/// two controls.
///
/// ⚠⚠ **TWO CONTROLS AND NOT ONE, DELIBERATELY.** The card starts something by itself, so a viewer must be
/// able to stop it — and a card that only offered *Play now* would leave *Cancel* to the MENU key, i.e. to
/// leaving the episode entirely. ⚠ Focus lands on *Play now* when it appears (the platform's own behaviour,
/// and the only sane default on a control that expires), which the screen does — not this view.
struct PlayerUpNextCard: View {

    @ObservedObject var store: PlaybackStore
    let focus: FocusState<PlayerFocus?>.Binding
    /// ⚠ The origin the episode's own still is fetched from — the screen's own address, which is what every
    /// playback URL is already built against.
    let base: URL
    let onPlayNow: () -> Void
    let onCancel: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: TVTokens.Player.upNextGap) {
            Text("Up next")
                .font(.system(size: TVTokens.Player.upNextEyebrowSize, weight: .bold))
                .foregroundStyle(RKMColour.accentHover)

            HStack(alignment: .top, spacing: TVTokens.Player.upNextGap) {
                if let next = store.nextEpisode {
                    // ⚠ THE APP'S ONE ARTWORK PATH, not a second loader: an episode's still rides the same
                    // poster route with the episode's own id, so the cookie handling, the log line and the
                    // fallback are the ones every other screen already uses.
                    PosterImageView(base: base, itemID: next.id, route: .backdrop)
                        .frame(width: TVTokens.Player.upNextThumbWidth,
                               height: TVTokens.Player.upNextThumbHeight)
                        .clipShape(RoundedRectangle(cornerRadius: TVTokens.Player.upNextThumbRadius,
                                                    style: .continuous))
                }
                VStack(alignment: .leading, spacing: TVTokens.Player.upNextGap * 0.4) {
                    if let label = store.upNextLabel {
                        Text(label)
                            .font(.system(size: TVTokens.Player.upNextTitleSize, weight: .semibold))
                            .foregroundStyle(RKMColour.primary)
                            .lineLimit(2)
                    }
                    if let countdown = store.upNextCountdownLabel {
                        Text(countdown)
                            .font(.system(size: TVTokens.Player.upNextBodySize))
                            .monospacedDigit()
                            .foregroundStyle(RKMColour.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            HStack(spacing: TVTokens.Player.upNextButtonGap) {
                Button {
                    onPlayNow()
                } label: {
                    Text("Play now")
                        .font(.system(size: TVTokens.Player.upNextTitleSize, weight: .semibold))
                }
                .buttonStyle(PlayerNoticeButtonStyle(isPrimary: true))
                .focused(focus, equals: .upNextPlay)
                .accessibilityLabel("Play the next episode now")

                Button {
                    onCancel()
                } label: {
                    Text("Cancel")
                        .font(.system(size: TVTokens.Player.upNextTitleSize, weight: .semibold))
                }
                .buttonStyle(PlayerNoticeButtonStyle(isPrimary: false))
                .focused(focus, equals: .upNextCancel)
                .accessibilityLabel("Stay on this episode")
            }
        }
        .frame(width: TVTokens.Player.upNextWidth, alignment: .leading)
        .padding(TVTokens.Player.upNextPadding)
        .background(
            RoundedRectangle(cornerRadius: TVTokens.Player.upNextRadius, style: .continuous)
                .fill(RKMColour.background.opacity(0.92))
        )
        .overlay(
            RoundedRectangle(cornerRadius: TVTokens.Player.upNextRadius, style: .continuous)
                .stroke(Color.white.opacity(0.09), lineWidth: 1)
        )
        // ⚠ A section of its own, so the two buttons are aimed at by the CARD's frame rather than by each
        // button's own — the round-12 rule, and the reason the card is `u * 40` wide for two small controls.
        .focusSection()
    }
}

// MARK: - The caption strip (⚠ a tvOS addition) and the toast
/// The chosen subtitle's active cue, drawn over the film.
///
/// ⚠⚠ **THIS IS NOT A TRANSCRIPTION — his file has no caption strip.** The app draws it because the api hands
/// over an external WebVTT stream per chosen track and `AVPlayer`'s own legible-media selection works on what
/// the HLS playlist declares instead (`Core/PlaybackAPI.swift::subtitleText` records the choice). The numbers
/// are the app's, and the position is above the transport so the two never overlap.
struct PlayerCueStrip: View {

    let text: String?

    var body: some View {
        Group {
            if let text, !text.isEmpty {
                Text(text)
                    .font(.system(size: TVTokens.Player.cueSize, weight: .semibold))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(RKMColour.primary)
                    .shadow(color: .black.opacity(0.85), radius: 6, y: 1)
                    .frame(maxWidth: TVTokens.Player.cueMeasure)
                    .padding(.horizontal, TVTokens.Player.toastPaddingH)
            }
        }
    }
}

/// `.toast` — the feedback line at the bottom of the frame.
struct PlayerToast: View {

    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: TVTokens.Player.toastSize, weight: .semibold))
            .foregroundStyle(RKMColour.primary)
            .padding(.horizontal, TVTokens.Player.toastPaddingH)
            .padding(.vertical, TVTokens.Player.toastPaddingV)
            .background(
                RoundedRectangle(cornerRadius: TVTokens.Player.toastRadius, style: .continuous)
                    .fill(RKMColour.background.opacity(0.86))
            )
            .overlay(
                RoundedRectangle(cornerRadius: TVTokens.Player.toastRadius, style: .continuous)
                    .stroke(Color.white.opacity(0.09), lineWidth: 1)
            )
    }
}
