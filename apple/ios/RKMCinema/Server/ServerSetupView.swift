import SwiftUI
// ⚠ UIKit as well: `Color(uiColor:)` takes a UIColor, and `.secondarySystemBackground` / `.separator`
// are UIColor class properties. SwiftUI does not re-export UIKit, so the implicit-member lookup fails
// without this import.
import UIKit
import RKMServerKit

/// Screen #0 — the server address (`docs/APPLE_CLIENTS_PLAN.md` §2, the Jellyfin/Infuse/Plex
/// model). The address is typed here and remembered, so the tailnet host is never baked into a
/// build.
struct ServerSetupView: View {

    @EnvironmentObject private var app: AppModel
    @FocusState private var addressFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                field
                preview
                connectRow
                if let error = app.setupError {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
                hints
                debugRow
            }
            .padding(24)
            .frame(maxWidth: 620, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .onAppear {
            if app.typedAddress.isEmpty { addressFocused = true }
        }
    }

    // MARK: - Pieces

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("RKMCinema").font(.largeTitle.bold())
            Text("Enter the address of your server. The app loads the cinema interface from it — sign in there with your usual household details.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var field: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Server address").font(.headline)
            TextField("192.168.1.10:8124", text: $app.typedAddress)
                .font(.body.monospaced())
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .keyboardType(.URL)
                .textContentType(.URL)
                .submitLabel(.go)
                .focused($addressFocused)
                .onSubmit { Task { await app.connect() } }
                .padding(12)
                .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10).stroke(Color(uiColor: .separator))
                )
                .disabled(app.isConnecting)
        }
    }

    /// ⚠ Live feedback, in both directions: the address it *will* use, or **why** it was refused.
    /// The plan's rule is that a rejected address must say why — "invalid address" is a dead end
    /// for the person typing.
    @ViewBuilder
    private var preview: some View {
        if let result = app.typedAddressResult {
            switch result {
            case .success(let address):
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.right")
                            .font(.caption)
                        Text(address.displayString)
                            .font(.callout.monospaced())
                    }
                    if !address.hadExplicitScheme {
                        Text("No scheme given, so the app will use \(address.scheme)://")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            case .failure(let error):
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                    Text(error.errorDescription ?? "That address is not valid.")
                        .fixedSize(horizontal: false, vertical: true)
                }
                .font(.callout)
                .foregroundStyle(.orange)
            }
        }
    }

    private var connectRow: some View {
        HStack(spacing: 12) {
            Button {
                addressFocused = false
                Task { await app.connect() }
            } label: {
                HStack(spacing: 8) {
                    if app.isConnecting {
                        ProgressView().controlSize(.small)
                    }
                    Text(app.isConnecting ? "Connecting…" : "Connect")
                        .frame(minWidth: 96)
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(app.isConnecting || app.typedAddress.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

            Text("The app checks the server answers before it switches screens — a typo is answered here, not by a blank page.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var hints: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Where to find it").font(.headline)
            Label("On your home network: the machine running the server and its port — e.g. 192.168.1.10:8124",
                  systemImage: "house")
            Label("Away from home: the Tailscale name — e.g. your-hp.tailXXXX.ts.net — with the Tailscale app running on this device",
                  systemImage: "shield.lefthalf.filled")
            Label("Plain http:// is fine on your own network: the app declares the exception iOS needs",
                  systemImage: "info.circle")
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    private var debugRow: some View {
        VStack(alignment: .leading, spacing: 4) {
            Toggle(isOn: Binding(get: { app.hudVisible }, set: { app.setHUD($0) })) {
                Text("Debug overlay").font(.footnote)
            }
            Text("Screenshots are worth far more with it on: the overlay carries the correlation id that ties a picture to the log file. In the shell, triple-tap the top-left corner to toggle it.")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
