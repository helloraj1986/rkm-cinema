import SwiftUI
import Combine
import RKMServerKit

/// The on-screen log — and on tvOS it is not a convenience, it is **the only diagnostic surface there
/// is.** No Safari Web Inspector (no WebKit at all), no attached console, no easy way to get a file off a
/// TV. On iOS the best lever was `webView.isInspectable` + Safari's Develop menu; on tvOS the equivalent
/// does not exist, so every diagnosis starts here.
///
/// ⚠ **It displays `RKMLog.shared.ring` directly** rather than keeping its own list, which is what makes a
/// photograph of the screen and the file log agree — the property `apple/LOGGING.md` §9 requires, and the
/// reason the correlation id on every line is the single most valuable thing on this panel.
///
/// ⚠ **It starts OFF** (`AppLog.hudStartsVisible`), because the panel is large and sits over the middle
/// of the screen — a build that opens with it on covers whatever that screen was trying to show and reads
/// as a blank app. That lesson was paid for on iOS on 2026-09-19. Routed in by the Debug toggle on screen
/// #0, or `-RKMDebugHUD YES` for one launch.
struct DebugHUD: View {

    let session: SessionStore?
    let onHide: () -> Void

    /// ⚠ `@State` so the publisher is built ONCE. A plain `let` here is rebuilt on every body
    /// evaluation, and each rebuild makes another subscription to a one-second timer.
    @State private var ticker = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    @State private var now = Date()

    private let lineLimit = 18

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            header
            Divider()
            lines
            footer
        }
        .padding(14)
        .frame(width: 980, alignment: .leading)
        .background(Color.black.opacity(0.88), in: RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10).stroke(Color.white.opacity(0.25), lineWidth: 1)
        )
        .onReceive(ticker) { stamp in
            // ⚠ The tick is not decoration: the ring buffer is not an observable object, and a HUD that
            // redraws only when something else changes is a HUD that shows nothing exactly when the app is
            // stuck — which is when it is needed.
            now = stamp
        }
    }

    private var header: some View {
        HStack(spacing: 14) {
            Text("DEBUG")
                .font(.caption.bold())
                .foregroundStyle(.yellow)
            Text(session?.address.displayString ?? "no server")
                .font(.system(size: 13, design: .monospaced))
                .foregroundStyle(.white)
            if let profile = session?.currentProfile?.name {
                Text("as \(profile)")
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            if session?.busy == true {
                ProgressView().controlSize(.small)
            }
            Spacer(minLength: 0)
            Button("Hide", action: onHide)
                .font(.caption)
        }
        .padding(.bottom, 2)
    }

    private var lines: some View {
        VStack(alignment: .leading, spacing: 2) {
            let entries = Array(RKMLog.shared.ring.newestFirst.prefix(lineLimit))
            if entries.isEmpty {
                Text("no log lines yet")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(.secondary)
            } else {
                ForEach(entries) { entry in
                    Text(entry.hudText)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(colour(for: entry.level))
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var footer: some View {
        HStack(spacing: 12) {
            Text("\(RKMLog.shared.ring.count) line(s) held · level \(RKMLog.shared.level.name)")
            if let url = RKMLog.shared.fileURL {
                Text("· file: \(url.path)")
                    .lineLimit(1)
                    .truncationMode(.head)
            } else {
                Text("· NO FILE LOG")
                    .foregroundStyle(.orange)
            }
            Spacer(minLength: 0)
        }
        .font(.system(size: 11, design: .monospaced))
        .foregroundStyle(.secondary)
        .padding(.top, 2)
    }

    private func colour(for level: LogLevel) -> Color {
        switch level {
        case .error: return .red
        case .info: return .white
        case .verbose: return .gray
        case .off: return .gray
        }
    }
}
