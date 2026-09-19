import SwiftUI

/// One card in the LIBRARY GRID — the prototype's `.card` from
/// `tvos_ux/2. LibraryViewandItemDetailsView/library-view.html`, **and it is a different card from the
/// Home's**, deliberately.
///
/// ```
/// ┌──────────────────┐
/// │                  │   2:3 POSTER — `.card { aspect-ratio: 2/3 }`, radius `14px`
/// │      ART         │
/// │                  │   at rest: ART ONLY. No caption, no badge, no bar.
/// │   ▓▓▓▓▓▓▓▓▓▓▓▓   │   on focus: `scale(1.14)`, a gold ring, the prototype's own double shadow,
/// │   River Wild     │             and THIS fades in over the art's lower edge —
/// │   2021 · 1h 52m  │             title `16px` w600, then `year · runtime` `13px` muted,
/// └──────────────────┘             over a bottom-up black scrim.
/// ```
///
/// ⚠⚠ **WHY IT IS NOT THE HOME'S `PosterCard`, AND WHY THAT IS STILL THE SPEC OBEYED.** His two design
/// inputs describe two different cards, and both are his:
///
///   * **set 1** (`1. UserProfileSelection_HomePage`) — 16:9 keyart at `19u`, **caption UNDER the art**, a
///     type badge, a state chip and a progress bar. That is `Home/PosterCard.swift` (U7, "the premium card"),
///     accepted on his simulator;
///   * **set 2** (`2. LibraryViewandItemDetailsView`) — **2:3 poster**, art only at rest, a label that fades
///     in OVER the art on focus.
///
/// `tvos-ux-principles.md` §8 calls the poster card *"the exact same component"* in the grid and on the
/// title screen — and it is, in this file. What is NOT shared is the ARTWORK PIPELINE, which is where a
/// second copy would become a second silent failure (`PosterCard.swift`'s own header): both cards draw
/// `PosterImageView` → `PosterLoader` → `PosterURL`, so there is one request, one log line, one fallback and
/// one "no photo" mark for the whole app.
///
/// ⚠⚠ **NOTHING IS ON A HOVER, AND NOTHING IS REVEALED BY A TIMER.** The web card's chips are hover-revealed;
/// a TV has no pointer, so the card is ONE `Button` — Select opens the title — and the caption's arrival is
/// driven **only** by focus (`@Environment(\.isFocused)`, the mechanism `TabButtonStyle` and the Profile
/// tile already use on this app, both of which have been on his screen). ⚠ No focus arithmetic is written
/// here: the ring, the lift and the reveal all read a published value, and the SCROLL is the platform's.
///
/// ⚠ The prototype's card also carries no badge, no state chip and no progress bar, because his file draws
/// none — recorded rather than "improved" (`docs/TVOS_LIBRARY_UI_PLAN.md` §3.2). A half-watched title in the
/// grid therefore looks like any other; the progress bar stays on the Home's rail card.
struct LibraryGridCard: View {

    let item: MediaItem
    let base: URL
    /// ⚠ **Passed IN, not computed here.** The card's width is the grid's arithmetic
    /// (`LibraryRules.cardWidth`, a RUNNABLE rule), and a card that measured itself would be a second copy of
    /// it — which is exactly how `TVTokens.Profile.rowWidthUnits` came to exist.
    let width: CGFloat
    let onSelect: (MediaItem) -> Void

    /// `.card { aspect-ratio: 2/3 }`.
    private var artHeight: CGFloat { width * TVTokens.Grid.cardAspect }

    private var meta: String { LibraryRules.cardMetaLine(item) }

    var body: some View {
        Button {
            onSelect(item)
        } label: {
            artwork
        }
        .buttonStyle(LibraryCardStyle())
        // ⚠ The caption is invisible until focus, so a screen reader would otherwise get nothing but an
        // image — the same rule the Home's card follows. The words are the ones the card DRAWS.
        .accessibilityLabel(accessibilityLabel)
    }

    /// ⚠ Every fact the card shows, in one sentence, built from the same rules the drawing uses.
    private var accessibilityLabel: String {
        [item.title, meta].filter { !$0.isEmpty }.joined(separator: ", ")
    }

    // MARK: - The art, and the label that fades in over its lower edge

    private var artwork: some View {
        PosterImageView(base: base, itemID: item.itemID)
            .frame(width: width, height: artHeight)
            .clipShape(RoundedRectangle(cornerRadius: TVTokens.Grid.cardRadius, style: .continuous))
            // ⚠ `.label { position:absolute; left:0; right:0; bottom:0 }` — the caption lives INSIDE the
            // card's bottom edge, over a `.label`-own `linear-gradient(to top, rgba(0,0,0,.85), transparent)`
            // scrim. That scrim travels WITH the label, so at rest the card really is art only.
            .overlay(alignment: .bottom) {
                LibraryCardReveal {
                    caption
                }
            }
    }

    private var caption: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(item.title)
                .font(.system(size: TVTokens.Grid.cardTitleSize, weight: .semibold))
                .foregroundStyle(RKMColour.primary)
                // ⚠ `.label .t { line-height: 1.25 }`, and **TWO lines** — the spec's own long-title rule
                // ("truncate to two lines with ellipsis in the focus label; never wrap the grid layout
                // itself"). A third line would push text out through the top of the scrim.
                .lineLimit(2)
                .multilineTextAlignment(.leading)

            if !meta.isEmpty {
                Text(meta)
                    .font(.system(size: TVTokens.Grid.cardMetaSize))
                    .foregroundStyle(RKMColour.muted)
                    .lineLimit(1)
                    .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, TVTokens.Grid.labelInsetTop)
        .padding(.horizontal, TVTokens.Grid.labelInsetH)
        .padding(.bottom, TVTokens.Grid.labelInsetBottom)
        // ⚠ `.background(_:in:)` and NOT `.background(_:)`: the two-argument form is the current API, the
        // single-view form has been deprecated since iOS 15, and this app builds against the tvOS 26 SDK.
        // ⚠ `.black` is deliberate — it is the prototype's own `rgba(0,0,0,.85)` scrim, not a brand colour,
        // and R3 of `check-design-tokens.py` leaves system colours alone.
        .background(
            LinearGradient(colors: [.clear, .black.opacity(0.85)], startPoint: .top, endPoint: .bottom),
            in: Rectangle()
        )
    }
}

/// The caption's own reveal — `.card .label { opacity:0; transform:translateY(6px) }` → `opacity:1 /
/// translateY(0)` on focus, at the prototype's own `200ms ease`.
///
/// ⚠⚠ **A separate view rather than a modifier on the caption, because `@Environment(\.isFocused)` is
/// INHERITED**: the value is published for the focused view and read by its descendants, which is the whole
/// mechanism. ⚠ And it is NOT named `Body` — every `Style`/`View` protocol declares that name as an
/// associatedtype, which is what U6's second Mac round died on (`check-tvos-members.py` rule 4).
private struct LibraryCardReveal<Content: View>: View {

    let content: Content
    @Environment(\.isFocused) private var isFocused

    /// ⚠ An explicit `@ViewBuilder` init rather than an attributed stored property (which does not compile):
    /// the caption is built by the caller and handed in whole.
    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
            .opacity(isFocused ? 1 : 0)
            .offset(y: isFocused ? 0 : TVTokens.Grid.labelRevealOffset)
            .animation(.easeOut(duration: 0.2), value: isFocused)
    }
}

/// The library card's focus treatment — the prototype's `.card.is-focused`.
///
/// ⚠⚠ **THE STYLE OWNS THE BOX.** `.card.is-focused` is `transform: scale(1.14)` plus
/// `box-shadow: 0 18px 30px rgba(0,0,0,.55), 0 0 0 3px var(--gold), 0 0 34px rgba(232,179,61,.45)` — a ring
/// that must sit around the ARTWORK, not around the caption inside it. That is the fault his screenshot
/// bought on the Home's `Details` button (a focus ring drawn around the word, inside the button's box), and
/// the fix then was structural: **take the box away from the caller**. The card's caller supplies only
/// `PosterImageView`, so the ring cannot land in the wrong place.
///
/// ⚠ The animation is the prototype's own curve for a card — `cubic-bezier(.34,1.56,.64,1)` at `260ms` — and
/// NOT a hand-rolled spring, for the reason `RailFocus` was deleted: his file states the motion, so there is
/// nothing to invent.
struct LibraryCardStyle: ButtonStyle {

    func makeBody(configuration: Configuration) -> some View {
        LibraryCardChrome(configuration: configuration)
    }

    /// ⚠ NOT `Body`: every `Style` protocol declares an associatedtype requirement called `Body`, so a helper
    /// view nested inside a conformer and named `Body` collides with it — measured on his Mac, U6's second
    /// round. `TileBody`/`TabChrome`/`IconChrome` are the same rule spelled the same way.
    private struct LibraryCardChrome: View {

        let configuration: ButtonStyle.Configuration
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .scaleEffect(isFocused ? TVTokens.Grid.cardFocusScale : 1)
                .shadow(color: .black.opacity(0.55),
                        radius: TVTokens.Grid.cardShadowRadius * 0.6,
                        y: TVTokens.Grid.cardShadowY)
                .overlay {
                    RoundedRectangle(cornerRadius: TVTokens.Grid.cardRadius, style: .continuous)
                        .stroke(RKMColour.accent,
                                lineWidth: isFocused ? TVTokens.Grid.cardFocusRing : 0)
                }
                // ⚠ The focus GLOW — the prototype's second shadow, `0 0 34px rgba(232,179,61,.45)` — drawn
                // only when focused, because a glow at rest would tint every card in the wall.
                .shadow(color: RKMColour.accent.opacity(isFocused ? 0.45 : 0),
                        radius: TVTokens.Grid.cardShadowRadius)
                .animation(.timingCurve(0.34, 1.56, 0.64, 1, duration: 0.26), value: isFocused)
        }
    }
}
