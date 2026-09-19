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
///   * **A tvOS METRIC that was never in the CSS** (safe margins, focus/dimming behaviour) lives here as
///     well, because a generator for a hand-written number is worse than no generator — there is no source
///     in the CSS to generate it from, and pretending otherwise would make the drift gate lie.
///
/// ⚠⚠ **A TYPE SCALE IS DELIBERATELY *NOT* HERE — with exactly two exceptions, both named.** The tvOS
/// buildspec proposes a whole scale (`64/32/22/16/14`), and it is prose: it was never measured against this
/// app, and its colour table — the one part of it that COULD be checked — was wrong in eight of ten values
/// (`docs/TVOS_UX_PLAN.md` §0.1). The accepted screens' type sizes are what his simulator round verified, so
/// they stay where they are, as literals. The TWO sizes taken from it are the titles of the two screens this
/// phase actually redesigns (`Metric.profileTitle`, `Metric.heroTitle`); retro-fitting the rest across
/// screens this phase does not touch is Phase D polish, and adopting half a scale everywhere would be exactly
/// the second copy this file's header warns about.
///
/// ⚠ `Foundation`-only, so `apple/scripts/check-apple-typecheck.sh` compiles it on Linux. It carries
/// NUMBERS; the conversion to `SwiftUI.Color` is in `Design/DesignColours.swift`.
enum TVTokens {

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
        /// ⚠ **HIS DECISION (2026-09-19): tvOS only — the web keeps `#70747e`.** (`#70747e` is a genuine
        /// accessibility miss there too, but that is a one-line change to `frontend/`, and this phase writes
        /// nothing under `frontend/`.) ⚠ Which is precisely why a view must read THIS property and never
        /// `DesignTokens.Colour.textMuted` — `apple/scripts/check-design-tokens.py` fails the round if any
        /// tvOS source does the latter.
        static let textMuted = RGBAColor(red: 129 / 255,
                                         green: 133 / 255,
                                         blue: 143 / 255,
                                         alpha: 1)
    }

    /// tvOS layout metrics that have no CSS source.
    enum Metric {

        /// The screens' horizontal margin.
        ///
        /// ⚠ Not invented here: it is the value every accepted tvOS screen already pads by
        /// (`HomeView`, `BrowseView`, `ProfilesView` all use `padding(.horizontal, 60)`), collected into one
        /// place so the next screen cannot pick a fourth number. On a TV this is the safe-area inset a
        /// television's overscan would otherwise eat.
        ///
        /// ⚠ **The buildspec asks for 90pt left/right and 60pt top/bottom, and 90 is NOT adopted here.**
        /// Changing the margin changes every screen at once — including the two his simulator round already
        /// accepted — so it is a whole-app decision (Phase D), not a side effect of the Profile Switcher's
        /// redesign. Recorded rather than quietly ignored.
        static let safeMargin: CGFloat = 60

        /// "Who's watching?" — the buildspec's screen-title size (§1).
        ///
        /// ⚠ One of exactly TWO sizes taken from the buildspec's type scale, because these are the two
        /// screens this phase redesigns. The rest of the scale is deliberately not adopted, for the reason in
        /// this file's header — a half-adopted scale is the second copy of a rule, which is what the phase
        /// exists to avoid.
        static let profileTitle: CGFloat = 64

        /// The Home hero's title — the buildspec's hero-title size (§1), and the other adopted one.
        static let heroTitle: CGFloat = 68

        /// How far the Home top bar recedes once focus has left it.
        ///
        /// ⚠ **A HYPOTHESIS, NOT A MEASUREMENT.** The buildspec asks for it, and whether SwiftUI on tvOS can
        /// observe focus leaving a container cleanly is EXACTLY the kind of platform claim this repo has paid
        /// for twice (the deleted `RailFocus`, and B3's 2-D grid — see `RailView`'s header). So it is built the
        /// platform's way, the value lives here so the round has one line to change, and falsifier **F6**
        /// ("the top bar dims when focus leaves it") is what settles it. If it cannot be observed cleanly the
        /// honest fallback is the platform's own focus treatment, not a hand-rolled dim.
        static let topBarDimmed = 0.55

        /// How far an UNFOCUSED profile tile is taken down, so the focused one reads as the choice.
        ///
        /// ⚠ Same status as `topBarDimmed`: the buildspec's number, and falsifier **F1** is what tests it
        /// ("the Profile row reads as one choice"). ⚠ It is only observable because SwiftUI publishes
        /// per-tile focus state — no arithmetic, no nearest-centre maths, which is the trap §3 of the plan
        /// names.
        static let profileTileDimmed = 0.72
    }
}
