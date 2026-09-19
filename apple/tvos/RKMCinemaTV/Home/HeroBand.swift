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
                        .font(.system(size: TVTokens.Hero.ctaFontSize, weight: .bold))
                }
                // ⚠ The prototype's `.cta-btn.primary`: gold fill, near-black text (`#1a1300`), 0.9u radius.
                .foregroundStyle(RKMColour.background)
                .padding(.horizontal, TVTokens.Hero.ctaPaddingH)
                .padding(.vertical, TVTokens.Hero.ctaPaddingV)
                .background(RKMColour.accent,
                            in: RoundedRectangle(cornerRadius: TVTokens.Hero.ctaRadius, style: .continuous))
            }
            .buttonStyle(CtaButtonStyle())
            .accessibilityLabel(primaryLabel)

            if !primaryOpensTheItem {
                Button("Details", action: onDetails)
                    // ⚠ The prototype's `.cta-btn.secondary`: 12 % white, no border.
                    .font(.system(size: TVTokens.Hero.ctaFontSize, weight: .semibold))
                    .foregroundStyle(RKMColour.primary)
                    .padding(.horizontal, TVTokens.Hero.ctaPaddingH)
                    .padding(.vertical, TVTokens.Hero.ctaPaddingV)
                    .background(RKMColour.primary.opacity(0.12),
                                in: RoundedRectangle(cornerRadius: TVTokens.Hero.ctaRadius, style: .continuous))
                    .buttonStyle(CtaButtonStyle())
            }
        }
    }
}

/// ⚠ The prototype's `.cta-btn:focus` — a 1.09 lift with a white ring. The fill is drawn by the caller, so
/// this style carries only the focus treatment both hero buttons share.
struct CtaButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        Body(configuration: configuration)
    }

    private struct Body: View {
        let configuration: ButtonStyle.Configuration
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .overlay {
                    RoundedRectangle(cornerRadius: TVTokens.Hero.ctaRadius, style: .continuous)
                        .stroke(RKMColour.primary.opacity(0.85),
                                lineWidth: isFocused ? TVTokens.Bar.focusRing : 0)
                }
                .scaleEffect(isFocused ? 1.09 : 1)
                .animation(.easeOut(duration: 0.2), value: isFocused)
        }
    }
}
