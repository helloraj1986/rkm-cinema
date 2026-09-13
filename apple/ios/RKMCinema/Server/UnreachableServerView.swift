import SwiftUI
// ⚠ UIKit for `Color(uiColor: .systemBackground)` — see the note in ServerSetupView.swift.
import UIKit
import RKMServerKit

/// The state that stops a wrong address bricking the app (plan §3.2, `apple/ios/README.md`).
///
/// Reached two ways, and both matter: a failed reachability check on screen #0, and a **web-view
/// navigation failure** once the shell is up. The second is the one that would otherwise be a
/// white screen with no way out.
struct UnreachableServerView: View {

    @EnvironmentObject private var app: AppModel
    let info: UnreachableInfo

    @State private var confirmClearWebsiteData = false
    @State private var confirmForget = false

    var body: some View {
        ZStack {
            Color(uiColor: .systemBackground).ignoresSafeArea()

            VStack(spacing: 14) {
                Image(systemName: "wifi.exclamationmark")
                    .font(.system(size: 44))
                    .foregroundStyle(.orange)

                Text("Can’t reach this server")
                    .font(.title2.bold())

                Text(info.address.displayString)
                    .font(.callout.monospaced())
                    .textSelection(.enabled)

                Text(info.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: 520)

                hints

                actions

                secondary

                if let summary = app.websiteDataSummary {
                    Text(summary)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(24)
        }
    }

    // MARK: - Pieces

    /// ⚠ The hints name the two things the app genuinely cannot fix for itself: the network is
    /// the client's problem (plan §2.3), and a raw tailnet or LAN address only works when the
    /// device is actually on it.
    @ViewBuilder
    private var hints: some View {
        VStack(alignment: .leading, spacing: 6) {
            if info.address.isLikelyTailscale {
                Label("This is a Tailscale address — check the Tailscale app is running on this device.", systemImage: "shield.lefthalf.filled")
            }
            if info.address.isLikelyOnLocalNetwork {
                Label("This is a local address — check this device is on the same network as the server.", systemImage: "wifi")
            }
            Label("Check the server itself is running (the containers on the host).", systemImage: "server.rack")
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: 520, alignment: .leading)
    }

    private var actions: some View {
        HStack(spacing: 12) {
            Button {
                Task { await app.retry() }
            } label: {
                HStack(spacing: 8) {
                    if app.isConnecting {
                        ProgressView().controlSize(.small)
                    }
                    Text(app.isConnecting ? "Trying…" : "Try again")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(app.isConnecting)

            // Always available — this button is the requirement.
            Button("Change server") {
                app.changeServer()
            }
            .buttonStyle(.bordered)
        }
    }

    private var secondary: some View {
        VStack(spacing: 8) {
            Button("Forget this address") { confirmForget = true }
                .font(.footnote)

            Button("Clear website data") { confirmClearWebsiteData = true }
                .font(.footnote)

            Text("Clearing website data signs you out and removes anything the page cached. Worth trying when the server is reachable but the app still will not load.")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)
        }
        .padding(.top, 4)
        .confirmationDialog("Forget the saved address?",
                            isPresented: $confirmForget,
                            titleVisibility: .visible) {
            Button("Forget", role: .destructive) {
                app.forgetSavedAddress()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("The app will open on this screen next time instead of the shell.")
        }
        .confirmationDialog("Clear website data?",
                            isPresented: $confirmClearWebsiteData,
                            titleVisibility: .visible) {
            Button("Clear", role: .destructive) {
                app.clearWebsiteData()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("You will need to sign in again.")
        }
    }
}
