import Foundation

// Hand-written models for the endpoints this app calls, with the **FROZEN contract** as the source of
// truth: `docs/api/openapi.v1.json` (ADR-0001 — additive only). The frontend generates its TypeScript
// types from that same file; tvOS does not generate, and this header is the reason why that is still
// safe rather than a shortcut.
//
// ⚠⚠ **`apple/scripts/check-tvos-models.py` RUNS ON LINUX AND FAILS THE ROUND IF THIS FILE DRIFTS.**
// It reads the contract and every `Decodable` in this folder and checks, mechanically:
//
//   R1  every type here exists as a schema in the contract (no invented models);
//   R2  every JSON key decoded here is a property of that schema (no invented fields, no typos — a
//       mistyped key does not fail at runtime, it silently decodes to nil/`0`/`false`, which is the
//       exact class of bug a TV in another room makes undiagnosable);
//   R3  every property that is **not optional here** is `required` in the contract *or* carries a
//       `default` — i.e. the server has promised to send it. Anything else must be optional.
//
// ⚠ **WHERE R3 COMES FROM, because it is not pedantry.** In this contract almost nothing is
// `required` and the defaulted scalars are the exception: `LoginResponse.user`, `ProfilesResponse
// .profiles`, `SelectProfileResponse.profile` and both of `MeResponse`'s are $refs with NEITHER
// `required` NOR `default`. So they are optional *in the contract*, and decoding them as non-optional
// would turn a server that omitted one into a **decoding failure** — an app that cannot sign in,
// reporting `keyNotFound`. As optionals they decode to nil and the call site decides what to say. That
// is the same rule the iOS app learned the hard way in Phase B2: a silent default is worse than an
// absent value.
//
// ⚠ **Deliberately a SUBSET.** A contract property we do not decode is not drift — `SelectProfile
// Response.libraries` is a good example (the app does not need the grant list to draw a picker). The
// check is one-directional on purpose: nothing may be *invented* here, and nothing we *claim to read*
// may vanish from the contract.

// MARK: - Who is signed in

/// `#/components/schemas/SessionUser` — the signed-in user, as much of them as the client may see.
struct SessionUser: Decodable, Equatable {
    let id: String
    let name: String

    private enum CodingKeys: String, CodingKey {
        case id
        case name
    }
}

/// `#/components/schemas/ProfileUser` — one selectable profile, as the "Who's watching?" picker needs it.
///
/// ⚠ Carries no credential and no token by design: a profile's password is only ever *asked for*, never
/// returned (`PLEX_PROFILE_AUTH_PLAN.md` §4). The two flags are what let the picker show a lock and grey
/// out a disabled profile BEFORE anyone tries to enter it.
struct ProfileUser: Decodable, Equatable, Identifiable {
    let id: String
    let name: String
    let isAdmin: Bool
    let hasPassword: Bool
    let disabled: Bool
    let lastLogin: String

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case isAdmin = "is_admin"
        case hasPassword = "has_password"
        case disabled
        case lastLogin = "last_login"
    }
}

// MARK: - Screen #1 — sign in

/// `#/components/schemas/LoginRequest` — `POST /api/auth/login`.
///
/// ⚠ Identity is DELEGATED: these credentials are used once, against Jellyfin, and never stored. What
/// the app keeps is a session cookie it does not interpret. Nothing in this app ever holds a Jellyfin
/// token, and nothing here logs a password — `RKMLog`'s redactor is the gate that proves it.
///
/// ⚠ **`Encodable`, not `Decodable`.** The contract's request schemas default every field, so
/// optionality is meaningless on the way out; declaring this `Encodable`-only also keeps R3 aimed at
/// what it is for — the responses — instead of flagging a request the server would happily accept.
struct LoginRequest: Encodable {
    let username: String
    let password: String
    let deviceID: String

    private enum CodingKeys: String, CodingKey {
        case username
        case password
        case deviceID = "device_id"
    }
}

/// `#/components/schemas/LoginResponse`.
///
/// ⚠ `user` is **optional on purpose** — the contract does not mark it `required` and gives it no
/// default, so a server that omitted it must not fail the decode. The session is confirmed by
/// `GET /api/auth/me` straight afterwards anyway, which is the authoritative answer.
struct LoginResponse: Decodable {
    let ok: Bool
    let user: SessionUser?
    let expires: String

    private enum CodingKeys: String, CodingKey {
        case ok
        case user
        case expires
    }
}

// MARK: - Screen #2 — who's watching

/// `#/components/schemas/ProfilesResponse` — `GET /api/auth/profiles`.
///
/// ⚠ `profiles` is optional for the same reason as `LoginResponse.user`, and the app turns a nil list
/// into an empty one **with a log line**, so an empty picker is never silent.
struct ProfilesResponse: Decodable {
    let profiles: [ProfileUser]?
    let current: ProfileUser?
    let profileSelected: Bool
    let warning: String?

    private enum CodingKeys: String, CodingKey {
        case profiles
        case current
        case profileSelected = "profile_selected"
        case warning
    }

    /// The `warning` string as something displayable, empty when the server sent none.
    var warningText: String {
        let text = (warning ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return text
    }
}

/// `#/components/schemas/SelectProfileRequest` — `POST /api/auth/profile`.
///
/// ⚠ Switching to the ADMINISTRATOR's own profile needs that profile's password, so a shared device
/// cannot walk into it (decision 3, 2026-09-12). The client does not decide that rule — it asks for a
/// password when the server says the profile has one, and sends what it is given.
struct SelectProfileRequest: Encodable {
    let userID: String
    let password: String

    private enum CodingKeys: String, CodingKey {
        case userID = "user_id"
        case password
    }
}

/// `#/components/schemas/SelectProfileResponse` — the profile now in effect, and the libraries it may see.
///
/// ⚠ `libraries` is deliberately not decoded (see the header): the picker does not need it, and the
/// contract may grow it further without this file changing.
struct SelectProfileResponse: Decodable {
    let ok: Bool
    let profile: ProfileUser?

    private enum CodingKeys: String, CodingKey {
        case ok
        case profile
    }
}

// MARK: - The session's own answer

/// `#/components/schemas/MeResponse` — `GET /api/auth/me`: who is signed in, and which profile is in effect.
///
/// ⚠ This one call is what decides screen #1, #2 or #3 at launch, because it separates the three states
/// that look identical from the outside: *401* = signed out, *200 with `profile_selected` false* = this
/// device has a session but no profile chosen, and *200 with it true* = watching as that profile.
struct MeResponse: Decodable {
    let user: SessionUser?
    let profile: SessionUser?
    let onOwnProfile: Bool
    let profileSelected: Bool
    let expires: String

    private enum CodingKeys: String, CodingKey {
        case user
        case profile
        case onOwnProfile = "on_own_profile"
        case profileSelected = "profile_selected"
        case expires
    }
}
