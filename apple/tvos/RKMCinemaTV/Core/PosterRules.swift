import Foundation

// How ONE piece of artwork should be drawn into the band it was given.
//
// ⚠⚠ **WHY THIS IS A PURE FILE AND NOT THREE LINES INSIDE `PosterImageView`, RUN ON LINUX LIKE EVERY OTHER
// RULE HERE.** His report, 2026-09-20: *"i can only see 1/3rd of the poster"* — the title screen's band fell
// back from a missing 16:9 backdrop to the item's **2:3 poster** (`PosterLoader.fallBackToPoster`, which is the
// web's own chain), and the view drew it with `aspectRatio(contentMode: .fill)` into a **1920 × 313** band. A
// 2:3 image asked to FILL a 6:1 band is scaled until its height covers the band and then **60 % of its width is
// cut off** — the poster's middle third, which is exactly what he described.
//
// ⚠ The defect is invisible to every gate on this machine (there is no SwiftUI here), it is the second time
// this class has cost a round, and the fix is one predicate — so the predicate is executed rather than eyeballed
// (`apple/scripts/check-tvos-core.py`).
//
// ⚠ **WHAT IS NOT HERE: how the ambient layer is drawn.** This file decides *which treatment*; the blur radius,
// the opacity and the `Image` calls are SwiftUI and live in `PosterImageView` / `TVTokens.Artwork`.

/// Which of the two treatments a piece of artwork gets in the band it must fill.
enum ArtworkTreatment: Equatable {
    /// The image covers the band, cropping the overflow — correct when the art's shape is close to the band's
    /// (a 16:9 backdrop in a 16:9 hero, a 2:3 poster in a 2:3 card).
    case fill
    /// The image is shown **whole**, over a blurred, dimmed copy of itself that fills the band.
    ///
    /// ⚠ This is the treatment for art that is the wrong SHAPE for its band — a portrait poster in a landscape
    /// band. Cropping it is what his report was about, and letterboxing it alone would leave black bars, which
    /// on a television reads as a broken image. The blurred copy is what Apple's own TV apps do in exactly this
    /// case, and it costs **no extra request**: it is the bytes already in hand, drawn twice.
    case ambient
}

enum PosterRules {

    /// ⚠ A tolerance rather than `width < height`: art that is exactly square is neither, and a 16:9 backdrop
    /// measured as 1.77 is a fill in a 16:9 band. `1 %` is the slack for a server that rounds its dimensions.
    static let squareTolerance: Double = 0.01

    /// Is this image taller than it is wide — a poster rather than a backdrop?
    static func isPortrait(width: Double, height: Double) -> Bool {
        guard width > 0, height > 0 else { return false }
        return width < height * (1 - squareTolerance)
    }

    /// Is this band wider than it is tall — a hero band, a 16:9 card, the whole page?
    static func isLandscape(width: Double, height: Double) -> Bool {
        guard width > 0, height > 0 else { return false }
        return width > height * (1 + squareTolerance)
    }

    /// ⚠⚠ **THE RULE HE FOUND: A PORTRAIT IMAGE IN A LANDSCAPE BAND IS NEVER CROPPED.**
    ///
    /// ⚠ And the converse holds, because a backdrop in a landscape band is the shape it was drawn for: it fills.
    /// ⚠ Filling is also the answer for a poster in a POSTER-shaped band (`isLandscape` false), so a 2:3 card
    /// with the same fallback still fills as it always did — the treatment is about the two shapes disagreeing,
    /// not about the route the bytes came from.
    static func treatment(imageWidth: Double, imageHeight: Double,
                          bandWidth: Double, bandHeight: Double) -> ArtworkTreatment {
        isPortrait(width: imageWidth, height: imageHeight)
            && isLandscape(width: bandWidth, height: bandHeight)
            ? .ambient
            : .fill
    }
}
