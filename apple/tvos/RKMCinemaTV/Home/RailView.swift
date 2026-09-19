import SwiftUI

/// One horizontally scrolling rail of posters.
///
/// ⚠⚠ **THE SCROLL IS THE PLATFORM'S, AND THAT WAS A DELIBERATE DELETION.** The Phase B plan said "the row
/// scrolls to keep the focused card visible", and the first draft of this phase wrote the arithmetic for
/// that as a pure, unit-tested file (`RailFocus`). It was removed before this landed, for two reasons:
///
///   1. **tvOS already does it.** The focus engine scrolls an ancestor `ScrollView` to reveal the newly
///      focused view — that is what makes a tvOS rail work at all. A hand-rolled `offset(x:)` would run in
///      addition to that, and two things scrolling one row is a jitter bug that looks like "the arrows are
///      broken" and diagnoses as nothing.
///   2. **Untested maths that ships is worse than no maths.** The rule I wrote could be asserted on Linux
///      and still be wrong about the platform — a green test proving only that my model of tvOS was
///      self-consistent. ⚠ This could not be settled from the sandbox (no tvOS SDK here), so the phase
///      takes the failure mode that is *visible and one line to fix* — if the round shows a focused card
///      going off the edge, the fix is to add the offset deliberately — over one that is invisible and
///      fights the system.
///
/// The 2-D grid in B3 is the different case, and the plan is right about it: column memory across rows is
/// something the platform does NOT give you for free.
struct RailView: View {

    let rail: HomeRail
    let base: URL
    let onSelect: (MediaItem) -> Void

    /// ⚠ A row with no id cannot be opened and has no poster, so it is dropped here rather than rendered as
    /// a dead card. (The web card is keyed by `item_id`, so it carries the same assumption; this makes it
    /// explicit instead of a crash on a duplicate empty id.)
    private var cards: [MediaItem] {
        rail.items.filter { !$0.itemID.isEmpty }
    }

    var body: some View {
        if cards.isEmpty {
            // A rail whose every row was unusable renders nothing — the same rule as a rail with no items,
            // because an empty heading over nothing is worse than no heading.
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 12) {
                Text(rail.title)
                    .font(.system(size: 32, weight: .semibold))
                    .padding(.horizontal, 60)

                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 28) {
                        ForEach(cards) { item in
                            PosterCard(item: item, base: base, onSelect: onSelect)
                        }
                    }
                    .padding(.horizontal, 60)
                    // ⚠ Vertical room for the focus scale. The tvOS card style grows the focused card, and
                    // a rail cropped to its resting height clips the focused edge — which reads as a
                    // rendering fault rather than a focus effect.
                    .padding(.vertical, 26)
                }
            }
        }
    }
}
