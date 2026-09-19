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
/// ⚠⚠ **PHASE U2 REDESIGNED THE TILE ROW, ON THIS SAME ACCEPTED SCREEN** — `docs/TVOS_UX_PLAN.md` §1a. The
/// delta: the eyebrow line above the title (with the profile count), a circular gold-initials avatar
/// replacing the SF Symbol, the lock moved to a bottom-right BADGE on that avatar, a centred scrolling ROW
/// instead of a `LazyVGrid`, the administrator's two admin controls, and focus that lifts the focused tile
/// (~1.14) while the others dim (0.72) so the row reads as ONE choice.
///
/// ⚠⚠ **TWO THINGS IT DELIBERATELY DID NOT TAKE FROM THE BUILDSPEC:**
///   * **the words.** The buildspec's `"Profile · password"` set is a second vocabulary for one idea and
///     cannot express the disabled case — HIS DECISION, 2026-09-19: the app's words win. They live in
///     `ProfileRules.subtitle`, pinned by tests.
///   * **the example data.** The buildspec's §3 shows specific profiles locked and `rkm` as administrator.
///     Every one of those facts is SERVER state (`has_password`, `is_admin`, `disabled`) and is read from the
///     wire — hardcoding it ships a screen that lies the first time a password changes (falsifier **F2**).
struct ProfilesView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var session: SessionStore

    /// The profile whose password is being asked for, if any.
    @State private var asking: ProfileUser?
    @State private var password = ""

    /// ⚠ The administrator's notice panel — see ``adminNotice``. `Add profile` and `Manage profiles` are the
    /// buildspec's controls and they are ADMIN-GATED; what they open is stated rather than faked.
    @State private var showingAdminNotice = false

    @FocusState private var passwordFocused: Bool

    /// ⚠⚠ **The focus state the dimming rule needs, and the ONE thing on this screen that is new
    /// machinery.** The buildspec wants the unfocused tiles taken down so the focused one reads as *the*
    /// choice — and on tvOS that is observable with no arithmetic at all: SwiftUI publishes which tile is
    /// focused, and the view dims the others. ⚠ It is a HYPOTHESIS about the platform (whether SwiftUI
    /// reports it cleanly inside a `ScrollView`), so it is falsifier **F1**, and the value it dims to is
    /// `TVTokens.Metric.profileTileDimmed` — one line to change if the round says it reads wrong.
    /// ⚠ This is NOT the hand-rolled focus maths §3 of the plan rejects: no frames are measured, no nearest
    /// centre is computed, and where the focus ring lands is still the engine's business.
    @FocusState private var focusedProfile: String?

    var body: some View {
        ScrollView {
            VStack(spacing: 34) {
                header

                if let warning = session.warning, !warning.isEmpty {
                    notice(warning, colour: RKMColour.warning)
                }

                if session.busy && session.profiles.isEmpty {
                    ProgressView()
                } else if session.profiles.isEmpty {
                    emptyState
                } else {
                    profileRow
                }

                if let error = session.error {
                    notice(error, colour: RKMColour.warning)
                }

                exits
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 48)
        }
        .background(RKMColour.background)
        .overlay {
            if let profile = asking {
                passwordPrompt(for: profile)
            } else if showingAdminNotice {
                adminNotice
            }
        }
    }

    // MARK: - The eyebrow, the title, the signed-in line

    private var header: some View {
        VStack(spacing: 10) {
            // ⚠ The eyebrow sits ABOVE the title (the buildspec's §1a delta) and carries the profile COUNT,
            // which this screen never used to say. The wording and the singular are `ProfileRules.eyebrow`.
            Text(ProfileRules.eyebrow(profileCount: session.profiles.count,
                                      signedInAs: session.signedInUser?.name))
                .font(.system(size: 22))
                .foregroundStyle(RKMColour.muted)

            Text("Who’s watching?")
                .font(.system(size: TVTokens.Metric.profileTitle, weight: .bold))
        }
        .multilineTextAlignment(.center)
        .padding(.horizontal, TVTokens.Metric.safeMargin)
    }

    /// ⚠ **A nil `profiles` array is logged by `SessionStore` and lands here as an empty list**, so an
    /// empty picker is never silent — the failure this replaces is a screen that simply has nothing on it.
    private var emptyState: some View {
        VStack(spacing: 12) {
            Label("No profiles were returned.", systemImage: "person.crop.circle.badge.questionmark")
                .font(.system(size: 26))
            Text("The server answered, so this is not a network problem. Household profiles are created in the "
                    + "web app under Settings, and a profile must exist before it can be picked here.")
                .font(.system(size: 22))
                .foregroundStyle(RKMColour.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 900)
        }
        .multilineTextAlignment(.center)
    }

    private func notice(_ text: String, colour: Color) -> some View {
        Text(text)
            .font(.system(size: 20))
            .foregroundStyle(colour)
            .frame(maxWidth: 900)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(.center)
    }

    // MARK: - The row of profiles

    /// A **centred, horizontally scrolling row** — the buildspec's layout, replacing the accepted grid.
    ///
    /// ⚠ The `GeometryReader` is not focus arithmetic: it makes the row CENTRED when the profiles fit on
    /// screen and SCROLLABLE when they do not. Without it a horizontal `ScrollView`'s content sits at the
    /// leading edge, so a household of four would look left-aligned on a 1920pt screen — which is the one
    /// thing the buildspec asks this row not to be.
    private var profileRow: some View {
        GeometryReader { geometry in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 36) {
                    ForEach(session.profiles) { profile in
                        Button {
                            choose(profile)
                        } label: {
                            tile(profile)
                        }
                        .buttonStyle(ProfileTileStyle())
                        .disabled(profile.disabled || session.busy)
                        // ⚠ The focused tile is the ONE the row highlights; every other tile reads
                        // `profileTileDimmed`. Both come from one `@FocusState` value.
                        .opacity(focusedProfile == nil || focusedProfile == profile.id
                                 ? 1 : TVTokens.Metric.profileTileDimmed)
                        .animation(.easeOut(duration: 0.15), value: focusedProfile)
                        .focused($focusedProfile, equals: profile.id)
                        // ⚠ The buildspec's §6: a tile is a name and a glyph, and a glyph says nothing to a
                        // screen reader — so the label states the same facts `subtitle` does.
                        .accessibilityLabel(ProfileRules.accessibilityLabel(profile))
                    }

                    if isAdministrator {
                        Button { showingAdminNotice = true } label: { addProfileTile }
                            .buttonStyle(ProfileTileStyle())
                            .accessibilityLabel("Add profile")
                    }
                }
                .padding(.horizontal, TVTokens.Metric.safeMargin)
                // ⚠ The centred-when-it-fits half. When the row is wider than the screen this is a no-op and
                // the scroll view scrolls; the focus engine brings the focused tile into view either way.
                .frame(minWidth: geometry.size.width)
            }
        }
        // ⚠ A fixed height, because a `GeometryReader` has none of its own: without it the row would take all
        // the space left on the screen and push the exits off the bottom. 300pt = the 220pt avatar + the two
        // text lines + the focus lift's own room.
        .frame(height: 300)
    }

    /// One tile: the circular initials avatar with the lock BADGE on it, the name, and the subtitle.
    private func tile(_ profile: ProfileUser) -> some View {
        VStack(spacing: 12) {
            avatar(profile)
            VStack(spacing: 4) {
                Text(profile.name)
                    .font(.system(size: 30, weight: .semibold))
                    .foregroundStyle(profile.disabled ? RKMColour.muted : RKMColour.primary)
                Text(ProfileRules.subtitle(profile))
                    .font(.system(size: 18))
                    .foregroundStyle(RKMColour.muted)
            }
        }
        .frame(width: 260)
        .opacity(profile.disabled ? 0.55 : 1)
    }

    /// The circular avatar — **gold initials on the elevated surface**, with the lock as a bottom-right badge.
    ///
    /// ⚠ The initials colour is `accentHover` (`#ffd43b`), the app's own token. The buildspec's table gives
    /// `goldBright #FFD873` for exactly this role — and `#ffd43b` is what this app actually uses for it
    /// (`docs/TVOS_UX_PLAN.md` §0.1: the buildspec's table is wrong in 8 of 10 values, so the TOKENS are the
    /// source, never the table).
    ///
    /// ⚠ The focus ring is around the AVATAR, not the tile, and it is read from the environment rather than
    /// measured — `@Environment(\.isFocused)` is published for the focused view and inherited by its
    /// descendants, which is the whole mechanism (no frames, no arithmetic).
    private func avatar(_ profile: ProfileUser) -> some View {
        ZStack {
            Circle().fill(RKMColour.surface3)
            Circle().stroke(RKMColour.border, lineWidth: 1)
            Text(ProfileRules.initials(profile.name))
                .font(.system(size: 62, weight: .bold))
                .foregroundStyle(profile.disabled ? RKMColour.muted : RKMColour.accentHover)
            if profile.hasPassword || profile.isAdmin {
                lockBadge
            }
        }
        .frame(width: 220, height: 220)
        .overlay(ring)
    }

    /// The lock, as the buildspec asks: a small badge overlapping the avatar's BOTTOM-RIGHT corner, rather
    /// than the glyph that used to sit beside a symbol.
    private var lockBadge: some View {
        Image(systemName: "lock.fill")
            .font(.system(size: 20, weight: .semibold))
            .foregroundStyle(RKMColour.primary)
            .frame(width: 46, height: 46)
            .background(RKMColour.background, in: Circle())
            .overlay(Circle().stroke(RKMColour.border, lineWidth: 1))
            // Pushed out to the circle's lower-right, the way the buildspec's concept draws it.
            .offset(x: 74, y: 74)
    }

    /// The focus ring. ⚠ A separate view so it can be an `@Environment` reader — a `ButtonStyle` cannot see
    /// the label's own subviews, and measuring the avatar to draw this would be the hand-rolled focus maths
    /// the plan rejects.
    private var ring: some View {
        FocusRing()
    }

    /// The administrator's `Add profile` tile — the buildspec's dashed `+`. ⚠ Shown to administrators ONLY
    /// (`ProfileRules.isAdministrator`): a tile that appears for somebody the server will refuse is exactly
    /// the fault `docs/ARCHITECTURE.md` §11 names.
    private var addProfileTile: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle().stroke(RKMColour.border, style: StrokeStyle(lineWidth: 2, dash: [8, 8]))
                Image(systemName: "plus")
                    .font(.system(size: 54, weight: .light))
                    .foregroundStyle(RKMColour.secondary)
            }
            .frame(width: 220, height: 220)

            VStack(spacing: 4) {
                Text("Add profile")
                    .font(.system(size: 30, weight: .semibold))
                Text("Administrator")
                    .font(.system(size: 18))
                    .foregroundStyle(RKMColour.muted)
            }
        }
        .frame(width: 260)
    }

    private var isAdministrator: Bool {
        ProfileRules.isAdministrator(signedInUserID: session.signedInUser?.id, profiles: session.profiles)
    }

    // MARK: - The ways out

    /// ⚠ **THE WAYS OUT STAY.** Phase A's rule, unchanged: a TV screen whose only controls are unreachable
    /// with a remote is a dead end, and a dead end on a TV is a phone call. The buildspec's row is
    /// `Manage profiles` + `Sign out`; `Reload profiles` and `Change server` are the accepted screen's own
    /// exits and they are kept — dropping either would take away the only way out of a server that answers
    /// with no profiles at all.
    private var exits: some View {
        HStack(spacing: 20) {
            if isAdministrator {
                Button("Manage profiles") { showingAdminNotice = true }
                    .buttonStyle(.bordered)
            }
            Button("Sign out") { Task { await app.signOut() } }
                .buttonStyle(.bordered)
            Button("Reload profiles") { Task { _ = await session.loadProfiles() } }
                .buttonStyle(.bordered)
                .disabled(session.busy)
            Button("Change server") { app.changeServer() }
                .buttonStyle(.bordered)
        }
        .font(.system(size: 22))
        .padding(.top, 6)
    }

    /// ⚠⚠ **WHAT `Add profile` / `Manage profiles` OPEN, AND WHY IT IS NOT A FORM.** Both are real server
    /// routes (`POST /api/admin/users`, `/rename`, `/password`, `/policy`, `DELETE /api/admin/users/{id}` —
    /// `backend/api/routes/admin_users.py`), so offering them is not offering what the server refuses. But
    /// this app has **no admin write path at all** — no model, no client method, no screen — and building one
    /// is a phase of its own, not a side effect of a redesign. So rather than a form that cannot submit, the
    /// control states where profiles are actually managed and names the server it is on. That is the honest
    /// version of the control, and the alternative (hiding it) would be the app pretending the feature does
    /// not exist.
    private var adminNotice: some View {
        ZStack {
            Color.black.opacity(0.78)

            VStack(spacing: 22) {
                Text("Profiles are managed in the web app")
                    .font(.system(size: 34, weight: .bold))

                Text("This TV app can switch between profiles. Creating, renaming, resetting a password and "
                        + "deleting them happens in RKM Cinema's web UI, under Settings.")
                    .font(.system(size: 22))
                    .foregroundStyle(RKMColour.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 820)

                Text(session.address.displayString)
                    .font(.system(size: 22, design: .monospaced))
                    .foregroundStyle(RKMColour.accent)

                Button("Close") { showingAdminNotice = false }
                    .buttonStyle(.borderedProminent)
                    .font(.system(size: 22))
            }
            .padding(44)
            .background(RKMColour.surface3, in: RoundedRectangle(cornerRadius: DesignTokens.Radius.xl,
                                                                 style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.xl, style: .continuous)
                    .stroke(RKMColour.border, lineWidth: 1)
            )
        }
    }

    /// ⚠ The password card is an **overlay, not a sheet**, and that is deliberate on tvOS: a modal has to
    /// own focus to be dismissible with the remote's Back, and a plain overlay keeps the row's focus model
    /// visible behind it. It carries its own `Cancel`, so there is always a way out.
    private func passwordPrompt(for profile: ProfileUser) -> some View {
        ZStack {
            Color.black.opacity(0.75)

            VStack(alignment: .leading, spacing: 20) {
                Text(profile.name).font(.system(size: 34, weight: .bold))
                Text("This profile needs its password.")
                    .font(.system(size: 22))
                    .foregroundStyle(RKMColour.secondary)

                SecureField("password", text: $password)
                    .font(.system(size: 28))
                    .focused($passwordFocused)
                    .padding(16)
                    .frame(width: 640, alignment: .leading)
                    .background(RKMColour.surface2, in: RoundedRectangle(cornerRadius: DesignTokens.Radius.md))
                    .overlay(
                        RoundedRectangle(cornerRadius: DesignTokens.Radius.md)
                            .stroke(RKMColour.border, lineWidth: 1)
                    )

                if let error = session.error {
                    Text(error)
                        .font(.system(size: 20))
                        .foregroundStyle(RKMColour.warning)
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
            .background(RKMColour.surface3, in: RoundedRectangle(cornerRadius: DesignTokens.Radius.xl,
                                                                 style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.xl, style: .continuous)
                    .stroke(RKMColour.border, lineWidth: 1)
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

/// The white focus ring around an avatar.
///
/// ⚠ Its own view because it reads `@Environment(\.isFocused)`: the environment is published for the
/// FOCUSED view and inherited by its descendants, so this ring lights up exactly when its tile has focus —
/// no frame is measured and no focus maths is written (the trap `docs/TVOS_UX_PLAN.md` §3 names, and the
/// reason `RailFocus.swift` was deleted in Phase B).
///
/// ⚠ **A separate type from `ProfileTileStyle`, on purpose: the ring is around the AVATAR and the lift is
/// the whole TILE.** One view cannot be both, and faking it by drawing the ring on the tile is the version
/// that looks wrong at the edges.
struct FocusRing: View {

    @Environment(\.isFocused) private var isFocused

    var body: some View {
        Circle()
            .stroke(RKMColour.primary.opacity(isFocused ? 0.9 : 0), lineWidth: 5)
            .padding(-10)
            .animation(.easeOut(duration: 0.15), value: isFocused)
    }
}

/// A focus-aware tile style: the buildspec's lift, and a spring rather than a linear ease.
///
/// ⚠ The focused state changes the **background, border and scale only** — never the fill — because a tile
/// that turns solid white on focus loses the poster-style identity the row is for, and on a 4K TV in a dark
/// room a full-bleed white rectangle is unpleasant to look at while moving through a row.
///
/// ⚠ The scale is **1.14** and the animation is the buildspec's spring
/// (`response 0.35, dampingFraction 0.7`) — the two motion values this phase adopts. ⚠ Whether a 1.14 lift
/// reads well NEXT TO the platform's own focus treatment is the round's business (falsifier **F1**), and it
/// is one line here to change.
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
                .padding(20)
                .background(RKMColour.surface1.opacity(isFocused ? 0.95 : 0.55),
                            in: RoundedRectangle(cornerRadius: DesignTokens.Radius.xl, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: DesignTokens.Radius.xl, style: .continuous)
                        .stroke(RKMColour.primary.opacity(isFocused ? 0.85 : 0.12),
                                lineWidth: isFocused ? 3 : 1)
                )
                .scaleEffect(isFocused ? 1.14 : 1.0)
                .animation(.spring(response: 0.35, dampingFraction: 0.7), value: isFocused)
        }
    }
}
