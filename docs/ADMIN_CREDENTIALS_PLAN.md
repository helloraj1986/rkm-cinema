# Admin credentials — provision without a stored password, rename the account, self-service password

**Status:** SCOPED 2026-09-12 (nothing built yet). Absorbs **Phase D** of
`PLEX_PROFILE_AUTH_PLAN.md` (rename + the profile's own change-my-password) by the user's decision of
2026-09-12, and follows **Phase C** (`5e303e0`), which is what makes per-profile identity real.

## 1. What the user asked for, in his words

> *"ideally the password should not be in .env file ... can we provision it so that user can set it
> from ui... and then we can remove it from .env file .. we have to be careful so that we dont lock
> ourself out"*

> *"also the admin can change its user name... the role should only be admin rather than the actual
> name saying admin"*

and, revising the fresh-install question the same day:

> *"or we can do like ths fresh install will create a admin with password.. which bootstrap.ps1 will
> let the user know so that it can record it and in that way there will be no fear of loosing the
> password"*

## 2. Decisions (user, 2026-09-12 — all inputs, not recommendations)

1. **A fresh install creates the admin WITH a strong generated password, printed ONCE by the
   bootstrap so it can be recorded.** Nothing is written to `.env`; nothing is generated or printed
   on later runs. **This replaces** the earlier "create it with no password" choice, and §4 records
   what that choice would have cost — the reversal is what removes the risky phase.
2. **The admin account can be RENAMED**, and the UI must present a **role** ("Administrator") rather
   than leaning on the literal name `admin`. Nothing may depend on that name.
3. **`.env` keeps `RKM_JELLYFIN_ADMIN_PASSWORD` as OPTIONAL** — never generated, never required by
   compose, never read by the provisioner after the first run; documented as "leave blank unless you
   want the local Python tools to sign in". A different arrangement for the tools is a LATER
   investigation, recorded here so it is not forgotten.
4. **This workstream absorbs Phase D** — the rename UI and the self-service "change my password"
   screen are built here, not separately.

## 3. Measured inventory — what actually needs that password (live, 2026-09-12)

| Consumer | Needs it? | Evidence |
|---|---|---|
| **The api container** | **NO** | its Jellyfin credential is **`JELLYFIN_API_KEY`**, minted by the provisioner into the `rkm_shared` volume (`runtime.json`, `RKM_RUNTIME_PATH`). `JELLYFIN_ADMIN_PASSWORD` is passed to the **provisioner service only** (`docker-compose.yml` §provisioner) |
| The provisioner | **once**, on a brand-new `jellyfin-config` | `provision.py::run_startup()` posts the startup wizard (`POST /Startup/User {Name, Password}`) — the ONLY place a password is *created*; afterwards `ensure_admin()` merely authenticates |
| `docker-compose.yml` | as a **GATE** | `JELLYFIN_ADMIN_PASSWORD: "${…:?…}"` — compose REFUSES to start the provisioner when unset. **The first thing that must change** (`:?` → `:-`) |
| `render_config.py` | it **generates and writes it back** | `if backend == "jellyfin" and not admin_pw: admin_pw = secrets.token_urlsafe(18); write_env_key(ENV_PATH, …)` — how the value got there, and why "just delete the line" does not stick. **The generation already produces a strong password; where it goes is the whole change** |
| Local tools | yes | `tools/rkm_common.py::Jellyfin._login` (so `probe_stack`, `diag_household_gate`, `prove_profile_isolation`, the diagnostic probes) and `backend/scripts/probe_jellyfin_{detail,hls}.py` |
| The bootstrap console | **no log file** | `grep` for `Tee-Object`/`Out-File`/`Start-Transcript` in `bootstrap.ps1`, `rkm-cinema.ps1` and `scripts/*.ps1` finds none — a printed password is not written to disk, which is what makes §2 decision 1 safe. (It does live in the terminal scrollback, and in anything the console output is pasted into.) |

### 3a. The break-glass credential, MEASURED

**A Jellyfin API key satisfies elevation.** `GET /Library/VirtualFolders` answers **200 with an API
key** and **403 with a non-administrator's session token** (both measured on 10.11.11, 2026-09-12).
The key lives in the `rkm_shared` volume, survives rebuilds, is never typed by a human and is never
in a repo file — so it is the credential a **recovery command** can rely on when every password is
forgotten. This is the real answer to "no fear of losing the password": recording the printed value
is convenience, the volume key is the guarantee.

⚠ Still to be PROVEN (not assumed), on the throwaway stack of §7: that an API key is accepted by
`POST /Users/Password?userId=…` with `ResetPassword: true` (`/Users/Password` is in the server's own
contract; Jellyfin expresses its elevation policy in code, not in the OpenAPI document, so the
proxy above is strong evidence and not proof).

## 4. The lockout that the REJECTED design would have produced (kept as history — it is why §2 decision 1 was reversed)

The first decision was to create the admin with **no password** and force one from the UI. Measured
against the code, that combination had a guaranteed dead end:

* `POST /api/auth/login` **succeeds** with a blank password (supported — `401a3c7`, pinned by
  scenario D of `tools/check_login_flow.py`), and the session is created with the administrator as
  its owner;
* then the picker appears — and `POST /api/auth/profile` refuses a blank attempt on the
  administrator's own profile **unconditionally**:

  ```python
  wants_admin = bool(target.get("is_admin"))
  if wants_admin and not payload.password:
      raise HTTPException(status_code=401, detail="Enter the administrator's password to switch to that profile")
  ```

  That rule is decision 3 of the profile model, chosen deliberately so a guest cannot walk into the
  admin's profile on a shared device. It does **not** consult `has_password`.

So a fresh install would have let the administrator in the front door and then stranded them at a
picker where **no profile could be selected**. Fixing that would have required a mandatory
set-password gate between sign-in and the picker, server-enforced, plus the state to back it — the
riskiest thing in the workstream.

**Generating the password at creation time removes all of it:** the admin has a password from the
first second, the picker behaves exactly as it does today, and there is no new gate to get wrong.

## 5. The second trap: the literal name `admin`

Renaming the account breaks anything that assumes the name:

* `RKM_JELLYFIN_ADMIN_USER` (`.env`, default `admin`) is what the provisioner authenticates with and
  what every tool signs in as;
* `ensure_admin()` looks that name up; a rename leaves it authenticating as a user that no longer
  exists → `wizard_pending() is False` + auth fails → **fail fast naming the password** (a confusing
  message for a rename problem).

**Rule for the implementation:** resolve the administrator by **id** (from the stored identity /
`runtime.json`) wherever the credential is the API key, and treat `RKM_JELLYFIN_ADMIN_USER` as a
**first-run hint only**. A rename must not require an `.env` edit.

## 6. Phases (one sitting each, one commit each, gates green every time)

| Phase | Content | Gate |
|---|---|---|
| **0** | This plan + the throwaway-stack recipe (§7); amend `PLEX_PROFILE_AUTH_PLAN.md` §7 rows D/E to point here | docs links |
| **1** ✅ | **No password needed after the first run, and the first-run one is PRINTED, never stored.** The generation MOVES from `render_config` (which runs on every bootstrap and cannot tell a fresh install from a re-run) to `provision.py::run_startup()` (which knows it is creating the admin because that is what it is doing): generate `token_urlsafe(18)`, set it on the account, and print it in a boxed, unmissable notice **only when the wizard step actually succeeded** (`200/204`), never on a re-run. `ensure_admin()` tries the STORED credential first (`JELLYFIN_API_KEY` / `runtime.json`) and resolves the admin by id; compose `:?` → `:-`; `render_config` stops generating or writing the key; `.env.example` documents it as OPTIONAL (tooling) with the reason. If it IS set in `.env`, it is used and nothing is printed — the manual override survives | pytest (provisioner: fresh install prints + sets; re-run prints nothing and needs no password; a rename does not break it), ruff, docs links |
| **2** ✅ | **Household: role vs name.** An **Administrator** badge and the account's real name; rename (`POST /Users?userId=`) with the rails; the picker/header/sidebar never label a person by their role — **BUILT 2026-09-12**; see §6a | tsc, vitest, `check_household_ui.py` + `check_profile_picker.py` (new scenarios), build |
| **3** ✅ | **Self-service password screen** for every profile (Phase D's other half): change my own password with `CurrentPw` + `NewPw`; honest messaging for a password-less member — **BUILT 2026-09-12** (`57dd122`); see §6b/§6h | gates + DOM check |
| **4** ✅ | **Recovery, documented and tested** — **BUILT 2026-09-13**: `rkm-cinema.ps1 reset-admin-password` reads the API key from the `rkm_shared` volume (never `.env`), finds the administrator **by policy** (never the literal name `admin`), prompts for a new password (never an argument — history and the process list), writes it with **`ResetPassword: false`** ⚠ (this row said `true` until §6c measured that `true` is a silent no-op that CLEARS a password), then **proves it by signing in**. `OPERATIONS.md` gained the "Locked out? The ladder" section. See §6i | the tool's own verification output; **38 pytest** for its rules and its whole flow against a stub server |
| **5** | ADR (the credential model), docs truth pass (`ARCHITECTURE`, `OPERATIONS`, `README`), PROGRESS record | full suite + docs links |

### 6i. ✅ Phase 4 — the break-glass (`rkm-cinema.ps1 reset-admin-password`), and the plan row that was wrong

Built 2026-09-13. Locked out of the administrator account is the one failure with **no UI way out**:
Household needs an administrator, and being one needs the password. `tools/reset_admin_password.py`
(invoked through the single entry point) removes the need for it — the stack's own **API key** lives
in the `rkm_shared` volume, and an administrator's **privilege** is what authorises a reset, so
nothing remembered is required.

⚠ **The plan's own Phase 4 row said `ResetPassword=true`, written BEFORE §6c measured it.** On
Jellyfin 10.11.11 `true` answers 204, sets nothing, and **CLEARS a password that existed**. The tool
sends **`false`, always**; there is no parameter to change it, and a test asserts the flag can never
be true in the body. The row itself is corrected in place — a future session reading the plan would
otherwise have implemented the destructive shape it described.

* **The administrator is found BY POLICY** (`IsAdministrator` and not disabled), never by the name
  `admin` — §5: the account was renamed to `rkm`, and a MEMBER can perfectly well be called "admin"
  (that case has its own test).
* **The password is never an argument and never printed**: it is typed at the tool's own prompt,
  twice, and sent straight to the media server. An argument would sit in PowerShell history and in
  the process list.
* **It proves the change by signing in** with the new value (§6d), and exits non-zero when it cannot:
  `0` verified · `2` no key · `3` key refused · `4` no usable administrator · `5` server refused the
  reset · `6` accepted but sign-in refused (not taken) · `7` accepted but unprovable (**stated as
  exactly that** — never as success).
* **Two ways to the key**, because the break-glass must work in the state he is actually in:
  `docker compose exec` on the running api container, then `docker run` with the volume mounted
  read-only — the same pattern `backup-rkm-state.ps1` uses, so it works with the stack stopped.
* **`-DryRun` is genuinely read-only** — proved by the stub test (one GET, zero writes) — and it is
  the first thing the wrapper tells him to run.
* **A MEMBER cannot be targeted with `-Name`**: it refuses and says where that is done instead
  (Household, or My password). The break-glass is the lockout recovery, not a household tool.
* **`OPERATIONS.md` gained "Locked out? The ladder"**: administrator (this tool) → a member
  (Household / My password) → no key in the volume (a deploy re-provisions and prints once) → state
  volume lost (restore from backup) → no backup at all (**explicitly out of scope and destructive**:
  the accounts live in Jellyfin's own database, and nothing here improvises that).

**Evidence.** **38 pytest** (`backend/tests/test_reset_admin_password.py`) — the pure rules AND the
whole flow driven against a real local HTTP stub: the measured body on the wire, the
proof-by-sign-in, the password-mismatch retry, the refused API key, an empty account list and a
member-by-name dead end. **Falsified**: with the destructive flag restored and administrators picked
by name, 8 tests fail.

⚠ **Not covered by execution:** the `.ps1` wrapper itself (there is no PowerShell in the sandbox). It
is deliberately a thin, obvious forwarding wrapper for that reason, and the runbook's first step is
`-DryRun`. The tool's CLI and its no-docker failure path WERE run here (`--help`, `--dry-run`).

### 6h. ✅ A STALE TOKEN IS NOT A WRONG PASSWORD — and the message never reached the screen anyway

Queue item #2's first half, built 2026-09-13. Three separate faults, all of the same family: **the
app was naming the wrong culprit.**

**1. `401` and `403` are different answers** (`jellyfin.py::change_own_password`). Measured on the
live server (§6c): the profile's own token + a wrong `CurrentPw` → **403**; a token Jellyfin no
longer accepts → **401** ("Invalid token" — the burst measured 2026-09-12). Both were mapped to
`"wrong-password"`, so a stale sign-in was reported to the person as *"that current password is not
correct"* — a false accusation AND a dead end, because retyping cannot revive a token. The remedy is
**switching profile again** (the only thing that re-authenticates a profile; Jellyfin has no
impersonation). The provider now returns `"stale-session"` for a 401 and the route answers
401 *"This profile is no longer signed in to the media server — use Switch profile in the account
menu, then retry."* — naming the exact control.

**⚠ 2. The message could never have appeared live: the Façade DROPPED the provider's reason.**
`LibraryService.change_own_password`'s loop kept only `None`/`"unreachable"`, so with the REAL
provider a wrong current password was reported as *"the media server refused the password change"*
(502) — the server blamed for the user's typo. **Every unit test passed** because the fake library in
`test_profile_auth_api.py` returned the reason itself; only reading the façade did. Fixed: the first
non-`None` reason wins (a definite answer about the credential beats "could not ask"), pinned by
`TestTheFacadeKeepsTheProvidersAnswer`.

**⚠ 3. Answering 401 honestly would have made things WORSE, because the client signs you out on any
401.** `api.changeMyPassword` was the one auth-route call WITHOUT `skipAuthRedirect`, so a 401 from
it fired the global *"the session is dead"* rule: **the person was signed out of the whole app and the
query cache cleared** — for typing their password wrong, and (after this change) for a stale token.
Measured: the new vitest case failed against the old client. Fixed with `{ skipAuthRedirect: true }`
— both 401s belong to the form, exactly like `login` and `profiles`.

**Evidence.** 966 backend pytest (+6: the façade pass-through ×4, the 401/403 split, the route's
stale-session message) · ruff clean · **282 vitest** (+2: the sign-out rule, and the server's words
reaching the form) · tsc clean · build · **5 browser checks** · openapi 53 paths · docs links.
Falsified both ways: reverting the three backend files fails the 4 new backend tests; the vitest case
fails without `skipAuthRedirect`.

**⏭ STILL OPEN — deferred to Phase E deliberately (this is the "long" half).** On a **media** call a
stale profile token is still indistinguishable from a dead session, so the client signs the browser
out and the app cannot say *"switch profile again"* there. Fixing it properly means the API
distinguishing **session-401** (the cookie is gone) from **profile-token-401** (the cookie is fine,
the profile's credential is stale) across the media routes, and/or **per-session device ids** so the
app stops rotating its own tokens away (`_client_header()` uses ONE device id, `rkm-cinema-web`, for
every session — two browsers signed in as the same account kill each other's tokens). Both belong in
**Phase E's 401/403 sweep**, where the whole taxonomy is settled once instead of twice.

### 6g. ⚠ "You removed the household from rkm as well" — the nav gate read a field the server never sent

**His report (2026-09-13), verbatim:** *"you have removed the household from rkm(admin) as well, now i
can change profile passwords and access for other users...it was supposed to be aviable only to admin
user and removed from non admin users...also we need tweaks in ui, for example 'my password' option
doesn't need to be sitting on the left side bar it can simply reside when user click its avatar so
consolidate the ui elements to make it premium user experience just like any other world class app"*

#### The bug, exactly

`GET /api/auth/profiles` built its `current` row as **`ProfileUser(id=context.profile_id(),
name=context.profile_name())`** — a name-only stub. `ProfileUser.is_admin` defaults to **False**, so
`current.is_admin` was **false for every profile in effect, including the administrator's**. The nav
gates Household on `mayManageHousehold(current.is_admin)`, which **fails closed by design**, so
Household disappeared for everybody: a gate that was built to protect members hid the screen from the
one person entitled to it.

**Why no check caught it.** `tools/check_nav_access.py` and every harness stub in
`frontend/harness/` supplied `current: {... is_admin: true}` — a payload the server was incapable of
producing. The stub was kinder than reality and the check was green for the whole life of the feature.
(Same family as §6e: the fake cannot reveal a fallback the real code has.)

**Fixed** in `api/routes/auth.py`: `current` is now the SERVER's own row for the profile in effect,
through the same `_profile(row)` converter the list uses. When the account is not in the list — the
server could not be asked, or it was removed — `current` keeps the id and name we know and the flags
stay **False**: an unknown answer must not OFFER an administrator's screen. Pinned by
`TestProfiles::test_the_current_profile_carries_the_SERVERS_own_answer` (fails against the old code)
and `test_an_unknown_current_profile_fails_closed`.

#### The consolidation (his second request, same message)

The same three destinations were offered in **three different places, differently**: the header had
four separate controls (name, a non-clickable avatar, a "Switch profile" link, a "Sign out" button),
the sidebar nav had My password (for everyone) and Household (administrators), and the mobile sheet
had its own copies. Now there is ONE account menu:

* `frontend/src/features/auth/AccountMenu.tsx` — the avatar IS the trigger, with an identity block
  (monogram, name, role, and *"signed in as …"* only when the profile differs from the account).
* Items come from the pure rule `accountDestinations(isAdmin, profileSelected)` in `features/auth/lib.ts`:
  **Switch profile · My password (every profile) · Household (administrators only) · Sign out**.
  One gate, `mayManageHousehold`, so the two surfaces cannot drift.
* Mounted twice from the same component: the header avatar (every breakpoint, so the phone gets it)
  and the sidebar footer, which used to be a decorative identity card that named you and offered
  nothing (`variant="wide"`; the name/role/chevron show only at `xl`, where the sidebar is 240px).
* The sidebar nav and the mobile "More" sheet now carry **navigation only** — a member's navigation
  fires no `/api/admin/*` call at all, and there is no duplicated Household/My password anywhere.

`PopupMenu` gained `header` (a non-interactive block above the items), `triggerTestId` and
`triggerLabel` (the trigger says *"Watching as Guest"* while the menu is named *"Account menu for
Guest"*). `tools/check_nav_access.py` now proves the menu from **every** trigger, on a **phone
viewport** as well — 5 scenarios, falsified by opening the gate (`mayManageHousehold` returning true
for a member), which fails both member surfaces.

#### ⚠ And the harness that could not see any of it

`frontend/harness/nav-frame.tsx` **never loaded the app's stylesheet** (the other four frames do).
Text-based assertions passed anyway, so nobody noticed — but every screenshot and geometry
measurement of that frame was *unstyled*: the account menu measured 1424px wide, and the mobile
"More" button was clickable at a desktop width where CSS hides it. It imports `../src/styles/index.css`
now, and the check uses a desktop viewport for the desktop surfaces and a phone one for the mobile
bar. `check_profile_picker.py` and `check_login_flow.py` were updated to open the menu (they looked
for a standalone "Switch profile" link and "Sign out" button).

#### Evidence

**960 backend pytest** (+2) · ruff clean · **tsc** clean · **280 vitest** (+6) · `npm run build` ·
**5 browser checks** green (`check_nav_access` 5 scenarios, falsified; `check_profile_picker`,
`check_login_flow`, `check_password_change`, `check_household_ui`) · openapi **53 paths** ·
docs links resolve. Screenshots for his eyeball: `/workspace/rkm-ux-shots/account-menu-*.png`.

**His deploy** — BOTH containers this time (api for `current`, web for the UI):

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
docker compose -p rkm-bundled up -d --build api web
```

### 6f. ⚠ THE RAIL: a request that arrived as SOMEBODY can no longer act as a stranger

Built 2026-09-13 — the first item of §6e's hand-off queue. §6e fixed the ONE route; this fixes the
CLASS. The bug was never "the password route is wrong": it was that **a route could resolve a
session and then reach the provider as nobody**, and the provider's two fallbacks (the app's
elevated API key, and `_user_id()`'s "first account in `/Users` order") turned that into a silent
write on a different person's account, reported as success.

**The rail** (`backend/api/session.py`). `session_context_from_request` — the ONE place a cookie
becomes a session — now also RECORDS the session it resolved, with the route it happened on. The
identity helpers `acting_media_token()`, `acting_user_id()` and `acting_profile_is_owner()` then
REFUSE to fall back in that state:

| the request | who the call acts as |
|---|---|
| **no request context at all** — the provisioner, the scheduler's jobs, every tool, unit tests | the app's own key. **Unchanged, and load-bearing** |
| **arrived as NOBODY** — no cookie, or a stale one; a normal request while `RKM_AUTH_REQUIRED=false` | the app's own key. Unchanged |
| **arrived as SOMEBODY, and nothing published it** | **`UnpublishedIdentityError`**, raised before any URL is built |

The last state is never legitimate: it means a route resolved the session and then called the
provider without publishing it. The error message names the route and the account, and is logged at
ERROR — the log line is the whole diagnosis.

`owner_media_token()` is the ONE deliberate exception: its fallback IS the administrator's own
credential, every call it serves is server administration, and refusing there would break the
household routes on a routine request.

**The credential split that makes it possible** (`jellyfin.py::_api`). Account administration —
`/Users`, `/Users/New`, `/Users/{id}/Policy`, `/Users/Password`, `/Users?userId=`, `/Users/{id}` —
now runs on the OWNER's credential **by default**. It used to take whatever identity was in effect,
which only ever worked because the profiles in effect happened to be the administrator's; with a
MEMBER selected the same call runs on the member's token and Jellyfin answers 403, so the picker
would be told *"there are no profiles on this server"*. `credential="acting"` survives for exactly
ONE caller, `change_own_password`, where being the acting identity IS the feature — on the owner
credential the `CurrentPw` would stop being checked at all, which is an escalation. Pinned
structurally by `test_no_other_provider_call_reaches_for_the_acting_credential` (AST).

**The façade may not contain it** (`services/library/service.py`). Its `except Exception` handlers
exist to turn a provider failure into an honest "nothing happened", and the first version of the
rail was swallowed there: the screen was told *"the media server refused the password change"* —
blaming the server for a bug in our own wiring. `_rethrow_identity_rail` lets it out.

**Falsified, not asserted.** With the guard removed (`_published_identity` behaving as before),
`tests/test_identity_rail.py::…::test_forgetting_to_publish_fires_the_rail_instead_of_writing` fails
with the 2026-09-12 report **verbatim**:

```
the rail did NOT fire, so the write went through:
  /Users/Password on 'app-key-ADMIN' targeting ['uid-first'] — the session had uid-kid selected
```

i.e. the write reaches the server on the app's elevated key, aimed at whichever account the server
lists first. Restoring the guard turns it green (22/22).

**⚠ Found while adding the per-route test: the structural guard was VACUOUS.** FastAPI 0.141 keeps
each `include_router` as an `_IncludedRouter` on `app.routes` whose sub-routes carry paths WITHOUT
the prefix — so `test_every_api_route_publishes_a_identity`, the test whose entire job is to stop a
new router shipping without `SESSION_SCOPED`, was inspecting **zero** routes and passing. It now
enumerates through `include_context` (prefix + include-level dependencies) and `original_router`,
ASSERTS it found ≥ 40 routes before anyone trusts it, and was falsified by removing
`dependencies=SESSION_SCOPED` from the config router — it names `/api/config`. **Generalise: any
test that enumerates framework objects must assert it found something.**

**Evidence.** 958 backend pytest (+23: 22 in `tests/test_identity_rail.py`, 1 auth-route inventory) ·
ruff clean · openapi still **53 paths** · docs links resolve · **no frontend change**, so this is an
api-only deploy.

**His runbook** (nothing here needs the web container):

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
docker compose -p rkm-bundled up -d --build api
```

Then the two-minute sanity pass: sign in → pick a profile → **My password** → change it → sign out →
pick that profile → the new password is asked for; and Household → every row still lists.

### 6e. ⚠ THE ROOT CAUSE of "it says changed but nothing changes": the route was not session-scoped

Found 2026-09-12 after a long chase, by reproducing his exact symptom **through the app's own HTTP API**
(admin login → select the profile → change the password → verify by logging in outside the app). The
response was `{ok: true, confirmation: "refused", name: "raj"}` and `raj`'s password had not changed.

**Mechanism.** `POST /api/auth/profile/password` lives on the **auth router**, which is deliberately
**not** session-scoped (sign-in must work signed out — see `api/main.py::SESSION_SCOPED`). So no
dependency ever publishes the session contextvar for it, and the provider — which reads the identity
from that contextvar — silently fell back to:

* the **app's API key** for the credential (elevated, so the write ALWAYS succeeded), and
* `_user_id()`'s historical lookup, which is **the first account on the server**.

So the change was applied to whichever profile happened to be **first in `/Users` order** (measured:
`meenu`, `raj`, `rkm` → `meenu`), while the route's own name/verification — which reads the session
from the REQUEST — correctly reported on the profile it was told about. That is why:

* it looked **intermittent**: the "first account" changes as profiles are created and removed;
* it appeared to work for `meenu` earlier: `meenu` WAS first, so "meenu's" change changed `meenu`;
* proof positive, measured read-only: `raj + 'raj1234'` refused, **`meenu + 'raj1234'` logged in**,
  `rkm + 'raj1234'` refused — his "raj" change had landed on `meenu`.

**Fixed** by publishing the session around the provider call (`set_current_session` / `reset_…` in a
`finally`) in that route. A regression test at the routing layer drives the **REAL** provider through
the route and asserts the POST targets the profile's id *and* carries the profile's own credential —
and it **fails without the fix** (a fake library can never reveal this: the fallback only exists in the
real provider).

**Proven end-to-end** with the fixed code running locally against the live Jellyfin: login → select
`raj` → change → `{"ok": true, "confirmation": "verified", "name": "raj"}`, and outside the app the old
password stops working while the new one logs in.

**The lesson, generalised:** a silent fallback that substitutes a *different identity* is worse than an
error. "No context" is the right default for the provisioner, the scheduler and the tools — and the
wrong one for any write that must act as the person asking. Any route that writes as "the current
identity" must publish that identity first, and a test must prove it does.

### 6d. A 2xx is not evidence — a password change is now PROVED before it is claimed

**His second report:** *"password change from the profile itself doesn't work..it just says password
changed after filling in the old password and new password..but it never lands...when switch profile
and login back to rajeev it still takes the old password"*.

Measured with the app's own code (session seam set as a real session, then verified by logging in):

| | result |
|---|---|
| profile **set** in the session (normal) | `change_own_password()` → landed; new password logs in, old one does not ✔ |
| profile **NOT set** (partial session) | the app falls back to the **OWNER** and targets the administrator's account |

That second row is the dangerous one, and it is why the screen could report a change that had not
happened **to the account the person was looking at**. And the shape itself is fine: the raw
self-change call (`CurrentPw` + `ResetPassword: false`, caller's own token) lands, verified by login —
so nothing about the request needed changing.

**What changed**: the route no longer believes the status code. After a successful call it signs in
**with the new password** (`password_change_took_effect`, on its own `rkm-password-verify` device —
never the app's device, because Jellyfin rotates a `(device, user)` token on every login and that
would kill the session asking), and only then says "changed". If that fails it answers **502** with
*"…the new password does not work, so it was not applied"*. The screen also now **names the account it
will change** (`data-testid="password-target"`), so a wrong target is visible before pressing rather
than discovered afterwards.

⚠ **Still open** — *which* account his attempt actually hit. The api logs the profile id on every
change (`logger.info("auth.password …confirmed for profile id=%s")`), so one retry plus
`docker compose -p rkm-bundled logs api | Select-String "auth.password"` names it. If it names the
administrator's id rather than the member's, the cause is a stale/partial session (profile not set),
and the follow-up fix is to refuse to change a password when the session is not on a profile.

### 6c. ⚠ MEASURED: `ResetPassword: true` is a silent no-op that CLEARS passwords

**Found live 2026-09-12**, from his report: *"i have logged in as admin(rkm) -> household -> set a
password in rajeev -> it still says no password"*. Measured on Jellyfin **10.11.11** by driving every
combination against a real account, each attempt verified by **logging in with the intended value**
(never by the status code):

| credential | body | result |
|---|---|---|
| admin session token | `ResetPassword: true`, `CurrentPw: ""` | **204 — sets nothing, CLEARS an existing password** |
| app API key (what Household sent) | `ResetPassword: true` | **204 — sets nothing** |
| app API key | `ResetPassword: false`, `CurrentPw: ""` | **204 — the password IS set** ✔ |
| admin session token | `ResetPassword: false`, `CurrentPw: "guessing"` | **204 — still sets it** ✔ (privilege, not the flag, authorises a reset) |
| member's own token | `ResetPassword: false`, correct `CurrentPw` | **204 — set** ✔ |
| member's own token | `ResetPassword: false`, wrong `CurrentPw` | **403** ✔ (refused, as the screen says) |

**So the app had it exactly backwards.** The belief recorded in this codebase — *"`ResetPassword: true`
is what lets an administrator change somebody else's password without knowing the old one"* — is
false here: the flag does nothing, **and wipes passwords set elsewhere**, which is why the same
account could be "set" repeatedly and still have none. The administrator's own privilege is what
authorises a reset.

**What changed** (`backend/services/library/{jellyfin,service}.py`):

* `set_user_password()` sends **`ResetPassword: false`, always**, and the parameter is **gone** — a
  flag that must never be true should not exist for someone to pass by accident. `change_own_password`
  already sent the working shape; only Household's path was broken.
* The write now **proves itself**: after the 2xx the provider re-reads the account and reports
  success only when a password is really there. This endpoint has answered 204 while storing nothing
  for the whole life of the feature — a 2xx from it is not evidence.
* Regression tests pin both: the body carries `ResetPassword: false`, and a 204 with no password
  afterwards is a **failure**, not a success.

**Verified live, end to end, against his server** — the app's own `set_user_password()` on a real
member: `accepted=True`, `has_password` flips to true, and a real login with the new value succeeds.
`tools/probe_password_write.py` is the repeatable verifier (read-only by default; `--target X
--password Y` drives the app's own code and checks it by logging in).

⚠ **Nothing about this was provable from unit tests** — every test in the suite passed while the
feature did nothing on a real server. It took one live round-trip per combination.

### 6b. Phase 3 as built — "Settings → My password"

**Shipped 2026-09-12.** Contract **52 → 53 paths** (one additive route). `POST /api/auth/profile/password`,
and the sidebar entry **My password** — the one screen every profile has, and the gap it closes: until
now a password could only be changed by an ADMINISTRATOR (Household → Reset password), for somebody
else. A member's password is their Jellyfin credential and the lock on their profile; they had no
way to change it themselves.

**One credential rule.** The target is the PROFILE in effect (`context.profile_id()`), and the
provider's call takes **no user id at all** — there is no parameter a caller could fill in with
somebody else's account, so "change my own" cannot become "change theirs". `ResetPassword: false`
always: the reset flag is the administrator's path (it needs no old password) and would be an
escalation here. Sending the OLD password is what makes this a genuine self-change.

**Rails** (server-side, mirrored by the screen so the button is honest before it is pressed):
session required · the new password must be non-empty · the OLD one is required whenever the account
has one, and **Jellyfin is the judge** of that · neither value is logged, echoed, or returned.

**Two deliberate non-rules**, both from the repo's own history: a **whitespace-only** password is
ALLOWED (Jellyfin accepts it; refusing it here would be a second implementation of the server's
contract — the trap that once made password-less accounts unable to sign in), and there is **no
length rule**. Only a truly empty value is refused, because the app's model is that an account is
*created* without a password, not emptied afterwards.

**⚠ The one thing still UNPROVEN (needs two minutes at his keyboard):** the failure mapping. This
build reads a Jellyfin **401/403** as "that current password is not correct" (matching
`authenticate_jellyfin`'s own taxonomy). If Jellyfin instead refuses a *self*-change for a permission
reason, a correct password would be reported as a wrong one. Prove it by changing a member's password
with a deliberately WRONG current password (expect: "that current password is not correct"), then
with the right one (expect: it changes). Do NOT disambiguate by logging in again as the profile —
that rotates the app device's token for that user and would break the very session asking.

**A real bug the browser check found** (not a theorised one): with a 502 and no response body, the
screen showed `POST /auth/profile/password -> 502` — the HTTP client's own fallback string, put in
front of a person. The cause was structural: `ApiError` carried no way to tell the server's `detail`
from that fallback, so a screen could only string-match. Fixed at the source — `ApiError` now carries
`detail: string | null` (the server's own words, or null) — and the screen shows the server's words
when it has them, its own when it does not ("…your old password still works", so a refusal never
reads as a lockout).

**Evidence.** **927 backend pytest (+14)**, all 14 verified to FAIL against the pre-change source ·
**266 vitest (+17)** · ruff, tsc, build clean · openapi **53 paths**, additive · docs links resolve ·
`tools/check_password_change.py` **4/4** (A: required while the account has one, refused before any
request, one clean post carrying exactly the two fields · B: a password-LESS account can set one and
is never blocked · C: a 401 is reported as the current password being wrong and echoes neither value ·
D: a refusal that is not a typo is not blamed on the user — including when the server says nothing) ·
`check_household_ui.py` 4/4, `check_profile_picker.py`, `check_login_flow.py` unchanged.

**Deploy:** api AND web — `docker compose -p rkm-bundled up -d --build api web` (a new route *and* a
new screen). The provisioner is not involved; no library scan is at risk.

### 6a. Phase 2 as built (2026-09-12) — two traps it had to measure

**`POST /api/admin/users/{id}/rename`** (contract **51 → 52**, purely additive) → the provider's
`rename_user()` → Jellyfin's **`POST /Users?userId=<id>`**, whose shape came from the server's OWN
contract (315 paths, read live) rather than from the plan's table:

| Measured | Consequence |
|---|---|
| the target is a **QUERY** parameter (`?userId=`), *not* a path segment | the path form 404s — the same query-vs-path trap the password route already paid for |
| the body is a `UserDto`, which carries **`Policy`** among its 14 properties | ⚠ `/Users/{id}/Policy` is known to REPLACE all 47 policy fields. **If `POST /Users` shares those semantics, a `{"Name": …}` body would wipe `IsAdministrator` — a LOCKOUT.** So the payload carries the id, the name **and the policy the server just reported**, which is correct under EITHER semantics; `HasPassword` is deliberately never sent, so a rename has no way to touch a password. A test asserts the policy travels back |

**The session-name trap.** A session stores the **name it was handed** at sign-in / profile
selection, and nothing re-reads Jellyfin per request — so after a rename the header chip would keep
naming the account the OLD way (a silent wrong answer about who is watching, which is exactly what
this workstream exists to stop). The route now calls `SessionStore.rename_identity()` for the
session making the request. **Another device corrects itself on its next profile selection** — a
name is display, so that is tolerable; unlike a token, which must never be stale.

**Rails** (each has a test): 401 anonymous · 403 a non-administrator (the shared gate, which also
refuses while somebody else's profile is selected) · 404 an unknown id · 400 a blank name · 409 a
name another account already has · 502 when the server refuses — never a false success · a rename to
the SAME name is an idempotent no-op that reaches no server · and the rename never touches a
password. **No client-side length or character rule**: that would be a second implementation of the
server's contract and could forbid a name Jellyfin accepts (the trap that once made a
password-LESS account unusable).

**Evidence:** 913 backend pytest (+14, of which the rename set was verified to FAIL against the
pre-change source) · 249 vitest (+6) · ruff, tsc, build clean · `check_household_ui.py` **4/4**
(its new scenario D proves a refused rename sends NO request, a good one sends only the name, and
the **Administrator badge survives** a rename) · `check_profile_picker.py` and
`check_login_flow.py` unchanged and green · docs links resolve. **Deploy = api AND web.**

⚠ **Not verified here: the live payload semantics.** The read-modify-write is safe by construction
under both readings, but which one Jellyfin actually implements is unproven — a no-op rename on a
live account (rename it to the name it already has, then compare its policy before/after) would
settle it, and needs the owner's consent because it WRITES to his server.

⚠ **There is no forced-set-password phase any more** — that row existed only to rescue §4's rejected
design. Do not add it back "for symmetry".

## 7. Verification, and how we avoid locking ourselves out

**The fresh-install path CANNOT be tested in the sandbox** (no Docker daemon there) and must not be
tested against the real stack (a fresh `jellyfin-config` means losing the household's watch state —
the documented escalation, and unacceptable for a test). So it runs on a **throwaway stack on
RKM-HP**: the same repo with its own project name, ports and volumes.

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
$env:RKM_PROJECT="rkm-test"; $env:RKM_DASHBOARD_PORT="8125"; $env:RKM_JELLYFIN_PORT="8099"
.\bootstrap.ps1                          # exactly how it is invoked is Phase 1's business
docker compose -p rkm-test down -v        # the volumes go; none of yours was ever in them
```

What must be PROVEN there, in order, with the console output quoted in the record:

1. an empty `jellyfin-config` creates the admin, and the **printed password signs in** (blank fails);
2. a SECOND run needs no password, prints nothing, and provisions normally (the API-key-first path);
3. an API key resets that password (`ResetPassword: true`) — proving the break-glass rail;
4. **renaming** the admin does not break the next bootstrap run (the id-not-name rule);
5. `down -v`, and the real stack is untouched.

Then, on the REAL stack (safe, but not free): after Phase 1, one `bootstrap.ps1` run with NO password
in `.env` must provision normally. Run it when no library scan is in progress — the provisioner
issues `/Library/Refresh`, which cancels a running scan.

## 8. Escape hatches (unchanged, and stated so nobody "improves" them away)

* **The API key in `rkm_shared`** — the break-glass credential (§3a), and what the recovery command
  uses. This is the guarantee; a recorded password is the convenience.
* **`RKM_JELLYFIN_ADMIN_PASSWORD` in `.env`** — still honoured as the first-run password and by the
  tools. Nothing removes that ability; it is the documented manual override.
* **The app itself** — an administrator can set or reset any account's password from
  `Settings → Household` today (`Reset password`), including their own, and Phase 3 adds the
  self-service screen for everybody else.
* **`RKM_AUTH_REQUIRED` stays `false`** unless he arms it; nothing here flips it.
* **Jellyfin's own dashboard** on the host knows nothing about this app — but it needs the admin's
  password too, so it is NOT first-line recovery: the volume API key is.

## 9. Honest open questions (answers needed before the phase that uses them)

1. Should the **rename** be available for members too (Household already lists them), or only for the
   administrator's own account? (Phase 2 assumes both, since the rail is the same.)
2. Does a member's **self-service** password change need the administrator's approval to be
   discoverable, or is it simply a Settings entry every profile sees? (Phase 3 assumes the latter.)
3. Is a **one-time printed password** acceptable for the throwaway-stack test, or does the test need a
   fixed value to script against? (Phase 1 assumes it can be read from the console; a fixed value can
   always be supplied via the `.env` override when scripting.)

## 10. Risks

1. **Lockout** — the design that carried this risk was rejected (§4). What remains: a mistyped or
   lost printed password, answered by the app's own reset (already built) and by the volume key
   (§3a).
2. **A rename breaking provisioning** — mitigated by the id-not-name rule (§5).
3. **`.env` regrowth** — if any code path still generates the key, the value comes back and the whole
   change is cosmetic; Phase 1 removes the generation AND asserts its absence in a test.
4. **The printed password leaking** — no log file (§3), but the console is a transcript: the notice
   says plainly that it is shown once, and the value is rotatable in the app in seconds.
5. **Tools losing their login** — accepted deliberately (§2 decision 3): the key stays optional and
   documented; the workaround for a password-less-by-default world is a LATER investigation.
