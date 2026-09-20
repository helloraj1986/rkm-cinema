import SwiftUI
import RKMServerKit

/// Item detail — screen #5, **rewritten in Phase W to `tvos_ux/2. LibraryViewandItemDetailsView/title-view.html`**.
///
/// ⚠⚠ **WHY IT WAS REWRITTEN RATHER THAN PATCHED, IN HIS OWN WORDS (2026-09-20):** *"the details view screen
/// is available but its resolution somehow not working … we should reuse the details screen component
/// wherever we can … rewrite the code if it is required rather than just patching up the existing details
/// screen"*. What the rewrite actually changed is STRUCTURAL, and that is the reason a patch could not have
/// done it:
///
///   1. **the top bar is an OVERLAY over the hero, not a band above it** — his `.topbar` is `position:fixed`
///      and the hero runs from `y = 0` under it;
///   2. **the hero is FULL-BLEED** — the app's screens now fill tvOS's 1920 × 1080 point canvas
///      (`AppRootView`, W1), so the artwork reaches both screen edges exactly as his `.hero` does;
///   3. **the action row is the first thing under the hero** (`padding: 36px 64px 0`), which is the band
///      order his file draws.
///
/// ⚠⚠ **AND THE FAULT BEHIND HIS REPORT WAS NOT ON THIS SCREEN AT ALL.** `KNOWN_ISSUES` #13's *"the whole
/// page is zoomed in and I can only see a portion of the page"* was the app laying this screen out inside
/// tvOS's safe area (1760 × 960 at (80, 60)) and THEN indenting by his own `64px` margin — a double inset
/// that left the content 9.1 % narrower than the design and made this screen's 712.8 pt hero **74 %** of the
/// height instead of the `66vh` his file asks for, which pushed `Play` off the bottom edge and opened the
/// screen scrolled with its hero cut. The fix is one `ignoresSafeArea()` at the root, and it applies to every
/// screen in the app — see `AppRootView`, and the trade it accepts is recorded in `TVTokens.Metric`.
///
/// ⚠ **Every decision this screen obeys is still in `DetailRules.swift`** (pure, RUN on Linux): the meta
/// line, the rating readout, the resume percentage, the season grouping, each episode's progress sentence,
/// the credits lines, the cast cap and the four states. This type lays that out and nothing else.
///
/// ⚠⚠ **WHAT IS STILL DELIBERATELY NOT BUILT — his answer to this phase's own question, and §11's rule
/// (*never offer what the server will refuse*) applies to each:**
///   * **the other three action buttons.** `Trailer` needs `RemoteTrailers` on the detail payload —
///     `ItemDetail` decodes 21 keys and none is a trailer (`Core/Models/DetailModels.swift`), so it is a
///     wire change of its own. `Add to Watchlist` and `More` are the acquisition/administration half of
///     rkm-cinema, which `apple/tvos/README.md` keeps on web/iOS and where a keyboard and forms exist;
///   * **the "Because you watched" shelf.** On the web it is not a library row at all — `SimilarRow.tsx`
///     **drops every title already in the library** and its cards open a TMDB page offering *Add to
///     watchlist* / *Download*, because `/api/jellyfin/similar` carries a **TMDB id and no Jellyfin item
///     id**. Replicating it on tvOS means building an acquisition surface, which is its own phase
///     (`docs/TVOS_LIBRARY_UI_PLAN.md` §1 row 3 and §5);
///   * **the bar's collapse-on-scroll** (his `.topbar` fades out with the page). It is the same class of
///     platform claim as the Home's F6, and that round settles it first — not this screen.
///
/// ⚠ **THE EPISODE LIST IS NOT IN HIS FILE AT ALL** (his title screen is a film), so a series keeps B4's
/// episode rows: that is real data the screen would otherwise have nowhere to put, and it is the one place
/// the app can say what an episode's progress is (`DetailRules.episodeProgress`, the phone's own rule).
struct DetailView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var store: DetailStore
    let base: URL

    /// ⚠⚠ **THE ONE PLACE A TELEVISION DIFFERS FROM ANOTHER TELEVISION (W3).** tvOS's point space is fixed
    /// at 1920 × 1080 on every device — a 4K panel draws the same points at `scale = 2.0` — so no LAYOUT here
    /// needs a panel check. ARTWORK does: a full-width hero is 3840 px on 4K and 1920 px on 1080p, and the
    /// route's own default (1600, the web app's number) is 2.4× short of the first. `displayScale` is the
    /// platform's own answer and is never a constant in this file.
    @Environment(\.displayScale) private var displayScale

    /// ⚠⚠ **HIS PROTOTYPE'S OWN DECISION, AND HIS ROUND-8 REPORT IS WHY IT IS LOAD-BEARING:** *"I CAN SE
    /// ETHE PLAY BUTTON BUT CANT NAVIGATE FROM TOP TO THE PLAY BUTTON"*. `Play` is the one focusable control
    /// this screen draws and it sits below a 712.8 pt hero that has nothing focusable in it, while the focused
    /// `Back` tab is on the bar that floats over that hero. The screen therefore opens with the ring ON
    /// `Play` (`title-view.html`: *"default focus: play/pause"*), so the primary verb is reachable even if a
    /// direction search down from the bar is not.
    ///
    /// ⚠⚠ **THE MECHANISM IS A HYPOTHESIS, STATED AS ONE.** No engine runs on this machine. **The falsifier is
    /// his own:** does the ring start on `Play`, does Select play the film, and can the arrows reach the top
    /// bar from there?
    @FocusState private var playFocused: Bool

    /// ⚠⚠ **THE ARTWORK'S OWN COLOUR, AS SAMPLES THE PURE RULE CAN READ (W13).** Filled once by the page's
    /// `PosterImageView` (`onImage`), and consumed by `artworkScrim` through `ArtworkTint.scrim(for:)`.
    ///
    /// ⚠ `nil` is a REAL state and the FIRST one: it is what the page has before the artwork arrives, and what it
    /// keeps if the artwork fails. `ArtworkTint.scrim(for: nil)` answers it with the neutral scrim, so the page is
    /// never drawn on raw art waiting for a colour that may not come.
    @State private var artworkTint: ArtworkRGB?

    var body: some View {
        // ⚠⚠ **THE BAR IS AN OVERLAY AGAIN, AND THE REASON IS ARITHMETIC RATHER THAN TASTE.** W3 moved the bar
        // INSIDE the scroller to answer his round-9 report (*"i am on back to browse button but i cant come down
        // to play button through navigation"*), and his round-10 reply is that the dead end is STILL there:
        // *"still stuck on back to browse cannot come down using keyboard"*. What that structural change cost,
        // provably, on the way:
        //
        //   `DetailRules.titlePageHeight` is the PAGE — hero + action row + resume bar + synopsis + credits +
        //   cast row — and it sums to **1058.5 pt of a 1080 pt screen** (21.5 pt of air) **with the bar counted
        //   as ZERO**, because in his file the bar is `.topbar { position: fixed }`. As a BAND the bar adds its
        //   own `Bar.clearance` (115.2 pt), so the scroller's content became **1173.7 pt — 93.7 pt over a screen
        //   that cannot scroll**, since nothing below `Play` takes focus (every band there is information, and
        //   `ARCHITECTURE.md` §11 forbids a control whose only outcome is an apology). That is precisely the
        //   class of defect W2 existed to remove.
        //   ⇒ The overlay restores the fit AND his file's own structure, and the dead end is attacked with the
        //   tool the platform documents for it — see below.
        //
        // ⚠⚠ **`.focusSection()` ON THE BAR AND ON THE CONTENT — A HYPOTHESIS, STATED AS ONE.** The focus
        // engine's direction search prefers to move between SECTIONS, and a group of one focusable control above
        // a group of one focusable control is what `View.focusSection()` exists for (tvOS 15+). ⚠ It adds no
        // control and removes none: it only tells the engine how the screen is divided. **No focus engine runs
        // on this machine, so none of this is proved** — which is why the evidence is LOGGED rather than argued.
        // `TopBar` publishes every change of its own focus (`bar-focus: <id>`) and this screen publishes
        // `Play`'s (`detail-focus: play=…`), so pressing `Down` with the ring on `Back` prints one of exactly
        // two stories: **`bar-focus: nil` then `detail-focus: play=true`** (it moved — any remaining complaint
        // is about something else), or **`bar-focus: back` staying put with no `play=true`** (the engine found
        // no candidate at all, and the geometry is what changes next).
        //
        // ⚠ Every `measured(…)` call on this screen is a `.background` reader — handed the view's size AFTER
        // layout, so it cannot change it. ⚠ The reader this screen DELETED in round 3 was the other kind:
        // wrapped AROUND the focusable content, which is what the focus engine then navigated on. KNOWN_ISSUES
        // #11 — *"i cant come to the titles by pressing down arrow"* — was fixed in `BrowseView` by deleting
        // exactly that shape, and it is not coming back. ⚠⚠ **ROUND 11 WENT ONE STEP FURTHER AND DELETED THE
        // `ScrollView` ITSELF** — the device fact that decided it is in the note inside the `ZStack`.
        ZStack(alignment: .topLeading) {
            // ⚠⚠ **THE ARTWORK IS THE PAGE — HIS DECISION, 2026-09-20: *"can we make it a background of the
            // details page with using gradients color depening on the poster so that the text on the details page
            // can be seen clearly"*.** It used to be a 313.2 pt BAND with the title block over its lower part; it
            // is now the whole screen, and the title block is a term in the page's flow
            // (`DetailRules.titlePageHeight`). ⚠ Plan, the +37.6 pt it costs and the six falsifiers:
            // `docs/TVOS_TITLE_ARTWORK_PLAN.md`.
            // ⚠ It is drawn ONLY when there is a title: the three message states have no artwork to show behind
            // them and keep the app's own background.
            artworkPage

            // ⚠⚠ **AND THERE IS NO `ScrollView` HERE ANY MORE — HIS ROUND-11 OBSERVATION IS WHAT SETTLED IT:**
            // *"the navigation for individual title works when there is resume button but it dont comes down
            // when there is play button so i think its unable to find the play button on the individual titles
            // details page"*. ⚠⚠ **Read that twice, because it is the first fact in this whole defect that came
            // from the device rather than from a theory:** the SAME screen, the SAME button, the SAME code — and
            // it works on a title whose page is LONGER (an in-progress title draws `Resume (n%)` plus a progress
            // bar beneath the button) and fails on one whose page is SHORTER. The BUTTON's geometry does not
            // change between those two cases. **What changes is the page's relationship to the container it sits
            // in** — and that is the container's business, which is why the container is gone.
            //
            // ⚠⚠ **A scroller that can NEVER scroll is a boundary the focus engine must cross for nothing.**
            // The page FITS by construction — `DetailRules.titlePageHeight` is 1058.5 pt of a 1080 pt screen and
            // the harness pins it — and W2 established WHY it has to fit: *a tvOS `ScrollView` scrolls only
            // when focus moves onto something inside it*, and every band below `Play` is information
            // (`ARCHITECTURE.md` §11 forbids a control whose only outcome is an apology). ⇒ This `ScrollView`
            // could never have scrolled, for any data: it contributed no behaviour and one extra container. ⚠
            // Deleting a container is this repo's own precedent, twice — `KNOWN_ISSUES` #11 was fixed in
            // `BrowseView` by deleting one, and the three shapes that came before this one all KEPT this one.
            //
            // ⚠ `measured("screen", …)` stays, on the GROUP, so `detail-size: screen` still reports the box
            // (`1920x1080 pt at x=0 y=0`) — that readout is `KNOWN_ISSUES` #13's falsifier and it does not get
            // to disappear along with the scroller.
            measured("screen", Group {
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
            .focusSection()
            // ⚠ `maxHeight: .infinity` because the scroller used to fill the screen: every state must keep
            // starting at the TOP edge rather than floating to the middle of a content-hugging stack.
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            // ⚠⚠ **AND THE SECTION MODIFIER GOES OUTSIDE THE FRAME — ORDER MATTERS, AND THIS WAS WRONG.** A
            // focus section is a movement TARGET, and the engine aims at *the section's frame* (Apple:
            // *"the focus sections have to take up more space than their contents"*). Applying `.focusSection()`
            // inside the `.frame(…)` leaves the section the size of the content that hugs it, so it is not the
            // full-width box beneath the bar that the gesture needs. The action row's own section (see `below`)
            // is the precise fix; this one is the coarse one, and both are the platform's own mechanism.
            .focusSection())

            topBar
                // ⚠ Same rule, the other direction: a section is aimed at BY its frame, so the bar's section
                // spans the full width rather than hugging its own controls. (It is also what makes `Up` from
                // `Play` reliable, which is the direction that has always worked.)
                .frame(maxWidth: .infinity, alignment: .leading)
                .focusSection()
        }
        // ⚠⚠ The screen's default focus — see `playFocused`. `.defaultFocus` is the PLATFORM's way to say
        // this (the focus engine owns every move from there); nothing here computes a neighbour.
        .defaultFocus($playFocused, true)
        // ⚠⚠ **AND THE SCREEN GETS ITS OWN WAY OUT.** The tvOS MENU button is the canonical Back and it does
        // not depend on the bar being on screen or reachable. `ARCHITECTURE.md` ranks a dead end above any
        // cosmetic rule.
        .onExitCommand { app.closeDetail() }
        // ⚠ The falsifier for the hypothesis above, one line per CHANGE of focus — see this body's own note.
        .onChange(of: playFocused) { _, focused in
            RKMLog.info("detail-focus: play=\(focused)", category: .app)
        }
        // ⚠ `.task`, not `.onAppear`: the load is async, and the store is built per item (`AppModel`), so
        // this runs once for the item that is open.
        .task {
            await store.load()
        }
    }

    // MARK: - The top bar

    /// ⚠ **The app's own bar, with ONE tab** — his title screen draws *"the wordmark and a back link"* and no
    /// library tabs, which is exactly what this is. ⚠ It carries the profile avatar too, because the avatar
    /// is where `Sign out`, `Change server` and `Manage profiles` already live and the bar is the only surface
    /// on this screen that can hold them.
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
        // ⚠⚠ **`Bar.clearance` IS BACK, AND IT IS BACK FOR THE SAME REASON THE BAR IS AN OVERLAY AGAIN.** The
        // bar floats over the content (his `.topbar { position: fixed }`), so a state whose first line is a
        // WORD has to start below it — artwork may bleed under the bar, a sentence may not. ⚠ The content state
        // needs no equivalent: its first band is the full-bleed hero, which is SUPPOSED to run under the bar.
        .padding(.leading, LibraryRules.marginFromPrototype)
        .padding(.top, TVTokens.Bar.clearance)
        .padding(.bottom, TVTokens.Grid.emptyPaddingV)
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
        // ⚠ Same reason as `loading`: the bar floats over this screen, so a sentence starts below it.
        .padding(.top, TVTokens.Bar.clearance)
        .padding(.bottom, TVTokens.Grid.emptyPaddingV)
        .buttonStyle(.bordered)
    }

    // MARK: - The title

    private func content(_ snapshot: DetailSnapshot) -> some View {
        // ⚠⚠ **NO `GeometryReader` WRAPPED AROUND THE CONTENT — AND THAT IS A FOCUS RULE, NOT A TIDY-UP.**
        // The reader was removed in round 3: it was here to measure `66vh`, and on tvOS the box is FIXED
        // (`TVTokens.Metric.screenHeight`), so the fraction is a constant and nothing needs measuring. A
        // reader whose frames the focus engine navigates on is the structure `BrowseView.cardWidth` blames
        // for his *"i cant come to the titles by pressing down arrow"* (KNOWN_ISSUES #11).
        //
        // ⚠ `measured("page", …)` IS W2's FALSIFIER: **the fit is a claim, and this is the instrument that
        // checks it.** `DetailRules.titlePageHeight` says the page is 1058.5 pt of a 1080 pt screen — if this
        // line logs MORE than 1080, the cast row is below the fold on a screen that cannot scroll and one
        // number (the hero's fraction, or `Metric.lineHeightRatio`) is what moves.
        measured("page", VStack(alignment: .leading, spacing: 0) {
            // ⚠⚠ **THE PAGE STARTS UNDER THE BAR, AND THE BAR IS AN OVERLAY OVER THE ARTWORK.** The bar floats
            // (his `.topbar { position: fixed }`), so its own height is the first thing the flow has to clear —
            // ⚠ ART may sit under the bar, a WORD may not. ⚠⚠ **It is deliberately NOT a term in
            // `DetailRules.titlePageHeight`**: the bar covers artwork in every layout, so that 115.2 pt is spent
            // either way, and counting it twice is the one arithmetic error that makes this change look
            // impossible (that function's note says so).
            Color.clear
                .frame(height: TVTokens.Bar.clearance)

            measured("title-block", titleBlock(snapshot))

            below(snapshot)

            if snapshot.showsEpisodes {
                episodes(snapshot)
            }

            // ⚠⚠ **THE TAIL IS GONE (W13), AND IT WAS A REAL OVERFLOW.** `.spacer-bottom { height:100px }` was
            // DRAWN here but never counted in `DetailRules.titlePageHeight` — 126 pt of page no gate could see —
            // and its whole job was to keep the last shelf off the edge of a scroller, which this screen has not
            // had since round 11. ⇒ Deleted rather than budgeted for, so the budget and the screen finally
            // describe the same page.
        }
        .frame(maxWidth: .infinity, alignment: .leading))
    }

    /// ⚠⚠ **THE PAGE'S ARTWORK — THE WHOLE SCREEN, WITH THE SCRIM BUILT FROM ITS OWN COLOUR (W13).**
    ///
    /// ⚠ **The shape treatment is NOT re-decided here.** `PosterRules.treatment` already answers it, and its own
    /// comment names *"a hero band, a 16:9 card, **the whole page**"*: a 16:9 backdrop fills, and **a 2:3 poster —
    /// the fallback for a title with no keyart — is shown WHOLE over a blurred, dimmed copy of itself**, which is
    /// the fix `KNOWN_ISSUES` #16 bought (*"i can only see 1/3rd of the poster"*). ⚠ The blurred copy is exactly
    /// what lets a portrait poster cover a whole page without cropping it, so this layout INHERITS that fix
    /// instead of re-testing it.
    ///
    /// ⚠ **It asks for the pixels the PAGE needs** (`PosterURL.width(points:scale:route:)`, W3): 3840 px on a 4K
    /// panel, 1920 px on a 1080p one — the route's own 1600 default is the WEB app's number and is 2.4× short.
    @ViewBuilder
    private var artworkPage: some View {
        if case .content(let snapshot) = store.state {
            ZStack {
                PosterImageView(base: base,
                                itemID: snapshot.detail.itemID,
                                route: .backdrop,
                                width: PosterURL.width(points: TVTokens.Metric.screenWidth,
                                                       scale: displayScale,
                                                       route: .backdrop),
                                // ⚠⚠ The samples arrive HERE, once, off bytes this page was decoding anyway —
                                // and what they MEAN is `ArtworkTint`'s decision, not this view's.
                                onImage: { artworkTint = ArtworkTint.tint(samples: $0.rkmSampleGrid()) })

                artworkScrim
            }
            .frame(width: TVTokens.Metric.screenWidth, height: TVTokens.Metric.screenHeight)
            .clipped()
            // ⚠ Decorative: the title block already carries the name, and a screen reader should not hear the art.
            .accessibilityHidden(true)
        } else {
            RKMColour.background
        }
    }

    /// ⚠⚠ **THE SCRIM, AND EVERY NUMBER IN IT COMES FROM `ArtworkTint.scrim(for:)` — A PURE RULE, RUN ON LINUX.**
    /// This view draws what that rule returns and decides nothing: which colour the artwork is, how deep the wash
    /// must be for that colour's luminance, and where the tint fades out are all arithmetic that would otherwise
    /// be verified only by his eyes on a television.
    ///
    /// ⚠ Three layers, because they do three different jobs:
    ///   1. **a flat wash over the whole page** — the term that guarantees contrast in the MIDDLE, where the
    ///      synopsis, the credits and the cast sit over raw artwork;
    ///   2. **the artwork's own colour at the top edge**, where the bar and the title block are;
    ///   3. **a floor at the bottom edge**, for the cast row.
    ///
    /// ⚠⚠ **BEFORE THE ARTWORK ARRIVES — and if it fails — `ArtworkTint.scrim(for: nil)` returns the neutral
    /// scrim**, so the page is legible on its own background for that first frame rather than flashing raw art.
    private var artworkScrim: some View {
        let scrim = ArtworkTint.scrim(for: artworkTint)
        return ZStack {
            RKMColour.background.opacity(scrim.wash)

            LinearGradient(stops: [
                .init(color: RKMColour.artwork(scrim.tintColour, opacity: scrim.tintAlpha), location: 0),
                .init(color: RKMColour.artwork(scrim.tintColour, opacity: 0), location: scrim.tintFade),
            ], startPoint: .top, endPoint: .bottom)

            LinearGradient(stops: [
                .init(color: RKMColour.background.opacity(0), location: scrim.tintFade),
                .init(color: RKMColour.background.opacity(scrim.baseAlpha), location: 1),
            ], startPoint: .top, endPoint: .bottom)
        }
        // ⚠ The scrim is paint: it must never intercept a press, and it holds no control of its own.
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
            // ⚠⚠ **THE ACTION ROW COMES FIRST — IT IS HIS FILE'S OWN ORDER** (`.hero` → `.actions` → the
            // shelves), and `.actions` holds the `Play` control his prototype OPENS ON. Nothing competes with
            // it: this screen is otherwise information only, and the bar floats above it.
            // ⚠⚠ **THE ACTION ROW IS ITS OWN FOCUS SECTION, AND THIS IS THE ACTUAL FIX FOR `KNOWN_ISSUES` #15.**
            //
            // Apple's `focusSection()` documentation, verbatim: *"swiping right on any of the buttons in the
            // '1'-'3' group would do nothing, since the focus system finds no focusable views **directly to
            // their right**."* ⇒ **`Down` from the bar's `Back to Browse` tab only moves if a focusable — or a
            // focus SECTION — sits directly BENEATH it.**
            //
            // ⚠⚠ **AND THAT IS EXACTLY WHY HIS DEVICE FACT WAS THE ONE THAT CRACKED IT:** the tab sits at
            // x ≈ 300–450 (after the `RKM · CINEMA` wordmark). `Resume (9%)` is a LONG label, so the button
            // reaches x ≈ 340 — it overlaps the tab's band and `Down` works. `Play` is four characters, ends
            // near x ≈ 250 — **nothing is directly beneath the tab, so the gesture fails.** The label's WIDTH
            // was the whole difference, which is why moving the bar, the scroller and the hero changed nothing.
            //
            // ⇒ WWDC23's focus cookbook gives the remedy in one line: *"mark the bottom button's container as a
            // focus section… **to be effective, the focus sections have to take up more space than their
            // contents.**"* This frame makes the row span the full screen width, so the section's frame reaches
            // under the tab, and the engine delivers focus to the first focusable inside it — `Play`.
            //
            // ⚠ This is the app's ONE piece of focus machinery and it is the PLATFORM's own tool: no frame is
            // measured and no neighbour is computed (the deleted `RailFocus.swift` is still deleted).
            playAction(snapshot)
                .padding(.top, TVTokens.Title.actionTopPad)
                .frame(maxWidth: .infinity, alignment: .leading)
                .focusSection()

            if snapshot.isInProgress, snapshot.resumePercent > 0 {
                resumeBar(percent: snapshot.resumePercent)
                    .padding(.top, TVTokens.Title.metaGapBottom)
            }

            // ⚠ His file's order after the actions is `.synopsis` → the cast shelf; the credits lines
            // (director / writers / studios) are Jellyfin information his file does not carry, so they sit
            // with the other text, between the synopsis and the shelf, where they cannot push a control.
            synopsis(snapshot)

            credits(snapshot)

            measured("cast-row", cast(snapshot))
        }
        .padding(.horizontal, LibraryRules.marginFromPrototype)
    }

    @ViewBuilder
    private func credits(_ snapshot: DetailSnapshot) -> some View {
        VStack(alignment: .leading, spacing: TVTokens.Title.creditLineGap) {
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
    ///
    /// ⚠ Not in his file — his mockup is an unwatched film — and kept because it is the one thing on this
    /// screen that his file could not have had. Recorded rather than dropped as "not in the design".
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
    /// ⚠ **ONE control, not his prototype's four** — see this file's header for the measurement behind each
    /// of the three that are absent. ⚠ Its chrome is the app's ONE action-button implementation
    /// (`CtaButtonStyle`) with set 2's own measurements (`metrics: .title`): his `.btn` is `19px / 16px 30px
    /// / r14` with a `2px --gold-bright` ring and a glow, where set 1's hero CTA is `1.1u / 0.85u 1.8u / 0.9u`
    /// with a white one.
    private func playAction(_ snapshot: DetailSnapshot) -> some View {
        Button {
            app.openPlayer(itemID: snapshot.detail.itemID, detail: snapshot.detail)
        } label: {
            HStack(spacing: TVTokens.Hero.actionSpacing) {
                Image(systemName: "play.fill")
                Text(snapshot.primaryVerb)
            }
        }
        .buttonStyle(CtaButtonStyle(kind: .primary, metrics: .title))
        .focused($playFocused)
        .accessibilityLabel(snapshot.primaryVerb)
    }

    /// ⚠ `.synopsis` — *"max-width capped for readability (~60 characters per line) rather than spanning the
    /// full screen width"*. ⚠ `TVTokens.Title.synopsisMeasure` is that cap, converted from `62ch` with the
    /// prototype's own font size (SwiftUI has no `ch`), and the derivation is written beside it.
    ///
    /// ⚠⚠ **AND IT IS CAPPED AT `Title.synopsisLineLimit` LINES (W2) — HIS CALL: *"cap it at 3 lines"*.** This
    /// is the one band on the screen whose height is the DATA's rather than the design's, and the page has to
    /// fit because nothing below it can pull focus (`DetailRules.titlePageHeight`). A longer overview
    /// ellipsises rather than pushing the cast row off a screen nobody can scroll.
    @ViewBuilder
    private func synopsis(_ snapshot: DetailSnapshot) -> some View {
        if !snapshot.overview.isEmpty {
            Text(snapshot.overview)
                .font(.system(size: TVTokens.Title.synopsisSize))
                .lineSpacing(TVTokens.Title.synopsisLineSpacing)
                .foregroundStyle(RKMColour.primary.opacity(0.9))
                .lineLimit(TVTokens.Title.synopsisLineLimit)
                .frame(maxWidth: TVTokens.Title.synopsisMeasure, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, TVTokens.Title.synopsisTopPad)
        }
    }

    /// ⚠ **No headshots, and no scrolling.** tvOS draws the names on round initials — which is exactly what
    /// the prototype draws (`initials(name)` on a coloured field) and needs **no request per person**, where
    /// the web's `personHeadshotUrl` is one proxy call each. See this file's header for why the row is ONE row.
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
        }
    }

    // MARK: - ⚠⚠ A MEASUREMENT, NOT A LAYOUT

    /// ⚠⚠ **THIS EXISTS TO BE DELETED, AND IN PHASE W IT ANSWERED THE QUESTION IT WAS ADDED FOR.**
    ///
    /// His round-6 report: *"THE WHOLE PAGE IS ZOOMED IN AND I CAN ONLY SEE A PORTION OF THE PAGE..MAY BE IT'S
    /// A RESOLUTION ISSUE IN DETAILS PAGE NOT SURE"*. Round 9's file log answered it —
    /// `detail-size: screen = 1760x960 pt at x=80 y=60` — i.e. the box was the canvas MINUS its overscan
    /// inset, which the app's own margin was then added on top of. W1 fixed that at the root.
    ///
    /// ⚠ **W-F7 IS THE FALSIFIER AND IT IS THIS LINE**: after W1 the screen must report
    /// **`1920x1080 pt at x=0 y=0`**. If it still reports `1760x960 at x=80 y=60`, the double inset is still
    /// there and this phase did not land. The labels kept are the CANVAS (`screen`), the BAR (`bar` — which
    /// now floats, so its `y` should be 0) and the HERO (`hero` — which should span the full width and start
    /// at `y = 0` under the bar).
    ///
    /// ⚠ Read them from the FILE log, which needs no panel and no scrolling:
    /// `find "$(xcrun simctl get_app_container booted com.helloraj1986.RKMCinemaTV data)" -name rkm-tvos.log`
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
        // ⚠⚠ No bottom tail any more (W13) — see `content`'s note: it was drawn but never budgeted, and the
        // scroller it existed for is gone. ⚠ The episode list is the one band that can make this page LONGER
        // than `DetailRules.titlePageHeight` budgets (a series is not the case that function's terms describe),
        // which is the same exposure it has always had: nothing below `Play` takes focus, so it cannot be
        // scrolled to. Recorded rather than newly introduced.
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
