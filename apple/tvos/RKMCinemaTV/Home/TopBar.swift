import SwiftUI

/// One tab in the Home's top bar.
///
/// ⚠ **A tab is not a `LibraryNavEntry` on purpose.** The bar's tabs are built FROM the profile's libraries
/// (`BrowseRules.browseEntries` — the one rule), but the row also carries the Home entry and, when the server
/// sent no libraries at all, one way into Browse. Modelling the row as "libraries" would have made that
/// fallback impossible to express honestly.
struct TopBarTab: Identifiable {
    let id: String
    let title: String
    /// False for a library the server could not resolve — ⚠ it is still SHOWN (`BrowseRules`' rule: an
    /// unresolved library explains itself rather than disappearing), it simply cannot be selected.
    let isEnabled: Bool
    /// Why it is not selectable, said to a screen reader and never hidden.
    let warning: String
    let action: () -> Void
}

/// The Home's top bar — the buildspec's §2/§4 replacement for the web app's left sidebar.
///
/// ⚠⚠ **WHY A TOP BAR AND NOT THE SIDEBAR, in the buildspec's own words:** up/down on the Siri Remote is the
/// primary gesture for scrolling CONTENT, and a persistent vertical sidebar competes with it. Every major
/// tvOS app uses a horizontal tab row. That argument is the buildspec's and it is a good one.
///
/// ⚠⚠ **THE TABS ARE THIS PROFILE'S LIBRARIES, NOT A LITERAL LIST.** The buildspec names a fixed row
/// (`Home · Movies Kids · Movies · TV Shows · Watchlist · Discover · Suggest`); libraries are per-profile and
/// dynamic, and `BrowseRules.browseEntries` is already *"the ONE place that decides what the library list
/// contains"* (his iPad report of 2026-09-14 is why that rule exists). A literal array here would be the third
/// copy of a rule this repo has consolidated twice — falsifier **F3** is exactly this.
///
/// ⚠ **`Downloads` is deliberately absent**, and so are `Watchlist` / `Discover` / `Suggest`: those screens do
/// not exist on tvOS yet (`docs/TVOS_UX_PLAN.md` §5), and a tab whose screen the app cannot show is a control
/// the app refuses — the fault `docs/ARCHITECTURE.md` §11 names. `HomeView` supplies the one fallback that IS
/// honest, for the case where the profile has no libraries at all.
///
/// ⚠⚠ **THE RECEDE IS A HYPOTHESIS, AND IT IS FALSIFIER F6.** The buildspec asks for the bar to dim to ~55%
/// once focus leaves it. Whether SwiftUI on tvOS publishes that cleanly is NOT provable in this sandbox (the
/// same class of claim that produced the deleted `RailFocus.swift` and B3's grid), so it is built the
/// straightforward way — one `@FocusState` on the bar's own controls, and the bar dims when none of them is
/// focused. ⚠ No geometry is measured and no focus maths is written. If the round shows it failing, the fix is
/// `TVTokens.Metric.topBarDimmed` (one line) or the platform's own focus treatment — not an offset.
///
/// ⚠ The bar's background is the SYSTEM MATERIAL (`.ultraThinMaterial`), per buildspec §5 — the spec's
/// `rgba(24,24,27,0.66)` + blur is exactly the hand-rolled version Apple's guidance replaces, and the plan
/// keeps `glass` out of the token layer for that reason.
struct TopBar: View {

    let tabs: [TopBarTab]
    /// The signed-in profile's initials, for the avatar button. ⚠ `ProfileRules.initials` — the same rule the
    /// Profile Switcher's tiles use, so the two cannot show different letters for one person.
    let initials: String
    /// The tab row's failure, if it had one. ⚠ Shown here rather than only in the footer: a bar with no tabs
    /// because the fetch failed looks exactly like a profile with no libraries.
    let failure: String?
    /// ⚠ The avatar opens the PROFILE SWITCHER — where `Sign out`, `Change server` and the administrator's
    /// `Manage profiles` already live. That is the app's equivalent of the buildspec's "fold Settings into the
    /// profile menu", and it is one press from Home, so no exit was lost when the old header row went.
    let onProfile: () -> Void

    /// ⚠ One focus value for the whole bar. `nil` means focus is somewhere else on the screen — which is the
    /// recede's entire input.
    @FocusState private var focus: String?

    private static let profileTabID = "top-bar:profile"

    var body: some View {
        HStack(spacing: 14) {
            Text("RKMCinemaTV")
                .font(.system(size: 26, weight: .bold))
                .foregroundStyle(RKMColour.accent)
                .padding(.trailing, 8)

            ForEach(tabs) { tab in
                Button(tab.title) { tab.action() }
                    .buttonStyle(.bordered)
                    .disabled(!tab.isEnabled)
                    .accessibilityLabel(tab.warning.isEmpty ? tab.title : "\(tab.title), \(tab.warning)")
                    .focused($focus, equals: tab.id)
            }

            Spacer(minLength: 16)

            if let failure, !failure.isEmpty {
                Text(failure)
                    .font(.system(size: 18))
                    .foregroundStyle(RKMColour.warning)
                    .lineLimit(1)
            }

            Button(action: onProfile) { avatar }
                .buttonStyle(.bordered)
                .accessibilityLabel("Profiles")
                .focused($focus, equals: Self.profileTabID)
        }
        .font(.system(size: 20))
        .padding(.horizontal, TVTokens.Metric.safeMargin)
        .padding(.vertical, 14)
        // ⚠ Applied to the CONTENT only, then the material behind it: a bar whose background faded as well
        // would let the shelf below show through it, which reads as a rendering fault rather than a recede.
        .opacity(focus == nil ? TVTokens.Metric.topBarDimmed : 1)
        .animation(.easeOut(duration: 0.2), value: focus)
        .background(.ultraThinMaterial)
    }

    private var avatar: some View {
        Text(initials)
            .font(.system(size: 18, weight: .bold))
            .foregroundStyle(RKMColour.accentHover)
            .frame(width: 40, height: 40)
            .background(RKMColour.surface3, in: Circle())
            .overlay(Circle().stroke(RKMColour.border, lineWidth: 1))
    }
}
