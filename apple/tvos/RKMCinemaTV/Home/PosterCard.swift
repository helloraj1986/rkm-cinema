import SwiftUI
import UIKit

/// One poster card: the picture, its type badge, the resume bar, the title, and the one meta line.
///
/// ⚠⚠ **NOTHING HERE IS ON HOVER.** The web card reveals Play/Details on hover and shows the ⋯ menu on
/// hover; a TV has neither. So the card is a plain `Button` — **Select opens the title** — and every state
/// the web expresses on hover becomes a FOCUS state drawn by the button style. That is the whole design in
/// one sentence, and it is why this card is much smaller than `MediaCard.tsx`.
///
/// ⚠ It carries **no watched control**, matching the web rule his decision fixed on 2026-09-18: the poster
/// REFLECTS status and the details screen OWNS the watched toggle. B2 has no details screen yet, so for now
/// the card shows the played state and offers no way to change it — which is correct, not incomplete.
///
/// ⚠⚠ **PHASE U3 ADDED THE TYPE BADGE AND DELIBERATELY NOT THE PLAY GLYPH.** The buildspec's §4 card has
/// "an episode/type badge (`S2·E4`, `MOVIE`), a play glyph, an optional progress bar". The badge is here, its
/// CONTENT is the web app's own rule (`MediaCard.tsx`: the episode code when there is one, otherwise the
/// tv/film glyph — `HomeRules.typeIcon`, not the buildspec's word badge, because a word badge here and a glyph
/// on the phone is a second vocabulary for one fact). **The play glyph is NOT here:** nothing plays yet
/// (Phase C), and a play triangle that does nothing is the control `docs/ARCHITECTURE.md` §11 forbids. It
/// lands with the player, on the day the gesture means something.
struct PosterCard: View {

    let item: MediaItem
    let base: URL
    let onSelect: (MediaItem) -> Void

    /// ⚠ The web card's own dimensions, as a ratio rather than two numbers: a poster is 2:3 everywhere, and
    /// 260pt wide is what fits four-and-a-bit across a 1920pt TV at the rail's spacing.
    private static let width: CGFloat = 260
    private static let aspect: CGFloat = 2.0 / 3.0

    var body: some View {
        Button {
            onSelect(item)
        } label: {
            VStack(alignment: .leading, spacing: 10) {
                poster
                resumeBar
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.title)
                        .font(.system(size: 26, weight: .semibold))
                        .lineLimit(1)
                    Text(HomeRules.cardMetaLine(item))
                        .font(.system(size: 20))
                        .foregroundStyle(RKMColour.muted)
                        .lineLimit(1)
                }
                // ⚠ A fixed width for the whole label: without it, a long title makes this card wider than
                // its neighbours and the rail's rhythm falls apart. The title truncates instead.
                .frame(width: Self.width, alignment: .leading)
            }
        }
        .buttonStyle(.card)
        // ⚠ The badge carries real information (an episode code, or what kind of thing this is) and a screen
        // reader would otherwise hear only the title — the buildspec's §6 rule, and the same reason the
        // profile tiles carry one.
        .accessibilityLabel(badgeText.isEmpty
                            ? item.title
                            : "\(item.title), \(badgeText)")
    }

    // MARK: - The badge

    /// ⚠ The episode code when there is one, otherwise empty — and the caller draws the type GLYPH in that
    /// case. The code comes from `HomeRules.episodeItemCode`, the same rule the card's meta line uses, so the
    /// `S1E3` above the artwork and the `S1E3 · Series` underneath cannot disagree.
    private var badgeText: String {
        HomeRules.episodeItemCode(item) ?? ""
    }

    private var badge: some View {
        Group {
            if badgeText.isEmpty {
                Image(systemName: HomeRules.typeIcon(item).systemImage)
                    .font(.system(size: 15, weight: .semibold))
            } else {
                Text(badgeText)
                    .font(.system(size: 15, weight: .bold))
            }
        }
        .foregroundStyle(RKMColour.primary)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(RKMColour.background.opacity(0.65),
                    in: RoundedRectangle(cornerRadius: DesignTokens.Radius.sm, style: .continuous))
    }

    // MARK: - The picture

    @ViewBuilder
    private var poster: some View {
        PosterImageView(base: base, itemID: item.itemID)
            .frame(width: Self.width, height: Self.width / Self.aspect)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.md, style: .continuous))
            // ⚠ The badge sits on the ARTWORK's top-left corner, as the buildspec draws it — an overlay on the
            // picture rather than a row above the title, so the rail's rhythm does not change.
            .overlay(alignment: .topLeading) {
                badge.padding(8)
            }
    }

    // MARK: - The resume bar

    /// ⚠ **The bar is the reason this screen is worth having.** A Continue Watching row of identical
    /// posters tells the viewer nothing; the bar is what says how much is left. It is drawn ONLY when the
    /// model can state the fraction honestly (`progressFraction` returns nil for an unknown runtime and for
    /// a finished title), so an absent bar means "unknown", never "just started" — the same rule the phone
    /// uses, from the same function.
    @ViewBuilder
    private var resumeBar: some View {
        if let fraction = item.progressFraction {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(RKMColour.primary.opacity(0.22))
                    Capsule().fill(RKMColour.accent).frame(width: geometry.size.width * fraction)
                }
            }
            .frame(width: Self.width, height: 6)
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
/// ⚠ **U3 gave it a `route`** so the Home's hero band can ask for the 16:9 backdrop through the same loader.
struct PosterImageView: View {

    let base: URL
    let itemID: String
    /// `.poster` (2:3, the cards) or `.backdrop` (16:9, the hero band). ⚠ One parameter rather than a second
    /// image view: the cookie handling, the log line and the failure mark are the parts that must not drift.
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
            // The placeholder: warm, flat, and obviously not a poster — a black rectangle reads as a
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
