import SwiftUI
import UIKit
import RKMServerKit

/// The debug overlay's toggle — **three taps (or one press-and-hold) in the top-left corner.**
///
/// ⚠⚠ **Why this is not a tappable view any more — two failures, both measured** (2026-09-14).
///
/// **Failure 1: the target was 59pt below the corner he taps.** The original was a 52pt
/// `Color.clear` square placed with `.overlay(alignment: .topLeading)`, which aligns to the
/// **modified view's** bounds. The root view here is inset by the safe area, so the square sat at
/// **y ≈ 59pt — *below* the status bar, inside the page's own header** — while every tap aimed at
/// the top of the *display*. His screenshot is the proof: the page's title and back chevron begin at
/// the same height as the overlay's first line, and above both is an empty strip.
///
/// **Failure 2 (the fix for #1 that did not work): `.offset` moved the *mark*, not the *hit area*.**
/// The second version drew its bug glyph correctly in the corner — and still did not respond, to a
/// click on the glyph itself. The mark is positioned against the **window** (`positionMarker`), so
/// the drawing moved; the touch target evidently did not follow it, because SwiftUI's hit-testing for
/// a hosted `UIView` does not have to agree with a render-time offset. **The lesson is the point: a
/// control whose hit area depends on SwiftUI's layout of an overlay over a `WKWebView` is a control
/// with two unknowns multiplying.** So this version removes both unknowns:
///
/// 1. **The gesture recognisers are installed on the `UIWindow`**, in `didMoveToWindow`. Every touch
///    in the app passes through the window, whatever is on top of it, whatever the safe area is, and
///    whatever SwiftUI does with an overlay — there is nothing left to be wrong.
/// 2. **They only accept a touch inside a 110×110pt corner**, checked in `shouldReceive`. So the
///    page keeps every touch outside that square, and `cancelsTouchesInView = false` plus
///    simultaneous recognition means it keeps the touches *inside* it too — a three-tap in the
///    corner does not steal a page interaction, it just also toggles the overlay.
///
/// ⚠ The visible mark remains, because an invisible control cannot be debugged by looking at the
/// screen — that is the failure that cost the first round trip.
///
/// ⚠ `LOGGING.md` §4's "build flag / triple-tap" is still honoured, in reverse order of importance:
/// the **build flag** is the primary route (a Debug build opens with the overlay already on, see
/// `AppLog.hudStartsVisible`), and this gesture is the way back if it has been hidden.
struct HUDCornerToggle: UIViewRepresentable {

    let onToggle: () -> Void

    /// ⚠ Only positions the visible **mark** now — see `positionMarker`. The touch target is the
    /// `corner` square below, in window coordinates, and does not depend on this frame at all.
    static let size = CGSize(width: 68, height: 134)
    static let upwardShift: CGFloat = -100

    func makeUIView(context: Context) -> HUDCornerToggleView {
        let view = HUDCornerToggleView(frame: .zero)
        view.onToggle = onToggle
        return view
    }

    func updateUIView(_ uiView: HUDCornerToggleView, context: Context) {
        uiView.onToggle = onToggle
    }
}

/// Draws the mark, and owns the window-level gestures that toggle the overlay.
final class HUDCornerToggleView: UIView, UIGestureRecognizerDelegate {

    var onToggle: (() -> Void)?

    /// ⚠ The tappable corner, in **window** points. Generous on purpose: the status-bar strip is
    /// ~44–62pt tall, and a thumb goes for the corner of the display, not for a 26pt dot.
    static let corner = CGSize(width: 110, height: 110)

    private static let markerSize: CGFloat = 26

    private let marker = UIImageView()
    /// ⚠ Weak: the window owns the hierarchy, not the other way round. Holding it strongly would make
    /// a cycle out of `window → recogniser → this view`, and a view that outlives its own removal is
    /// exactly how a stale toggle keeps firing.
    private weak var installedWindow: UIWindow?
    private var gestures: [UIGestureRecognizer] = []

    /// ⚠ One live instance at a time. If SwiftUI ever rebuilds this view, the previous instance must
    /// take its recognisers off the window **first**: two sets would each toggle once per triple-tap,
    /// i.e. on and straight back off, and the overlay would look broken while being perfectly
    /// correct. That is a failure mode worth a static for.
    private static weak var current: HUDCornerToggleView?

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = UIColor.clear
        isOpaque = false
        buildMarker()
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used — the toggle is code-built") }

    deinit {
        detachGestures()
    }

    // MARK: - Window lifecycle

    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard let hostWindow = window else {
            // Off the hierarchy: leave nothing behind on the window.
            detachGestures()
            return
        }
        attachGestures(to: hostWindow)
        setNeedsLayout()
    }

    // MARK: - The mark

    private func buildMarker() {
        let configuration = UIImage.SymbolConfiguration(pointSize: 12, weight: .semibold)
        marker.image = UIImage(systemName: "ladybug.fill", withConfiguration: configuration)
        marker.tintColor = UIColor.white.withAlphaComponent(0.9)
        marker.contentMode = .center
        // A translucent disc, so the glyph stays legible over a light *or* dark page.
        marker.backgroundColor = UIColor.black.withAlphaComponent(0.32)
        marker.layer.cornerRadius = HUDCornerToggleView.markerSize / 2
        marker.isUserInteractionEnabled = false
        addSubview(marker)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        positionMarker()
    }

    /// ⚠ Positioned against the top-left of the **window**, not of this view. This view is a
    /// zero-size host that SwiftUI places somewhere inside the safe area; the mark belongs at the
    /// corner of the *display*, so the arithmetic is done in window coordinates and needs no
    /// assumption about the device's insets. (`clipsToBounds` is false by default, so a subview
    /// outside the bounds still draws — which is exactly what makes this work.)
    private func positionMarker() {
        guard let hostWindow = window else { return }
        // ⚠ `CGPoint.zero`, spelled out: `convert` is overloaded for `CGPoint` and `CGRect`, and a
        // bare `.zero` leaves the compiler with two equally good candidates — that failed a build.
        let origin = convert(CGPoint.zero, to: hostWindow)
        marker.frame = CGRect(
            x: 8 - origin.x,
            y: 6 - origin.y,
            width: HUDCornerToggleView.markerSize,
            height: HUDCornerToggleView.markerSize
        )
    }

    // MARK: - Gestures, on the window

    private func attachGestures(to hostWindow: UIWindow) {
        if let previous = HUDCornerToggleView.current, previous !== self {
            previous.detachGestures()
        }
        HUDCornerToggleView.current = self

        guard installedWindow !== hostWindow else { return }
        detachGestures()

        let tap = UITapGestureRecognizer(target: self, action: #selector(handleTap))
        tap.numberOfTapsRequired = 3
        // ⚠ Never cancel: the page keeps its own taps, including the taps that make up our gesture.
        tap.cancelsTouchesInView = false
        tap.delegate = self

        let hold = UILongPressGestureRecognizer(target: self, action: #selector(handleHold(_:)))
        hold.minimumPressDuration = 1.0
        hold.cancelsTouchesInView = false
        hold.delegate = self

        hostWindow.addGestureRecognizer(tap)
        hostWindow.addGestureRecognizer(hold)
        gestures = [tap, hold]
        installedWindow = hostWindow

        RKMLog.verbose(
            "toggle: listening — 3 taps or a 1s press within \(Int(HUDCornerToggleView.corner.width))pt of the top-left corner",
            category: .app
        )
    }

    private func detachGestures() {
        for gesture in gestures {
            installedWindow?.removeGestureRecognizer(gesture)
        }
        gestures = []
        installedWindow = nil
    }

    // MARK: - UIGestureRecognizerDelegate

    /// ⚠ The whole safety story: a touch only counts if it landed in the corner. Everything else in
    /// the app is untouched by these recognisers, so the page cannot lose an interaction to them.
    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool {
        guard let hostWindow = installedWindow else { return false }
        let point = touch.location(in: hostWindow)
        return point.x >= 0
            && point.x <= HUDCornerToggleView.corner.width
            && point.y >= 0
            && point.y <= HUDCornerToggleView.corner.height
    }

    /// ⚠ And the other half: the page's own recognisers always win alongside ours, so nothing the
    /// web UI does is delayed or suppressed by the overlay's toggle.
    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,
                           shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool {
        true
    }

    /// ⚠ Logged **before** the toggle, at verbose level. "The overlay did not appear" and "the touch
    /// never arrived" look identical on the screen and are opposite problems; these lines are what
    /// separates them from the file log instead of from another screenshot.
    @objc private func handleTap() {
        RKMLog.verbose("toggle: 3-tap in the corner", category: .app)
        onToggle?()
    }

    @objc private func handleHold(_ gesture: UILongPressGestureRecognizer) {
        guard gesture.state == .began else { return }
        RKMLog.verbose("toggle: press-and-hold in the corner", category: .app)
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
