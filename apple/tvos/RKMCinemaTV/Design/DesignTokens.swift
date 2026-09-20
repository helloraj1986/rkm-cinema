// ⚠⚠ GENERATED FILE — DO NOT EDIT BY HAND, and do not hand-copy a hex in beside it.
//
// Source of truth: frontend/src/styles/index.css
// Regenerate:      python3 apple/scripts/generate-design-tokens.py
// Drift gate:      python3 apple/scripts/check-design-tokens.py   (requires this file to be a no-op diff)
//
// ⚠⚠ WHY THIS IS GENERATED RATHER THAN TRANSCRIBED. The tvOS buildspec's §1 colour table claims to be
// extracted from this app's web UI. It is not: measured 2026-09-19, **8 of its 10 values were wrong,
// including the brand accent** — it specified gold `#F2B93A` where the app is `#ffc400`
// (`docs/TVOS_UX_PLAN.md` §0.1). A hand-copied table also has no way to notice the web app changing. So
// the CSS custom properties are the source, this file is generated from them, and a gate fails the round
// the moment the two drift — the same trade `docs/api/openapi.v1.json` makes for the wire format.
//
// ⚠ This file is `Foundation`-only ON PURPOSE, so `apple/scripts/check-apple-typecheck.sh` compiles it on
// Linux. It carries NUMBERS, not `SwiftUI.Color` — the bridge to SwiftUI lives in `Design/DesignColours.swift`,
// which is a mechanical conversion with no rule in it to run.
//
// ⚠ A tvOS-only difference does NOT belong here — it belongs in `Design/TVTokens.swift`, and it carries
// its reason. A value migrating from there into this file stops being a tvOS decision and becomes a brand
// change that affects the phone and the web.
//
// ⚠ NOT generated, deliberately:
//   · --z-sticky — DOM stacking order — tvOS has no z-index
//   · --z-header — DOM stacking order — tvOS has no z-index
//   · --z-dropdown — DOM stacking order — tvOS has no z-index
//   · --z-popover — DOM stacking order — tvOS has no z-index
//   · --z-drawer — DOM stacking order — tvOS has no z-index
//   · --z-modal — DOM stacking order — tvOS has no z-index
//   · --z-toast — DOM stacking order — tvOS has no z-index
//   · --z-player — DOM stacking order — tvOS has no z-index

import Foundation

/// A colour as four 0…1 components.
///
/// ⚠ The PARSING happened in Python, at generation time: this type holds numbers, so there is no hex
/// parser in the app to be wrong about a three-digit hex or an alpha channel. `Equatable` for tests,
/// `Sendable` because a token table is a constant.
struct RGBAColor: Equatable, Sendable {
    let red: Double
    let green: Double
    let blue: Double
    let alpha: Double
}

/// The web app's palette, radii and spacing — generated, never transcribed.
enum DesignTokens {

    /// `index.css`'s colour foundation (§2.3). ⚠ These are the WEB app's values. Where tvOS deliberately
    /// differs, the difference is in `TVTokens` with its reason attached.
    enum Colour {
        static let background = RGBAColor(red: 8.0 / 255.0,
                                       green: 9.0 / 255.0,
                                       blue: 11.0 / 255.0,
                                       alpha: 1.0)
        static let surface1 = RGBAColor(red: 16.0 / 255.0,
                                       green: 18.0 / 255.0,
                                       blue: 22.0 / 255.0,
                                       alpha: 1.0)
        static let surface2 = RGBAColor(red: 21.0 / 255.0,
                                       green: 23.0 / 255.0,
                                       blue: 28.0 / 255.0,
                                       alpha: 1.0)
        static let surface3 = RGBAColor(red: 27.0 / 255.0,
                                       green: 30.0 / 255.0,
                                       blue: 36.0 / 255.0,
                                       alpha: 1.0)
        static let card = RGBAColor(red: 23.0 / 255.0,
                                       green: 25.0 / 255.0,
                                       blue: 30.0 / 255.0,
                                       alpha: 1.0)
        static let border = RGBAColor(red: 255.0 / 255.0,
                                       green: 255.0 / 255.0,
                                       blue: 255.0 / 255.0,
                                       alpha: 0.08)
        static let textPrimary = RGBAColor(red: 245.0 / 255.0,
                                       green: 245.0 / 255.0,
                                       blue: 247.0 / 255.0,
                                       alpha: 1.0)
        static let textSecondary = RGBAColor(red: 167.0 / 255.0,
                                       green: 170.0 / 255.0,
                                       blue: 178.0 / 255.0,
                                       alpha: 1.0)
        static let textMuted = RGBAColor(red: 112.0 / 255.0,
                                       green: 116.0 / 255.0,
                                       blue: 126.0 / 255.0,
                                       alpha: 1.0)
        static let accent = RGBAColor(red: 255.0 / 255.0,
                                       green: 196.0 / 255.0,
                                       blue: 0.0 / 255.0,
                                       alpha: 1.0)
        static let accentHover = RGBAColor(red: 255.0 / 255.0,
                                       green: 212.0 / 255.0,
                                       blue: 59.0 / 255.0,
                                       alpha: 1.0)
        static let success = RGBAColor(red: 53.0 / 255.0,
                                       green: 208.0 / 255.0,
                                       blue: 127.0 / 255.0,
                                       alpha: 1.0)
        static let warning = RGBAColor(red: 255.0 / 255.0,
                                       green: 176.0 / 255.0,
                                       blue: 32.0 / 255.0,
                                       alpha: 1.0)
        static let danger = RGBAColor(red: 255.0 / 255.0,
                                       green: 91.0 / 255.0,
                                       blue: 91.0 / 255.0,
                                       alpha: 1.0)
    }

    /// `index.css`'s radii (§41).
    enum Radius {
        static let sm: CGFloat = 6.0
        static let md: CGFloat = 10.0
        static let lg: CGFloat = 14.0
        static let xl: CGFloat = 20.0
    }

    /// `index.css`'s spacing scale (§41).
    enum Space {
        static let s1: CGFloat = 4.0
        static let s2: CGFloat = 8.0
        static let s3: CGFloat = 12.0
        static let s4: CGFloat = 16.0
        static let s5: CGFloat = 24.0
        static let s6: CGFloat = 32.0
        static let s7: CGFloat = 48.0
        static let s8: CGFloat = 64.0
    }
}
