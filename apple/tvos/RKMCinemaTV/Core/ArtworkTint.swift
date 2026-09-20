import Foundation

/// One sampled artwork colour, as components.
/// ⚠⚠ **NOT a SwiftUI `Color`, and that is the whole reason this type exists** — this file has to compile and RUN
/// on Linux (`apple/scripts/check-tvos-core.py`), where there is no SwiftUI. The bridge to a `Color` is one
/// function in `Design/DesignColours.swift`, which is the app's one sanctioned place to build a colour.
struct ArtworkRGB: Equatable {
    let red: Double
    let green: Double
    let blue: Double

    /// ⚠ **Rec. 709 relative luminance** — the same weighting the platform's own colour maths uses. It is what
    /// decides how deep the scrim has to be: a bright poster needs more than a dark one, and that single number
    /// is the difference between text that is legible over ANY poster and text that is legible over the one
    /// somebody tested.
    var luminance: Double { 0.2126 * red + 0.7152 * green + 0.0722 * blue }

    /// ⚠ HSB saturation, from the same components. Artwork is usually a muted background with one vivid accent;
    /// this is what lets `ArtworkTint.tint` prefer the accent over the mud.
    var saturation: Double {
        let high = max(red, green, blue)
        let low = min(red, green, blue)
        return high <= 0 ? 0 : (high - low) / high
    }
}

/// ⚠⚠ **THE PAGE'S SCRIM, DERIVED FROM THE ARTWORK'S OWN COLOUR — HIS ASK, 2026-09-20:** *"can we make it a
/// background of the details page with using gradients color depening on the poster so that the text on the
/// details page can be seen clearly"*.
///
/// ⚠⚠ **WHY THIS IS A PURE FILE AND NOT SIX LINES INSIDE `DetailView`.** Its own header states the rule this repo
/// keeps paying for: a decision that can be arithmetic is arithmetic, and one that lives in a view is a decision
/// **no test on this machine can reach** — there is no SwiftUI here, so a `View`'s colour maths is verified only by
/// his eyes on a television, one round at a time. Both halves below are executed (`check-tvos-core.py`).
///
/// ⚠ **What is NOT here:** turning pixels into samples, and turning a colour into a `Color`. Those are UIKit and
/// SwiftUI respectively (`Home/PosterCard.swift`, `Design/DesignColours.swift`) — this file is only the arithmetic
/// between them.
enum ArtworkTint {

    // ---------------------------------------------------------------- the colour

    /// ⚠ A sample darker than this is thrown away: artwork has black bars, vignettes and letterboxing, and a
    /// scrim built from them would be a scrim built from nothing. `0.08` is just above the app's own `void`
    /// (`#0A0B0D` is `0.043` luminance), so the page's own background colour never votes.
    static let darkestKept: Double = 0.08

    /// ⚠ And a sample brighter than this is thrown away too: titles, credits and borders burned into artwork are
    /// near-white, and letting them vote would drag every scrim toward grey.
    static let brightestKept: Double = 0.95

    /// ⚠ Below this saturation nothing is "colourful", and the saturation weighting is dropped rather than
    /// applied to noise — a genuinely GREY poster still gets a scrim built from its own grey.
    static let saturatedEnough: Double = 0.12

    /// ⚠⚠ **WHAT COLOUR A SET OF SAMPLES MEANS.** The samples are weighted by `saturation²`, so a vivid accent
    /// outweighs the muted background it sits on — which is what makes the wash read as *that poster's* colour
    /// rather than as the average of everything in the frame (an average of a poster is almost always mud).
    ///
    /// ⚠ Returns `nil` when nothing survives the two cuts: **an artwork with no usable colour gets the app's own
    /// neutral scrim, not a black one**, and that is a real case — a title whose artwork failed to load, or a
    /// poster that is genuinely all black.
    static func tint(samples: [ArtworkRGB]) -> ArtworkRGB? {
        let kept = samples.filter { $0.luminance >= darkestKept && $0.luminance <= brightestKept }
        guard !kept.isEmpty else { return nil }

        let anyColour = kept.contains { $0.saturation >= saturatedEnough }
        let weights = kept.map { anyColour ? $0.saturation * $0.saturation : 1 }
        let total = weights.reduce(0, +)
        guard total > 0 else { return nil }

        return ArtworkRGB(red: weighted(kept, weights, total) { $0.red },
                          green: weighted(kept, weights, total) { $0.green },
                          blue: weighted(kept, weights, total) { $0.blue })
    }

    private static func weighted(_ samples: [ArtworkRGB], _ weights: [Double], _ total: Double,
                                 _ component: (ArtworkRGB) -> Double) -> Double {
        var sum = 0.0
        for (sample, weight) in zip(samples, weights) {
            sum += component(sample) * weight
        }
        return sum / total
    }

    // ---------------------------------------------------------------- the scrim

    /// ⚠ The app's `void` (`#0A0B0D`, `frontend/src/styles/index.css`), as components. ⚠ It is a LITERAL here and
    /// not `RKMColour.background` because this file is Foundation-only; the harness pins the two against each
    /// other so they cannot drift.
    static let void = ArtworkRGB(red: 10.0 / 255, green: 11.0 / 255, blue: 13.0 / 255)

    /// The scrim, as data — the view draws it and decides nothing.
    struct Scrim: Equatable {
        /// The colour the wash is tinted with: the artwork's own, or `void` when there is none.
        /// ⚠⚠ **NAMED `tintColour` AND NOT `tint`, AND THAT IS NOT STYLE.** `ArtworkTint` also has a STATIC METHOD
        /// `tint(samples:)`, and a member called `tint` on a nested type makes `someScrim.tint` ambiguous for the
        /// compiler — it reported `cannot convert value of type 'ArtworkTint.Scrim' to expected argument type
        /// 'ArtworkRGB'`, measured. ⇒ the property is named for what it IS, and the collision cannot come back.
        let tintColour: ArtworkRGB
        /// ⚠ A FLAT wash over the whole page. **This is the term that guarantees contrast in the middle**, where
        /// the synopsis, the credits and the cast sit — a gradient alone leaves the centre of the page on raw
        /// artwork, which is exactly where a bright poster beats the text.
        let wash: Double
        /// The artwork's own colour at the page's TOP edge, where the bar and the title block sit.
        let tintAlpha: Double
        /// Where the tint has faded out (fraction of the page's height, from the top).
        let tintFade: Double
        /// The floor at the BOTTOM edge, for the cast row.
        let baseAlpha: Double
    }

    /// ⚠⚠ **THE LEGIBILITY RULE, IN ONE LINE: THE DEPTH FOLLOWS THE ARTWORK'S OWN LUMINANCE.** A dark poster is
    /// left almost alone; a bright one is washed heavily. ⚠ The bounds are the calibration and are the numbers his
    /// round should argue with — `0.42` is enough over a dark frame, `0.84` is heavy enough for white text over a
    /// white poster, and the band between them is what makes the scrim *change* from title to title (falsifier
    /// **A5**: two titles must not share one wash).
    static let washRange: ClosedRange<Double> = 0.42...0.84

    /// ⚠ And the tint's own alpha runs the other way: a BRIGHT artwork needs MORE of its own colour over the top
    /// to hold the title, where a dark one needs almost none.
    static let tintAlphaRange: ClosedRange<Double> = 0.30...0.70

    static func scrim(for tint: ArtworkRGB?) -> Scrim {
        guard let tint else {
            // ⚠ The neutral case, and it is his prototype's own scrim measured against a flat page: a plain wash
            // with no tint at all. It is what the screen shows before the artwork arrives, and what a title with
            // no usable colour keeps.
            return Scrim(tintColour: void, wash: 0.55, tintAlpha: 0, tintFade: 0, baseAlpha: 0.85)
        }
        let lum = min(max(tint.luminance, 0), 1)
        return Scrim(tintColour: tint,
                     wash: washRange.lowerBound + (washRange.upperBound - washRange.lowerBound) * lum,
                     tintAlpha: tintAlphaRange.lowerBound
                        + (tintAlphaRange.upperBound - tintAlphaRange.lowerBound) * (1 - lum),
                     tintFade: 0.45,
                     baseAlpha: 0.85)
    }

    // ---------------------------------------------------------------- the Home's hero band (W14)

    /// ⚠⚠ **THE HERO BAND'S WASH IS A FRACTION OF THE PAGE'S, AND THE FRACTION IS A NAMED CONSTANT HERE — NOT A
    /// MAGIC NUMBER IN A VIEW (`W14`, his instruction: *"the Home's hero gets the same tinted scrim"*).**
    ///
    /// ⚠ **Why it is not the same strength.** On the title page the wash is the ONLY thing between the text and
    /// the artwork over most of its surface, so it carries the whole contrast job. A **hero band** is different:
    /// its copy sits ON the band's own fade to solid `background` — a gradient that exists because the band has to
    /// blend into the page below it — so most of the contrast is already there, and a page-strength wash on top of
    /// it would flatten the keyart into a grey rectangle. That is the one thing a hero band exists to avoid.
    ///
    /// ⚠ **Everything else is shared**: the colour, the luminance rule behind its depth, and where it fades out.
    /// ⇒ two surfaces, one rule, and the one number that differs says exactly why it differs.
    static let bandWashFactor: Double = 0.55

    static func bandScrim(for tint: ArtworkRGB?) -> Scrim {
        let page = scrim(for: tint)
        return Scrim(tintColour: page.tintColour,
                     wash: page.wash * bandWashFactor,
                     tintAlpha: page.tintAlpha,
                     tintFade: page.tintFade,
                     baseAlpha: page.baseAlpha)
    }
}
