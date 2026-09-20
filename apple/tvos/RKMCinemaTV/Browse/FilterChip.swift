import SwiftUI

/// One chip in the Library screen's filter row — the prototype's `.chip`.
///
/// ⚠⚠ **THREE STATES, AND ONLY ONE OF THEM IS FOCUS.** `.chip` rests on `--surface` with `--text-dim`; the
/// SELECTED chip is gold with dark text (the spec's *"the one static, non-focus use of gold in this screen, so
/// the active filter stays legible even when focus has moved elsewhere"*); and the FOCUSED chip grows to
/// `1.08` inside a `--gold-bright` border. The point of the distinction is that a viewer who has moved focus
/// down into the grid can still see which genre is active — so a style that painted "selected" and "focused"
/// the same would lose the one thing the chip row is for.
///
/// ⚠ The `All` chip is the same control as every genre chip: it SELECTS the empty filter. `LibraryRules`
/// owns that mapping (`genre(forChip:)`), so a chip cannot come to mean "the genre literally called All".
struct FilterChip: View {

    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(title) { action() }
            .buttonStyle(ChipButtonStyle(isSelected: isSelected))
    }
}

/// The prototype's `.chip`, `.chip.selected` and `.chip.is-focused`, in one style.
///
/// ⚠⚠ **THE STYLE OWNS THE BOX** — padding, fill, border and radius all live here, so a caller supplies a
/// `String` and nothing else, and the border therefore lands around the pill rather than around its text.
/// That is the U7 structural fix (`CtaButtonStyle`/`PillButtonStyle` learnt it from his screenshot); a caller
/// that can only supply content cannot supply it in the wrong place.
struct ChipButtonStyle: ButtonStyle {

    let isSelected: Bool

    func makeBody(configuration: Configuration) -> some View {
        ChipChrome(configuration: configuration, isSelected: isSelected)
    }

    /// ⚠ NOT `Body`: every `Style` protocol declares an associatedtype requirement called `Body`, which is
    /// what U6's second Mac round died on. `TileBody`/`TabChrome`/`IconChrome`/`LibraryCardChrome` are the
    /// same rule spelled the same way, and `check-tvos-members.py` rule 4 is the gate for it.
    private struct ChipChrome: View {

        let configuration: ButtonStyle.Configuration
        let isSelected: Bool
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .font(.system(size: TVTokens.Grid.chipFontSize, weight: isSelected ? .semibold : .regular))
                .foregroundStyle(textColour)
                .lineLimit(1)
                .padding(.horizontal, TVTokens.Grid.chipPaddingH)
                .padding(.vertical, TVTokens.Grid.chipPaddingV)
                .background(
                    RoundedRectangle(cornerRadius: TVTokens.Grid.chipRadius, style: .continuous)
                        .fill(isSelected ? RKMColour.accent : RKMColour.surface2)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: TVTokens.Grid.chipRadius, style: .continuous)
                        .stroke(isFocused ? RKMColour.accentHover : Color.clear,
                                lineWidth: TVTokens.Grid.chipBorderWidth)
                )
                .scaleEffect(isFocused ? TVTokens.Grid.chipFocusScale : 1)
                // `.chip.is-focused { box-shadow: 0 6px 20px rgba(232,179,61,0.35) }` — the glow that makes a
                // focused chip lift off the row on a black screen.
                .shadow(color: RKMColour.accent.opacity(isFocused ? 0.35 : 0),
                        radius: TVTokens.Grid.chipGlowRadius,
                        y: TVTokens.Grid.chipGlowY)
                // ⚠ `transform 160ms cubic-bezier(.34,1.56,.64,1)` — the prototype's own curve, and SHORTER
                // than a poster's 260ms because a chip is a small thing answering a press.
                .animation(.timingCurve(0.34, 1.56, 0.64, 1, duration: 0.16), value: isFocused)
        }

        /// ⚠ `.chip { color: var(--text-dim) }`, `.chip.is-focused { color: var(--text) }`,
        /// `.chip.selected { color:#1a1204 }` — the dark text is the app's own near-black
        /// (`RKMColour.background`), the same pairing the top bar's focused tab already uses, rather than a
        /// second hand-typed hex.
        private var textColour: Color {
            if isSelected { return RKMColour.background }
            return isFocused ? RKMColour.primary : RKMColour.secondary
        }
    }
}
