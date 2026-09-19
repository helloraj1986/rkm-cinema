import SwiftUI
import RKMServerKit

/// Item detail — screen #5, read-only. Phase B4's screen.
///
/// ⚠ **READ-ONLY, AND IT SAYS SO.** The tvOS player is Phase C, and there is no api route this app may play
/// from yet, so this screen offers **no Play control at all**. `docs/ARCHITECTURE.md` §11's rule is "never
/// OFFER what the server will refuse"; a focusable Play button that apologises when pressed is the same lie
/// told one press later. What the screen does instead is show the verb it WILL offer — the phone's own
/// words, from `DetailRules.primaryVerb` ("Resume S1E4", "Resume (28%)", "Play") — under a line that says
/// where playback comes from. That is the plan's "the screen must say so rather than doing nothing".
///
/// ⚠ **Every decision this screen obeys is in `DetailRules.swift`** (pure, RUN on Linux): the meta line, the
/// rating readout, the resume percentage, the season grouping, each episode's progress sentence, the
/// credits lines and the four states. This type lays that out and nothing else.
///
/// ⚠ **THE WAYS OUT STAY, and there is now one more of them than on any other screen.** `Back` returns to
/// where this was opened from (Home or Browse — `AppModel.detailReturnLabel` names it), and the four session
/// exits are here exactly as they are on Home and Browse. A detail screen reached from three folders deep
/// with no named way back is a dead end with a nice poster on it.
struct DetailView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var store: DetailStore
    let base: URL

    /// ⚠ The web card's 2:3 poster, larger: this is the one screen where the artwork is the page.
    private static let posterWidth: CGFloat = 340
    private static let posterAspect: CGFloat = 2.0 / 3.0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header

            Group {
                switch store.state {
                case .loading:
                    loading
                case .content(let snapshot):
                    content(snapshot)
                case .notFound:
                    notFound
                case .failed(let message):
                    failure(message)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        // ⚠ `.task`, not `.onAppear`: the load is async, and the store is built per item (`AppModel`), so
        // this runs once for the item that is open.
        .task {
            await store.load()
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 18) {
            // ⚠ FIRST, and filled: on a screen reached from somewhere else, the way back is the primary verb.
            Button(app.detailReturnLabel) { app.closeDetail() }
                .buttonStyle(.borderedProminent)
            Button("Home") { app.showHome() }
            Button("Browse") { app.showBrowse() }
            Button("Change profile") { Task { await app.changeProfile() } }
            Button("Sign out") { Task { await app.signOut() } }
            Button("Change server") { app.changeServer() }
            Spacer(minLength: 0)
        }
        .font(.system(size: 22))
        .padding(.horizontal, 60)
        .padding(.top, 44)
        .padding(.bottom, 10)
        .buttonStyle(.bordered)
    }

    // MARK: - Loading

    private var loading: some View {
        VStack(alignment: .leading, spacing: 16) {
            ProgressView()
                .controlSize(.large)
            Text("Loading this title…")
                .font(.system(size: 24))
                .foregroundStyle(.secondary)
        }
        .padding(60)
    }

    // MARK: - The two failure states

    /// ⚠ The api's own `404` — "We couldn't find that title in the library", the web app's exact words
    /// (`lib.ts::DETAIL_NOT_FOUND_TITLE`). ⚠ It is deliberately NOT the same screen as a network failure:
    /// the server answered, and the answer is that the title is gone.
    private var notFound: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(DetailCopy.notFoundTitle)
                .font(.system(size: 36, weight: .semibold))
            Text(DetailCopy.notFoundSub)
                .font(.system(size: 24))
                .foregroundStyle(.secondary)
            Button("Back to the library") { app.closeDetail() }
                .font(.system(size: 22))
                .padding(.top, 6)
        }
        .padding(60)
        .buttonStyle(.borderedProminent)
    }

    private func failure(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Couldn't load this title")
                .font(.system(size: 36, weight: .semibold))
            Text(message)
                .font(.system(size: 24))
                .foregroundStyle(.secondary)
            HStack(spacing: 18) {
                Button("Try again") { Task { await store.load() } }
                    .buttonStyle(.borderedProminent)
                Button(app.detailReturnLabel) { app.closeDetail() }
            }
            .font(.system(size: 22))
            .padding(.top, 6)
        }
        .padding(60)
        .buttonStyle(.bordered)
    }

    // MARK: - The title

    private func content(_ snapshot: DetailSnapshot) -> some View {
        ScrollView(.vertical, showsIndicators: false) {
            HStack(alignment: .top, spacing: 44) {
                PosterImageView(base: base, itemID: snapshot.detail.itemID)
                    .frame(width: Self.posterWidth, height: Self.posterWidth / Self.posterAspect)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

                VStack(alignment: .leading, spacing: 16) {
                    Text(snapshot.detail.name)
                        .font(.system(size: 46, weight: .bold))
                    facts(snapshot)
                    if !snapshot.genres.isEmpty {
                        Text(snapshot.genres.joined(separator: " · "))
                            .font(.system(size: 22))
                            .foregroundStyle(.secondary)
                    }
                    credits(snapshot)
                    if snapshot.isInProgress, snapshot.resumePercent > 0 {
                        resumeBar(percent: snapshot.resumePercent)
                    }
                    playbackNotice(snapshot)
                    overview(snapshot)
                    cast(snapshot)
                }
                .frame(maxWidth: 1200, alignment: .leading)
            }
            .padding(.horizontal, 60)
            .padding(.top, 20)

            if snapshot.showsEpisodes {
                episodes(snapshot)
            }
        }
    }

    /// `year · runtime (or seasons) · certification`, then the rating — ⚠ the parts come from
    /// `DetailRules.metaBits` and unknown ones are already dropped, so there is no empty separator to trim.
    @ViewBuilder
    private func facts(_ snapshot: DetailSnapshot) -> some View {
        HStack(spacing: 14) {
            if !snapshot.metaBits.isEmpty {
                Text(snapshot.metaBits.joined(separator: " · "))
                    .font(.system(size: 24))
            }
            if !snapshot.rating.isEmpty {
                // ⚠ The star is the web's own readout (`ratingText` + a ★), so a score reads the same shape
                // on both surfaces. One decimal, and a whole number loses its `.0`.
                Text("★ \(snapshot.rating)")
                    .font(.system(size: 24, weight: .semibold))
            }
        }
        .foregroundStyle(.secondary)
    }

    @ViewBuilder
    private func credits(_ snapshot: DetailSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let line = snapshot.directorLine {
                Text(line).font(.system(size: 22)).foregroundStyle(.secondary)
            }
            if let line = snapshot.writerLine {
                Text(line).font(.system(size: 22)).foregroundStyle(.secondary)
            }
            if !snapshot.studiosLine.isEmpty {
                Text(snapshot.studiosLine).font(.system(size: 20)).foregroundStyle(.tertiary)
            }
        }
    }

    private func resumeBar(percent: Int) -> some View {
        HStack(spacing: 14) {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(.white.opacity(0.22))
                    Capsule().fill(.white)
                        .frame(width: geometry.size.width * CGFloat(percent) / 100)
                }
            }
            .frame(width: Self.posterWidth, height: 6)
            Text("\(percent)% watched")
                .font(.system(size: 20))
                .foregroundStyle(.secondary)
        }
    }

    /// ⚠⚠ **THE PLACE A PLAY BUTTON WOULD BE, AND WHY THERE ISN'T ONE.** See this file's header: Phase B has
    /// no player and the api has no playable route for tvOS, so the screen states the fact and names the verb
    /// it will offer. The verb is a RULE (`DetailRules.primaryVerb`) rendered as information — which is also
    /// what makes it worth computing: Phase C's button reads the same value, so the two cannot disagree.
    private func playbackNotice(_ snapshot: DetailSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(DetailCopy.playPendingTitle)
                .font(.system(size: 24, weight: .semibold))
            Text(DetailCopy.playPendingSub)
                .font(.system(size: 22))
                .foregroundStyle(.secondary)
            Text(DetailCopy.nextUp(snapshot.primaryVerb))
                .font(.system(size: 22))
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 14)
        .padding(.horizontal, 20)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(.white.opacity(0.06)))
    }

    @ViewBuilder
    private func overview(_ snapshot: DetailSnapshot) -> some View {
        if !snapshot.overview.isEmpty {
            Text(snapshot.overview)
                .font(.system(size: 23))
                .lineSpacing(6)
                .foregroundStyle(.secondary)
                .frame(maxWidth: 1000, alignment: .leading)
        }
    }

    /// ⚠ **No headshots.** tvOS draws the names and their roles; the web's round avatar is a proxy request
    /// per person (`/api/jellyfin/person`), and Phase B's artwork budget is the posters — one request per
    /// card is what the wall is for. The screen says who is in it, which is what a preplay page is for.
    @ViewBuilder
    private func cast(_ snapshot: DetailSnapshot) -> some View {
        if !snapshot.cast.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Cast")
                    .font(.system(size: 24, weight: .semibold))
                Text(snapshot.cast.map(\.name).joined(separator: " · "))
                    .font(.system(size: 22))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: 1000, alignment: .leading)
            }
            .padding(.top, 4)
        }
    }

    // MARK: - Episodes

    /// One season per heading, episodes underneath — ⚠ the grouping is `DetailRules.groupBySeason`, which
    /// sorts the season numbers and leaves the episodes in the server's order.
    ///
    /// ⚠ **A partial failure is RENDERED.** A series whose episode list could not be fetched looks exactly
    /// like a series with no episodes, so the sentence is on the screen (`DetailCopy.partialWarning`) rather
    /// than only in the log. ⚠ …and it shows even when some seasons DID arrive, because the list comes back
    /// as one response: there is no partial payload.
    @ViewBuilder
    private func episodes(_ snapshot: DetailSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            if let warning = snapshot.partialWarning {
                Text(warning)
                    .font(.system(size: 24))
                    .foregroundStyle(.orange)
            } else if snapshot.episodes.isEmpty {
                // ⚠ A real answer, not a fault: the server answered, and this series has no episodes the
                // profile may see. The same distinction Home and Browse make between empty and failed.
                Text("No episodes yet")
                    .font(.system(size: 24))
                    .foregroundStyle(.secondary)
            }

            ForEach(snapshot.seasons) { group in
                VStack(alignment: .leading, spacing: 12) {
                    // ⚠ The web's own heading, verbatim (`ItemDetail.tsx`: `Season {group.season}`) — which
                    // is why season 0 (specials) reads "Season 0" here rather than being renamed.
                    Text("Season \(group.season)")
                        .font(.system(size: 30, weight: .semibold))
                        .padding(.top, 10)
                    ForEach(group.episodes) { episode in
                        episodeRow(episode)
                    }
                }
            }
        }
        .padding(.horizontal, 60)
        .padding(.top, 34)
        .padding(.bottom, 60)
    }

    /// ⚠ **THE ROW CARRIES NO PLAY BUTTON** — the web's `EpisodeRow` ends in a Play/Resume/Replay control,
    /// and Phase B cannot honour it (this file's header). What the row DOES carry is the episode's state,
    /// computed by `DetailRules.episodeProgress` — the same function the phone's row reads, so the two
    /// surfaces cannot describe the same half-watched episode differently.
    private func episodeRow(_ episode: EpisodeItem) -> some View {
        let progress = DetailRules.episodeProgress(episode)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 16) {
                Text(DetailRules.episodeCode(episode))
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(.tint)
                    .frame(width: 84, alignment: .leading)
                Text(episode.name)
                    .font(.system(size: 24, weight: .medium))
                    .lineLimit(1)
            }
            Text(stateLine(episode, progress: progress))
                .font(.system(size: 20))
                // ⚠ `Color.` on both sides: `.green` and `.secondary` are two DIFFERENT style types, and a
                // ternary over `ShapeStyle` does not typecheck.
                .foregroundStyle(episode.played ? Color.green : Color.secondary)
                .padding(.leading, 100)
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 20)
        .frame(maxWidth: 1400, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(progress.inProgress ? Color.white.opacity(0.10) : Color.white.opacity(0.04))
        )
    }

    /// `ItemDetail.tsx::EpisodeRow`'s three cases, in its order: watched, in progress, else the episode's own
    /// length — and `"Not watched"` when the server sent no runtime at all (the web's `|| "Not watched"`).
    private func stateLine(_ episode: EpisodeItem, progress: EpisodeProgress) -> String {
        if episode.played { return DetailCopy.watchedWord }
        if progress.inProgress {
            return "\(progress.percent)% watched · \(progress.remainingLabel)"
        }
        let runtime = HomeRules.runtimeText(episode.runtime)
        return runtime.isEmpty ? "Not watched" : runtime
    }
}
