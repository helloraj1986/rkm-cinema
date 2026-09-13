import SwiftUI
import UIKit
import RKMServerKit

/// The debug overlay's toggle.
///
/// ⚠⚠ **The 52pt triple-tap square is gone, and the reason is measured, not guessed** (first real
/// run, 2026-09-14: *"i am clicking the top left corner for the overlay nothing comes up"*). That
/// square never fired once, and the cause was **geometry, not the gesture**.
/// `.overlay(alignment: .topLeading)` aligns to the **modified view's** bounds, and the root view
/// here is inset by the safe area — so on an iPhone the square sat at **y ≈ 59pt**: *below* the
/// status bar, inside the page's own header strip. He was tapping the corner of the display, which
/// is **above** it.
///
/// His screenshot is the proof: the page's title and back chevron begin at the same height as the
/// overlay's first line, and above both is an empty **white** strip.
/// ⚠ That strip is the *window* background, not page content — the cinema UI is dark at that point
/// in the film — which is only possible if the web view is inset to the safe area. Same conclusion,
/// measured twice.
///
/// So the hit area **reaches above the corner it is laid out at**, by construction:
///
/// ```text
///   ┌────────────────────────┐ ← top of the display
///   │  ▣   (status-bar strip)│   the strip a thumb actually aims at — no page content here
///   ├────────────────────────┤ ← safe-area top: where `.topLeading` lays the frame out (y ≈ 59pt)
///   │                        │   +34pt into the page's header. Still less than the 52pt square
///   └────────────────────────┘   this replaces, so the page loses *less* of its own top-left.
/// ```
///
/// Three further changes, each answering a different way the old one failed:
/// 1. **It is drawn.** An invisible control cannot be debugged by looking at the screen: "nothing
///    happens" was indistinguishable from "you are tapping 59pt too high" for a whole round trip.
/// 2. **One tap, not three.** A single `UITapGestureRecognizer` has no timing window to miss.
///    `apple/LOGGING.md` §4 asked for a "build flag / triple-tap" — the build flag is now the
///    **primary** route (`AppLog.hudStartsVisible`: a Debug build opens with the overlay already
///    on), and this chip is the way back if it has been hidden.
/// 3. ⚠ **A real `UIView`, not SwiftUI-drawn content.** A UIKit view is added as a subview *above*
///    the `WKWebView`, so its hit-testing does not depend on how SwiftUI composites drawing over a
///    representable; and in UIKit a clear background is irrelevant to hit-testing, so the SwiftUI
///    question "is `Color.clear` tappable?" never arises.
struct HUDToggleChip: UIViewRepresentable {

    let onToggle: () -> Void

    /// The frame SwiftUI gives the chip: laid out at the overlay's top-leading corner, then shifted
    /// up by `upwardShift` so the target begins at the **top of the display** whatever the device's
    /// safe-area inset happens to be (44pt–62pt across current iPhones).
    static let size = CGSize(width: 68, height: 134)

    /// ⚠ The shift must be ≥ the largest safe-area top inset we expect, and the frame's height must
    /// exceed the shift, or the region would start below the display's corner and this bug would
    /// simply move. 100 ≥ 62 ✓, 134 > 100 ✓ — and the visible mark is positioned against the
    /// *window*, not against this shifted frame (see `layoutSubviews`), so it cannot be drawn off
    /// the top of the screen either.
    static let upwardShift: CGFloat = -100

    func makeUIView(context: Context) -> ToggleChipView {
        let view = ToggleChipView()
        view.onToggle = onToggle
        return view
    }

    func updateUIView(_ uiView: ToggleChipView, context: Context) {
        uiView.onToggle = onToggle
    }
}

/// The hit area, plus the small mark that says where the hit area is.
final class ToggleChipView: UIView {

    var onToggle: (() -> Void)?

    /// ⚠ The mark lives *inside* the toggle rather than in a SwiftUI sibling on purpose: it must be
    /// drawn relative to the top of the **window** (the frame is shifted above the display's
    /// corner), and keeping it as a subview means `allowsHitTesting` never has to be reasoned about.
    private let marker = UIImageView()

    init() {
        super.init(frame: .zero)
        // ⚠ Clear is fine *and* fully tappable: `UIView.hitTest` is decided by `point(inside:)` and
        // `isUserInteractionEnabled`, never by alpha. The page shows through; only the touches are
        // taken, and only in this rectangle.
        backgroundColor = .clear
        isOpaque = false

        buildMarker()
        installGestures()
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used — the chip is code-built") }

    // MARK: - The mark

    private func buildMarker() {
        let configuration = UIImage.SymbolConfiguration(pointSize: 12, weight: .semibold)
        marker.image = UIImage(systemName: "ladybug.fill", withConfiguration: configuration)
        marker.tintColor = UIColor.white.withAlphaComponent(0.9)
        marker.contentMode = .center
        // A translucent disc, so the glyph stays legible over a light *or* dark page.
        marker.backgroundColor = UIColor.black.withAlphaComponent(0.32)
        marker.layer.cornerRadius = Self.markerSize / 2
        marker.isUserInteractionEnabled = false
        addSubview(marker)
    }

    private static let markerSize: CGFloat = 26

    override func layoutSubviews() {
        super.layoutSubviews()
        guard let window else { return }
        // ⚠ Positioned against the top-left of the **display**, not of this view. The frame is
        // deliberately shifted above the display's corner (`HUDToggleChip.upwardShift`), so a fixed
        // offset within the frame would draw the mark off the top of the screen. `max(6, …)` is the
        // other case: if the frame was laid out *below* the window's top after all — i.e. the
        // assumption this fix is built on stops holding — the mark still lands somewhere visible
        // instead of disappearing, which is how you tell the two apart.
        let origin = convert(.zero, to: window)
        let top = max(6, 6 - origin.y)
        marker.frame = CGRect(x: 8, y: top, width: Self.markerSize, height: Self.markerSize)
    }

    // MARK: - Gestures

    private func installGestures() {
        // ⚠ Two gestures, one job. This chip is the app's only guaranteed route back to its own
        // diagnostics (`apple/ios/README.md` calls always-reachable *Change server* a
        // non-negotiable, and the overlay is where that lives), so a press-and-hold is offered
        // beside the tap in case a single tap is ever swallowed by the page below.
        let tap = UITapGestureRecognizer(target: self, action: #selector(handleTap))
        addGestureRecognizer(tap)

        let hold = UILongPressGestureRecognizer(target: self, action: #selector(handleHold))
        hold.minimumPressDuration = 0.5
        addGestureRecognizer(hold)
    }

    /// ⚠ Logged **before** the toggle, at verbose level. "The overlay did not appear" and "the touch
    /// never arrived" look identical on the screen and are opposite problems; this line is what
    /// separates them from the file log instead of from another screenshot.
    @objc private func handleTap() {
        RKMLog.verbose("toggle chip: tap", category: .app)
        onToggle?()
    }

    @objc private func handleHold(_ gesture: UILongPressGestureRecognizer) {
        guard gesture.state == .began else { return }
        RKMLog.verbose("toggle chip: press-and-hold", category: .app)
        onToggle?()
    }
}

/// Shake as a secondary toggle. It costs no screen area at all and is the natural gesture on an
/// iPhone, and on the **simulator** it is reachable from the menu — `Device ▸ Shake` (⌃⌘Z) — which
/// makes it the one toggle that can be exercised without touching the screen at all.
/// ⚠ An iPad has no shake gesture, so this can never be the only route.
struct ShakeToToggle: UIViewRepresentable {

    let onShake: () -> Void

    func makeUIView(context: Context) -> ShakeReportingView {
        let view = ShakeReportingView()
        view.onShake = onShake
        // Motion events are delivered through the responder chain, not through hit testing, so the
        // view does not have to intercept touches — and must not.
        view.isUserInteractionEnabled = false
        return view
    }

    func updateUIView(_ uiView: ShakeReportingView, context: Context) {
        uiView.onShake = onShake
    }
}

final class ShakeReportingView: UIView {

    var onShake: (() -> Void)?

    override var canBecomeFirstResponder: Bool { true }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard window != nil else { return }
        becomeFirstResponder()
    }

    override func motionEnded(_ motion: UIEvent.EventSubtype, with event: UIEvent?) {
        guard motion == .motionShake else { return }
        // Ask for it back: something else (the address field's keyboard) may hold it by now.
        becomeFirstResponder()
        onShake?()
    }
}
