# RKM Cinema — tvOS 26 Build Spec

Target: **Profile Switcher** and **Home** screens for Apple tvOS 26+.
Companion visual reference: `rkm-cinema-tvos-concept.html` (open it and navigate with arrow keys + Enter — it simulates the Siri Remote focus engine). That file is a **prototype for layout, states, and motion only** — see the reality check below before writing any code from it.

This doc is written so a coding agent can implement the screens without needing the human to fill gaps. Anywhere an assumption was necessary, it's labeled `ASSUMPTION` — verify against the real codebase before relying on it.

---

## 0. Platform reality check (read this first)

tvOS apps are native — there is no web runtime on the platform. The HTML file is **not portable code**; it exists to pin down layout, spacing, focus states, and motion so the native build matches intent pixel-for-pixel.

What genuinely carries over from the web/iOS codebase vs. what must be rebuilt:

| Layer | Reuse as-is | Rebuild for tvOS |
|---|---|---|
| Design tokens (color, type scale, radius) | ✅ Extract into a shared token source (see §1) | — |
| Data layer (API client, models, auth/session) | ✅ If iOS is Swift, share the module directly | — |
| View models / business logic (if iOS is SwiftUI + MVVM) | ✅ Share via a shared framework target | — |
| Image loading/caching, avatar-initials logic | ✅ Share | — |
| Iconography | Map to SF Symbols | New symbol picks where web used custom SVGs |
| Layout & navigation chrome | — | Rebuild natively — sidebar becomes a top bar (see §4) |
| Focus/interaction | — | New — driven by Apple's Focus Engine, not hover/click |

`ASSUMPTION`: the existing iOS app is SwiftUI. All structural snippets below are SwiftUI. If iOS is UIKit or a different stack, port the same tokens/hierarchy/focus rules into that framework's equivalent (`UIFocusEnvironment` for UIKit).

---

## 1. Design tokens

Extracted from the current web UI so both platforms stay visually identical. Put these in one shared source of truth (`DesignTokens.swift` or a generated token file consumed by both iOS and tvOS targets) rather than hand-copying hex values into each screen.

### Color

| Token | Hex | Usage |
|---|---|---|
| `bg` | `#08080A` | App background |
| `bgElevated` | `#1B1B1E` | Cards, avatar fallback circles |
| `glass` | `rgba(24,24,27,0.66)` | Translucent bars/panels (see §5 on Liquid Glass) |
| `hairline` | `rgba(255,255,255,0.09)` | Dividers, subtle borders |
| `textPrimary` | `#F5F5F7` | Titles, primary labels |
| `textSecondary` | `#ABABB2` | Metadata, subtitles |
| `textTertiary` | `#75757C` | De-emphasized captions |
| `gold` (brand accent) | `#F2B93A` | Logo mark, active states, progress fill, primary CTA |
| `goldBright` | `#FFD873` | Avatar initials, focus highlights on gold surfaces |
| `focusRing` | `rgba(255,255,255,0.85)` | Focus outline/glow on any focused element |

### Typography

Base: SF Pro (system font — do not bundle a custom face unless the brand already ships one).

| Role | Size (pt, 1080p reference) | Weight |
|---|---|---|
| Hero title | 68 | Bold |
| Screen title ("Who's watching?") | 64 | Bold |
| Section/shelf title | 32 | Semibold |
| Card title | 26 | Semibold |
| Body / metadata | 22 | Regular |
| Caption / badge | 18 | Semibold |

tvOS type sizes run larger than iOS/web for 10-foot viewing — do not reuse iOS point sizes directly; use `.font(.system(...))` with the sizes above or map through `UIFontMetrics` for Dynamic Type support.

### Spacing, radius, elevation

- Base unit: 8pt grid.
- Screen safe margins: minimum **90pt** left/right, **60pt** top/bottom (Apple's title-safe guidance) — never place interactive content closer to the edge.
- Card corner radius: 12pt. Avatar: fully round. Glass panels: 20pt continuous.
- Card shadow on focus: large, soft, dark (`shadowRadius: 40, opacity: 0.5`), plus the white `focusRing` glow.

### Motion

- Focus scale: `1.0 → ~1.12–1.16`, spring animation (`response: 0.35, dampingFraction: 0.7`), not a linear ease.
- Unfocused sibling items dim slightly (opacity ~0.85–1.0, don't overdo it) so the focused item reads as *the* selected thing, not just *a* highlighted one.
- One ambient motion only: a slow (20–30s) hero background drift/Ken Burns. Don't add motion to every card — Apple's HIG explicitly warns against motion fatigue on TV screens viewed for hours.

---

## 2. Information architecture change: sidebar → top bar

The web UI uses a **left vertical sidebar** (Browse / Libraries / Collections). This does not translate to tvOS:

- Up/down on the Siri Remote is the primary gesture for scrolling *content* (shelves, hero). A persistent vertical sidebar competes with that gesture and forces awkward left/right escapes.
- Apple TV, and every major tvOS streaming app (Apple TV app, Disney+, Netflix, Max), uses a **horizontal top tab bar** instead.

Mapping:

| Web sidebar item | tvOS location |
|---|---|
| Home, Movies Kids, Movies, TV Shows | Top bar, primary tabs |
| Watchlist, Discover, Suggest | Top bar, secondary tabs (same row, can overflow into a "More" tab if the row gets too wide for a given locale) |
| Search | Icon button, far right of top bar |
| Profile avatar / switch profile | Icon button, far right of top bar (opens Profile Switcher) |
| Settings | Fold into the profile menu, not a top-level tab — tvOS home screens keep the top bar short |

The top bar should recede (dim / lower opacity, ~55%) once focus moves down into content, and return to full opacity when focus returns to it — this is what the prototype's `dimmed` class demonstrates.

---

## 3. Screen: Profile Switcher ("Who's watching?")

**Purpose:** matches the web "Who's watching?" screen — same 4 profiles (`meenu`, `raj`, `rkm`, `sharanya`), same lock semantics (profiles with a password show a lock badge; `rkm` is the administrator).

### Layout
- Full-bleed dark background, centered content, no top bar.
- Title "Who's watching?" + subtitle ("N profiles on this server · Signed in as X").
- Horizontal row of circular avatar tiles, centered. Each tile: avatar circle (initials, brand gold-on-dark, matching web) → name → subtitle (`Profile · password`, `Administrator · password`, or `Profile`).
- Locked profiles show a small lock glyph badge overlapping the bottom-right of the avatar.
- An "Add profile" tile (dashed outline, `+`) sits at the end of the row — admin-only in the real app; gate this behind the signed-in account's role.
- Below the row: "Manage profiles" and "Sign out", as secondary pill buttons.

### Focus behavior
- Default focus lands on the first profile tile.
- Focused tile: scale up ~1.14, lift slightly, white focus-ring glow around the avatar; unfocused tiles sit at ~0.7 opacity so the choice is unambiguous from across a room.
- Up/down from the avatar row moves to the Manage/Sign out row and back.
- Selecting a locked profile should push to a numeric/on-screen keyboard PIN entry (native tvOS text entry — reuse whatever the iOS app already does for password entry on this server, adapted to the remote's on-screen keyboard).

### SwiftUI structure (illustrative)
```swift
struct ProfileSwitcherView: View {
    @FocusState private var focusedProfile: String?
    let profiles: [Profile] // reuse the existing Profile model from the shared/iOS module

    var body: some View {
        VStack(spacing: 48) {
            VStack(spacing: 8) {
                Text("Who's watching?").font(.system(size: 64, weight: .bold))
                Text("\(profiles.count) profiles on this server · Signed in as \(currentServerUser)")
                    .foregroundStyle(Tokens.textSecondary)
            }
            HStack(spacing: 40) {
                ForEach(profiles) { profile in
                    ProfileTile(profile: profile)
                        .focused($focusedProfile, equals: profile.id)
                }
                AddProfileTile() // admin-only
            }
            HStack(spacing: 24) {
                Button("Manage profiles") { /* ... */ }
                Button("Sign out") { /* ... */ }
            }
        }
        .padding(.horizontal, 90)
    }
}
```

---

## 4. Screen: Home

**Purpose:** matches the web Home screen — hero "Continue Watching" item, then `Continue Watching`, `Recently Played`, `Recently Added` shelves.

### Layout
- **Top bar** (per §2): brand mark, tab row, search + profile-avatar icon buttons on the right. Rendered as a translucent glass material (see §5), sits above content, recedes on scroll/focus-down.
- **Hero**: full-width band showing the top "Continue Watching" item — eyebrow label, title, metadata line (kind · genre · year · progress), a progress bar, and two actions (`Resume` primary, `Details` secondary).
- **Shelves**: horizontal, focus-scrollable rows of 16:9 cards. Each card: artwork, an episode/type badge (`S2·E4`, `MOVIE`) in the top-left corner, a play glyph, an optional progress bar along the bottom edge of the artwork, then title + subtitle beneath.

### States per card
- Default: artwork only, title/subtitle at normal weight.
- Focused: scale ~1.1, lift, white focus-ring around the artwork, siblings unaffected (no group-dimming on shelves — only the profile screen dims siblings, since shelves are dense and would look broken half-dimmed).
- In-progress: bottom progress bar in `gold` over a dark track.

### Focus behavior
- Left/right moves within a shelf (or the top bar); up/down moves between the top bar, hero actions, and shelves.
- Moving focus onto a shelf item scrolls that item to center-ish in the viewport (`scrollIntoView`/`ScrollViewReader.scrollTo` equivalent) so it's never partially offscreen.
- Top bar dims to ~55% opacity whenever focus is anywhere below it, returns to 100% when focus re-enters it.

### SwiftUI structure (illustrative)
```swift
struct HomeView: View {
    var body: some View {
        VStack(spacing: 0) {
            TopBar(tabs: tabs, onSelectTab: { ... }) // shared tab model from existing nav config
            ScrollView {
                HeroBanner(item: continueWatchingHero)
                ShelfRow(title: "Continue Watching", items: continueWatchingItems)
                ShelfRow(title: "Recently Played", items: recentlyPlayedItems)
                ShelfRow(title: "Recently Added", items: recentlyAddedItems)
            }
        }
    }
}
```
Reuse the existing shelf/item data models and API calls from the iOS app's Home view model directly — only the rendering layer (`TopBar`, `HeroBanner`, `ShelfRow`, `Card`) is new.

---

## 5. Liquid Glass & tvOS 26 specifics

tvOS 26 adopts Apple's "Liquid Glass" material language:

- Use `Material` / the platform's glass materials (not a flat translucent color) for the top bar and any overlay panels — real specular/blur behavior comes from the system material, not a hand-rolled `rgba` + blur.
- Corners on glass panels use the continuous ("squircle") curve, not a simple rounded rect.
- Don't stack multiple glass layers on top of each other (e.g., a glass card inside a glass bar) — it muddies the blur and hurts legibility from a couch-viewing distance.
- Respect system focus effects where possible (`.buttonStyle(.card)` and tvOS's built-in focus lift) rather than fully hand-rolling scale/shadow animations, so the app inherits any future Apple focus-engine refinements for free.

---

## 6. Accessibility

- Every focusable element needs a meaningful `.accessibilityLabel` (e.g. "Meenu, profile, password protected" rather than just "Meenu").
- Respect Reduce Motion: disable the hero drift animation and reduce focus-scale amounts when the system setting is on.
- Focus order must be logical top-to-bottom, left-to-right — verify with VoiceOver + remote, not just visually.
- Don't rely on color alone for the "locked profile" or "in progress" states — the lock glyph and the badge text (`S2·E4`, `MOVIE`) already carry that meaning non-visually; keep it that way.

---

## 7. Build checklist

- [ ] Design tokens pulled into a single shared source, not hardcoded per screen
- [ ] Top bar replaces the web sidebar; tabs match the existing nav config
- [ ] Profile Switcher: avatar tiles, lock badges, Add Profile (admin-gated), Manage/Sign out row
- [ ] Home: top bar + hero + three shelves, matching existing shelf data sources
- [ ] Focus engine: scale + glow on focus, siblings dim only on the profile screen, shelf items auto-scroll into view
- [ ] Top bar dim/recede behavior wired to focus location
- [ ] Glass materials use system `Material`, continuous corner radius
- [ ] VoiceOver labels on every focusable element; Reduce Motion respected
- [ ] Visual QA against `rkm-cinema-tvos-concept.html` side-by-side on an actual Apple TV or simulator (browser rendering is a stand-in, not a pixel reference — always verify final spacing on-device)
