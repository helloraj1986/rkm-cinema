import SwiftUI

/// One horizontally scrolling shelf of cards — the prototype's `.shelf` + `.shelf-track`.
///
/// ⚠⚠ **THE SCROLL IS THE PLATFORM'S, AND THAT WAS A DELIBERATE DELETION.** The Phase B plan said "the row
/// scrolls to keep the focused card visible", and the first draft of that phase wrote the arithmetic for
/// it as a pure, unit-tested file (`RailFocus`). It was removed before that phase landed, for two reasons:
///
///   1. **tvOS already does it.** The focus engine scrolls an ancestor `ScrollView` to reveal the newly
///      focused view — that is what makes a tvOS rail work at all. A hand-rolled `offset(x:)` would run in
///      addition to that, and two things scrolling one row is a jitter bug that looks like "the arrows are
///      broken" and diagnoses as nothing.
///   2. **Untested maths that ships is worse than no maths.** The rule I wrote could be asserted on Linux
///      and still be wrong about the platform — a green test proving only that my model of tvOS was
///      self-consistent.
///
/// ⚠⚠ **AND HIS U6 PROTOTYPE ASKS FOR BOTH OF THOSE THINGS — `scrollIntoView` on every focus move (line 518)
/// and nearest-neighbour maths for up/down (lines 546-561). Neither is ported, and the reason is the two
/// findings above plus B3's 2-D grid.** A browser needs them because it has no focus engine; tvOS is the
/// focus engine. ⚠ It is the one part of that file that is a spec for LAYOUT, STATES and MOTION only — see
/// `docs/TVOS_UX_PLAN.md` §3. The falsifier that keeps us honest is **F4** (move down a shelf and back; the
/// card's column must be kept): if the platform does NOT do it, that is a real defect and the fix goes in the
/// view — deliberately, one round later, rather than pre-emptively.
///
/// ⚠ Geometry is the prototype's (`TVTokens.Shelf`): a `1.5u` bold heading inset by the screen margin, a
/// `1.3u` gap between `19u` cards, and `0.6u` of vertical breathing room plus the platform's focus lift.
struct RailView: View {

    let rail: HomeRail
    let base: URL
    /// ⚠⚠ **THE SCREEN'S CARD FOCUS, PASSED IN RATHER THAN DECLARED HERE** — `.focused` has to be attached to
    /// the focusable view itself, so the binding belongs to the screen that claims a default
    /// (`HomeView.defaultFocusCardID`). ⚠⚠ **It is a PASSED `FocusState` BINDING: use it as `focus`, never as
    /// `$focus`.** There is no wrapper to project through — a binding is a `let`, and `$focus` on one does not
    /// compile. That is the members gate's rule 6, bought by a Mac round.
    let focus: FocusState<String?>.Binding
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
            VStack(alignment: .leading, spacing: TVTokens.Shelf.titleGap) {
                Text(rail.title)
                    .font(.system(size: TVTokens.Shelf.titleSize, weight: .bold))
                    .foregroundStyle(RKMColour.primary)
                    .padding(.horizontal, TVTokens.Metric.safeMargin)

                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: TVTokens.Shelf.gap) {
                        ForEach(cards) { item in
                            PosterCard(item: item, base: base, onSelect: onSelect)
                                // ⚠⚠ The binding is attached to the FOCUSABLE view, which is why it is passed
                                // in: the screen that claims a default focus cannot do it from a distance.
                                .focused(focus, equals: item.itemID)
                        }
                    }
                    .padding(.horizontal, TVTokens.Metric.safeMargin)
                    // ⚠ Vertical room for the focus lift. The tvOS card style grows the focused card, and a
                    // shelf cropped to its resting height clips the focused edge — which reads as a rendering
                    // fault rather than a focus effect. The prototype's own `0.6u` plus that lift.
                    .padding(.vertical, TVTokens.Shelf.trackPaddingV + TVTokens.Shelf.titleGap)
                }
            }
        }
    }
}
