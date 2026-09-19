import SwiftUI
import RKMServerKit

/// Screen #0 — the server address (`docs/APPLE_CLIENTS_PLAN.md` §2, the Jellyfin/Infuse/Plex model). The
/// address is typed here and remembered, so the tailnet host is never baked into a build.
///
/// ⚠ **THE FIELD OPENS PRE-FILLED** (`ServerDefaults.address`). This is the tvOS-specific decision the
/// plan spends §4.2 on: a Siri Remote is a poor text input, so the common case has to be one button
/// press. The field stays fully editable, and three better inputs exist when it is not the right address —
/// the nearby iPhone/iPad keyboard (Continuity, automatic when a field is focused), a paired Bluetooth
/// keyboard, and Siri dictation.
///
/// ⚠ **The distance rule is why this screen looks nothing like its iOS twin:** no `footnote` type, no
/// 620pt column. Everything is sized to be read from three metres, and the whole content column is
/// ~1100pt on a 1920pt screen rather than a phone-width stripe.
///
/// ⚠ NO keyboard-hint modifiers (`.keyboardType`, `.textContentType`, `.submitLabel`,
/// `.textInputAutocapitalization`, `.autocorrectionDisabled`). They are all real iOS API and their tvOS
/// availability cannot be checked from this sandbox, so they are simply absent rather than a build round
/// spent finding out. Adding one back is a one-line change with a known cost.
struct ServerSetupView: View {

    @EnvironmentObject private var app: AppModel
    @FocusState private var addressFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                header
                field
                preview
                connectRow
                if let error = app.setupError {
                    Text(error)
                        .font(.callout)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
                hints
                debugRow
            }
            .padding(60)
            .frame(maxWidth: 1100, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .onAppear {
            // Focus the field so the remote starts where the typing is — the opposite of the iOS app,
            // which had a keyboard competing for the screen.
            addressFocused = true
        }
    }

    // MARK: - Pieces

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("RKMCinemaTV").font(.system(size: 54, weight: .bold))
            Text("Enter the address of your server, then press Connect.")
                .font(.title3)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var field: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Server address").font(.headline)
            TextField("192.168.1.10:8124", text: $app.typedAddress)
                .font(.system(size: 28, design: .monospaced))
                .focused($addressFocused)
                .padding(16)
                .background(Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                .overlay(
                    RoundedRectangle(cornerRadius: 12).stroke(Color.white.opacity(0.28), lineWidth: 1)
                )
                .disabled(app.isConnecting)
        }
    }

    /// ⚠ Live feedback, in both directions: the address it *will* use, or **why** it was refused. The
    /// plan's rule is that a rejected address must say why — "invalid address" is a dead end for the
    /// person typing, and on a TV it is a dead end they cannot fix with a keyboard app.
    @ViewBuilder
    private var preview: some View {
        if let result = app.typedAddressResult {
            switch result {
            case .success(let address):
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 10) {
                        Image(systemName: "arrow.right")
                            .font(.caption)
                        Text(address.displayString)
                            .font(.system(size: 22, design: .monospaced))
                    }
                    if !address.hadExplicitScheme {
                        Text("No scheme given, so the app will use \(address.scheme)://")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                }
            case .failure(let error):
                HStack(alignment: .firstTextBaseline, spacing: 10) {
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
        HStack(spacing: 20) {
            Button {
                addressFocused = false
                Task { await app.connect() }
            } label: {
                HStack(spacing: 10) {
                    if app.isConnecting {
                        ProgressView()
                    }
                    Text(app.isConnecting ? "Connecting…" : "Connect")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(app.isConnecting
                        || app.typedAddress.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

            Text("The app checks the server answers before it moves on — a typo is answered here.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var hints: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Where to find it").font(.headline)
            Label("On your home network: the machine running the server and its port — e.g. 192.168.1.10:8124",
                  systemImage: "house")
            Label("Away from home: the Tailscale name — e.g. your-hp.tailXXXX.ts.net — with the Tailscale app running on this Apple TV",
                  systemImage: "shield.lefthalf.filled")
            Label("Typing is easier from your iPhone: when this field is selected, your phone offers its keyboard.",
                  systemImage: "iphone")
        }
        .font(.callout)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    /// ⚠ The tvOS route into the debug overlay, and it is a **visible control** on purpose. On iOS the
    /// toggle was a corner gesture that had never once fired, and both fixes were found from a
    /// screenshot — the lesson being that *a control nobody can see is unfalsifiable*. There is no shake
    /// and no triple-tap on a TV, so this is what the overlay has instead (plus `-RKMDebugHUD YES`).
    private var debugRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            Toggle(isOn: Binding(get: { app.hudVisible }, set: { app.setHUD($0) })) {
                Text("Debug overlay").font(.callout)
            }
            Text("It carries the correlation id that ties a photograph of the screen to the log file. It starts OFF; "
                    + "`-RKMDebugHUD YES` turns it on for one launch without a rebuild.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
