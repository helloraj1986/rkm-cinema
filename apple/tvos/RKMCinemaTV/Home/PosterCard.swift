import SwiftUI
import UIKit

/// One poster card: the picture, the resume bar, the title, and the one meta line.
///
/// ⚠⚠ **NOTHING HERE IS ON HOVER.** The web card reveals Play/Details on hover and shows the ⋯ menu on
/// hover; a TV has neither. So the card is a plain `Button` — **Select opens the title** — and every state
/// the web expresses on hover becomes a FOCUS state drawn by the button style. That is the whole design in
/// one sentence, and it is why this card is much smaller than `MediaCard.tsx`.
///
/// ⚠ It carries **no watched control**, matching the web rule his decision fixed on 2026-09-18: the poster
/// REFLECTS status and the details screen OWNS the watched toggle. B2 has no details screen yet, so for now
/// the card shows the played state and offers no way to change it — which is correct, not incomplete.
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
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                // ⚠ A fixed width for the whole label: without it, a long title makes this card wider than
                // its neighbours and the rail's rhythm falls apart. The title truncates instead.
                .frame(width: Self.width, alignment: .leading)
            }
        }
        .buttonStyle(.card)
    }

    // MARK: - The picture

    @ViewBuilder
    private var poster: some View {
        PosterImageView(base: base, itemID: item.itemID)
            .frame(width: Self.width, height: Self.width / Self.aspect)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
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
                    Capsule().fill(.white.opacity(0.22))
                    Capsule().fill(.white).frame(width: geometry.size.width * fraction)
                }
            }
            .frame(width: Self.width, height: 6)
        }
    }
}

/// The poster itself: a state-driven image with its own loader, so a card never silently draws nothing.
///
/// ⚠ **Why not `AsyncImage`:** it cannot log, and on a TV there is no other way to find out why a wall is
/// empty. `PosterLoader` logs the HTTP status, the byte count and whether a session cookie was attached —
/// which is the answer to B2's one open device question (`GET /api/jellyfin/poster` is session-scoped).
/// A placeholder is shown while that happens, and a failure shows the reason rather than a grey rectangle,
/// because "no poster" and "broken poster" must not look the same.
private struct PosterImageView: View {

    let base: URL
    let itemID: String

    @StateObject private var loader: PosterLoader

    init(base: URL, itemID: String) {
        self.base = base
        self.itemID = itemID
        _loader = StateObject(wrappedValue: PosterLoader(base: base, itemID: itemID))
    }

    var body: some View {
        ZStack {
            // The placeholder: warm, flat, and obviously not a poster — a black rectangle reads as a
            // rendering fault, which is the one thing it must not be mistaken for.
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(.white.opacity(0.08))

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
        .foregroundStyle(.secondary)
    }
}
