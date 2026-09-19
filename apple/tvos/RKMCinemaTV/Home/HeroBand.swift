import SwiftUI

/// The Home's hero band — the prototype's `.hero`.
///
/// ⚠⚠ **EVERY WORD AND EVERY NUMBER IN IT IS A RULE**, and since U6 the geometry is the prototype's own:
/// height `32u`, padding `3u / 4.2u`, eyebrow `1u` gold bold, title `3.6u` at weight 800 capped at 60 % of
/// the width, meta `1.05u`, progress `26u × 0.35u` with a gold fill, and a gold primary button beside a
/// 12 %-white secondary. ⚠ The copy is bottom-aligned (`justify-content:flex-end`), which is what makes the
/// band read as a poster with its caption rather than a banner with a title in the middle.
///
/// ⚠ The WORDS and NUMBERS inside the copy are `HomeRails.swift`'s rules, mirrored from the web app
/// (`lib.ts::heroEyebrow`, `::heroPrimaryLabel`, `::heroMetaLine`, `::resumePercent`, and the meta/title
/// assembly in `LibraryHomeView.tsx`'s `HomeHero`) — the eyebrow, the verb, the meta line, the percentage and
/// the countdown are all already values by the time they arrive, which is what makes them checkable on Linux.
///
/// ⚠⚠ **THE PRIMARY BUTTON DOES NOT PLAY, AND THAT IS THE HONEST VERSION OF IT.** The tvOS player is Phase C
/// and C1 alone is built, so a `Resume` button that started a film would be a promise the app cannot keep
/// (`docs/ARCHITECTURE.md` §11). Two precedents settle what happens instead:
///   * **a SERIES' primary goes to its DETAIL screen**, exactly as the web's does — its label is
///     `"Explore Episodes"`, because a series is explored rather than played. That is a real destination and
///     it works today;
///   * **anything else's primary shows the Playback placeholder** the detail screen already shows
///     (`DetailCopy.playPendingTitle/playPendingSub`), and the screen names the verb it WILL offer
///     (`DetailCopy.nextUp`). ⚠ The same two sentences as B4, deliberately: a second "playback arrives later"
///     wording is a second vocabulary for one fact.
struct HeroBand: View {

    let item: MediaItem
    /// Whether this title came from Continue Watching — the eyebrow's only input.
    let isContinueWatching: Bool
    let base: URL
    /// The primary button was pressed. ⚠ For a series this is never called (the view routes it to `onDetails`).
    let onPrimary: () -> Void
    let onDetails: () -> Void

    private var isSeries: Bool { HomeRules.isSeries(item) }
    private var isEpisode: Bool { HomeRules.isEpisodeItem(item) }
    private var percent: Int { HomeRules.heroPercent(item) }
    private var runtimeLeft: String { HomeRules.heroRuntimeLeft(item) }

    private var primaryLabel: String {
        HomeRules.heroPrimaryLabel(isEpisode: isEpisode,
                                   episodeCode: HomeRules.episodeItemCode(item) ?? "",
                                   isSeries: isSeries,
                                   percent: percent)
    }

    /// ⚠ The web's `primaryGoesToPage`: a series' primary opens the item (its episode list), so it does not
    /// get a separate `Details` button — two controls doing the same thing is worse than one.
    private var primaryOpensTheItem: Bool { isSeries }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            artwork
            gradients
            copy
        }
        .frame(height: TVTokens.Hero.height)
        .frame(maxWidth: .infinity)
        .clipped()
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Continue watching \(HomeRules.heroTitle(item))")
    }

    // MARK: - The picture

    /// ⚠ **The 16:9 BACKDROP, through `PosterImageView` — one artwork path for the whole app.** It is the same
    /// loader the cards use (same cookie handling, same log line, same "no photo" mark on failure, and the same
    /// poster fallback), so a hero whose artwork failed says why rather than showing a black band.
    ///
    /// ⚠ The prototype paints this band with a drifting two-tone gradient because a mockup has no library
    /// behind it. Real keyart is strictly better, so the artwork is the source and the prototype's own
    /// gradient is kept only as the fallback underneath it.
    private var artwork: some View {
        ZStack {
            Self.fallbackWash
            PosterImageView(base: base, itemID: item.itemID, route: .backdrop)
        }
        .frame(maxWidth: .infinity)
        .frame(height: TVTokens.Hero.height)
        .clipped()
    }

    /// The prototype's hero background as a static wash, for the moment before (or instead of) artwork.
    private static var fallbackWash: some View {
        LinearGradient(colors: [RKMColour.surface2, RKMColour.background],
                       startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    /// The bands that make the copy readable, built from the app's own `--bg` token rather than a hex: the
    /// prototype stacks three gradients (`0deg` bottom-first, plus a top darkening); these are those two jobs,
    /// and the bottom-fade is the one that carries the title.
    private var gradients: some View {
        ZStack {
            LinearGradient(colors: [RKMColour.background.opacity(0.9), .clear],
                           startPoint: .leading, endPoint: .trailing)
            LinearGradient(colors: [RKMColour.background.opacity(0.15), RKMColour.background],
                           startPoint: .center, endPoint: .bottom)
        }
        .allowsHitTesting(false)
    }

    // MARK: - The copy

    private var copy: some View {
        VStack(alignment: .leading, spacing: 0) {
            // ⚠ UPPERCASED HERE, NOT IN THE RULE: the string is the app's, the presentation is the
            // prototype's (`.hero-eyebrow` is a bold gold line). Uppercasing inside the rule would change what
            // every other consumer reads.
            Text(HomeRules.heroEyebrow(continueWatching: isContinueWatching, isEpisode: isEpisode).uppercased())
                .font(.system(size: TVTokens.Hero.eyebrowSize, weight: .bold))
                .foregroundStyle(RKMColour.accent)
                .padding(.bottom, TVTokens.Hero.eyebrowSize * 0.5)

            Text(HomeRules.heroTitle(item))
                .font(.system(size: TVTokens.Hero.titleSize, weight: .heavy))
                .foregroundStyle(RKMColour.primary)
                .lineLimit(2)
                .frame(maxWidth: TVTokens.Hero.titleMaxWidth, alignment: .leading)
                .padding(.bottom, TVTokens.Hero.titleSize * 0.17)

            let meta = HomeRules.heroMetaLine(item)
            if !meta.isEmpty {
                Text(meta)
                    .font(.system(size: TVTokens.Hero.metaSize))
                    .foregroundStyle(RKMColour.secondary)
                    .padding(.bottom, TVTokens.Hero.metaSize)
            }

            if HomeRules.heroShowsProgress(item) {
                progress
                    .padding(.bottom, TVTokens.Hero.metaSize * 1.4)
            }

            actions
        }
        .padding(.horizontal, TVTokens.Hero.paddingH)
        .padding(.vertical, TVTokens.Hero.paddingV)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// ⚠ The bar and its two numbers, exactly as the prototype draws them: a `26u × 0.35u` track with a gold
    /// fill, and `42% · 38m left` beside it — where the countdown is present ONLY when `heroRuntimeLeft` has
    /// something to say (a film that is part-watched). An episode shows its percentage alone.
    private var progress: some View {
        HStack(spacing: TVTokens.Hero.metaSize) {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Rectangle().fill(RKMColour.primary.opacity(0.18))
                    Rectangle().fill(RKMColour.accent)
                        .frame(width: geometry.size.width * CGFloat(percent) / 100)
                }
            }
            .frame(width: TVTokens.Hero.progressWidth, height: TVTokens.Hero.progressHeight)
            .clipShape(Capsule())

            Text(runtimeLeft.isEmpty ? "\(percent)%" : "\(percent)% · \(runtimeLeft) left")
                .font(.system(size: TVTokens.Hero.metaSize))
                .foregroundStyle(RKMColour.secondary)
        }
    }

    private var actions: some View {
        HStack(spacing: TVTokens.Hero.actionSpacing) {
            Button {
                // ⚠ A series opens its own screen; everything else asks for playback, which arrives with
                // Phase C — so it says so instead of doing nothing.
                if primaryOpensTheItem { onDetails() } else { onPrimary() }
            } label: {
                HStack(spacing: TVTokens.Hero.actionSpacing * 0.5) {
                    Image(systemName: "play.fill")
                        .font(.system(size: TVTokens.Hero.ctaFontSize * 0.8))
                    Text(primaryLabel)
                }
            }
            // ⚠⚠ **NO padding/background/foregroundStyle HERE, AND THAT IS THE FIX HE FOUND.** The style owns
            // the box: it draws the fill, the padding, the radius and the focus ring around all of it.
            .buttonStyle(CtaButtonStyle(kind: .primary))
            .accessibilityLabel(primaryLabel)

            if !primaryOpensTheItem {
                Button("Details", action: onDetails)
                    .buttonStyle(CtaButtonStyle(kind: .secondary))
            }
        }
    }
}

/// The prototype's `.cta-btn`, in both its kinds — **and the style draws the whole button, box included.**
///
/// ⚠⚠ **WHY THE STYLE OWNS THE BOX** (his report, 2026-09-20: *"homescreen → scrolling to details button → the
/// ux has bug"*). A `ButtonStyle` receives `configuration.label`, which is the button's CONTENT and nothing
/// else. The first version of this file applied the padding and the fill to the `Button` — outside the label —
/// while the ring was drawn inside the style, so **the ring wrapped the word `Details` and sat inside the
/// button's own grey box**, exactly as his screenshot shows. ⚠ **The fix is not to move the ring: it is to take
/// the box away from the caller.** A caller that can only supply content cannot supply it in the wrong place.
/// ⚠ No gate of mine can see the difference — there is no SwiftUI on Linux — which is precisely why the
/// structure has to make it impossible instead of a convention having to remember it.
///
/// ⚠ The two kinds are the prototype's own: `.primary` is a gold fill with near-black text (`#1a1300`), and
/// `.secondary` is 12 % white with no border. Both take the same `0.9u` radius, the same `0.85u / 1.8u`
/// padding, the same `1.09` focus lift and the same white ring, so they cannot drift apart.
struct CtaButtonStyle: ButtonStyle {

    enum Kind { case primary, secondary }

    let kind: Kind

    func makeBody(configuration: Configuration) -> some View {
        CtaChrome(configuration: configuration, kind: kind)
    }

    // ⚠⚠ NOT `Body`: every `Style` protocol declares an associatedtype requirement called `Body`, so a
    // helper view nested inside a conformer and named `Body` collides with it — measured on the Mac, U6's
    // second round. The Phase A tile style is called `TileBody` for exactly this reason.
    private struct CtaChrome: View {
        let configuration: ButtonStyle.Configuration
        let kind: Kind
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .font(.system(size: TVTokens.Hero.ctaFontSize, weight: kind == .primary ? .bold : .semibold))
                .foregroundStyle(kind == .primary ? RKMColour.background : RKMColour.primary)
                .padding(.horizontal, TVTokens.Hero.ctaPaddingH)
                .padding(.vertical, TVTokens.Hero.ctaPaddingV)
                .background(fill, in: RoundedRectangle(cornerRadius: TVTokens.Hero.ctaRadius,
                                                       style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: TVTokens.Hero.ctaRadius, style: .continuous)
                        .stroke(RKMColour.primary.opacity(0.85),
                                lineWidth: isFocused ? TVTokens.Bar.focusRing : 0)
                }
                .scaleEffect(isFocused ? 1.09 : 1)
                .animation(.easeOut(duration: 0.2), value: isFocused)
        }

        private var fill: Color {
            kind == .primary ? RKMColour.accent : RKMColour.primary.opacity(0.12)
        }
    }
}
