# ADR-0006: Identity is delegated to Jellyfin; the app owns sessions, not accounts

- **Status:** Accepted
- **Date:** 2026-09-13
- **Phase:** `feat/auth-multiuser` → `feat/phase-5-taxonomy-and-docs` (`AUTH_MULTIUSER_PLAN.md`, phases 0–5; supersedes nothing)

## Context

Until 2026-09-12 this app had **no identity at all**. Every request — signed out or not, from anyone
who could reach nginx on the tailnet — was served as the stack's own credential, which is an
administrator's credential. Browsing, playback, watch state, acquisitions, everything. The app was
private in the sense that the *network* was private; it had no authorisation of its own.

Two needs made that untenable, and they arrived in this order:

1. **A household, not a person.** The requirement was per-person Continue Watching and per-person
   subtitle choices on a shared device (a TV browser), with the *shared* things — the acquisition
   queue, one download quota — deliberately staying shared.
2. **"The media is still readable after logout."** Once members exist, "anyone who can reach it is
   the administrator" stops being a convenience and becomes the hole.

**This is a BREAKING contract change** in ADR-0001's sense, which is the reason this ADR exists: every
app path now requires a session, and a client that worked before will not work without one.

Nine measurements shaped the decision. All were taken against the live bundled Jellyfin 10.11.11
before (or instead of) writing code:

| # | Measured | Consequence |
|---|---|---|
| 1 | Jellyfin has **no impersonation** — the only user-scoped token endpoint is `/Users/AuthenticateByName` | "acting as a profile" must mean *authenticating as that profile* |
| 2 | Jellyfin **invalidates the previous token of a `(device, user)` pair on every login** | one device id per login, per session — or sessions rotate each other's tokens (§4e) |
| 3 | A member's token gets **403 from `/Library/VirtualFolders`** (elevation) but a correctly-scoped `/UserViews?userId=` returns that member's own libraries | a member's sidebar is built from *their* views, never the server's library list |
| 4 | A user's token may read **its own** `/Users/{id}` (200) but not another account's | the app can ask "is this credential still accepted?" cheaply, as the acting identity |
| 5 | `/Users/{id}` with `Authorization: <token>` answers **401**; `?api_key=<token>` answers **200** | the credential *style* is load-bearing (Phase 5's probe pins it) |
| 6 | A password change answers **403** for a wrong `CurrentPw` and **401** for a token the server no longer accepts | 401 ≠ 403: a stale sign-in must not be reported as a wrong password |
| 7 | `ResetPassword: true` answers **204 while storing nothing** (it *clears* a password) | the app never uses that flag, and proves a change by signing in |
| 8 | Jellyfin's activity log and session list are per **device id**, and a token that is not revoked stays live | the app revokes what it does not use, and gives tools their own device |
| 9 | `/Sessions/Logout` with `Authorization: <token>` answers **401** (measured 2026-09-13) | ⚠ `revoke_jellyfin_session` has probably never revoked anything. Best-effort by contract; recorded, not fixed here |

## Decision

**Identity is delegated. Jellyfin owns accounts, passwords and privileges; the app owns only
sessions, and one profile concept on top of them.**

* **The browser holds ONE opaque session id**, in an `HttpOnly`, `SameSite=Lax` cookie with no
  `Secure` (the tailnet is plain http and Tailscale encrypts transport; `Secure` here would silently
  break sign-in). It is stored server-side **as a sha256** — a leaked store file yields no usable
  session, and logout is a real revocation because the row is deleted.
* **The Jellyfin access token never leaves the server.** It is never in a cookie, a response body, a
  log line, or `records()`.
* **ONE administrator signs in to the server.** Everyone else reaches the app by selecting a
  **profile** inside that session. A member cannot open a session of their own, and that is enforced
  server-side (403 at `/api/auth/login`), not by hiding a form.
* **A profile switch re-authenticates as that profile** (there is no impersonation): blank password
  for a password-less profile, its own password otherwise. Selecting the **administrator's own**
  profile always requires the administrator's password — the shared-device rule that stops a guest
  walking into server administration.
* **One dependency publishes the identity per request.** `api/main.py` applies
  `require_live_credential` to every app router (ONE line each, never a `Depends` on ~40 endpoints:
  a site that forgot it would keep serving one person's library to another). It sets a contextvar
  that the provider reads, so **no request context means today's behaviour** — the provisioner, the
  scheduler's jobs, the tools and the unit tests keep acting as the app's own key.
* **The rail.** A request that RESOLVED a session and then published nothing does not fall back to
  the app's key; it raises `UnpublishedIdentityError`. That fallback wrote a password to the wrong
  account once (2026-09-12) while reporting success.
* **The switch.** `RKM_AUTH_REQUIRED` (default `false`) decides whether a missing session is a 401 or
  an anonymous request. `.\\rkm-cinema.ps1 auth on|off` sets, applies and **proves** it. The escape
  hatch is the reason the phases shipped in this order: the login UI existed before anything was
  enforced.
* **Two 401s, two answers (Phase 5).** A cookie that is gone means *sign in again*. A cookie that is
  fine while the credential the app is **acting as** was refused means *pick the profile again*, and
  is reported as `401` + `X-RKM-Auth-Problem: profile-token` so the browser does not sign a live
  session out over it.
* **One device id per session (Phase 5).** Each sign-in gets its own `rkm-cinema-web-<hex>`; a
  profile switch stays on it. Callers that name a device (the operation tools, `rkm-tools`) keep
  theirs, which is what stops a diagnostic from rotating the browser's token away.

## Rejected alternatives

| Option | Why not |
|---|---|
| **A shared household password** | No per-person identity, so no per-person Continue Watching or subtitle choices — it fails requirement 1 while satisfying requirement 2. It also makes every action unattributable |
| **App-owned accounts** (its own password store) | A second credential store to hash, reset, migrate and secure; drift from Jellyfin the moment somebody changes a password there, and a second lockout story. Delegation keeps ONE owner of identity |
| **An IP / localhost bypass for the repo's tooling** | Spoofable in principle, and unnecessary: the tools sign in properly as the administrator on their own device id. A bypass is also the kind of "temporary" rule that silently outlives its reason |
| **Remembering the chosen profile in the browser** (sessionStorage) | The session lasts 30 days and is shared by every tab and device; a locally-remembered answer would disagree with the server after a reload, a second tab, or on the phone. A UI-only rule deciding who has access is the one thing this workstream exists to avoid |
| **The Jellyfin token in the cookie** | Puts a long-lived media-server credential in the one place an XSS can read it, and makes logout unprovable |
| **A machine token (`X-RKM-Token`) for the tools** (planned in Phase 2, never built) | Superseded by the same reasoning as the bypass: the tools sign in as the administrator, on a device of their own, using credentials that already exist in `.env`. `.env.example` therefore documents no `RKM_API_TOKEN`, and `RKM_CORS_ORIGINS` was never needed either — production is one origin through nginx, and the Vite dev server proxies `/api` |

## Consequences

* **Every non-browser caller signs in**: the operation tools do it themselves (`tools/rkm_common.py`,
  device `rkm-tools`); the Jellyfin-direct probes, the scheduler and the provisioner never call the
  app over HTTP, so they need nothing.
* **`GET /api/health` and the six `/api/auth/*` routes stay reachable signed out** — the Docker
  HEALTHCHECK calls the first (a 401 there marks the api unhealthy and cascades), and the second are
  sign-in itself, which must be reachable *and* is the fix for a refused credential.
* **A new router must use the ONE session dependency**, or the 401 taxonomy is decorative on that
  route. `tests/test_route_protection.py` fails if it does not.
* **A new cache must be keyed by user** — a provider cache added later would serve one person's items
  to another.
* **Names are not re-read per request.** The session stores the name it was handed; a rename is
  followed for the session that made the change and corrected on the next profile selection
  elsewhere. A token, unlike a name, must never be stale — which is what Phase 5's probe is for.
* **Honest limits.** (a) The switch is a single flag: `auth off` is a full return to the old world,
  by design, because a lockout with no way back is worse than a permissive default. (b) The
  stale-credential probe costs one extra media-server call per session per 20 seconds while it is
  cached; a refusal is reported within that window, not instantly. (c) This app still owns no
  password reset: a forgotten member password is reset by the administrator (Household) and a
  forgotten administrator password by `.\\rkm-cinema.ps1 reset-admin-password`.

## See also

* `AUTH_MULTIUSER_PLAN.md` — the phase plan, the lockout rule, and the traps.
* `PLEX_PROFILE_AUTH_PLAN.md` — the profile model, the shared-device rule (§4.3) and the §4e bug the
  live proof found.
* `ADMIN_CREDENTIALS_PLAN.md` §6f (the rail), §6h (the 401 taxonomy), §6j (route protection), §6k
  (why the tools sign in on their own device).
* `ARCHITECTURE.md` §11 — the same model, as built.
