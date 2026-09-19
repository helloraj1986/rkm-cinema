import SwiftUI
import UIKit

/// One card in a shelf — the prototype's `.card`.
///
/// ⚠⚠ **U6 REBUILT THIS FROM THE PROTOTYPE, AND THE SHAPE WAS THE BIGGEST DIFFERENCE: the art is 16:9, not
/// the 2:3 poster this card used to carry.** The prototype's `.card-art { aspect-ratio: 16/9 }` at a
/// `19u` (~365 pt) card width is what gives the Home its dense, cinematic shelves instead of a row of tall
/// posters — his words after the first build: *"the current one doesn't even look like what is seen in the
/// html"*. The artwork now comes from the **backdrop** route, with a ONE-STEP fall back to the poster when an
/// item has no keyart (`PosterLoader.fallBackToPoster`), because a poster-only library would otherwise be a
/// wall of "no photo" marks.
///
/// ⚠⚠ **NOTHING HERE IS ON HOVER.** The web card reveals Play/Details on hover; a TV has neither. So the card
/// is one `Button` — **Select opens the title** — and every state the web expresses on hover becomes a FOCUS
/// state drawn by the button style (`.card`, the platform's own treatment: buildspec §5 asks for exactly that
/// rather than a hand-rolled scale/glow).
///
/// ⚠ **THE PLAY GLYPH IS DECORATIVE, AND THAT IS THE PROTOTYPE'S OWN SHAPE.** `.card-play` in his file is a
/// `<span>` INSIDE the card button — it is chrome on the artwork, not a control, and the whole card is the
/// target. So it is drawn (a viewer pressing it gets the card's action, exactly as in the prototype) and
/// hidden from VoiceOver, because the card's accessible name already says what Select does. ⚠ It does NOT
/// promise playback: the tvOS player is Phase C, and the detail screen is where the app says so.
///
/// ⚠ It carries **no watched control**, matching the web rule his decision fixed on 2026-09-18: the poster
/// REFLECTS status and the details screen OWNS the watched toggle.
struct PosterCard: View {

    let item: MediaItem
    let base: URL
    let onSelect: (MediaItem) -> Void

    /// ⚠ The prototype's `flex: 0 0 19u` — one number, in the prototype's own unit (`TVTokens.Shelf`).
    private static var width: CGFloat { TVTokens.Shelf.cardWidth }
    /// ⚠ `.card-art { aspect-ratio: 16/9 }`.
    private static let aspect: CGFloat = 9.0 / 16.0

    var body: some View {
        Button {
            onSelect(item)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                artwork
                Text(item.title)
                    .font(.system(size: TVTokens.Shelf.cardTitleSize, weight: .semibold))
                    .foregroundStyle(RKMColour.primary)
                    .lineLimit(1)
                    .padding(.top, TVTokens.Shelf.titleGapTop)
                Text(HomeRules.cardMetaLine(item))
                    .font(.system(size: TVTokens.Shelf.subSize))
                    .foregroundStyle(RKMColour.muted)
                    .lineLimit(1)
            }
            // ⚠ A fixed width for the whole label: without it, a long title makes this card wider than
            // its neighbours and the shelf's rhythm falls apart. The title truncates instead.
            .frame(width: Self.width, alignment: .leading)
        }
        .buttonStyle(.card)
        // ⚠ The badge and the progress bar carry real information a screen reader would otherwise miss — the
        // buildspec's §6 rule, and the same reason the profile tiles carry a label.
        .accessibilityLabel(accessibilityLabel)
    }

    private var accessibilityLabel: String {
        let meta = HomeRules.cardMetaLine(item)
        return meta.isEmpty ? item.title : "\(item.title), \(meta)"
    }

    // MARK: - The artwork, its chrome and its bar

    private var artwork: some View {
        PosterImageView(base: base, itemID: item.itemID, route: .backdrop)
            .frame(width: Self.width, height: Self.width * Self.aspect)
            .clipShape(RoundedRectangle(cornerRadius: TVTokens.Shelf.artRadius, style: .continuous))
            .overlay(alignment: .topLeading) { badge.padding(TVTokens.Shelf.badgeInset) }
            .overlay(alignment: .bottomTrailing) { playGlyph.padding(TVTokens.Shelf.playInset) }
            // ⚠ The bar is INSIDE the art's bottom edge (`position:absolute; left:0; right:0; bottom:0`), so
            // it is an overlay rather than a row under the picture — that is what the prototype draws, and it
            // keeps the shelf's vertical rhythm independent of whether a title is in progress.
            .overlay(alignment: .bottom) { progressBar }
    }

    /// `S2·E4` / `MOVIE` — the text chip on the artwork's top-left corner. ⚠ The words are
    /// `HomeRules.badgeText`'s rule, so the TV and every other surface answer "what am I looking at?" the
    /// same way.
    private var badge: some View {
        Text(HomeRules.badgeText(item))
            .font(.system(size: TVTokens.Shelf.badgeSize, weight: .bold))
            .tracking(0.4)
            .foregroundStyle(RKMColour.primary)
            .padding(.horizontal, TVTokens.Shelf.badgePaddingH)
            .padding(.vertical, TVTokens.Shelf.badgePaddingV)
            .background(RKMColour.background.opacity(0.55),
                        in: RoundedRectangle(cornerRadius: TVTokens.Shelf.badgeRadius, style: .continuous))
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
    /// model can state the fraction honestly (`progressFraction` returns nil for an unknown runtime and for
    /// a finished title), so an absent bar means "unknown", never "just started" — the same rule the phone
    /// uses, from the same function.
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
/// ⚠ **Made non-private in B4** so the detail screen reuses the SAME poster renderer the cards use: one
/// load path, one log line, one "no photo" mark. A second image view on the detail screen is a second place
/// for artwork to fail silently — which is the failure this whole file exists to make visible.
/// ⚠ **U3 gave it a `route`** so the Home's hero band can ask for the 16:9 backdrop through the same loader;
/// **U6 made the cards ask for the backdrop too**, and the loader now falls back to the poster once when an
/// item has no keyart.
struct PosterImageView: View {

    let base: URL
    let itemID: String
    /// `.poster` (2:3) or `.backdrop` (16:9 — the cards and the hero from U6). ⚠ One parameter rather than a
    /// second image view: the cookie handling, the log line, the fallback and the failure mark are the parts
    /// that must not drift.
    var route: PosterURL.Route = .poster

    @StateObject private var loader: PosterLoader

    init(base: URL, itemID: String, route: PosterURL.Route = .poster) {
        self.base = base
        self.itemID = itemID
        self.route = route
        _loader = StateObject(wrappedValue: PosterLoader(base: base, itemID: itemID, route: route))
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
                    Image(uiImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
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
