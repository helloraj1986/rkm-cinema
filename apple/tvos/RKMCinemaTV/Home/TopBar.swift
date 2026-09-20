import SwiftUI
// ⚠ `RKMServerKit` for `RKMLog` — this app's own module, and on the 26 SDK `import SwiftUI` does not
// re-export it. `apple/scripts/check-imports.py` has a name-exact rule for exactly this, because
// `HomeView` lost a whole Mac round to `RKMLog` with no import and no gate able to see it.
import RKMServerKit

/// One tab in the Home's top bar.
///
/// ⚠ **A tab is not a `LibraryNavEntry` on purpose.** The bar's tabs are built FROM the profile's libraries
/// (`BrowseRules.browseEntries` — the one rule), but the row also carries the Home entry and, when the server
/// sent no libraries at all, one way into Browse. Modelling the row as "libraries" would have made that
/// fallback impossible to express honestly.
struct TopBarTab: Identifiable {
    let id: String
    let title: String
    /// True for the tab the viewer is on — the prototype's `[aria-current="true"]` (white + semibold, where
    /// the other tabs are `--text-2`).
    let isCurrent: Bool
    /// False for a library the server could not resolve — ⚠ it is still SHOWN (`BrowseRules`' rule: an
    /// unresolved library explains itself rather than disappearing), it simply cannot be selected.
    let isEnabled: Bool
    /// Why it is not selectable, said to a screen reader and never hidden.
    let warning: String
    let action: () -> Void
}

/// The Home's top bar — the prototype's `.tv-topbar`, and the buildspec's §2 replacement for the web sidebar.
///
/// ⚠⚠ **WHY A TOP BAR AND NOT THE SIDEBAR, in the buildspec's own words:** up/down on the Siri Remote is the
/// primary gesture for scrolling CONTENT, and a persistent vertical sidebar competes with it. Every major
/// tvOS app uses a horizontal tab row. That argument is the buildspec's and it is a good one.
///
/// ⚠⚠ **THE TABS ARE THIS PROFILE'S LIBRARIES, NOT A LITERAL LIST.** The prototype names a fixed row
/// (`Home · Movies Kids · Movies · TV Shows · Watchlist · Discover · Suggest`); libraries are per-profile and
/// dynamic, and `BrowseRules.browseEntries` is already *"the ONE place that decides what the library list
/// contains"* (his iPad report of 2026-09-14 is why that rule exists). A literal array here would be the third
/// copy of a rule this repo has consolidated twice — falsifier **F3** is exactly this. ⚠ **`Watchlist` /
/// `Discover` / `Suggest` are absent for the same reason `Downloads` is:** those screens do not exist on tvOS
/// yet (`docs/TVOS_UX_PLAN.md` §5), and a tab whose screen the app cannot show is a control it refuses.
///
/// ⚠⚠ **GEOMETRY IS THE PROTOTYPE'S, IN ITS OWN UNIT.** Every number below is `u * <the number in the HTML>`
/// (`TVTokens.Bar`): padding `1.7u / 4.2u`, brand `1.35u` at weight 800 with the gold dot, tabs `1.05u` with
/// `0.55u / 1.1u` padding and `0.8u` radius, the icon buttons `2.6u` circles. ⚠ The FOCUSED TAB is
/// **black-on-gold** as the prototype draws it (`:focus { color:#111; background: var(--gold) }`) — a custom
/// style, because no system button style paints a brand-gold fill.
///
/// ⚠ The bar's background is the **system material** (`.regularMaterial`) under the prototype's own
/// `--glass-strong` tint, per buildspec §5 — the spec's `rgba(24,24,27,0.66)` + blur is exactly the hand-rolled
/// version Apple's guidance replaces, and the plan keeps `glass` out of the token layer for that reason.
///
/// ⚠⚠ **THE RECEDE IS A HYPOTHESIS, AND IT IS FALSIFIER F6.** The prototype asks for `opacity:.55` once focus
/// leaves the bar. Whether SwiftUI on tvOS publishes that cleanly is NOT provable in this sandbox (the same
/// class of claim that produced the deleted `RailFocus.swift` and B3's grid), so it is built the
/// straightforward way — one `@FocusState` on the bar's own controls, and the bar dims when none of them is
/// focused. ⚠ No geometry is measured and no focus maths is written. If the round shows it failing, the fix is
/// `TVTokens.Metric.topBarDimmed` (one line) or the platform's own focus treatment — not an offset.
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
        HStack(spacing: TVTokens.Bar.tabSpacing) {
            brand

            ForEach(tabs) { tab in
                Button(tab.title) { tab.action() }
                    .buttonStyle(TabButtonStyle(isCurrent: tab.isCurrent))
                    .disabled(!tab.isEnabled)
                    .accessibilityLabel(tab.warning.isEmpty ? tab.title : "\(tab.title), \(tab.warning)")
                    .focused($focus, equals: tab.id)
            }

            Spacer(minLength: TVTokens.Bar.tabSpacing * 2)

            if let failure, !failure.isEmpty {
                Text(failure)
                    .font(.system(size: TVTokens.Bar.tabFontSize))
                    .foregroundStyle(RKMColour.warning)
                    .lineLimit(1)
            }

            // ⚠ The prototype also has a SEARCH icon here. It is NOT drawn: tvOS has no search screen
            // (`docs/TVOS_UX_PLAN.md` §5 puts it out of scope), and an icon whose every press must be refused
            // is the control `docs/ARCHITECTURE.md` §11 forbids. It lands with the screen.
            Button(action: onProfile) {
                Text(initials)
                    .font(.system(size: TVTokens.Bar.iconFontSize, weight: .bold))
                    .foregroundStyle(RKMColour.accentHover)
                    .frame(width: TVTokens.Bar.iconSize, height: TVTokens.Bar.iconSize)
                    .background(RKMColour.avatarGradient, in: Circle())
            }
            .buttonStyle(IconButtonStyle())
            .accessibilityLabel("Profiles")
            .focused($focus, equals: Self.profileTabID)
        }
        .padding(.horizontal, TVTokens.Bar.paddingH)
        .padding(.vertical, TVTokens.Bar.paddingV)
        // ⚠ Applied to the CONTENT only, then the material and the tint behind it: a bar whose background
        // faded as well would let the shelf below show through it, which reads as a rendering fault rather
        // than a recede.
        .opacity(focus == nil ? TVTokens.Metric.topBarDimmed : 1)
        .animation(.easeOut(duration: 0.3), value: focus)
        .background {
            Rectangle()
                .fill(.regularMaterial)
                .overlay(RKMColour.topBarTint)
                .ignoresSafeArea(edges: .top)
        }
        // The prototype's `border-bottom: 1px solid var(--hairline)`.
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(RKMColour.border)
                .frame(height: 1)
        }
        // ⚠⚠ **THE BAR PUBLISHES ITS OWN FOCUS, AND IT IS A FALSIFIER RATHER THAN A DIAGNOSTIC.** The title
        // screen's dead end (`KNOWN_ISSUES` #15) has exactly one line of evidence to give: **whether focus LEFT
        // the bar when Down was pressed.** `bar-focus: nil` followed by `detail-focus: play=true` means it did
        // (and any remaining complaint is about something else); `bar-focus: back` staying put with no
        // `play=true` means the engine found no candidate below at all, and the geometry is what changes next.
        // ⚠ One line per CHANGE of focus, never per frame — and `nil` is a real answer here, so it is printed
        // as the word rather than as an empty string.
        .onChange(of: focus) { _, value in
            RKMLog.info("bar-focus: \(value ?? "nil")", category: .app)
        }
    }

    /// `RKM·CINEMA` — the prototype's wordmark, weight 800, with its gold dot. ⚠ The app used to print its
    /// target name (`RKMCinemaTV`) here; the prototype's own brand lockup replaces it, because the bar is the
    /// one place a viewer sees the product's name.
    private var brand: some View {
        HStack(spacing: TVTokens.Bar.tabSpacing * 1.2) {
            Text("RKM")
            Text("·").foregroundStyle(RKMColour.accent)
            Text("CINEMA")
        }
        .font(.system(size: TVTokens.Bar.brandSize, weight: .heavy))
        .foregroundStyle(RKMColour.primary)
        .fixedSize()
        .padding(.trailing, TVTokens.Bar.tabSpacing * 2.8)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("RKM Cinema")
    }
}

/// ⚠ The prototype's `.nav-tab` states, which no system tvOS button style paints: an idle tab is `--text-2`,
/// the CURRENT tab is white and semibold, and a FOCUSED tab inverts to black-on-gold with a white ring.
///
/// ⚠ A focus-dependent style and not focus ARITHMETIC — `@Environment(\.isFocused)` is published for the
/// focused view and inherited by its descendants, which is the whole mechanism (the same one
/// `ProfileTileStyle` uses). No frame is measured and no nearest-neighbour is computed.
struct TabButtonStyle: ButtonStyle {

    let isCurrent: Bool

    func makeBody(configuration: Configuration) -> some View {
        TabChrome(configuration: configuration, isCurrent: isCurrent)
    }

        // ⚠⚠ NOT `Body`: every `Style` protocol declares an associatedtype requirement called `Body`, so a
    // helper view nested inside a conformer and named `Body` collides with it — measured on the Mac,
    // U6's second round: `type 'TabButtonStyle' does not conform to protocol 'ButtonStyle'` plus
    // `struct 'Body' must be as accessible as its enclosing type`. The Phase A tile style is called
    // `TileBody` for exactly this reason; this is that rule, spelled the same way.
    private struct TabChrome: View {
        let configuration: ButtonStyle.Configuration
        let isCurrent: Bool
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .font(.system(size: TVTokens.Bar.tabFontSize, weight: isCurrent ? .semibold : .regular))
                .foregroundStyle(isFocused ? RKMColour.background
                                           : (isCurrent ? RKMColour.primary : RKMColour.secondary))
                .padding(.horizontal, TVTokens.Bar.tabPaddingH)
                .padding(.vertical, TVTokens.Bar.tabPaddingV)
                .background {
                    RoundedRectangle(cornerRadius: TVTokens.Bar.tabRadius, style: .continuous)
                        .fill(isFocused ? RKMColour.accent : .clear)
                }
                .overlay {
                    RoundedRectangle(cornerRadius: TVTokens.Bar.tabRadius, style: .continuous)
                        .stroke(RKMColour.primary.opacity(0.85), lineWidth: isFocused ? TVTokens.Bar.focusRing : 0)
                }
                .scaleEffect(isFocused ? TVTokens.Bar.focusScale : 1)
                .animation(.easeOut(duration: 0.2), value: isFocused)
        }
    }
}

/// The prototype's `.icon-btn`: a translucent circle with a white ring and a 1.16 lift on focus.
struct IconButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        IconChrome(configuration: configuration)
    }

        // ⚠⚠ NOT `Body`: every `Style` protocol declares an associatedtype requirement called `Body`, so a
    // helper view nested inside a conformer and named `Body` collides with it — measured on the Mac,
    // U6's second round: `type 'TabButtonStyle' does not conform to protocol 'ButtonStyle'` plus
    // `struct 'Body' must be as accessible as its enclosing type`. The Phase A tile style is called
    // `TileBody` for exactly this reason; this is that rule, spelled the same way.
    private struct IconChrome: View {
        let configuration: ButtonStyle.Configuration
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .opacity(isFocused ? 1 : 0.94)
                .overlay {
                    Circle().stroke(RKMColour.primary.opacity(0.85),
                                    lineWidth: isFocused ? TVTokens.Bar.focusRing : 0)
                }
                .scaleEffect(isFocused ? 1.16 : 1)
                .animation(.easeOut(duration: 0.2), value: isFocused)
        }
    }
}
