# Plan: household accounts from inside the app (create / scope / manage Jellyfin users)

**Status: SCOPED 2026-09-12, NOT STARTED.** Continues on branch `feat/auth-multiuser`
(this is the auth workstream: `AUTH_MULTIUSER_PLAN.md` §6 Phase 5 lists an *optional*
"add Jellyfin user" flow — the user asked for it explicitly, so it is promoted to a real
phase here). ONE branch, ONE merge at the end.

**Why it moved forward in the order.** Phase 3's live proof needs a SECOND Jellyfin user
to exist, and the user's instruction was *"I WANT TO DO IT FROM THE UI, CREATING NEW USER
AND STUFF"* — he wants to add the household member from the app rather than the Jellyfin
dashboard. Building this first unblocks Phase 3 with his own click-through as the test.

---

## 1. What this delivers

A **Settings → Household** screen, visible to a Jellyfin **administrator**, where he can:

| Action | Result |
|---|---|
| See the household | every account: name, admin?, disabled?, **which libraries it can see**, last login |
| **Add a member** | name + password + library tick-boxes ⇒ creates the Jellyfin user AND grants exactly those libraries |
| Change access | re-tick libraries (read-modify-write the policy), enable/disable an account |
| Reset a password | for a member who forgot theirs |
| Remove a member | typed confirmation; irreversible |

It is a **front end for Jellyfin's own user management** — the app still owns no accounts,
no password store and no password reset flow of its own.

## 2. Measured facts (live, 2026-09-12 — `python3 tools/probe_jellyfin_users.py`)

The read-only probe ships with this plan. Its output on the real server:

- **3 libraries**, and their ids are what a grant refers to:
  `Movies` → `f137a2dd21bbc1b99aa5c0f6bf02a805` (`/data/Movies`),
  `TV Shows` → `767bffe4f11c93ef34b805451a696a4e` (`/media2/TV Shows`),
  `Movies Kids` → `7e9b296eea8d39a9f2e5c88d147d0df3` (`/data/Movies Kids`)
- **1 user**: `admin` (`1760c9b047d444d39c94a99d082773ed`), administrator, `EnableAllFolders=true`
  ⇒ `sees: ALL`; `/Views` → `['Movies', 'Movies Kids', 'TV Shows']`

The endpoints, read from the RUNNING server's own `/api-docs/openapi.json` (315 paths) —
not from the docs, which is what settled the subtitle upload shape too:

| Endpoint | Shape (measured) |
|---|---|
| `POST /Users/New` | body `CreateUserByName {Name, Password}` → creates the account |
| `POST /Users/{userId}/Policy` | body **`UserPolicy` (47 fields) — the WHOLE policy is replaced** |
| `POST /Users/Password?userId=<id>` | body `UpdateUserPassword {CurrentPassword, CurrentPw, NewPw, ResetPassword}` — **the target is a QUERY param** |
| `POST /Users?userId=<id>` | body `UserDto` (rename, etc.) |
| `GET /Users/{userId}` / `DELETE /Users/{userId}` | read / delete one account |
| `GET /Users` | list accounts (admin only) |
| `GET /UserViews?userId=<id>` | the libraries THAT user can see |

⚠ `GET /Users/{userId}/Views` **still answers today but is NOT in the server's own
contract**, so the app must read `/UserViews?userId=`. (The probe prints a loud
`NOT in this server's contract` line for exactly this class of trap.)

## 3. Design

**Routes (additive, `backend/api/routes/admin_users.py`):**

```
GET    /api/admin/users                    # the household (no secrets in the payload)
GET    /api/admin/libraries                # grantable libraries (id + name + type)
POST   /api/admin/users                    # {name, password, library_ids[]} -> creates + grants
POST   /api/admin/users/{id}/policy        # {library_ids[], disabled?} -> read-modify-write
POST   /api/admin/users/{id}/password      # {new_password, reset: true}
DELETE /api/admin/users/{id}
```

Provider work: `JellyfinLibraryProvider` gains `list_users`, `list_libraries`,
`create_user`, `user_policy`, `set_user_policy`, `set_user_password`, `delete_user`
(+ the same on `services/library/service.py`'s ABC, since `build_library_service()`
returns that interface). Every call goes through the provider, so it inherits the
Phase 3 `_token()` rule for free.

**Authorization — checked LIVE, per request, against Jellyfin.** `GET /Users/{session.user_id}`
⇒ `Policy.IsAdministrator`. No stored `is_admin` flag is trusted for authorization: a stale
flag is an authorization bug, and this app's rule is that the media server's own state is
authoritative. (A stored flag may be used as a UI *hint* only, and must be labelled as one.)

**These routes are session-STRICT from day one, independent of `RKM_AUTH_REQUIRED`.**
They can create accounts, so they must never answer an anonymous caller even while the rest
of the app is deliberately unenforced — the same rule `/api/auth/me` already follows. So:
`require_session` (401 without a session) + `require_admin` (403 for a non-admin, checked
live). Enforcement of the REST of the app (Phase 2) does not gate this feature.

**Tokens:** the calls are made **as the signed-in administrator** — never with the app's
admin token. That keeps Jellyfin's own log attributable ("who created this account") and
leaves Jellyfin's own 403 as the backstop if our check is ever wrong.

**Secrets:** the password is used ONCE and passed straight to Jellyfin. It is never stored,
never logged and never returned — tests assert no response body and no log record contains
it (the same shape as the auth Phase 0 test).

**UI:** `frontend/src/features/admin/HouseholdView.tsx` + pure helpers with unit tests, an
entry in the header/settings that renders only for an admin (the server still enforces it),
and a DOM check tool `tools/check_household_ui.py` (Playwright, mirrors
`check_subtitle_panel.py`) proving the list renders, the add form posts the right body, and
a non-admin never sees the entry.

## 4. Phases — ✅ **ALL THREE DONE 2026-09-12**

| Phase | Content | Gate |
|---|---|---|
| **1b.0** ✅ | provider methods + routes + strict session/admin gating, tests against a FAKE transport (no real user is created in the suite), contract snapshot + typed client | pytest, ruff, tsc, vitest, build |
| **1b.1** ✅ | the Household UI + pure-helper tests + `tools/check_household_ui.py` | tsc, vitest, build, DOM check |
| **1b.2** ✅ | docs + the record | docs links, then the record |

**Acceptance (his, on RKM-HP):** he signs in as `admin`, adds a household member from the
app — **with no password** (his decision, §8.1) — and a chosen set of libraries, that member
then signs in with just their username, sees ONLY those libraries, and creates their own
Continue Watching. That member is what Phase 3's two-account live proof uses.

## 4a. As built (2026-09-12) — what the code actually does

Five new additive paths (`/api/admin/users` GET+POST, `/api/admin/libraries`,
`/api/admin/users/{user_id}/policy`, `/api/admin/users/{user_id}/password`,
`/api/admin/users/{user_id}` DELETE): **contract 44 → 49 paths, +300/−0**; typed client **+358/−0**.

1. **The gate is `require_admin_session`** (`api/session.py`): a session **plus** a LIVE
   `IsAdministrator` AND-not-disabled check asked of the server on **every call** — never a cached
   flag. It is strict even while `RKM_AUTH_REQUIRED=false` (`api/routes/admin_users.py` docstring
   says why: these routes create and delete accounts).
   ⚠ **Honest limitation:** in 1b these calls go out on the app's **admin** credential, because
   per-request identity is Phase 3. So the route's own check is the only gate right now; Jellyfin's
   own 403 becomes the backstop only once Phase 3 makes the calls as the signed-in user.
2. **Read-modify-write only.** `mutate_user_policy()` reads, mutates, posts the WHOLE policy —
   pinned by a test that asserts a field the request never mentioned survives the write.
3. **A password-less member is a first-class case.** `POST /Users/New` omits `Password` entirely
   when the admin leaves the field blank (a blank string is a different thing to sending none).
4. **The DELETE carries its confirmation in the body** (`confirm_name`) — the name must be typed
   out; the server checks it too.
5. **The last-administrator rail is a BACKSTOP, not a live path**, and the route says so. Because
   the gate guarantees the caller is an enabled administrator, any non-self admin target
   necessarily has the caller for company — the **self rail** is what actually protects the final
   admin. The last-admin check stays for the window where the caller's rights change mid-request.
6. **The UI mirrors the rails** (`features/admin/lib.ts`: `deleteDecision`, `confirmsName`) so the
   Remove button is disabled with the reason on screen rather than offering a 400. The server
   remains the authority.
7. **Unknown grants are surfaced, not swallowed.** A grant is a library **ItemId**; a stale id
   grants nothing and looks like "the app hid my library", so `accessSummary()` reports it.
8. **The Household nav link is visible to everyone on purpose.** Hiding it is not security; the
   API answers 403 and the screen states the requirement plainly.
9. **The Phase 1 login form had to change for §8.1**: it had `required` on the password field, so
   the BROWSER would have blocked a password-less account's sign-in with no error anywhere.
   Removed, and pinned by a new scenario in `tools/check_login_flow.py`.

10. ⚠ **THE FIRST LIVE RUN TOLD THE ADMINISTRATOR THEY WERE NOT AN ADMINISTRATOR** (`61d6b67`,
    the day it shipped). The screen said *"Only a Jellyfin administrator can manage household
    accounts"*. That was false, and TWO defects produced it, both swallowed by the gate's
    `try/except`:
    * **the FACADE** — the routes are handed `LibraryService`, a facade over the providers. The
      household methods had been added to `LibraryProvider` only, so every route call raised
      `AttributeError`. The facade now delegates all nine.
    * **the MESSAGE** — `is_administrator()` collapsed "not an administrator" and "could not ask
      the server" into one `False`. It is now `admin_status()` → `True`/`False`/`None` and the
      route answers **503** for `None`, logging the provider's `last_api_error`. 401 / 403 / 503
      are three different truths and must stay three answers.
11. **`library_folders()` is a DICT on the facade and a LIST on the provider.** `/api/admin/
    libraries` 500'd (`'str' object has no attribute 'get'`) and the create-with-every-library
    grant would have too; one `_library_rows()` helper reads either shape. **Any route reading a
    provider capability must check which shape it is given**, because the route's `library` is
    always the facade.
12. **Why the 39 tests missed both, and the fix that closes it:** the route tests replaced
    `build_library_service` outright, the provider tests built the provider directly — so NOTHING
    exercised route → facade → provider. There is now `TestFactoryWiring`, which builds the REAL
    service from config and drives it through the facade, and the fake provider answers
    `library_folders()` in the FACADE's shape. Changing that fake immediately failed two more
    tests and exposed defect (11) — **make the fake mirror what the route really receives, not
    what the provider really returns.**
13. `tools/diag_household_gate.py` reports what is actually true (config, provider built?, login
    ok?, what `list_users`/`get_user_policy` answer, which gate answer applies) in one command.
    **Minting an API key by logging in on the app's own device id does not work**: Jellyfin
    rotates a device's token on every login, so the app's next login invalidates it (401). Use a
    distinct `DeviceId` for tooling.

## 5. Ordering

**Recommended: Phase 1 (login UI) → 1b (this) → Phase 2 (enforcement) → Phase 3 (identity) → 4 → 5.**

- 1b needs a signed-in admin in the browser ⇒ it needs Phase 1, not Phase 2.
- Doing 1b BEFORE enforcement lets him exercise account creation while the app is still
  permissive (no lockout risk during testing), and Phase 2 then protects the new admin
  routes along with everything else.
- Phase 3's live proof is unblocked the moment 1b lands — that is the point.
- If he would rather have the app protected first: 1 → 2 → 1b → 3 … works too; only the
  order of two independent phases changes.

## 6. Non-goals

- No app-owned accounts, passwords, invitations or self-service signup (Jellyfin owns them).
- No parental-control editing in v1 beyond library access + enable/disable (the policy has
  `MaxParentalRating`, `BlockedTags`, schedules etc. — a later, separate decision).
- No email/notification of a new account — he tells the household member the password himself.
- Deleting an account does not manage their media or watch history (Jellyfin's own cascade decides).

## 7. Risks and traps

1. **The policy is REPLACED wholesale.** Read-modify-write only: a partial `UserPolicy` body
   silently resets the fields you did not send.
2. **`EnabledFolders` holds library ItemIds** (with `EnableAllFolders=false`); a wrong/stale id
   grants nothing and looks like "the app hid my library".
3. **Authorization must be live, never cached** — and these routes strict regardless of the
   global flag.
4. **Never let the password reach a log, a response, or the store** — test-pinned.
5. **Deleting is irreversible**, and deleting the LAST administrator would take the app's
   ability to manage accounts with it ⇒ refuse to delete the last admin, and require the
   account's name typed to confirm.
6. **`POST /Users/Password?userId=`** — query param, not a path segment (a path-form call 404s).
7. A created account with **no password** signs in with a BLANK password — so the app's login form
   must not block an empty submit (it did until `b360b38`; scenario D pins it), and such an account
   must never be an administrator (§8.1).
8. Any provider-level cache added later must be keyed by USER (the standing Phase 3 rule).

## 8. Decisions — DECIDED by the user 2026-09-12

1. **Password: NO password (option 1c).** The user's instruction was *"i want to create the second
   user without password"* — a real Jellyfin case (their own apps let such an account in with just a
   username). Consequences, which are now build requirements rather than choices:
   - the create form's password field is **optional**;
   - the app's **login form must accept a blank password** (a `required` field would block the empty
     submit and make such an account impossible to use — fixed in Phase 1, `b360b38`, and pinned by
     scenario D of `tools/check_login_flow.py`);
   - a password-less account must **NEVER** be granted administrator: anyone who can reach the app
     would then be able to create and delete accounts. The create route refuses it (there is no
     admin checkbox in v1) and Jellyfin's own policy default is non-admin;
   - the honest reach picture stays what makes this acceptable: the app is reachable on `localhost`,
     the LAN and the Tailscale tailnet, and **tailnet-only** (`docs/TAILSCALE_HOSTING.md`, never
     funnel). Adding a password later is a Jellyfin policy change, not an app change.
2. **Library access default for a new member: same as the creating admin** (option 2a).
3. **v1 scope: add + grant + disable + password reset + delete** (option 3a).
4. **Order:** the user did not answer this one; the session took the recommendation —
   **1b BEFORE Phase 2** (`RKM_AUTH_REQUIRED` stays false while 1b is tested). Noted in PROGRESS so
   he can reverse it in one sentence; it only changes the order of two independent phases.

## 9. Verification commands

```bash
python3 tools/probe_jellyfin_users.py             # who exists, what can be granted (read-only)
python3 tools/probe_jellyfin_users.py --schemas   # full property lists for create/policy
cd backend && python -m pytest -q && python -m ruff check .
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
python3 backend/scripts/snapshot_openapi.py       # 44 -> 49 paths when 1b.0 lands
```
