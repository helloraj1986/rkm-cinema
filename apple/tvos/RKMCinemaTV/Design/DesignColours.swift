import SwiftUI

/// The bridge from the token tables to `SwiftUI.Color` — and it is deliberately the ONLY thing here.
///
/// ⚠⚠ **THIS FILE IS OUTSIDE EVERY GATE, AND THAT IS SAID OUT LOUD RATHER THAN DISCOVERED.** There is no
/// SwiftUI on Linux, so `apple/scripts/check-apple-typecheck.sh` cannot compile it and
/// `check-tvos-core.py` cannot run it. The mitigation is the shape of the file: it holds **no rule that can
/// be wrong** — one subtraction-free conversion from four components the generator already parsed and
/// proved, plus three named accessors. Anything with a decision in it belongs in `DesignTokens.swift`
/// (generated, drift-gated) or `TVTokens.swift` (hand-written, typechecked here on Linux), not in this file.
///
/// ⚠ Use `.sRGB`, explicitly. `Color(red:green:blue:)` is the sRGB initialiser on Darwin and would look
/// identical *on his Apple TV* — but a colour built without stating its space is the kind of difference that
/// surfaces on somebody else's display and diagnoses as nothing.
extension RGBAColor {

    /// This colour as a SwiftUI colour.
    var color: Color {
        Color(.sRGB, red: red, green: green, blue: blue, opacity: alpha)
    }
}

/// The names the tvOS views speak, so no view has to know which of the two token files a value came from.
///
/// ⚠ **`muted` reads `TVTokens`, every other entry reads the generated `DesignTokens`** — that asymmetry IS
/// the design. `muted` is the one token a television overrides (why: `TVTokens.Colour.textMuted`), and a
/// view asking for "the de-emphasised caption colour" should get the television's answer without having to
/// remember which file it lives in. ⚠ `apple/scripts/check-design-tokens.py` fails the round if a tvOS
/// source reaches past this and reads `DesignTokens.Colour.textMuted` directly.
enum RKMColour {

    // ---- from the generated table (identical to the web app)
    static let background = DesignTokens.Colour.background.color
    static let surface1 = DesignTokens.Colour.surface1.color
    static let surface2 = DesignTokens.Colour.surface2.color
    static let surface3 = DesignTokens.Colour.surface3.color
    static let card = DesignTokens.Colour.card.color
    static let border = DesignTokens.Colour.border.color
    static let primary = DesignTokens.Colour.textPrimary.color
    static let secondary = DesignTokens.Colour.textSecondary.color
    static let accent = DesignTokens.Colour.accent.color
    static let accentHover = DesignTokens.Colour.accentHover.color
    static let success = DesignTokens.Colour.success.color
    static let warning = DesignTokens.Colour.warning.color
    static let danger = DesignTokens.Colour.danger.color

    // ---- the tvOS-only colours (each with its reason in `TVTokens.Colour`)
    static let muted = TVTokens.Colour.textMuted.color
    static let avatarTop = TVTokens.Colour.avatarTop.color
    static let avatarBottom = TVTokens.Colour.avatarBottom.color
    static let profileGlow = TVTokens.Colour.profileGlow.color
    static let topBarTint = TVTokens.Colour.topBarTint.color

    /// The avatar circle both screens draw — the Profile Switcher's tile and the top bar's button, so the
    /// same person's initials sit on the same gradient wherever they appear.
    ///
    /// ⚠ A `LinearGradient` and not a flat fill: it is the one place in either screen where the app draws a
    /// lit surface rather than a token colour, and it is the prototype's (`160deg`).
    static let avatarGradient = LinearGradient(
        colors: [avatarTop, avatarBottom],
        startPoint: .top,
        endPoint: .bottom
    )
}
