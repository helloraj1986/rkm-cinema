import Foundation
// ⚠⚠ **Combine, not SwiftUI — and this import is load-bearing.** `ObservableObject` and `@Published` are
// Combine's, and SwiftUI stopped re-exporting Combine with the iOS 26 SDK. Omitting it fails the Mac build
// with "type 'SessionStore' does not conform to protocol 'ObservableObject'" plus a wall of
// "missing import of defining module 'Combine'" pointing at every `@Published` line.
//
// ⚠ It is also the one defect NEITHER of the other two gates can see: the Linux typecheck passes because
// `typecheck-stubs/TVStubs.swift` declares `ObservableObject` in the same module, so the missing import is
// invisible there — `apple/scripts/check-imports.py apple/tvos/RKMCinemaTV` is what caught it, on the first
// run. Two gates, one blind spot each; that is the argument for having both.
import Combine
import RKMServerKit

/// Who is signed in, which profile is in effect — and nothing else.
///
/// ⚠ **This is NOT a second implementation of the web app's auth.** Every state here is read back from
/// the server's own routes (`GET /api/auth/me`, `GET /api/auth/profiles`, `POST /api/auth/profile`), and
/// the session cookie is held by `URLSession`'s shared cookie store — the same mechanism the browser
/// uses. **There is no token in this file and there must never be one**: the cookie is the credential.
/// (The only credential this app ever *sends* is a username/password to `POST /api/auth/login`, once, and
/// the server delegates that straight to Jellyfin without storing it.)
///
/// ⚠ **The rule this file exists to obey: ONE server answer decides the state.** After any change —
/// sign in, select a profile — the app re-reads `GET /api/auth/me` rather than assembling the new state
/// from the response it just got. Assembling it locally is how a client and a server come to disagree
/// about which profile is watching, and the disagreement is invisible until the wrong person's Continue
/// Watching appears on the TV.
///
/// ⚠ `Foundation` + `Combine` + `RKMServerKit` only — no SwiftUI — so
/// `apple/scripts/check-apple-typecheck.sh` compiles it on Linux before a Mac round is spent on it.
final class SessionStore: ObservableObject {

    /// What `POST /api/auth/login` sends as `device_id`. ⚠ Not a secret and not a tracking id: it is the
    /// Jellyfin-side session label, so the server's own client list can tell which device a session came
    /// from. The server uses `rkm-cinema-web` for the browser; this is the TV's.
    static let deviceID = "rkm-cinema-tvos"

    /// The name the server's session cookie is set under (`backend/services/auth.py`). Used to log the
    /// cookie's **name** and existence, never its value — which is the whole point of `LogRedactor`.
    static let sessionCookieName = "rkm_session"

    let address: ServerAddress
    private let client: APIClient

    @Published private(set) var signedInUser: SessionUser?
    @Published private(set) var currentProfile: SessionUser?
    @Published private(set) var onOwnProfile = true
    @Published private(set) var profileSelected = false
    @Published private(set) var profiles: [ProfileUser] = []
    @Published private(set) var warning: String?
    @Published private(set) var busy = false
    @Published private(set) var error: String?

    init(address: ServerAddress, client: APIClient? = nil) {
        self.address = address
        self.client = client ?? APIClient(address: address)
    }

    /// What `GET /api/auth/me` said at launch — the three states that look identical from outside.
    enum StartOutcome: Equatable {
        case signedIn
        case signedOut
        /// A transport failure only. An HTTP response is never this (`ServerProbe`'s rule).
        case unreachable(String)
    }

    // MARK: - Launch

    /// ⚠ **`401` and "no network" must not be collapsed**: the first is the server telling us to sign in,
    /// the second is the server not answering at all. They lead to different screens, and on a TV the
    /// difference is a room away.
    func start(correlation: CorrelationID) async -> StartOutcome {
        await withBusy { () async -> StartOutcome in
            do {
                let me: MeResponse = try await self.client.get("api/auth/me", correlation: correlation)
                self.apply(me)
                self.logCookieState("after /api/auth/me")
                return .signedIn
            } catch let error as APIError {
                if error.isUnauthorized {
                    RKMLog.info("not signed in (401 \(error.authProblem ?? "no problem header"))",
                                category: .auth, correlation: correlation)
                    return .signedOut
                }
                return .unreachable(error.errorDescription ?? "Could not reach the server.")
            } catch {
                return .unreachable(String(describing: error))
            }
        }
    }

    // MARK: - Sign in

    func signIn(username: String, password: String, correlation: CorrelationID = .next()) async -> Bool {
        error = nil
        let user = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !user.isEmpty else {
            error = "Enter your username."
            return false
        }

        return await withBusy {
            do {
                // ⚠ The response's `user` is optional in the contract; it is logged, not trusted.
                let response: LoginResponse = try await self.client.post(
                    "api/auth/login",
                    body: LoginRequest(username: user, password: password, deviceID: Self.deviceID),
                    correlation: correlation
                )
                RKMLog.info("sign-in ok=\(response.ok) user=\(response.user?.name ?? "not reported")"
                                + " expires=\(response.expires.isEmpty ? "not reported" : response.expires)",
                            category: .auth, correlation: correlation)
                self.logCookieState("after sign-in")
                // ⚠ Re-read the session rather than trusting the login response — one authority.
                return await self.refreshSession(correlation: correlation)
            } catch {
                self.error = (error as? APIError)?.errorDescription ?? String(describing: error)
                RKMLog.error("sign-in failed: \(self.error ?? "")", category: .auth, correlation: correlation)
                return false
            }
        }
    }

    // MARK: - Who's watching

    /// `GET /api/auth/profiles` — the picker's data. ⚠ A nil `profiles` (the contract does not require it)
    /// becomes an empty list **with a log line**, so an empty picker is never silent.
    func loadProfiles(correlation: CorrelationID = .next()) async -> Bool {
        error = nil
        return await withBusy {
            do {
                let response: ProfilesResponse = try await self.client.get("api/auth/profiles",
                                                                          correlation: correlation)
                if let list = response.profiles {
                    self.profiles = list
                } else {
                    self.profiles = []
                    RKMLog.error("profiles: the server sent no `profiles` array", category: .auth,
                                 correlation: correlation)
                }
                self.profileSelected = response.profileSelected
                let warning = response.warningText
                self.warning = warning.isEmpty ? nil : warning
                RKMLog.info("profiles: \(self.profiles.count) profile(s),"
                                + " selected=\(response.profileSelected)"
                                + (warning.isEmpty ? "" : ", warning: \(warning)"),
                            category: .auth, correlation: correlation)
                return true
            } catch {
                self.error = (error as? APIError)?.errorDescription ?? String(describing: error)
                return false
            }
        }
    }

    /// `POST /api/auth/profile` — the whole of "who is watching".
    ///
    /// ⚠ `password` is that profile's OWN password: optional for a password-less profile, **required for
    /// the administrator's own profile** so a shared device cannot walk into it. The rule is enforced
    /// SERVER-side (`api/session.py`); the client only decides when to ask.
    func select(_ profile: ProfileUser, password: String,
                correlation: CorrelationID = .next()) async -> Bool {
        error = nil
        return await withBusy {
            do {
                let response: SelectProfileResponse = try await self.client.post(
                    "api/auth/profile",
                    body: SelectProfileRequest(userID: profile.id, password: password),
                    correlation: correlation
                )
                RKMLog.info("selected profile \(profile.name) ok=\(response.ok)", category: .auth,
                            correlation: correlation)
                // ⚠ Again: the server's answer decides. If the selection did not take, `/me` says so.
                return await self.refreshSession(correlation: correlation)
            } catch {
                self.error = (error as? APIError)?.errorDescription ?? String(describing: error)
                RKMLog.error("profile switch failed: \(self.error ?? "")", category: .auth,
                             correlation: correlation)
                return false
            }
        }
    }

    /// `POST /api/auth/logout` — ⚠ a `204`, so it is sent through the no-body path.
    ///
    /// ⚠ The cookie store is also wiped HERE, deliberately, rather than trusting the server's deletion
    /// `Set-Cookie` to have landed: a sign-out that leaves a live session cookie behind means the next
    /// person at the TV is still signed in, and the app would look like it lied.
    func signOut(correlation: CorrelationID = .next()) async {
        await withBusy {
            do {
                try await self.client.postIgnoringBody("api/auth/logout", correlation: correlation)
                RKMLog.info("signed out", category: .auth, correlation: correlation)
            } catch {
                RKMLog.error("sign-out request failed: \((error as? APIError)?.errorDescription ?? "\(error)")",
                             category: .auth, correlation: correlation)
            }
            self.clearCookies(reason: "sign-out")
            self.signedInUser = nil
            self.currentProfile = nil
            self.profileSelected = false
            self.profiles = []
            self.warning = nil
            self.error = nil
        }
    }

    // MARK: - Internals

    /// Run `work` with `busy` true for exactly its duration.
    ///
    /// ⚠ One helper rather than five `busy = true` / `busy = false` pairs: the failure mode this prevents
    /// is a spinner left running on a TV because one early-return path forgot to clear it, and that reads
    /// as a hung app. `defer` is what makes it true on every path, including the throwing ones.
    ///
    /// ⚠ Not `@MainActor`, matching the iOS app's convention: `URLSession`'s async results and SwiftUI's
    /// actions arrive on the main thread, and marking this class isolated would force `@preconcurrency`
    /// conformances whose syntax depends on the language mode his Xcode picks. The main-thread discipline
    /// is real; the compiler-version dependency is not worth a build failure that cannot be reproduced here.
    private func withBusy<T>(_ work: () async -> T) async -> T {
        busy = true
        defer { busy = false }
        return await work()
    }

    /// ⚠ Called when a NEW interaction starts, so the message on screen always belongs to the attempt
    /// being made now — a stale "wrong password" beside a fresh password field is a bug that reads as a
    /// rejected password.
    func clearError() {
        error = nil
    }

    /// `GET /api/auth/me` again, for state the app has just changed. Returns false on 401 — which is a
    /// legitimate answer, not an error, so it does not set `error`.
    private func refreshSession(correlation: CorrelationID) async -> Bool {
        do {
            let me: MeResponse = try await client.get("api/auth/me", correlation: correlation)
            apply(me)
            return true
        } catch let error as APIError {
            if error.isUnauthorized {
                signedInUser = nil
                currentProfile = nil
                profileSelected = false
                return false
            }
            self.error = error.errorDescription
            return false
        } catch {
            self.error = String(describing: error)
            return false
        }
    }

    private func apply(_ me: MeResponse) {
        signedInUser = me.user
        currentProfile = me.profile
        onOwnProfile = me.onOwnProfile
        profileSelected = me.profileSelected
        // ⚠ Worth its own line: `on_own_profile == false` means the session is acting as a profile that
        // is NOT the signed-in user. That is the state the server's whole identity seam exists to protect,
        // and a log line is how it is proved rather than assumed.
        RKMLog.info("session: user=\(me.user?.name ?? "?")"
                        + " profile=\(me.profile?.name ?? "none")"
                        + " onOwnProfile=\(me.onOwnProfile) selected=\(me.profileSelected)",
                    category: .auth)
    }

    /// ⚠ **Cookie NAMES only, never values** — `LogRedactor.redact(cookieNames:)` is the one place that
    /// decides what is safe to print, and `apple/LOGGING.md` §6 makes
    /// `grep -iE "password|token|api_key|rkm_session"` over a real run an acceptance gate. This line is
    /// how "the cookie never arrived" is told apart from "the cookie arrived and was refused".
    private func logCookieState(_ what: String) {
        let names = HTTPCookieStorage.shared.cookies?.map(\.name) ?? []
        let hasSession = names.contains(Self.sessionCookieName)
        RKMLog.info("\(what): session cookie \(hasSession ? "present" : "ABSENT") —"
                        + " \(LogRedactor.redact(cookieNames: names))",
                    category: .auth)
    }

    private func clearCookies(reason: String) {
        let storage = HTTPCookieStorage.shared
        guard let ours = ServerAddressHost.normalise(address.host) else { return }
        var removed = 0
        // ⚠ Matched by HOST, not by name: deleting every cookie called `rkm_session` in the store would
        // also sign the app out of a second server he may have added later.
        for cookie in storage.cookies ?? [] {
            guard let host = ServerAddressHost.normalise(cookie.domain), host == ours else { continue }
            storage.deleteCookie(cookie)
            removed += 1
        }
        RKMLog.info("cleared \(removed) cookie(s) for \(ours) (\(reason))", category: .auth)
    }
}

/// ⚠ A cookie's `domain` may carry a leading dot for a domain cookie and the address's host does not, so
/// the two cannot be compared raw.
enum ServerAddressHost {
    static func normalise(_ host: String) -> String? {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let withoutDot = trimmed.hasPrefix(".") ? String(trimmed.dropFirst()) : trimmed
        return withoutDot.isEmpty ? nil : withoutDot
    }
}
