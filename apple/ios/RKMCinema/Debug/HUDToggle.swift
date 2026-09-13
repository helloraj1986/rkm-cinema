import SwiftUI
import UIKit

/// ⚠ **An iPad has no shake gesture.** `LOGGING.md` §4 says the overlay is turned on by
/// "a build flag / triple-tap", and this is why that is not merely a preference: a shake-only
/// toggle would be unreachable on the very device this app exists for. So the primary toggle is a
/// 52pt square in the top-left corner — the smallest thing that reliably catches three taps, and
/// the only part of the screen the shell takes away from the page.
struct HUDToggleHotspot: View {

    let onToggle: () -> Void

    var body: some View {
        Color.clear
            .frame(width: 52, height: 52)
            .contentShape(Rectangle())
            .onTapGesture(count: 3, perform: onToggle)
    }
}

/// Shake as a secondary toggle. It costs no screen area at all and is the natural gesture on an
/// iPhone; on an iPad it simply never fires.
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
