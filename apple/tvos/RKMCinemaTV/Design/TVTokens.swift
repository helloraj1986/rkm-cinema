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
        /// `.hero { padding: 3u 4.2u }` and a `32u` band in the prototype.
        ///
        /// ⚠⚠ **W2 SHRANK IT FROM `32u` (614.4 pt, 56.9 % OF THE SCREEN) TO A QUARTER OF THE SCREEN, AND IT IS
        /// HIS CALL, NOT A RESTYLE (2026-09-20).** His report on the built Home: *"there also i can only see
        /// continue watching hero page and one title in continue watching"* — and the arithmetic agrees: bar
        /// `115.2` + hero `614.4` = **729.6** of a 1080 pt screen, which leaves **350.4** for the rails — and ONE
        /// rail is `HomeRules.railHeight` ≈ **382.7**. So the old band showed one rail WITH ITS BOTTOM CUT, and no
        /// more of the page at all.
        ///
        /// ⚠⚠ **AND IT IS A `minHeight`, NOT A `height` — FOUND WHILE SHRINKING IT, AND IT WOULD HAVE BEEN A BUG.**
        /// The band's own copy needs ≈**397 pt** at these tokens (vertical padding 115.2 + eyebrow 32.6 + title
        /// 94.7 + meta 44.4 + progress 52.4 + the CTA row 58), so a FIXED 270 pt band would clip its own buttons —
        /// the hero's height is not a free number while its contents are fixed. ⇒ The band sizes to its own copy
        /// and this is the FLOOR under it (`0.25 × 1080 = 270`), so the artwork stays at least a quarter of the
        /// screen tall and the copy can never be cut on a title with a two-line name.
        ///
        /// ⚠ What it buys, and what it cannot: `HomeRules.firstScreenRails` computes it from these tokens — a rail
        /// is ~382.7 pt and the rails' area is 964.8 pt, so **two whole rails need the hero and the cards to shrink
        /// TOGETHER**, and three rails do not fit at any hero height. ⚠ On a fixed `32u` band, by contrast, the
        /// content happened to fit with 217 pt of artwork left over.
        static let minHeightFraction: CGFloat = 0.25
        static let minHeight = Metric.screenHeight * minHeightFraction
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

        /// ⚠⚠ **THE BAR'S OWN HEIGHT, SO A SCREEN CAN CLEAR IT — AND IT IS A MEASURED NUMBER, NOT A SUM.**
        /// His round-9 file log: `detail-size: bar = 1759x115 pt at x=80 y=59`. ⚠ It cannot be derived from
        /// this table: the bar's contents are a brand, a row of tabs, an icon button and their paddings, and
        /// the MATERIAL behind them is extended upward by `.ignoresSafeArea(edges: .top)` — so the bar is
        /// taller than its own content box and only a measurement says by how much.
        /// ⚠ The one caller is the title screen (W2): its bar FLOATS over the hero, so every state that is
        /// not the hero has to clear it. `u * 6` = 115.2 pt, rounded from the log's 115.
        static let clearance = u * 6
    }

    // MARK: - Artwork that is the wrong SHAPE for its band (`PosterRules`)

    /// ⚠⚠ **NOT A PROTOTYPE NUMBER — tvOS METRICS FOR THE ONE CASE HIS REPORT FOUND (2026-09-20): a 2:3
    /// poster standing in for a 16:9 backdrop.** `PosterRules.treatment` decides *that* the art is shown whole
    /// over a blurred copy of itself; these two numbers decide *how* that copy looks. ⚠ They are here rather
    /// than in the view because a blur radius and an opacity are design values, and a design value inside a
    /// `View` is a value nothing can compare against anything.
    enum Artwork {

        /// The blur on the ambient copy, in points. ⚠ Large on purpose: the job is to remove every hard edge
        /// from a picture that is standing behind the artwork rather than being looked at. `2u` = 38.4 pt on a
        /// 1920 pt screen — at that radius a 16:9 frame is a colour wash and nothing else.
        static let ambientBlur = u * 2

        /// ⚠ **`0.55`, and the dark half is what makes the fitted poster readable.** A blur that is not dimmed
        /// competes with the image in front of it; a film's keyart is often bright, and the whole treatment
        /// exists so that ONE image is legible. Below ~0.4 the ambient layer stops being visible as art and the
        /// band reads as a flat tint; above ~0.7 it starts to be mistaken for the main image.
        static let ambientOpacity: Double = 0.55
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

        // ---- the artwork page (his decision, 2026-09-20)
        //
        // ⚠⚠ **THERE IS NO HERO BAND ANY MORE.** The artwork used to be a `313.2 pt` band at the top of the page
        // with the title block over its lower part; his ask — *"can we make it a background of the details page"*
        // — makes it **the page itself**, so `heroHeightFraction`, `heroMinHeight` and `heroHeight` are DELETED
        // rather than left behind at a value nothing reads. ⚠ A dead token with a mutation attached to it is a
        // gate asserting something no screen does (`references/falsification-and-test-stubs.md`).
        //
        // ⚠ **The band's whole job moved to `DetailRules.titlePageHeight`**: the title block is now a term in the
        // page's flow instead of being drawn inside the band, and that is the +37.6 pt the plan measured. The
        // ONE number his round should argue with is `DetailRules.titlePageHeight`'s total — never a per-band
        // re-derivation.

        /// ⚠⚠ **THE TITLE'S OWN LINE HEIGHT — HIS FILE'S, NOT SWIFTUI'S DEFAULT (W13, 2026-09-20).**
        /// `title-view.html`: `.title-block h1 { font-size:64px; line-height:1.02 }`. ⚠ The fit budget had been
        /// charging the h1 the shared `Metric.lineHeightRatio` of **1.2**, i.e. a line box his file does not
        /// ask for — **29.0 pt over two lines**, and that is exactly the margin that makes the artwork page fit.
        /// ⚠ It applies to the TITLE ONLY: every other line on the page keeps `Metric.lineHeightRatio`, because
        /// the CSS says nothing about them and 1.2 is the honest default for text that has no declared height.
        static let titleLineHeightRatio: CGFloat = 1.02

        // Keep `Metric.lineHeightRatio` (1.2) for the title of set 1's Home — this is set 2's number only.
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

        // ---- the action row (`.actions { padding: 36px 64px 0 }`)
        /// ⚠ **THE ACTION ROW'S OWN TOP PADDING, transcribed rather than approximated by `sectionTitleGap`
        /// (22px).** His title screen opens on `Play`, and `DetailView.below()` draws this row FIRST for that
        /// reason — with the wrong pad the primary verb of the whole screen sits 14px low, which is how a
        /// control ends up within a button's height of the bottom edge.
        static let actionTopPad = px * 36

        // ---- the action button (`.btn`, and it is NOT the Home's `.hero-cta`)
        /// ⚠⚠ **HIS TWO PROTOTYPES DRAW TWO DIFFERENT GOLD BUTTONS, AND BOTH ARE HIS.** Set 1's hero CTA is
        /// `font-size:1.1u`, `padding:0.85u 1.8u`, `radius:0.9u` (`TVTokens.Hero.cta*`), and set 2's `.btn` —
        /// the one on this screen — is absolute px:
        ///
        ///     padding: 16px 30px;  border-radius: 14px;  font-size: 19px;  font-weight: 600
        ///     border: 2px solid transparent;  .is-focused { transform: scale(1.08); border-color: var(--gold-bright) }
        ///
        /// ⇒ `19px → 23.94 pt` against the hero's `1.1u = 21.12 pt`, and the padding is 30 px against
        /// `1.8u = 34.56 pt`. Reading them as one button would be this file's header rule broken in the
        /// direction it was written for. ⚠ What IS shared is the CHROME — one focus ring, one scale
        /// animation, one place the gold fill is decided (`CtaButtonStyle`, which takes these as a preset).
        static let btnFontSize = px * 19
        static let btnPaddingH = px * 30
        static let btnPaddingV = px * 16
        static let btnRadius = px * 14
        static let btnFocusScale: CGFloat = 1.08
        /// `.btn { border: 2px solid transparent }` → `--gold-bright` on focus. ⚠ The app's `accentHover` IS
        /// his `--gold-bright` (U6's palette table), which is why the ring is that token and not a new colour.
        static let btnRingWidth = px * 2
        /// `.btn.is-focused { box-shadow: 0 10px 26px rgba(0,0,0,.45), 0 0 26px rgba(232,179,61,.4) }` — the
        /// second shadow only. ⚠ The first is a DROP shadow under a lifted control, and on a black screen at
        /// three metres it is invisible; the gold one is the part that makes the focused button read as lit,
        /// which is why it is the one kept (`26px → 41.16 pt`, its colour's own 0.4).
        static let btnGlowRadius = px * 26
        static let btnGlowOpacity: Double = 0.4

        // ---- the synopsis (`.synopsis`)
        static let synopsisTopPad = px * 40
        static let synopsisSize = px * 19
        /// `line-height: 1.6` on a `19px` font.
        ///
        /// ⚠⚠ **CORRECTED IN W2: `px * 11.4` (0.6 em) → `px * 7.6` (0.4 em), and the old number was a real
        /// defect rather than a taste call.** `line-height:1.6` means the LINE BOX is **1.6 em** — and SwiftUI
        /// has already supplied about **1.2 em** of that before `lineSpacing` is added (`.lineSpacing` is the
        /// gap BETWEEN lines, not the total). The first version added the full `0.6 em`, so every synopsis line
        /// was **1.8 em apart instead of 1.6** — about 12 % too loose, and the single largest consumer of the
        /// vertical budget this screen has to fit. ⚠ The remaining `0.4 em` is what completes his `1.6`, and
        /// the assumption about SwiftUI's own 1.2 em is named in `DetailRules.synopsisLineHeight` so a round
        /// can correct it in one place.
        static let synopsisLineSpacing = px * 7.6
        /// ⚠⚠ **THE ONE CONTENT CAP ON THIS SCREEN, AND IT IS HIS CALL (2026-09-20): *"cap it at 3 lines"*.**
        /// A description varies from two lines to eight, and it is the only band whose height is the DATA's
        /// rather than the design's — so an uncapped synopsis is an uncappable page (`DetailRules.titlePageHeight`
        /// measures the capped case). ⚠ Three lines at `synopsisMeasure` is where most of his real overviews
        /// already end; a longer one ellipsises rather than pushing the cast off the screen.
        static let synopsisLineLimit = 3
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

        /// ⚠⚠ **THE GAP BETWEEN THE CREDIT LINES — ONE TOKEN, AND IT WAS A LITERAL `6` IN TWO PLACES (W13).**
        ///
        /// `credits()` sits BELOW the synopsis and carries the director / writers / studios lines. ⚠ **It is the
        /// app's own block: his `title-view.html` has no credits at all**, so there is no design value to
        /// transcribe — which is exactly why a bare `6` in the view AND another bare `6` in
        /// `DetailRules.titlePageHeight` was the wrong shape for it, and why the artwork page could not be made to
        /// fit without touching one of them blind.
        ///
        /// ⚠ It is `2` and not `6` because the page has to FIT: the three-line credits block's two gaps are
        /// **8 pt of the budget**, and the artwork page (`titlePageHeight` = 1067.09) lands 12.9 pt inside a
        /// 1080 pt screen — under the 20 pt floor this repo keeps for the line-height estimate. Four points per
        /// gap is invisible between 14 pt lines and it is the cheapest place on the page to find them. ⚠ This is
        /// the ONE visual change the page-as-artwork cost, and it is recorded rather than slipped in.
        static let creditLineGap: CGFloat = 2

        // ⚠⚠ **`bottomSpacer` (`.spacer-bottom { height:100px }`) IS DELETED, NOT KEPT AT ZERO (W13).** It was
        // drawn as the page's tail while `DetailRules.titlePageHeight` never counted it — 126 pt of overflow no
        // gate could see — and the only thing it ever did was keep the last shelf off a scroller's edge. This
        // screen has had no scroller since round 11, so the tail goes and the budget and the page finally
        // describe the same screen.
    }

    // MARK: - ⚠⚠ SET 3'S UNIT (Phase C) — his PLAYER prototype has no `--u` either

    /// ⚠⚠ **THE PLAYER IS DRAWN IN CSS px AGAINST A 1600 × 900 FRAME, SO THE FRAME IS THE ANCHOR.**
    ///
    /// `tvos_ux/3. MediaPlayerUx/rkm-cinema-tvos-player.html` mixes `%`, `rem` and absolute pixels — it is a
    /// browser mock, so it has a viewport. What it does fix is its own canvas:
    /// `.tv { width:100%; height:100%; max-width:1600px; aspect-ratio:16/9 }` — **1600 × 900**. tvOS renders
    /// in a fixed 1920 × 1080 point space, so:
    ///
    /// > **`playerPx` = 1920 / 1600 = `1.2` pt per CSS px**, and a PERCENTAGE in that file is a percentage of
    /// > the same canvas — so `p%` ≡ **`u * p`** (1920 pt = 100u).
    ///
    /// ⚠⚠ **CHECKED AGAINST THE ONE VALUE THREE PROTOTYPES NOW SHARE — the screen margin.** This file pads
    /// `.topbar` and `.bottombar` by `4.2%`; 4.2 % of 1920 = **80.64 pt = `Metric.safeMargin` (4.2u)** — the
    /// margin set 1 fixed and set 2's `px` was derived from. Three files, one margin, which is the strongest
    /// evidence available that this scale is right. ⚠ **If a round shows the player too large or too small,
    /// this is the ONE constant to change — never one metric at a time.**
    static let playerPx: CGFloat = 1.2

    /// The player screen — `tvos_ux/3. MediaPlayerUx/rkm-cinema-tvos-player.html`, transcribed.
    ///
    /// ⚠ Every entry is `playerPx * <his px>` or `u * <his %>`, and the line it came from is named, because a
    /// number that cannot be traced back is a number that has already drifted.
    enum Player {

        // ---- the frame
        /// `.topbar { padding: 3.6% 4.2% 0 }` / `.bottombar { padding: 0 4.2% 4.2% }`.
        static let barPaddingTop = u * 3.6
        static let barPaddingH = u * 4.2
        static let barPaddingBottom = u * 4.2

        // ---- the top bar
        /// `.backbtn { width/height:44px }` and its `svg { width:18px }`.
        static let backSize = playerPx * 44
        static let backGlyph = playerPx * 18
        /// `.film-title { font-size:2.5rem }` — `rem` is the browser's 16 px, so 40 px.
        static let titleSize = playerPx * 40
        static let titleGap = playerPx * 5.6          // `.titleblock { gap:.35em }` at 2.5rem
        static let titleMaxWidth = u * 62             // `.titleblock { max-width:62% }`
        static let metaSize = playerPx * 14.72        // `.meta-row { font-size:.92rem }`
        static let metaGap = playerPx * 10.3          // `.meta-row { gap:.7em }`
        static let metaDot = playerPx * 3             // `.meta-row .dot { width:3px }`
        static let clockSize = playerPx * 15.2        // `.clock { font-size:.95rem }`
        /// `.badge { padding:.22em .62em; border-radius:5px; font-size:.72rem }` — the paddings are `em`, so
        /// they are the badge's OWN font size multiplied, which is exactly what the CSS says.
        static let badgeSize = playerPx * 11.52
        static let badgeRadius = playerPx * 5
        static let badgePaddingH = badgeSize * 0.62
        static let badgePaddingV = badgeSize * 0.22
        static let backrowGap = playerPx * 13.6       // `.backrow { gap:.85em }` at the root 16 px

        // ---- the scrims (`.scrim-top` / `.scrim-bottom`) — KEPT, and they are not decoration: the title,
        // the meta row and the transport all sit on live video, and keyart is often bright exactly there.
        static let scrimTopFraction: CGFloat = 0.34
        static let scrimBottomFraction: CGFloat = 0.48

        // ---- the centre pulse (`@keyframes pulseFeedback`, 0.62 s)
        static let pulseSize = playerPx * 108
        static let pulseGlyph = playerPx * 42
        static let pulseSeconds: Double = 0.62

        // ---- the scrubber (`.scrub-wrap`, `.track`, `.playhead`, `.scrub-tooltip`)
        static let scrubTopPad = playerPx * 22         // `.scrub-wrap { padding-top:1.6em }` at `.86rem`
        static let scrubTimesSize = playerPx * 13.76   // `.scrub-times { font-size:.86rem }`
        static let scrubTimesGap = playerPx * 7.6      // …its `margin-bottom:.55em`
        static let trackHeight = playerPx * 5
        static let trackFocusHeight = playerPx * 8     // `.track.is-focused { height:8px }`
        static let trackRadius = playerPx * 4
        /// `.ticks` — ⚠⚠ **THE ONE ELEMENT IN THIS FILE THE APP CANNOT DRAW.** His tick marks come from a
        /// hardcoded `chapters` array in its JavaScript; the api sends no chapter data at all (measured
        /// 2026-09-20: no `Chapters` anywhere in `backend/`). The constant is transcribed and DELIBERATELY
        /// UNUSED so the gap is visible to the next session rather than looking like an oversight.
        static let tickWidth = playerPx * 2
        static let tickHeight = playerPx * 10
        static let playheadSize = playerPx * 16
        /// `.track.is-focused .playhead { box-shadow: 0 0 0 8px rgba(232,196,104,.18) }` — transcribed as a
        /// RING, and its colour comes from the app's accent rather than from his `--gold-bright` (see the plan's
        /// palette table: his gold is not the brand).
        static let playheadRing = playerPx * 8
        static let playheadRingOpacity: CGFloat = 0.18
        static let tooltipLift = playerPx * 14         // the focused tooltip's `translate(-50%,-14px)`
        static let tooltipRadius = playerPx * 6
        static let tooltipPaddingH = playerPx * 8.6    // `.tooltip-time { padding:.25em .65em }`
        static let tooltipPaddingV = playerPx * 3.3
        static let tooltipSize = playerPx * 13.76

        // ---- the transport row (`.controls`, `.ctl-btn`)
        static let controlSize = playerPx * 58
        static let controlPrimarySize = playerPx * 74
        static let controlGlyph = playerPx * 22
        static let controlPrimaryGlyph = playerPx * 26
        static let controlGap = playerPx * 13.6        // `.controls { gap:.85em }`
        static let controlSpacer = playerPx * 22.4     // `.ctl-spacer { width:1.4em }`
        static let controlLabelSize = playerPx * 12.48 // `.ctl-label { font-size:.78rem }`
        static let controlLabelLift = playerPx * 26.2  // `top:-2.1em` at that font
        static let focusScale: CGFloat = 1.14          // `--focus-scale`
        static let focusRingWidth = playerPx * 2
        /// `.ctl-btn.primary { background:rgba(245,242,234,.98) }` — the near-white play button, which is the
        /// only element on the screen that is brighter than the film.
        static let primaryFillOpacity: CGFloat = 0.98

        // ---- the info panel (`.info-panel`, `.info-inner`)
        static let infoTopFraction: CGFloat = 0.32
        static let infoPaddingBottom = u * 5.2
        static let infoMeasure = playerPx * 640        // `.info-inner { max-width:640px }`
        static let infoBodySize = playerPx * 16        // `.info-inner p { font-size:1rem }`
        static let infoBodyLineSpacing = playerPx * 8.8  // `line-height:1.55` on a 1rem body
        static let infoGap = playerPx * 11.2           // `.info-inner { gap:.7em }`
        static let tagSize = playerPx * 13.6
        static let tagRadius = playerPx * 20
        static let tagPaddingH = playerPx * 9.5
        static let tagPaddingV = playerPx * 3.8
        static let tagGap = playerPx * 8.2

        // ---- the settings drawer (`.settings-panel` and friends)
        /// `width: min(58%, 760px)` — ⚠ transcribed as the MINIMUM of the two, exactly as CSS resolves it:
        /// 58 % of 1920 is 1113.6 pt and the 760 px cap is 912 pt, so **the cap wins** on every tvOS screen.
        static let settingsFraction: CGFloat = 0.58
        static let settingsMaxWidth = playerPx * 760
        static let settingsTopPad = u * 5.5            // `padding:5.5% 0 4.5%`
        static let settingsBottomPad = u * 4.5
        static let settingsHeaderSize = playerPx * 12.48  // `.settings-header { font-size:.78rem }`
        static let settingsHeaderTop = u * 2.6
        static let settingsHeaderInset = playerPx * 41.6  // `left/right:2.6em` at the root 16 px
        static let navWidth = playerPx * 230
        static let navGap = playerPx * 4.8             // `.settings-nav { gap:.3em }`
        static let navItemSize = playerPx * 16         // `.settings-nav-item { font-size:1rem }`
        static let navItemRadius = playerPx * 9
        static let navItemPaddingH = playerPx * 14.4   // `.8em .9em`
        static let navItemPaddingV = playerPx * 12.8
        static let navFocusScale: CGFloat = 1.06       // `.settings-nav-item.is-focused { transform:scale(1.06) }`
        static let contentPaddingH = playerPx * 44.8   // `.settings-content { padding:0 2.8em }`
        static let contentGap = playerPx * 24          // …`gap:1.5em`
        static let paneGap = playerPx * 17.6           // `.settings-pane { gap:1.1em }`
        static let paneTitleSize = playerPx * 25.6     // `.settings-section-title { font-size:1.6rem }`
        static let paneDescSize = playerPx * 13.6      // `.settings-desc { font-size:.85rem }`
        static let segGap = playerPx * 9.6             // `.segmented { gap:.6em }`
        static let segSize = playerPx * 14.72          // `.seg-btn { font-size:.92rem }`
        static let segRadius = playerPx * 9
        static let segPaddingH = playerPx * 16.9       // `.62em 1.15em` at `.92rem`
        static let segPaddingV = playerPx * 9.1
        static let segFocusScale: CGFloat = 1.09       // `.seg-btn.is-focused { transform:scale(1.09) }`
        static let listGap = playerPx * 4.8            // `.settings-list { gap:.3em }`
        static let listItemSize = playerPx * 16        // `.settings-item` inherits 1rem
        static let listItemRadius = playerPx * 8
        static let listItemPaddingH = playerPx * 12.8  // `.7em .8em`
        static let listItemPaddingV = playerPx * 11.2
        static let listFocusScale: CGFloat = 1.04      // `.settings-item.is-focused { transform:scale(1.04) }`
        static let footerSize = playerPx * 13.12       // `.settings-footer { font-size:.82rem }`
        static let footerTopPad = playerPx * 13.2      // …`padding-top:1.1em`
        static let checkSize = playerPx * 14           // the `✓` on a selected row

        // ---- the toast (`.toast`)
        static let toastBottom = u * 6
        static let toastRadius = playerPx * 24
        static let toastSize = playerPx * 13.6         // `.toast { font-size:.85rem }`
        static let toastPaddingH = playerPx * 16.3
        static let toastPaddingV = playerPx * 9.5

        /// The subtitle cues — ⚠ **A tvOS ADDITION, not a transcription.** His file has no caption strip (the
        /// web player draws cues in its own `Player.tsx`), so there is nothing to transcribe: the strip sits
        /// above the transport row, in the app's own primary colour with a shadow, because a caption over a
        /// bright frame is unreadable without one.
        static let cueBottom = u * 12
        static let cueSize = playerPx * 20
        static let cueMeasure = u * 70

        /// tvOS-only tints for the player's glass. ⚠ Same status as `Colour.topBarTint`: the blur itself is the
        /// platform's material, these are only the tints under it, transcribed from his `--glass` /
        /// `--glass-strong` — and kept OUT of the generated table so they cannot become a brand change.
        static let glass = RGBAColor(red: 16 / 255, green: 16 / 255, blue: 18 / 255, alpha: 0.66)
        static let glassStrong = RGBAColor(red: 12 / 255, green: 12 / 255, blue: 14 / 255, alpha: 0.86)
    }

    /// tvOS layout metrics that have no prototype line to point at.
    enum Metric {

        /// ⚠ **THE CANVAS, IN THE UNIT THIS WHOLE TABLE IS WRITTEN IN.** `u` is 1 % of the screen width, so
        /// 100u = the 1920 pt tvOS renders in. Named because a rule OUTSIDE this file now needs to say "the
        /// width of a screen" as arithmetic rather than by writing 1920 by hand — `DetailRules.castCapacity`
        /// is the caller, and its job is to make a row FIT.
        ///
        /// ⚠⚠ **AND SINCE W1 THIS IS THE BOX THE SCREENS ACTUALLY LAY OUT IN, NOT JUST THE CANVAS.** The app
        /// fills tvOS's 1920 × 1080 point space (`AppRootView`) and applies each prototype's own margin itself,
        /// so a rule about WHAT FITS counts from here. Before W1 the screens were laid out inside the safe area
        /// and the prototypes' margins were added ON TOP of it — a double inset that cost this app four rounds
        /// (KNOWN_ISSUES #13).
        static let screenWidth = u * 100

        /// ⚠ **The canvas' height: 1080 pt, the same on every panel.** A 4K Apple TV renders these same
        /// points at `scale = 2.0` (Apple's own Apple-TV-4K guidance) — so the tvOS point space is NOT a
        /// property of the television, and no layout here needs a panel check. Named because two fractions of
        /// the SCREEN depend on it and both used to carry a hand-multiplied constant: the title hero's `66vh`
        /// (`Title.heroHeight`) and its `min-height`.
        static let screenHeight = u * 56.25

        /// ⚠⚠ **THE OVERSCAN INSET tvOS PUTS AROUND EVERY VIEW — MEASURED, NOT ASSUMED.** His round-9 log,
        /// straight out of the app's own file log on the Apple TV 4K simulator:
        ///
        ///     detail-size: screen = 1760x960 pt at x=80 y=60
        ///
        /// i.e. a view that RESPECTS the safe area is handed `80 pt` inside each side of the 1920 pt canvas
        /// (60 pt top and bottom). ⚠ Apple's own tvOS figure is **90 / 60** — a device and a simulator do not
        /// agree, which is the reason this is a measurement and not a citation.
        ///
        /// ⚠⚠ **AND WHAT W1 CHANGED IS WHAT IT IS FOR: the app's screens do NOT respect it.** Every prototype
        /// indents by `4.2u` of the SCREEN (`TVTokens.Metric.safeMargin`, set 2's `64px`), and adding tvOS's
        /// inset to that put every word on the screen 160.64 pt from the panel edge instead of his 80.64 pt,
        /// in a box 9.1 % narrower than the design — which is the fault he reported. So the inset is kept here
        /// as the reason the ARTWORK may bleed and the MARGIN may not be doubled, and nothing subtracts it.
        /// ⚠ The exposure this accepts, stated: a television cropping more than 4.2 % of the frame can clip the
        /// outer edge of `safeMargin`. The knob if a round ever shows that is `safeMargin` — one number.
        static let overscanInsetX: CGFloat = 80

        /// …and the vertical half of the same measurement: **60 pt** top and bottom (`y=60` in the same log
        /// line). ⚠ Used for ONE thing — putting the debug HUD back where it was before the screens gave the
        /// safe area up (`AppRootView`), because a readout whose position moves between rounds stops being
        /// comparable with the last round's screenshot.
        static let overscanInsetY: CGFloat = 60

        /// ⚠ **The width a screen's CONTENT really has: the canvas minus the design's own margin on each
        /// side.** It is the number every fit rule counts against (`DetailRules.castCapacity` is the first),
        /// and since W1 it is `screenWidth` minus nothing else — the safe area is NOT subtracted, because the
        /// screens fill the canvas. ⚠ It used to be 1760 (the canvas minus 2 × 80), which is what the app's
        /// layout box WAS while it respected the safe area: a correct reading of the wrong box.
        static let layoutWidth = screenWidth

        /// ⚠ **THE LINE BOX A SYSTEM FONT GIVES A `Text` BEFORE ANY `lineSpacing` — about 1.2 em.**
        ///
        /// ⚠⚠ **NAMED HERE BECAUSE TWO SCREENS' FIT ARITHMETIC DEPENDS ON IT, AND BECAUSE IT IS AN ASSUMPTION.**
        /// `Text.lineSpacing` is the gap BETWEEN lines; it does not replace the line box. So a CSS
        /// `line-height: 1.6` is completed by **0.4 em** (`Title.synopsisLineSpacing`), and every band height
        /// that has text in it is `size × this` (`DetailRules.titlePageHeight`, `HomeRules.railHeight`).
        /// ⚠ Nothing on this machine renders a `Text`, so this number **cannot be measured here** — it is the
        /// one assumption in both budgets, both screens log their real height to the file log, and if the sums
        /// are out this is the single constant to move (never a per-band re-derivation).
        static let lineHeightRatio: CGFloat = 1.2

        /// ⚠ The screens' horizontal margin.
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
