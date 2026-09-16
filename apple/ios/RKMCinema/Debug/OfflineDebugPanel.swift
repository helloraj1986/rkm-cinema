import SwiftUI
import Combine
import RKMServerKit

/// ⚠⚠ **DEV-PHASE ONLY — and it exists because of the phase order, not for convenience.**
///
/// B2 is the downloader; the page affordances (a Download button on a detail screen, a Downloads screen)
/// are **B4**, and the loopback server that PLAYS a downloaded film is **B3**. Without something to press,
/// B2's own gate — *"downloads complete with the app backgrounded, resume after a forced failure, and
/// appear in the manifest after a relaunch"* — could not be tested on the Mac at all, and the phase would
/// hand over unverified work. This panel is that something: it starts a real download through exactly the
/// same API the page will call in B4, so what it exercises is the feature, not a mock of it.
///
/// It is compiled only into a Debug build, it carries no state of its own, and it will be deleted when B4
/// lands. ⚠ It is deliberately NOT the beginning of a native UI: the iOS app's screens are the web app's
/// (`apple/README.md`).
#if DEBUG
struct OfflineDebugPanel: View {

    @ObservedObject var offline: OfflineDownloads

    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            header

            if expanded {
                Divider().overlay(Color.white.opacity(0.25))
                if let problem = offline.storeProblem {
                    Text("⚠ \(problem)")
                } else {
                    summary
                    settings
                    rows
                    candidates
                }
            }
        }
        .font(.system(size: 10, design: .monospaced))
        .foregroundStyle(.white)
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 6) {
            Button {
                expanded.toggle()
            } label: {
                Text((expanded ? "▾ " : "▸ ") + "offline (B2)")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
            }
            .buttonStyle(.plain)
            .foregroundStyle(.white)

            if !expanded {
                Text(headline)
                    .opacity(0.7)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }
            Spacer(minLength: 0)
        }
    }

    private var headline: String {
        if let problem = offline.storeProblem { return "⚠ \(problem)" }
        if offline.rows.isEmpty { return "no downloads" }
        let downloading = offline.rows.filter { $0.state == .downloading }.count
        let ready = offline.rows.filter { $0.state == .ready }.count
        return "\(offline.rows.count) record(s) · \(downloading) downloading · \(ready) ready"
    }

    // MARK: - Summary and switches

    private var summary: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("session \(OfflineDownloads.sessionIdentifier)")
                .lineLimit(1)
                .truncationMode(.middle)
            Text("cookies \(offline.cookies.summary)")
                .lineLimit(1)
                .truncationMode(.middle)
            Text("configured \(offline.isConfigured ? "yes" : "no") · store open \(offline.store != nil)")
        }
        .opacity(0.8)
    }

    private var settings: some View {
        VStack(alignment: .leading, spacing: 2) {
            Toggle(isOn: $offline.wifiOnly) { Text("Wi-Fi only") }
                .toggleStyle(.switch)
                .font(.system(size: 10))
            Toggle(isOn: $offline.autoResume) { Text("Auto-resume interrupted") }
                .toggleStyle(.switch)
                .font(.system(size: 10))
        }
    }

    // MARK: - Rows

    @ViewBuilder
    private var rows: some View {
        if offline.rows.isEmpty {
            Text("no downloads yet").opacity(0.6)
        } else {
            ForEach(offline.rows) { row in
                VStack(alignment: .leading, spacing: 2) {
                    Text(row.title)
                        .lineLimit(1)
                        .truncationMode(.tail)
                    Text(row.progressLine)
                        .lineLimit(2)
                        .truncationMode(.tail)
                        .opacity(0.85)
                    if let fraction = row.fraction, row.state == .downloading {
                        ProgressView(value: fraction)
                            .progressViewStyle(.linear)
                            .tint(.white)
                    }
                    HStack(spacing: 6) {
                        switch row.state {
                        case .downloading:
                            button("Cancel") { offline.cancel(itemId: row.itemId) }
                        case .paused:
                            button("Resume") { offline.retry(itemId: row.itemId) }
                        case .failed:
                            button("Retry") { offline.retry(itemId: row.itemId) }
                        case .ready:
                            Text("ready").opacity(0.7)
                        }
                        button("Delete") { offline.delete(itemId: row.itemId) }
                        Spacer(minLength: 0)
                    }
                }
                .padding(.vertical, 2)
            }
        }
    }

    // MARK: - Candidates (the item ids, without typing a GUID)

    private var candidates: some View {
        VStack(alignment: .leading, spacing: 2) {
            Divider().overlay(Color.white.opacity(0.25))
            HStack(spacing: 6) {
                button(offline.isLoadingCandidates ? "loading…" : "Load titles") { offline.refreshCandidates() }
                Text("sign in inside the app first — downloads use the page's session")
                    .opacity(0.6)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }
            if let error = offline.libraryError {
                Text("⚠ \(error)").lineLimit(2).truncationMode(.tail)
            }
            ForEach(offline.candidates) { candidate in
                HStack(spacing: 6) {
                    Text(candidate.title + (candidate.year.map { " (\($0))" } ?? ""))
                        .lineLimit(1)
                        .truncationMode(.tail)
                    Spacer(minLength: 0)
                    button("Download") {
                        offline.start(itemId: candidate.itemId, title: candidate.title)
                    }
                }
            }
        }
    }

    private func button(_ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.white.opacity(0.16), in: RoundedRectangle(cornerRadius: 4))
        }
        .buttonStyle(.plain)
        .foregroundStyle(.white)
    }
}
#endif
