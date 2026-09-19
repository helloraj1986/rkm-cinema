import SwiftUI
import RKMServerKit

/// Screen #1 — sign in (`POST /api/auth/login`).
///
/// ⚠ **The credentials go to the server once and are never stored.** Identity is delegated to Jellyfin
/// (`AUTH_MULTIUSER_PLAN.md` §3.7); what this app keeps is a session cookie it does not interpret. Nothing
/// in this file logs a password, and `LogRedactor` is the gate that proves it — `apple/LOGGING.md` §6
/// makes a grep for `password|token|api_key|rkm_session` over a real run an acceptance item.
///
/// ⚠ The screen is reachable in exactly two states, and the second is the one that matters: nobody is
/// signed in (401 from `/api/auth/me`), or the session was refused. Both need the same door.
struct LoginView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var session: SessionStore

    @State private var username = ""
    @State private var password = ""
    @FocusState private var focused: Field?

    private enum Field: Hashable {
        case username
        case password
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header
                fields
                if let error = session.error {
                    Text(error)
                        .font(.callout)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: 900, alignment: .leading)
                }
                actions
                note
            }
            .padding(60)
            .frame(maxWidth: 1100, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .onAppear { focused = .username }
    }

    // MARK: - Pieces

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Sign in").font(.system(size: 54, weight: .bold))
            Text("Use your household details, the same ones you use in the web app.")
                .font(.title3)
                .foregroundStyle(.secondary)
            Text(session.address.displayString)
                .font(.system(size: 22, design: .monospaced))
                .foregroundStyle(.secondary)
        }
    }

    private var fields: some View {
        VStack(alignment: .leading, spacing: 18) {
            labelled("Username") {
                TextField("username", text: $username)
                    .focused($focused, equals: .username)
            }
            labelled("Password") {
                SecureField("password", text: $password)
                    .focused($focused, equals: .password)
            }
        }
    }

    private func labelled<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            content()
                .font(.system(size: 28))
                .padding(16)
                .frame(maxWidth: 760, alignment: .leading)
                .background(Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                .overlay(
                    RoundedRectangle(cornerRadius: 12).stroke(Color.white.opacity(0.28), lineWidth: 1)
                )
                .disabled(session.busy)
        }
    }

    private var actions: some View {
        HStack(spacing: 20) {
            Button {
                focused = nil
                Task {
                    if await session.signIn(username: username, password: password) {
                        password = ""
                        await app.didSignIn()
                    }
                }
            } label: {
                HStack(spacing: 10) {
                    if session.busy { ProgressView() }
                    Text(session.busy ? "Signing in…" : "Sign in")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(session.busy || username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

            Button("Change server") { app.changeServer() }
                .buttonStyle(.bordered)
        }
    }

    /// ⚠ Names the thing this app cannot do for itself — and it is the same sentence the iOS app needed,
    /// because a TV is an even worse place to discover it.
    private var note: some View {
        Text("The Apple TV must be able to reach the server: on the home network, or on the tailnet with "
                + "Tailscale running on the TV itself.")
            .font(.footnote)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: 900, alignment: .leading)
    }
}
