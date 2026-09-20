import SwiftUI
import UIKit

/// One card in a shelf — the prototype's `.card`, **premium pass** (his review of the first build that ran,
/// 2026-09-20: *"the card ux doesn't look good, the text positions are going to the border on left, make it
/// ultra premium with some additional relevant info which the user would appreciate, like duration, ratings
/// etc."*).
///
/// ⚠⚠ **THE SHAPE IS STILL THE PROTOTYPE'S: 16:9 keyart at `19u`.** What changed is the *caption* and the
/// artwork's chrome:
///
/// ```
/// ┌──────────────────────────────────┐
/// │ [SERIES]                         │   type / episode badge (top-left)
/// │                                  │
/// │            ARTWORK               │   16:9 keyart, hairline edge, soft shadow
/// │                                  │
/// │ [38m left]              (▶)      │   state chip (lower-left) · play chrome (lower-right)
/// │ ▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░  │   progress bar, only when the fraction is known
/// └──────────────────────────────────┘
///    Adventure Time: Fionna and Cake     1.05u semibold, inset 0.5u
///    44m · 2023 · Animation · 3 plays    0.82u muted — the facts line
/// ```
///
/// ⚠⚠ **EVERY VALUE ON IT COMES OFF THE WIRE — NOTHING IS INVENTED.** `MediaItem` carries `runtime`,
/// `genres`, `year`, `play_count`, `played`, `playback_position` and the episode facet; the facts line, the
/// state chip and the bar are built from those and nothing else (`HomeRules.cardFacts`,
/// `.cardStateText`, `.minutesLeft`, and the model's own `progressFraction`).
///
/// ⚠⚠ **THERE IS NO RATING ON THIS CARD, AND IT IS NOT AN OVERSIGHT.** He asked for ratings, and **the data
/// does not exist on this wire**: `MediaItem` (which R6/R7 of `check-tvos-models.py` pins against the
/// frontend's own `MediaItem` interface, key for key) has no rating, no content rating and no resolution —
/// Jellyfin's `CommunityRating`, `OfficialRating` and `Height`/`Width` are dropped by the api's
/// `_item_public()`. Adding one is a **three-file change plus a deploy** (backend `_item_public()`, the
/// frontend `MediaItem`, then this model), i.e. its own phase — recorded in `docs/PROGRESS.md` as the next
/// thing to offer him, and deliberately NOT smuggled into a UX branch that promises nothing to deploy.
///
/// ⚠⚠ **NOTHING HERE IS ON HOVER.** The web card reveals Play/Details on hover; a TV has neither. So the card
/// is one `Button` — **Select opens the title** — and every state the web expresses on hover becomes a FOCUS
/// state drawn by the platform's own `.card` treatment (buildspec §5 asks for exactly that rather than a
/// hand-rolled scale/glow).
///
/// ⚠ **THE PLAY GLYPH IS DECORATIVE, AND THAT IS THE PROTOTYPE'S OWN SHAPE.** `.card-play` in his file is a
/// `<span>` INSIDE the card button — chrome on the artwork, not a control, and the whole card is the target.
/// ⚠ It does NOT promise playback: the tvOS player is Phase C, and the detail screen is where the app says so.
///
/// ⚠ It carries **no watched control**, matching the web rule his decision fixed on 2026-09-18: the poster
/// REFLECTS status and the details screen OWNS the watched toggle. The `Watched` chip is that reflection.
struct PosterCard: View {

    let item: MediaItem
    let base: URL
    let onSelect: (MediaItem) -> Void

    /// ⚠ The prototype's `flex: 0 0 19u` — one number, in the prototype's own unit (`TVTokens.Shelf`).
    private static var width: CGFloat { TVTokens.Shelf.cardWidth }
    /// ⚠ `.card-art { aspect-ratio: 16/9 }`.
    private static let aspect: CGFloat = 9.0 / 16.0

    private var artHeight: CGFloat { Self.width * Self.aspect }
    private var facts: [String] { HomeRules.cardFacts(item) }
    private var state: String { HomeRules.cardStateText(item) }

    var body: some View {
        Button {
            onSelect(item)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                artwork

                // ⚠⚠ THE CAPTION IS INSET, and that is his report fixed: with no inset the title and the facts
                // line began at the artwork's exact left edge. `textInset` is the same `0.5u` the badge uses on
                // the art, so the card's two corners line up.
                VStack(alignment: .leading, spacing: 0) {
                    Text(item.title)
                        .font(.system(size: TVTokens.Shelf.cardTitleSize, weight: .semibold))
                        .foregroundStyle(RKMColour.primary)
                        .lineLimit(1)

                    if !facts.isEmpty {
                        // ⚠ The separator belongs to the VIEW (the rule returns a list) — a narrow card can
                        // wrap this into two chips without the rule changing.
                        Text(facts.joined(separator: " · "))
                            .font(.system(size: TVTokens.Shelf.subSize))
                            .foregroundStyle(RKMColour.muted)
                            .lineLimit(1)
                            .padding(.top, TVTokens.Shelf.factsGapTop)
                    }
                }
                .padding(.horizontal, TVTokens.Shelf.textInset)
                .padding(.top, TVTokens.Shelf.titleGapTop)
            }
            // ⚠ A fixed width for the whole label: without it, a long title makes this card wider than its
            // neighbours and the shelf's rhythm falls apart. The title truncates instead.
            .frame(width: Self.width, alignment: .leading)
        }
        .buttonStyle(.card)
        // ⚠ The badge, the chips and the bar carry real information a screen reader would otherwise miss — the
        // buildspec's §6 rule, and the same reason the profile tiles carry a label.
        .accessibilityLabel(accessibilityLabel)
    }

    /// ⚠ Every fact the card DRAWS, in one sentence, so nothing on it is invisible to VoiceOver. Built from
    /// the same rules the drawing uses — a second wording here would be a second vocabulary for one card.
    private var accessibilityLabel: String {
        var parts = [item.title]
        let badge = HomeRules.badgeText(item)
        if !badge.isEmpty { parts.append(badge) }
        parts.append(contentsOf: facts)
        if !state.isEmpty { parts.append(state) }
        return parts.joined(separator: ", ")
    }

    // MARK: - The artwork, its chrome and its bar

    private var artwork: some View {
        PosterImageView(base: base, itemID: item.itemID, route: .backdrop)
            .frame(width: Self.width, height: artHeight)
            .clipShape(RoundedRectangle(cornerRadius: TVTokens.Shelf.artRadius, style: .continuous))
            // ⚠ The scrim, UNDER the chips and the bar: keyart is often bright exactly where they sit, and a
            // chip you cannot read is worse than no chip.
            .overlay(alignment: .bottom) {
                LinearGradient(colors: [.clear, RKMColour.background.opacity(TVTokens.Shelf.scrimOpacity)],
                               startPoint: .top, endPoint: .bottom)
                    .frame(height: TVTokens.Shelf.scrimHeight)
                    .allowsHitTesting(false)
            }
            .overlay(alignment: .topLeading) { badge.padding(TVTokens.Shelf.badgeInset) }
            .overlay(alignment: .bottomTrailing) { playGlyph.padding(TVTokens.Shelf.playInset) }
            .overlay(alignment: .bottomLeading) { stateChip.padding(TVTokens.Shelf.badgeInset) }
            // ⚠ The bar is INSIDE the art's bottom edge (`position:absolute; left:0; right:0; bottom:0`), so it
            // is an overlay rather than a row under the picture — that is what the prototype draws, and it
            // keeps the shelf's vertical rhythm independent of whether a title is in progress.
            .overlay(alignment: .bottom) { progressBar }
            // ⚠ The `1px` inner hairline (the prototype's `--hairline`): on a black screen a 16:9 card with no
            // edge dissolves into the shelf behind it.
            .overlay {
                RoundedRectangle(cornerRadius: TVTokens.Shelf.artRadius, style: .continuous)
                    .stroke(RKMColour.primary.opacity(0.08), lineWidth: TVTokens.Shelf.artBorderWidth)
            }
            // ⚠ The prototype's own `box-shadow: 0 0.5u 1.4u rgba(0,0,0,.45)` — the card is an object on the
            // page, not a hole in it.
            .shadow(color: RKMColour.background.opacity(TVTokens.Shelf.artShadowOpacity),
                    radius: TVTokens.Shelf.artShadowRadius,
                    y: TVTokens.Shelf.artShadowY)
    }

    /// `SERIES` / `MOVIE` / `S2E4` — the text chip on the artwork's top-left corner. ⚠ The words are
    /// `HomeRules.badgeText`'s rule, so the TV and every other surface answer "what am I looking at?" the same
    /// way. ⚠ The badge is the LOUDEST thing on the card (bold, tracked, brightest chip fill): it is the only
    /// chip that says what the title IS.
    private var badge: some View {
        Text(HomeRules.badgeText(item))
            .font(.system(size: TVTokens.Shelf.badgeSize, weight: .bold))
            .tracking(0.6)
            .foregroundStyle(RKMColour.primary)
            .padding(.horizontal, TVTokens.Shelf.badgePaddingH)
            .padding(.vertical, TVTokens.Shelf.badgePaddingV)
            .background(chipFill,
                        in: RoundedRectangle(cornerRadius: TVTokens.Shelf.badgeRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: TVTokens.Shelf.badgeRadius, style: .continuous)
                    .stroke(RKMColour.primary.opacity(0.14), lineWidth: 1)
            )
    }

    /// `38m left` / `Watched` — the state chip on the artwork's lower-left, and the ONLY chip that appears
    /// conditionally. ⚠ One chip, two facts, in priority order, all of it `HomeRules.cardStateText`'s rule: a
    /// half-watched title says how much is LEFT (the bar says it is half watched, not how long that is), and
    /// only a finished one falls through to `Watched`.
    @ViewBuilder
    private var stateChip: some View {
        if !state.isEmpty {
            Text(state)
                .font(.system(size: TVTokens.Shelf.chipSize, weight: .semibold))
                .foregroundStyle(RKMColour.primary)
                .padding(.horizontal, TVTokens.Shelf.chipPaddingH)
                .padding(.vertical, TVTokens.Shelf.chipPaddingV)
                .background(chipFill,
                            in: RoundedRectangle(cornerRadius: TVTokens.Shelf.badgeRadius, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: TVTokens.Shelf.badgeRadius, style: .continuous)
                        .stroke(RKMColour.primary.opacity(0.14), lineWidth: 1)
                )
        }
    }

    /// ⚠ One fill for every chip, so a fourth one cannot arrive looking different: the app's own `--bg` at a
    /// fixed opacity, which stays legible over both bright and dark keyart.
    private var chipFill: Color {
        RKMColour.background.opacity(0.62)
    }

    /// The gold play circle on the artwork's bottom-right — **chrome, not a control** (see this file's
    /// header). ⚠ `accessibilityHidden(true)`: it says nothing the card's own label does not already say, and
    /// a second element inside a `Button` is a second thing for VoiceOver to stop on.
    private var playGlyph: some View {
        Image(systemName: "play.fill")
            .font(.system(size: TVTokens.Shelf.playSize * 0.45))
            .foregroundStyle(RKMColour.background)
            .frame(width: TVTokens.Shelf.playSize, height: TVTokens.Shelf.playSize)
            .background(RKMColour.accent, in: Circle())
            .accessibilityHidden(true)
    }

    /// ⚠ **The bar is the reason this screen is worth having.** A Continue Watching shelf of identical
    /// artwork tells the viewer nothing; the bar is what says how much is left. It is drawn ONLY when the
    /// model can state the fraction honestly (`progressFraction` returns nil for an unknown runtime and for a
    /// finished title — and ⚠ the `Watched` chip is that same nil, read from the other side), so an absent bar
    /// means "unknown", never "just started". Same rule and same function as the phone.
    @ViewBuilder
    private var progressBar: some View {
        if let fraction = item.progressFraction {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    // The prototype's track: `rgba(0,0,0,.4)` full width, gold fill, `0.22u` tall.
                    Rectangle().fill(RKMColour.background.opacity(0.4))
                    Rectangle().fill(RKMColour.accent).frame(width: geometry.size.width * fraction)
                }
            }
            .frame(height: TVTokens.Shelf.progressHeight)
        }
    }
}

/// The artwork itself: a state-driven image with its own loader, so a card never silently draws nothing.
///
/// ⚠ **Why not `AsyncImage`:** it cannot log, and on a TV there is no other way to find out why a wall is
/// empty. `PosterLoader` logs the HTTP status, the byte count and whether a session cookie was attached —
/// which is the answer to B2's one open device question (`GET /api/jellyfin/poster` is session-scoped).
/// A placeholder is shown while that happens, and a failure shows the reason rather than a grey rectangle,
/// because "no poster" and "broken poster" must not look the same.
/// ⚠ **Made non-private in B4** so the detail screen reuses the SAME poster renderer the cards use: one load
/// path, one log line, one "no photo" mark. A second image view on the detail screen is a second place for
/// artwork to fail silently — which is the failure this whole file exists to make visible.
/// ⚠ **U3 gave it a `route`** so the Home's hero band can ask for the 16:9 backdrop through the same loader;
/// **U6 made the cards ask for the backdrop too**, and the loader falls back to the poster once when an item
/// has no keyart (`PosterLoader.fallBackToPoster`).
struct PosterImageView: View {

    let base: URL
    let itemID: String
    /// `.poster` (2:3) or `.backdrop` (16:9 — the cards and the hero from U6). ⚠ One parameter rather than a
    /// second image view: the cookie handling, the log line, the fallback and the failure mark are the parts
    /// that must not drift.
    var route: PosterURL.Route = .poster
    /// ⚠⚠ **The PIXEL width to ask for, where the band's own size is known (W3).** `nil` keeps the route's
    /// default (500 for a card, 1600 for a backdrop) — which is right for a CARD, whose art is a couple of
    /// hundred points wide, and wrong for the title screen's full-width hero on a 4K panel. The caller that
    /// knows how wide its band is passes `PosterURL.width(points:scale:route:)` with its own
    /// `@Environment(\.displayScale)`; everything else keeps the default and does not double its bytes.
    var width: Int?

    @StateObject private var loader: PosterLoader

    init(base: URL, itemID: String, route: PosterURL.Route = .poster, width: Int? = nil) {
        self.base = base
        self.itemID = itemID
        self.route = route
        self.width = width
        _loader = StateObject(wrappedValue: PosterLoader(base: base, itemID: itemID, width: width, route: route))
    }

    var body: some View {
        ZStack {
            // The placeholder: warm, flat, and obviously not artwork — a black rectangle reads as a
            // rendering fault, which is the one thing it must not be mistaken for.
            Rectangle()
                .fill(RKMColour.primary.opacity(0.08))

            switch loader.state {
            case .loaded(let data):
                if let image = UIImage(data: data) {
                    drawn(image)
                } else {
                    // ⚠ Bytes arrived and are not an image. That is a different fault from a failed
                    // request, and the log line above says which.
                    failMark("unreadable image")
                }
            case .failed(let reason):
                failMark(reason)
            case .idle, .loading:
                ProgressView()
            }
        }
        .task {
            await loader.load()
        }
    }

    /// ⚠⚠ **THE BYTES DECIDE HOW THEY ARE DRAWN — AND IT IS `Core/PosterRules.swift` THAT DECIDES, so the rule
    /// is RUN on Linux rather than eyeballed here.** His report (2026-09-20): *"i can only see 1/3rd of the
    /// poster"* — the band had fallen back to the 2:3 poster and `.fill` into a 1920 × 313 band cuts **60 % of
    /// its width**. A portrait image in a landscape band is now shown WHOLE over a blurred, dimmed copy of
    /// itself (`ArtworkTreatment.ambient`); everything else fills exactly as it did.
    ///
    /// ⚠ The band's own size is what the rule needs, so this reads it with a `GeometryReader` **in a
    /// `.background`** — the one placement that cannot affect layout and cannot join the focus engine (the same
    /// instrument `DetailView.measured` uses, and the opposite of the reader round 3 had to delete).
    @ViewBuilder
    private func drawn(_ image: UIImage) -> some View {
        GeometryReader { proxy in
            switch PosterRules.treatment(imageWidth: image.size.width,
                                         imageHeight: image.size.height,
                                         bandWidth: proxy.size.width,
                                         bandHeight: proxy.size.height) {
            case .fill:
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
            case .ambient:
                ZStack {
                    Image(uiImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .blur(radius: TVTokens.Artwork.ambientBlur, opaque: true)
                        .opacity(TVTokens.Artwork.ambientOpacity)
                    Image(uiImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                }
            }
        }
    }

    private func failMark(_ reason: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "photo")
                .font(.system(size: 34))
            Text(reason)
                .font(.system(size: 16))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 14)
        }
        .foregroundStyle(RKMColour.muted)
    }
}
