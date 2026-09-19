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
        static let lockSize = u * 2.2
        static let lockFontSize = u * 1.1
        static let lockRing = u * 0.22
        /// ⚠ The white ring around the FOCUSED avatar only (`0.28u`) — the ring is on the avatar, the lift is
        /// on the tile, exactly as the prototype draws it.
        static let focusRing = u * 0.28
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
