# Plex-style profile authentication — server login, profile selection, per-profile state

**Status:** SCOPED 2026-09-12 (nothing built yet). Supersedes the *login model* of
`AUTH_MULTIUSER_PLAN.md`; reuses its plumbing (sessions, `/api/auth/*`, the contextvar seam) and
all of `HOUSEHOLD_USERS_PLAN.md` (account create/grant/disable/reset/delete — already shipped).

## 1. What changes, in one paragraph

Today each household member signs in with **their own Jellyfin username and password** at the app's
login screen. The user wants the **Plex Home** model instead: **one** credential opens the server
(the administrator's), and everybody else arrives by picking a **profile** — optionally protected by
a password. Profiles are still Jellyfin users underneath (that is where watch state, resume, watched
flags, history and library grants live), so nothing about *where* the per-person state lives changes:
what changes is **how a person gets to it**, and who is allowed to touch the server directly.

    Server login (administrator only)  →  Profile selection  →  that profile's media experience

## 2. Measured facts this design rests on (live, Jellyfin 10.11.11, 2026-09-12)

| Fact | Evidence |
|---|---|
| **There is NO impersonation.** A token for a user comes only from `POST /Users/AuthenticateByName` (username + password) or `AuthenticateWithQuickConnect`. `/Auth/Keys` mints server-wide keys, not per-user ones | server's own `/api-docs/openapi.json`: the only user-scoped auth path is `AuthenticateByName` |
| **Consequence:** the app cannot act as a password-protected profile without its password. The administrator can **reset** it (`POST /Users/Password?userId=`, `ResetPassword: true`) but cannot bypass it | same; reset is already implemented (`admin_users.py`) |
| A password-less account authenticates with a **blank** password (the user's chosen model for members) | verified for the admin account 2026-09-12 (`check_login_flow.py` scenario D, and the live login proof) |
| `UpdateUserPassword {CurrentPassword, CurrentPw, NewPw, ResetPassword}` | self-change = `CurrentPw` + `NewPw`; admin reset = `ResetPassword: true`. Both natively supported |
| `UserDto`: `Name`, `HasPassword`, `IsDisabled` (via `Policy`), `LastLoginDate`, `LastActivityDate`, `PrimaryImageTag` | rename via `POST /Users?userId=`, and the picker has what it needs to show a lock/last-seen |
| `UserPolicy`: `EnabledFolders`, `EnableAllFolders`, `BlockedMediaFolders`, `IsDisabled`, `MaxActiveSessions`, `EnableRemoteAccess`, `EnableMediaPlayback` | every per-profile control requested is enforced **by Jellyfin**, server-side |
| Per-user libraries: `GET /UserViews?userId=` | `GET /Users/{id}/Views` answers but is NOT in the contract — never depend on it |

## 3. The model

**Two kinds of session, one cookie.** The session record grows a *profile* alongside the account that
authenticated:

| Field | Meaning |
|---|---|
| `owner_user_id` / `owner_token` | the account that **signed in to the server** — always an administrator (see §4) |
| `profile_user_id` / `profile_token` | the **selected profile** — the Jellyfin identity every media call is made as |
| `expires`, `last_seen`, `created` | unchanged (sliding 30-day, `0600`, `/data/rkm/sessions.json`, survives restarts) |

* The **admin profile** is a profile like any other: selecting it sets `profile_* = owner_*`, so the
  administrator browses as themselves with everything visible.
* **Media calls run as `profile_token`.** That single change is what turns folder grants (and each
  person's Continue Watching / resume / watched / history) from *cosmetic* into *enforced* — the
  contextvar seam from `AUTH_MULTIUSER_PLAN` Phase 0 was built for exactly this.
* **Administrative calls require the owner to be an administrator AND the admin profile to be
  selected** (§4.3). A kid's profile on the family iPad therefore cannot reach the Household screen
  even though the device holds the admin's login.

## 4. Routes (additive; contract 49 → ~54 paths)

| Route | Who | What |
|---|---|---|
| `POST /api/auth/login` | anyone | **administrator accounts only** — a non-admin credential is refused (§6 decision 2). Unchanged otherwise |
| `GET /api/auth/profiles` | server session | the selectable profiles: `{id, name, has_password, disabled, is_admin, last_login}` |
| `POST /api/auth/profile` | server session | `{user_id, password?}` → authenticates to Jellyfin AS that profile → stores `profile_*` → returns the profile **and its own libraries** |
| `DELETE /api/auth/profile` | server session | switch back to the admin profile; **requires the admin's password** (§4.3) |
| `POST /api/auth/profile/password` | profile session | the profile changes **its own** password: `CurrentPw` + `NewPw` |
| `POST /api/admin/users/{id}/rename` | admin profile | `{name}` → `POST /Users?userId=` |
| `GET /api/auth/me` | any session | gains `profile` (+ keeps `user`), so the UI always knows which profile it is |

Everything from `HOUSEHOLD_USERS_PLAN.md` stays as-is: create, folder grant, enable/disable, set &
reset password, delete, typed-name confirmation, last-admin rail.

### 4a. As built (amended 2026-09-12, measured)

Phase A shipped the FIRST TWO routes above and nothing more: `GET /api/auth/profiles` and
`POST /api/auth/profile` (contract **49 → 51**, purely additive). Rows in the table above that do
**not** exist yet, so the next session does not go looking for them:

* **`DELETE /api/auth/profile`** — not built, and not needed: "switch back to the administrator" is
  `POST /api/auth/profile` with the administrator's profile id and their password, which §4.3
  requires anyway. A second verb would carry the same check and earn nothing.
* **`POST /api/auth/profile/password`** — not built; the profile changing its OWN password is
  Phase D's screen (§7), which is the phase that owns password UX.
* **`POST /api/admin/users/{id}/rename`** — not built; also Phase D (`POST /Users?userId=`).

### 4b. Why Phase B needed a backend field after all (this plan said it would not)

The §7 table called Phase B "frontend:". **That was wrong**, and here is the measurement that shows
it: `SessionContext.profile_id()` deliberately falls back to the OWNER, so a fresh sign-in (nobody
chosen yet) and "the administrator chose themselves" produce an **identical** `me()` payload —
`profile` is the administrator either way, and `on_own_profile` is `true` in both. The picker's
trigger therefore cannot be derived from anything the api was already sending.

`me()` and `/api/auth/profiles` now report **`profile_selected`** (additive: +10/−0, still 51 paths),
read straight off the session record. **Rejected alternative:** remember the click in the browser
(sessionStorage). The session lasts 30 days, is shared by every tab and every device, and §6
decision 4 says the choice must survive a restart — a locally-remembered answer would disagree with
the server after a reload or on the phone. A UI-only rule deciding who has access to the app is the
one thing this workstream exists to avoid.

### 4c. What the picker costs the administrator (honest — and it IS decision 3)

Because a blank attempt on the administrator's profile is always refused, the administrator types
their password **twice** on a fresh sign-in: once to open the server, then again to select their own
profile. That was left exactly as decided. Allowing a blank attempt while no profile is chosen would
hand that profile to anyone who walks up to a device where the administrator has just signed in —
the precise hole §4.3 exists to close. If the double prompt ever becomes unwanted, the change belongs
in the RULE as a new user decision, **never** in the UI.

### 4d. Phase C — the enforcement, as MEASURED (2026-09-12, live Jellyfin 10.11.11)

Measured against the live server with TWO REAL accounts — `admin` (administrator, all folders) and
`Geetanjali` (non-administrator, no password, granted **`Movies` only**) — by minting one session
token per account on its **own** device id (Jellyfin rotates a device's token on every login).
Every number below is from that run; the tool that proves it is `tools/prove_profile_isolation.py`.

| Call | as the ADMINISTRATOR's own token | as the PROFILE's token |
|---|---|---|
| `GET /Library/VirtualFolders` | 3 libraries (`Movies`, `TV Shows`, `Movies Kids`) | **403** (needs elevation) |
| `GET /UserViews?userId=<id>` | 3 | **1** (`Movies`) |
| `GET /Users/{uid}/Items?IncludeItemTypes=Series` | 115 | **0** |
| `GET /Users/{uid}/Items?IncludeItemTypes=Movie` | 853 | 713 |
| `GET /Users/{uid}/Items/{tvId}` (item_detail / item_path / item_similar / _user_state) | 200 | **404** |
| `GET /Items/{tvId}/Images/Primary` (poster) | 200 | **404** |
| `POST /Items/{tvId}/PlaybackInfo` | 200 | **404** |
| `GET /Items/{tvId}/Ancestors?userId=` | `['TV Shows', 'Media Folders']` | **404** |
| write a resume position as ONE profile | — | appears in **that** profile's `/Items/Resume` only; the other profile's Resume is unchanged (and a position-0 write removes it again) |

**Four consequences — three of them contradict what this plan assumed.** They are recorded so the
next session does not "fix" a non-problem or re-open a settled one:

1. **§7's Phase C acceptance claim is CONFIRMED — through the app's OWN URL shapes, and it needs no
   app-level guard.** ⚠ But the same server DOES answer two OTHER forms **unfiltered**:
   `/Users/{uid}/Items?Ids=<id>` returned the non-granted TV series (200, `Items[1]`), and
   `/Items/{id}?userId=<uid>` answered for it too. The app builds **neither** form. So: never
   "harden" this by adding a membership check (unnecessary), and never switch a provider call to an
   `Ids=` list query or a bare `/Items/{id}` (that would silently hand a member anything whose id
   they know — the leak this plan exists to prevent).
2. **`library_folders()` cannot read `/Library/VirtualFolders` while somebody else's profile is in
   session — it is 403.** A profile's libraries therefore come from **its own
   `/UserViews?userId=`**, and the app keeps the administrator's own profile on `VirtualFolders`
   exactly as today (that call IS elevated for the administrator's session token — measured, see
   row 1). The owner/profile distinction is the session's own fact (`on_own_profile()`), not a guess.
3. **`/UserViews` rows carry NO `CollectionType`** (the row's `Type` is `CollectionFolder`, and the
   only path it reports is Jellyfin-internal, `/config/root/default/Movies`). The profile's views are
   therefore ENRICHED — id → `collection_type` + `path` — from the administrator's folder list, which
   is metadata the app already holds (it is what `.env`'s `MEDIA_LIBRARY_N_PATH` is matched against)
   and which is then **filtered down to the profile's own views** before anything is returned. Without
   the enrichment the sidebar loses its per-library icon and `/library/<kind>` loses its redirect
   target, for members only — a silent, cosmetic-only regression.
4. **The seam had to be ARMED: `require_session` was referenced by no route at all**, so no media
   route published the session contextvar and the provider could not have seen a profile even with
   the threading in place. Phase C adds it as a **router-level dependency** on every app router
   (`/api/health` and `/api/auth/*` excepted — the healthcheck and the sign-in must stay public),
   which is ONE line per router instead of a `Depends` on ~40 endpoints.

### 4.3 The shared-device rule (recommended, decision 3)
The device holds the administrator's session, so "anyone can walk up and administer" is the real risk
of this model — Plex's answer is a PIN on the Home admin, and the backend equivalent is: **admin
routes and the switch back to the admin profile require the administrator's password while a
non-administrator profile is selected.** Enforced in `require_admin_session`, not in the UI.

## 5. What is already built vs what this adds

| Requirement | State |
|---|---|
| Sessions persist across restarts, `0600`, opaque cookie, `sha256(id)` only | ✅ Phase 0 |
| Login / logout / who-am-I | ✅ Phase 0–1 |
| **Administrator-only server login** | ➕ this (one guard in `POST /api/auth/login`) |
| Profile list + selection + optional password prompt | ➕ this |
| Admin: create, delete, folders, enable/disable, set/reset password, last-admin rail | ✅ Phase 1b |
| Admin: **rename** | ➕ this (`POST /Users?userId=`) |
| Profile: change own password | ➕ this (native, requires the old one) |
| **Per-profile watch state / resume / watched / history** | ⚠ Jellyfin already stores it per user — the app just is not asking as that user yet. **This is the identity threading, and it is the whole ballgame** |
| Per-profile libraries (server-enforced) | ⚠ same: real the moment calls run as the profile |
| Password-less profile + tailnet = anyone who can reach the app can pick that profile | ⚠ honest consequence; PIN-protect anything that matters |
| Watchlist (acquisition queue) stays **shared** | unchanged, deliberate (user decision 2026-09-12) |

## 6. Decisions (all recommended options are what I will build unless told otherwise)

1. **A profile's password IS its Jellyfin user password** — no app-owned PIN store. One credential
   system, admin set/reset already works, and the same password keeps working in Jellyfin's own
   apps. (Alternative: an app PIN store — a second password system to secure and migrate, rejected.)
2. **`POST /api/auth/login` refuses non-administrator accounts.** "Only the admin can log in" is then
   backend-true rather than merely absent from the UI. Members reach the app only via profile
   selection inside the administrator's session.
3. **While a non-admin profile is selected, admin routes are refused and switching back to the admin
   profile needs the administrator's password.** This is the only thing that stops a shared device
   from handing every guest full server control.
4. **The selected profile persists per browser** (same 30-day session), so a restart keeps a person on
   their own profile; "Switch profile" is always available and the admin can always sign in again at
   `/login`.

## 7. Phases (one sitting each, one commit each, gates green every time)

| Phase | Content | Gate |
|---|---|---|
| **A** | backend: admin-only login, profile list/select/clear, profile self-password, session record grows `owner`/`profile`, rename, `me` gains `profile`; tests for every refusal (non-admin login, wrong/blank profile password, disabled profile, admin route with a non-admin profile selected, switch-back requires the password) | pytest, ruff, contract snapshot + typed client |
| **B** | frontend: "Who's watching?" picker (lock badge, disabled greyed, password prompt), header profile switcher, guard sends a server session with no profile to the picker; browser check `tools/check_profile_picker.py` — **plus ONE additive backend field** (`profile_selected` on `me()`/`profiles()`, see §4b: this row used to claim B was frontend-only, and that was wrong) | tsc, vitest, build, DOM check |
| **C** | **identity threading — the enforcement:** provider `_token()` prefers `profile_token`; every media/progress/resume/watched/subtitle/stream call goes out as the profile; sidebar libraries come from that profile's `/UserViews`; **live proof with two real profiles that their state and libraries do not leak into each other** | pytest (+ a test per route family), frontend, live two-profile proof |
| **D** | admin extras in `Settings → Household`: rename, "has password" state, and the profile's own "change my password" screen | gates + DOM check |
| **E** | enforcement sweep (401/403 for every router; a profile cannot reach admin routes), ADR-0006, docs (`ARCHITECTURE`, `OPERATIONS`, `README`), PROGRESS record | full suite + docs links |

Arming `RKM_AUTH_REQUIRED` stays **his** switch (decision of 2026-09-12): the model above works with
it off (everyone can still browse as the admin), and becomes *true* — profile required to browse —
when he arms it. **Phase C is what makes folder access real; until then, grants are display only.
Say that plainly whenever the screens are described.**

## 8. Risks

1. **Identity threading is the riskiest change in the whole workstream** (21 `api_key=` sites, 18
   `build_library_service` call sites). Mitigated by the Phase 0 contextvar seam — one diff point —
   plus a test per route family and the two-profile live proof. A missed site silently shows the
   administrator's data to a member.
2. **A stale profile token** (Jellyfin rotates a device's token on every login of that device) must
   degrade to "switch profile again", never to a 500.
3. **Shared-device administration** — answered by 4.3; without it the model is a privilege-escalation
   hole dressed as convenience.
4. **Lockout**: the administrator can always reach `/login` with the admin credential from `.env`;
   the escape hatch (`RKM_AUTH_REQUIRED=false` + `--force-recreate api`) is unchanged.
5. **Profile state is Jellyfin's**, so deleting a profile deletes their history with it (Jellyfin's own
   cascade) — same as today, now with a UI that makes it obvious.

## 9. Verification

```bash
python3 tools/diag_household_gate.py          # the admin path, one command
cd backend && python -m pytest -q && python -m ruff check .
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
python3 backend/scripts/snapshot_openapi.py   # 49 -> ~54 paths as phases land

# The picker itself (Phase B) — six scenarios over the REAL ProfilesView, no api needed:
cd frontend && npx vite --port 5199 --strictPort &
python3 tools/check_profile_picker.py
python3 tools/check_login_flow.py             # sign-in -> picker -> app, and the enforced world
```
⚠ Restart that vite after ANY source edit and confirm the SERVED module is the edited one
(`curl -s localhost:5199/src/features/profiles/ProfilesView.tsx | grep -c profile-picker`) — a
stale module on this mount has produced both false FAILs and false PASSes in this repo's history.
