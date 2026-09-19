import SwiftUI

/// The Home's hero band — the buildspec's §4 "full-width band showing the top Continue Watching item".
///
/// ⚠⚠ **EVERY WORD AND EVERY NUMBER IN IT IS A RULE FROM `HomeRails.swift`, MIRRORED FROM THE WEB APP**
/// (`lib.ts::heroEyebrow`, `::heroPrimaryLabel`, `::heroMetaLine`, `::resumePercent`, and the meta/title
/// assembly in `LibraryHomeView.tsx`'s `HomeHero`). This view lays those out and decides nothing: the eyebrow,
/// the verb, the meta line, the percentage and the countdown are all already values by the time they arrive,
/// which is what makes them checkable on Linux (`apple/scripts/check-tvos-core.py`) instead of only on a TV.
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
        .frame(height: Self.height)
        .frame(maxWidth: .infinity)
        .clipped()
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Continue watching \(HomeRules.heroTitle(item))")
    }

    /// ⚠ 460pt: the buildspec's hero is a 21:10 band (`min-h-[340px]` at 1080p on the web, `min-h-[470px]` on
    /// a desktop window). At 1920×1080 a TV hero that takes a third of the screen leaves two rails visible
    /// below it, which is the point of a hero — it must not be the whole screen.
    private static let height: CGFloat = 460

    // MARK: - The picture

    /// ⚠ **The 16:9 BACKDROP, through `PosterImageView` — one artwork path for the whole app.** It is the same
    /// loader the cards use (same cookie handling, same log line, same "no photo" mark on failure), so a hero
    /// whose artwork failed says why rather than showing a black band. ⚠ It falls back to nothing graceful on
    /// purpose: a failed hero backdrop is a visible mark, never a silent empty rectangle.
    private var artwork: some View {
        PosterImageView(base: base, itemID: item.itemID, route: .backdrop)
            .frame(maxWidth: .infinity)
            .frame(height: Self.height)
            .clipped()
    }

    /// The web's three stacked gradients, reduced to the two that carry the copy: the band must blend into the
    /// page at the bottom AND on the leading edge, because the title sits over the artwork.
    ///
    /// ⚠ Built from `RKMColour.background` rather than a hex — the buildspec's gradient values are hand-rolled
    /// rgba, and this repo's rule is that a colour comes from a token (`check-design-tokens.py`, R3).
    private var gradients: some View {
        ZStack {
            LinearGradient(colors: [RKMColour.background, RKMColour.background.opacity(0),],
                           startPoint: .leading, endPoint: .trailing)
            LinearGradient(colors: [RKMColour.background.opacity(0), RKMColour.background],
                           startPoint: .center, endPoint: .bottom)
        }
        .allowsHitTesting(false)
    }

    // MARK: - The copy

    private var copy: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: isEpisode ? "tv" : "play.fill")
                    .font(.system(size: 14))
                // ⚠ UPPERCASED HERE AND NOT IN THE RULE: the string is the app's, the presentation is the
                // buildspec's. Uppercasing inside the rule would change what every other consumer reads.
                Text(HomeRules.heroEyebrow(continueWatching: isContinueWatching, isEpisode: isEpisode).uppercased())
                    .font(.system(size: 16, weight: .bold))
                    .tracking(2)
            }
            .foregroundStyle(RKMColour.accent)

            Text(HomeRules.heroTitle(item))
                .font(.system(size: TVTokens.Metric.heroTitle, weight: .bold))
                .foregroundStyle(RKMColour.primary)
                .lineLimit(2)

            let meta = HomeRules.heroMetaLine(item)
            if !meta.isEmpty {
                Text(meta)
                    .font(.system(size: 22, weight: .medium))
                    .foregroundStyle(RKMColour.secondary)
            }

            if HomeRules.heroShowsProgress(item) {
                progress
            }

            HStack(spacing: 16) {
                Button {
                    // ⚠ A series opens its own screen; everything else asks for playback, which arrives with
                    // Phase C — so it says so instead of doing nothing.
                    if primaryOpensTheItem { onDetails() } else { onPrimary() }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "play.fill").font(.system(size: 16))
                        Text(primaryLabel).font(.system(size: 22, weight: .bold))
                    }
                    .foregroundStyle(RKMColour.background)
                    .padding(.horizontal, 22)
                    .padding(.vertical, 12)
                    .background(RKMColour.accent, in: RoundedRectangle(cornerRadius: DesignTokens.Radius.md,
                                                                       style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(primaryLabel)

                if !primaryOpensTheItem {
                    Button("Details", action: onDetails)
                        .font(.system(size: 22, weight: .semibold))
                        .buttonStyle(.bordered)
                }
            }
            .padding(.top, 4)
        }
        .padding(.horizontal, TVTokens.Metric.safeMargin)
        .padding(.bottom, 30)
        .frame(maxWidth: 1100, alignment: .leading)
    }

    /// ⚠ The bar and its two numbers, exactly as the web draws them: a thin track, the accent fill, and
    /// `9% · 1h 50m left` — where the countdown is present ONLY when `heroRuntimeLeft` has something to say
    /// (a film that is part-watched). An episode shows its percentage alone, because its remainder is not a
    /// countdown but another episode.
    private var progress: some View {
        HStack(spacing: 14) {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(RKMColour.primary.opacity(0.15))
                    Capsule().fill(RKMColour.accent)
                        .frame(width: geometry.size.width * CGFloat(percent) / 100)
                }
            }
            .frame(width: 320, height: 6)

            Text(runtimeLeft.isEmpty ? "\(percent)%" : "\(percent)% · \(runtimeLeft) left")
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(RKMColour.secondary)
        }
    }
}
