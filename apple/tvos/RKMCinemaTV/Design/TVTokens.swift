import Foundation

/// The **tvOS-only** layer of the design tokens — hand-written, small, and every entry carries its reason.
///
/// ⚠⚠ **WHY THIS FILE EXISTS AT ALL, AND WHERE ITS BOUNDARY IS.** `Design/DesignTokens.swift` is GENERATED
/// from the web app's `frontend/src/styles/index.css`, and its drift gate fails the round if the two ever
/// disagree — which means the tvOS app cannot hold a brand value the phone and the web do not. That is the
/// point. But one token legitimately differs on a television, and this is the file that holds it:
///
///   * **A colour that is deliberately different from the web lives HERE, with its reason.** A value that
///     migrates out of this file into the generated one stops being a tvOS decision and becomes a brand
///     change — one that affects the phone, the tablet and the desktop too.
///   * **A colour that agrees with the web is read from `DesignTokens.Colour`.** Duplicating it here is how
///     two files come to hold one value, which is this repo's most-repeated defect.
///   * **A tvOS METRIC that was never in the CSS** (the screen scale, safe margins, focus/dimming behaviour)
///     lives here as well, because a generator for a hand-written number is worse than no generator.
///
/// ⚠⚠ **PHASE U6 — HIS PROTOTYPE IS NOW THE SOURCE FOR THE TWO SCREENS' GEOMETRY, AND IT BRINGS ITS OWN
/// SCALE.** `tvos_ux/1. UserProfileSelection_HomePage/rkm-cinema-tvos-concept.html` sizes *everything* off
/// `--u: 1cqw` — one percent of the screen's width — so that no measurement in it is a magic number and the
/// two screens cannot drift apart. His words after seeing the first build: *"the current one doesn't even
/// look like what is seen in the html"*. So the scale is adopted wholesale:
///
/// > **`Metric.u` = 1 % of the screen width = 19.2 pt** (tvOS renders in a fixed 1920 × 1080 point space),
/// > and every number below is transcribed as `u * <the number in the HTML>` — **never** as a hand-converted
/// > point value. A number that cannot be traced to a line of that file does not belong here.
///
/// ⚠ What is still **NOT** adopted from the design input, and why:
///   * **the buildspec's prose type scale (64/32/22/16/14)** — the prototype's `--u` sizes supersede it for
///     these two screens, and the rest of the app keeps the sizes his earlier simulator rounds accepted;
///   * **the prototype's JavaScript** — it hand-rolls nearest-neighbour up/down focus AND `scrollIntoView`
///     (lines 546-561), which tvOS's focus engine already does; porting it is the mistake `RailFocus.swift`
///     and B3's 2-D grid already paid for twice. ⚠ What IS ours is the top bar's recede, and it is F6.
///
/// ⚠ `Foundation`-only, so `apple/scripts/check-apple-typecheck.sh` compiles it on Linux. It carries
/// NUMBERS and raw colours; the conversion to `SwiftUI.Color` is in `Design/DesignColours.swift`.
enum TVTokens {

    // MARK: - The prototype's scale

    /// ⚠⚠ One percent of the screen width. **Every metric below is a multiple of this**, exactly as the
    /// prototype's `--u: 1cqw` is, so a number here can be read against its line in the HTML.
    static let u: CGFloat = 19.2

    // MARK: - Colours that differ from the web app

    /// Colours that intentionally differ from the web app's.
    enum Colour {

        /// `--text-muted` **as a television needs it** — the one token whose value changes on tvOS.
        ///
        /// ⚠⚠ **WHY, MEASURED — NOT A PREFERENCE.** WCAG 2.1 contrast ratios against `--bg #08090b` were
        /// computed from the real tokens on 2026-09-19 (`docs/TVOS_UX_PLAN.md` §2b). Normal text needs
        /// **4.5:1**; `--text-muted #70747e` measures **4.26:1** on the background and **fails outright on
        /// every surface it actually sits on** — `--surface-1` 4.01, `--surface-2` 3.83, `--card` 3.76,
        /// `--surface-3` 3.57. And it is the app's DE-EMPHASISED CAPTION colour, i.e. the smallest text on
        /// screen, read from three metres away.
        ///
        /// The fix is **lightness only** and nothing else — hue and saturation are identical
        /// (HLS lightness 0.467 → 0.532) — so it stays recognisably the same grey:
        ///
        ///     #70747e → #81858f
        ///     on --bg 4.26 → 5.39 · --surface-1 4.01 → 5.08 · --surface-2 3.83 → 4.85
        ///     --card 3.76 → 4.76 · --surface-3 3.57 → 4.52
        ///
        /// ⇒ AA on every surface the app puts it on.
        ///
        /// ⚠ **HIS DECISION (2026-09-19): tvOS only — the web keeps `#70747e`.** Which is precisely why a
        /// view must read THIS property and never `DesignTokens.Colour.textMuted` —
        /// `apple/scripts/check-design-tokens.py` fails the round if any tvOS source does the latter.
        static let textMuted = RGBAColor(red: 129 / 255,
                                         green: 133 / 255,
                                         blue: 143 / 255,
                                         alpha: 1)

        /// The prototype's avatar circle — `.profile-tile .avatar`'s
        /// `linear-gradient(160deg,#2A2A2E,#161618)`, and the same gradient the top bar's avatar button uses.
        ///
        /// ⚠ **Not a web token and not a brand colour:** `index.css` has no gradient for an avatar because the
        /// web renders avatars as flat initials on `--surface-3`. The prototype gives the TV a lit circle so
        /// the face of the screen reads as a portrait, and his HTML is the source. ⚠ It is deliberately in
        /// THIS file and not in the generated one — a gradient that migrated there would become a brand change
        /// affecting the phone and the web.
        static let avatarTop = RGBAColor(red: 42 / 255, green: 42 / 255, blue: 46 / 255, alpha: 1)
        static let avatarBottom = RGBAColor(red: 22 / 255, green: 22 / 255, blue: 24 / 255, alpha: 1)

        /// The warm wash behind the Profile Switcher — the prototype's
        /// `radial-gradient(120% 90% at 50% 0%, rgba(60,50,20,.35), transparent 55%)`.
        ///
        /// ⚠ Same status as the avatar gradient: a tvOS-only light on the room's darkest screen, taken from
        /// his HTML and kept out of the generated table on purpose.
        static let profileGlow = RGBAColor(red: 60 / 255, green: 50 / 255, blue: 20 / 255, alpha: 0.35)

        /// The top bar's own background — the prototype's `--glass-strong`
        /// (`rgba(14,14,16,0.86)` under a 24 px blur).
        ///
        /// ⚠ The blur itself is the PLATFORM's material (`.ultraThinMaterial` / `.regularMaterial`), per
        /// buildspec §5 — this is only the tint laid over it, because the prototype's bar is noticeably darker
        /// than `--surface-1` and that darkness is what lets the brand and tabs sit on it.
        static let topBarTint = RGBAColor(red: 14 / 255, green: 14 / 255, blue: 16 / 255, alpha: 0.86)
    }

    // MARK: - The hero band (`.hero` in the prototype)

    enum Hero {
        static let height = u * 32
        static let paddingV = u * 3
        static let paddingH = u * 4.2
        static let eyebrowSize = u * 1
        static let titleSize = u * 3.6
        static let metaSize = u * 1.05
        /// ⚠ `max-width: 60%` on `.hero-title` — a long title must wrap rather than run under the artwork's
        /// bright side, which is where the copy would become unreadable.
        static let titleMaxWidth = u * 60
        static let progressWidth = u * 26
        static let progressHeight = u * 0.35
        static let actionSpacing = u * 1
        static let ctaFontSize = u * 1.1
        static let ctaRadius = u * 0.9
        static let ctaPaddingH = u * 1.8
        static let ctaPaddingV = u * 0.85
    }

    // MARK: - The top bar (`.tv-topbar` in the prototype)

    enum Bar {
        static let paddingV = u * 1.7
        static let paddingH = u * 4.2
        static let brandSize = u * 1.35
        static let tabFontSize = u * 1.05
        static let tabPaddingH = u * 1.1
        static let tabPaddingV = u * 0.55
        static let tabRadius = u * 0.8
        static let tabSpacing = u * 0.5
        static let iconSize = u * 2.6
        static let iconFontSize = u * 1.05
        /// The ring a focused tab or icon button draws (§`box-shadow: 0 0 0 0.16u`).
        static let focusRing = u * 0.16
        static let focusScale: CGFloat = 1.08
    }

    // MARK: - A shelf (`.shelf` + `.card` in the prototype)

    enum Shelf {
        static let titleSize = u * 1.5
        static let titleGap = u * 1.1
        static let trackPaddingV = u * 0.6
        static let gap = u * 1.3
        static let cardWidth = u * 19
        static let artRadius = u * 0.7
        static let badgeSize = u * 0.68
        static let badgeInset = u * 0.5
        static let badgeRadius = u * 0.3
        static let badgePaddingH = u * 0.5
        static let badgePaddingV = u * 0.15
        static let playSize = u * 1.9
        static let playInset = u * 0.55
        static let progressHeight = u * 0.22
        static let cardTitleSize = u * 1.05
        static let titleGapTop = u * 0.7
        static let subSize = u * 0.82

        // ---- the PREMIUM pass (his review of the first card that ran, 2026-09-20: *"the card ux doesn't look
        // good, the text positions are going to the border on left"*). ⚠ The prototype has no card CHROME, only
        // art + two lines of text, so these are tvOS additions rather than transcriptions — each carries its
        // reason, and the numbers stay in the prototype's unit.

        /// ⚠ The text block's inset, and it is the fix for what he reported: with no inset the title and the
        /// facts line started at the artwork's exact left edge, which on a 10-foot screen reads as text running
        /// off the card rather than as a caption under a picture. `0.5u` is `badgeInset` — the same inset the
        /// badge uses on the art above it, so the two corners line up.
        static let textInset = u * 0.5
        /// The facts line sits under the title. `0.35u` is what stops two lines of different sizes from
        /// looking like one paragraph.
        static let factsGapTop = u * 0.35
        /// The meta chips (duration and state) are QUIETER than the type badge: the badge says what the thing
        /// IS, the chips are detail. Same box, smaller type, less contrast.
        static let chipSize = u * 0.62
        static let chipPaddingH = u * 0.45
        static let chipPaddingV = u * 0.2
        /// ⚠ A scrim over the artwork's lower half. The duration, the state chip and the progress bar all sit
        /// on the art, and keyart is often bright exactly where they are — a chip you cannot read is worse
        /// than no chip, and this is cheaper than a shadow per element.
        static let scrimHeight = u * 7
        static let scrimOpacity = 0.55
        /// The design input's `box-shadow: 0 0.5u 1.4u rgba(0,0,0,.45)` and its `1px` inner hairline
        /// (`--hairline` = white 8 %). ⚠ On a black screen a 16:9 card with no edge dissolves into the shelf.
        static let artShadowY = u * 0.5
        static let artShadowRadius = u * 1.4
        static let artShadowOpacity = 0.45
        static let artBorderWidth = u * 0.05
    }

    // MARK: - The Profile Switcher (`.profile-tile` and friends)

    enum Profile {
        static let eyebrowSize = u * 1.05
        static let titleSize = u * 4.4
        static let titleGap = u * 3.2
        static let rowGap = u * 2.6
        static let rowBottomGap = u * 3
        static let tileWidth = u * 13
        static let tilePadding = u * 0.8
        static let tileRadius = u * 1.2
        static let avatarSize = u * 10.4
        static let avatarFontSize = u * 3.4
        static let nameSize = u * 1.5
        static let subSize = u * 0.95
        /// ⚠ The prototype's own gaps (`.name { margin-top: 1.1u }`, `.sub { margin-top: 0.25u }`) — they are
        /// NOT multiples of the font sizes, so they are tokens rather than a fraction of `nameSize`.
        static let nameGapTop = u * 1.1
        static let subGapTop = u * 0.25
        /// ⚠⚠ **DERIVED, AND THE DERIVATION IS THE POINT: this is what makes "does the row fit?" answerable
        /// without a screen.** One tile is `avatarSize 10.4u + nameGapTop 1.1u + the name's own line 1.8u +
        /// subGapTop 0.25u + the sub's own line 1.14u ≈ 14.7u`, plus the focus lift (`0.3u`) and the ring
        /// (`0.28u`) — the two things that overflow FIRST when a row is only just tall enough. Rounded up.
        static let rowHeight = u * 15.6
        /// ⚠⚠ **THE ROW'S WIDTH, IN `u`, SO THE FIT IS ARITHMETIC AND NOT A HOPE.** Five tiles (four profiles
        /// plus `Add profile`) at the prototype's own sizes are `5 × 13u + 4 × 2.6u = 75.4u`, and with the
        /// screen's own `4.2u` margins that is **83.8 of the 100u available** — it fits with room to spare, and
        /// it stops fitting the moment a second margin is added anywhere (which is exactly what made the `Add`
        /// profile tile hang off the right edge of his screenshot).
        static let rowWidthUnits: CGFloat = 5 * 13 + 4 * 2.6
        static let rowMarginUnits: CGFloat = 4.2
        static let lockSize = u * 2.2
        static let lockFontSize = u * 1.1
        static let lockRing = u * 0.22
        /// ⚠ The white ring around the FOCUSED avatar only (`0.28u`) — the ring is on the avatar, the lift is
        /// on the tile, exactly as the prototype draws it.
        static let focusRing = u * 0.28
        /// ⚠ The prototype's own focus shadow (`0 1.4u 2.6u rgba(0,0,0,.6)`), and it is not decoration: on a
        /// black screen the focused tile has to LIFT, and without the shadow the scale change alone reads as
        /// the avatar simply being bigger.
        static let focusShadowY = u * 1.4
        static let focusShadowRadius = u * 2.6
        static let focusLift = u * 0.3
        static let focusScale: CGFloat = 1.14
        static let unfocusedOpacity: CGFloat = 0.72
        static let pillFontSize = u * 1.05
        static let pillRadius = u * 2.4
        static let pillPaddingH = u * 2.1
        static let pillPaddingV = u * 0.9
        static let actionGap = u * 1.4
        static let screenPaddingV = u * 4
        static let screenPaddingH = u * 6
    }

    // MARK: - ⚠⚠ SET 2'S UNIT (Phase V) — his second prototype has no `--u`

    /// ⚠⚠ **THE LIBRARY AND TITLE PROTOTYPES ARE DRAWN IN CSS px, NOT IN `u` — SO THE px IS PINNED HERE.**
    ///
    /// `tvos_ux/2. LibraryViewandItemDetailsView/` is a different file by the same hand and it does **not**
    /// carry set 1's `--u: 1cqw`; it is absolute pixels (`padding:28px 64px`, `gap:46px 28px`,
    /// `font-size:19px`). A browser page's px mean nothing on tvOS's fixed 1920 × 1080 point canvas until an
    /// anchor is chosen, and choosing one badly is a whole-screen error in both screens, so the anchor is the
    /// one value the two prototypes MUST agree on:
    ///
    /// > **the page margin.** Set 1 fixes it at `4.2u` (= 80.64 pt) and `Metric.safeMargin` already carries
    /// > it; set 2 pads **every** band by `64px` (`.topbar`, `.filterbar`, `.grid-wrap`, `.actions`,
    /// > `.synopsis`, `.shelf h2`, `.shelf-track`). So `64px ≡ 4.2u` ⇒ **1px = 4.2/64 u = 0.065625u =
    /// > 1.26 pt**, and every metric in `Grid` and `Title` below is `px * <the number in the HTML>`.
    ///
    /// ⚠ **Checked against the one element both files draw — the top bar — and it lands within a point:**
    /// brand `20px → 25.2` vs set 1's `1.35u = 25.92`; bar padding-V `28px → 35.28` vs `1.7u = 32.64`.
    /// ⚠ Set 2's tabs are deliberately BIGGER than set 1's (`19px → 23.94` vs `1.05u = 20.16`): set 2 is the
    /// later file, and it is the file these two screens are built from.
    ///
    /// ⚠⚠ **What this pin does NOT preserve is the prototype's margin-to-page ratio** — a browser width was
    /// never stated, so it could not be. What it DOES preserve is the 6-column grid and the app's ONE margin.
    /// ⇒ **If the round shows both screens too small or too large, this is the ONE constant to change; do not
    /// re-derive it per metric.** Alternatives and their measured cost are in `docs/TVOS_LIBRARY_UI_PLAN.md` §2.
    static let px: CGFloat = 1.26

    // MARK: - The Library screen (set 2 — `library-view.html`)

    /// `.topbar`'s siblings: `.filterbar`, `.grid-wrap` and the grid itself.
    enum Grid {

        // ---- the filter row (`.filterbar` + `.chip` + `.meta-count`)
        static let filterTopPad = px * 8
        static let filterBottomPad = px * 28
        static let chipGap = px * 16
        static let chipFontSize = px * 17
        static let chipPaddingH = px * 22
        static let chipPaddingV = px * 10
        /// `.chip { border-radius: 999px }` — a pill, so the radius is half the control's height and is
        /// written as a number larger than any chip can be rather than as `Capsule()`, because that is what
        /// the prototype says (and it keeps working if the type scale changes).
        static let chipRadius = px * 999
        /// `.chip.is-focused { transform: scale(1.08) }` — ⚠ smaller than a POSTER's 1.14, and that is the
        /// prototype's own distinction: a chip grows into its own gap, a poster grows into a whole screen.
        static let chipFocusScale: CGFloat = 1.08
        /// ⚠ `.chip { border: 2px solid transparent }`, which on focus becomes `--gold-bright`.
        static let chipBorderWidth = px * 2
        /// `.chip.is-focused { box-shadow: 0 6px 20px rgba(232,179,61,0.35) }` — the glow under a focused
        /// chip. Same numbers as the prototype's, and drawn only when focused (an always-on glow would tint
        /// every chip in the row).
        static let chipGlowY = px * 6
        static let chipGlowRadius = px * 20
        /// `.meta-count { font-size:16px }`, pushed right by `margin-left:auto`.
        static let countSize = px * 16
        static let countLeadIn = px * 24

        // ---- the grid (`.grid` + `.grid-title`)
        /// `grid-template-columns: repeat(6, 1fr)` — **six, fixed**, not `.adaptive`.
        ///
        /// ⚠ `.adaptive(minimum:)` was what `BrowseView` used before this phase, and it is the wrong rule for a
        /// TV: the column count would change with the window width, so a wall would re-flow between two
        /// screenshots of the same library. The prototype's own number is 6, and a fixed count is also what
        /// gives the focus engine its column memory.
        static let columns = 6
        static let gridTitleSize = px * 15
        static let gridTitleGap = px * 18
        static let gridTopPad = px * 8
        /// `.grid-wrap { padding-bottom: 120px }` — the wall's tail, so the last row is not flush with the
        /// screen's bottom edge.
        static let gridBottomPad = px * 120
        /// `.grid { gap: 46px 28px }` — row gap, then column gap, in the prototype's own order.
        static let rowGap = px * 46
        static let columnGap = px * 28

        // ---- the grid card (`.card` — 2:3, art only, reveal on focus)
        /// `.card { aspect-ratio: 2/3 }` — the POSTER, where the Home's shelf card is 16:9 keyart. Both are
        /// his, from two files, and they are deliberately different cards (`docs/TVOS_LIBRARY_UI_PLAN.md` §3.2).
        static let cardAspect: CGFloat = 3.0 / 2.0
        static let cardRadius = px * 14
        /// `.card.is-focused { transform: scale(1.14) }`.
        static let cardFocusScale: CGFloat = 1.14
        /// `.card.is-focused`'s `0 0 0 3px var(--gold)` — the ring is drawn INSIDE the style (the U7b lesson:
        /// a caller that can only supply content cannot put the ring in the wrong place).
        static let cardFocusRing = px * 3
        /// …and its `0 18px 30px rgba(0,0,0,.55)` + `0 0 34px rgba(232,179,61,.45)`.
        static let cardShadowY = px * 18
        static let cardShadowRadius = px * 30
        /// `.card .label { padding: 14px 12px 12px }` — the caption block is INSIDE the card's bottom edge
        /// (`position:absolute; left:0; right:0; bottom:0`), over a bottom-up scrim.
        ///
        /// ⚠⚠ **The spec's PROSE says "a label block fades in BELOW the art" and the CSS says the opposite.**
        /// The CSS wins: `tvos-ux-parity-and-defects.md` — *"its GEOMETRY IS THE SPEC — TRANSCRIBE IT"* — and
        /// a caption below a 2:3 card would change the card's height on focus, which the CSS does not do.
        static let labelInsetTop = px * 14
        static let labelInsetH = px * 12
        static let labelInsetBottom = px * 12
        static let cardTitleSize = px * 16
        static let cardMetaSize = px * 13
        /// `.card .label { opacity:0; transform:translateY(6px) }` → `1` / `0` on focus.
        static let labelRevealOffset = px * 6

        // ---- the empty state (`.empty-state`)
        static let emptyPaddingV = px * 80
        static let emptyPaddingH = px * 4
        static let emptyTitleSize = px * 26
        static let emptyBodySize = px * 17
        static let emptyGap = px * 18
    }

    // MARK: - The Title screen (set 2 — `title-view.html`)

    enum Title {

        // ---- the hero (`.hero`)
        /// `.hero { height: 66vh; min-height: 520px }` — ⚠ a FRACTION of the screen and not a point value,
        /// because that is what `vh` is: `0.66 × 1080 ≈ 712.8 pt`. The Home's hero is `32u = 614.4 pt`, so
        /// the Title screen's backdrop is genuinely taller, which is the prototype's intent ("the title block
        /// sits over the BACKDROP", where the Home's sits over a band).
        static let heroHeightFraction: CGFloat = 0.66
        /// …and its `min-height`, which matters on no tvOS screen (1080 pt is fixed) but is transcribed so the
        /// two numbers stay side by side with their source.
        static let heroMinHeight = px * 520
        /// `.hero::after`'s `linear-gradient(to top, var(--void) 0%, rgba(10,11,13,.65) 32%, transparent 68%)`.
        static let scrimSolidStop: CGFloat = 0
        static let scrimMidStop: CGFloat = 0.32
        static let scrimMidOpacity: CGFloat = 0.65
        static let scrimClearStop: CGFloat = 0.68
        /// ⚠ `.hero-emblem` (a `280px` watermark at `right:8%; top:12%; opacity:.16`) is **NOT drawn**, and
        /// the reason is that it is not layout: it is the prototype's stand-in for ARTWORK. His `.hero` has a
        /// CSS `radial-gradient` background because a prototype has no film to show; the app has the real
        /// backdrop (`PosterURL.Route.backdrop`, U3) with a poster fallback, so an invented mark on top of it
        /// would be decoration the design does not actually ask for. ⚠ Recorded rather than silently skipped.

        // ---- the title block (`.title-block`)
        static let blockPaddingBottom = px * 40
        static let blockMaxWidth = px * 920
        static let titleSize = px * 64
        static let titleGapBottom = px * 14
        static let metaSize = px * 19
        static let metaGap = px * 14
        static let metaGapBottom = px * 18
        /// `.genre-pill { padding:6px 16px; border-radius:999px; font-size:15px }` and `.genre-chips { gap:10px }`.
        static let pillFontSize = px * 15
        static let pillPaddingH = px * 16
        static let pillPaddingV = px * 6
        static let pillGap = px * 10
        static let pillRadius = px * 999

        // ---- the synopsis (`.synopsis`)
        static let synopsisTopPad = px * 40
        static let synopsisSize = px * 19
        /// `line-height: 1.6` on a `19px` font — the extra leading is `0.6 × 19px`.
        static let synopsisLineSpacing = px * 11.4
        /// ⚠ `max-width: 62ch`, and **a `ch` is not a point value**, so it is converted with the prototype's
        /// own font size rather than guessed: a system sans digit is ≈`0.5em`, so `62 × 0.5 × 19px = 589px`.
        /// Stated as arithmetic so the number can be re-derived if the type scale ever moves.
        static let synopsisMeasure = px * 589

        // ---- a shelf's headings and tracks (`.shelf`, `.shelf h2`, `.shelf-track`)
        static let shelfTopPad = px * 44
        static let sectionTitleSize = px * 24
        static let sectionTitleGap = px * 22
        static let trackGap = px * 28
        static let trackPaddingBottom = px * 26

        // ---- the cast shelf (`.cast-item`, `.avatar`)
        /// `.avatar` — the prototype draws `hsl(<hue> 55% 62%)`, one hue per person. ⚠ The two constants are
        /// his; the hue is derived per person by `DetailRules.castHue` (see there for why the colour is a
        /// derivation and not data).
        static let avatarSaturation: Double = 0.55
        static let avatarBrightness: Double = 0.62
        static let castItemWidth = px * 150
        static let castItemRadius = px * 16
        static let avatarSize = px * 110
        static let avatarGapBottom = px * 12
        static let initialsSize = px * 32
        static let castNameSize = px * 16
        static let castRoleSize = px * 14
        /// `.cast-item.is-focused { transform: scale(1.1) }`.
        static let castFocusScale: CGFloat = 1.1

        /// `.spacer-bottom { height:100px }`.
        static let bottomSpacer = px * 100
    }

    /// tvOS layout metrics that have no prototype line to point at.
    enum Metric {

        /// The screens' horizontal margin.
        ///
        /// ⚠ **U6 moved this from a hand-picked 60 to the prototype's own content inset** — every band in the
        /// HTML pads by `4.2u` (`.tv-topbar`, `.hero`, `.shelf-title`, `.shelf-track`), so 4.2u is the app's
        /// margin and it is now shared by every screen: the two redesigned ones AND `BrowseView` /
        /// `DetailView`, which have no prototype of their own. ⚠ Two margins in one app is exactly the drift
        /// this file exists to prevent, and a Home that indents by 81 pt beside a Browse that indents by 60 pt
        /// is visible in one press of the Back button.
        static let safeMargin = u * 4.2

        /// How far the Home top bar recedes once focus has left it — the prototype's `.dimmed` (`opacity:.55`).
        ///
        /// ⚠ **STILL A HYPOTHESIS, AND STILL FALSIFIER F6.** The prototype proves the VALUE he wants; it does
        /// not prove SwiftUI can observe "focus left the bar" cleanly, and that is the class of platform claim
        /// this repo has paid for twice (`RailFocus`, B3's grid). So it is built the platform's way — one
        /// `@FocusState` — and the round is what settles it.
        static let topBarDimmed: CGFloat = 0.55

        /// How far an UNFOCUSED profile tile is taken down, so the focused one reads as the choice —
        /// the prototype's `.profile-tile { opacity:.72 }`. ⚠ Falsifier **F1**.
        static let profileTileDimmed: CGFloat = 0.72
    }
}
