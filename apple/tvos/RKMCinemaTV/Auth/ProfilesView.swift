import SwiftUI
import RKMServerKit

/// Screen #2 — "Who's watching?" (`GET /api/auth/profiles`, `POST /api/auth/profile`).
///
/// ⚠ **The lock is shown BEFORE anyone tries a profile**, which is the whole reason the server reports
/// `has_password` and `disabled` per profile: greying out a disabled profile and marking a protected one
/// is the difference between a picker and a guessing game. On a TV, a wrong guess costs a login screen
/// typed with a remote.
///
/// ⚠ **Selecting the administrator's own profile needs the administrator's password** (decision 3,
/// 2026-09-12) — the device holds their session, so this is what stops a guest walking into it. The rule
/// is enforced SERVER-side in `api/session.py::session_context_from_request`; the client only decides
/// *when to ask*, and asking when the server would refuse is the difference between a form and an error.
///
/// ⚠ **The grid is a focus grid, and the profile tiles are `Button`s** — the only thing on screen, so a
/// d-pad reaches every one of them with no dead tiles to pass through.
struct ProfilesView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var session: SessionStore

    /// The profile whose password is being asked for, if any.
    @State private var asking: ProfileUser?
    @State private var password = ""
    @FocusState private var passwordFocused: Bool

    private let columns = [GridItem(.adaptive(minimum: 320, maximum: 420), spacing: 32)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                header

                if let warning = session.warning, !warning.isEmpty {
                    Text(warning)
                        .font(.callout)
                        .foregroundStyle(.orange)
                        .frame(maxWidth: 900, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if session.busy && session.profiles.isEmpty {
                    ProgressView()
                } else if session.profiles.isEmpty {
                    emptyState
                } else {
                    grid
                }

                if let error = session.error {
                    Text(error)
                        .font(.callout)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: 20) {
                    Button("Reload profiles") { Task { _ = await session.loadProfiles() } }
                        .buttonStyle(.bordered)
                        .disabled(session.busy)
                    Button("Sign out") { Task { await app.signOut() } }
                        .buttonStyle(.bordered)
                    Button("Change server") { app.changeServer() }
                        .buttonStyle(.bordered)
                }
            }
            .padding(60)
            .frame(maxWidth: 1400, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .overlay {
            if let profile = asking {
                passwordPrompt(for: profile)
            }
        }
    }

    // MARK: - Pieces

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Who’s watching?").font(.system(size: 54, weight: .bold))
            Text(session.signedInUser.map { "Signed in as \($0.name)" } ?? "Choose a profile")
                .font(.title3)
                .foregroundStyle(.secondary)
        }
    }

    /// ⚠ **A nil `profiles` array is logged by `SessionStore` and lands here as an empty list**, so an
    /// empty picker is never silent — the failure this replaces is a screen that simply has nothing on it.
    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("No profiles were returned.", systemImage: "person.crop.circle.badge.questionmark")
                .font(.title3)
            Text("The server answered, so this is not a network problem. Household profiles are created in the "
                    + "web app under Settings, and a profile must exist before it can be picked here.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 900, alignment: .leading)
        }
    }

    private var grid: some View {
        LazyVGrid(columns: columns, alignment: .leading, spacing: 32) {
            ForEach(session.profiles) { profile in
                Button {
                    choose(profile)
                } label: {
                    tile(profile)
                }
                .buttonStyle(ProfileTileStyle())
                .disabled(profile.disabled || session.busy)
            }
        }
    }

    private func tile(_ profile: ProfileUser) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: profile.isAdmin ? "star.circle.fill" : "person.crop.circle.fill")
                    .font(.system(size: 44))
                    .foregroundStyle(profile.disabled ? Color.secondary : Color.white)
                if profile.hasPassword || profile.isAdmin {
                    Image(systemName: "lock.fill")
                        .font(.headline)
                        .foregroundStyle(.secondary)
                }
            }
            Text(profile.name)
                .font(.system(size: 30, weight: .semibold))
            Text(subtitle(profile))
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .frame(width: 360, alignment: .leading)
        .padding(24)
    }

    private func subtitle(_ profile: ProfileUser) -> String {
        if profile.disabled { return "Disabled — cannot be selected" }
        if profile.isAdmin { return "Administrator — asks for a password" }
        if profile.hasPassword { return "Password protected" }
        return "No password"
    }

    /// ⚠ The password card is an **overlay, not a sheet**, and that is deliberate on tvOS: a modal has to
    /// own focus to be dismissible with the remote's Back, and a plain overlay keeps the grid's focus model
    /// visible behind it. It carries its own `Cancel`, so there is always a way out.
    private func passwordPrompt(for profile: ProfileUser) -> some View {
        ZStack {
            Color.black.opacity(0.75)

            VStack(alignment: .leading, spacing: 20) {
                Text(profile.name).font(.system(size: 34, weight: .bold))
                Text("This profile needs its password.")
                    .font(.callout)
                    .foregroundStyle(.secondary)

                SecureField("password", text: $password)
                    .font(.system(size: 28))
                    .focused($passwordFocused)
                    .padding(16)
                    .frame(width: 640, alignment: .leading)
                    .background(Color.white.opacity(0.1), in: RoundedRectangle(cornerRadius: 12))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12).stroke(Color.white.opacity(0.3), lineWidth: 1)
                    )

                if let error = session.error {
                    Text(error)
                        .font(.callout)
                        .foregroundStyle(.orange)
                        .frame(maxWidth: 640, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: 20) {
                    Button {
                        let chosen = profile
                        let secret = password
                        passwordFocused = false
                        Task {
                            if await session.select(chosen, password: secret) {
                                password = ""
                                asking = nil
                                app.didSelectProfile()
                            }
                        }
                    } label: {
                        HStack(spacing: 10) {
                            if session.busy { ProgressView() }
                            Text(session.busy ? "Switching…" : "Watch as \(profile.name)")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(session.busy)

                    Button("Cancel") {
                        password = ""
                        asking = nil
                        passwordFocused = false
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding(44)
            .background(Color.black.opacity(0.92), in: RoundedRectangle(cornerRadius: 18))
            .overlay(
                RoundedRectangle(cornerRadius: 18).stroke(Color.white.opacity(0.2), lineWidth: 1)
            )
        }
        .onAppear { passwordFocused = true }
    }

    /// ⚠ Ask for a password when the profile has one **or is an administrator** — the server requires the
    /// administrator's password even though `has_password` may read false for a profile that has never set
    /// one, and a client that guessed "no password needed" would produce a 4xx instead of a form.
    private func choose(_ profile: ProfileUser) {
        session.clearError()
        if profile.hasPassword || profile.isAdmin {
            password = ""
            asking = profile
        } else {
            Task {
                if await session.select(profile, password: "") {
                    app.didSelectProfile()
                }
            }
        }
    }
}

/// A focus-aware tile: the default button chrome on a TV is a capsule, which is wrong for a profile card.
/// ⚠ The focused state changes the **border and scale only** — never the fill — because a tile that turns
/// solid white on focus loses the poster-style identity the grid is for, and on a 4K TV in a dark room a
/// full-bleed white rectangle is unpleasant to look at while moving through a row.
struct ProfileTileStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        TileBody(configuration: configuration)
    }

    private struct TileBody: View {
        // ⚠ Fully qualified: a nested type does not inherit the enclosing `ButtonStyle` scope, and a bare
        // `Configuration` here does not resolve.
        let configuration: ButtonStyle.Configuration
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .background(Color.white.opacity(isFocused ? 0.18 : 0.06),
                            in: RoundedRectangle(cornerRadius: 16))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.white.opacity(isFocused ? 0.9 : 0.18),
                                lineWidth: isFocused ? 3 : 1)
                )
                .scaleEffect(isFocused ? 1.04 : 1.0)
                .animation(.easeOut(duration: 0.15), value: isFocused)
        }
    }
}
