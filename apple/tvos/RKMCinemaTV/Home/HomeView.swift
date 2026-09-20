import SwiftUI
// ⚠ `RKMServerKit` for `RKMLog` — and this import is the whole reason Phase B2's first Mac round failed.
// `apple/scripts/check-imports.py` did not cover the app's OWN module until that failure (the table was
// written for Apple's frameworks, and nobody asked whether `RKMServerKit` needed the same rule), and this
// file is SwiftUI, so `check-apple-typecheck.sh`'s list does not include it either. Two gates, one blind
// spot each, and the round found it. The checker now has the rule AND a `--selftest` that pins it.
import RKMServerKit

/// The Home screen — Phase B's first real content screen, and **Phase U3's redesign of it**.
///
/// ⚠ **THE WAYS OUT STAY.** Phase A's note applies unchanged: a TV screen with no focusable exit is a dead
/// end, and a dead end on a TV is a phone call. U3 moved them rather than removing them: the top bar's avatar
/// button opens the PROFILE SWITCHER, which is where `Change profile`, `Sign out`, `Change server` and the
/// administrator's `Manage profiles` already live — one press away, and the buildspec's own instruction
/// ("fold Settings into the profile menu") is the same move.
///
/// ⚠ **Everything this screen SHOWS is decided in `HomeRails.swift`**, which is pure and executed on Linux:
/// which rails exist, their order, their caps, which title is the hero, and which of the four states
/// (loading / content / empty / failed) the screen is in. This type lays that out, and nothing else. A state
/// decision made here would be a decision no test could reach.
///
/// ⚠⚠ **THE REDESIGN'S THREE PIECES, all in `docs/TVOS_UX_PLAN.md` §1b:** the top bar (tabs from
/// `BrowseRules.browseEntries` — the profile's OWN libraries, never a literal list), the hero band (whose
/// every word and number is a mirrored web rule), and the card's type badge. ⚠ **No focus arithmetic
/// anywhere** — §3 of the plan: the rail is a `ScrollView` of focusable cards and that is the platform's
/// business. The two focus-adjacent behaviours this screen owns (the hero's de-duplication, and the top bar's
/// recede) are stated as falsifiers **F4** and **F6** in the round, not asserted here.
struct HomeView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var store: HomeStore
    let base: URL

    /// ⚠ The Playback placeholder, exactly as B4's detail screen shows it: the primary button cannot start a
    /// film (Phase C is parked), so it says where playback comes from instead of doing nothing.
    @State private var playbackVerb: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            topBar

            Group {
                if !store.hasLoaded && store.isLoading {
                    loading
                } else if let placeholder = store.snapshot.placeholder {
                    message(placeholder.title, placeholder.sub)
                } else {
                    content
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

            footer
        }
        // ⚠ `.task` and not `.onAppear`: the load is async and the screen must not be re-fetched by a
        // re-render — `HomeStore.load()` is idempotent in effect but each call is five requests.
        .task {
            await store.load()
        }
        .overlay {
            if let verb = playbackVerb {
                playbackNotice(verb)
            }
        }
    }

    // MARK: - The top bar

    /// ⚠⚠ **THE TABS ARE THE PROFILE'S LIBRARIES, from the SAME rule Browse uses** (`BrowseRules`), so the
    /// bar and the Browse screen can never disagree — the buildspec's fixed list is rejected in writing
    /// (`docs/TVOS_UX_PLAN.md` §1b), and falsifier **F3** is what a round would catch it with.
    ///
    /// ⚠ **The `Browse` tab is a FALLBACK, and it exists exactly when the tabs cannot do their job**: a
    /// profile with no libraries at all would otherwise have a top bar with nothing in it and no way into the
    /// Browse screen (which is the screen that EXPLAINS the empty config). It is not offered beside real tabs,
    /// because then it would duplicate them.
    private var topBar: some View {
        TopBar(tabs: topBarTabs,
               initials: ProfileRules.initials(app.session?.currentProfile?.name ?? ""),
               // ⚠ `nav.failedMessage` and NOT a `navFailure` accessor: this line is what U5's first Mac
               // round died on (`value of type 'HomeSnapshot' has no member 'navFailure'`) — a member that
               // was written in this view and never in the model, which nothing on this machine could catch.
               // `NavOutcome`'s own member is the shortest truthful path, and `check-tvos-members.py` now
               // checks exactly this class of access before a round is spent on it.
               failure: store.snapshot.nav.failedMessage,
               onProfile: { Task { await app.changeProfile() } })
    }

    /// ⚠⚠ **THE TABS ARE THE PROFILE'S LIBRARIES, from the SAME rule Browse uses, and `BrowseRules.tabPlan`
    /// IS that rule as of Phase V.** It used to be built here inline; the Library screen needs the same row
    /// with a different tab marked current, which is exactly the shape of this repo's most-repeated defect
    /// ("one rule in two places"), so the DECISION moved into the pure file — where it is RUN — and this
    /// property only attaches the closures.
    ///
    /// ⚠ The `Browse` fallback inside `tabPlan` is not cosmetic: a profile with no libraries would otherwise
    /// have an empty bar and **no way into the one screen that explains the empty config**.
    private var topBarTabs: [TopBarTab] {
        // ⚠ The prototype marks the tab you are on (`[aria-current="true"]` → white and semibold). On this
        // screen that is always `Home`; a library tab the viewer has not entered cannot be current here.
        BrowseRules.tabPlan(entries: store.snapshot.navEntries, current: .home).map { plan in
            TopBarTab(id: plan.id,
                      title: plan.title,
                      isCurrent: plan.isCurrent,
                      // ⚠ An unresolved library keeps its tab and its warning and simply cannot be
                      // selected — `BrowseRules`' rule, on the top bar as well as in Browse.
                      isEnabled: plan.isEnabled,
                      warning: plan.warning,
                      action: { go(to: plan) })
        }
    }

    /// ⚠ The closures for `BrowseRules.tabPlan`'s three kinds — the only part of the bar this screen owns.
    private func go(to plan: BrowseRules.LibraryTabPlan) {
        switch plan.kind {
        case .home:
            app.showHome()
        case .browse:
            app.showBrowse()
        case .library:
            // ⚠ An unresolved library is `.disabled` in the bar, so this is only ever reached with a real
            // folder — the fallback keeps the branch total rather than force-unwrapping a `String?`.
            if let folderID = plan.folderID {
                app.openLibrary(folderID: folderID)
            } else {
                app.showBrowse()
            }
        }
    }

    // MARK: - The three non-content states

    private var loading: some View {
        VStack(alignment: .leading, spacing: 16) {
            ProgressView()
                .controlSize(.large)
            Text("Loading your library…")
                .font(.system(size: 24))
                .foregroundStyle(RKMColour.secondary)
        }
        .padding(TVTokens.Metric.safeMargin)
    }

    private func message(_ title: String, _ sub: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title)
                .font(.system(size: 36, weight: .semibold))
            Text(sub)
                .font(.system(size: 24))
                .foregroundStyle(RKMColour.secondary)
            // ⚠ The retry is a real Button, so it is focusable — an error screen whose only action cannot
            // be reached with the remote is the dead end this app keeps designing out.
            Button("Try again") { Task { await store.load() } }
                .font(.system(size: 22))
                .padding(.top, 6)
        }
        .padding(TVTokens.Metric.safeMargin)
        .buttonStyle(.borderedProminent)
    }

    // MARK: - The hero and the rails

    private var content: some View {
        ScrollView(.vertical, showsIndicators: false) {
            // ⚠ `2u` between sections and a `3u` tail, both the prototype's (`.shelf { padding: 2u 0 0 }`,
            // `.tv-scroll { padding-bottom: 3u }`) — a shelf that ends flush against the screen edge reads as
            // cropped.
            VStack(alignment: .leading, spacing: TVTokens.u * 2) {
                if let hero = store.snapshot.hero {
                    HeroBand(item: hero,
                             isContinueWatching: store.snapshot.heroIsContinueWatching,
                             base: base,
                             onPrimary: { showPlaybackPlaceholder(for: hero) },
                             onDetails: { open(hero) })
                }

                ForEach(store.snapshot.rails) { rail in
                    RailView(rail: rail, base: base, onSelect: open)
                }
            }
            // ⚠ The hero is edge-to-edge and the shelves keep the screen margin: the band's artwork is meant
            // to bleed, and `RailView`/`HeroBand` own their own horizontal padding (both read
            // `TVTokens.Metric.safeMargin` / the prototype's `4.2u`).
            .padding(.bottom, TVTokens.u * 3)
        }
    }

    /// ⚠ The rows that FAILED, said out loud. A row that did not load and a row that is genuinely empty look
    /// identical on screen, and only one of them is worth pressing `Try again` about — so the difference is
    /// written down rather than left to the viewer to guess. Hidden when nothing failed.
    @ViewBuilder
    private var footer: some View {
        if !store.snapshot.failedRowTitles.isEmpty {
            Text("Couldn't load: \(store.snapshot.failedRowTitles.joined(separator: ", "))")
                .font(.system(size: 20))
                .foregroundStyle(RKMColour.warning)
                .padding(.horizontal, TVTokens.Metric.safeMargin)
                .padding(.bottom, 30)
        }
    }

    // MARK: - Playback, said honestly

    /// ⚠⚠ **The primary button's other half, and it is B4's placeholder verbatim**
    /// (`DetailCopy.playReadyTitle` / `playReadySub` / `nextUp`). The hero knows the verb the app DOES
    /// offer — `Resume`, `Play S1E3` — so it names it rather than pretending. The tvOS player is Phase C.
    private func showPlaybackPlaceholder(for item: MediaItem) {
        playbackVerb = HomeRules.heroPrimaryLabel(isEpisode: HomeRules.isEpisodeItem(item),
                                                 episodeCode: HomeRules.episodeItemCode(item) ?? "",
                                                 isSeries: HomeRules.isSeries(item),
                                                 percent: HomeRules.heroPercent(item))
    }

    private func playbackNotice(_ verb: String) -> some View {
        ZStack {
            Color.black.opacity(0.78)

            VStack(spacing: 16) {
                Text(DetailCopy.playReadyTitle)
                    .font(.system(size: 36, weight: .bold))
                Text(DetailCopy.playReadySub)
                    .font(.system(size: 24))
                    .foregroundStyle(RKMColour.secondary)
                Text(DetailCopy.nextUp(verb))
                    .font(.system(size: 26, weight: .semibold))
                    .foregroundStyle(RKMColour.accent)
                Button("Close") { playbackVerb = nil }
                    .buttonStyle(.borderedProminent)
                    .font(.system(size: 22))
                    .padding(.top, 6)
            }
            .padding(44)
            .background(RKMColour.surface3, in: RoundedRectangle(cornerRadius: DesignTokens.Radius.xl,
                                                                 style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.xl, style: .continuous)
                    .stroke(RKMColour.border, lineWidth: 1)
            )
        }
    }

    // MARK: - Select

    /// ⚠ **The detail screen is B4, so Select opens it.** Until B4 this logged instead — a real Button whose
    /// press does nothing visible reads as a broken remote, so it said so; now it goes where it says.
    private func open(_ item: MediaItem) {
        app.openDetail(itemID: item.itemID)
    }
}
