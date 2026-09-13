import SwiftUI
// ⚠ WebKit for `shell.webView?.isInspectable` — a **member reached through an instance**, so this file
// contains no `WK`-prefixed name at all. That is why the name-based sweep of the imports missed it and
// cost a third build round; `apple/scripts/check-imports.py` exists to catch exactly this, and did.
import WebKit
import RKMServerKit

/// The on-screen overlay — `apple/LOGGING.md` §4, layer 3.
///
/// ⚠ It exists for **screenshots**. He photographs the iPad; the correlation id rides in the
/// picture; the matching lines are then a `grep` away in the file. Without the id a screenshot and
/// a 5000-line log cannot be joined up, which is why this is Phase 0 work and not polish.
///
/// ⚠ It reads `RKMLog.shared.ring` — **the same entries the file got** — rather than keeping its
/// own list. That is what makes the two agree, and `LOGGING.md` §9's second acceptance item
/// ("given only a HUD correlation id from a screenshot, the matching log lines can be found")
/// depends on it.
struct DebugHUD: View {

    @EnvironmentObject private var app: AppModel
    let shell: WebShellModel?

    @State private var showingActions = false

    var body: some View {
        TimelineView(.periodic(from: Date(), by: 0.5)) { _ in
            panel(entries: RKMLog.shared.ring.newestFirst)
        }
        .font(.system(size: 10, design: .monospaced))
        .foregroundStyle(.white)
        .padding(10)
        .frame(maxWidth: 380, alignment: .leading)
        .background(Color.black.opacity(0.78), in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8).stroke(Color.white.opacity(0.18), lineWidth: 1)
        )
        .confirmationDialog("Debug overlay", isPresented: $showingActions, titleVisibility: .visible) {
            // ⚠ The always-reachable way back out. If the shell loads but is unusable, this corner is
            // the only route to the setup screen that does not need a reinstall.
            Button("Change server") { app.changeServer() }
            Button("Clear website data") { app.clearWebsiteData() }
            Button("Hide overlay") { app.setHUD(false) }
            Button("Cancel", role: .cancel) {}
        }
    }

    // MARK: - Pieces

    private func panel(entries: [LogEntry]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            header
            lines(entries: entries)
        }
    }

    /// The only interactive strip in the overlay. It sits top-right of the panel, clear of the
    /// corner hotspot that toggles the overlay on and off.
    private var header: some View {
        HStack(spacing: 8) {
            Text("── RKMCinema debug ──────")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
            Spacer(minLength: 4)
            Button {
                showingActions = true
            } label: {
                Image(systemName: "gearshape.fill").font(.system(size: 11))
            }
            .buttonStyle(.plain)
            .foregroundStyle(.white)
        }
    }

    /// ⚠ Pass-through: every tap belongs to the page underneath. The overlay is for reading (and
    /// photographing), and stealing touches from a live web UI would make it unusable with the
    /// overlay on — which is exactly when he needs to use it.
    private func lines(entries: [LogEntry]) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            field("base", addressLine)
            field("web", webLine)
            field("auth", "cookies \(shell?.cookieSummary ?? "—")")
            // ⚠ A *request* line, not merely the newest `.net` line. The page loads its artwork
            // straight from the TMDB CDN, so its server-trust challenges are also `net` — and they
            // carry no correlation id, so the field read as `[-------] net auth challenge: …` on a
            // screen where six real requests sat right below it. §4 defines this field as the last
            // request; a line with no id is not one.
            field("net", entries.first { $0.category == .net && $0.correlationID != nil }?.hudText ?? "—")
            if let lastError = entries.first(where: { $0.level == .error }) {
                field("last", "⚠ \(lastError.message)")
            }

            Divider().overlay(Color.white.opacity(0.25))

            if entries.isEmpty {
                Text("no lines yet").opacity(0.6)
            } else {
                ForEach(Array(entries.prefix(8))) { entry in
                    Text(entry.hudText)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
            }
        }
        .allowsHitTesting(false)
    }

    private func field(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text(label)
                .frame(width: 34, alignment: .leading)
                .opacity(0.65)
            Text(value)
                .lineLimit(2)
                .truncationMode(.middle)
            Spacer(minLength: 0)
        }
    }

    private var addressLine: String {
        if let address = app.shell?.address { return address.displayString }
        return app.typedAddress.isEmpty ? "—" : app.typedAddress
    }

    private var webLine: String {
        guard let shell else { return "not in the shell" }
        let path = shell.pagePath.isEmpty ? "/" : shell.pagePath
        var line = "\(path) · \(shell.state.label)"
        if #available(iOS 16.4, *) {
            line += (shell.webView?.isInspectable ?? false) ? " · inspectable ✓" : " · inspectable ✗"
        }
        return line
    }
}
