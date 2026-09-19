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
/// ⚠⚠ **PHASE U2 REDESIGNED THIS SCREEN; PHASE U6 REBUILT ITS GEOMETRY FROM HIS PROTOTYPE.** His words after
/// the first build: *"the current one doesn't even look like what is seen in the html"*. Everything below is
/// now `u * <the number in the HTML>` (`TVTokens.Profile`): a centred column padded `4u / 6u`, the eyebrow
/// `1.05u` over the title at `4.4u`, tiles `13u` wide with `10.4u` gradient avatars, `3.4u` gold-bright
/// initials, a `2.2u` lock badge with a black ring, `1.5u` names over `0.95u` subtitles, and the pill row.
/// ⚠ The screen also carries the prototype's warm `profileGlow` radial — the one light source on an
/// otherwise black screen, and the reason the Profile Switcher does not read as an error page.
///
/// ⚠⚠ **TWO THINGS IT STILL DELIBERATELY DOES NOT TAKE FROM THE DESIGN INPUT:**
///   * **the words.** The prototype's `"Profile · password"` / `"Administrator · password"` is a second
///     vocabulary for one idea and cannot express the disabled case — HIS DECISION, 2026-09-19: the app's
///     words win. They live in `ProfileRules.subtitle`, pinned by tests;
///   * **the example data.** The prototype shows specific profiles locked and `rkm` as administrator. Every
///     one of those facts is SERVER state (`has_password`, `is_admin`, `disabled`) and is read from the wire —
///     hardcoding it ships a screen that lies the first time a password changes (falsifier **F2**).
struct ProfilesView: View {

    @EnvironmentObject private var app: AppModel
    @ObservedObject var session: SessionStore

    /// The profile whose password is being asked for, if any.
    @State private var asking: ProfileUser?
    @State private var password = ""

    /// ⚠ The administrator's notice panel — see ``adminNotice``. `Add profile` and `Manage profiles` are the
    /// prototype's controls and they are ADMIN-GATED; what they open is stated rather than faked.
    @State private var showingAdminNotice = false

    @FocusState private var passwordFocused: Bool

    /// ⚠⚠ **The focus state the dimming rule needs, and the ONE thing on this screen that is new
    /// machinery.** The prototype takes the unfocused tiles down to `opacity:.72` so the focused one reads as
    /// *the* choice — and on tvOS that is observable with no arithmetic at all: SwiftUI publishes which tile is
    /// focused, and the view dims the others. ⚠ It is a HYPOTHESIS about the platform (whether SwiftUI reports
    /// it cleanly inside a `ScrollView`), so it is falsifier **F1**, and the value it dims to is
    /// `TVTokens.Metric.profileTileDimmed` — one line to change if the round says it reads wrong.
    /// ⚠ This is NOT the hand-rolled focus maths §3 of the plan rejects: no frames are measured, no nearest
    /// centre is computed, and where the focus ring lands is still the engine's business.
    @FocusState private var focusedProfile: String?

    var body: some View {
        ZStack {
            background

            ScrollView {
                VStack(spacing: 0) {
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
                .padding(.horizontal, TVTokens.Profile.screenPaddingH)
                .padding(.vertical, TVTokens.Profile.screenPaddingV)
                .frame(maxWidth: .infinity)
            }
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

    /// The prototype's `.screen-profiles` background: `--bg` with a warm radial at the top centre.
    private var background: some View {
        ZStack {
            RKMColour.background
            RadialGradient(colors: [RKMColour.profileGlow, .clear],
                           center: .init(x: 0.5, y: 0),
                           startRadius: 0,
                           endRadius: TVTokens.u * 55)
        }
        .ignoresSafeArea()
    }

    // MARK: - The eyebrow, the title, the signed-in line

    private var header: some View {
        VStack(spacing: 0) {
            // ⚠ The eyebrow sits ABOVE the title (the design input's own order) and carries the profile COUNT,
            // which this screen never used to say. The wording and the singular are `ProfileRules.eyebrow`.
            Text(ProfileRules.eyebrow(profileCount: session.profiles.count,
                                      signedInAs: session.signedInUser?.name))
                .font(.system(size: TVTokens.Profile.eyebrowSize))
                .foregroundStyle(RKMColour.secondary)
                .padding(.bottom, TVTokens.Profile.eyebrowSize * 0.6)

            Text("Who’s watching?")
                .font(.system(size: TVTokens.Profile.titleSize, weight: .bold))
                .foregroundStyle(RKMColour.primary)
                .padding(.bottom, TVTokens.Profile.titleGap)
        }
        .multilineTextAlignment(.center)
    }

    /// ⚠ **A nil `profiles` array is logged by `SessionStore` and lands here as an empty list**, so an
    /// empty picker is never silent — the failure this replaces is a screen that simply has nothing on it.
    private var emptyState: some View {
        VStack(spacing: 12) {
            Label("No profiles were returned.", systemImage: "person.crop.circle.badge.questionmark")
                .font(.system(size: TVTokens.u * 1.35))
            Text("The server answered, so this is not a network problem. Household profiles are created in the "
                    + "web app under Settings, and a profile must exist before it can be picked here.")
                .font(.system(size: TVTokens.Profile.eyebrowSize))
                .foregroundStyle(RKMColour.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: TVTokens.u * 47)
        }
        .multilineTextAlignment(.center)
        .padding(.bottom, TVTokens.Profile.rowBottomGap)
    }

    private func notice(_ text: String, colour: Color) -> some View {
        Text(text)
            .font(.system(size: TVTokens.Profile.eyebrowSize))
            .foregroundStyle(colour)
            .frame(maxWidth: TVTokens.u * 47)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(.center)
            .padding(.bottom, TVTokens.Profile.rowBottomGap)
    }

    // MARK: - The row of profiles

    /// A **centred, horizontally scrolling row** — the layout, replacing the accepted grid.
    ///
    /// ⚠ The `GeometryReader` is not focus arithmetic: it makes the row CENTRED when the profiles fit on
    /// screen and SCROLLABLE when they do not (a household can grow past the width, and a row that simply
    /// overflowed would put a profile beyond the remote's reach). Without it a horizontal `ScrollView`'s
    /// content sits at the leading edge, so a household of four would look left-aligned on a 1920pt screen.
    private var profileRow: some View {
        GeometryReader { geometry in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: TVTokens.Profile.rowGap) {
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
                        .animation(.easeOut(duration: 0.28), value: focusedProfile)
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
                .padding(.horizontal, TVTokens.Profile.screenPaddingH)
                // ⚠ The centred-when-it-fits half. When the row is wider than the screen this is a no-op and
                // the scroll view scrolls; the focus engine brings the focused tile into view either way.
                .frame(minWidth: geometry.size.width)
            }
        }
        // ⚠ A fixed height, because a `GeometryReader` has none of its own: without it the row would take all
        // the space left on the screen and push the exits off the bottom. `13u` is the prototype's tile width
        // — the tile is that wide and as tall as its parts, and the gap below is the row's own `3u`.
        .frame(height: TVTokens.Profile.avatarSize + TVTokens.u * 3.4)
        .padding(.bottom, TVTokens.Profile.rowBottomGap)
    }

    /// One tile: the gradient avatar with the lock BADGE on it, the name, and the subtitle — the prototype's
    /// `.profile-tile`, whose width is set by the AVATAR (`13u`) and whose padding is `0.8u`.
    private func tile(_ profile: ProfileUser) -> some View {
        VStack(spacing: 0) {
            avatar(profile)
            Text(profile.name)
                .font(.system(size: TVTokens.Profile.nameSize, weight: .semibold))
                .foregroundStyle(profile.disabled ? RKMColour.muted : RKMColour.primary)
                .padding(.top, TVTokens.Profile.nameSize * 0.73)
            Text(ProfileRules.subtitle(profile))
                .font(.system(size: TVTokens.Profile.subSize))
                .foregroundStyle(RKMColour.secondary)
                .padding(.top, TVTokens.Profile.subSize * 0.26)
        }
        .frame(width: TVTokens.Profile.tileWidth)
        .padding(TVTokens.Profile.tilePadding)
        .opacity(profile.disabled ? 0.55 : 1)
    }

    /// The circular avatar — **gold initials on the prototype's own gradient**, with the lock as a
    /// bottom-right badge.
    ///
    /// ⚠ The initials colour is `accentHover` (`#ffd43b`), the app's own token. The design input's table gives
    /// `goldBright #FFD873` for exactly this role — and `#ffd43b` is what this app actually uses for it
    /// (`docs/TVOS_UX_PLAN.md` §0.1: that table is wrong in 8 of 10 values, so the TOKENS are the source,
    /// never the table).
    ///
    /// ⚠ The focus ring is around the AVATAR, not the tile, and it is read from the environment rather than
    /// measured — `@Environment(\.isFocused)` is published for the focused view and inherited by its
    /// descendants, which is the whole mechanism (no frames, no arithmetic).
    private func avatar(_ profile: ProfileUser) -> some View {
        ZStack {
            Circle().fill(RKMColour.avatarGradient)
            // The design input's `inset 0 0 0 1px rgba(255,255,255,.06)`.
            Circle().stroke(RKMColour.primary.opacity(0.06), lineWidth: 1)
            Text(ProfileRules.initials(profile.name))
                .font(.system(size: TVTokens.Profile.avatarFontSize, weight: .bold))
                .foregroundStyle(profile.disabled ? RKMColour.muted : RKMColour.accentHover)
            if profile.hasPassword || profile.isAdmin {
                lockBadge
            }
        }
        .frame(width: TVTokens.Profile.avatarSize, height: TVTokens.Profile.avatarSize)
        .overlay(FocusRing())
    }

    /// The lock, as the design input asks: a small badge overlapping the avatar's BOTTOM-RIGHT corner, with
    /// the black ring that separates it from the avatar it sits on (`box-shadow: 0 0 0 0.22u #000`).
    private var lockBadge: some View {
        Image(systemName: "lock.fill")
            .font(.system(size: TVTokens.Profile.lockFontSize))
            .foregroundStyle(RKMColour.primary)
            .frame(width: TVTokens.Profile.lockSize, height: TVTokens.Profile.lockSize)
            .background(RKMColour.surface3, in: Circle())
            .overlay(Circle().stroke(RKMColour.background, lineWidth: TVTokens.Profile.lockRing))
            // Pushed out to the circle's lower-right, the way the prototype draws it (`right:-2%; bottom:-2%`).
            .offset(x: TVTokens.Profile.avatarSize * 0.34, y: TVTokens.Profile.avatarSize * 0.34)
    }

    /// The administrator's `Add profile` tile — the prototype's dashed `+`. ⚠ Shown to administrators ONLY
    /// (`ProfileRules.isAdministrator`): a tile that appears for somebody the server will refuse is exactly
    /// the fault `docs/ARCHITECTURE.md` §11 names.
    private var addProfileTile: some View {
        VStack(spacing: 0) {
            ZStack {
                Circle().stroke(RKMColour.primary.opacity(0.09),
                                style: StrokeStyle(lineWidth: TVTokens.u * 0.13, dash: [TVTokens.u * 0.6,
                                                                                        TVTokens.u * 0.6]))
                Image(systemName: "plus")
                    .font(.system(size: TVTokens.Profile.avatarFontSize, weight: .light))
                    .foregroundStyle(RKMColour.secondary)
            }
            .frame(width: TVTokens.Profile.avatarSize, height: TVTokens.Profile.avatarSize)

            Text("Add profile")
                .font(.system(size: TVTokens.Profile.nameSize, weight: .semibold))
                .foregroundStyle(RKMColour.primary)
                .padding(.top, TVTokens.Profile.nameSize * 0.73)
            // ⚠ The prototype keeps an empty line here (`<span class="sub">&nbsp;</span>`) so the tiles'
            // names stay on one baseline whether or not they have a subtitle. A `Text(" ")` does the same.
            Text(" ")
                .font(.system(size: TVTokens.Profile.subSize))
                .padding(.top, TVTokens.Profile.subSize * 0.26)
        }
        .frame(width: TVTokens.Profile.tileWidth)
        .padding(TVTokens.Profile.tilePadding)
    }

    private var isAdministrator: Bool {
        ProfileRules.isAdministrator(signedInUserID: session.signedInUser?.id, profiles: session.profiles)
    }

    // MARK: - The ways out

    /// ⚠ **THE WAYS OUT STAY.** Phase A's rule, unchanged: a TV screen whose only controls are unreachable
    /// with a remote is a dead end, and a dead end on a TV is a phone call. The prototype's row is
    /// `Manage profiles` + `Sign out`; `Reload profiles` and `Change server` are the accepted screen's own
    /// exits and they are kept — dropping either would take away the only way out of a server that answers
    /// with no profiles at all.
    private var exits: some View {
        HStack(spacing: TVTokens.Profile.actionGap) {
            if isAdministrator {
                pill("Manage profiles") { showingAdminNotice = true }
            }
            pill("Sign out") { Task { await app.signOut() } }
            pill("Reload profiles") { Task { _ = await session.loadProfiles() } }
                .disabled(session.busy)
            pill("Change server") { app.changeServer() }
        }
    }

    /// ⚠ The design input's `.pill-btn`: a translucent fill, a hairline border, a fully-rounded box and a
    /// `1.05u` label — the secondary row under the profile band.
    ///
    /// ⚠⚠ **NOTHING IS PADDED HERE, AND THAT IS THE POINT.** `PillButtonStyle` draws the whole button
    /// (padding, fill, border, focus ring), because a caller that pads the `Button` instead puts the focus
    /// ring inside the box rather than around it — his report on the Home's `Details` button, 2026-09-20, was
    /// exactly that. One place to get right, and it is not the caller.
    private func pill(_ title: String, action: @escaping () -> Void) -> some View {
        Button(title, action: action)
            .buttonStyle(PillButtonStyle())
    }

    /// ⚠ The one pill that is FILLED rather than translucent — the password prompt's
    /// `Watch as <name>`. Same style, different kind, so the geometry cannot drift from the row above it.
    private func primaryPill(action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: TVTokens.u * 0.5) {
                if session.busy { ProgressView() }
                Text(session.busy ? "Switching…" : "Watch as \(asking?.name ?? "")")
            }
        }
        .buttonStyle(PillButtonStyle(kind: .primary))
        .disabled(session.busy)
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
            RKMColour.background.opacity(0.78)

            VStack(spacing: TVTokens.u * 1.15) {
                Text("Profiles are managed in the web app")
                    .font(.system(size: TVTokens.u * 1.75, weight: .bold))
                    .foregroundStyle(RKMColour.primary)

                Text("This TV app can switch between profiles. Creating, renaming, resetting a password and "
                        + "deleting them happens in RKM Cinema's web UI, under Settings.")
                    .font(.system(size: TVTokens.Profile.eyebrowSize))
                    .foregroundStyle(RKMColour.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: TVTokens.u * 43)

                Text(session.address.displayString)
                    .font(.system(size: TVTokens.Profile.eyebrowSize, design: .monospaced))
                    .foregroundStyle(RKMColour.accent)

                pill("Close") { showingAdminNotice = false }
            }
            .padding(TVTokens.u * 2.3)
            .background(RKMColour.surface3, in: RoundedRectangle(cornerRadius: TVTokens.u,
                                                                 style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: TVTokens.u, style: .continuous)
                    .stroke(RKMColour.border, lineWidth: 1)
            )
        }
    }

    /// ⚠ The password card is an **overlay, not a sheet**, and that is deliberate on tvOS: a modal has to
    /// own focus to be dismissible with the remote's Back, and a plain overlay keeps the row's focus model
    /// visible behind it. It carries its own `Cancel`, so there is always a way out.
    private func passwordPrompt(for profile: ProfileUser) -> some View {
        ZStack {
            RKMColour.background.opacity(0.75)

            VStack(alignment: .leading, spacing: TVTokens.u) {
                Text(profile.name)
                    .font(.system(size: TVTokens.u * 1.75, weight: .bold))
                    .foregroundStyle(RKMColour.primary)
                Text("This profile needs its password.")
                    .font(.system(size: TVTokens.Profile.eyebrowSize))
                    .foregroundStyle(RKMColour.secondary)

                SecureField("password", text: $password)
                    .font(.system(size: TVTokens.u * 1.45))
                    .focused($passwordFocused)
                    .padding(TVTokens.u * 0.8)
                    .frame(width: TVTokens.u * 33, alignment: .leading)
                    .background(RKMColour.surface2,
                                in: RoundedRectangle(cornerRadius: TVTokens.u * 0.6, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: TVTokens.u * 0.6, style: .continuous)
                            .stroke(RKMColour.border, lineWidth: 1)
                    )

                if let error = session.error {
                    Text(error)
                        .font(.system(size: TVTokens.Profile.eyebrowSize))
                        .foregroundStyle(RKMColour.warning)
                        .frame(maxWidth: TVTokens.u * 33, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: TVTokens.Profile.actionGap) {
                    primaryPill {
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
                    }

                    pill("Cancel") {
                        password = ""
                        asking = nil
                        passwordFocused = false
                    }
                }
            }
            .padding(TVTokens.u * 2.3)
            .background(RKMColour.surface3, in: RoundedRectangle(cornerRadius: TVTokens.u,
                                                                 style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: TVTokens.u, style: .continuous)
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
/// that looks wrong at the edges. ⚠ The ring is drawn OUTSIDE the avatar (`padding(-ring)`) with the
/// prototype's own `0.28u` weight.
struct FocusRing: View {

    @Environment(\.isFocused) private var isFocused

    var body: some View {
        Circle()
            .stroke(RKMColour.primary.opacity(isFocused ? 0.85 : 0),
                    lineWidth: isFocused ? TVTokens.Profile.focusRing : 0)
            .padding(-TVTokens.Profile.focusRing * 1.6)
            .animation(.easeOut(duration: 0.28), value: isFocused)
    }
}

/// A focus-aware tile style: the prototype's lift, and its own easing curve.
///
/// ⚠ The focused state changes the **background, border and scale only** — never the fill — because a tile
/// that turns solid white on focus loses the poster-style identity the row is for, and on a 4K TV in a dark
/// room a full-bleed white rectangle is unpleasant to look at while moving through a row.
///
/// ⚠ The motion is the prototype's own: `transform .28s cubic-bezier(.2,.9,.3,1)` and
/// `translateY(-0.3u) scale(1.14)`. ⚠ Whether that reads well NEXT TO the platform's own focus treatment is
/// the round's business (falsifier **F1**), and it is one line here to change.
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
                .scaleEffect(isFocused ? TVTokens.Profile.focusScale : 1.0)
                .offset(y: isFocused ? -TVTokens.Profile.focusLift : 0)
                .animation(.timingCurve(0.2, 0.9, 0.3, 1, duration: 0.28), value: isFocused)
        }
    }
}

/// The prototype's `.pill-btn`, in both its kinds — **and the style draws the whole button, box included.**
///
/// ⚠⚠ **WHY IT OWNS THE BOX: his report on the Home's `Details` button.** A `ButtonStyle` receives the
/// button's CONTENT and nothing else, so a ring drawn in the style while the padding and the fill are applied
/// to the `Button` wraps the LABEL — a small ring around a word, inside the button's own box, which is what he
/// saw. Moving the box in here makes that impossible rather than merely fixed, and it is the same shape
/// `TabButtonStyle` already had.
///
/// ⚠ The `1.08` lift, the lighter fill and the white ring are the prototype's `.pill-btn:focus`; `.primary`
/// is its gold CTA fill with near-black text.
struct PillButtonStyle: ButtonStyle {

    enum Kind { case plain, primary }

    var kind: Kind = .plain

    func makeBody(configuration: Configuration) -> some View {
        PillChrome(configuration: configuration, kind: kind)
    }

    // ⚠⚠ NOT `Body`: every `Style` protocol declares an associatedtype requirement called `Body`, so a
    // helper view nested inside a conformer and named `Body` collides with it — measured on the Mac, U6's
    // second round: `type 'TabButtonStyle' does not conform to protocol 'ButtonStyle'` plus
    // `struct 'Body' must be as accessible as its enclosing type`. The Phase A tile style is called
    // `TileBody` for exactly this reason; this is that rule, spelled the same way.
    private struct PillChrome: View {
        let configuration: ButtonStyle.Configuration
        let kind: Kind
        @Environment(\.isFocused) private var isFocused

        var body: some View {
            configuration.label
                .font(.system(size: TVTokens.Profile.pillFontSize, weight: kind == .primary ? .semibold : .regular))
                .foregroundStyle(kind == .primary ? RKMColour.background : RKMColour.primary)
                .padding(.horizontal, TVTokens.Profile.pillPaddingH)
                .padding(.vertical, TVTokens.Profile.pillPaddingV)
                .background(fill, in: RoundedRectangle(cornerRadius: TVTokens.Profile.pillRadius,
                                                       style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: TVTokens.Profile.pillRadius, style: .continuous)
                        .stroke(isFocused ? RKMColour.primary.opacity(0.85) : RKMColour.border,
                                lineWidth: isFocused ? TVTokens.Bar.focusRing : 1)
                }
                .scaleEffect(isFocused ? 1.08 : 1)
                .opacity(isFocused ? 1 : 0.94)
                .animation(.easeOut(duration: 0.22), value: isFocused)
        }

        private var fill: Color {
            kind == .primary ? RKMColour.accent : RKMColour.surface2.opacity(0.9)
        }
    }
}
