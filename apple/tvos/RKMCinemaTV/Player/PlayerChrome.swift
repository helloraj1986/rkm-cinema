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
enum PlayerFocus: Hashable {
    case back
    case scrubber
    case audio
    case back10
    case play
    case forward10
    case info
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
/// the app jogs the position itself — which is also why `PlaybackRules.jogSeconds` exists.
struct PlayerScrubber: View {

    @ObservedObject var store: PlaybackStore
    let focus: FocusState<PlayerFocus?>.Binding
    let onSeek: (Double) -> Void

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
            // Left/right JOG the position (`PlaybackRules.jogSeconds`), which the screen wires up.
            Button {
            } label: {
                Color.clear.frame(height: TVTokens.Player.trackFocusHeight)
            }
            .buttonStyle(PlayerScrubStyle(fraction: store.progressFraction))
            .focused(focus, equals: .scrubber)
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
struct PlayerScrubStyle: ButtonStyle {

    let fraction: Double

    func makeBody(configuration: Configuration) -> some View {
        ScrubChrome(configuration: configuration, fraction: fraction)
    }

    /// ⚠ NOT `Body` — every `Style` protocol declares an associatedtype requirement with that name, and
    /// `check-tvos-members.py` rule 4 refuses a nested `struct Body` (round 2's whole failure).
    private struct ScrubChrome: View {

        let configuration: ButtonStyle.Configuration
        let fraction: Double
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            ZStack(alignment: .leading) {
                GeometryReader { geometry in
                    let width = max(1, geometry.size.width)
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.white.opacity(0.16))
                        Capsule()
                            .fill(
                                LinearGradient(colors: [RKMColour.accent, RKMColour.accentHover],
                                               startPoint: .leading, endPoint: .trailing)
                            )
                            .frame(width: width * fraction)
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
                                .offset(x: width * fraction - TVTokens.Player.playheadSize / 2)
                        }
                    }
                    .overlay(alignment: .topLeading) {
                        if isFocused {
                            Text(PlaybackRules.fmtTime(0))
                                .font(.system(size: TVTokens.Player.tooltipSize, weight: .bold))
                                .monospacedDigit()
                                .foregroundStyle(RKMColour.primary)
                                .padding(.horizontal, TVTokens.Player.tooltipPaddingH)
                                .padding(.vertical, TVTokens.Player.tooltipPaddingV)
                                .background(
                                    RoundedRectangle(cornerRadius: TVTokens.Player.tooltipRadius,
                                                     style: .continuous)
                                        .fill(RKMColour.background.opacity(0.86))
                                )
                                .offset(x: width * fraction, y: -TVTokens.Player.tooltipLift)
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
                .scaleEffect(isFocused ? TVTokens.Player.focusScale : 1)
                .shadow(color: isFocused ? RKMColour.accent.opacity(0.9) : .clear, radius: 0)
                .animation(.timingCurve(0.34, 1.56, 0.64, 1, duration: 0.3), value: isFocused)
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

        var body: some View {
            configuration.label
                .frame(width: size, height: size)
                .background(Circle().fill(RKMColour.background.opacity(0.66)))
                .overlay(
                    Circle().stroke(isFocused ? RKMColour.accentHover : Color.white.opacity(0.09),
                                    lineWidth: TVTokens.Player.focusRingWidth)
                )
                .scaleEffect(isFocused ? TVTokens.Player.focusScale : 1)
                .animation(.timingCurve(0.34, 1.56, 0.64, 1, duration: 0.28), value: isFocused)
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
