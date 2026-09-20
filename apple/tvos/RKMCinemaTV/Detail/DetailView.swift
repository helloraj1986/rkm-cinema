import SwiftUI
import RKMServerKit

/// Item detail — screen #5, **redesigned in Phase V to `tvos_ux/2. LibraryViewandItemDetailsView/title-view.html`**.
///
/// ⚠⚠ **READ-ONLY, AND IT SAYS SO — AND IN PHASE V THAT IS A DECISION HE MADE, NOT A DEFAULT.**
/// His prototype opens with focus on **Play** (*"the one-button path to watching"*). ⚠ That control was
/// deliberately ABSENT until 2026-09-20: the tvOS player was Phase C and parked (`Core/PlaybackAuth.swift`
/// existed; C2–C5 did not), so he was asked and chose **no Play control until the player exists** —
/// `docs/ARCHITECTURE.md` §11's rule is *"never OFFER what the server will refuse"*, and a focusable Play
/// button that apologises when pressed
/// is that lie told one press later.
///
/// ⇒ **NOTHING ON THIS SCREEN IS A BUTTON EXCEPT THE WAY OUT.** The top bar carries the app's own `TopBar`
/// ⚠⚠ **PHASE C3 LANDED THE PLAYER, SO THE ROW IS NOW ONE REAL CONTROL** — `playAction` below, labelled by
/// `DetailSnapshot.primaryVerb` and wired to `AppModel.openPlayer`. Everything else about this screen is
/// unchanged: it still states where playback comes from, and the verb it offers is still a rule.
///
/// with ONE tab — `Back`, named by `AppModel.detailReturnLabel` — and the profile avatar; the avatar opens
/// the Profile Switcher, which is where `Sign out`, `Change server` and `Manage profiles` already live (the
/// move Home made in U3, accepted on his simulator). **`Back` therefore has the default focus**, which is
/// B4's own rule — *"on a screen reached from somewhere else, the way back is the primary verb"* — and it
/// also means the screen is neither a focus trap nor a dead end.
///
/// ⚠⚠ **AND THE CAST ROW IS ONE ROW FOR THAT REASON.** The prototype's cast shelf scrolls horizontally, which
/// on a television is *unreachable* unless something inside it can take focus (no focus, no scroll) — and
/// making an avatar focusable would create a control whose only outcome is a press that does nothing. So the
/// row is drawn at its own `150px` item pitch and has to FIT: `DetailRules.castRows` caps at
/// **`DetailRules.castCapacity`**, which is how many of his `150px` items fit `1920 − 2 × 64px` — **seven**, and
/// not the flat ten this line used to claim. ⚠ That claim was the defect: it took the item's width from the
/// AVATAR (`110px`) instead of from his `.cast-item` (`150px`), so ten items came to 2208 pt of a 1758.7 pt
/// content width, and the overflowing row made the whole PAGE wider than the canvas — every element on this
/// screen drawn left of the screen edge and cut (KNOWN_ISSUES #13, his *"THE WHOLE PAGE IS ZOOMED IN AND I CAN
/// ONLY SEE A PORTION OF THE PAGE"*). ⚠ It is information, not a
/// control, and the round's falsifier **V-F6** is what checks that it reads that way.
///
/// ⚠ **Every decision this screen obeys is in `DetailRules.swift`** (pure, RUN on Linux): the meta line, the
/// rating readout, the resume percentage, the season grouping, each episode's progress sentence, the credits
/// lines, the cast cap and the four states. This type lays that out and nothing else.
///
/// ⚠⚠ **WHAT IS DELIBERATELY NOT BUILT, so the next session does not "finish" it by accident:**
///   * **the action row** (Play / Trailer / Add to Watchlist / More) — his decision, above. ⚠ `Trailer`
///     cannot land with Phase C either: `ItemDetail` decodes 21 keys and **none of them is a trailer**
///     (`Core/Models/DetailModels.swift`), so it needs a wire change of its own;
///   * **the "Because you watched" shelf.** On the web it is not a library row at all — `SimilarRow.tsx`
///     **drops every title already in the library** and its cards open a TMDB page offering *Add to
///     watchlist* / *Download*, because `/api/jellyfin/similar` carries a **TMDB id and no Jellyfin item
///     id**. Replicating it on tvOS means building an acquisition surface, which is its own phase
///     (`docs/TVOS_LIBRARY_UI_PLAN.md` §1 row 3 and §5);
///   * **the top bar's collapse-on-scroll** (his `.topbar.scrolled`). It is the same class of platform claim
///     as the Home's F6, and the plan says the Home's round settles that first — not this screen.
///
/// ⚠ **THE EPISODE LIST IS NOT IN HIS FILE AT ALL** (his title screen is a film), so a series keeps B4's
/// episode rows: that is real data the screen would otherwise have nowhere to put, and it is the one place
/// the app can say what an episode's progress is (`DetailRules.episodeProgress`, the phone's own rule).
struct DetailView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var store: DetailStore
    let base: URL

    var body: some View {
        measured("screen", VStack(alignment: .leading, spacing: 0) {
            measured("bar", topBar)

            measured("page", Group {
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
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading))
        })
        // ⚠ `.task`, not `.onAppear`: the load is async, and the store is built per item (`AppModel`), so
        // this runs once for the item that is open.
        .task {
            await store.load()
        }
    }

    // MARK: - The top bar

    /// ⚠ **The app's own bar, with ONE tab.** His title screen draws *"the wordmark and a back link"* and no
    /// library tabs, which is exactly what this is — and the bar is where `Back` lives so that the way out is
    /// the first focusable thing on the screen, which is what makes the default focus honest rather than a
    /// compromise.
    private var topBar: some View {
        TopBar(tabs: [
            TopBarTab(id: "detail:back",
                      title: app.detailReturnLabel,
                      isCurrent: false,
                      isEnabled: true,
                      warning: "",
                      action: { app.closeDetail() }),
        ],
        initials: ProfileRules.initials(app.session?.currentProfile?.name ?? ""),
        failure: nil,
        onProfile: { Task { await app.changeProfile() } })
    }

    // MARK: - Loading

    private var loading: some View {
        VStack(alignment: .leading, spacing: TVTokens.Grid.emptyGap) {
            ProgressView()
                .controlSize(.large)
            Text("Loading this title…")
                .font(.system(size: TVTokens.Title.metaSize))
                .foregroundStyle(RKMColour.secondary)
        }
        .padding(LibraryRules.marginFromPrototype)
    }

    // MARK: - The two failure states

    /// ⚠ The api's own `404` — "We couldn't find that title in the library", the web app's exact words
    /// (`lib.ts::DETAIL_NOT_FOUND_TITLE`). ⚠ It is deliberately NOT the same screen as a network failure:
    /// the server answered, and the answer is that the title is gone.
    private var notFound: some View {
        message(DetailCopy.notFoundTitle, DetailCopy.notFoundSub, retry: false)
    }

    private func failure(_ text: String) -> some View {
        message("Couldn't load this title", text, retry: true)
    }

    /// ⚠ A focusable way out, always — the same rule as every other state in this app.
    private func message(_ title: String, _ sub: String, retry: Bool) -> some View {
        VStack(alignment: .leading, spacing: TVTokens.Grid.emptyGap) {
            Text(title)
                .font(.system(size: TVTokens.Grid.emptyTitleSize, weight: .semibold))
            Text(sub)
                .font(.system(size: TVTokens.Grid.emptyBodySize))
                .foregroundStyle(RKMColour.secondary)
            HStack(spacing: TVTokens.Grid.chipGap) {
                if retry {
                    Button("Try again") { Task { await store.load() } }
                        .buttonStyle(.borderedProminent)
                }
                Button(app.detailReturnLabel) { app.closeDetail() }
            }
            .font(.system(size: TVTokens.Grid.emptyBodySize))
            .padding(.top, TVTokens.Grid.gridTopPad)
        }
        .padding(.horizontal, LibraryRules.marginFromPrototype)
        .padding(.vertical, TVTokens.Grid.emptyPaddingV)
        .buttonStyle(.bordered)
    }

    // MARK: - The title

    private func content(_ snapshot: DetailSnapshot) -> some View {
        // ⚠⚠ **NO `GeometryReader` — AND REMOVING IT IS A FOCUS FIX, NOT A TIDY-UP.** His round-3 report:
        // *"i can not go to the play button on any title"*, and the Play control is the only focusable thing
        // inside this scroll content. The reader was here to measure `66vh`, which is the SAME structure
        // `BrowseView.cardWidth` blames for KNOWN_ISSUES #11 (*"i cant come to the titles by pressing down
        // arrow"*): a `GeometryReader` reports its size only AFTER layout, and the frames it hands its children
        // are what the focus engine navigates on. On tvOS the canvas is fixed at 1080 pt, so `66vh` is a
        // CONSTANT (`TVTokens.Title.heroHeight`, pinned by the harness against the fraction it came from) and
        // nothing needs measuring. ⚠ What is left is the app's own working shape — a `ScrollView` whose content
        // is a plain `VStack`, exactly like the Home's rails.
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                measured("hero", hero(snapshot, height: TVTokens.Title.heroHeight))

                measured("below", below(snapshot))

                if snapshot.showsEpisodes {
                    episodes(snapshot)
                }

                // `.spacer-bottom { height:100px }` — the tail, so the last shelf is not flush with the
                // screen's bottom edge. ⚠ A fixed-height `Color.clear` and NOT a `Spacer()`: a `Spacer`
                // inside a `ScrollView`'s stack has no space to claim, so it collapses to nothing.
                Color.clear
                    .frame(height: TVTokens.Title.bottomSpacer)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// `.hero` — the full-bleed backdrop with the title block over its lower part.
    private func hero(_ snapshot: DetailSnapshot, height: CGFloat) -> some View {
        ZStack(alignment: .bottomLeading) {
            artwork(snapshot, height: height)
            scrim
            titleBlock(snapshot)
        }
        .frame(maxWidth: .infinity)
        .frame(height: height)
        .clipped()
    }

    /// ⚠ **The 16:9 BACKDROP, through `PosterImageView` — one artwork path for the whole app**, the same one
    /// the Home's hero band uses (same loader, same cookie handling, same log line, same poster fallback), so
    /// a hero whose artwork failed says why rather than showing a black band.
    ///
    /// ⚠ The prototype paints its hero with a two-tone CSS gradient and an `.hero-emblem` watermark because a
    /// mockup has no film behind it. Real keyart is strictly better, so the artwork is the source and the
    /// prototype's own wash is kept only as the fallback underneath it — the same trade `HeroBand` makes.
    private func artwork(_ snapshot: DetailSnapshot, height: CGFloat) -> some View {
        ZStack {
            LinearGradient(colors: [RKMColour.surface2, RKMColour.background],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
            PosterImageView(base: base, itemID: snapshot.detail.itemID, route: .backdrop)
        }
        .frame(maxWidth: .infinity)
        .frame(height: height)
        .clipped()
    }

    /// `.hero::after` — `linear-gradient(to top, void 0%, rgba(10,11,13,.65) 32%, transparent 68%)`, so the
    /// title over the artwork's lower half stays readable without a solid panel.
    private var scrim: some View {
        LinearGradient(stops: [
            .init(color: RKMColour.background, location: TVTokens.Title.scrimSolidStop),
            .init(color: RKMColour.background.opacity(TVTokens.Title.scrimMidOpacity),
                  location: TVTokens.Title.scrimMidStop),
            .init(color: RKMColour.background.opacity(0), location: TVTokens.Title.scrimClearStop),
        ], startPoint: .bottom, endPoint: .top)
        .allowsHitTesting(false)
    }

    /// `.title-block` — the title, its metadata line and the genre pills, left-aligned over the backdrop's
    /// lower part, capped at `920px` so a long title wraps rather than running to the screen edge.
    private func titleBlock(_ snapshot: DetailSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(snapshot.detail.name)
                .font(.system(size: TVTokens.Title.titleSize, weight: .bold))
                .foregroundStyle(RKMColour.primary)
                .lineLimit(2)
                .padding(.bottom, TVTokens.Title.titleGapBottom)

            metaLine(snapshot)

            if !snapshot.genres.isEmpty {
                genrePills(snapshot.genres)
                    .padding(.top, TVTokens.Title.metaGapBottom)
            }
        }
        .frame(maxWidth: TVTokens.Title.blockMaxWidth, alignment: .leading)
        .padding(.horizontal, LibraryRules.marginFromPrototype)
        .padding(.bottom, TVTokens.Title.blockPaddingBottom)
    }

    /// `.meta-line` — `year · runtime · certification`, then the ★ rating, which the DETAIL payload really
    /// carries (`community_rating`; ⚠ a LIBRARY row does not — `LibraryRules`' header).
    ///
    /// ⚠ The parts come from `DetailRules.metaBits`, which has already dropped the unknown ones, so there is
    /// no empty separator to trim and no third vocabulary for "no certification".
    ///
    /// ⚠⚠ Iterated by INDEX, deliberately: `ForEach(parts.enumerated(), id: \.offset) { index, part in … }`
    /// relies on destructuring a tuple parameter in a closure, which Swift only allows in some positions — and
    /// this file is compiled by nothing here. The index form has no such question in it.
    private func metaLine(_ snapshot: DetailSnapshot) -> some View {
        let parts = snapshot.metaBits
        return HStack(spacing: TVTokens.Title.metaGap) {
            ForEach(parts.indices, id: \.self) { index in
                if index > 0 {
                    // `.dot-sep { opacity:0.5 }` — the separator is dimmer than either side of it.
                    Text("·").foregroundStyle(RKMColour.secondary.opacity(0.5))
                }
                Text(parts[index]).foregroundStyle(RKMColour.secondary)
            }

            if !snapshot.rating.isEmpty {
                // `.rating { color: var(--gold-bright); font-weight:600 }` — the one gold thing in the block,
                // and the app's own `accentHover` is the token that stands for his `--gold-bright`.
                Text("★ \(snapshot.rating)")
                    .font(.system(size: TVTokens.Title.metaSize, weight: .semibold))
                    .foregroundStyle(RKMColour.accentHover)
            }
        }
        .font(.system(size: TVTokens.Title.metaSize))
        .lineLimit(1)
    }

    /// `.genre-pill` — *"non-focusable, purely informational here — filtering belongs to the library screen,
    /// not the detail screen"*, which is his own sentence and is why they are `Text` and not chips.
    private func genrePills(_ genres: [String]) -> some View {
        HStack(spacing: TVTokens.Title.pillGap) {
            ForEach(genres, id: \.self) { genre in
                Text(genre)
                    .font(.system(size: TVTokens.Title.pillFontSize))
                    .foregroundStyle(RKMColour.secondary)
                    .padding(.horizontal, TVTokens.Title.pillPaddingH)
                    .padding(.vertical, TVTokens.Title.pillPaddingV)
                    .overlay(
                        RoundedRectangle(cornerRadius: TVTokens.Title.pillRadius, style: .continuous)
                            .stroke(RKMColour.border, lineWidth: 1)
                    )
            }
        }
    }

    // MARK: - Everything under the hero

    private func below(_ snapshot: DetailSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            // ⚠⚠ **THE ACTION ROW COMES FIRST — IT IS HIS FILE'S OWN ORDER, AND PUTTING IT LATER IS HIS
            // ROUND-6 REPORT.** `title-view.html` runs `.hero` → `.actions` (`padding: 36px 64px 0`) →
            // `.synopsis` → the shelves, and `.actions` holds the `Play` control his prototype OPENS ON (`the
            // one-button path to watching`). Nothing competes with it: this screen is otherwise information
            // only, and the top bar's `Back` is above it.
            // ⚠ What it must NOT be is the THIRD thing down. The credits block below is not in his file at
            // all, and with it first the primary verb landed at ≈1030 pt of a 1080 pt screen — at the bottom
            // edge, on a screen whose only other focusable control is the top bar's `Back`. That is the shape
            // he described as *"not able to navigate anywhere"*.
            playAction(snapshot)
                .padding(.top, TVTokens.Title.actionTopPad)

            if snapshot.isInProgress, snapshot.resumePercent > 0 {
                resumeBar(percent: snapshot.resumePercent)
                    .padding(.top, TVTokens.Title.metaGapBottom)
            }

            // ⚠ His file's order after the actions is `.synopsis` → the cast shelf; the credits lines
            // (director / writers / studios) are Jellyfin information his file does not carry, so they sit
            // with the other text, between the synopsis and the shelf, where they cannot push a control.
            measured("synopsis", synopsis(snapshot))

            measured("credits", credits(snapshot))

            measured("cast", cast(snapshot))
        }
        .padding(.horizontal, LibraryRules.marginFromPrototype)
    }

    @ViewBuilder
    private func credits(_ snapshot: DetailSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let line = snapshot.directorLine {
                Text(line).font(.system(size: TVTokens.Title.castRoleSize)).foregroundStyle(RKMColour.secondary)
            }
            if let line = snapshot.writerLine {
                Text(line).font(.system(size: TVTokens.Title.castRoleSize)).foregroundStyle(RKMColour.secondary)
            }
            if !snapshot.studiosLine.isEmpty {
                Text(snapshot.studiosLine)
                    .font(.system(size: TVTokens.Title.castRoleSize))
                    .foregroundStyle(RKMColour.muted)
            }
        }
        .padding(.top, TVTokens.Title.sectionTitleGap)
    }

    /// ⚠ **The bar is the reason a preplay screen is worth having**: identical artwork tells a viewer nothing
    /// about where they stopped. Drawn only when the state can be stated honestly (`DetailRules.resumePercent`
    /// is 0 for a finished title and for one with no runtime), so an absent bar means "unknown".
    private func resumeBar(percent: Int) -> some View {
        HStack(spacing: TVTokens.Title.metaGap) {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(RKMColour.primary.opacity(0.22))
                    Capsule().fill(RKMColour.accent)
                        .frame(width: geometry.size.width * CGFloat(percent) / 100)
                }
            }
            .frame(width: TVTokens.Shelf.cardWidth, height: TVTokens.Shelf.progressHeight)
            Text("\(percent)% watched")
                .font(.system(size: TVTokens.Title.castRoleSize))
                .foregroundStyle(RKMColour.secondary)
        }
    }

    /// ⚠⚠ **THE ACTION ROW — AND PHASE C IS WHAT MADE IT HONEST.** B4 deliberately drew no Play control:
    /// the api had routes this app had not yet been taught to use, and a focusable button that apologises
    /// when pressed is exactly what `docs/ARCHITECTURE.md` §11 forbids. The player exists now, so the
    /// control does, and **its WORD was already a rule** — `DetailSnapshot.primaryVerb` ("Play" /
    /// "Resume S1E4" / "Play next") has been rendered by the Home's hero since B4, so the button and the
    /// sentence can never disagree about what pressing it does.
    ///
    /// ⚠ **ONE control, not his prototype's four.** `Trailer` needs `RemoteTrailers` on the detail payload
    /// and `Add to Watchlist` / `More` are acquisition/administration — the half of rkm-cinema that
    /// `apple/tvos/README.md` keeps on web/iOS. A row of controls this screen cannot honour is the thing
    /// this file's header has been refusing since B4.
    private func playAction(_ snapshot: DetailSnapshot) -> some View {
        Button {
            app.openPlayer(itemID: snapshot.detail.itemID, detail: snapshot.detail)
        } label: {
            HStack(spacing: TVTokens.Hero.actionSpacing) {
                Image(systemName: "play.fill")
                Text(snapshot.primaryVerb)
            }
        }
        .buttonStyle(CtaButtonStyle(kind: .primary))
        .accessibilityLabel(snapshot.primaryVerb)
    }

    /// `.synopsis` — *"max-width capped for readability (~60 characters per line) rather than spanning the
    /// full screen width"*. ⚠ `TVTokens.Title.synopsisMeasure` is that cap, converted from `62ch` with the
    /// prototype's own font size (SwiftUI has no `ch`), and the derivation is written beside it.
    @ViewBuilder
    private func synopsis(_ snapshot: DetailSnapshot) -> some View {
        if !snapshot.overview.isEmpty {
            Text(snapshot.overview)
                .font(.system(size: TVTokens.Title.synopsisSize))
                .lineSpacing(TVTokens.Title.synopsisLineSpacing)
                .foregroundStyle(RKMColour.primary.opacity(0.9))
                .frame(maxWidth: TVTokens.Title.synopsisMeasure, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, TVTokens.Title.synopsisTopPad)
        }
    }

    /// ⚠ **No headshots, and no scrolling.** tvOS draws the names on round initials — which is exactly what
    /// the prototype draws (`initials(name)` on a coloured field) and needs **no request per person**, where
    /// the web's `personHeadshotUrl` is one proxy call each. See this file's header for why the row is one row.
    ///
    /// ⚠ The initial's letters come from `ProfileRules.initials` — the SAME function the Profile Switcher's
    /// tiles and the top bar's avatar use, so the app has one answer to "what are this name's initials".
    @ViewBuilder
    private func cast(_ snapshot: DetailSnapshot) -> some View {
        if !snapshot.cast.isEmpty {
            VStack(alignment: .leading, spacing: TVTokens.Title.sectionTitleGap) {
                Text("Cast")
                    .font(.system(size: TVTokens.Title.sectionTitleSize, weight: .semibold))
                    .foregroundStyle(RKMColour.primary)

                HStack(alignment: .top, spacing: TVTokens.Title.trackGap) {
                    ForEach(snapshot.cast, id: \.id) { person in
                        castItem(person)
                    }
                    Spacer(minLength: 0)
                }
            }
            .padding(.top, TVTokens.Title.shelfTopPad)
            .frame(width: TVTokens.Title.castItemWidth, alignment: .leading)
        }
    }

    // MARK: - ⚠⚠ A MEASUREMENT, NOT A LAYOUT (added 2026-09-20 to answer his round-6 report)

    /// ⚠⚠ **THIS EXISTS TO BE DELETED, AND IT ANSWERS A QUESTION NOTHING ON THIS MACHINE CAN.**
    ///
    /// His round-6 report: *"THE WHOLE PAGE IS ZOOMED IN AND I CAN ONLY SEE A PORTION OF THE PAGE..MAY BE IT'S
    /// A RESOLUTION ISSUE IN DETAILS PAGE NOT SURE"*.
    ///
    /// Measured from the screenshot he sent (3840 × 2160 = a 1920 × 1080 pt canvas at 2×, and **every font on it
    /// measures at its token size, so the UI itself is not scaled**): the focused tab's label sits at x = 59.5 pt
    /// where `Bar.paddingH` + the brand + `tabSpacing` put it at ≈293 pt, and the bar's right-hand content (the
    /// profile avatar) is not on screen at all. That is a page WIDER than the canvas and shifted left — but
    /// every element in this file has a bound, and reading them cannot say which one is the outlier. So the
    /// round measures it instead of guessing:
    ///
    ///     detail-size: <label> = <w>×<h> pt at x=<global minX> y=<global minY>
    ///
    /// ⚠ **IT CANNOT AFFECT LAYOUT, WHICH IS THE ONLY REASON IT IS ALLOWED ON THIS SCREEN.** A `GeometryReader`
    /// in a `.background` is handed the view's size AFTER the view has laid out — the opposite of the reader
    /// that was DELETED from this screen's content in round 3, which was wrapped AROUND the focusable content
    /// so its frames were what the focus engine navigated on. Nothing measured here is focusable.
    private func measured<Content: View>(_ label: String, _ content: Content) -> some View {
        content.background {
            GeometryReader { proxy in
                Color.clear
                    .onAppear { report(label, proxy) }
                    .onChange(of: proxy.size) { _, _ in report(label, proxy) }
            }
        }
    }

    private func report(_ label: String, _ proxy: GeometryProxy) {
        let frame = proxy.frame(in: .global)
        RKMLog.info("detail-size: " + label + " = " + "\(Int(proxy.size.width))x\(Int(proxy.size.height)) pt"
                    + " at x=\(Int(frame.minX)) y=\(Int(frame.minY))", category: .app)
    }

    /// ⚠⚠ **THE ITEM IS HIS WIDTH, AND THAT IS A LAYOUT RULE, NOT A DETAIL.** His `.cast-item { width:150px }`
    /// was applied to the AVATAR only, so an item was as wide as the PERSON'S NAME — and a row of ten
    /// unbounded names is what made the whole page wider than the screen (see `DetailRules.castCapacity`).
    /// The name truncates inside the item (`lineLimit(1)`) exactly as his file does, instead of widening it.
    private func castItem(_ person: DetailPerson) -> some View {
        VStack(spacing: 0) {
            Text(ProfileRules.initials(person.name))
                .font(.system(size: TVTokens.Title.initialsSize, weight: .bold))
                .foregroundStyle(RKMColour.background)
                .frame(width: TVTokens.Title.avatarSize, height: TVTokens.Title.avatarSize)
                .background(RKMColour.castAvatar(hue: DetailRules.castHue(person)), in: Circle())
                .padding(.bottom, TVTokens.Title.avatarGapBottom)

            Text(person.name)
                .lineLimit(1)
                .font(.system(size: TVTokens.Title.castNameSize, weight: .semibold))
                .foregroundStyle(RKMColour.primary)
                .lineLimit(1)

            if !person.role.isEmpty {
                // ⚠ An empty role is DROPPED rather than drawn as a blank line — Jellyfin really does send
                // one (`DetailRules.castRows`' own note).
                Text(person.role)
                    .font(.system(size: TVTokens.Title.castRoleSize))
                    .foregroundStyle(RKMColour.muted)
                    .lineLimit(1)
            }
        }
        .frame(width: TVTokens.Title.castItemWidth)
        .accessibilityElement(children: .combine)
    }

    // MARK: - Episodes

    /// One season per heading, episodes underneath — ⚠ the grouping is `DetailRules.groupBySeason`, which
    /// sorts the season numbers and leaves the episodes in the server's order.
    ///
    /// ⚠ **A partial failure is RENDERED.** A series whose episode list could not be fetched looks exactly
    /// like a series with no episodes, so the sentence is on the screen (`DetailCopy.partialWarning`) rather
    /// than only in the log.
    @ViewBuilder
    private func episodes(_ snapshot: DetailSnapshot) -> some View {
        VStack(alignment: .leading, spacing: TVTokens.Title.sectionTitleGap) {
            if let warning = snapshot.partialWarning {
                Text(warning)
                    .font(.system(size: TVTokens.Title.castNameSize))
                    .foregroundStyle(RKMColour.warning)
            } else if snapshot.episodes.isEmpty {
                // ⚠ A real answer, not a fault: the server answered, and this series has no episodes the
                // profile may see.
                Text("No episodes yet")
                    .font(.system(size: TVTokens.Title.castNameSize))
                    .foregroundStyle(RKMColour.secondary)
            }

            ForEach(snapshot.seasons) { group in
                VStack(alignment: .leading, spacing: TVTokens.Title.pillGap) {
                    // ⚠ The web's own heading, verbatim (`ItemDetail.tsx`: `Season {group.season}`) — which
                    // is why season 0 (specials) reads "Season 0" here rather than being renamed.
                    Text("Season \(group.season)")
                        .font(.system(size: TVTokens.Title.sectionTitleSize, weight: .semibold))
                        .padding(.top, TVTokens.Title.pillGap)
                    ForEach(group.episodes) { episode in
                        episodeRow(episode)
                    }
                }
            }
        }
        .padding(.horizontal, LibraryRules.marginFromPrototype)
        .padding(.top, TVTokens.Title.shelfTopPad)
        .padding(.bottom, TVTokens.Title.bottomSpacer)
    }

    /// ⚠ **THE ROW CARRIES NO PLAY BUTTON** — the web's `EpisodeRow` ends in a Play/Resume/Replay control,
    /// and this phase cannot honour it. What the row DOES carry is the episode's state, computed by
    /// `DetailRules.episodeProgress` — the same function the phone's row reads, so the two surfaces cannot
    /// describe the same half-watched episode differently.
    private func episodeRow(_ episode: EpisodeItem) -> some View {
        let progress = DetailRules.episodeProgress(episode)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: TVTokens.Title.pillGap) {
                Text(DetailRules.episodeCode(episode))
                    .font(.system(size: TVTokens.Title.castRoleSize, weight: .bold))
                    .foregroundStyle(RKMColour.accent)
                    .frame(width: TVTokens.Title.castItemWidth * 0.5, alignment: .leading)
                Text(episode.name)
                    .font(.system(size: TVTokens.Title.castNameSize, weight: .medium))
                    .lineLimit(1)
            }
            Text(stateLine(episode, progress: progress))
                .font(.system(size: TVTokens.Title.castRoleSize))
                // ⚠ `Color.` on both sides: `.green` and `.secondary` are two DIFFERENT style types, and a
                // ternary over `ShapeStyle` does not typecheck.
                .foregroundStyle(episode.played ? RKMColour.success : RKMColour.secondary)
                .padding(.leading, TVTokens.Title.castItemWidth * 0.6)
        }
        .padding(.vertical, TVTokens.Title.pillGap)
        .padding(.horizontal, TVTokens.Title.pillGap)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RKMColour.primary.opacity(progress.inProgress ? 0.10 : 0.04),
                    in: RoundedRectangle(cornerRadius: TVTokens.Grid.cardRadius, style: .continuous))
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
