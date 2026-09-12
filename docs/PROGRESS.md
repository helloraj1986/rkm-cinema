## ▶ LATEST SESSION (2026-09-13, later) — HOUSEHOLD WAS HIDDEN FROM THE ADMIN TOO (fixed) + the account menu · next = his eyeball, then queue item #2

**His report, verbatim:** *"you have removed the household from rkm(admin) as well, now i can change
profile passwords and access for other users...it was supposed to be aviable only to admin user and
removed from non admin users...also we need tweaks in ui , for example "my password" option doesn't
need to be sitting on the left side bar it can simply reside when user click its avatar so
consolidate the ui elements to make it premium user experience just like any other world class app"*

| | |
|---|---|
| Branch | `feat/auth-multiuser`, worktree CLEAN, local tip == remote — **51 commits ahead of `main`** (`c0ae65e`) |
| This session's commit | `064df72` (+ this record). Full mechanism: `docs/ADMIN_CREDENTIALS_PLAN.md` **§6g** |
| Gates | **960 backend pytest** · ruff clean · **tsc** clean · **280 vitest** · `npm run build` · **5 browser checks** · openapi **53 paths** · docs links resolve |
| His deploy | `docker compose -p rkm-bundled up -d --build api web` — **BOTH containers this time** |

### The bug — WHY Household vanished for the administrator

`GET /api/auth/profiles` built its `current` row as `ProfileUser(id=…, name=…)` — **name only**.
`ProfileUser.is_admin` defaults to **False**, so `current.is_admin` was false for **every** profile in
effect, and the nav's `mayManageHousehold` **fails closed by design** — so the gate that exists to
protect members hid Household from the one person entitled to it. `current` is now the SERVER's own
row for the profile in effect (the same `_profile()` converter the list uses); when the account is not
in the list the id/name survive and the flags stay **False** (an unknown answer must not OFFER an
administrator's screen). `TestProfiles::test_the_current_profile_carries_the_SERVERS_own_answer` fails
against the old code; `test_an_unknown_current_profile_fails_closed` pins the other half.

⚠ **Why every check was green anyway:** every harness stub supplied `current.is_admin = true` — a
payload the server was **incapable of producing**. Same family as §6e: a stub cannot reveal what the
real code does, and a check that cannot fail is documentation. The stubs now mirror the server.

### The UI consolidation (his second request, same message)

ONE account menu (`frontend/src/features/auth/AccountMenu.tsx`), opened from the **avatar**: an
identity block (monogram · name · role · *"signed in as X"* only when the profile differs from the
account) over **Switch profile · My password (every profile) · Household (administrators only) ·
Sign out**. The items are a pure rule, `accountDestinations(isAdmin, profileSelected)`, behind the ONE
`mayManageHousehold` gate, so the surfaces cannot drift. The header is one control now (the name span,
the static avatar, the "Switch profile" link and the "Sign out" button are gone); the sidebar footer's
decorative identity card became the same menu (`variant="wide"`, name/role/chevron only at `xl`); and
the sidebar nav + the mobile "More" sheet are **navigation only** — nothing duplicated anywhere.

**Screenshots for his eyeball:** `/workspace/rkm-ux-shots/account-menu-*.png` and
`mobile-sheet-navigation-only.png`.

### ⚠ Two harness faults this exposed (they affect EVERY future UI check)

1. **`frontend/harness/nav-frame.tsx` loaded NO stylesheet** (the other four frames do). Text
   assertions passed while every screenshot and geometry measurement of that frame was *unstyled* —
   the account menu measured 1424px wide, and the mobile "More" button was clickable at a desktop
   width where CSS hides it. It imports `../src/styles/index.css` now.
2. Therefore the mobile scenarios must run on a **phone viewport**, and `open_frame` must wait for the
   **header** (the sidebar's `nav[aria-label="Primary"]` is `hidden md:flex` — it times out on a phone).

`tools/check_nav_access.py` now proves the menu from every trigger in **5 scenarios** (falsified by
opening the gate: `mayManageHousehold` true for a member fails both member surfaces);
`check_profile_picker.py` and `check_login_flow.py` were updated to open the menu, since they looked
for a standalone "Switch profile" link and "Sign out" button.

### Waiting on HIM, in order

1. **Deploy both containers** (see the table above).
2. **Sign in as `rkm`** → the avatar menu must offer **Household** (this is the regression).
3. **Household screen** lists the accounts; **My password** still opens from the menu.
4. **Pick a member's profile** → the menu must NOT offer Household, and My password must still be
   there. That is the whole admin-only rule, on one surface, in one place.
5. Then the queue continues at **#2 — stale-token degrade** (a Jellyfin 401 still reads as "that
   current password is not correct"; the honest degrade is "switch profile again", and per-session
   device ids would stop the app rotating its own tokens away — `PLEX_PROFILE_AUTH_PLAN.md` §4e);
   after that #3 `reset-admin-password`, #4 his throwaway-stack test, #5 merge (51 commits), #6 Phase E.


## ▶ LATEST SESSION (2026-09-13) — THE IDENTITY RAIL IS IN (queue item #1) · next = item #2 (stale-token degrade) · everything stays on `feat/auth-multiuser`  → ✅ **SAME SESSION, LATER:** his first live look found Household hidden from the ADMIN too (`064df72`, plan §6g) and asked for the account-menu consolidation — both done; see the block above.

**His instruction, verbatim:** *"continue from progress.md in rkm-cinema app"* — take up the queue at
the top of this file. Item **#1 (guard the identity fallback)** is now DONE, committed (`b4c5c47`) and
pushed. `main` is still `c0ae65e`; **nothing is merged** — he asks for merges.

| | |
|---|---|
| Branch | `feat/auth-multiuser`, worktree CLEAN, local tip == remote tip (`b4c5c47` + this record) |
| Ahead of `main` | **49 commits** — `main` is still `c0ae65e`, fully contained here |
| Gates | **958 backend pytest** (+23) · ruff clean · openapi **53 paths** (unchanged) · docs links resolve · **no frontend change → no web deploy** |
| His deploy | `docker compose -p rkm-bundled up -d --build api` (api ONLY) |

### What landed — the CLASS, not the route (plan `ADMIN_CREDENTIALS_PLAN.md` §6f)

§6e fixed the ONE route; this makes the failure IMPOSSIBLE rather than merely unwired.
`api/session.py` now RECORDS the session a request resolved (`session_context_from_request`, the one
place a cookie becomes a session), and `acting_media_token()` / `acting_user_id()` /
`acting_profile_is_owner()` raise **`UnpublishedIdentityError`** instead of falling back when a
request arrived as somebody and nothing published it. Three states, three answers — and the two that
must NOT change are unchanged: **no request context at all** (the provisioner, the scheduler's jobs,
every tool, unit tests) and **a request that arrived as NOBODY** (a normal anonymous request while
`RKM_AUTH_REQUIRED=false`) both still use the app's own key. `owner_media_token()` is the one
deliberate exception — its fallback IS the administrator's own credential, and every call it serves
is server administration.

Two supporting changes it required:

* **`jellyfin.py::_api` now defaults to the OWNER's credential**, with `credential="acting"` left for
  the ONE call that must act as a person — `change_own_password`. Account administration on a
  member's token earns a 403 from Jellyfin (`/Users` is administrator-only), so the picker would have
  been told *"there are no profiles on this server"*; and on the OWNER's credential a self-change
  would stop checking `CurrentPw` at all, i.e. an escalation. Pinned by an AST test: no other method
  may ask for the acting identity.
* **The façade may not contain the rail** (`service.py::_rethrow_identity_rail`). Its
  `except Exception` handlers exist to contain provider failures, and they had turned the rail's
  refusal into *"the media server refused the password change"* — blaming the server for our own
  wiring.

### Falsified, not asserted (the house rule)

Guard removed → `test_forgetting_to_publish_fires_the_rail_instead_of_writing` fails with his
2026-09-12 report **verbatim**: `/Users/Password on 'app-key-ADMIN' targeting ['uid-first'] — the
session had uid-kid selected`. So the test does not merely describe the rail: without it, the write
really does reach the media server on the elevated key, aimed at whichever account is listed first.
Guard restored → 22/22 green.

### ⚠ A GUARD THAT COULD NOT FAIL — found while writing the per-route test

FastAPI **0.141** keeps every `include_router` as an `_IncludedRouter` on `app.routes`, and the
sub-routes carry paths WITHOUT the prefix. So `test_every_api_route_publishes_a_identity` — whose
entire job is to stop a NEW router shipping without `SESSION_SCOPED` — was inspecting **ZERO** routes
and passing (the old code read `route.path` off objects that have no `.path`). It now enumerates
through `include_context` (prefix + include-level dependencies) and `original_router`, **asserts it
found ≥ 40 routes**, and was falsified by dropping `SESSION_SCOPED` from the config router (it names
`/api/config`). **Any future test that enumerates framework objects must assert it found something.**

### New tests worth not re-deriving

* `backend/tests/test_identity_rail.py` (22) — the rail unit by unit, the provider's REAL fallbacks
  (the substitute identity only exists there: a fake library never falls back), the AST credential
  pin, and **every `/api/auth/*` route driven over real HTTP with a live cookie**, asserting no call
  may act on a Jellyfin user id the session did not choose — the general shape of the bug. It stubs
  the media server at the `urllib` layer so the real routers, session store, contextvars and provider
  are what is under test.
* `test_profile_identity.py::_api_route_inventory()` — the route enumerator (see the warning above).

### Waiting on HIM

1. **Deploy the api**: `docker compose -p rkm-bundled up -d --build api`.
2. **The two-minute pass**: sign in → pick a profile → **My password** → change it → sign out → pick
   that profile → the new password is asked for. Then Household → every row still lists (that path
   now runs account administration on the owner's credential).
3. If anything looks wrong, send the log line: `docker compose -p rkm-bundled logs api |
   Select-String "identity rail"` — it names the route, the profile and what to fix. Nothing in the
   shipped code should ever produce it.

### The rest of the queue is untouched

**#2 stale-token degrade** (a Jellyfin 401 surfaces as "that current password is not correct"; the
honest degrade is "switch profile again", and the ~20 `Invalid token` lines in one second point at
per-session device ids — `PLEX_PROFILE_AUTH_PLAN.md` §4e) · **#3 Phase 4** `rkm-cinema.ps1
reset-admin-password` + the OPERATIONS runbook · **#4 Phase 1's fresh-install test on a throwaway
stack** (only he can run it) · **#5 merge to `main`** (49 commits, when he asks) · **#6 Phase E +
Phase 5** (the 401/403 sweep, ADR-0006, the docs truth pass) · and the XS one: `BROWSER_RADARR_URL` /
`BROWSER_SONARR_URL` point at `:7878`/`:8989` while the bundled compose publishes `:7879`/`:8988`.


## ▶ NEXT SESSION — START HERE: the auth workstream is COMPLETE and CONFIRMED · next = the identity/token hardening pass (#1) · everything stays on `feat/auth-multiuser`  → ✅ **ITEM #1 DONE 2026-09-13** (the identity rail, `b4c5c47`, plan §6f) — the rest of the queue below stands as written.

**His instruction, verbatim:** *"update the progress.md to take it up in the next session...commit and
merge all the changes to feature branch not the main"* — so: record the queue, commit, push, and
**do NOT merge to `main`**. He asks for merges explicitly.

---

### State at hand-off (2026-09-12/13)

| | |
|---|---|
| Branch | **`feat/auth-multiuser`**, worktree CLEAN, local tip == remote tip (`35c3480`) |
| Ahead of `main` | **46 commits** — `main` is still `c0ae65e` and is fully contained in this branch (nothing to merge in, nothing merged out) |
| Confirmed working by him | profile picker · per-profile libraries · per-profile watch state · rename + Administrator badge · **My password** · Household set/reset · navigation gating |
| Only outstanding deploy | the nav change (`16391fc`) is frontend-only → `docker compose -p rkm-bundled up -d --build web` |
| Gates at hand-off | **935 backend pytest** · ruff · **274 vitest** · tsc · build · **5 browser checks** (`check_household_ui`, `check_profile_picker`, `check_login_flow`, `check_password_change`, `check_nav_access`) · openapi **53 paths** · docs links resolve |

**Commits of the final round:** `14c06bf` the root-cause fix (auth route not session-scoped) ·
`16391fc` nav gating + mobile menu · `35c3480` its record. Plan sections to read first:
`docs/ADMIN_CREDENTIALS_PLAN.md` **§6c** (`ResetPassword: true` is destructive) · **§6d** (a 2xx is not
evidence) · **§6e** (⚠ THE ROOT CAUSE: a silent fallback substituted a different identity).

---

### THE QUEUE — in priority order (risk first, not size)

**1. Guard the identity fallback** — the provider must **never** substitute `_user_id()`'s "first
account on the server" lookup when a session exists but no identity was published. This is the exact
bug that cost the last two sessions: one mis-wired route silently wrote a password to the wrong
person's account, and it looked intermittent because the "first account" moves as profiles are made.
Fix the CLASS: a route that should act as somebody must fail **loudly** instead of acting as a
stranger. Suggested shape: a contextvar flag set wherever a session is resolved, checked in
`_user_id()`/`_api_token()`; plus a test per session-bearing route. **Effort M, value highest.**

**2. Stale-token degrade** — when Jellyfin answers 401 the app currently surfaces it as the nearest
human message, which for the password screen is *"that current password is not correct"* (wrong, and
confusing). The honest degrade is **"switch profile again"**. Same family: Jellyfin's log showed ~20
`"Invalid token"` errors in one second — the app hammering a token that its own next login rotated
away. Consider **per-session device ids** (`PLEX_PROFILE_AUTH_PLAN.md` §4e) so the app stops killing
its own tokens. **Effort M.**

**3. Phase 4 — `rkm-cinema.ps1 reset-admin-password`** from the API key in the `rkm_shared` volume,
plus the OPERATIONS runbook. The break-glass: today, a forgotten administrator password is a manual
recovery. **Effort S–M.**

**4. Phase 1's fresh-install test on a throwaway stack** — the ONE path never executed. **Only he can
run it** (no Docker in the sandbox). Own project name, own ports, empty volumes, then `down -v`:

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
$env:RKM_PROJECT="rkm-test"; $env:RKM_DASHBOARD_PORT="8125"; $env:RKM_JELLYFIN_PORT="8099"
# bootstrap, confirm the printed-once admin password works, then:
Remove-Item Env:\RKM_PROJECT, Env:\RKM_DASHBOARD_PORT, Env:\RKM_JELLYFIN_PORT
docker compose -p rkm-test down -v
```
⚠ Never run this against the real stack; it needs no library scan in progress.

**5. Merge to `main`** — 46 accepted commits. Do it when HE asks (and per the repo procedure: FF the
feature branch → `main`, then FF `experiment/bundled-docker-stack`, push all three; the PROGRESS
record lands on `main` afterwards, leaving `main` deliberately one commit ahead).

**6. Phase E + Phase 5** — the 401/403 sweep across every router, **ADR-0006**, and the docs truth pass
(`ARCHITECTURE.md`, `OPERATIONS.md`, `README.md` still describe pre-auth behaviour). Prerequisite for
him *arming* `RKM_AUTH_REQUIRED` — the app is open to anyone who can reach it today, which is his
explicit opt-in choice, not an oversight.

**XS, noticed while checking the ports:** `BROWSER_RADARR_URL` / `BROWSER_SONARR_URL` point at
`rkm-hp.tail8d5e8.ts.net:7878` / `:8989` while the bundled compose publishes **7879** / **8988** on the
host. Those two dashboard links likely refuse from the tailnet.

---

### Open follow-ups already recorded in code/plan (do not re-derive)

* the identity-fallback lesson and its generalisation — plan §6e;
* `docs/ADMIN_CREDENTIALS_PLAN.md` §6b — the 401/403 → "wrong password" mapping was confirmed live,
  but a *stale token* now produces the same message, which is item 2 above;
* `frontend/harness/README.md` documents every harness (nav, password, household, profile, login);
* the queue landed on a live server measurement each time — **measure before fixing**, this workstream
  has repeatedly shown that unit tests pass while a feature does nothing (929 passed while the
  password write was a no-op).

### Live server state (if the next session needs it)

Accounts: `rkm` (administrator, renamed from `admin`), `meenu`, `raj`. `.env` carries
`RKM_JELLYFIN_ADMIN_USER=rkm` with a working password (he updated it) — that is what lets the agent's
tools read the server. **Password state:** `raj` = `RAJ1234` (set by this session's proof, then
restored); `meenu` = his own value. `tools/probe_password_write.py` is the read-only-first verifier
for any future password work.

## ▶ NEXT SESSION — START HERE: password work is MID-FLIGHT — 4 fixes pushed, HIS RETRY + ONE LOG LINE still outstanding  → ✅ **RESOLVED 2026-09-12/13** (root cause found and fixed, `14c06bf`; he confirmed it works). Kept for the diagnostic detail it carries — see the block above.

**His instruction, verbatim:** *"record the session issues....we will take up in the next session
this session is too long · record ur findings and issues in progress.md to take it up later"*

**Branch:** `feat/auth-multiuser`, working tree CLEAN, everything pushed. `main` untouched at
`c0ae65e`. Nothing is merged — he asks for merges.

---

### ⚠ DO THIS FIRST NEXT SESSION (two questions for him, nothing else matters until they are answered)

1. **After deploying, did My password on `rajeev` work?** Deploy =
   `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema` then
   `docker compose -p rkm-bundled up -d --build api web`.
2. **If it still fails, the api log names the answer:**
   `docker compose -p rkm-bundled logs api | Select-String "auth.password|password verification"`
   * the `target id=` in that line is the account the change was made against — compare it with the
     account table below; if it is the administrator's id, the cause is a session with NO profile
     chosen (the owner fallback), and the rail added in `be5c282` should now refuse that anyway;
   * the verification failure logs the exception **class**: `InvalidCredentialsError` = the server
     REFUSED the new password (the change really did not take) · `AuthUnavailableError` = we could not
     ask, i.e. a false alarm.

### 🔬 LATE FINDINGS (2026-09-12, after his "intermittent" report) — one real hole, one real clue

His report: *"its like a intermittent behavious sometime it chnages sometimes not... for profile meenu
i could change the password but now i cant change the password for raj"*, with the payload
`{current_password: "RAJ1234", new_password: "raj1234"}` and the response
`{ok: true, confirmation: "refused"}`.

**Measured: a case-only change is NOT the problem.** Driven against the live server through the app's
own code path: `RAJ1234 -> raj1234` → POST 204 → the OLD password stops working and the NEW one logs
in. Jellyfin's passwords are case-sensitive and it applies the change.

**Ruled out too:** session limits and remote access — `MaxActiveSessions=0`, `EnableRemoteAccess=true`
on `meenu`, `raj` and `rkm`.

**Hole found in our OWN verification (fixed):** the name used to sign in came from the SERVER when the
lookup worked, but fell back to the session's remembered name when it did not — and that falls back to
the **OWNER**. So a failed lookup could sign in as a DIFFERENT account, be refused, and report
*"refused"* about a change that had landed. Intermittent by construction. Now: **no server-resolved
name means no check at all** (`confirmation: "unavailable"`), never a guess.

**Real clue in Jellyfin's log** (same window): a burst of ~20
`CustomAuthentication was not authenticated. Failure message: "Invalid token."` lines within one
second — the app hammering Jellyfin with a **stale session token**. That is the known per-device token
rotation (`docs/PLEX_PROFILE_AUTH_PLAN.md` §4e): every login of a device+user invalidates that pair's
previous token, and the app signs in on ONE device id for everyone. Separate from the password work and
worth its own pass: when Jellyfin answers 401, the app should degrade honestly ("switch profile again")
rather than looking broken.

**THE ANSWER (measured, read-only): the change landed on the WRONG PROFILE.** Login tests with the
value he typed: `raj + 'raj1234'` refused, `meenu + 'raj1234'` **LOGS IN**, `rkm + 'raj1234'` refused.
So his "raj" change went to **meenu** — the PROFILE IN EFFECT at the time — and two things hid it: the
check was unreliable (it could sign in as the owner, now fixed) and nothing in the answer said which
account was changed. Now the response carries `name` and the screen says *"Password changed for
meenu."* / *"…accepted the change for meenu but could not confirm it."* on EVERY outcome, so a wrong
target is visible the moment it happens.

⚠ Open question for him: whether the app was showing meenu (the screen's label names the account) or
the session was on meenu from earlier. The label + the named answer together make it self-evident now.

**What settles the remaining question:** the api log line now names the account it checked —
`auth.password accepted: target id=<id> name=<name> confirmation=<state>`. For a failing attempt:
`name='raj'` + `refused` = the sign-in genuinely failed for that account (a real problem to chase);
`name=''` + `unavailable` = we could not name it and deliberately did not check.

### ✅ HE CONFIRMED THE PASSWORD WORK ("seems to be working now") + two nav requests, both done

After `14c06bf` he confirmed it works. He then asked for two things, shipped in `16391fc`:

1. **"household path should not be available to non admin users"** — the desktop sidebar offered
   Household to EVERYONE (on the reasoning that the server's 403 explained itself). Now gated on the
   profile in effect being an administrator, via `mayManageHousehold()` (fails CLOSED while the
   server's answer is unknown). The server still refuses the routes — this only decides what the app
   offers.
2. **"and also it should be available on ui"** — the MOBILE "More" sheet had **no route to Household
   or My password at all**; both screens existed only in the desktop sidebar. Both are now there, with
   Household gated the same way.

The admin fact comes from the same `["auth","profiles"]` payload the picker and My-password screen
read (`useCurrentProfile`) — the server's answer, not an inference from a name.

New browser check **`tools/check_nav_access.py`** over `frontend/harness/nav-frame.tsx`: administrator
sees Household on both surfaces, a member sees it on neither (keeping My password), and a member's
navigation fires **zero** `/api/admin/*` calls. Falsified: with the gates opened, the member scenario
fails on both surfaces. `frontend/harness/README.md` documents the new frame.

⚠ Still open from this round (unchanged): a stale profile token surfaces as "that current password is
not correct" — the honest degrade is "switch profile again"; and a guard so the provider can never
substitute the first account when a session exists but no identity was published.

### 🎯 ROOT CAUSE FOUND AND FIXED (2026-09-12): the auth route was not session-scoped

`POST /api/auth/profile/password` lives on the auth router, which is deliberately NOT session-scoped
(sign-in must work signed out), so no dependency published the session contextvar for it. The provider
therefore fell back to **the app's API key** (elevated ⇒ the write always "succeeded") and to
`_user_id()`'s **first-account-on-the-server** lookup ⇒ **the change was applied to whichever profile
was first in `/Users` order** (`meenu`, `raj`, `rkm` → `meenu`). The route's name/verification read the
session from the REQUEST, so it reported on the right account while the write went elsewhere.

* Proof: `raj + 'raj1234'` refused · **`meenu + 'raj1234'` logged in** · `rkm + 'raj1234'` refused.
* Why it looked intermittent: the first account changes as profiles are made and removed.
* Fix: publish the session around the provider call (`set_current_session` … `finally reset`), plus a
  routing-layer regression test that drives the REAL provider and asserts the target id and the
  credential — **it fails without the fix**.
* Proven end-to-end locally against the live server: change → `{"ok": true, "confirmation":
  "verified", "name": "raj"}`, old password stops working, new one logs in.

⚠ **Follow-up worth doing:** a stale profile token now surfaces as "that current password is not
correct" (Jellyfin answers 401 for both). The honest degrade is "switch profile again". Also consider a
guard so the provider can never substitute the first account when a session exists but no identity was
published — "no context" is right for tools/provisioner and wrong for a write acting as a person.

### ✅ CONFIRMED BY HIM (end of session, 2026-09-12): the password flows work end to end

His words: *"i removed the old profile and tried with creating new profiles and it seems to work, i can
create password for individual profiles after admin creates the profiles...change the password...watch
progress is recorded correctly"*. That is the whole model working: the administrator creates accounts,
each profile sets and changes its OWN password, and watch state stays per profile.

**Why fresh accounts behaved and the old ones did not** — accumulated wreckage, not one bug: the old
accounts were created while the destructive `ResetPassword: true` was live (passwords wiped / set to
values nobody knew), their sessions held profile names from before a rename, and this session's own
probes had put probe passwords on `rajeev`/`sharanya`. A new account starts clean.

**Still open (do not close the phase on this alone):** the api container's verification login — the
advisory `confirmation` now reports it honestly (`unavailable`), and the log names the exception class.
It no longer blocks anything, so it is a diagnostics item, not a blocker.

**Hostname caveat for testing (recorded 2026-09-12):** `localhost`, a LAN IP and
`rkm-hp.<tailnet>.ts.net` are three different cookie jars — the session is per-hostname, so he signs in
once per hostname. Nothing about the fixes depends on which one he uses: the api container is always
Jellyfin's client, so Jellyfin's local/remote decision is identical either way.

### 🔴 LATEST FINDING (end of session): the change LANDS — the VERIFICATION was the thing lying

His log proved the targets are **correct** (`rajeev` / `sharanya` ids, not the administrator's),
Geetanjali **succeeds**, and rajeev + sharanya fail at the **verification** step. Then this session
measured that `sharanya` — `has_password: False` in the table below when he tried — **now HAS a
password**: the change landed and the check reported otherwise. A FALSE NEGATIVE, twice.

So the verification is **ADVISORY, never a gate**. The route returns **200** with the answer carried
back as a fact:

```
{"ok": true, "confirmation": "verified" | "refused" | "unavailable"}
  verified    -> "Password changed."
  refused     -> the server would NOT sign in with the new password (likely not applied)
  unavailable -> we could not ask; nothing is known either way -> amber wording, never "not applied"
```

An **absent** confirmation is NOT success (that default was a lie in the other direction). The screen
shows the amber wording for the last two, and `confirmationMessage()` in
`frontend/src/features/settings/password.ts` owns that wording (unit-tested both ways).

⚠ **Still unknown:** why the api container cannot complete the verification login while the same call
from the sandbox succeeds with the exact same header, device id and password (measured). The build now
logs the exception **CLASS** — `password verification refused|unavailable for '<name>': <Class>` — so
the next attempt names it. **Do NOT revert to blocking on the verification.**

### The account table (read-only, from the live server, 2026-09-12)

| name | has_password | admin | folders | id |
|---|---|---|---|---|
| `rkm` (renamed from `admin`) | True | **True** | 0 (sees all) | 1760c9b0… |
| Geetanjali | True | False | 1 | b556e3f2… |
| rajeev | True | False | 3 | 96ad5947… |
| sharanya | False | False | 1 | bbae2602… |

⚠ **`rajeev` currently has the password `AppPath-Bbb2`** — this session's probes set it to a known
value to measure. Change it from Household, or ask the agent to clear it. `rkm` and Geetanjali are
untouched. `.env` already carries `RKM_JELLYFIN_ADMIN_USER=rkm` (he updated it — that is what let
this session read the server at all).

---

### What this session established (each one MEASURED, never inferred)

**1. `ResetPassword: true` is destructive — the original "Set a password does nothing" bug.**
Jellyfin 10.11.11 returns **204, sets NOTHING, and CLEARS a password that existed**; the working body
is `ResetPassword: false` (an administrator resetting a password it does NOT know works too — the
caller's privilege authorises it, not the flag). The codebase believed the opposite. Fixed in
`6e34438`: the flag is gone from provider/ABC/facade, and the write now re-reads to confirm.
→ Full matrix: `docs/ADMIN_CREDENTIALS_PLAN.md` §6c.

**2. The self-change path works; the OWNER fallback is the dangerous one.**
With the profile set in the session, the app's own `change_own_password()` lands (verified by logging
in). With **no** profile set, every call falls back to the OWNER — so a change could be reported that
landed on the **administrator's** account while the screen showed a member's profile. Rails added:
`be5c282` refuses a password change when the session has no profile (409, "Choose a profile first").
→ §6d.

**3. A session remembers the account's NAME from when the profile was selected — and that name was
used to verify the change.** This is the answer to *"it works for geetanjali but only doesn't work for
rajeev"*: `rajeev` was renamed at some point, Geetanjali never was, so the verification signed in under
a name the server no longer has and refused a change that may have landed. Fixed in `1000bbe` (the api
resolves the name from the server, **by id**) and `a978f87` (the screen labels the account with the
server's current name). Same class as the Phase 2 rename trap, one surface further out.

**4. A 2xx from Jellyfin is not evidence.** The screen said "Password changed" while nothing had
changed; the route now **proves** it by signing in with the new password, on its own
`rkm-password-verify` device (never the app's device — Jellyfin rotates a `(device, user)` token on
every login, and verifying on it would kill the session asking). Failure is reported as what was
measured ("could not be confirmed"), never as a conclusion.

**5. The password-in-the-Network-tab question, answered.** A browser must send the password for the
server to check it; it appears in the Network tab for ANY web login form (Jellyfin's own UI, Plex,
Gmail). What matters, all verified in this app: never in a URL/query string · never in
`localStorage`/`sessionStorage` · never written to logs (pinned by a test) · never echoed in a
response · masked on screen. **The real caveat is plain HTTP on `:8124`** — loopback-only on his
machine, encrypted over the tailnet; it would need TLS in front if ever exposed beyond that.

---

### Open issues to pick up

1. **rajeev's My-password result** — awaiting his deploy + retry (see the two questions above). The
   stale-name fix probably resolves it, but it is **NOT confirmed** — do not claim it works.
2. **Stale names in other surfaces.** The header chip and the picker show the session's remembered
   `profile.name`, so a rename made elsewhere leaves them stale too. Candidate follow-up: resolve the
   display name server-side wherever a profile name is shown, or refresh the session's stored name on
   activation. (`rename_identity` in `services/auth.py` already updates the CURRENT session — this is
   about OTHER sessions/devices.)
3. **Phase 1's fresh-install test on a throwaway stack** — still never run (no Docker daemon in the
   sandbox). Own project name, own ports, empty volumes, then `down -v`.
4. **Phase 4** — `rkm-cinema.ps1 reset-admin-password` from the volume key + an OPERATIONS runbook.
   More valuable now: it is the break-glass when nobody knows the administrator's password.
5. **Phase 5 / Phase E** — ADR-0006, the 401/403 enforcement sweep, docs truth pass, PROGRESS record.
6. **Enforcement is still OFF** (`RKM_AUTH_REQUIRED=false`): a signed-out visitor still sees the app.
   Arming it stays HIS explicit opt-in.

### Tooling added this session (reusable, read-only by default)

`tools/probe_password_write.py` — prints what Jellyfin holds for every account; with
`--target X --password Y` it drives the **app's own** `set_user_password()` and confirms by logging in
with the new value. It is the verifier for any future password work. It speaks JSON properly now (its
first version 415'd itself, and the tool now shouts when it sees a 415 so its own bug can never be
mistaken for the app's).

### Commits this session (all pushed on `feat/auth-multiuser`)

`57dd122` Phase 3 "My password" · `0b8ee20` its record · `09d466a` picker lock cache ·
`6e34438` the destructive password flag · `11eaa91` its record · `0e2c38d` prove the change ·
`be5c282` refuse without a profile · `1000bbe` verify with the server's name · `a978f87` show the
server's name · **then the end-of-session round: the advisory confirmation (`confirmation` field +
`confirmationMessage`), prompted by his log showing the verification had been reporting false
negatives** — see LATEST FINDING above.

**Gates at hand-off:** 933 backend pytest · ruff clean · 266 vitest · tsc + build clean · openapi 53
paths (unchanged) · docs links resolve · `check_password_change.py` 4/4, `check_household_ui.py` 4/4,
`check_profile_picker.py` + `check_login_flow.py` green.

### The lesson worth carrying (it cost a full live round-trip per combination)

**Every unit test passed — 900+ of them — while the feature did nothing on a real server.** A 2xx from
`/Users/Password` was never evidence, and neither was re-reading `HasPassword` (true already when an
account had a password, so it cannot tell a real change from a silent no-op — that misread cost one
whole round). The only proof is **logging in with the value you just set**. Same family as the
`/Sessions/Playing*` trap (204, stores nothing).

## ▶ NEXT SESSION — START HERE: the password bug is FIXED (`6e34438`) — his live "set a passwo  → ✅ **SUPERSEDED 2026-09-12 by the block above** (the verification and the stale-name fixes landed after it, `1000bbe` + `a978f87`); kept for its detail — strd" never worked · next: deploy api+web, then Phase 4

**His report (verbatim):** *"password for user profile rajeev didn't work...when i set a new passord..it
says password changed but when i switch profile it doesnt have the lock icon and i can login just by
clicking on the rajeev profile"* and *"i have logged in as admin(rkm) -> clicked the side bar ->
household-> set a password in rajeev -> it still says no password"*

### The root cause, MEASURED on Jellyfin 10.11.11 (never guessed)

```
ResetPassword: true   -> HTTP 204, sets NOTHING, and CLEARS a password that existed   ← what we sent
ResetPassword: false  -> HTTP 204, the password is really set                          ← works, always
```

Proof method: every combination driven against a real account, each verified by **logging in with the
intended value** — never by the status code. An administrator resetting a password it does NOT know
works with `false`; a member's own change works with `false` (403 when their current password is
wrong). **The administrator's privilege authorises the reset, not the flag.**

The codebase believed the opposite, and that belief is written into `set_user_password`'s docstring
today minus the fix. That single wrong flag is the whole bug, and it was making "Set a password" wipe
passwords set elsewhere — so the same account could be "set" repeatedly and still have none.

**Changed** (`backend/services/library/{jellyfin,service}.py` + tests): `ResetPassword: false` always,
the `reset` parameter **deleted** through provider/ABC/facade (a flag that must never be true should
not be passable), and the write now **proves itself** — after the 2xx the provider re-reads the
account and reports success only when a password is really there. `tools/probe_password_write.py` is
the repeatable verifier: read-only by default, `--target X --password Y` drives the app's OWN code and
confirms by logging in.

**Verified live:** the app's own `set_user_password()` set a member's password, `has_password` flipped
true, and a real login with the new value succeeded.

⚠ **Every unit test passed while this feature did nothing on a real server** (929 of them). Only a
live round-trip per combination showed it — the same lesson as `/Sessions/Playing*` (204, stores
nothing). When an endpoint's 2xx is in doubt, RE-READ the state it claims to have changed.

### ⚠ Two things he must know

1. **`rajeev` currently has the password `Temp-Change-Me-123`** — set by this session's diagnosis, not
   by him. He should change it in the app (My password) once he has deployed, or it can be cleared.
2. A rename/password change in the UI leaves `.env` stale: he renamed the admin `admin` → **`rkm`** and
   updated `RKM_JELLYFIN_ADMIN_USER` accordingly ✔ (which is what let this session measure anything).

### Waiting on HIM

1. **Deploy**: `docker compose -p rkm-bundled up -d --build api web` (this fix is api; the picker's
   lock-cache fix `09d466a` is web).
2. Then: Household → `rajeev` → Set a password → the row should say **Reset password** afterwards
   (the label follows `has_password`), and the picker should show a **lock** on that profile; picking
   it should then ask for the password.
3. Still outstanding: **Phase 1's fresh-install test on a throwaway stack** (never run) and **Phase 4**
   (`rkm-cinema.ps1 reset-admin-password` from the volume key + OPERATIONS runbook) — Phase 4 matters
   more now: it is the break-glass when nobody knows the administrator password.

### Commits on `feat/auth-multiuser` (pushed; `main` still `c0ae65e`)

`09d466a` picker lock-cache fix · `6e34438` the password-flag fix · `57dd122`+`0b8ee20` Phase 3
(My password) · `8233012`+`3c3207f` Phase 2 (rename) · `bc018e1`+`ba301a2` Phase 1 (no password in
`.env`) · `5e303e0`+`f5574de` Phase C (identity threaded) · 4 accounts on the server: `rkm` (admin),
`Geetanjali`, `rajeev`, `sharanya`.

## ▶ NEXT SESSION — START HERE: admin credentials — Phase 3 ✅ BUILT (`57dd122`, "My password") · next Phase 4 (reset-admin-password CLI)  → ✅ **SUPERSEDED 2026-09-12: the password bug it describes is FIXED (`6e34438`)**; kept for the Phase 3 detail it carries

**His instruction:** *"go phase 3"* — Phase 3 of `docs/ADMIN_CREDENTIALS_PLAN.md` §6 (self-service
password). Committed `57dd122`, pushed on `feat/auth-multiuser`; `main` still untouched at `c0ae65e`.

### What landed (17 files, +1169/−8; contract 52 → 53, additive)

**`POST /api/auth/profile/password`** — the one screen every profile has. Until now a password could
only be changed by an ADMINISTRATOR (Household → Reset password), for somebody else. A member's
password IS their Jellyfin credential and the lock on their profile; they had no way to change it.

* **One credential rule**: the target is the PROFILE in effect (`context.profile_id()`), and the
  provider's `change_own_password(current, new)` takes **no user id at all** — there is no parameter
  a caller could fill in with somebody else's account, so "change my own" cannot become "change
  theirs". `ResetPassword: false` **always** (that flag is the administrator's path and would be an
  escalation here); sending the OLD password is what makes it a genuine self-change.
* **Facade delegation** added (`LibraryService.change_own_password`) — the trap this workstream has
  paid for twice: a provider-only capability raises `AttributeError` on every route call and the
  admin gate reports that as "you are not an administrator".
* **Rails**: session required · non-empty new password · the OLD one required whenever the account
  has one, with **Jellyfin as the judge** · neither value logged, echoed or returned.
* **Two deliberate NON-rules**: a whitespace-only password is ALLOWED (Jellyfin accepts it; forbidding
  it here would be a second implementation of the server's contract — the trap that once made
  password-less accounts unable to sign in) and there is **no length rule**. Only a truly empty value
  is refused: the app's model is an account *created* without a password, not emptied afterwards.
* **Frontend**: `features/settings/password.ts` (pure rules) + `PasswordView.tsx`, route
  `/settings/password`, sidebar **My password** (every profile). The current-password field is
  required only when the SERVER says the account has one — a password-less account is never blocked.

### A real bug the new browser check found (not theorised)

With a 502 and **no response body**, the screen showed `POST /auth/profile/password -> 502` — the
HTTP client's own fallback, in front of a person. Structural cause: `ApiError` carried no way to tell
the server's `detail` from that fallback, so a screen could only string-match. **Fixed at the
source**: `ApiError` now carries `detail: string | null` (the server's own words, or null), and the
screen shows the server's words when it has them, its own when it does not — *"…your old password
still works"*, because a refusal must never read as a lockout. The client's own 9 tests still pass
(the change is additive).

### Evidence (all green)

**927** backend pytest (**+14**, all 14 verified to FAIL against the pre-change source) · **266**
vitest (**+17**) · ruff, tsc, `npm run build` clean · openapi **53 paths**, additive · docs links
resolve · **`tools/check_password_change.py` 4/4** — A: required while the account has one, blank and
mismatch refused **before any request**, the good case posts exactly `{current_password,
new_password}` · B: a password-LESS account sets one and is never blocked · C: a 401 reads as "that
current password is not correct" and echoes neither value · D: a refusal that is not a typo is not
blamed on the user, including when the server says nothing · `check_household_ui.py` 4/4 ·
`check_profile_picker.py` + `check_login_flow.py` unchanged.

### ⚠ Waiting on HIM, in order

1. **Deploy** — `docker compose -p rkm-bundled up -d --build api web` (new route *and* new screen).
   Then sidebar → **My password**: set/change a password as a member, sign out, pick that profile —
   it should now ask for the new one.
2. **The two-minute test that settles the one unproven thing** (plan §6b): change a member's password
   with a deliberately **wrong** current password (expect *"that current password is not correct"*),
   then with the **right** one (expect it changes). This confirms Jellyfin's 403 really means "wrong
   password" for a self-change rather than "not allowed". **Do NOT** disambiguate by signing in as the
   profile again — that rotates the app device's token for that user and breaks the session asking.
3. **Phase 1's fresh-install test on a throwaway stack** is still pending (never run) — `.env`-free
   admin password, own project name/ports/empty volumes, then `down -v`.
4. Then **Phase 4**: `rkm-cinema.ps1 reset-admin-password` from the volume key + OPERATIONS runbook.

### Workflow lesson paid for this session (vite, again)

The check ran against a **pre-edit** vite twice: `--strictPort` made each NEW vite die silently while
an OLD one held `:5199`, and **killing the background wrapper does not kill the `node …/vite` child**.
The tell was the check's own stale-check (`curl … | grep -c <new identifier>` = 0) — without it, D's
failure would have been misread as a code bug. Always: `kill -9 $(ss -ltnp | grep 5199 | grep -oP
'pid=\K[0-9]+')`, confirm the port is free, start ONE vite, then grep the SERVED module for a string
that only exists after the edit.

## ▶ NEXT SESSION — START HERE: admin credentials — Phase 2 ✅ BUILT (`8233012`, rename) · next Phase 3 (self-service password screen)  → ✅ **PHASE 3 ALSO BUILT 2026-09-12** (`57dd122`); kept for the Phase 2 map it carries

**His instruction:** *"step 2 is working as intended proceed with phase 2"* — i.e. **Phase C accepted on RKM-HP**
(the picker, the per-profile library grants and per-profile watch state all confirmed by his own eyeball), then
Phase 2 of `docs/ADMIN_CREDENTIALS_PLAN.md`.

### Waiting on HIM, in this order

1. **Deploy Phase 1 + Phase 2 — api AND web** (Phase 2 changed both):
   ```powershell
   cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
   .\rkm-cinema.ps1 status
   docker compose -p rkm-bundled up -d --build api web
   ```
   Then **Settings → Household**: each row now has **Rename**. Rename the `admin` account to his own name — the
   **Administrator** badge must stay on that row, the top-bar chip must change with it, and the picker must show
   the new name. A blank name, the account's own current name, and a name another account already has are all
   refused on the spot with the reason (no request is sent). Nothing else about the account changes: not its
   libraries, not its password, not its watch state.
2. **Phase 1's fresh-install half still needs his throwaway-stack test** (no Docker daemon here) —
   `ADMIN_CREDENTIALS_PLAN.md` §7. Unchanged from the previous pointer, still not run.
3. Then **Phase 3 — say go**: the self-service "change my password" screen for every profile (Phase D's other
   half), then Phase 4 (`reset-admin-password` recovery from the volume key) and Phase 5 (ADR + docs).

### What landed (Phase 2, `8233012`)

* **`POST /api/admin/users/{id}/rename`** (contract **51 → 52**, purely additive) → provider `rename_user()` →
  Jellyfin's `POST /Users?userId=`. Two traps were MEASURED from the server's own contract (315 paths, live):
  * the target is a **QUERY** parameter, not a path segment — the same query-vs-path trap the password route
    already paid for;
  * the body is a `UserDto`, which carries **`Policy`**. Since `/Users/{id}/Policy` is known to REPLACE all 47
    fields, a `{"Name": …}` body would wipe `IsAdministrator` **if** `POST /Users` shares those semantics — a
    **LOCKOUT**. The payload carries the id, the name **and the policy the server just reported**, so it is
    correct under EITHER semantics; `HasPassword` is deliberately never sent.
* **A silent trap of its own:** a session stores the NAME it was handed and nothing re-reads Jellyfin per
  request, so the header chip would have kept the OLD name after a rename. The route now calls
  `SessionStore.rename_identity()` for the session making the request; **another device corrects itself at its
  next profile selection** (a name is display — tolerable; a token would not be).
* **UI:** a **Rename** action + inline panel per household row, with the pure rails (`renameIssue`) mirroring the
  server so a refused rename is disabled WITH the reason before any request. **No client-side length or
  character rule on purpose** — that would be a second implementation of the server's contract, the trap that
  once made a password-LESS account unusable.
* **Rails, each with a test:** 401 anonymous · 403 a non-administrator (the shared gate, which also refuses while
  somebody else's profile is selected) · 404 unknown id · 400 blank name · 409 duplicate · 502 when the server
  refuses (never a false success) · same-name rename is an idempotent no-op that reaches no server · a rename
  never touches a password.

### Evidence

* **913 backend pytest (+14)** — the rename set verified to **FAIL against the pre-change source** — **249
  vitest (+6)** · ruff, tsc, build clean · openapi **52 paths**, additive only · docs links resolve.
* `tools/check_household_ui.py` **4/4**: its new scenario D proves a REFUSED rename sends no request, a good one
  sends **only** the name, and the **Administrator badge survives** the rename of the admin account itself.
* `check_profile_picker.py` and `check_login_flow.py` unchanged and green (vite restarted, served module
  verified, port released).

### Honest gaps

* **`POST /Users` semantics are still unproven** — the read-modify-write is safe under both readings, but which
  one Jellyfin implements needs a no-op rename against the live server, and that WRITES to his account, so it
  needs his consent. Ask before doing it.
* The **fresh-install path** (§7) and the **compose change's semantics** are still unverified (no Docker here).
* `RKM_JELLYFIN_ADMIN_USER` in `.env` is unaffected by a rename: it is a **first-run hint** only. If he ever
  re-provisions from an EMPTY volume, the wizard would use the hint and create a second, differently-named
  administrator — worth one sentence if he asks what the env var still does.

## ▶ NEXT SESSION — START HERE: admin credentials — Phase 1 ✅ BUILT (`bc018e1`) · next Phase 2 (rename + role) · and Phase C still needs HIS deploy  → ✅ **PHASE 2 ALSO BUILT 2026-09-12** (`8233012`); kept for the map and the Phase 1 detail it carries — see the block above

**His instruction:** *"yes build it now"* → Phase 1 of `docs/ADMIN_CREDENTIALS_PLAN.md`. Earlier in the same
session he revised the fresh-install decision (*"fresh install will create a admin with password.. which
bootstrap.ps1 will let the user know so that it can record it and in that way there will be no fear of loosing
the password"*), which **deleted the plan's riskiest phase** (see the rejected-design note in that plan's §4).

### Waiting on HIM, in this order

1. **Phase C's deploy + eyeball is still outstanding** — api only, and it is already proven live:
   ```powershell
   cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
   .\rkm-cinema.ps1 status
   docker compose -p rkm-bundled up -d --build api web
   ```
   Expected: sign in → **Who's watching?** → his profile (password again) → switch to **Geetanjali** → sidebar
   shows only `Movies`, Continue Watching is hers, and a TV title cannot be opened even by URL.
2. **Phase 1's FRESH-INSTALL half needs HIS throwaway-stack test** — the sandbox has no Docker daemon, so it
   was not run. Recipe and the 5 things it must prove are in `ADMIN_CREDENTIALS_PLAN.md` §7 (own project name,
   own ports, own empty volumes, then `down -v`). Nothing he cares about is at risk there.
3. Then **Phase 2 — say go**: `Settings → Household` gains an **Administrator** badge, the account's real name,
   and **rename** (`POST /Users?userId=`).

### What landed (Phase 1)

* **Bootstrap no longer needs the admin's password at all.** `ensure_admin()` picks a credential in order:
  (1) the **stored API key** from `/shared/runtime.json` — what every run after the first one takes, so a
  password the user later changed cannot break a bootstrap; (2) the **configured password** (the optional
  `.env` override); (3) the **startup wizard** on a genuinely fresh install, which GENERATES a strong password,
  sets it, and **prints it ONCE** — after the wizard step AND an authentication with it, so the console can
  never announce a password that was not actually set, and nothing is written to any file.
* **The generation moved** out of `render_config` (which runs on every bootstrap and cannot tell a fresh
  install from a re-run) into `provision.py::run_startup()`, which knows it is creating the account because
  that is what it is doing. `render_config` no longer generates or writes the key — **that write-back is
  exactly why deleting the line from `.env` never stuck** — and compose's `:?` gate (which REFUSED to start
  the provisioner without a value) is now `:-`.
* **The administrator is resolved BY POLICY** (an enabled `IsAdministrator`), never by the literal name
  `admin`: `RKM_JELLYFIN_ADMIN_USER` is now a first-run hint. That is what makes the **rename** safe to add in
  Phase 2.
* **Docs that would otherwise have started lying**, updated in the same commit: the `bootstrap.ps1`/`.sh`
  first-run messages (they told the user the password is saved to `.env`), `scripts/restore-rkm-state.ps1`
  (after a restore the password is the RESTORED account's, not `.env`'s), the expected deploy output in
  `OPERATIONS.md`, README's two claims, and `.env.example` (documented as optional, with the reason).

### Evidence

* **899 backend pytest (+12)** · ruff clean · docs links resolve (39 files) · compose parses, no `:?` left.
* **14 of the new tests were verified to FAIL against the pre-change source** — the whole credential ladder,
  the policy-not-name resolution, and the "never generated or written" `render_config` rule.
* NOT verified here: the fresh-install path (no Docker daemon) and the compose change's SEMANTICS (no docker
  CLI) — both are on his box in step 2 above. Say so whenever this phase is described.

### What did NOT change

* `.env` may KEEP its current `RKM_JELLYFIN_ADMIN_PASSWORD` value — harmless, the stored key wins — and it can
  be deleted at any time; nothing requires it. Setting it still overrides everything (it is also what the
  local Python tools sign in with).
* The **api never received** the password and still does not: its credential is `JELLYFIN_API_KEY`.
* `RKM_AUTH_REQUIRED` untouched; **Phase E** (the 401/403 sweep + ADR-0006) still belongs to
  `PLEX_PROFILE_AUTH_PLAN.md`, and Phases 3–5 of the credentials plan are the self-service password screen,
  the `reset-admin-password` recovery command, and the docs/ADR pass.

## ▶ LATEST SESSION (2026-09-12) — PLEX PROFILE AUTH PHASE C: THE IDENTITY IS THREADED ✅ (branch `feat/auth-multiuser`, commits `3c08e65` + `5e303e0`; **api only — no frontend file changed**; nothing merged)

**His instruction:** *"start phase c from progress.md in rkm-cinema"* — the plan's §7 row C, the phase that
makes the profile model real rather than cosmetic.

### What landed

* **Every media call now goes out as the SELECTED PROFILE.** ONE rule decides the credential
  (`api/session.py::acting_media_token`) and two kinds of caller use it: the provider
  (`JellyfinLibraryProvider._api_token` — behind ALL 21 `api_key=` URL builds) and the four routes that build
  a raw upstream URL (`jellyfin_stream`, `jellyfin_tracks`, both `jellyfin_hls`). `acting_user_id()` sources
  the Jellyfin user id from the SAME session, so the id and the token cannot disagree.
* **Two calls stay the administrator's ON PURPOSE, both non-content** (`owner_media_token`): reading the
  server's library LIST (the display metadata a profile's own views are enriched with) and triggering a
  library-wide scan. Neither returns an item, a position or a watched flag.
* **The seam had to be ARMED: `require_session` was referenced by NO route** — nothing ever published the
  contextvar, so the threading alone would have changed nothing. It is now a router-level dependency of every
  app router (`api/main.py::SESSION_SCOPED`), health + auth excepted, with a structural test that fails if a
  new router forgets it.
* **Sidebar = the profile's GRANTS.** A profile's libraries come from its own `/UserViews`
  (`/Library/VirtualFolders` is **403** for a non-administrator — measured), enriched with
  `collection_type`/`path` from the folder list the app already holds, then filtered down to the views. New
  pure helper `media_libraries.visible_libraries()`: an UNGRANTED configured library is OMITTED (not reported
  as a config fault) and a granted library absent from `.env` still shows under the server's own name.
* New tool **`tools/prove_profile_isolation.py`** — the phase's acceptance, measured live (below).
* The plan gained **§4d** (the measurements) and **§4e** (the bug the proof found); row C is marked ✅.

### ⚠ A bug the live proof found, and it was SILENT

The proof's FIRST run failed *"the administrator's sidebar is whole again"*: after switching back to his own
profile, `/api/library/folders` returned **empty** and the api log said
`Jellyfin library_folders failed: HTTP Error 401`. Cause — **Jellyfin invalidates the previous token for a
device+user on every login**, and the app signs in on ONE device id (`rkm-cinema-web`), so the administrator
selecting their OWN profile re-authenticates as them on this device and kills the token the session has held
since sign-in. `set_profile()` kept the owner token by design (Phase A's rule), so the session then held a
DEAD one: every administrator-level call 401'd while the acting token stayed valid — which is why item detail
and Continue Watching kept working and NOTHING raised. Fix: `set_profile(..., owns_session=…)` replaces the
owner token when, and only when, the switch authenticated as the account owning the session; the store checks
the id itself, so a mismatched flag cannot write a member's token over the administrator's credential.
**Known limit, recorded not fixed** (§4e): because every app session signs in on the same device id, signing
in twice (phone + laptop) rotates the token under the first session; it needs per-session device ids.

### Evidence (all measured)

* **887 backend pytest (+80)** · ruff clean · tsc clean · **243 vitest** · vite build · openapi **51 paths**
  (only a route docstring changed) · docs links resolve (38 files).
* The new suite `backend/tests/test_profile_identity.py` (76 tests) was run against the PRE-change source and
  **36 of them FAILED** — including the guard that drives EVERY provider media method with a profile selected
  and asserts every URL it builds carries that profile's token, plus its fail-safe mirror (no session ⇒ the app
  key, exactly as before).
* Browser checks unchanged and green: `check_profile_picker.py` **6/6** · `check_login_flow.py` **4/4** ·
  `check_household_ui.py` **3/3** (vite restarted on :5199, served module verified, port released after).
* **`tools/prove_profile_isolation.py` = 24/24 against the LIVE server**, two real accounts (`admin`, and
  `Geetanjali` — non-admin, no password, granted `Movies` only): her sidebar is `['Movies']` vs his
  `['Movies', 'TV Shows', 'Movies Kids']` with `warnings=[]`; the TV item requested **by id, typed by hand**
  is **404** for her and **200** for him; a resume position written as her appears in HER Continue Watching
  (1 row) and **NOT** in his (10 rows, that item absent); everything reverted, the temporary API key deleted,
  the probe devices purged. The api for that run was local with `WATCHLIST_DB_PATH=/tmp/…`, so nothing was
  written into the household's real state.
* **The second user EXISTS and is already granted**: created from the app's own Household screen, exactly as
  he decided — no account was created by this session.

### ⚠ DEPLOY + EYEBALL — api only (no frontend file changed)

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 status
docker compose -p rkm-bundled up -d --build api
```

api-only on purpose: `up -d --build api` cannot cancel an in-flight library scan, and there is no frontend
change to ship. Expected at http://localhost:8124 — **Sign in** as the administrator → **Who's watching?** →
his profile (password again — decision 3) → the app as before, then **Switch profile** → **Geetanjali**: the
sidebar shows **only `Movies`** (TV Shows and Movies Kids gone, not greyed), Continue Watching is **hers**, and
a TV title cannot be opened even with its URL typed by hand. Switch back with his password: everything returns.

⚠ **If he was signed in on RKM-HP while the proof ran**, that session's token was rotated (same app device id
— §4e) and it will need a fresh sign-in. The proof itself leaves nothing behind.

### Honest state after this session

* **Per-profile watch state, resume, watched flags and LIBRARY ACCESS are now ENFORCED** — the point of the
  phase. A member's folder grants are real: Jellyfin refuses an ungranted item on every URL shape this app
  builds.
* Still true, unchanged: **the app is OPEN when nobody is signed in** (`RKM_AUTH_REQUIRED=false` is his
  deliberate opt-in, and no default was flipped). Arming it is Phase 2/E; `/api/health` and sign-in stay
  reachable even then (pinned by a test that arms the flag).
* **Phase D is next**: Settings → Household gains *rename* (`POST /Users?userId=`) and the profile's own
  *change my password* (`CurrentPw` + `NewPw`). Then **Phase E**: the 401/403 sweep, ADR-0006, and the docs
  truth pass (ARCHITECTURE/OPERATIONS/README still describe pre-auth behaviour).

## ▶ NEXT SESSION — START HERE: Plex profile auth — Phase C (identity threading, the phase that makes it real)  → ✅ **DONE 2026-09-12** (commits `3c08e65` + `5e303e0`; kept for the map it carries)

**Plan:** `docs/PLEX_PROFILE_AUTH_PLAN.md` §7. **Phase A ✅ `78f139e` · Phase B ✅ `af8033c` — both pushed**
on `feat/auth-multiuser`; nothing merges until he asks.

### Waiting on HIM, in this order

1. **The household fix from `61d6b67` is STILL not deployed** (independent of this plan).
2. **This session's Phase B needs a deploy + eyeball — api AND web** (Phase B added one api field):
   ```powershell
   cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
   .\rkm-cinema.ps1 status
   docker compose -p rkm-bundled up -d --build api web
   ```
   Expected at http://localhost:8124 — the app opens signed-out EXACTLY as before (nothing is
   enforced); top bar → **Sign in** → the Jellyfin admin credentials → **"Who's watching?" appears**
   (that is new: sign-in now asks); HIS profile shows a **lock** and asks the password again (that IS
   decision 3 — plan §4c, do not "fix" it by weakening the rule); then the app as before, his name in
   the chip, and **Switch profile** in the top bar brings the picker back. **Household** should now
   list accounts (that is the `61d6b67` fix riding along).
   ⚠ **If he was already signed in on that browser**, a session from Phase 0/1 has no profile, so the
   picker appears on the next page load. That is the feature working, not a bug.
3. **Then Phase C — say go.**

### Phase C (the riskiest, and the one that matters)

`acting_token()` through the provider's `_token()` seam (21 `api_key=` sites, 18 `build_library_service`
call sites — the contextvar seam exists so this is ONE diff point), a profile's libraries from its own
`/UserViews`, and **the live two-profile proof**: two real profiles with different watch positions —
resume a title as one and show the other does NOT see it; a profile granted only `Movies` gets an
empty/404 for a TV item even when the item URL is typed by hand. The SECOND Jellyfin user is created
from the app's own Household screen (his decision), so Phase C can start the moment that exists.
Mint any tooling key on its **own** device id — Jellyfin rotates a device's token on every login.

### The map (nothing to re-derive)

* Repo `/workspace/projects/rkm-cinema` (= his `D:\hermes_agent\hermes-workspace\projects\rkm-cinema`),
  branch **`feat/auth-multiuser`**, working tree clean, all pushed; **`main` untouched** (`c0ae65e`).
* Phase table `docs/PLEX_PROFILE_AUTH_PLAN.md` §7: **A ✅ · B ✅ · C ⏭ NEXT · D · E.**
  Phase C = identity threading · D = rename + the profile's own change-my-password · E = the 401/403
  sweep + ADR-0006 + docs.
* ⚠ **Phase A's route table is aspirational — read §4a before looking for routes that are not there.**
  Shipped: `GET /api/auth/profiles`, `POST /api/auth/profile` (that is the whole of "the picker").
  NOT built: `DELETE /api/auth/profile` (not needed — switching back IS `POST /api/auth/profile` with
  the admin's password), `POST /api/auth/profile/password` and `rename` (both Phase D).
* Gates before every commit in this workstream:
  ```bash
  cd backend  && python -m pytest -q && python -m ruff check .
  cd frontend && npx tsc --noEmit && npx vitest run && npm run build
  python3 backend/scripts/snapshot_openapi.py   # 51 paths is the current state
  python3 tools/check_md_links.py
  cd frontend && npx vite --port 5199 --strictPort &   # kill the PID holding 5199 FIRST
  python3 tools/check_profile_picker.py && python3 tools/check_login_flow.py
  ```
  ⚠ Restart vite after ANY source edit AND confirm the SERVED module is the edited one —
  `curl -s localhost:5199/src/features/profiles/ProfilesView.tsx | grep -c profile-picker`.
* Six traps this workstream has already paid for — do not repeat them:
  1. **A new provider capability needs a FACADE delegation** (`services/library/service.py`), or the
     route raises `AttributeError` and the gate reports it as "not an administrator".
  2. **A test fake must mirror what the ROUTE receives** (the facade's shapes), not what the provider
     returns.
  3. `grantable_rows()` (`api/session.py`) is the ONE shape handler — do not inline the isinstance
     dance again.
  4. Vite serves stale modules on this mount (both false FAILs and false PASSes come from it).
  5. Never offer an admin route to a non-administrator profile, and never arm `RKM_AUTH_REQUIRED` for him.
  6. **A "you shouldn't be here" redirect is a claim about INTENT** — the header's *Switch profile*
     bounced straight off the picker's own redundant-visit rule until a deliberate `?switch=1` made the
     two visits distinguishable. Keep that distinction when Phase C touches navigation.

### The honest state of the whole feature (say this, do not oversell it)

* The picker, the lock badges, the password prompt, the switcher and the admin-only server login are
  **real**, and the picker's trigger is a SERVER fact (`profile_selected`), not a remembered click.
* **Per-profile watch state, resume, watched flags and LIBRARY ACCESS are still NOT enforced** — every
  media call goes out on the ADMIN's credential until **Phase C threads the identity**. A member's
  folder grants are cosmetic today; the new picker must not be read as making them real.
* Nothing is enforced: a signed-out visitor sees the whole app exactly as before. Arming
  `RKM_AUTH_REQUIRED` remains his explicit opt-in (`.env` + `--force-recreate api`).
* Platform limit, recorded in code: Jellyfin has **no impersonation** — a profile's password is what
  lets the app act as it; the administrator's path to a forgotten one is **reset**, never bypass.

## ▶ NEXT SESSION — START HERE: Plex profile auth — Phase B (the "Who's watching?" picker)  → ✅ **BUILT + PUSHED 2026-09-12** (`af8033c`; see the record below). The deploy + eyeball it was waiting on is now in the pointer ABOVE this one.

**Plan:** `docs/PLEX_PROFILE_AUTH_PLAN.md` (four decisions taken by the user 2026-09-12, all built
into Phase A). **Phase A is DONE and pushed** — `78f139e` (backend, contract 49 → 51).

### Two independent things are waiting on HIM

1. **The household fix from earlier is still not deployed** (`61d6b67`): `docker compose -p
   rkm-bundled up -d --build api web`, then Household must list accounts. Independent of this plan.
2. **Phase B is the picker UI** — say go.

### Phase B (next, frontend)

Per the plan §7: a "Who's watching?" screen after sign-in, a lock badge on a protected profile, a
disabled profile greyed out, a password prompt, a header profile switcher, and the guard sending a
signed-in session with no profile to the picker. Verifier: `tools/check_profile_picker.py` over a
harness, the same shape as `check_login_flow.py` / `check_household_ui.py`.

Routes Phase B consumes (all live on `78f139e`):
* `GET  /api/auth/profiles` → `{profiles: [{id, name, is_admin, has_password, disabled, last_login}],
  current: {id, name}, warning}`
* `POST /api/auth/profile` `{user_id, password}` → `{ok, profile, libraries: [{id, name}]}`
* `GET  /api/auth/me` → `{user, profile, on_own_profile, expires}`

⚠ **The picker must not offer `/api/admin/libraries` to a non-administrator profile**: that route is
refused the moment somebody else's profile is selected (decision 3). A profile's libraries come from
the `POST /api/auth/profile` response, which already resolves them to names.

### Continue here — the map (so nothing has to be re-derived)

* Repo `/workspace/projects/rkm-cinema` (= his `D:\hermes_agent\hermes-workspace\projects\rkm-cinema`),
  branch **`feat/auth-multiuser`**, tip **`e820e6f`**, working tree clean, all pushed; **`main` is
  untouched** and nothing merges until he asks.
* The phase table lives in `docs/PLEX_PROFILE_AUTH_PLAN.md` §7. One line each, so this file is enough
  to pick up from:
  * **A ✅ `78f139e`** — administrator-only login, profiles list + select, owner/profile session, `me.profile`.
  * **B ⏭ NEXT** — the picker UI, header switcher, guard change, `tools/check_profile_picker.py`.
  * **C** — **identity threading**: `acting_token()` through the provider's `_token()`; a profile's
    libraries from its own `/UserViews`. **This is the phase that makes folder grants real.**
  * **D** — Household gains **rename** (`POST /Users?userId=`) and the profile's own
    "change my password" (`CurrentPw` + `NewPw`).
  * **E** — the 401/403 sweep, ADR-0006, docs, record.
* What Phase B touches: `frontend/src/features/auth/*` (provider/guard/login), `frontend/src/app/router.tsx`,
  `frontend/src/app/layout/Header.tsx` (switcher), a new `frontend/src/features/profiles/*`,
  `frontend/harness/profile-frame.*`, `tools/check_profile_picker.py`. **The backend needs no changes
  for B** — every route it uses is live and tested.
* Gates before every commit in this workstream:

  ```bash
  cd backend  && python -m pytest -q && python -m ruff check .
  cd frontend && npx tsc --noEmit && npx vitest run && npm run build
  python3 backend/scripts/snapshot_openapi.py   # only when routes change (49 → 51 is the current state)
  python3 tools/check_md_links.py
  ```

* Five traps this workstream has already paid for — do not repeat them:
  1. **A new provider capability needs a FACADE delegation** (`services/library/service.py`), or the
     route raises `AttributeError` and the gate reports it as "not an administrator". That cost a live
     wrong answer on 2026-09-12.
  2. **A test fake must mirror what the ROUTE receives** (the facade's shapes — `library_folders()`
     returns a dict), not what the provider returns, or a whole class of bug passes the suite and fails
     live.
  3. `grantable_rows()` (in `api/session.py`) is the ONE shape handler. Use it; do not inline the
     isinstance dance a third time.
  4. Vite serves **stale modules** on this mount: kill the PID holding the port before believing any
     DOM check, or the measurement is of pre-edit code (both false FAILs and false PASSes come from this).
  5. Never offer an admin route to a non-administrator profile, and never arm `RKM_AUTH_REQUIRED` for him.
* Phase C's proof — the one that actually matters, and the one to write into the block when it lands:
  with **two real profiles** holding different watch positions, resume a title as one and show the
  other does NOT see it; and a profile granted only `Movies` must get an empty/404 for a TV item even
  when the item URL is typed by hand. Mint any tooling API key on its **own** device id — Jellyfin
  rotates a device's token on every login, so a key minted on the app's device id dies at the next sign-in.

### The honest state of the whole feature (say this, do not oversell it)

* Profile selection, the admin-only login and the shared-device rule are **real** and backend-enforced.
* **Per-profile watch state, resume, watched flags and LIBRARY ACCESS are not yet enforced** — every
  media call still goes out on the ADMIN's credential, so a member's folder grants are display-only
  until **Phase C threads the identity** (`profile_token` through the provider's `_token()` seam).
  The contextvar seam, `SessionContext.acting_token()` and `grantable_rows()` are all in place for it.
* Arming `RKM_AUTH_REQUIRED` stays his explicit opt-in (`.env` + `--force-recreate api`).
* Platform limits, recorded in code: Jellyfin has **no impersonation** (a profile's password is what
  lets the app act as it; the administrator's path is RESET, never bypass), and with an administrator
  account that has NO password a deliberate non-empty attempt still succeeds — the blank refusal is a
  check on intent there, which is why the picker only shows a lock when one exists.

## ▶ LATEST SESSION (2026-09-12) — PLEX PROFILE AUTH PHASE B: "WHO'S WATCHING?" ✅ BUILT (branch `feat/auth-multiuser`, commit `af8033c`; **api AND web — ONE additive field**; nothing enforced, nothing merged)

**His instruction:** *"for rkm-cinema pickup next from progress.md"* — i.e. execute the plan's next
phase. Sign-in now asks who is watching, and the answer is a server fact.

### What landed

* **Backend, ONE additive field** (`+10/−0`, contract **51 paths unchanged**): `me()` and
  `/api/auth/profiles` report **`profile_selected`**. ⚠ **The plan's §7 row B claimed "frontend:" and
  that was FALSIFIED while building it** — `SessionContext.profile_id()` falls back to the OWNER, so
  "nobody chosen yet" and "the administrator chose themselves" were byte-identical payloads. Without
  a server fact the picker's trigger could only be a remembered click, and the session lasts 30 days
  across tabs and devices. Rejected alternative (sessionStorage) recorded in the plan's new **§4b**.
  3 tests, each verified to **fail against the pre-change source** (stashed the two source files and
  ran them: 3 failed).
* `frontend/src/features/profiles/{lib.ts,lib.test.ts,ProfilesView.tsx}` — the picker, OUTSIDE the
  shell like `/login`; a row per profile carrying only the SERVER's facts (lock, disabled + the
  reason, "Watching now" only when `profile_selected`); an inline password prompt; Sign out (nobody
  is trapped). Pure rules + 17 tests.
* `features/auth/lib.ts` — `guardDecision` gained a **third answer**: signed in with no profile ⇒
  `picker`. `profileSelected` is a **required** input, so no caller inherits a default that silently
  means "admin". Plus `watchingName()`: the Header chip and Sidebar card name the **PROFILE** — the
  identity media actually runs as.
* `features/auth/AuthProvider.tsx` — `profile`/`profileSelected` state and `selectProfile()` (clears
  the React Query cache: the next person's rows must not flash); a fresh sign-in confirms against
  `me()` instead of assuming.
* `RequireSession` carries the interrupted deep link through the picker (`/profiles?next=…`);
  `LoginView` lands there after a sign-in; `/profiles` is a top-level route. `Header` gained a profile
  chip + **Switch profile**; `Icon` gained a Lucide `lock`.
* New verifier **`tools/check_profile_picker.py`** (6 scenarios) + `frontend/harness/profile-frame.*`;
  **`tools/check_login_flow.py` and `login-frame.tsx` were UPDATED** because the flow genuinely changed
  (sign-in → picker → app). The harness README documents both.

### Two bugs the checks caught before shipping

1. **"Switch profile" bounced straight back into the app.** `ProfilesView` sends a redundant visit home
   when somebody is already watching — which is exactly what the header link looked like. Fixed with an
   explicit `?switch=1`; scenario E now asserts the picker STAYS. Generalise: a "you shouldn't be here"
   redirect is a claim about INTENT, and a deliberate navigation must be distinguishable from an
   accidental one.
2. **The first `pick_profile` click hit the container, not a row** — `data-testid="profile-picker"` also
   starts with `profile-`, so the login check timed out on a prompt that never opened. Rows are now
   selected by `[data-profile-name]`.

### Evidence (all green, measured)

* **807** backend pytest (+3) · ruff clean · tsc clean · **243** vitest (221 → +22) · vite build green ·
  openapi **51 paths**, `+10/−0` additive (two boolean fields).
* `tools/check_profile_picker.py` **6/6** — (A) the picker is shown and **app content NEVER appears**
  (MutationObserver); locks only where the server needs one, including an administrator with NO password
  of its own; the disabled row is inert even to a programmatic click and says why; no row claims
  "Watching now" before a choice; **zero `/api/admin/*` calls** (that route is refused while somebody
  else's profile is selected). (B) a password-less profile posts `{"user_id":"uid-guest","password":""}`
  and lands as `Watching as Guest`. (C) a protected one asks FIRST (0 requests before the prompt), a
  blank and a wrong attempt both answer the generic message, the right one lands. (D) the owner's
  profile asks even with no password set. (E) a chosen profile goes straight to the app and the header
  switcher brings the picker back with `admin` marked. (F) disabled = no call at all.
* `tools/check_login_flow.py` **4/4** (updated): signed-out stays usable · a correct password now lands
  on the **PICKER**, then profile → app with the right chip · a BLANK-password account still signs in and
  picks its profile · the enforced world goes straight to the login view with app content never appearing.
* `tools/check_household_ui.py` **3/3** — no regression from the Header/AuthProvider changes.
* docs links: 38 files, 9 relative links resolve.
* ⚠ **Not verified visually.** `vision_analyze` failed twice on this provider (server disconnected), so
  the picker's LOOK is uneyeballed; the content assertions above are the evidence, and acceptance is his
  RKM-HP eyeball anyway.

### Honest state after this session

* The picker, the locks, the prompt, the switcher and the admin-only login are **real**, and the picker's
  trigger is a server fact.
* **Per-profile watch state, resume, watched flags and LIBRARY ACCESS are still NOT enforced** — every
  media call goes out on the ADMIN's credential until **Phase C threads `acting_token()`**. A member's
  folder grants remain cosmetic; the new screen must not be read as making them real.
* Nothing is enforced (a signed-out visitor still sees the whole app), and arming `RKM_AUTH_REQUIRED`
  stays his explicit opt-in.
* **New, deliberate cost:** on a fresh sign-in the administrator types their password TWICE — once to
  open the server, again to select their own profile — because a blank attempt on that profile is always
  refused. That IS decision 3, written into the plan's new **§4c** so a future session does not "fix" it
  by weakening the rule.

### ⚠ DEPLOY + EYEBALL (api AND web — Phase B added one api field)

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 status
docker compose -p rkm-bundled up -d --build api web
```
Expected: the signed-out app unchanged · **Sign in** → **Who's watching?** · his profile shows a lock and
asks the password again · the app as before with his name in the chip · **Switch profile** returns to the
picker · **Household** lists accounts (the `61d6b67` fix riding along).

**Phase status: A ✅ · B ✅ · C ⏭ NEXT · D · E.** Nothing merges to `main` until he asks.

## ▶ LATEST SESSION (2026-09-12) — PLEX PROFILE AUTH: PLAN + PHASE A (backend) ✅

**His spec, in his words:** *"Implement authentication similar to Plex, where only the admin controls
access to the RKM-Cinema server… Once the admin is authenticated, users can select their own profile
from the profile-selection screen… The implementation should be production-grade, secure, and
backend-enforced. User permissions must never rely solely on frontend UI restrictions."*

**Plan:** `docs/PLEX_PROFILE_AUTH_PLAN.md` (`120b22d`) — the model, the phase table, the honest
"already built vs cosmetic" table, and the measurements behind it.
**Phase A:** `78f139e` — backend, contract 49 → 51 (nothing removed), 804 backend pytest (+19).

### Four decisions he made (all implemented, none guessed)

1. **A profile's password IS its Jellyfin user's password** — no app-owned PIN store.
2. **`POST /api/auth/login` refuses non-administrators** — "only the admin can log in" is backend-true;
   the unused token is revoked rather than left live.
3. **The shared-device rule** — while somebody else's profile is selected, admin routes are refused and
   switching back needs the administrator's password (a blank attempt is always refused).
4. **The profile persists with the session** (30-day sliding), so a restart keeps a person on it.

### Two measurements that decided the design (not preferences — platform facts)

* **Jellyfin has NO impersonation.** The only user-scoped token endpoint is
  `/Users/AuthenticateByName`; `/Auth/Keys` is server-wide. So the app must authenticate AS the
  profile, the profile's password must be its Jellyfin password, and the administrator's recovery
  path for a forgotten one is **reset** (already built in 1b), never bypass.
* `UpdateUserPassword {CurrentPassword, CurrentPw, NewPw, ResetPassword}` → "a user changes their own
  password" is native and requires the old one (Phase D wires the screen).

### What is REAL today, and what is still display-only

* Real and backend-enforced: profile selection, the administrator-only login, the shared-device rule,
  the profile list sitting behind a session.
* **NOT yet enforced: per-profile watch state, resume, watched flags and library access.** Every media
  call still runs on the ADMIN's credential, so a member's folder grants are display-only until
  **Phase C threads the identity**. The seam is ready: `SessionContext.acting_token()`, the Phase 0
  contextvar, and `grantable_rows()`. The plan says this plainly, and so must any status report.
* Arming `RKM_AUTH_REQUIRED` remains his explicit opt-in.

### Cross-cutting fix carried in this session

`grantable_rows()` now lives in `api/session.py` — the facade-dict-vs-provider-list shape handler that
had 500'd `/api/admin/libraries` and would have 500'd the create-with-every-library grant. Both the
admin routes and the new profile routes use the ONE helper.

## ▶ NEXT SESSION — START HERE: deploy the household fix, create the member, then Phase 2  → ✅ the fix shipped (`61d6b67`); this pointer is SUPERSEDED by the PLAN BELOW — Plex profile auth is now the active workstream (`120b22d` plan, Phase A `78f139e`). The household deploy itself is STILL outstanding.

**The Household screen was BROKEN in the 1b build and is FIXED** — commit `61d6b67` (pushed).
He signed in as `admin` and the screen said *"Only a Jellyfin administrator can manage household
accounts"*. That was the app's fault, not his: the household methods existed on the provider but
not on the **facade** the routes are handed, and the gate reported the resulting `AttributeError`
as a permission problem. Read `docs/HOUSEHOLD_USERS_PLAN.md` §4a items 10–13 before touching any
of this — they are the two defects, the shape trap, and why the tests missed all of it.

### 1. He deploys the fix (api AND web)

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
docker compose -p rkm-bundled up -d --build api web
```

Then **Household** in the sidebar: sign in as `admin` if the chip is not already his name. Expected
now — an account list with `admin` (Every library), and `+ Add member` offering the real library
tick-boxes `Movies`, `TV Shows`, `Movies Kids`.

If instead he sees *"Could not reach the media server to check administrator rights"*, that is the
NEW honest answer (503) and it means the api cannot reach Jellyfin or has no credential — one
command says which, printing no secret:

```powershell
docker compose -p rkm-bundled exec api python -c "from config.settings import get_config as g; c=g(); print('url', c.JELLYFIN_URL); print('key', 'set' if c.JELLYFIN_API_KEY else 'EMPTY')"
```
and the reason is in the log: `docker compose -p rkm-bundled logs --tail 100 api` — look for
`administrator check could not ask the server`.

### 2. Then the 1b acceptance (his, unchanged)

`+ Add member` → the name he wants, **password left BLANK**, tick the folders → Create. That member
signs in with only their username and sees only their ticked libraries. `tools/diag_household_gate.py`
reproduces the whole admin path against the live server in one command if anything looks wrong.

### 3. Then Phase 2 — enforcement, as an EXPLICIT OPT-IN

Decided 2026-09-12 (see the block below and `.env.example`): **no default is ever flipped.** Phase 2
ships `RKM_API_TOKEN` for the machine callers (health stays public), fixes CORS for credentialed
requests, makes the guard real on every app path, and proves BOTH states live. Arming stays his act:

```powershell
# repo .env: RKM_AUTH_REQUIRED=true
docker compose -p rkm-bundled up -d --force-recreate api
```

⚠ Nothing merges to `main` until he asks. Branch `feat/auth-multiuser`, tip `61d6b67`.

## ▶ LATEST SESSION (2026-09-12) — THE HOUSEHOLD SCREEN BLAMED HIM FOR OUR BUG ✅ FIXED

**His report, verbatim:** *"i can login using admin and password but i cant create users it says
only Only a Jellyfin administrator can manage household accounts."*

He was right and the app was wrong. Two independent defects produced that one false sentence, and
the gate swallowed both:

1. **The FACADE.** The routes are handed `LibraryService`, a facade over the providers. The nine
   household methods had been added to `LibraryProvider` only, so EVERY route call raised
   `AttributeError` — which the admin gate caught and reported as "you are not an administrator".
   The facade now delegates all nine.
2. **The MESSAGE.** `is_administrator()` collapsed "not an administrator" and "could not ask the
   server" into one `False`. Now `admin_status()` → `True`/`False`/`None`, and the route answers
   **503** for `None` with the provider's `last_api_error` logged — 401 / 403 / 503 are three
   different truths and stay three answers.

**A third, found while proving it over real HTTP:** `library_folders()` is a **dict** on the facade
and a **list** on the provider, so `/api/admin/libraries` 500'd (`'str' object has no attribute
'get'`) and the create-with-every-library grant would have done the same. One `_library_rows()`
helper now reads either shape.

**Why 39 passing tests missed all of it:** the route tests replaced `build_library_service` outright
and the provider tests built the provider directly, so NOTHING exercised route → facade → provider.
Now there is `TestFactoryWiring` (builds the REAL service from config, drives it through the facade)
and the fake provider answers `library_folders()` in the FACADE's shape — changing that fake
immediately failed two more tests and exposed the third defect. **Make the fake mirror what the
route really receives, not what the provider really returns.**

**Proven against the real server** (local uvicorn, Jellyfin 10.11, read-only): `GET /api/admin/users`
→ 401 with no cookie, **200** with one (1 account, `admin`, no password in the body);
`GET /api/admin/libraries` → **200** with `Movies f137a2dd…`, `TV Shows 767bffe4…`, `Movies Kids
7e9b296e…`; and the shape test passes for both the facade dict and a provider list. The proof minted
its API key on an INDEPENDENT Jellyfin device: minting it by logging in on the app's own device id
is invalidated by the app's next login, because **Jellyfin rotates a device's token on every login**
— that trap cost a 401 detour here. Both test devices purged (204 each).

**New tool:** `tools/diag_household_gate.py` — prints what is ACTUALLY true (config, is the provider
built, does login work, what `list_users`/`get_user_policy` answer, which of the three gate answers
applies) so this takes one command to diagnose next time instead of reasoning from a message.

**Gates:** 785 backend pytest (+7) · ruff clean · tsc clean · 220 vitest · vite build · commit
`61d6b67` pushed. **He must redeploy** (`up -d --build api web`) — the fix is not live yet.

## ▶ NEXT SESSION — START HERE: auth Phase 1b deploy + eyeball, then Phase 2 (enforcement)  → ✅ 1b BUILT (`6b7008c` + `0ad2b2a`); its first deploy found the household bug, FIXED in `61d6b67` (see the block below)

**Phase 1b is BUILT and pushed** — `6b7008c` (backend + contract 44 → 49) and `0ad2b2a` (the
Household screen + browser check). Phase order was confirmed by the user 2026-09-12:
**1b (done) → Phase 2 (next) → Phase 3 → 4 → 5.**

### 1. His part first: deploy + eyeball 1b (api AND web changed)

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 status
docker compose -p rkm-bundled up -d --build api web
```

Then at http://localhost:8124 → **Household** in the sidebar (below Settings):

| Check | Expected |
|---|---|
| Sign in as `admin` | the chip and the sidebar card show `admin` |
| Household | you see `admin` with **Every library**, and the test user if one exists |
| `+ Add member` | name + **password left BLANK** + tick boxes (all ticked by default) |
| The real second member | create whoever he wants (no password) with the libraries he wants ticked |
| That member signs in | just the username, blank password; they see ONLY their ticked libraries |
| Remove on your own row | disabled, with the reason on screen |
| A non-admin at /settings/household | a plain "only a Jellyfin administrator" message |

**Nothing is enforced yet** (`RKM_AUTH_REQUIRED=false`), so the app still opens signed out and
every existing screen behaves exactly as before. If a member created in the app cannot sign in,
check the password was truly left blank — a password-less Jellyfin account signs in with a blank
password, and scenario D of `tools/check_login_flow.py` pins that the form allows it.

### 2. Then Phase 2 — enforcement (the lockout-risk phase)

> **DECIDED by the user 2026-09-12 — enforcement is an EXPLICIT OPT-IN.** He chose "the default
> stays `false`, and I add `RKM_AUTH_REQUIRED=true` when I want the lock" over "the release flips
> the default". So **Phase 2 must NOT flip any default** (compose keeps `:-false`, `settings.py`
> keeps `or "false"`, `.env.example` documents an active `RKM_AUTH_REQUIRED=false` with the
> arming command). The deliverable is a lock that **works when armed**, not one that **is**
> armed: prove both states live. Arming is HIS act (`.env` + `--force-recreate api`) — a future
> session that flips the default for him is undoing a deliberate decision.

`docs/AUTH_MULTIUSER_PLAN.md` §Phase 2. In order:
1. `RKM_API_TOKEN` for machine callers (`render_config.py` generates it like the admin password;
   sent as `X-RKM-Token`, compared with `secrets.compare_digest`) — **the PowerShell tooling
   touches `/api/health` and `/api/library/folders`**, so health stays public and folders takes
   the token.
2. CORS: `allow_origins=["*"]` + credentials is browser-INVALID → explicit `RKM_CORS_ORIGINS`
   list + `allow_credentials=True`.
3. Make the guard real on every app path **when armed — without arming it**: the default stays
   `false` (his opt-in, above), so this phase ships a lock that exists but is off.
   **`/api/health` stays public** (the api's own HEALTHCHECK calls
   `http://127.0.0.1:8000/api/health`, and the PS tooling calls it).
4. The 401 sweep test: every router refuses an unsigned caller, so a future router cannot
   silently ship unprotected.
5. Live proof: signed out → every app path 401; signed in → 200; `/api/health` 200 with no cookie.
6. **Escape hatch, verified:** `RKM_AUTH_REQUIRED=false` in the repo `.env`, then
   `docker compose -p rkm-bundled up -d --force-recreate api` — the api's env comes from the
   RENDERED `.rkm.env`, so the value is now interpolated by compose from the repo `.env`; and it
   never runs the provisioner, so it cannot cancel an in-flight library scan.

⚠ Do NOT arm enforcement until 1b has been eyeballed on RKM-HP: enforcement is the only step in
this workstream that can lock him out, and the login screen plus the household screen must both
be known-good first. Phase 2's commit will be on this branch; nothing merges until he asks.

## ▶ LATEST SESSION (2026-09-12) — AUTH PHASE 1b: HOUSEHOLD ACCOUNTS FROM THE APP ✅ BUILT

**What the user asked for, verbatim:** *"i want to create the second user without password"* and
*"can we make sure the user auth is identical to plex...where one user is the admin who needs to
authenticate first to get in and then it can create other users which have specifc access to
folder based on the selection the admin can do"* — **yes, and this is that**: the admin signs in,
then creates household members from inside the app and ticks which libraries each may see. The
only Plex difference is deliberate: identity is delegated to Jellyfin, so the same account also
works in Jellyfin's own phone and TV apps. What Plex has that we do NOT have yet: **sign-in is
still not REQUIRED** — that is Phase 2, deliberately last-but-one because it is the only step
that can lock him out.

**Shipped:** `6b7008c` (backend + contract) and `0ad2b2a` (screen + browser check).

* `backend/api/routes/admin_users.py` — five additive paths, **contract 44 → 49 (+300/−0)**,
  typed client +358/−0: users list, libraries list (the tick-box ItemIds), create, policy
  (folder access and/or enable-disable), password, delete (typed-name confirmation in the body).
* `backend/services/library/{service.py,jellyfin.py}` — the provider methods, shapes taken from
  the live probe rather than the docs; `mutate_user_policy()` is read-modify-write because
  `POST /Users/{id}/Policy` replaces the whole object.
* `api/session.py::require_admin_session` — session PLUS a live, per-call `IsAdministrator`
  and not-disabled check, strict even while the rest of the app is unenforced.
* `frontend/src/features/admin/*` + a sidebar **Household** entry + `tools/check_household_ui.py`
  and `frontend/harness/household-frame.*`.
* `docs/HOUSEHOLD_USERS_PLAN.md` gains §4a "As built" — including one honest limitation: in 1b
  these calls use the app's admin credential (per-request identity is Phase 3), so the route's
  own check is the only gate today and Jellyfin's 403 becomes the backstop only in Phase 3.

**Evidence:** 778 backend pytest (+32) · ruff clean · tsc clean · 220 vitest (+16) · vite build ·
`check_household_ui.py` 3/3 (admin world: names resolve, "No password" shows, Remove disabled on
your own row WITH the reason, typed name arms the button only on an exact match · non-admin:
refusal stated and NO write attempted · add member: blank password and only the ticked libraries
reached the API) · `check_login_flow.py` 4/4 · docs links resolve.

**Two bugs found by writing the tests, not by the user:** the delete-rails test asserted a case
that cannot happen (the last-admin rail is a *backstop* — the SELF rail is what protects the final
admin, and the route now says so), and the fake library shallow-copied a module-level list so
demoting an admin in one test poisoned every later one. Both were test-side; both are now honest.

**Decisions settled this session (user):** the new member is created **with NO password** (1c),
new members default to the creating admin's library access (2a), v1 = add + grant + disable +
reset + delete (3a), and the order is **1b → Phase 2** (the open 4th question, now confirmed).

**One consequence worth remembering:** the Phase 1 login form had `required` on its password
field, so the BROWSER would have blocked a password-less account's sign-in with no error anywhere.
Fixed in `401a3c7` and pinned by scenario D. A password-less account must **never** be an
administrator — anyone who can reach the app could otherwise manage accounts.

## ▶ NEXT SESSION — START HERE: auth Phase 1b (household accounts from the app), then Phase 2 (enforcement). Branch `feat/auth-multiuser`; plans `docs/AUTH_MULTIUSER_PLAN.md` + `docs/HOUSEHOLD_USERS_PLAN.md`.  → ✅ **BUILT 2026-09-12** (`6b7008c` + `0ad2b2a`; see the block below)

**Where things stand (2026-09-12):** auth **Phase 0 ✅** (`dd921ed`) · **Phase 1 ✅** (`b360b38`) · **Phase 1b SCOPED, NOT STARTED** (`HOUSEHOLD_USERS_PLAN.md`). **Nothing is enforced**, so the running stack behaves exactly as it did before any of this, and the only deploy outstanding is the user's WEB-ONLY one for Phase 1.

**THE USER'S DEPLOY FOR PHASE 1 (web only — the api did not change):**
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 status
docker compose -p rkm-bundled up -d --build web
```
Eyeball at http://localhost:8124: top bar → **Sign in** → the Jellyfin admin credentials; the sidebar card must show HIS name (it used to be hardcoded "Rajeev"); **Sign out** returns to the signed-out app, which still works — because enforcement is still OFF. Nothing else in the app should look different.

**Decisions already taken for 1b (user, 2026-09-12):** *his first answer was "1a 2a 3a", then he changed the password one* — **the new member gets NO PASSWORD (1c)**; new members default to the creating admin's library access (2a); v1 = add + grant + disable + password reset + delete (3a). A password-less account must **never** be an admin, and the app's login form already accepts a blank password (`b360b38`, scenario D of `tools/check_login_flow.py`). The 4th question (1b before or after Phase 2) was never answered — **this session took the recommendation: 1b BEFORE Phase 2**, so he can create the second account while the app is still permissive. Say so if that is wrong. → **CONFIRMED by the user 2026-09-12** (*"okey lets do it"*, quoting that recommendation): **1b → Phase 2 immediately after**.

**PLEX PARITY (user asked 2026-09-12: "is it what we are doing now?"):** yes — a single admin who signs in, then creates household accounts and ticks which LIBRARIES each one may see. Plex's per-library checkboxes are Jellyfin's `Policy.EnabledFolders` + `EnableAllFolders=false`, and Jellyfin enforces them server-side exactly as Plex does. The one deliberate difference: identity is DELEGATED to Jellyfin rather than an app-owned account store, so the same account also works in Jellyfin's own phone/TV apps. The Plex-like "you must sign in before the app works" step is **Phase 2 (enforcement)** and is NOT built yet — until it lands, the app is open on the tailnet as it is today.

**Next task = PHASE 1b** (`HOUSEHOLD_USERS_PLAN.md` §4): **1b.0** provider methods + `/api/admin/users{,/libraries,/{id}/policy,/{id}/password}` + DELETE — strict session **and** a LIVE `GET /Users/{session.user_id}` → `Policy.IsAdministrator` check (never a stored flag); the policy is **READ-MODIFY-WRITE** (47 fields are replaced wholesale); the password is used once and never stored/logged/returned; delete must refuse the LAST administrator. Contract 44 → 49 paths + typed client. **1b.1** the Settings → Household UI + `tools/check_household_ui.py` (mirrors `check_login_flow.py`). **1b.2** docs + record. The read-only probe `tools/probe_jellyfin_users.py` has ALREADY been run live — its numbers are in the plan; do not re-measure.

**Then PHASE 2** (enforcement + `RKM_API_TOKEN` + the 401 sweep test — the lockout-risk phase): the login UI has now shipped, which is what Phase 2 was waiting for. Keep `/api/health` public (the Dockerfile HEALTHCHECK calls it) and keep the admin token as the provider fallback.

**Lockout recovery — VERIFIED MECHANISM (measured in Phase 0):** the api's config is the RENDERED `.rkm.env`, so a bare `.env` edit + rebuild does NOT apply a new value; `docker-compose.yml` now interpolates `RKM_AUTH_REQUIRED` from the repo `.env`, so
`docker compose -p rkm-bundled up -d --force-recreate api` really does flip it — no render, no provisioner, so it cannot cancel an in-flight library scan.

**Per-user vs shared is decided (§4) — do not "fix" it:** watch state, resume, watched flags and library visibility per user (free from Jellyfin); subtitle PREFERENCES per user; subtitle USAGE counts and the watchlist stay **household-shared**.

**Gates every phase:** `cd backend && python -m pytest -q && python -m ruff check .`; plus `cd frontend && npx tsc --noEmit && npx vitest run && npm run build`; and for any auth/UI change, `cd frontend && npx vite --port 5199 --strictPort &` then `python3 tools/check_login_flow.py` (restart vite after editing source — the watcher does not fire on this mount).

**Also queued after this:** native Jellyfin collections (app-authored, visible in Jellyfin's own apps).
## ▶ LATEST SESSION (2026-09-12) — AUTH PHASE 1 OF 6: LOGIN VIEW, GUARD, SIGN OUT ✅ (branch `feat/auth-multiuser`, commit `b360b38`; **FRONTEND ONLY, nothing enforced — the app is unchanged for a signed-out visitor**)

**User instruction:** *"Let me know"* on the in-app household flow, answered with **"1a 2a 3a"** — and, earlier in the same session, *"wait the password do you have it or i need to provide you"*, i.e. he wanted to be sure the app asks HIM for a new member's password rather than expecting him to hand one to the agent. It does: the form is his, the value goes browser → api → Jellyfin once, and nothing is stored. This session then executed **Phase 1** (the plan's own order: the login UI ships BEFORE anything is enforced).

**What landed (`b360b38`, 15 files, +1137/−37 — no api, no contract, so the deploy is web-only):**
- `features/auth/lib.ts` + 12 tests: the guard rule (`guardDecision`) and the messages, pure. It needs TWO facts — do we have a session, and has the SERVER ever refused an app call — and only the second justifies taking the app away. That is how Phase 2 will arm the frontend **without a frontend change**: the first 401 is the signal.
- `AuthProvider` (keeps those facts apart; a 401 from `/api/auth/me` is the ordinary signed-out answer, never a sign-out event; `queryClient.clear()` on sign-in and sign-out so the previous user's rows cannot flash), `RequireSession` (skeleton → app or login), `LoginView` (outside the shell, so it renders when nothing else can).
- `lib/api/client.ts`: `credentials: "same-origin"`, `api.login/logout/me`, and ONE 401 handler fired ONCE per burst — six queries failing together are one sign-out. The auth routes are EXEMPT: a wrong password is the form's business. 7 new tests pin those edges.
- The app's identity surface is honest now: the SIDEBAR card was hardcoded ("R / Rajeev / Personal library" from the design mockup) — with real sessions that is a lie the moment a second person signs in — so it reads the session, and says "Not signed in" when there is none.

**Two things the verification changed (both worth keeping):**
1. **The provider PROBES enforcement once at startup** (`me()` → 401 → one ordinary app call). Without it, a signed-out visitor in an ENFORCED world would watch the app mount and then get bounced to the login view. `tools/check_login_flow.py` asserts with a **MutationObserver** that app content NEVER appears in that world, so the fix is pinned rather than assumed.
2. That tool's first run FAILED scenario C — **and the stub was wrong, not the app**: it refused app calls even for a VALID session. Fixed the stub (a cruder-than-reality stub makes a correct app look broken — the mirror image of the subtitle-era "check the probe stubs it"). Its second run produced a FALSE FAIL for a different reason: **vite was serving the PRE-EDIT module** (the documented watcher trap) — killed the PID holding `:5199`, verified the new module was being served, re-ran. Both false results are recorded here because the next session will hit the same two traps.

**Gates:** tsc clean · **204** vitest (19 new) · vite build green · `tools/check_login_flow.py` **3/3** scenarios (unenforced stays usable / enforced goes straight to login with no flash / a valid session is left alone) · **the REAL app in Chromium** against a local api: shell renders signed-out, Sign in offered, `/login` renders with its honest hint ("Nothing is enforced yet: the app stays usable signed out"), no page errors.

**⚠ DEPLOY + EYEBALL (user, web only — the api did NOT change):**
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
docker compose -p rkm-bundled up -d --build web
```
Check: top bar shows **Sign in**; signing in with the Jellyfin admin names HIM in the sidebar card instead of "Rajeev"; a wrong password shows one generic message and does NOT bounce the app; **Sign out** returns to the signed-out app, which still works (**nothing is enforced yet** — that is Phase 2, deliberately).
## ▶ LATEST SESSION (2026-09-12) — SUBTITLE EYEBALL CLOSED ✅ + HOUSEHOLD ACCOUNTS SCOPED 📋 (plan `docs/HOUSEHOLD_USERS_PLAN.md`, probe `tools/probe_jellyfin_users.py`; branch `feat/auth-multiuser`, **NOT STARTED — nothing deployed, nothing enforced**)

**User:** *"THIS IS DONE"* (the outstanding subtitle eyeball) and *"I WANT TO DO IT FROM THE UI, CREATING NEW USER AND STUFF..LET ME KNOW"* — so the SECOND Jellyfin user that Phase 3's live proof needs will be created from the app's own UI, not the Jellyfin dashboard.

- ✅ **Subtitle eyeball CLOSED.** The two older blocks are marked in place (the Phase 5 block and the selection-fix block): `main` @ `c0ae65e` is accepted, the tick / Off / "N downloads left today" checks passed, and nothing on the subtitle feature is outstanding. No code changed for this — it was a RECORD fix, and until now that record was lying to the next session.
- 📋 **Phase 1b scoped: household accounts from inside the app** (`HOUSEHOLD_USERS_PLAN.md`, promoted out of AUTH_MULTIUSER_PLAN §6 Phase 5's *optional* row). It creates and manages Jellyfin users: see the household, add a member (name + password + library tick-boxes), change library access, reset a password, delete with a typed confirmation.
- 🔍 **Measured BEFORE planning, and the measurement changed the design** — new read-only probe `tools/probe_jellyfin_users.py`: users + their library grants, every library's ItemId, and the RUNNING server's own contract for the endpoints. Against the live server: **3 libraries** (`Movies` `f137a2dd…`, `TV Shows` `767bffe4…`, `Movies Kids` `7e9b296e…`) and **1 user** (`admin`, `EnableAllFolders=true`). Three findings, each of which would have shipped as a silent bug:
  1. **`POST /Users/{userId}/Policy` REPLACES the whole 47-field `UserPolicy`** ⇒ read-modify-write only; a partial body would quietly reset permissions.
  2. **`POST /Users/Password?userId=`** — the target is a **QUERY** parameter (a path-form call 404s); body `UpdateUserPassword {CurrentPassword, CurrentPw, NewPw, ResetPassword}`. This is how an admin resets a member's password.
  3. **`GET /Users/{userId}/Views` still answers but is NOT in the server's own contract** ⇒ the app must read `/UserViews?userId=`. (The probe now prints a loud `NOT in this server's contract` line for that class of trap; its first draft reported three endpoints as "not present" because it matched the wrong spellings — fixed before it was believed.)
- **Design calls recorded in the plan:** authorization is checked LIVE against Jellyfin (`GET /Users/{session.user_id}` → `Policy.IsAdministrator`), never from a stored flag; the admin routes are **session-STRICT from day one** regardless of `RKM_AUTH_REQUIRED` (they can create accounts, so they must never answer an anonymous caller); the calls are made as the SIGNED-IN admin (attributable in Jellyfin's own log, and its 403 stays the backstop); the password is used once and never stored, logged or returned (test-pinned); and deleting the LAST administrator is refused.
- **Ordering decided and written into AUTH_MULTIUSER_PLAN §5/§6:** Phase 1 (login UI) → **1b (this)** → Phase 2 (enforcement) → Phase 3 (identity) → 4 → 5. He exercises account creation while the app is still permissive, and Phase 2 then protects the new admin routes along with everything else.
- **Waiting on him (4 decisions, plan §8):** password handling, default library access, v1 scope, and 1b before or after Phase 2.
## ▶ LATEST SESSION (2026-09-12) — AUTH PHASE 0 OF 6: SERVER-SIDE SESSIONS + `/api/auth/*` ✅ (branch `feat/auth-multiuser`, commit `dd921ed`, pushed; **NOTHING ENFORCED — nothing to deploy**)

**User instruction:** *"PICKUP THE WORK FROM PROGRESS.MD IN RKM-CINEMA APP"* — execute
`AUTH_MULTIUSER_PLAN.md` phase by phase: ONE commit per phase, gates green after each.
This session did **Phase 0 only** (the plan's own order); Phases 1–5 are untouched.

**What landed (additive only — 41 → 44 contract paths, +143/−0; typed client +206/−0):**
- `backend/services/auth.py` — `SessionStore` (create / lookup / revoke / prune / count / `records()`): atomic tmp+`os.replace`, **mode 0600**, mtime-cached reads, corrupt file ⇒ log + start empty, **sha256 of the id as the stored key**, 30-day **sliding** expiry refreshed on use (rate-limited to one write per 60 s so the hot path stays a read), and a login that prunes expired rows. Plus `authenticate_jellyfin()` with its own typed taxonomy (`InvalidCredentialsError` ⇒ 401, `AuthUnavailableError` ⇒ 503) — credential check delegated to `/Users/AuthenticateByName`, the login attributed to a NEW identity `MediaBrowser Client="RKM Cinema", Device="RKM Cinema Web"` (deliberately not the `rkm-tools` identity: Jellyfin's own log is how a dropped write is traced back to a client).
- `backend/api/session.py` — `require_session` + `current_session()` on a **contextvar**, and `session_context_from_request()`. Enforcement is the FLAG, not a code path: with `RKM_AUTH_REQUIRED=false` a stranger is not an error (behave exactly as before), with it true a missing session is a 401.
- `backend/api/routes/auth.py` — `POST /api/auth/login` (`{username,password}` → user + `Set-Cookie`), `POST /api/auth/logout` (revoke + clear), `GET /api/auth/me` (STRICT 401 when signed out, independent of the flag — the frontend guard asks this, and "signed out" ≠ "not enforced yet"). `LoginRequest`/`SessionUser`/`LoginResponse`/`MeResponse` in `api/models.py`.
- `config/settings.py` `RKM_AUTH_REQUIRED` (annotated ⇒ the real-env passthrough carries it; `auth_required()` reads it PER REQUEST and **fails OPEN** on a typo) + `render_config.py::build_api_vars` carries it into `.rkm.env` (the api container's env is the RENDERED file — a key missing there can never be set by the user).

**Four things this session had to MEASURE or PROVE, each of which would have failed silently:**
1. ⚠ **`require_session` must be `async def`.** FastAPI runs a *sync* dependency in a worker thread whose context is a **copy**, so a contextvar set there is discarded before the endpoint runs — the Phase 3 provider would then quietly fall back to the ADMIN token and every user would share one identity, with no error anywhere. Proved by test: swapping it to `def` fails `TestSessionSeam` with `context_user=None` (contextvar lost, dependency value fine); restored, all 4 pass.
2. ⚠ **Set the cookie on the RESPONSE YOU RETURN.** FastAPI does not merge headers set on an injected `Response` into a returned `JSONResponse`, so the obvious `def login(response: Response)` form silently drops the cookie (200, no session). Building the `JSONResponse` first and calling `set_cookie` on it is test-pinned (`HttpOnly; Max-Age=2592000; Path=/; SameSite=lax`, **no `Secure`** — plain-http tailnet).
3. ⚠ **The plan's lockout command was FALSIFIED and is now fixed in infrastructure, not just in prose.** The api's environment is the rendered `.rkm.env`, so `RKM_AUTH_REQUIRED` set in `.env` + `up -d --build api` (§5's "no render needed: the value is read per request") would NOT have taken effect. `docker-compose.yml` now interpolates `RKM_AUTH_REQUIRED: "${RKM_AUTH_REQUIRED:-false}"` from the repo `.env` — compose reads it for interpolation and recreates on a changed config hash, so the documented recovery works and (unlike a full deploy) cannot cancel an in-flight library scan.
4. **A raw transport error must be WRAPPED** (`(URLError, timeout, OSError)` ⇒ `AuthUnavailableError`), or it escapes the taxonomy and the route answers a 500 instead of a 503; the message carries the exception CLASS, never its text (a urllib error stringifies its URL).

**Gates:** **746** backend pytest (65 new) · ruff clean · `tsc --noEmit` clean · **185** vitest · vite build green · contract 41 → **44** paths, purely additive · typed client +206/−0 · openapi `added: ['/api/auth/login','/api/auth/logout','/api/auth/me']`, `removed: []`.

**LIVE proof against the real thing** (local uvicorn `:8033`, isolated store in `/tmp`, the real bundled Jellyfin 10.11 at `host.docker.internal:8098`, a genuine `POST /api/auth/login` with the repo's admin credentials — never printed):
```
signed out:            GET /api/auth/me -> 401
nothing enforced yet:  GET /api/library/folders -> 200
REAL login:            POST /api/auth/login -> 200  {"user":{"id":"1760c9b047d444d39c94a99d082773ed","name":"admin"}}
  Set-Cookie: rkm_session=<opaque>; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax      (43-char cookie, token NOT in it)
with the cookie:       GET /api/auth/me -> 200
logout:                POST /api/auth/logout -> 200  (Max-Age=0)   then /api/auth/me -> 401   (server-side revocation)
store on disk:         keys are 64-hex sha256, the raw cookie value is absent from the file
```
The login created one device entry in HIS Jellyfin; it was purged afterwards (`DELETE /Devices?Id=rkm-cinema-web` → **204**, re-listed and confirmed absent). One earlier purge attempt answered 401 — because Jellyfin ROTATES a device's token on every login, so the row the script picked was already dead, not because of the header style.

**Nothing to deploy.** Phase 0 is additive and unenforced; the running stack is behaviourally identical. Next: Phase 1 (frontend login view, still nothing enforced).
## ▶ LATEST SESSION (2026-09-12) — SUBTITLES PHASE 5: HARDENING + DOCS + ADR-0005 ✅ **PLAN COMPLETE (all 6 phases)** (branch `feat/subtitles-hardening`; the four earlier commits are on `main` at `710f678`) → ✅ **EYEBALLED + ACCEPTED by the user 2026-09-12** ("this is done")

**Hardening — the plan's criterion 10 as TESTS, not as hope.** Seven new API tests + three client tests pin the failure paths end to end: a dead network, a vendor payload nobody expected, blank credentials, quota exhausted, and a rate limit. What they enforce: the search listing **degrades to the item's own tracks on a 200** (never a 500, never an empty panel), select answers **503** not configured / **502** credentials & transport / **429** quota & rate limit, nothing is attached or remembered when the download failed, and "off" still works with the vendor dead. `tools/check_subtitle_panel.py --fail-search` proves the same thing in the BROWSER: with the online search returning 502, the item's own subtitles are still listed and still appliable, the Off row survives, and the notice says why.
- ⚠ **A real gap, found by writing those tests rather than by a user report:** the client's retry loop only caught our own `TransportError`, so a **raw `OSError`** (connection refused — what `urllib` actually raises) escaped **un-typed and un-retried**. Consequence: the select route returned **HTTP 500** (it maps the typed taxonomy only) and GETs silently skipped their retry budget. Fixed in `_request`: raw network errors are wrapped into `TransportError` and get the same single retry as a 5xx. The wrapped message carries the exception **CLASS, never its text** — a `urllib` error stringifies its URL and our URLs can be the pre-signed download link (the redaction test now covers exactly that).
- Proof the tests bite: run against the pre-fix tree (`git stash` the two source files) **5 of them fail**, including the raw-`OSError` escape.
- Polish: the picker no longer offers "Search again" once the API has said OpenSubtitles is not configured.

**Docs.** `docs/adr/ADR-0005-opensubtitles-integration.md` — the decision, the four measurements behind it, the rejected options (the Jellyfin plugin: manual install outside bootstrap, creds in Jellyfin's config, quota invisible to the api, issues #109/#159; Bazarr: no picker, no usage tracking, kept for bulk later), credential handling, and the runtime-quota rule. `ARCHITECTURE.md` gains **§15** (the flow diagram, the three rules that are easy to get wrong, the store shape) plus the three endpoints and the client row in the integration table. `OPERATIONS.md` gains four symptom→command rows and both subtitle probes. `README.md` gains the feature row and the `OPENSUBTITLES_*` config row.

**Gates:** **681** backend pytest · ruff clean · `tsc` clean · **185** vitest · vite build green · layout **10/10** both modes (with the settings panel open) · panel check: normal (exactly one row ticked, the chosen result) AND `--fail-search` (own subtitles survive) · docs links 35 files / 7 links.

**⚠ DEPLOY + EYEBALL (last step) — api AND web changed:**
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 status
docker compose -p rkm-bundled up -d --build api web
```
Check: the tick lands on the row you clicked (**3 Deewarein (2003)**), the delivered row reads `English - SUBRIP - External · downloaded`, **Off** sticks across a reload, "N downloads left today" matches what the API actually reports, and — the new bit — with the api key blanked or the vendor unreachable, **everything else still plays** and the picker explains itself instead of failing.

**Phase status: 0 ✅ · 1 ✅ · 2 ✅ · 3 ✅ · 4 ✅ (incl. the eyeball's selection fix) · 5 ✅.** Plan doc marked COMPLETE.
## ▶ LATEST SESSION (2026-09-12) — SUBTITLE SELECTION FIX (found by the user's eyeball) ✅ FIXED → **MERGED to `main` 2026-09-12** (`710f678`; `main` `251ec63` → `710f678`, deploy branch `experiment/bundled-docker-stack` FF'd to match, all three pushed). ✅ **EYEBALLED + ACCEPTED 2026-09-12** (the user: "this is done") — the rebuild happened and the fix is confirmed; nothing on the subtitle feature is outstanding

**The user's report, verbatim:** *"i did this for 3 deewarein movie...i searched-> selected->it says downloaded-> but i dont see the selection on the subtitle(the round box?)...can you have look"* — i.e. the download reported success and the picker showed NO selection.

**Diagnosis (reproduced against his LIVE stack, item `c4c3baac31b473887f75f6e6b73562f8`):** nothing was broken in the download — the file was attached and the server held `index=0 English - SUBRIP - External`. The API reported `preferred_subtitle {subtitle_id: os:682960, '3 Deewarein (2003)', index: 0}` and marked the LOCAL row active while **the row he clicked (`os:682960`) was inactive**. Two independent causes, one symptom:
1. `merge_subtitle_rows()` **hard-coded `"active": False` on every REMOTE row** — so only a local track could ever be ticked, and the delivered track is one the server names generically ("English - SUBRIP - External", indistinguishable from an embedded subtitle). The row he chose could not light up for ANY input.
2. The player **never re-read playback-info after a download**, so the newly delivered track did not exist in the panel yet — at the moment of selection there was no local row to tick either, and no sign the file had landed.

**Fix (`5ba203a`) — the user's CHOICE is now separate from the stream INDEX that plays:**
- `merge_subtitle_rows(..., active_subtitle_id=…)` marks **exactly one** row: the result the user picked. The local track it resolved to is that SAME subtitle (a delivery of it, not a second choice) so it is deliberately not ticked as well; with no remote identity stored, `active_index` behaves exactly as before.
- The player keeps `subChoiceId` (restored from playback-info on load) beside `subIndex`, and the pure helper **`activeSubtitleRowKey()`** decides the single ticked row — the chosen result when the panel lists it, otherwise the local track actually applying. The delivered row also gains a `downloaded` hint so it reads as ours.
- After a select the player re-reads playback-info (the new track appears immediately) and shows a notice naming what was added.

**Side-by-side on his LIVE data (old rule vs new rule, same item, same stored choice):**
```
OLD: [*TICKED*] local  English - SUBRIP - External      <- a row he never clicked
     [        ] remote 3 Deewarein (2003)               <- the row he clicked
NEW: [        ] local  English - SUBRIP - External
     [*TICKED*] remote 3 Deewarein (2003)
```

**Evidence:** backend +3 tests (fail against the pre-fix code — verified by running them on a stashed tree: `merge_subtitle_rows() got an unexpected keyword argument`), frontend +7 tests including "never ticks two rows for one choice", the harness stub now mirrors the LIVE case (a delivered track named "English - SUBRIP - External" beside the chosen result), and `tools/check_subtitle_panel.py` now **ASSERTS** exactly one OpenSubtitles row is ticked and names the chosen one — the reported symptom can no longer return unnoticed. New read-only diagnostic **`tools/probe_subtitle_selection.py "<title>"`** answers "why isn't my subtitle marked?" in one command (server tracks + every row's active/local/index/used + playback-info's preferred_subtitle) and REFUSES a fuzzy title match. Gates: 671 backend · ruff · tsc · 185 vitest · build · layout 10/10 both modes · docs links.

⚠ **The lesson worth keeping:** a picker whose rows are *results* and whose applied state lives on a *different* row needs ONE explicit rule for which row is ticked — "mark the track at the resolved index" and "mark the result the user clicked" are genuinely different rows here, and only the second one matches what the user sees himself clicking.

## ▶ LATEST SESSION (2026-09-12) — SUBTITLES, PHASES 0–4 OF 6 EXECUTED → **EYEBALLED 2026-09-12: one selection bug found and fixed in the block above; MERGED to `main` (`710f678`)** (branch: `feat/subtitles-opensubtitles`, commits `1db4215` (plan) → `4d08890` (P0) → `e27d28d` (P1) → `c7e4412` (P2) → `c29ce0b` (P3) → `9722d88` (P4); plan `SUBTITLES_OPENSUBTITLES_PLAN.md`. **Nothing is deployed yet — the api AND web changed, so this needs one rebuild + the user's eyeball. Phase 5 (docs/ADR-0005) is all that remains after that.**)
**User instruction:** *"proceed with next in rkm-cinema"*, then *"continue with phase 4"*. The queued item was the scoped OpenSubtitles work; the branch was rebased onto current `main` (`251ec63`) before any code landed, and the user registered an OpenSubtitles API key into the repo `.env`, which unblocked the live halves of Phases 2–3.

**Phase 0 (`4d08890`) — config plumbing + ONE `.env` parser.** Five `OPENSUBTITLES_*` settings declared on `Config`, read in `_load()`, rendered into `.rkm.env` (api only), one api startup line, `.env.example` + live `.env` documented. `has_opensubtitles()` keys off the **API key alone** — a missing login degrades to the anonymous tier, never to "disabled"; `validate_required()` stays untouched so a blank config boots. **`backend/config/env_file.py` is now THE .env parser** for `render_config`, `config.settings` and `tools/rkm_common` (three copies before): the api's copy did a bare `partition("=") + strip()`, so a quoted value arrived WITH its quotes, and none tolerated a leading BOM (the plan's §4.1 trap — its own snippet starts with one). Proved old-vs-new: OLD keys `['\ufeffOPENSUBTITLES_PASSWORD', …]` → NEW `['OPENSUBTITLES_PASSWORD', …]`.

**Phase 1 (`e27d28d`) — `services/opensubtitles.py` + 59 fake-transport tests** (no live calls in the suite). Keyed `tmdb_id → imdb_id → title+year(+season/episode)`; empty results are `[]`; typed taxonomy (`NotConfigured / AuthFailed / QuotaExhausted / RateLimited / NoResults / UnsupportedFormat / TransportError`). **A `/download` POST is never retried** (it may already have been charged); GETs — including 5xx — are retried exactly once. The download link is pre-signed: fetched WITHOUT the `Api-Key`, never returned to a client, never logged. Live: 30 results by tmdb_id AND by imdb_id, 19 for an episode keyed by series title, Hindi results for `hi`.

**Phase 2 (`c7e4412`) — delivery: `services/subtitles.py` + `item_path`/`refresh_item`/`upload_subtitle`/`subtitle_search_context`.** The only code that writes to the media drive: sidecar `<stem>.<lang>.srt`, atomic, UTF-8, encoding-normalised; an existing same-language sidecar is **REUSED** (no download, user's file untouched); the **ITEM** is refreshed and a library scan can never be triggered (test-asserted); a non-subtitle payload is refused; identity→index resolution with a 639-1/639-2 normaliser. **Verified live end-to-end** against his own library (item resolved by EXACT tmdb id): the track appeared in `PlaybackInfo` and the app's own VTT proxy served real content (119,258 chars of WEBVTT).

**Phase 3 (`c29ce0b`) — `services/subtitle_store.py` + `subtitle-search`/`select`/`disable` + additive `playback-info.preferred_subtitle`.** Prefs are per ITEM and keep an IDENTITY; usage is per SUBTITLE (global — it ranks results and drives "Used N times"). One JSON file beside the watchlist (atomic, mtime-cached, corrupt-tolerant; JSON rather than SQLite deliberately). Contract **38 → 41 paths**, snapshot **+183/−0** and typed client **+216/−0**. Verified live through the real api (`:8125`, isolated store, temp Jellyfin key, all traces removed): movie search 30 results, **episode search 19 + its 2 existing local tracks**, select → preferred resolved to index 0, re-search ranks it first `used=1`, disable → `null`.

**Phase 4 (`9722d88`) — the in-player panel + auto-apply.** The Subtitles block is now rows: **Off** (persisted, reversible) / the item's own tracks (unchanged behaviour) / ranked OpenSubtitles results with language, source, `Used N times`, SDH and an active marker taken from the server's own flag, plus an inline **Search OpenSubtitles** button. Per-row busy state; "N downloads left today" once known; errors are a **non-blocking notice pill** (the plan forbids a subtitle problem blocking playback). **Auto-apply on load** uses playback-info's `preferred_subtitle` through `resolveActiveSubtitle()`, which re-resolves the identity to a current index and applies NOTHING when it no longer matches — never a different subtitle. Pure helpers (+15 vitest): `languageKey` (639-1↔639-2, including codes whose prefix lies: German `ger` ≠ `ge`, Swedish `swe` ≠ `sw`), `usedCountLabel`, `subtitleRowLabel`, `rankSubtitleRows`, `resolveActiveSubtitle`. API rows now carry `file_id`, so the client asks by the provider's own id instead of parsing `os:<id>`.
- Verified by CONTENT, not by eye: new `tools/check_subtitle_panel.py` opens the real `<Player>` in the harness, opens the panel and prints the section's text + every row's `aria-pressed`. Output: `Off / English (eng) / Harness.Release.1080p · EN · OpenSubtitles · Used 4 times / … · Used once / … · SDH`, marker on the row the server reported, and **0 subtitle-search calls before the button, 1 after** (the on-demand search, proven).
- `tools/measure_player_layout.py`: **10/10 viewports with the settings panel open** and 10/10 without.

**Four live findings, all now encoded in the code (each cost a round trip):**
1. **`POST /Videos/{itemId}/Subtitles` is JSON, not multipart** — multipart gets **415**; the body is `UploadSubtitleDto` with **base64** `Data`. Settled by reading the RUNNING server's own `/api-docs/openapi.json`.
2. **Indexing LAGS a delivery** — reading tracks right after an upload can return the OLD list; `_tracks()` re-reads a bounded ~1s before believing an empty answer.
3. **`remaining` IS a real daily counter** (4 → 3 on a new file) but does **not** decrement for a repeat download of the SAME file (repeat downloads are free). Key-only has no `/infos/user`, so before the first download the figure is genuinely unknown — the UI stays silent, never invents one.
4. **`attributes.format` is free text** (`eng-sdh`, `eng-full`, `x265-heteam`), not an extension — take the extension from `files[0].file_name`.

**Two bugs the new tests caught before shipping:** the usage-ranking lookup assumed one key form (`{"os:123"}` vs `{"123"}`) so every count read 0 and "rank by our usage" silently did nothing; and the service built its own OpenSubtitles client lazily, so a route-level injection was ignored — the TESTS WERE REACHING THE LIVE VENDOR API.

**Two things Phase 4 had to change in the VERIFICATION TOOLS** (both disclosed because they made a gate more honest, not weaker): the layout harness never stubbed the API, so `info` stayed null and every data-driven panel section was SKIPPED — the probe was measuring an empty shell; it now stubs playback-info + subtitle-search and counts the searches. And the probe's "nothing outside the viewport" check counted content below the fold *inside a scroll container* as a failure — that is reachable by scrolling, and the settings dialog is `max-h-[…] overflow-y-auto` by design, because a title with 30 subtitle results cannot fit a 390px-tall phone in landscape. Stranded elements still FAIL (the dock-below-the-screen class is untouched); reachable ones are now reported in the detail column instead.

⚠ **My first 10/10 was measured against an ORPHANED vite from 2026-09-10 still holding `:5199`** — the fresh server hit `--strictPort`, died, and the harness served the PRE-EDIT Player (an old `<select>` was in the DOM where the rows should be). Caught by dumping the rendered HTML, killed the orphan, restarted, re-measured. **Always confirm your own dev server actually started**; the tell is `Error: Port 5199 is already in use` in its log.

**Gates:** **668 backend pytest, 0 failures** · ruff clean · `tsc --noEmit` clean · **vitest 178/178** · vite build green · layout **10/10** (both modes) · docs links 34 files / 7 links · contract + typed client purely additive.

**⚠ DEPLOY + EYEBALL (RKM-HP) — api AND web changed:**
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
docker compose -p rkm-bundled up -d --build api web
```
Prefer this over a full `bootstrap.ps1` (a deploy re-runs the provisioner and CANCELS an in-flight library scan; `.\rkm-cinema.ps1 status` first shows whether one is running). Eyeball: open a movie → Play → gear → **Subtitles** → **Search OpenSubtitles** → pick one → it applies, the row shows **Used once**, and closing/reopening the player applies it again without touching anything; a second search shows the count rising and that row ranked first; **Off** sticks across a reload; the item's own embedded subtitles still work exactly as before. Then merge: FF `feat/subtitles-opensubtitles` → `main`, FF `experiment/bundled-docker-stack`, push all three.

**Next — Phase 5 (`short`):** failure-path hardening end-to-end (creds blanked / quota exhausted / network down ⇒ playback, seek and local subs unaffected), docs (`.env.example` is done; README, ARCHITECTURE subtitle flow, OPERATIONS symptom→command row), **ADR-0005** (new external dependency + credential handling + why the Jellyfin plugin was rejected), then the merge. Open decisions from the plan: §10.3 store = JSON sibling file (implemented as recommended; SQLite stays a separate decision) and §10.4 default languages (`en` implemented — add `hi`/`ta` in `.env` if wanted).

## ▶ LATEST SESSION (2026-09-12) — SUBTITLE INTEGRATION SCOPED 📋 NEXT ITEM QUEUED (plan `docs/SUBTITLES_OPENSUBTITLES_PLAN.md` on branch `feat/subtitles-opensubtitles` @ `6f117cd`)

- User scoped the next session's work: OpenSubtitles + Jellyfin subtitles — discovery, in-player selection, **persistence**, usage counts, Plex-like panel. Plan committed as that branch's first commit, together with `tools/probe_subtitles.py` (the read-only reconnaissance its verification section re-runs).
- **Four findings that changed the spec** (all measured live 2026-09-12, no guessing):
  1. An **API key is MANDATORY** — OpenSubtitles.com requires the `Api-Key` header on every call and `/download` additionally needs a login JWT. Username/password alone cannot work, so `.env` gains `OPENSUBTITLES_API_KEY` (flagged to the user, not silently adopted). Quotas: 5 downloads/day anonymous, **20/day signed in**.
  2. **No OpenSubtitles provider is installed** in the bundled Jellyfin (plugins: AudioDB/MusicBrainz/OMDb/Studio Images/TMDb) → `GET /Items/{id}/RemoteSearch/Subtitles/eng` returns `[]` today, so the remote path is dead until something provides it.
  3. The api's media-root mounts are **rw** (`x-media: &media "${RKM_MEDIA_PATH:-./data}:/data"`, no `:ro`) and the watchlist already proves writes from the api land on the host drive → the sidecar-`.srt` delivery the recommended design rests on is viable.
  4. **Subtitle stream indices are positional** (our own download shifts them), so a persisted choice must store **identity** (provider + subtitle id + language + display title) and resolve the index at playback — never persist an index as the source of truth.
- **Recommended architecture:** the **api owns an isolated OpenSubtitles client** (`services/opensubtitles.py`) and hands the file to Jellyfin (sidecar `<name>.<lang>.srt` + item-level refresh), so Jellyfin keeps *storing and serving* subtitles, the existing VTT proxy is untouched and credentials never leave `.env`. Jellyfin's own plugin (credentials would move into plugin config + the install doesn't survive our container rebuilds) and Bazarr (no in-player picker, no usage tracking) are documented as rejected/alternative, not silently dropped.
- **Build on what exists:** `playback-info` already returns audio + text-subtitle tracks and `/api/jellyfin/subtitle` already proxies a text track as VTT (live-verified path with the extra `/0/`); the player already renders the track list in its settings overlay — the OpenSubtitles rows join that list rather than a new UI. Persistence copies the `JsonWatchlistRepository` atomic-write pattern.
- ⚠ **Blocking decision before Phase 1:** an OpenSubtitles API key (free to register) in `.env`. Phases 0/3/4 are implementable against fakes meanwhile. Also open: JSON store (recommended — no migration) vs the existing SQLite repository; default language list; confirm no plugin install.
- **No application code changed** by this scoping session (docs + one read-only probe tool only); `main` is otherwise exactly as merged earlier today.

## ▶ LATEST SESSION (2026-09-11) — CONTINUE WATCHING ROOT-CAUSED + FIXED: the progress report was a no-op ⏳ AWAITING THE RKM-HP EYEBALL (branch: `fix/resume-progress` off `refactor/remove-plex-emby`, commit `88598cf`; supersedes nothing — the Plex/Emby record below it is still unmerged)
**User-reported (live, RKM-HP):** *"continue watching is not being updated — I was just watching a movie 3 Deewarein but after closing it it's not coming in the continue watching section… can you check why"*.

**ROOT CAUSE (one sentence):** the app reported playback through Jellyfin's `/Sessions/Playing*` endpoints, which only persist a position when the report matches a live **device playback session** — and in-app playback never is one (the app proxies the stream itself), so Jellyfin answered every report **204 and stored nothing**; the app then faithfully showed the server's (empty) truth.

**How the triple-check isolated it (each step against the LIVE stack, no theorising):**
1. `tools/probe_continue_watching.py` — the three views side by side. Jellyfin's own `UserData` for '3 Deewarein': **PlaybackPositionTicks=0, Played=False, PlayCount=0**; Jellyfin's own `/Items/Resume` did NOT contain it; and the app's 5 CW items matched Jellyfin's Resume list **exactly**. So the app's read side was innocent — the WRITE never arrived.
2. The app's route reproduced it deterministically from the sandbox: `POST /api/jellyfin/progress` returned **204 for start/timeupdate/stopped and the position stayed 0**.
3. Jellyfin's **own log** (via the `System/Logs` API) named the culprit: `Playback stopped reported by app "RKM Cinema" "10.11.11" playing "3 Deewarein". Stopped at "1650965" ms` — the user's ~27-minute watch reached Jellyfin, was logged… and dropped.

**Every plausible fix of the Sessions shape was tried live and ALL were accepted-and-dropped (204, nothing stored):** the REAL `PlaySessionId` from PlaybackInfo, an invented one, `+ X-Emby-Authorization` device header, `X-Emby-Token`, and `Authorization: MediaBrowser …, Token="…"`. That ruled out plumbing/casing/credential theories and proved the endpoint family simply cannot work for a player that isn't a Jellyfin session.

**Why it looked like it "used to work":** the morning's resume positions (Chhaava 581s, Hulchul 459s, Disclosure Day 594s) were reported while the api was authenticating as the **provisioner's admin session** — the log attributes those to `app "RKM Provisioner"` — and those DID land. Since the api started reporting as the **"RKM Cinema" API key** (log: `app "RKM Cinema"`, first entry 17:06 today = the rebuild) every report has been dropped. So: worked this morning, silently broken after the redeploy.

**THE FIX (branch `fix/resume-progress`):**
- `JellyfinLibraryProvider.set_playback_position(item_id, position_ticks)` writes the item's own user data — `POST /Users/{uid}/Items/{id}/UserData` with **only** `PlaybackPositionTicks` — then invalidates the item cache. Same user-scoped family as the already-working `mark_state`.
- ⚠ It must NEVER send `Played`: verified live that an explicit `Played: false` **un-marks an already-watched title**, while omitting it leaves the flag alone. Pinned by a test.
- ABC + `LibraryService` gained `set_playback_position`, so the route goes through the service (§43) instead of hand-building a Jellyfin URL.
- `/api/jellyfin/progress` now answers **204 only when a backend confirms the write, 502 when it didn't** — "204 for a report that stored nothing" is literally the shape of this bug.
- `runtime_ticks` added to the progress payload (additive) and sent by the player, so a `stopped` within **5%** of the runtime marks the item **watched** instead of leaving a resume point at the credits.

**VERIFIED END-TO-END against the live stack through the app's own new code** (`tools/verify_progress_reporting.py`): wrote the user's real position for 3 Deewarein (1651s) → Jellyfin stored **1651.0s** → it appears in Jellyfin's Resume → **the app's `/api/library/continue-watching` now returns 6 items including '3 Deewarein'**. That call also restored the resume point the watch earned (the item is back for the user immediately — the reading side never needed a redeploy).

**Gates:** backend **487 passed** (+5: 4 route tests replaced by 5 behaviour tests, +2 provider tests) · ruff clean · openapi 38 paths (`runtime_ticks` additive) · `tsc` clean · vitest 163/163 · vite build green.
**New tools:** `tools/probe_continue_watching.py` (read-only diagnosis: item state vs Jellyfin Resume vs the app's payload) and `tools/verify_progress_reporting.py` (the write-then-read-back proof).

**⚠ Deploy + eyeball (RKM-HP)** — api AND web changed:
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
docker compose -p rkm-bundled up -d --build api web
```
Then: play something for ~30 s, close the player, and it should appear in **Continue Watching** on Home (resume point ≈ where you stopped). Finish something to the end and it should leave CW and show as watched. This is web+api only — no full `deploy`, so a library scan is not touched.
**Note for the merge:** this branch is stacked on `refactor/remove-plex-emby` (still awaiting its own eyeball). Merge that one first, then `fix/resume-progress` fast-forwards onto it, then FF `experiment/bundled-docker-stack`.
### Follow-up 2 (2026-09-12 ~04:40 AEST) — "new entries never reach Home" was RESUME ORDERING, not the write (commit `3ae9fb5`)

- User: *"it shows resume in the tv shows individual tab...but on the home tab the continue watching section doesn't update with new entries"*.
- The server payload was FINE (8 rows, Spider-Verse present at 138s) — but sitting at **position 8 of 8**. **CAVEAT:** Jellyfin's `/Items/Resume` sorts by **`LastPlayedDate`** (newest first, **nulls LAST**) and does NOT derive that from the position; `POST /Users/{uid}/Items/{id}/UserData` does not set it implicitly. Every title written by the direct path therefore had a position and NO `LastPlayedDate` → the newest watch sank to the END of the rail (and off it entirely past the provider's limit of 12), so Home never showed a "new" entry. The item page looked right because it reads that item's own user data — no ordering involved. **"Resume shows on the item page but Home never lists the new entry" = Resume ORDERING, not a failed write.**
- Fix: `set_playback_position` now sends `LastPlayedDate` (UTC now) alongside `PlaybackPositionTicks` — still never `Played` (verified live: the pair leaves `Played=True` alone, whereas an explicit `Played: false` un-marks a watched title). The provider test pins the exact body key set.
- Verified: `LastPlayedDate` IS writable and IS the ordering key (setting it moved the item to the head of Resume); `null` does NOT clear it — a position-0 write is what removes an item from Resume.
- ⚠ Self-inflicted, then cleaned up: `tools/verify_progress_reporting.py` resolved a bare `searchTerm` by Jellyfin's fuzzy score and wrote a phantom 138s resume position to **Spider-Man (2002)** while the user's actual watch was **Into the Spider-Verse**. Cleared (position 0) and the real 138s restored on the correct copy — `BRRip.mkv`, identified from Jellyfin's logs; the library holds TWO copies of that film and the `WEBRip.mp4` copy is untouched. The tool now prints every candidate and, unless exactly one matched, refuses and demands the item id.
- Live after the fix: Resume order = `['Spider-Man: Into the Spider-Verse', '3 Deewarein', '3 Idiots', 'Disclosure Day', 'Chhaava', 'Hulchul', 'Rangbaazi', 'Episode 1']` and `/api/library/continue-watching` agrees. 487 pytest · ruff clean.
- ⚠ Deploy for this one is **api only** — `docker compose -p rkm-bundled up -d --build api`. The frontend invalidation (`a14d449`) is already live on the box (verified: the served bundle hash is identical to a build of the current source).

### Follow-up (same session, 20:50 AEST) — Spider-Man "not appearing" was the CLIENT, not the write (commit `a14d449`)

- User: *"i just watched spiderman into the spider versefor few couple of inutes but it didn't appear in continue watching"*.
- Probed BEFORE changing anything: the fix above WAS live (`tools/probe_progress_deploy.py`: bogus item id -> 502, real item -> 204) and the position HAD recorded — `Played=False, PlaybackPositionTicks=1384813210` = **138s, exactly the "couple of minutes"** — present in Jellyfin's Resume and in the app's `/api/library/continue-watching` (7 items). ⚠ Jellyfin's activity log shows NO Sessions line for it: a direct UserData write logs nothing, which is now the signature of the FIXED path.
- REAL CAUSE — the client was stale. The player is an overlay owned by `LibraryLayout`, so the route behind it (Home / folder / item page) stays MOUNTED: closing the player remounts nothing, and with `staleTime: 30_000` + `refetchOnWindowFocus: false` (`main.tsx`) no query refetches. Every row behind the player kept its pre-playback payload — Continue Watching, Recently played/watched, the item's watched tick and its resume point. A page reload showed the item, which is what made it look like a server fault. **Lesson: "row did not update" is a CLIENT-cache symptom; "position == 0" is the WRITE symptom. Check which one you have before touching the backend.**
- Fix `a14d449`: `Player.tsx` invalidates the `["library"]` prefix on unmount (the close) so the just-reported position is visible the moment the user is back; every library query key is `["library", ...]` so ONE invalidation covers CW / recent / recently-watched / folder grids / item detail / similar. Same pattern the mark-watched path already uses in `library/api.ts`.
- `harness/player-frame.tsx`: now wraps the real `<Player>` in a `QueryClientProvider` — without one `useQueryClient()` throws and `tools/measure_player_layout.py` would silently render nothing (it mounts the player standalone, outside `main.tsx`'s provider).
- Gates: `tools/measure_player_layout.py` **10/10 viewports PASS** (so the harness renders and lays out), vitest **163/163**, `tsc --noEmit`, `vite build` green. No /api contract change. No unit test is possible for the invalidation itself (node-env vitest, no DOM/QueryClient harness); it is 5 lines reusing the existing invalidation pattern.
- ⚠ Deploy for this one is **web-only**: `docker compose -p rkm-bundled up -d --build web`.
- New tools: `tools/probe_continue_watching.py <title>` (item UserData + Jellyfin Resume + the app's own payload), `tools/probe_progress_deploy.py` (deployed-build discriminator + Jellyfin's playback log lines), `tools/verify_progress_reporting.py <title> <seconds>` (writes through the REAL provider code, then asserts persistence and that the app lists it).

## ▶ LATEST SESSION (2026-09-11) — PLEX/EMBY CODE REMOVED (plan phases 1–5) ⏳ AWAITING THE RKM-HP EYEBALL (branch: `refactor/remove-plex-emby`, 7 commits `bb6a2e5` → this record; plan `docs/REMOVE_PLEX_EMBY_PLAN.md`, now marked EXECUTED with a §8 "corrections found while executing")
**User instruction (2026-09-11):** *"continue with rkm-cinema app with next item in progress.md"* — the queued item was this plan. It executes the earlier decision *"i dont want use prod profile anymore as plex and emby's role is taken by jellyfin"*: the deployment went on `chore/retire-prod-stack`, this branch removes the **code** it left behind. Both prerequisites were already merged to `main`, and the branch was rebased onto that `main` before phase 1.

**Numbers, measured at both ends (§5 of the plan):**

| | before | after |
|---|---|---|
| functional Plex/Emby references (`grep` §5-1b) | **227 lines / 38 files** | **0** (allow-list in §8) |
| lines deleted outright | — | **1,562** (10 files: providers, probe scripts, their tests) |
| backend tests | 502 | **482** (every deleted test enumerated in its commit) |
| `/api` contract paths | 39 | **38** (one route gone) |
| frontend vitest | 164 | **163** |
| `plexUrl` / `embyUrl` / `plexKey` in the contract | present | **absent** (asserted, not eyeballed) |

**The 7 commits (one concern each, gates green after every one):**
1. `bb6a2e5` **factory is Jellyfin-only** — one provider or `None`; the `plex=` passthrough seam and the `"plex" if plex is not None` rule are gone; MEDIA_SERVER stops selecting a backend (still accepted/reported so an old `.env` deploys). `suggest.py`'s live `from services.plex import PlexService` lazy import now goes through `build_library_service()` like every other call site.
2. `06e313d` **delete the dead code** — `services/plex.py`, `plex_check.py`, `emby.py`, `library/plex.py`, `library/emby.py`, `api/routes/plex_thumb.py`, `scripts/verify_plex.py`, `add_with_plex_check.py` + 2 test files; `__init__` exports, `base.py::_plex_params()`, `PlexUnavailableError`/`EmbyUnavailableError`, the plex/emby `/api/health` services, and `library.py::_counts`' dead `_plex` branch. `db.py` is LIVE (repository.py uses it) so only its SQL comments changed — no persistence edit.
3. `01be4ab` **server-neutral domain vocabulary** — `in_library`, `library_links`, `watch_url`, `server_item_id`; `WatchLinks` loses the emby pair; the user-visible detail copy becomes "Available on Jellyfin". The provider-keyed `watch` map is deliberately UNCHANGED (the frontend reads `watch.jellyfin`) — its plex/emby keys went with the frontend commit.
4. `44eef23` **regenerate the OpenAPI snapshot** — the phase-2 route deletion had already moved 39 → 38, and the committed snapshot was stale.
5. `35e820f` **contract** — `plexUrl`/`embyUrl`/`plexKey` dropped from `StatusEntry`, `nginx` artwork location narrowed to the jellyfin paths, **ADR-0004** written, snapshot + typed client regenerated (`npm run generate:types` also absorbed PRE-EXISTING client drift: types.ts predated `/api/search/global`).
6. `9a0cb14` **frontend** — `posterUrl()` resolves by item id or null (the `/api/plex/thumb` fallback is gone; a bare image path has no proxy), `ResolvedState` loses plexUrl/embyUrl, `availableWatchLinks()` keeps only the jellyfin branch behind `type WatchProvider = "jellyfin"`, the dead "Watch on Plex/Emby" buttons are deleted, Settings `SERVICES` shrinks, and Discover/Folder/Home copy stops telling the user to connect Plex or Emby.
7. `e39f052` **config keys** — the six annotations (incl. the easy-to-miss `PLEX_BROWSER_URL`/`EMBY_BROWSER_URL`), `PLEX_SCAN_TTL`, `has_emby()`, `load_env()`'s Plex entries, and `validate_required()`'s `PLEX_TOKEN` requirement; `render_config.py` no longer passes them into `.rkm.env` and no longer `fail()`s on a retired `MEDIA_SERVER`.

**Three real bugs came out of this, none of them cosmetic:**
- **The reconciler hunted for `provider == "plex"`** to read `metadata["rating_key"]`. On a Jellyfin stack that lookup could only ever return `None`, so `server_item_id` was **silently always empty** (no test noticed — the tests were Plex-shaped). It now reads the match it actually got and its `metadata["item_id"]`.
- **`snapshot_to_status_result()` hardcoded the `plex` key** of the provider-keyed watch map; it now takes the first entry carrying a URL.
- **`api/routes/config.py` reported the media server as DOWN** whenever a retired `MEDIA_SERVER` value was still in `.env` (it compared the *resolved name* against `"jellyfin"`). It now reports whether the library provider is reachable.
- ⚠ **And the one that would have shipped worst:** `render_config.py`'s "tolerate the legacy value" step. `resolve_media_server()` returns a **known** retired value verbatim (it maps only UNKNOWN values to jellyfin), so a pass-through left `backend == "plex"` and **skipped the Jellyfin admin-password generation**, whose gate is `backend == "jellyfin"` — i.e. the "provisioner finished, yet every library is disabled" failure, behind a green deploy. Caught by writing the test FIRST; the renderer now always renders `jellyfin` (warn, never fail) and never passes the raw value through.

**Verified by execution, not by reading (§5):** the §5-1b grep ends EMPTY of functional references; `openapi.v1.json` → `38 paths` with zero plex/emby paths and no `plexUrl`/`embyUrl`/`plexKey` anywhere in the file; a real `Config` reports `validate_required() == []` and no `PLEX_URL`/`PLEX_TOKEN`/`EMBY_URL`/`has_emby`/`PLEX_SCAN_TTL` attributes, so the api's startup log no longer prints the phantom `Missing required config: ['PLEX_TOKEN']`; `python3 tools/verify_nginx_artwork_cache.py` re-run against the REAL repo config → `nginx -t` rc=0 and **6/6 PASS** (3 artwork paths cacheable with exactly one `Cache-Control`, JSON still `no-store`). Gates: **482 pytest** · ruff clean · `tsc --noEmit` clean · **vitest 163/163** · `vite build` green · `tools/check_md_links.py` 33 files / 7 links all resolve.

**What deliberately SURVIVES the grep (the plan's allow-list, now §8):** `X-Emby-Authorization` in `provisioner/provision.py` + the probes (that IS Jellyfin's own header — Jellyfin forked Emby), "Emby-derived API shape" notes, **"Plex-style" as a UI idiom** (the preplay/detail/player design comments and `PLEX_UI_PLAN.md`/`PLEX_VIEWS_PLAN.md` — those plans are KEPT), the `resolve_media_server()` legacy-value note, and the retired key NAMES inside tests that assert their absence. ⚠ The plan's §1 criterion 2 claimed `frontend/src` had no such idiom so the grep should reach zero; it has ~15 (all comments) — the plan's own rule for that case is to extend the criterion rather than rename a design comment, and that is what was done (corrections recorded in the plan's new §8).

**⚠ Deploy + accept (RKM-HP) — api, web AND nginx changed, so rebuild both images:**
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
docker compose -p rkm-bundled up -d --build api web
```
Prefer this over a full `bootstrap.ps1`: `render_config.py` changed, but its only effect is dropping now-unread keys from `.rkm.env`, and bootstrap would also re-run the provisioner and **cancel an in-flight library scan** (a `.rkm-cinema.ps1 status` first shows whether one is running; let it finish). A later `deploy` will tidy `.rkm.env` for free.
**Eyeball:** browse a library → open an item page → **Settings** (health cards: radarr/sonarr/tmdb/jellyfin only, no Plex/Emby) → play a movie **and** a transcoded episode → switch subtitles → **"Watch on Jellyfin"** from a watchlist card → request a title end-to-end. Then merge: FF `refactor/remove-plex-emby` → `main`, FF `experiment/bundled-docker-stack`, push all three.

**Found but deliberately NOT fixed (unrelated pre-existing doc drift, so the next session can do it on purpose):** `docs/ARCHITECTURE.md` §10 still describes `dashboard-data.json` built by `scripts/rebuild_dashboard.py`, and §11 still describes the removed `app.js`/`api.js` legacy frontend — both were deleted in 2026-09-08.
## ▶ LATEST SESSION (2026-09-11) — PLAYER FIT / ORIENTATION / FULLSCREEN ✅ (branch: `feat/player-layout`, commits `503d11f` → `31d6d31`, then this record; **ACCEPTED + MERGED to `main` 2026-09-11 — USER-CONFIRMED ON RKM-HP: "everything working"**)
**User-reported (phone browser AND laptop browser):** *"it doesn't fit the screen — there's a border around it that looks blank/transparent"* · *"on mobile the controls of the player are not fitting the screen"* · *"on the laptop the controls go down below the bottom screen margin"*.

**Nothing was guessed: the layout was MEASURED before it was changed** (`tools/measure_player_layout.py` drives the real `<Player>` in Chromium at 10 device sizes; baseline **3/10 PASS**). Three separate structural faults, all confirmed with numbers:

1. **The dock could sit 28–128px BELOW the visible screen.** The stage was a flex item with an `auto` min-height, so it could not shrink below the `<video>`'s intrinsic height (540px for the fixture, more for a 1080p file): the column overflowed the fixed shell, and the transport bar — `absolute bottom-0` *inside that stage* — went with it (measured dock bottom **628** on a 600px-tall window, **544.8** on a 390px-tall landscape phone). **Fix:** the `<video>` is out of flow (`absolute inset-0`) inside a stage that is the whole shell, and both chrome bands are anchored to the SHELL's edges (`.rkm-player__dock` / `__top`), so their position can no longer depend on the picture's size.
2. **The transport row was ~468px of controls in one non-wrapping flex row** (play · prev/next ep · mute · 64px volume slider · mode chip · time · settings · PiP · fullscreen) → **78px off-screen on a 390px phone** (measured button right edge 467.6), with the clock pushed out first. **Fix:** the clock now rides WITH the seek bar, the transport row holds only buttons, and it drops a tier below `sm` (36px targets, volume/PiP/mode-chip/prev-next hidden; row may wrap as a last resort — the dock is bottom-anchored so wrapping grows it UPWARD). **Added the missing ±10s skip buttons** (the keyboard had them; a phone had no way to nudge the timeline).
3. **The "blank transparent border" was the video being capped at its intrinsic pixels** (`max-h-full max-w-full`) inside a `p-4` box: on a 1366×768 laptop it rendered 960×540 with a 203px band either side filled by the `opacity-40 blur-md` poster + `bg-black/55` scrim. **Fix:** `h-full w-full object-contain` on the shell-sized stage (letterbox = the video's own black), `rounded-lg` gone; the keyart backdrop stays only for the pre-buffer moment and behind the chrome scrims.

**Plus, while in there (all guarded by tests):** the shell is `fixed` + `100dvh` (+`100vh` fallback) so a mobile URL bar cannot hide the dock; safe-area padding for the home indicator/notch is in `.rkm-player__*`; overlays (subtitles, Up-Next, settings) ride a `--rkm-dock-h` published by a ResizeObserver instead of guessing `bottom-24`/`bottom-28`; body scroll is locked while the player is open (iOS rubber-band was dragging the page under the fixed shell); fullscreen now picks a real path (`fullscreenPlan` — shell where the Element API exists, the video's own `webkitEnterFullscreen` on an iPhone where it does not, hidden when neither); a short viewport collapses the header's second line (`playerChromeFor`); `touch-manipulation` + no selection callout/loupe on the shell.

**Verified:** `10/10 viewports PASS` (320×568 → 1920×1080, portrait + landscape + short windows), with the tool now also asserting the row never clips, every rendered control is ≥32px and inside the viewport (6 controls @36px on phones, 9 @40px above), the header policy per viewport, the settings overlay opening fully on screen, and `--fullscreen` entering REAL element fullscreen on the four desktop sizes (shell == screen, dock bottom == screen bottom, 0 overflow). Before/after screenshots delivered in chat. Gates after every phase: **164 vitest tests**, `tsc --noEmit` clean, `vite build` green.

**The harness earned its keep:** the `--overlays` probe caught a fault this branch introduced — the stage carried `z-10`, so its own dialogs (settings panel, z-30) were trapped BELOW the top chrome (z-20) and the panel's ✕ became unclickable on short viewports. Caught and fixed before the user ever saw it (`31d6d31`, an unindexed stage).

**Verification infra committed** (not shipped — `vite build` only builds `/index.html`): `frontend/harness/player-frame.html` + `player-frame.tsx` (mounts the real player against a stubbed API; one iframe = one viewport) and `tools/measure_player_layout.py`. ⚠ Restart the dev server after editing app source — an orphaned `vite` holding port 5199 keeps serving the pre-edit module (it cost this session a false "no change" measurement).

**Deliberately NOT done:** `viewport-fit=cover` (would make the whole app full-bleed and need sticky-header top-inset handling that cannot be verified without a notched device; the player is already correct without it — see `PLAYER_LAYOUT_PLAN.md` §2.3).

**To accept (web-only — no api/backend change):** `docker compose -p rkm-bundled up -d --build web`, then check the phone in portrait AND landscape (picture fills the frame, every control on screen, nothing under the browser toolbar) and the laptop window. Merge `feat/player-layout` → `main` (fast-forward) after that eyeball, then fast-forward `experiment/bundled-docker-stack` and push all three.
## ▶ LATEST SESSION (2026-09-11) — PROD (Plex/Emby) STACK RETIRED + ONE ENTRY POINT NAMED `rkm-cinema.ps1` ✅ (branch: `chore/retire-prod-stack`, commits `d14ceb5` + `bcc25c9`; **ACCEPTED + MERGED to `main` 2026-09-11 — USER-CONFIRMED ON RKM-HP: "everything working"**)
**User decisions (2026-09-11):** *"i dont want use prod profile anymore as plex and emby's role is taken by jellyfin so remove that stack and just keep jellyfin and backend"* · *"scripts names should rkm-cinema.ps1"*.

**`run-rkm-cinema.ps1` deleted.** It was a pre-bundled-stack deploy (its own text said `:8123`) that ran plain `docker compose down` / `up -d --build` with **no `-p rkm-bundled`** — so running it today either collides on 8124 or raises a *second* stack under the default project name with fresh empty `jellyfin-config` volumes beside the real ones. That is the "state looks deleted / split across project names" trap this repo already documents, sitting in the repo root as a loaded gun. The bundled api + web + Jellyfin stack is now the only deployment.

**A missing `MEDIA_SERVER` no longer selects Plex.** Both the class default and the provider factory fell back to `"plex"`, so a config that lost the key silently swapped the whole library backend — and the symptom (every library row greyed out) reads like a broken drive mount, not a config default. There is now ONE rule, `config.settings.resolve_media_server()`, shared by the config loader, the provider factory and `/api/config`: jellyfin is the default *and* the safe fallback for a blank/unknown value; `plex`/`emby` are still honoured when explicitly asked for. (`render_config.py` already defaulted to jellyfin, so all four now agree.)

**Latent crash found by flipping that default — fixed.** `HealthChecker.check()` walked `lib.providers` unguarded, so on a stack whose configured media server has no credentials yet (a fresh Jellyfin before the provisioner writes its API key — a state this stack has actually been in) `/api/health` raised `AttributeError` and every client read the app as dead. It now reports that one service `ok=false` (degraded) and the endpoint answers; Jellyfin provider health is also attributed to the `jellyfin` service, not only plex/emby. Also kept the legacy `plex=` passthrough working (an explicitly-supplied PlexService *is* a request for the Plex backend).

**Docs told the truth again:** README (intro, diagram, deep-links row, script list, env table, ports table — prod column gone), ARCHITECTURE (deploy lines + the stale `:8123`), `.env.example` (`PLEX_*`/`EMBY_*` removed, `MEDIA_SERVER` documented as jellyfin-only), REPO_STRUCTURE_PLAN. **`docs/TAILSCALE_HOSTING.md` was rewritten outright**: it still described serving a generated `dashboard.html` via `python -m http.server` on `:8123` and regenerating it with `build_dashboard.py` — all removed with the legacy app. It now documents exposing the *running* stack (`:8124`) over Tailscale, which is what a phone actually needs.

**One entry point, and it's named after the app:** `rkm.ps1` → **`rkm-cinema.ps1`** (21 refs in README, 21 in OPERATIONS, plus ARCHITECTURE/TAILSCALE/`tools/rkm_status.py`/a test docstring). A **forwarder stays at the old name** (prints "renamed, forwarding") so notes and shortcuts keep working; it forwards raw `$args` on purpose so `restore -Archive <file>` and `-Yes` still bind. `bootstrap.ps1` keeps its name — it's the builder, and `rkm-cinema.ps1 deploy` wraps it.

**Deliberately NOT done here (now scoped for the next session):** the Plex/Emby *provider code* — `services/plex.py`, `plex_check.py`, `emby.py`, `library/plex.py`, `library/emby.py`, the `GET /api/plex/thumb` route, `scripts/verify_plex.py`, ~15 test files. That is an API-contract change (removing an endpoint) and a large test surface, so it is not smuggled into an ops cleanup. **It is now planned: `docs/REMOVE_PLEX_EMBY_PLAN.md` on branch `refactor/remove-plex-emby`** (227 functional references / 38 files → 0, phased with gates, 10 files / 1,562 lines deleted outright). Also left alone on purpose: PROGRESS.md's dated narratives still name `run-rkm-cinema.ps1`/`:8123`, and the older plan docs keep their original numbers — that is the record of what was true then.

**Verified:** backend **502 passed** (499 + 3 new guards: jellyfin default, legacy plex still explicit-only, the one-resolver rule), ruff clean, docs link checker green (29 files / 7 links). PowerShell is static-checked only (no `pwsh` in the sandbox): both scripts pure ASCII, no trailing space after a line continuation, braces balanced — user to confirm with `.\rkm-cinema.ps1 help` and `.\rkm.ps1 help`.

**To pick this up:** `git fetch origin; git checkout chore/retire-prod-stack; git pull`, then rebuild the **api** (backend changed) — `docker compose -p rkm-bundled up -d --build api` — and `.\rkm-cinema.ps1 status`. A full `deploy` works too but needlessly re-runs the provisioner (and must not be run mid-scan).

## ▶ SESSION (2026-09-10) — DOCS CONSOLIDATED INTO `docs/`, MERGED TO `main` ✅ (commit `cd8201a`)
- **Every root markdown file except `README.md` moved into `docs/`** with `git mv` (history preserved): `ARCHITECTURE.md`, `PROGRESS.md`, `TAILSCALE_HOSTING.md`. The root now has exactly one markdown file.
- **References fixed, not left to rot:** 26 `docs/<name>.md` mentions in PROGRESS.md and 1 in ARCHITECTURE.md dropped the prefix (from inside `docs/` the old form pointed at `docs/docs/`); navigable `README.md` mentions became `../README.md`; ARCHITECTURE.md's repo-layout tree now shows the real layout; the root README's layout block + docs table point into `docs/` and gained a `TAILSCALE_HOSTING.md` row (it was previously unreferenced).
- **Deliberately unchanged:** the dated session narrative in PROGRESS.md that names files as they were at the time (editing those would falsify the record), and mentions of files that no longer exist.
- **New `tools/check_md_links.py`** gates future moves: every relative markdown link must resolve (29 files / 7 links, all resolve; exits non-zero otherwise).
- **Merged to `main`** — fast-forward `9328c9e → cd8201a` — and `experiment/bundled-docker-stack` fast-forwarded to the same commit; all three refs pushed.
- Gates: backend **499 tests**, ruff clean. CI contract-drift check unaffected (`docs/api/` did not move).

## ▶ LATEST SESSION (2026-09-10) — "EVERY SHOW WATCHED" ROOT-CAUSED + ONE COMMAND TO RUN IT ALL ✅ (branch: `feat/configurable-media-libraries`)
**User-reported:** "the tv shows are coming up as watched again" → answered with live evidence, not theory.

**Why shows read as watched — Jellyfin's vacuous rule.** A *series* is marked played when all its episodes are played; with ZERO episodes indexed that is vacuously true. Mid-scan (and after a cancelled scan) that makes every show tick as watched. Our app only renders the flag Jellyfin reports.

**The old DB made it permanent:** it carried another Jellyfin's records (series created 2024-01 → 2026-07) with `Played=True` on 112/116 series — confirmed by two independent sources (Jellyfin UserData and our own /api payload). Dropping `jellyfin-config` and re-provisioning cleared it.

**Verified after the fresh scan (scan Idle, 18:00→18:08 UTC):**
- TV Shows: **116 series / 5190 episodes / 404 seasons** at `/media2/TV Shows`; Movies 712; Movies Kids 140.
- Classifier: **content-to-watch 115**, all-played 0, vacuous-watched 1 — the single "watched" show is a folder literally named `New folder` with no episodes (junk on the drive; rename or delete it).
- `/api/library/folders` → all three libraries `ok=true`, no warnings; `/api/library/series/<id>/episodes` → 8 episodes for '3 Body Problem'.

**Correction (mine):** an ad-hoc probe of mine used `Limit=0`, which in Jellyfin means *return zero items* — so episode counts read 0 everywhere. Count with `TotalRecordCount`, never `len(Items)`. The committed tools read `TotalRecordCount` and were not affected; the trap is now documented in `OPERATIONS.md`.

**Provisioner fixes (both reproduced live today):**
- `240d848` fresh install: `wait_ready()` accepted any HTTP 200 and `wizard_pending()` read "unknown" as "done", so it skipped creating the admin and died → no API key → every library disabled. Now readiness requires a JSON `Version`, the wizard check is tri-state, and `ensure_admin()` retries ~2 min.
- `88d925d` API key: 10.11 wants `POST /Auth/Keys?app=<name>` with an EMPTY body (JSON body → 400) and lists keys as `AppName`/`AccessToken` (not `App`/`Key`). Verified live by minting a real key.

**Consolidation (user asked "how do I remember all of these"):**
- **`rkm.ps1`** — one entry point: `status | deploy | backup | restore | schedule | diagnose | logs | help`; every verb wraps the real script so the two can never diverge.
- **`OPERATIONS.md`** — one page: the verbs, the three rules (no `down -v`; no restart mid-scan; always `-p rkm-bundled`), the fresh-install runbook, a symptom→command table, and what survives what.
- **`tools/rkm_common.py`** + **`tools/rkm_status.py`** — shared env/URL resolution so the tools run on Windows (`localhost`) *and* in the sandbox (`host.docker.internal`); all five existing tools now use it.
- Tests: `backend/tests/test_tools_rkm_common.py` (10) — caught a real bug (an `export KEY=value` line parsed as key `"export KEY"`). Gates: **499 pytest** · ruff clean.

## ▶ LATEST SESSION (2026-09-10) — ALL LIBRARIES "DISABLED" ROOT-CAUSED ✅ (branch: `feat/configurable-media-libraries`, commit `f678f6a`)
**User-reported: "all of three libraries on the left bar shows disabled — TV Shows, Movies, Movies Kids". Probe of the live stack split the problem cleanly in two: Jellyfin's own folders were CORRECT (`Movies → /data/Movies`, `TV Shows → /media2/TV Shows`, `Movies Kids → /data/Movies Kids` — the B: drive, the /media2 mount, the provisioner wiring and the prune all worked), while the api reported all three `ok=False`.**
- **ROOT CAUSE (my bug):** `Config._load()` copies real environment variables into the config env only for its DECLARED keys plus `MEDIA_LIBRARY_*`. `RKM_MEDIA_PATH` / `RKM_MEDIA_PATH_2` were in NEITHER list, so `parse_media_libraries()` ran with **no media roots**, could not translate any host-style path, and — now that the matcher is honest about untranslatable paths — reported every library unresolved. The sidebar therefore greyed out all three. The provisioner was unaffected (it reads `os.environ` directly), which is exactly why the two halves disagreed.
- ⚠ **Correction to the previous record:** the earlier read of the warning *"RKM_MEDIA_PATH is not set"* as a stale container env was WRONG. The container had the variable (render_config writes it into `.rkm.env`); Config was filtering it out. Do not "fix" that warning by force-recreating containers — check the passthrough filter first.
- **Fix:** `config/settings.py` gained `MEDIA_CONFIG_KEY_PREFIXES = ("MEDIA_LIBRARY_", "RKM_MEDIA_PATH")` + `is_env_passthrough_key()`, and the override loop was extracted into `Config._env_passthrough()` so the contract is testable instead of duplicated. Deliberately narrow — other `RKM_*` keys (admin passwords, ports) still never reach the api config.
- **Tests:** `tests/test_config_env_passthrough.py` (6) go through the REAL method: two-drive translation, single-drive, predicate coverage, and that unrelated/sensitive keys stay dropped. Verified the test FAILS against the old filter — it reproduces the live warning and the untranslated `B:/RKM_MEDIA/TV Shows` path vs the fixed `/media2/TV Shows`.
- **Gates:** **465 pytest (was 459)** · ruff clean. No /api contract change, no frontend edit.
- ⚠ **Deploy:** `.\\bootstrap.ps1` again (backend change → api image). Then `/api/library/folders` must show `ok=True` for all three, and the sidebar libraries go live. `RKM_MEDIA_PATH_2=B:/RKM_MEDIA` is now UNCOMMENTED in the live `.env` (done during this session) — the B: mount and `/media2/TV Shows` wiring are already confirmed working in the running stack.

## ▶ LATEST SESSION (2026-09-10) — LIBRARY CLEANUP (user-approved) ✅ (branch: `feat/configurable-media-libraries`, commit `ca88c65`)
**User decision (2026-09-10), after the probe found two leftover libraries with 404'd artwork: "Clean them up — have the provisioner remove libraries that aren't configured or discovered targets (files stay on disk, they just leave the app)".**
- **`prune_untargeted_libraries()` (+ `_under_mount`, `_prune_enabled`):** after wiring, bootstrap deletes any Jellyfin library that is not a target. `target_libraries_with_source()` now reports where the targets came from — `configured` | `discovered` | `sample` — which is what makes pruning safe to gate on.
- **Safety rails (this deletes things, so each one matters):** pruning is **REFUSED when the source is `sample`** (nothing configured AND nothing discovered = exactly what a failed drive mount looks like — pruning there would delete the user's real libraries); `RKM_PRUNE_LIBRARIES=false` is a strict no-op; a target NAME is never deleted (case-insensitive); only libraries whose Location sits under **our own container mounts** are considered (Jellyfin-internal collections and anything outside the media roots survive); files on disk are never touched, only the library registration. The bootstrap log now prints the target list WITH its source, so it is always clear why it pruned — or why it refused.
- **`.env` / `.env.example`:** `RKM_PRUNE_LIBRARIES` documented (default ON for the app-managed bundled Jellyfin; set false to keep libraries the app does not declare), rendered into `.rkm.env` so the provisioner container sees it. 37 active `.env` keys.
- **Gates:** **456 pytest (was 444; +13)** · ruff clean.
- ⚠ **What will happen on the next bootstrap:** with `MEDIA_LIBRARY_*` all commented, discovery names the targets. Live preview of what Jellyfin already knows under `/data`: `Movies Kids` (140 items — becomes the target) and `media` (7 items — **denylisted from discovery**, so it is NOT a target). So the stale `Movies` (6 items) and `TV Shows` (1 item) are removed, and if `D:\RKM_MEDIA\Movies` or `B:\RKM_MEDIA\TV Shows` exist as real folders they are wired (repairing the same-named stale library instead of removing it). Watch for `removed stale library '…'` / `libraries to wire: [...] (source: discovered)` in the bootstrap output; `RKM_PRUNE_LIBRARIES=false` reverts the behaviour instantly.

## ▶ LATEST SESSION (2026-09-10) — POSTER CACHING FIXED + DRIVE/BROWSE DIAGNOSIS ✅ (branch: `feat/configurable-media-libraries`)
**User-reported (2026-09-10, after deploying the media-root work): "when i click Libraries -> Movies Kids the posters are being loaded everytime" + "there are state watchlist and continue to watch, recently added items — will it by itself get overridden or we can create a fresh". Both questions investigated against the LIVE bundled stack (`:8124` / Jellyfin `:8098`) rather than answered from memory.**
- **ROOT CAUSE of the poster reloads (verified live):** `nginx/default.conf` stamped **`Cache-Control: no-store` on EVERY `/api/` response**, posters included — so each navigation re-downloaded all artwork through nginx → api → Jellyfin. Measured: a 140-title folder ≈ **13 MB per visit** (each 500px poster ≈ 95 KB). Jellyfin itself had been sending `Cache-Control: public, max-age=31536000` (1 year) for images; our own proxy layer threw that away, and the api route sent **no cache headers at all**.
- **Fix (commit `c654d8a`):** nginx keeps the blanket `no-store` for dynamic JSON and gives the artwork paths (`jellyfin/poster|person|backdrop`, `plex/thumb`) a nested location with `public, max-age=604800, stale-while-revalidate=604800` + `proxy_hide_header Cache-Control` so exactly ONE header is sent (keep in sync with `ARTWORK_CACHE_CONTROL` in `api/routes/jellyfin_poster.py`). The api sets the same policy itself (covers dev/Vite and any non-nginx proxy), **forwards Jellyfin's `Last-Modified`/`ETag`**, and answers a matching `If-None-Match`/`If-Modified-Since` with a bodiless **304**. A MISSING image is still never cached (artwork that appears later must be retryable). `get_poster()` returns the validators as ADDITIVE keys, so Plex/other providers are unaffected.
- **Verified by execution, not by reading:** `tools/verify_nginx_artwork_cache.py` runs a stand-in api behind the **REAL** repo nginx config and asserts all four artwork paths are cacheable, JSON stays `no-store`, and one `Cache-Control` header is present — **7/7 checks pass**. This caught a genuine config bug first: `proxy_pass` is NOT inherited into a nested location (all artwork 403'd) — hence the explicit `proxy_pass` in the nested block.
- **Gates:** **444 pytest (was 431; +13 in `tests/test_artwork_cache.py`)** · ruff clean · nginx config executed + asserted. No /api contract change, no frontend edit.
- **Diagnosis: browse state is HEALTHY (no action needed).** `/api/library` → movie 146, show 1, recent 9; `/api/library/continue-watching` → **12 items**. Continue Watching / Recently Played / Recently Added are all PROVIDER-DERIVED (Jellyfin `/Items/Resume`, `/Items/Latest`, played items) — they recompute on every request and self-populate as titles are played/scanned; there is nothing to "create". The **watchlist is app-owned** (its own store at `<media root>/rkm/watchlist.json`) and does **NOT** self-populate: `AUTO_ADD_ENABLED=false` in `.env` gates the autonomous auto-add (the `WATCHLIST_SCHEDULER=true` loop only reconciles status). Currently **1 entry, state `pending`**.
- ⚠ **Found while probing (needs a user decision):** Jellyfin has THREE libraries — `Movies` (6 items → `/data/media/_movie`), `TV Shows` (1 item → `/data/media/_tv`) and `Movies Kids` (140 items → `/data/Movies Kids`). The first two are LEFTOVERS pointing at the old sample tree; their **item images 404** (verified through both raw Jellyfin and the app proxy), so they inflate the library counts and show broken artwork in the sidebar. They are not configured targets, so the provisioner neither repairs nor removes them. Cleanup is destructive → ask before implementing a reconcile step.
- ⚠ **Deploy (RKM-HP):** `nginx/default.conf` lives in the **web** image and the poster route in the **api** image → `.\\bootstrap.ps1` (full rebuild), then hard-refresh. Eyeball: open a folder once, then navigate away/back — the Network tab should show posters coming from **memory/disk cache** (`200 (from disk cache)` or `304`), not repeated 200s. Artwork changes in Jellyfin appear within the week (or on revalidation).

## ▶ LATEST SESSION (2026-09-10) — SECOND MEDIA DRIVE SUPPORTED (`B:` TV + `D:` movies) ✅ (branch: `feat/configurable-media-libraries`, commits `a402ee8`+`e101581`+`52a168c`+`683415f`)
**User spec (2026-09-10, continuing the harnessed session): "b and d are separate drives, one have tv shows the other have movies... i will mention it in .env file" + "merge will be done later once i verify everything working". The stack mounted exactly ONE host path at `/data`, so the TV drive was UNREACHABLE by any container — this session makes media roots a list. Backend + config + compose only; no /api contract change, no new deps, no frontend edit.**
- **`media_roots(env)` (commit `a402ee8`, shared config layer):** `RKM_MEDIA_PATH` → `/data`, `RKM_MEDIA_PATH_2` → `/media2`, `RKM_MEDIA_PATH_3` → `/media3` … ordered, blank keys ignored, a host path declared twice keeps its FIRST mount and warns (a duplicate mount would only duplicate every library). `translate_media_path()` resolves a host PATH against EVERY root — longest matching prefix wins (nested roots behave) — and a path on a drive that was never declared now says exactly how to fix it: *"…declare it as RKM_MEDIA_PATH_2 in .env"* (the first test run caught the old message being a dead end).
- **Provisioner (commit `e101581`):** `_media_root_mounts()` derives the mounts from the ENV KEYS (not from filesystem guessing), so compose can mount `/media2` unconditionally yet an undeclared root is never discovered twice. `discover_media_root_libraries(root)` now returns paths rooted at the mount it scanned — it hardcoded `/data/`, so a second drive's libraries would have pointed at the wrong path. `discover_all_media_roots()` unions the roots; a folder NAME on two drives is kept once with a note naming the fix (Jellyfin/sidebar names must be unique).
- **`render_config.py` (commit `52a168c`) — real cross-platform bug fixed:** the "is this the repo-local sample tree?" decision used `Path.is_absolute()`, and `D:/RKM_MEDIA` is ABSOLUTE on Windows but RELATIVE to a POSIX interpreter — so any non-Windows run would have created `media/_movie` + `media/_tv` INSIDE the user's media drive. New `is_real_media_root()` treats drive-letter + UNC paths as real everywhere (own test). Also: every configured root is printed (`media root: B:/RKM_MEDIA → /media2`), a library on an extra drive is reported against that drive instead of against the primary root, app state (`downloads/`, `rkm/`) stays on the PRIMARY root only, and `RKM_MEDIA_PATH_N` passes into `.rkm.env`.
- **Compose (commit `683415f`):** `x-media2` / `x-media3` anchors mount `/media2` + `/media3` into api, jellyfin, radarr, sonarr and the provisioner (a container only reads what is bind-mounted). Unset keys point the extra mounts at `./data`; qBittorrent keeps its primary-root downloads mount; web/prowlarr untouched. Verified: YAML parses, all five services resolve the three mounts, `x-*` remain extension fields.
- **`.env` (gitignored, live):** `RKM_MEDIA_PATH_2=B:/RKM_MEDIA` is written COMMENTED with instructions (enabling a second drive is the user's call — an unshareable drive fails the whole `compose up`), every `MEDIA_LIBRARY_*` stays commented → the provisioner auto-discovers each root's subfolders. 34 active keys unchanged, auth keys intact.
- **Gates:** **431 pytest (was 398; +33 this session)** · ruff clean · **vitest 160/160** · `tsc` · `build` green.
- ⚠ **Deploy (RKM-HP) — NOT YET DONE, merge PARKED at the user's request:** first uncomment `RKM_MEDIA_PATH_2=B:/RKM_MEDIA` in `.env` **and confirm Docker Desktop can actually mount `B:`** (Docker Desktop → Settings → Resources → File sharing / the WSL mount), then `.\\bootstrap.ps1` (api + provisioner + compose changed → full rebuild). Eyeball: `docker logs rkm-bundled-provisioner` shows `media root(s)` + `[jellyfin] libraries to wire: [...]` with both drives' folders (`/data/...` and `/media2/TV Shows`), the sidebar Libraries group lists them, each opens its own folder page, and the watchlist starts fresh at `D:\RKM_MEDIA\rkm\watchlist.json`. If `docker compose up` fails immediately, it is the `B:` mount — that is the loud failure to expect.

## ▶ LATEST SESSION (2026-09-10) — MEDIA ROOT WIRED TO THE REAL DRIVE (`D:\RKM_MEDIA`) ✅ (branch: `feat/configurable-media-libraries`, commit `d629e17`)
**User spec (2026-09-10): point the stack at the REAL media drive; downloads/dubbing are Sonarr+Radarr's job (already configured — the app just hands titles to them); create a FRESH watchlist whose location comes from `.env`. Live-probed the user's own *arr instances first (see below), then closed the config gaps that `RKM_MEDIA_PATH=D:/RKM_MEDIA` exposes. Backend + config only — no /api contract change, no new deps.**
- **Live probe (radarr `:7878`, sonarr `:8989` @ 192.168.65.254 = the Windows host):** Radarr root folder = `D:\RKM_MEDIA\Movies`, Sonarr root folder = `B:\RKM_MEDIA\TV Shows`. Both *arr `/api/v3/filesystem` calls returned the SAME listing for every path asked (`D:\`, `D:\RKM_MEDIA`, `B:\`, `B:\RKM_MEDIA`) — the container's path translation ignores the drive letter, so that endpoint CANNOT be used to enumerate the real folders. ⚠ The real folder list must come from the user on Windows (`Get-ChildItem D:\RKM_MEDIA -Directory | Select Name`) before per-folder `MEDIA_LIBRARY_N_*` entries are written — not guessed.
- **`RKM_MEDIA_PATH=D:/RKM_MEDIA` set in the repo `.env`** (was `./data`), and the `MEDIA_LIBRARY_1/2` sample pairs (Movies/TV Shows → `/data/media/_movie|_tv`) are now COMMENTED OUT — with none set, the provisioner auto-discovers every subfolder of the media root as its own library. Watchlist DB path already comes from `.env` (`WATCHLIST_DB_PATH=/data/rkm/watchlist.json` → `<media root>/rkm/watchlist.json`), so the fresh store lands beside the media, per the user's instruction. The old 13-title `./data/rkm/watchlist.json` is left untouched on disk (unanchored copy; exportable).
- **`config/media_libraries.py` (commit `d629e17`):** `translate_media_path()` — a PATH may be written host-style (`D:/RKM_MEDIA/Movies Kids`) OR as the container path (`/data/...`); host paths under the root are translated to their `/data` equivalent (case-insensitive drive match), a path OUTSIDE the root warns loudly instead of being faked, the root itself maps to `/data`. New `MEDIA_LIBRARY_N_TYPE` (movie|tv|mixed aliases) → normalised Jellyfin collection type, default `mixed`.
- **Provisioner:** builds from context `./backend` (so it `COPY`s the SHARED `config/media_libraries.py` — one parser, no copies; `PYTHONPATH=/app`) and wires EVERY configured library. New `discover_media_root_libraries()` covers the zero-config case; `_folder_check()` reports MISSING / NOT A FOLDER / NOT READABLE and SKIPS that library rather than creating a broken empty one — an EMPTY folder still wires (it indexes as files arrive). `configured_target_libraries()` priority: explicit `MEDIA_LIBRARY_N_*` → auto-discovery → legacy sample pair.
- **`render_config.py`:** `ensure_storage(data, env)` no longer seeds the sample `media/_movie`/`media/_tv` dirs when the root is an ABSOLUTE (real) drive — only for the repo-local `./data` default — so bootstrap can never pollute `D:\RKM_MEDIA` with sample folders; it now prints each configured library's existence at render time (`[env] library 'X' → path [ok|MISSING]`). `RKM_MEDIA_PATH` + every `MEDIA_LIBRARY_*` key pass into `.rkm.env` (the api container env) and the provisioner now reads that same file.
- **Gates:** **398 pytest (was 366 test cases at the previous record; +2 new files `test_provisioner_libraries.py` 10 cases + `test_render_config.py` 3)** · ruff clean (canonical `ruff check .`; tests are excluded there) · **vitest 160/160** · `tsc` · `build` green.
- ⚠ **Deploy (RKM-HP):** `.\\bootstrap.ps1` (api + provisioner + compose changed → full stack rebuild), hard refresh. **Then eyeball:** sidebar **Libraries** lists one entry per `D:\RKM_MEDIA` subfolder (auto-discovery; no `MEDIA_LIBRARY_*` needed), each opens its own folder page; `docker logs rkm-bundled-provisioner` shows `[jellyfin] libraries to wire: [...]` + `ok`/`EMPTY`/`SKIP <reason>` per folder — a SKIP line means the mount/path needs fixing; the watchlist starts FRESH (D:\RKM_MEDIA\rkm\watchlist.json created on first run); Download on a watchlist title still lands in the existing Sonarr/Radarr (they own the download dirs). Then merge `feat/configurable-media-libraries` → main + push + fast-forward `experiment/bundled-docker-stack`.

## ▶ LATEST SESSION (2026-09-10) — CONFIGURABLE MEDIA LIBRARIES EXECUTED ✅ (branch: `feat/configurable-media-libraries`, 6 commits `33e46e6`→`0cb8624`)
**User spec: media folders fully configurable via `.env` (`MEDIA_LIBRARY_N_NAME` + `MEDIA_LIBRARY_N_PATH`); the sidebar renders configured library names; clicking a library lists that folder's media; no hardcoded Movies/TV Shows; validate + warn on missing folders. Plan `MEDIA_LIBRARIES_PLAN.md`; executed in gated phases — backend additive-only (ADR-0001), generic MediaLibrary{name, path}, container-aware env rendering.**
- **Design (user-confirmed):** PATH = the media server's own folder path (the bundled Jellyfin reports `/data/media/_movie` etc. via VirtualFolders — live-probed 2026-09-10). RKM never scans folders itself; a configured library is live when its PATH matches a real server folder, warning otherwise.
- **Phase 1 (commit `5a3499a`):** `config/media_libraries.py` parses an arbitrary count of `MEDIA_LIBRARY_N_NAME/PATH` into `MediaLibrary{name, path}` (name = user-facing label — the internal key is never displayed) with structural warnings (empty/duplicate entries); wired into `Config.media_libraries` + `media_library_warnings`; real-env overrides accept the keys. +15 tests.
- **Phase 2 (commit `1798a24`):** `LibraryProvider` gains `library_folders()` + `items_in_folder()` (ABC default `[]`) with `LibraryService` aggregation; Jellyfin implements both — `library_folders()` reads `/Library/VirtualFolders` (new `_fetch_list_or_items` for the top-level-list shape, 60 s TTL), `items_in_folder()` scopes `/Users/{uid}/Items` by `ParentId=<ItemId>&Movie,Series` (live-verified); pure `match_libraries()` path→folder resolver (path match, name fallback, clear warnings) + `server_default_libraries()` (no-config fallback from the server's own folder names). +16 tests.
- **Phase 3 (commit `ca4e0bc`):** additive endpoints — `GET /api/library/folders` (provider + server folders + sidebar `libraries` list + config warnings) and `GET /api/library/folders/{id}/items` (folder-scoped poster wall). Contract **37 → 39 paths (+205/−0)**. +6 API tests.
- **Phase 4 (commit `00e80b5`):** client types + `getLibraryFolders()`/`getFolderItems()` + `useLibraryFolders()`/`useFolderItems()` hooks; `libraryIconFor`/`libraryByFolderId`/`folderCountLabel`; new `folder` icon glyph. +3 vitest.
- **Phase 5 (commit `26047ff`):** Sidebar Browse keeps Home; new **Libraries** group renders the API names (configured values when set, else server folder names — never hardcoded), amber dot for unresolved paths; `/library/folder/:folderId` folder page (folder-scoped items, heading from API, toolbar countNoun "titles"); `/library/movies` + `/library/shows` become redirects to the matching server folder preserving `?genre` (global-search deep links keep working; Home fallback); MobileNav = Home + first two live libraries, rest in More sheet. Retired the client-side type-split helpers (folders own the pages now). +folder glyph.
- **Phase 6 (commit `0cb8624`):** `.env.example` media-libraries section; `render_config.py` passes every `MEDIA_LIBRARY_*` key through to `.rkm.env` (the api container's env_file); Settings gained a Media libraries card (names + ok/unresolved + warnings).
- Gates: **366 pytest · ruff · vitest 160/160 · tsc · build**; live end-to-end verified vs the bundled Jellyfin (folders enumerate, config matches, broken path warns, folder items scope).
- ⚠ **Deploy (RKM-HP):** `.\\bootstrap.ps1` (api + web both changed; render_config passes the new keys into `.rkm.env` — the repo `.env` now declares `MEDIA_LIBRARY_1/2` Movies/TV Shows → `/data/media/_movie` `/data/media/_tv`), hard refresh, eyeball: sidebar **Libraries** group shows Movies + TV Shows (add/remove a `MEDIA_LIBRARY_N_*` pair in `.env` to see the sidebar + Settings update); clicking each lists only that folder's titles; a deliberately wrong PATH shows the amber warning + Settings "unresolved". Then merge `feat/configurable-media-libraries` → main + push + fast-forward `experiment/bundled-docker-stack`.

## ▶ LATEST SESSION (2026-09-10) — WATCHCARD ⋯ MORE MENU REMOVED + `feat/intelligent-search` MERGED TO MAIN ✅
**User-directed cleanup (continued from the intelligent-search session): the ⋯ More hover menu on Watchlist cards was redundant — the card click already opens the details modal and the hover row already shows the state-driven primary chip (Download / Play / Watch link) + Trailer, so it and its actions duplicated the card. Removed the menu + its now-unused `PopupMenu` import from `WatchCard.tsx` (commit `3920372`, frontend-only, −51 lines).**
- Gates: **vitest 161/161 · tsc · build** green.
- Merged: `feat/intelligent-search` (9 commits `b79a2b3`→`3920372`) fast-forwarded → `main`; `experiment/bundled-docker-stack` fast-forwarded to match; all pushed.
- RKM-HP deploy note (from the record below): backend + web both changed across the branch → `.\\bootstrap.ps1`, hard refresh, eyeball the intelligent-search checklist (⌘K global search, DISCOVER Add to library, no search boxes on Movies/TV/sidebar) — the WatchCard cleanup itself is web-only (`docker compose -p rkm-bundled up -d --build web`).

## ▶ LATEST SESSION (2026-09-10) — INTELLIGENT GLOBAL SEARCH EXECUTED ✅ (branch: `feat/intelligent-search`, 8 commits `b79a2b3`→`f58ab45`)
**User spec (2026-09-10): one intelligent global search answering "do I own this?" first. Plan `GLOBAL_SEARCH_PLAN.md`; executed in gated phases — backend additive-only (ADR-0001), frontend consolidation, no new deps.**
- **Phase 0 probe (live, bundled Jellyfin 10.11 @ host.docker.internal:8098):** `Items?searchTerm` matches Movie/Series/Episode by NAME (episode names + per-episode UserData); People/Genres/BoxSets resolve ONLY via `/Search/Hints`; actor drill-down via `PersonIds`. Locked the contract.
- **Backend (commit `48bd35c`, Phases 1–2):** `LibraryProvider.search_items()/items_by_person()` ABC + `LibraryService` aggregates (Jellyfin implemented; Plex/Emby default-skip). Pure scoring module `services/global_search.py`: `normalize_title`/`title_match_score` (same-name different-year remakes stay distinct), `owned_strong_match`, `is_duplicate_discovery` (tmdb-id + title), `next_episode_facts` (resume ep preferred), `owned_state` (watch/resume/watch_again/next_episode). **Additive `GET /api/search/global`** — owned rows w/ state + series next-episode enrich (≤3 shows), Person/Genre/BoxSet hints, person drill-down titles, TMDB DISCOVER **only when no strong owned match**, duplicates suppressed server-side. Contract **36 → 37 paths (+385/−0)**, +12 tests → **329 pytest** · ruff clean.
- **Frontend Phase 3 (commit `e051423`):** client types + `searchGlobal()` (`80593bf`); pure helpers (+7 tests); **GlobalSearch command palette in the top bar** — debounced, library-first sections ("In your library" rows with ▶ Watch Now / Continue Watching (S/E + min-left) / Play Next Episode / Watch Again + Details; Titles-with-person; genre/collection hints; DISCOVER "not in your library" → Add to library w/ toasts), keyboard ↑/↓/Enter/Esc, `/`+⌘K focus; **`?play=1[&episode=]` deep links** on ItemDetail fire the right starter once data is ready.
- **Frontend Phase 4 (commit `f58ab45`):** consolidation — `/search` redirects Home, `SearchView` page + sidebar Search tab removed, MobileNav Search tab dropped, Movies/TV folder free-text box removed (genre/sort/view stay; folder URL never reads/writes `q=`).
- **Follow-up fix (same session):** DISCOVER "Add to library" from the overlay was wiping previously-added TMDB-only watchlist titles from the local cache (the old `&&` dedupe dropped any existing entry whose imdbId was `""` whenever a new entry also had `imdbId:""`) — the watchlist showed only the new item until a refresh. Now deduped on REAL ids only (`isSameWatchlistTitle`/`upsertWatchlistEntries`, +3 tests → vitest 161/161) with a background entries refetch after the optimistic update.
- Gates: **vitest 158/158 (was 151)** · tsc · build green · no /api change beyond the additive path.
- ⚠ **Deploy (RKM-HP):** api + web both changed → `.\\bootstrap.ps1` (or `docker compose -p rkm-bundled up -d --build`), hard refresh, eyeball: ⌘K → "3 body problem" → In your library w/ ▶ Continue/Play + Details and NO Download/duplicate TMDB; an unowned title → DISCOVER → Add to library; actor/genre/partial queries land owned results; no search boxes on Movies/TV or sidebar; Details opens the item page and Watch/Continue starts at the right spot. Then merge `feat/intelligent-search` → main + push + fast-forward `experiment/bundled-docker-stack`.

## ▶ LATEST SESSION (2026-09-10) — PREMIUM PLAYER CHROME EXECUTED ✅ (branch: `feat/player-tail`, commits `6cdd5c0` + `ae67e03`)
**User-requested player UX refresh on `feat/player-tail` (on top of the roadmap-tail work): Plex-style settings overlay, TV episode prev/next + S/E context, and a typography coherence pass across every player surface. Frontend-only, no /api change, no new deps.**
- **Commit `6cdd5c0` — queue S/E facts:** `QueueEntry` carries `season`/`episode` (mapped in `episodeQueue`); new pure `prevEpisode` + `queueEntryCode` helpers. +3 tests.
- **Commit `ae67e03` — premium chrome:** 1) **Settings overlay** — all extra controls (Speed/Quality chips, Audio/Subtitle selects, live ABR caption, mode + track-count footer) moved out of the main surface into a semi-transparent gear button + glass overlay panel at the top of the stage (Plex-style; backdrop click / Esc / ✕ dismiss; chrome never auto-hides while open). The bottom settings strip is deleted; the transport bar keeps only playback essentials: play · prev/next episode · volume · mode chip · time · settings · PIP · fullscreen. 2) **TV episodes** — prev/next episode chevron buttons on the transport (report stopped before switching), top bar shows the **S1E4 + "N of M"** context line, Up Next card gains its S/E chip. 3) **Type coherence** — title 15px w/ tight tracking, a strict 10px uppercase micro-label scale (chips/context), 11–12px tabular time scale, unified button geometry, duplicate mode chips + duplicate time readouts consolidated (top-bar time removed; single transport readout `cur / total`).
- Gates: **vitest 151/151 (was 148)** · tsc clean · build ok. No /api contract change.
- ⚠ **Deploy (RKM-HP):** web-only → `docker compose -p rkm-bundled up -d --build web`, hard refresh, eyeball: player transport is now minimal; gear (semi-transparent) opens the top settings panel (speed/quality chips persist; audio/subs work; Esc/backdrop close); on a series, prev/next chevrons + "S1E4 · N of M" in the top bar and S/E chips on Up Next; fonts read coherent and premium. Then merge `feat/player-tail` → main + push + fast-forward `experiment/bundled-docker-stack`.

## ▶ LATEST SESSION (2026-09-10) — PLAYER ROADMAP TAIL EXECUTED ✅ (branch: `feat/player-tail`, 4 commits `082f814`→`aa6efb1`)
**Executed the queued player roadmap tail (PROGRESS 2026-09-09 record) on a NEW branch from main @ `67bb9fd`; plan `PLAYER_TAIL_PLAN.md`; gates green after every phase — frontend-only, no /api change, no new deps.**
- **Commit `082f814` — hls.js ABR/buffer policy + live badge:** `hlsConfigFor()` centralises the hls.js build config — 60 s forward buffer (180 s max), a 5 Mbps LAN-first ABR seed (transcodes no longer open blurry while the estimator samples), tuned up/down switch factors (`abrBandWidthUpFactor` 1.2 / `abrBandWidthFactor` 0.85), `capLevelToPlayerSize:false`. Player tracks `LEVEL_SWITCHED` → passive **"Auto · 1080p"** badge beside Quality (informational only — the Quality select stays a cap, never mislabelled). +4 helper tests.
- **Commit `da95be7` — cinema auto-hiding chrome:** top bar + bottom control bar fade out after **2.8 s idle while playing** (`shouldAutoHideChrome` pure helper), cursor hides; pointer/keyboard activity, pausing, loading, errors or Up Next reveal instantly. **Subtitles never hide.** Hover tracking on the seek bar + transport row; hidden chrome is pointer-events-disabled so invisible controls can't swallow clicks. +3 tests.
- **Commit `d35006d` — warm-start next-episode prefetch:** module warm cache (TTL 10 min, cap 8, LRU evict) of in-flight `playback-info` promises keyed by item id. `warmNext()` fires from `timeupdate` inside the last 45 s AND on `ended` (before Up Next auto-play); HLS routes pre-fetch the master manifest once (no-store) so Jellyfin's transcode pipe is hot. Mount consumes the warm promise (no spinner) then deletes it so replays refetch fresh. +6 tests.
- **Commit `aa6efb1` — PiP + Media Session + prefs:** persisted prefs (volume/mute/speed/quality cap — `rkm.playerPrefs.v1`, sanitised per-field) load once per mount and save on every change → carry across episodes AND browser sessions; the per-item quality reset honours the persisted cap. Picture-in-Picture button (capability-gated) + enter/leave tracking; Media Session metadata + play/pause/seek/seek±10/next handlers make the PiP window + OS media keys work; `setPositionState` keeps the OS timeline honest on the report cadence. +4 tests.
- Gates after every phase: **vitest 148/148 (was 131)** · tsc clean · build ok. No /api contract change, no backend edit, no new deps.
- ⚠ **Deploy (RKM-HP):** web-only → `docker compose -p rkm-bundled up -d --build web`, hard refresh, eyeball: transcode opens crisp + "Auto · 1080p" badge appears next to Quality; fullscreen idle ~3 s hides chrome/cursor (subs stay; nudge reveals); finish an episode → Up Next → Play next (and auto) start with no spinner; set volume 40% + 1.5× + 720p → next episode AND a new browser session remember them; PIP button floats the video, OS media keys + PiP controls work. Then merge `feat/player-tail` → main + push + fast-forward `experiment/bundled-docker-stack`.

## ▶ LATEST SESSION (2026-09-10) — Search detail bug FIXED: any live TMDB result opened "Sappho's Tale" ✅
**User-reported (Search tab): searching TMDB (e.g. "game of thrones") listed live results, but clicking ANY row opened Sappho's Tale's detail modal. Root cause: live TMDB hits are built with `imdbId:""` (backend `search.py`), and pending entry **Sappho's Tale** (TMDB-only, no IMDb id) persists with `imdbId:""` — `entryForHit` matched `imdbId === ""` FIRST, so every live hit resolved to the first empty-imdb watchlist entry and hijacked the modal. Fix (`frontend/src/features/watchlist/lib.ts`): IMDb matching only when the hit genuinely carries an id (entry id must be real too); empty-imdb hits now fall through to the correct tmdbId match → `null` → the row's own stub detail. A genuine Sappho's Tale hit still resolves via tmdbId 1756365. +1 regression test → **vitest 131/131 (was 130)** · tsc · build ok. Frontend-only — redeploy `docker compose -p rkm-bundled up -d --build web` (no api/provisioner); user verified fixed on RKM-HP.**

## ▶ LATEST SESSION (2026-09-09) — UX POLISH PASS EXECUTED ✅ (branch: `feat/ux-polish-pass`, 7 commits `37d6a5d`→`35025e5`)
**Executed the last session's queued recommendation (1+2 in one session, 3 as a side check) on a NEW branch from main, gates green after every phase, then headless-accepted the built shell live against the real bundled Jellyfin.**
- **Commit `37d6a5d` — fix(search) [item 3]:** live `/api/search` always returned `tmdb:[]` even though `tmdbKey:true` — ROOT-CAUSED live: the route built every `SearchResult` WITHOUT the required `imdbId`/`snippet` fields (and passed a non-existent `overview` kwarg), so Pydantic raised on EVERY live row and `except Exception: pass` swallowed it into an empty group (suggest worked from the same container — same key, service-layer path). Fix: route maps real fields (`imdbId:""`, `snippet=overview`) and calls the shared `TMDBService.search_multi` (RKM UA + Accept + retry — the path every working TMDB call uses), logging failures instead of hiding them. +6 tests (`test_search_live.py`) → **317 pytest** · ruff clean · contract **zero-diff (36 paths)**. End-to-end verified (fresh uvicorn + real repo key): `/api/search?q=fauda` → 2 live TMDB rows (tv + movie) with posters/snippets.
- **Commit `390cd7d` — item 1a polish:** new shared **`Dialog`** shell (§51 modal chrome: surface-2 panel, white/8 border, 16px radius, modal shadow, black/65 + 8px blur backdrop) with phase-9 a11y built in (scroll lock, Esc, backdrop close, focus moved in + RESTORED on close, Tab trapped). SuggestDetailModal + WatchlistDetail refactored onto it: seeded-art fallback (no emoji), §14 pill chips, §71 button hierarchy, Icon close, skeleton fetch state, reduced-motion-safe trailer scroll. SuggestCard premium pass matching WatchCard (art fallback, hover lift, accent/glass pills, line-clamp). **Settings page rebuilt**: premium header + degraded chip, service cards w/ icons + neutral not-set badge, skeleton loading + EmptyState error (was raw text + npm instruction). Search + Suggest views: premium page headers, glow-focus inputs, Icon search, skeleton/empty states.
- **Commit `2ecfae6` — item 1b player chrome (§68):** full-screen player restyled to the design language — gradient scrim top bar with icon Back + title + mode pill (accent when transcoding), Icon transport (play/pause, volume/volume-x, maximize/minimize — new outline glyphs in Icon.tsx), amber seek bar with glow thumb, Up-Next card on surface-2 with play/cancel, premium error card, settings strip on a surface-2 panel with token selects; z-index via `--z-player`. No behaviour change.
- **Commit `d70d5d5` — item 1c phase-9 checklist:** Discover loading → `.skeleton` shimmer (was legacy pulse), sr-only h1, Library preview empty state + stat cards on tokens (no emoji); Search gets a no-query EmptyState prompt; Watchlist Load-more + My Library footer on tokens; shared CardRow/EmptyState now use Icon (no unicode glyphs); MobileNav More sheet: Esc closes + focus returns, role=menu/menuitem, aria-haspopup. (Reduced-motion is global in index.css; trailer auto-scroll guarded.)
- **Commit `57efc12` — item 2a folder URL state (§60/§63):** `/library/movies` + `/library/shows` read `q`/`genre`/`sort` from the URL (`libraryFilterFromParams/ToParams` — unknown sort keys fall back to recent, never trusted) and write back replace-style, debounced for typing, so refresh/Back/deep links keep the exact view. `<ScrollRestoration>` mounted in the shell → Back from an item page returns to the same grid position. +4 helper tests.
- **Commit `f90c6de` — item 2b sorts + compact view (§16–17):** toolbar sort select now offers **8 honest sorts** (Recently added, A–Z, Z–A, Release date, Recently played, Progress, Runtime, Unwatched first) — every key maps to a field the frozen list payload truly carries; Rating is deliberately NOT offered (list items have no community rating). Grid/list **view toggle** with URL persistence (`view=compact`); compact renders **`MediaListRow`** (thumbnail | title | year | genre | runtime | status table rows). +10 tests.
- **Commit `35025e5` — item 2c ⋯ menus + More actions (§46/§25):** new **`PopupMenu`** (portalled to body so poster overflow/rail clips can't cut it; outside-click/Esc/scroll/resize close; viewport-clamped; role=menu + menuitems; danger tint). MediaCard hover row ⋯ = Play/Episodes · Mark watched/unplayed · View details · Open in Jellyfin (hover + keyboard); WatchCard gets a More row (details/trailer/download/play/watch from live state, hover + focus-within); ItemDetail: Open-in-Jellyfin ghost link moved into a ⋯ More menu + Mark-as-unplayed when watched. **Also fixed a real stacking bug the headless smoke caught**: MediaCard's whole-card open button sat ABOVE poster hover actions once the poster transform created a stacking context — open button now z-auto under the pointer-events-none poster wrapper (z-[1]) and ALL poster hover children gate pointer-events to their visible state (group-hover/focus-within), which also stops invisible chips intercepting card taps on touch.
- Gates after every phase: **vitest 130/130** (+10 pure helpers, from 120) · tsc clean · build ok; no /api contract change. **Headless-accepted LIVE** (harness static+proxy `:8129` → real bundled Jellyfin; 0 console errors / 0 pageerrors): Home, Movies (6 cards), Shows, Watchlist, Search, Suggest, Settings, Discover, item movie page all render; folder sort options = 8, `sort=title` survives reload; `view=compact` → 6 list rows, grid toggle back; card ⋯ menu opens/Esc-closes with Play·Mark watched·View details·Open in Jellyfin; search row → detail dialog opens/Esc-closes (Fauda); item-page ⋯ More opens.
- ⚠ **Deploy (RKM-HP):** `.\\bootstrap.ps1` (api + web both changed) → eyeball: Suggest/Search detail modals + Settings page; full-screen player chrome; Movies/TV folder sort select (8 options), grid/list toggle, URL keeps `?q=&genre=&sort=&view=` on refresh/Back; card ⋯ menus (hover + keyboard) + item-page ⋯ More; **Search now returns live TMDB results** (fauda → tv + movie). Then merge `feat/ux-polish-pass` → main + push (fast-forward `experiment/bundled-docker-stack`).
- **Queued next (recommended order):** 1) player roadmap tail — warm-start/next-episode prefetch, auto-hiding controls + PiP + preference persistence, hls.js ABR ladder; 2) bigger parked items — Bazarr auto-subtitles (needs an OpenSubtitles account), multi-user/auth (roadmap item 6), collections (§67). Also open from the earlier roadmap: item 5 transcode-fallback engine (auto-open Jellyfin when direct play fails) remains partially deferred.

## ▶ LATEST SESSION (2026-09-09) — Premium Media Library UX REDESIGN EXECUTED ✅ (branch: `feat/premium-ux-redesign`, 7 commits `1dfdb10`→`355e20b`)
**User asked to implement the design guide + prototype they dropped in `RKM-CINEMA_NEW_UX/` (Premium Media Library spec + visual HTML). Frontend-only redesign executed in committed phases on a NEW branch (NOT main, per user), gates green after every phase; live-accepted in real Chromium against the `:8124` backend.**
- **Phase 0 — docs:** committed the design reference (`docs(design)` `1dfdb10`).
- **Theme foundation (`89b4787`):** design tokens centralised (spec §41) + the Tailwind zinc scale remapped onto the layered dark surfaces (`#08090B` bg → `#101216` surface-1 → `#15171C` surface-2 → `#1B1E24` elevated, `#F5F5F7`/`#A7AAB2`/`#70747E` text), amber → `#FFC400` accent, emerald → `#35D07F`; Inter type; layered shadows; skeleton shimmer, snap rails, hero vignette, seeded `art-0..5` poster fallback gradients; focus-visible + reduced motion.
- **Shell (`1d1a658`):** Sidebar 240px→72px rail (md–xl) → hidden <md: brand lockup, Browse/Collections/Tools groups w/ consistent stroke icons (new deps-free `Icon.tsx`), selected-pill + 3px yellow indicator, Settings + profile bottom; 64px blurred TopBar (breadcrumb, global search, `/`+⌘K focus); MobileNav bottom bar (Home/Movies/Shows/Search + More sheet); root index → Home (was Settings).
- **Home (`aae945d`):** full-bleed cinematic hero (CW movie preferred → episode → recently added; backdrop → poster → seeded art fallback; Resume + % · time-left progress; Scan Library glass chip), landscape 16:9 Continue-Watching rail (`ContinueWatchingCard`: SxEy pill, always-reachable ▶ resume, 3px edge progress), Recently Played/Added poster rails w/ `SectionHeader` (See all only where a route exists), skeleton/empty/error states, **no provider labels**.
- **Cards + folders (`d8def15`):** `MediaCard`/`WatchCard` poster-first (2:3, 10px radius, hover lift + layered shadow, centered ▶ / Episodes, watched toggle, 3px progress, art fallback, `fluid` grid variant); Movies/TV folder pages = page header w/ human counts + search/pill-genre/sort toolbar + auto-fill grid (mobile 2-up), empty states w/ Scan Library.
- **Item + collections (`d561709`):** full-bleed item page — backdrop hero, overlapping poster, type chip + ★, display title, meta hierarchy, ONE dominant Play/Resume, rich season-grouped episode list w/ in-progress yellow edge; Watchlist page header + accent pills + auto-fill grid; CardRow/EmptyState premium.
- **Search + polish (`355e20b`):** `/search?q=` URL-state (top-bar typing, deep links, Back all seed results); favicon.
- Gates: **vitest 120/120 (+5 pure-helper)** · tsc · build ok; **no /api/contract change**. **Live-accepted** (Playwright-core + local Chrome → real `:8124` data): Home hero + 12 landscape CW cards, Movies 6 / Shows 1 cards, Watchlist 6, Discover rows, `/search?q=fauda` seeds + rows, item page movie + 3BP series (Season 1 + 8 episode rows + Because-you-watched), mobile bottom nav + More sheet — all routes **0 console errors / 0 horizontal overflow / 0 broken images**.
- ✅ **MERGED → main + pushed (2026-09-09):** user ran the branch, confirmed it works, and asked to merge — `main` fast-forwarded `8bb66d9 → b5177d4`, pushed to GitHub, `experiment/bundled-docker-stack` fast-forwarded to match + pushed. (This also merged the still-pending Similar Titles + CW Episodes branch — it is in this branch's ancestry.)
- ⚠ **Deploy (RKM-HP):** `.\\bootstrap.ps1` → eyeball Home hero/CW rail, Movies/TV grids, an item page (movie + series episodes), Watchlist, top-bar ⌘K search. Sandbox gotchas banked in the skill ref (`vite --host 0.0.0.0`, 9p stale-vite restarts, orphan vite squatters on :5173, playwright-core + system Chrome recipe).

## ▶ LATEST SESSION (2026-09-09) — Similar Titles ("Because you watched") + Continue-Watching EPISODES ✅ (branch: `feat/similar-titles-cw-episodes`, 4 commits)
**Executed both READY plans back-to-back (`SIMILAR_TITLES_PLAN.md` + `CONTINUE_WATCHING_EPISODES_PLAN.md`), gates green after EVERY phase. Headless-accepted live against the real bundled Jellyfin 10.11.11; RKM-HP deploy + eyeball remains the acceptance (then merge → main).**
- **Commit `8b43efe` — SIMILAR backend:** additive `GET /api/jellyfin/similar?id=&limit=` (contract **35 → 36 paths**, snapshot + types regenerated, +1 only). `TMDBService.get_similar(tmdb_id, media_type)` — `/movie|tv/{id}/similar`, cached 6h (`similar:{kind}:{id}`), normalised rows `{tmdb_id,title,year,media_type,score,poster,backdrop}`, blank/no-id rows dropped (never fabricated), failure → `[]`. `JellyfinLibraryProvider.item_similar` — light single-item fetch (`Fields=ProviderIds`) → `ProviderIds.Tmdb` → TMDB → display rows `{id,title,year,kind movie|show,score,poster,backdrop}` capped by limit; `None` for missing/not-Movie-Series/no-Tmdb/failure (route 404), `[]` is a real empty answer; `tmdb=` DI seam (lazy TMDBService default). `LibraryService.item_similar` aggregate (first provider answering non-None); ABC default `None`. Route mirrors `jellyfin_detail`: 503 unconfigured / 404 missing id or unresolvable / 200 `{similar:[…]}`. **+12 tests → 304 pytest** · ruff clean.
- **Commit `f69a020` — SIMILAR frontend:** `api.getSimilar` + `SimilarItem/SimilarShape` hand-types; `useSimilar` (5-min stale, retry off — 404s are not errors); pure helpers (unit-tested +7): `similarItemToResult` (row → SuggestResult adapter), `similarRowInLibrary`/`filterLibraryRows` (drop titles already owned; conservative — same-name different-year remakes survive). **`SimilarRow.tsx`** renders under item metadata on movie/tv pages: reuses **SuggestCard** + **SuggestDetailModal** so the row is actionable (Add-to-Watchlist / Download with toasts + busy + in-watchlist patch — no new deps, no new components). **vitest 112/112** · tsc · build ok.
- **Commit `7944a38` — CW-EPISODES backend (Option A):** `continue_watching()` now reads Jellyfin **`/Items/Resume`** FIRST (lists every in-progress item individually — incl. EPISODES; series UserData never rolls up episode positions, which is why the old scan filter could never see them), then merges the old scan filter (pos>0 && not played) as fallback; dedupe by id; played episodes excluded. Episode rows: additive `kind=episode` + `episode` facet `{number,season,series_id,series_name}` + standard play facts (own thumb via id-proxy); movie/series rows gain additive `kind=movie|show`. Endpoint stays free-form → **contract snapshot ZERO diff**. Resume-unavailable degrades cleanly to the old behaviour. **+7 tests → 311 pytest** · ruff clean. **Live probe:** `/api/library/continue-watching` → **12 items (5 movies + 7 in-progress 3BP episodes S1E01–S1E07)** with positions + series context.
- **Commit `47e3a3c` — CW-EPISODES frontend:** `MediaItem` gains optional `kind` + `episode` facet (hand-typed; free-form endpoint). Pure helpers (+4): `isEpisodeItem`, `episodeItemCode`, `seriesTargetForEpisode` (series-page mapping, drops the facet). `MediaCard` renders episode cards: **SxEy badge** (instead of MOVIE/TV), series name under the title, amber resume bar; hover ▶ resumes the EPISODE instantly (id+position already ride `quickPlay`); `ContinueWatchingRow` whole-card click opens the **SERIES** page. **vitest 116/116** · tsc · build ok.
- **Headless acceptance (sandbox static+proxy → real bundled Jellyfin; 0 console errors):** Prisoners item page → "Because you watched Prisoners" + **10 real TMDB cards** (posters, ★ scores, hover Add/Download); 3BP series page → same with TV cards; Home CW row → **12 cards incl. S1E1–S1E7 episode cards**; episode-card click → `/library/item/<series id>` with **Episodes + Season 1 + the similar row** all rendering.
- ⚠ **Deploy (RKM-HP):** `.\\bootstrap.ps1` (api + web both changed) → eyeball: a movie + a series item page show the "Because you watched" row; watch part of a 3BP episode → Home shows it in Continue Watching as an SxEy card → hover ▶ resumes at the right spot, card click opens the series page. Then merge `feat/similar-titles-cw-episodes` → main + push (fast-forward `experiment/bundled-docker-stack`).
- **Sandbox gotchas banked in the skill reference:** don't `source` the repo `.rkm.env` raw (Windows CRLF → trailing `\r` in every key; TMDB_API_KEY ends `%0D` → TMDB 401) — `sed 's/\r$//'` first; the Jellyfin API key is NOT in `.rkm.env` — authenticate to `host.docker.internal:8098`, keep the token in `/tmp/jf_tok`; `process kill` on the wrapper leaves the uvicorn child holding the port — kill via the `/proc` socket scan; orphaned acceptance servers from older sessions sit on `:8000`/`:8124` with stale code/ROOT (`web/dist` 404s) — clear them before booting.

## ▶ LATEST SESSION (2026-09-08) — legacy vanilla app REMOVED (React is the only UI) ✅ (branch: `chore/remove-legacy-app`, from main @ `c43b229`)
**User-approved scope: delete the COMPLETE legacy app; Plex BACKEND support and the frozen `/api` contract stay. Gates green: 292 pytest · ruff · tsc · vitest 105/105 · build · contract zero-diff (no /api change).**
- **Merged the restructure first:** `refactor/production-repo-structure` → `main` (fast-forward, `e71eaf0..c43b229`), `experiment/bundled-docker-stack` fast-forwarded to match; both pushed.
- **Commit `67019bf` — delete the legacy app + serving surface:** `git rm` `frontend/legacy/` (index.html app.js app.css api.js + node harnesses phase11/18/25/26); nginx `/legacy` alias + location blocks removed (default.conf is now React-origin + /api proxy only); compose web mount `./frontend/legacy:/legacy-source:ro` and the `VITE_ENABLE_REACT` build arg removed; React cleanup — deleted `LegacyPlaceholder.tsx` / `PortedPlaceholder.tsx` / `lib/flags.ts` (the flag existed only to keep legacy serving), `AppShell` always renders the shell, dropped the orphaned `/playback` placeholder route, removed the Sidebar "Legacy app (/legacy)" link, ConfigHealthView error copy de-flagged; `frontend/Dockerfile` ARG/ENV removed.
- **Commit `a69831a` — archive rebuild_dashboard:** `git mv backend/scripts/rebuild_dashboard.py → tools/archive/` (its only consumer was the legacy dashboard data file). Dropped the dashboard-rebuild subprocess/import steps from the live ops scripts (add_watchlist_cron, auto_complete, daily_recommendations, enrich_trailers, backfill_tmdb_artwork, fetch_trailers, migrate_json_to_sqlite) and updated docstrings referencing it (services/dashboard.py, api/models.py, watchlist route, test_watchlist_entries → `services/dashboard.to_rich_entry`).
- **Docs (this commit):** README + ARCHITECTURE trees/diagrams/commands updated to the legacy-free layout (frontend is the only UI; no rebuild step; harness command gone); PROGRESS header + this record.
- ⚠ **Deploy (RKM-HP):** `.\\bootstrap.ps1` — the web image no longer builds with the flag and nginx no longer serves `/legacy`; eyeball the dashboard (all views incl. /discover /watchlist /search /suggest + a Play path). Then merge `chore/remove-legacy-app` → main + push (and fast-forward `experiment/bundled-docker-stack`).
- **Note for later:** the Skill reference `jellyfin-web-playback → references/rkm-cinema.md` was updated for the restructure; the legacy-removal notes were folded into PROGRESS + README (skill file refresh optional).

## ▶ LATEST SESSION (2026-09-08) — repo restructure EXECUTED: backend/ + frontend/ monorepo ✅ (plan: `REPO_STRUCTURE_PLAN.md`)
**Executed the production repo structure plan Phases 0–5 on `refactor/production-repo-structure`, gates green after EVERY phase, contract zero-diff throughout. No container/live steps (sandbox has no docker daemon) — RKM-HP deploy + eyeball remains the acceptance.**
- **Phase 0 — baseline + hygiene:** 292 pytest · ruff · tsc · vitest 105/105 · 4 node harnesses · snapshot zero-diff all green pre-move; removed the stray literal `D:\…\data` dir + root `.DS_Store` (gitignored/untracked → no commit).
- **Phase 1 — `backend/`:** `git mv` api services domain core config infrastructure application jobs scripts provisioner requirements.txt ruff.toml Dockerfile tests → `backend/` (pytest now runs `cd backend && python -m pytest tests/`; the 4 legacy node harnesses stayed at root `tests/` temporarily because their `join(__dirname,'..')` loads need the legacy files at repo root until Phase 3). Compose api `build.context: ./backend` (Dockerfile COPYs unchanged), provisioner `./backend/provisioner`; `backend/.dockerignore`; `config/settings.py` gained a repo-root `.env` fallback appended after `/workspace/.env` + `/app/.env`; `scripts/snapshot_openapi.py` output path now repo-root-anchored (runs from any CWD). Commit `8939cb5`.
- **Phase 2 — `frontend/`:** `git mv web frontend` (56 files). `frontend/Dockerfile` COPYs `frontend/…` (build context stays repo root so `nginx/default.conf` stays reachable); compose web `dockerfile: frontend/Dockerfile`; root `.dockerignore` patterns updated; npm ci + typecheck + vitest 105/105 + build green from `frontend/`. Commit `0e60ca5`. ⚠ Sandbox 9p quirk hit here: `git mv web frontend` left a ghost dir the FS refused to delete (`rmdir` ENOTEMPTY, `nlink=1`, invisible children) — resolved via `os.rename` handle cycling; leftover `zz_ghost*` entry suppressed with `.git/info/exclude` (local only), delete from the Windows host if it ever shows.
- **Phase 3 — `frontend/legacy/`:** `git mv` index.html app.js app.css api.js → `frontend/legacy/` + the 4 node harnesses → `frontend/legacy/tests/` (their `..` now resolves beside the legacy files — all 4 PASS). Compose web volume `./frontend/legacy:/legacy-source:ro` (nginx alias unchanged). `scripts/rebuild_dashboard.py` re-anchored (`__file__`-relative backend sys.path; output BASE → `frontend/legacy/`). 292 pytest green. Commit `5c8b85c`.
- **Phase 4 — archive + path hygiene:** root one-off tools (`build_dashboard build_first_watchlist rebuild_verify tvdb_enrich verify_dashboard verify_html verify_trailers check_js`) → `tools/archive/`; stale docs (`RKM_Watchlist_Production_Refactor_Task.md .hermes_report_data_model_tests.md progress_download_selection.md ARCHITECTURE_GUIDE.md`) + old `archive/` (qa scripts → `tools/archive/qa/`) → `docs/archive/`; grep-confirmed nothing imports them. Separately, the 5 live backend ops scripts (auto_complete / daily_recommendations / enrich_trailers / backfill_tmdb_artwork / migrate_json_to_sqlite) were re-anchored from hardcoded `/workspace/projects/rkm-cinema` to `__file__`-relative backend paths (migrate gained the `Path` import it now needs). Commits `517daff` + `228cb29`.
- **Phase 5 — docs/CI/skill:** README (status block, local-dev, stack, **project layout rewritten to the new tree**, tests block), ARCHITECTURE (header, layout diagram, §3 tree, §13/§14 commands), `.github/workflows/ci.yml` (on-disk, gitignored: backend working-directory + frontend + cache-dependency-path), skill `jellyfin-web-playback → references/rkm-cinema.md` all updated to the new layout + this record.
- **Gates (final, from the new homes):** `cd backend && python -m pytest tests/ -q` **292 passed** · ruff (prod packages) clean · `node frontend/legacy/tests/phase*.test.mjs` **4/4 PASS** · `cd frontend && npm run typecheck && npx vitest run && npm run build` **105/105 + build ok** · `python backend/scripts/snapshot_openapi.py` **zero-diff (35 paths)** · `git status` clean.
- ⚠ **Deploy (RKM-HP):** `.\\bootstrap.ps1` — the api image now builds from `./backend` and the web image COPYs `frontend/`; `/legacy` is served from `./frontend/legacy`. Then eyeball: dashboard (React origin), one Play path, and `/legacy/` (legacy app still reachable). After sign-off: merge `refactor/production-repo-structure` → main and push both.
- **Notes for the next session:** pytest/ruff now run from `backend/`; frontend gates from `frontend/`; harnesses from `frontend/legacy/tests/`; contract snapshot from the repo root via `python backend/scripts/snapshot_openapi.py`; `rebuild_dashboard.py` writes the legacy outputs into `frontend/legacy/` (dashboard.html + dashboard-data.json stay gitignored basename patterns).

## ▶ LATEST SESSION (2026-09-08) — player bug FIXED: "small native-style player" for HEVC/AV1 titles ✅
**Root-caused + fixed + live-verified.** The user-reported bug (some newer movies play in a SMALL low-res window with the app's own fullscreen button; older titles fine) was NOT a second/native player element — it is one player, but Jellyfin transcoded those files at **416×234 @ 256 kbps** because our HLS/stream requests omitted `VideoBitRate`.
- **Root cause (live-verified 10.11.11):** Jellyfin sizes the transcode RESOLUTION/quality ladder from **`VideoBitRate`**. `MaxStreamingBitrate` alone is **ignored** (probe: 120 Mbps via MaxStreamingBitrate still returned 416×234; adding `VideoBitRate=120000000` returned 3840×2160). With no `VideoBitRate`, a genuine re-encode (HEVC/AV1/10-bit) falls back to the tiny 256 kbps default. h264 titles were unaffected because codec=h264 on an h264 source = copy (no re-encode), which is why only the later 10-bit files (Prisoners AV1-4K, One Battle After Another HEVC-Main10, Mad Max HEVC-Main10) looked broken. Ladder verified: 8M→1080p, 5M→720p, 120M→source res.
- **Fix (`api/routes/jellyfin_hls.py` + `api/routes/jellyfin_stream.py`):** `mode=transcode` now ALWAYS sends `VideoBitRate` — the quality picker's `max_bitrate` when set, else an unthrottled 120 Mbps cap so a real re-encode keeps the source resolution. transcode_audio (video copy) doesn't need it; remux untouched.
- **Verified:** via the fixed proxy against the real bundled Jellyfin — Prisoners master now `RESOLUTION=3840x2160` (was 416x234), One Battle + Mad Max `1920x1080` (was 416x234); quality ladder 8M→1080p / 5M→720p honoured. Real-Chrome live-origin DOM check confirms the player pipeline is one element, no native controls; the ONLY defect was the tiny transcode resolution. Note on the user's third title, **Nightcrawler**: its CURRENT file is h264/AAC mp4 (added 2026-08-19) and it already plays full-res 1920×800 via remux in the live check — its reported symptom likely came from an earlier HEVC/10-bit copy or file replacement, and the transcode fix covers that case regardless.
- Gates: **292 pytest** (was 291; +1 regression) · ruff clean · contract snapshot **unchanged** (query params already existed — no regen needed) · web untouched (no frontend change; the picker already sends `max_bitrate`).
- ⚠ **Deploy (RKM-HP):** backend change → `.\\bootstrap.ps1` (or `docker compose -p rkm-bundled up -d --build api`), then play Prisoners / One Battle After Another / Mad Max — they should now open full-screen at full quality; Quality picker (1080p/720p) actually caps the transcode now.

## ▶ SESSION WRAP (2026-09-07) — shipped today, concise
Everything merged to **main** (= `experiment/bundled-docker-stack`, fast-forward):
- **Legacy parity** — Discover / Watchlist / Search / Suggest ported from `/legacy/` to the React shell; additive `GET /api/watchlist/entries` (live rich entries); contract 34→35 paths; **291 pytest** · ruff clean · **vitest 105/105** · tsc · build ok. Plan `LEGACY_PARITY_PLAN.md` EXECUTED.
- **Real *arr integration (bundled stack)** — the bundled api now talks to the machine’s already-running **Radarr/Sonarr/Prowlarr/qBittorrent** (URLs + API keys), so Suggest/Watchlist Download works; same for Plex/Emby/Jellyfin/TMDB. Quality-profile IDs wired.
- **Single repo-level `.env`** — `rkm.config.toml` removed; copy `.env.example` → `.env` and paste everything (Jellyfin admin, *arr, Plex/Emby, TMDB, ports, paths, store/jobs); bootstrap/render/docker all read it; one-time auto-migration already copied your existing service keys in.
- **Bugfixes** — Suggest Add save-path (JSON store env now container path `/data/rkm/watchlist.json` + env-independent default), card hover buttons reachable (pointer-events), API errors surface real `detail`, modal Add-button sync + per-action busy states + trailer auto-scroll.
- **Deploy:** `.\bootstrap.ps1` on RKM-HP, then eyeball the four views + downloads.

## ▶ NEXT SESSION (user-reported 2026-09-07) — PLAYER BUG: some movies open a SMALL native-style player inside the app ✅ **FIXED 2026-09-08 — see the LATEST SESSION block above (root cause: missing `VideoBitRate` on transcode → 416×234 encodes; fix deployed in both jellyfin routes).**
**User, RKM-HP, Brave tab:** when opening a movie page and pressing Play, the video runs inside a **small media player at the centre of the screen** — “a small player inside the main player window”, **reduced quality**, and it **has its own native controls including an expand-to-fullscreen button**. Only for the titles added later to the library: **Prisoners, Nightcrawler, One Battle After Another**. Older titles ((500) Days of Summer, 50 First Dates, etc.) play correctly as intended.
- **What this smells like:** a plain native `<video controls>` element rendering at its intrinsic small size instead of our custom full-screen player (no custom chrome, native fullscreen button → the `controls` attribute is ON somewhere for this path, or a second/fallback video element is being created). Reduced quality points at a different stream mode (transcode?) for those files.
- **Leading hypotheses to check first (in order):**
  1. **Codec/container difference** — the 3 new files are likely mkv/HEVC or carry EAC3/TrueHD vs the older mp4/H.264/AAC files. Run `playback-info` (probe harness exists: `scripts/probe_jellyfin_hls.py` / `probe_jellyfin_detail.py`) for Prisoners + Nightcrawler + One Battle vs 50 First Dates and compare container/video/audio codecs and the chosen route (direct/remux/transcode_audio/transcode).
  2. **Duplicate/native video element** — grep `Player.tsx` for any fallback path that sets `controls`, renders a second `<video>`, or attaches hls.js to a video while a raw `<video src>` also plays; check DOM in the repro for 2 video elements.
  3. **Mode/routing edge** — if those files end up on a route (e.g., direct of an HEVC/mkv the browser can’t decode, or HLS fallback after error) where the Player renders the element unstyled/native (no wrapper classes / `w-full h-full object-contain` missing on that branch).
  4. **hls.js native-vs-js engine** — same titles may advertise native HLS on Chromium/Brave while segments fail → hlsEngineFor returns hls.js except Apple mobile; verify engine + master playlist chosen for the 3 titles.
- **Triage recipe (next session):** live uvicorn against bundled Jellyfin → probe the 3 titles’ playback-info + stream/HLS master (compare against 50 First Dates) → headless render the Player for one bad title and capture DOM/video element state + console → fix at the Player/routing layer; gates pytest/vitest/tsc/build; deploy `.\bootstrap.ps1`; user eyeball in Brave.
- Also worth checking while there: these 3 were added to the library later — confirm their Jellyfin scan metadata (container/codec) is what the probe reports (they may have been added as a different library type/path).

## ▶ LATEST SESSION (2026-09-07) — Bugfix follow-up: card action buttons were dead (pointer-events) ✅
**After redeploy the overlay Add worked but the CARD Add still did nothing (opened the detail) and Download returned `{"detail":"movie acquisition is not configured"}`.**
- **Root cause (card buttons):** the hover action buttons live inside the poster wrapper, which is `pointer-events-none` — clicks fell through to the card (open-detail), so Add/Download/Trailer could never fire. Added `pointer-events-auto` to the action containers in **`WatchCard`**, **`SuggestCard`** and (latent, same pattern) **`MediaCard`**. Combined with the earlier container-click guard, action clicks now hit the button and never open the detail; poster/whole-card clicks still open it.
- **Download 503:** `{"detail":"movie acquisition is not configured"}` is the backend’s correct answer on the **bundled stack default profile** — it has no Radarr/Sonarr (those are the opt-in `fullstack` profile). Not a UI bug. The client now surfaces the real `detail` in errors (FastAPI `detail`/`{message}` parsed into `ApiError.message`) and toasts a clear warn for 503/502: “enable Radarr/Sonarr (bundled fullstack profile) or use the prod stack”. On the prod stack (`run-rkm-cinema.ps1`) Radarr/Sonarr are configured and the same request path is unit-covered 200.
- Gates: vitest **105/105** · tsc clean · `VITE_ENABLE_REACT=1` build ok (no backend change this round).
- ⚠ **Deploy (RKM-HP):** web-only change → `docker compose -p rkm-bundled up -d --build web` (or `.\bootstrap.ps1`), hard-refresh, then: Suggest card **Add to Watchlist** adds (no overlay); **Download** on the bundled stack shows the friendly warn (needs the `fullstack` profile / prod stack to actually grab).

## ▶ LATEST SESSION (2026-09-07) — Suggest UI fixes (modal button sync, per-action busy, trailer scroll) ✅
**User-reported on Suggest/Watchlist:** (1) modal Add succeeded but its button flipped back to “Add to Watchlist” until the tab was re-opened; (2) clicking Download also flipped the Add button to “Adding…”; (3) opening a trailer in the detail popup left it below the fold (had to scroll).
- **(1)**: the open detail modal snapshots its `SuggestResult` at open time; `patchItem` only updated the grid array. `patchItem` now also patches `detail` when it matches, so the modal button flips to “✓ Added to Watchlist” immediately (and reverts on failure like before).
- **(2)**: one shared `busyId` drove both buttons. Split into `busyAdd`/`busyDownload`; card + modal each show “Adding…” only for Add and “Starting download…” only for Download.
- **(3)**: `WatchlistDetail` scrolls the trailer embed into view when it opens (ref + `scrollIntoView`, 120 ms after open so the modal settles).
- Gates: tsc clean · vitest **105/105** · `VITE_ENABLE_REACT=1` build ok (web-only).
- ⚠ **Deploy (RKM-HP):** `docker compose -p rkm-bundled up -d --build web`, hard-refresh.

## ▶ LATEST SESSION (2026-09-07) — Config rework: ONE repo-level `.env`, no rkm.config.toml ✅
**User asked for a single env file: paste everything for the full stack (Jellyfin/Radarr/Sonarr/Plex/Emby/TMDB/ports/paths) into one `.env`, and script + docker read it and run.**
- **New single source = repo-level `.env`** (`D:\hermes_agent\hermes-workspace\projects\rkm-cinema\.env`). `.env.example` (committed, fully commented) documents every variable: `RKM_MEDIA_PATH`/ports/TZ/PUID/PGID, `MEDIA_SERVER` (jellyfin|plex|emby), `RKM_JELLYFIN_ADMIN_USER/PASSWORD/RKM_JELLYFIN_BROWSER`, `PLEX_URL/TOKEN`, `EMBY_URL/API_KEY`, `TMDB_API_KEY`, `RADARR_URL/API_KEY`, `SONARR_URL/API_KEY`, quality-profile ids, `PROWLARR_*`, `QBITTORRENT_URL`, `WATCHLIST_STORE/DB_PATH`, `WATCHLIST_SCHEDULER`, `AUTO_ADD_ENABLED/HOUR`, `RECONCILE_INTERVAL_MIN`.
- **`rkm.config.toml` + example deleted.** `render_config.py` rewritten: reads ONLY the repo `.env` (no ancestor/workspace .env), seeds safe defaults into `.env` when missing, auto-generates `RKM_JELLYFIN_ADMIN_PASSWORD` and persists it back into `.env`, fails with a clear list on missing required keys (e.g. `TMDB_API_KEY`), creates the storage tree, and writes the derived `.rkm.env` (api env_file: container-internal addresses resolved, e.g. Jellyfin `http://jellyfin:8096`, watchlist `/data/rkm/watchlist.json`) + `.rkm_state.json`. `bootstrap.ps1`/`.sh`: no more toml copy — if `.env` is missing it copies `.env.example` and tells the user to fill it. `docker compose` substitutes ports/paths/provisioner admin from the same `.env`. Verified in a temp sandbox copy: defaults filled, password generated + saved, `.rkm.env` correct, missing-TMDB error path exit 2.
- Note: the API app itself (prod paths, `config/settings.py`) still accepts the classic env var names; the repo `.env`/`.rkm.env` now carry them for the bundled stack.

## ▶ LATEST SESSION (2026-09-07) — Bugfix: Suggest Add on RKM-HP (bundled) ✅
**User-reported after deploying parity:** (1) clicking Add on a Suggest result card opened the detail overlay instead of adding; (2) adding from the overlay returned `{ok:false, message:"Failed to add: Save failed: [Errno 2] No such file or directory: '/workspace/media/watchlist.json.tmp'"}`.
- **Root cause (2):** `render_config.py` wrote the bundled api env’s `WATCHLIST_DB_PATH` as a **host-side absolute path** (`./data` resolved on Windows). Inside the api container that path is meaningless, so `JsonWatchlistRepository` fell back to its blanket default `/workspace/media/watchlist.json` — a dir the bundled stack does NOT mount → atomic `.tmp` save ENOENT. Fix: **`WATCHLIST_DB_PATH=/data/rkm/watchlist.json`** (container path on the media bind; `/data/rkm` is created host-side by `ensure_storage`), plus an **env-independent default-path fallback** (`_pick_json_default_path`: existing file → prod `/workspace/media` file → bundled `/data/rkm` dir → legacy default) so the store never lands in an unmounted dir even when env is missing. +1 regression test → **291 pytest** · ruff (CI scope) clean.
- **Fix (1):** `SuggestCard`/`WatchCard` dropped the transparent full-card `<button>` overlay for a **container onClick/keyboard pattern** that ignores clicks originating in `button, a` — an Add/Download/Trailer click structurally cannot open the detail modal anymore (poster/whole-card clicks still do). vitest **105/105** · tsc clean · `VITE_ENABLE_REACT=1` build ok.
- ⚠ **Deploy (RKM-HP):** re-run `.\bootstrap.ps1` (api env re-rendered + web rebuilt), then in Suggest: search → **Add to Watchlist** on a card adds without opening the overlay; overlay Add/Download succeeds; card shows “On Watchlist” / “Added”; entry appears in Watchlist grid.

## ▶ LATEST SESSION (2026-09-07) — Legacy parity: Discover / Watchlist / Search / Suggest → React ✅ (plan: `LEGACY_PARITY_PLAN.md`)
**The last four legacy-only top-level views now render in the React shell from LIVE /api data — no `dashboard-data.json` dependency. Backend `2e18f06` + the frontend commit below; the sidebar’s More group is fully ported (legacy stays recoverable at `/legacy/` until sign-off).**
- **Phase 0 backend (`2e18f06`):** shared mapper **`services/dashboard.py:to_rich_entry`** (GENRE_HINTS + trailer-id scrub + score/genre/overview fallbacks moved verbatim out of `rebuild_dashboard.normalize_entry`, which now delegates — one mapper for the API and the static rebuild) + additive **`GET /api/watchlist/entries`**: live rich entries (posters/backdrops/IMDb·RT·TMDB scores/synopsis/cast/director/trailer) from the authoritative SQLite store, reusing `WatchlistEntryResponse`. Contract **34 → 35 paths** (additive) · `types.ts` regenerated · +3 tests → **290 pytest** · ruff clean. **Live probes (sandbox uvicorn → real store):** `/api/watchlist/entries` → **471 rich entries** (Arrival: poster+backdrop+imdb 7.9+tmdbScore 7.6+genres; TV sample The Bear type=tv); `/api/watchlist` resources 200 → 471 (Arrival `can_watch`, watch links **plex+emby**); `POST /api/suggest` live TMDB 200.
- **Phases 1–2 frontend (this commit):** shared `features/watchlist` slice + four thin views:
  - **client.ts**: `getWatchlistEntries`/`getWatchlistResources`/`search`/`suggest`/`suggestDetail`/`suggestAdd`/`requestMedia`/`runAddWatchlistJob` + rich-entry/resource/search/suggest types; `useWatchlist()` combines entries + §18 resources into per-entry `ResolvedState` (legacy DATA+RES+`st()`).
  - **`lib.ts` pure parity helpers (+38 unit tests):** `mediaIdOf`, `resolveState`, `cardPrimaryAction`, `jellyfinMarker`, `seededShuffle`/`daySeed`/`pickHero`/`buildWatchlistRows`, `filterWatchlist` (chips + 4 sorts), `suggestHistoryPush/Label`, `persistedToEntry`/`suggestItemToEntry` — mirroring legacy exactly.
  - **Views**: **Discover** (hero auto/newest/random from `/api/config` heroMode + curated rows + Continue Watching / Recently Added library rows + My Library strip) · **Watchlist** (All/Movies/TV Shows/Downloaded/Not Downloaded chips + Recently Added/Rating/Release/Title sort + Load-more, state-aware `WatchCard`s) · **Search** (debounced page over `/api/search`, Watchlist + Live TMDB groups, ArrowUp/Down/Enter/Escape, row → detail modal + Download) · **Suggest** (type/genre/year/rating/sort/count filters, Recent-history chips in localStorage, results grid with On-Watchlist/In-Library badges, Add = upsert full card + invalidate resources, Download = add + `POST /api/media/{id}/request`, card-click → on-demand detail modal with IMDb rating). Shared `WatchCard`/`WatchlistDetail`/`CardRow`/`Toaster`; Play in RKM / Episodes navigate to the item’s routed page (`/library/item/:id` — the Plex model); Watch links open Plex/Emby/Jellyfin externally.
- **Gates:** vitest **105/105** (was 67; +38) · `tsc --noEmit` clean · `VITE_ENABLE_REACT=1` vite build ok (131 modules) · full pytest **290** · ruff clean · contract snapshot +1 path (additive). **SPA fallback smoke** (nginx-equivalent static + `/api` proxy): `/discover` `/watchlist` `/search` `/suggest` `/library/item/:id` all serve the shell, `/api/watchlist/entries` proxied 200. (No in-sandbox browser this session — the RKM-HP eyeball is the acceptance, as before.)
- ⚠ **Deploy (RKM-HP):** backend + frontend both changed → `.\bootstrap.ps1` (or `docker compose -p rkm-bundled up -d --build api web`), then eyeball the four views: Discover hero/rows, Watchlist chips + sort + Download → Requested, Search groups + detail, Suggest Search → Add/Download (bundled Jellyfin stack: the 2 movies with Play-in-RKM; prod store: 471 titles with Plex/Emby watch links).
- **Queued next (user-approved order):** roadmap item 4 v2 — "Because you watched"/similar (server-side TMDB enrichment; own plan doc when started). Legacy `app.js` retirement waits for parity sign-off.

## ▶ LATEST SESSION (2026-09-07) — Library & discovery Phases 0–1 DONE ✅ (roadmap item 4; plan: `LIBRARY_DISCOVERY_PLAN.md`)
**Approved as "next" (with legacy parity queued after). The Movies / TV Shows folders are now browsable: instant client-side search, genre chips, and truthful sort (Recently added / A–Z / Unwatched first). Backend + frontend; /api contract unchanged (additive dict keys on a free-form endpoint).**
- **Phase 0 backend (`05f97d1`):** `_get_items` now requests `Genres,DateCreated`; `JellyfinItem` + `_parse_item` store them; `_item_public` emits **`genres[]`** and **`added` (DateCreated ISO | None)** on every library item (all_items / continue_watching / recently_watched / recently_added share the serialiser). No route/schema change (`/api/library/items` is free-form — snapshot regen produced **zero diff**). +2 regression tests (parse captures both; absent → `[]`/None, never fabricated) → **287 pytest** · ruff clean.
- **Phase 1 frontend (`cfb29fb`):** pure helpers in `features/library/lib.ts` — `addedTime` (normalises Jellyfin's 7-digit fractional ISO so sort can't break on any engine; null when unknown — never a guess), `libraryGenres` (unique chip list), `filterLibraryItems` (case-insensitive title `q` + genre membership + `recent`/`title`/`unwatched` sorts; unknown dates last, stable). **`LibraryFolderView` toolbar**: search box, genre chip row, sort `<select>`, live "N of M titles" count, no-matches state with Clear. `MediaItem` gains optional `genres`/`added`. No new deps; filtering runs over the shared `useLibraryItems` cache — **zero fetches**. vitest **67/67** (+11) · tsc clean · build ok.
- **Deploy (RKM-HP):** backend + frontend → `.\\bootstrap.ps1` (or `docker compose -p rkm-bundled up -d --build api web`), then eyeball: search narrows instantly, chips come from that folder's own titles, Recently added orders by real Jellyfin `DateCreated`, movie card never in Shows.
- **Queued next (user-approved order):** **legacy parity** — port Discover/Watchlist/Search/Suggest from `/legacy/` to React (own plan doc when started; then roadmap item 4 v2 "Because you watched"/similar which needs server-side TMDB enrichment).

## ▶ LATEST SESSION (2026-09-07) — Plex-style views & navigation Phases 0–2 DONE ✅ (frontend-only; plan: `PLEX_VIEWS_PLAN.md`)
**Executed the parked Plex-navigation plan: the preplay OVERLAY is gone from the library flow — every title opens in its own URL-backed page (Back works, deep-linkable, refresh keeps you there) and the left sidebar browses Movies / TV Shows folders. Frontend-only: no backend/contract change, no new npm deps.**
- **Phase 0 — routes + views split:** `/library` → `/library/home` (redirect keeps old links working). New **`LibraryLayout`** owns the full-screen player + card handlers and shares them with every route via outlet context (so the player overlays Home, folders AND the item page — Plex layers it the same). **`LibraryHomeView`** = Continue Watching + Recently Watched + **Recently Added** (from the existing frozen `GET /api/library` — client-only `getLibraryRecent`, zero contract change). **`LibraryFolderView`** renders `/library/movies` and `/library/shows` by filtering the shared `useLibraryItems` cache client-side (`libraryItemsByType`, new pure helper). Sidebar gains a **Library group — Home · Movies · TV Shows** — with per-route active states (Settings + More groups unchanged).
- **Phase 1 — dedicated item page:** `ItemDetail` overlay → **`ItemDetailContent`**, an in-flow card driven by the URL id (the list item only supplies type/fallbacks/Jellyfin link, so a hard-refreshed deep link renders); **`ItemDetailPage`** wrapper adds **Back button + Esc** — Esc closes the full-screen player FIRST (gated on live player state from the layout) then leaves the page — plus scroll-to-top per title and a deep-link fallback to `/library/home`. `LibraryView.tsx` **deleted**; card clicks **navigate** (hover ▶ for movies still plays instantly; series ▶ opens their page).
- **Gates:** vitest **56/56** (+4 folder-split helpers) · `tsc --noEmit` clean · `vite build` 103 modules · **backend untouched** (no pytest run needed; `/api` contract + `types.ts` unchanged).
- **Deploy (RKM-HP):** frontend-only → `docker compose -p rkm-bundled up -d --build web` (or `.\\bootstrap.ps1`), hard-refresh, then: click a card → its own page with URL/Back; browse **Movies** and **TV Shows** folders (movie card never in Shows); Resume/Play from the page starts the HLS player at the right position; Esc closes the player first, then leaves the page; mark-watched still moves badges everywhere (Home rows, folder grids, item page). Live-data headless acceptance was **deferred by the user** this session (the bundled Jellyfin admin password in `rkm.config.toml` is stale → 401 against `:8098`) — the RKM-HP eyeball is the acceptance. Parked next to it (unchanged): roadmap items 4–5, legacy parity ports, Bazarr subs.

## ▶ LATEST SESSION (2026-09-06) — user confirmed on RKM-HP + Plex-style views direction PARKED ✅ (plan: `PLEX_VIEWS_PLAN.md`)
**User deployed `.\bootstrap.ps1`, confirmed the preplay overlay works ("yes it works"), then asked for the Plex navigation model as a future change.** Feedback: a title should open in **its own dedicated view/page** (URL-backed, Back works, deep-linkable) rather than an overlay, and the **left sidebar should browse Movies / TV Shows folders** like Plex. That is now a full plan, **PARKED for a future session** (`PLEX_VIEWS_PLAN.md`): Phases 0–3 — `/library/home|movies|shows` + `/library/item/:id` routes, sidebar library group, `ItemDetail` overlay → routed `ItemDetailPage` (Back/Esc/scroll-top/player-on-top), card click navigates; expected to need **no backend/contract change** (client-side `isSeries` filter of the cached items) and **no new npm deps**. Everything else on the roadmap is parked/unchanged (list in the block above). No code shipped this session — this is the plan + tracking record only (commit below).

## ▶ LATEST SESSION (2026-09-06) — Plex-style UI revamp Phases 1–3 DONE ✅ (backend + frontend, headless-accepted; plan: `PLEX_UI_PLAN.md`)
**Click any card → a Plex-style preplay overlay** (backdrop hero, poster, synopsis, ★ rating, genres, studio, cast headshots, big Resume/Play). One additive endpoint + a detail component + a card revamp; no new npm deps.
- **Phase 1 backend (`4831da9`):** `JellyfinLibraryProvider.item_detail(id)` normalises the single-item fetch (`/Users/{uid}/Items/{id}?Fields=Overview,Genres,People,CommunityRating,…` — live-verified 10.11.11) into `{type,name,year,runtime,overview,genres,community_rating,official_rating,studios,people{actors|directors|writers(id/name/role/has_image)},has_backdrop,primary_aspect,play{played,resume_ticks,resume,play_count}}`; Episode items carry series context. Additive `GET /api/jellyfin/detail?id=` (via `LibraryService.item_detail` aggregate; 404 soft-miss, 503 unconfigured) + `GET /api/jellyfin/person?id=` headshot proxy — person images sit at the same `/Items/{id}/Images/Primary` shape (HTTP 200 image/jpeg verified for imaged people; 404 for headshot-less → UI uses initials, and `has_image` skips doomed requests). Contract 32 → **34 paths**; `types.ts` regen. Probe harness `scripts/probe_jellyfin_detail.py` (redacted). **285 pytest** (+11) · ruff clean · vitest 40/40.
- **Phase 2/3 frontend (`f2dc060`):** whole-card click → **`ItemDetail.tsx`** preplay overlay (fetched ONLY on open, cached per item, 5 min staleTime); **`MediaCard` revamp** — hover ▶ (movie plays / series opens episodes), watched toggle + Jellyfin link on hover, ✓ badge + amber resume bar kept, metadata-clean footer; series detail auto-continues via **`nextPlayableEpisode`** (in-progress → first unwatched) and renders season-grouped episode rows with per-episode resume % + Play/Resume/Replay; **`EpisodePicker.tsx` deleted** (superseded — the detail owns episodes now). Pure helpers unit-tested (`fmtRuntime`/`ratingText`/detail-resume labels/person URL/continue-episode). **vitest 52/52** (+12) · tsc clean · `VITE_ENABLE_REACT=1` build ok.
- **Headless acceptance PASS** (built dist served like nginx → real bundled Jellyfin): movie detail Resume **(51%)** + ★7.3/10 + AU-M + synopsis + cast roles + initials fallback (those actors have no headshot in this library); series detail ★7.5/10 AU-MA 15+ Netflix + **Resume S1E1** + all **8 real episodes** w/ per-episode resume (16/62/43/44/12/6%) + 8 person-proxy headshots; Esc + ✕ close; **0 console errors**.
- ⚠ **Backend + frontend change → `.\\bootstrap.ps1` deploy on RKM-HP** (sandbox has no Docker daemon); then click cards → detail and eyeball it (DEPLOY PENDING block above has the check list).
- Deferred (kept light per plan): preplay footer media-facts line (needs a playback-info fetch per open; low value vs weight), trailers/more-like-this (server-side TMDB cost).

## ▶ LATEST SESSION (2026-09-06) — Phase 4: cutover — React served as origin, legacy recoverable at /legacy/ ✅ + live UI test

**Your one command now serves the React shell.** `bootstrap.ps1` unchanged — `docker compose up -d --build` builds the new multi-stage `web` image.

- **`web/Dockerfile`** — node:20-alpine build stage (`VITE_ENABLE_REACT=1`) → nginx serving `web/dist`; **no Node needed on the host**.
- **`nginx/default.conf`** — React SPA at `/` (try_files → `index.html`); `/api` proxy unchanged; repo root mounted at `/legacy-source` served under **`/legacy/`** so the old app + live `dashboard-data.json` stay reachable (discover/watchlist/search/suggest are there until ported).
- **`docker-compose.yml`** — `web` builds from `web/Dockerfile` (`rkm-bundled-web`), mounts `./:/legacy-source:ro`. `bootstrap.ps1`'s `up -d --build` picks it up automatically.
- **`.dockerignore`** — keeps `node_modules`/`web/dist`/pycache out of the build context.
- **Sidebar** — added a **Legacy app (/legacy)** link so the old UI is one click away.
- **Live UI validation (sandbox):** started the FastAPI backend against the **bundled Jellyfin** (freshly-authenticated admin token), served the **built `web/dist`** exactly as nginx would (static + `/api` proxy), and rendered it in headless Chromium: **Full Library + Continue Watching render, 5 cards, 5 posters, real titles/percentages/play-counts, `/legacy` link, 0 console errors.** Provably the same artifact the container serves.
- **⚠ Docker/nginx runtime not executed here** (daemon unreachable in sandbox) — the container config is authored; it was verified by the equivalent static+proxy server instead. Deploy step on RKM-HP: `.\bootstrap.ps1` (or `docker compose -p rkm-bundled up -d --build web`).

**To run it (RKM-HP):**
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\bootstrap.ps1
# React UI:  http://localhost:8124  |  Legacy:  http://localhost:8124/legacy/
```
Legacy `app.js`/`index.html` are **kept** (not retired) — full retirement waits for discover/watchlist/search/suggest parity (Phase 3 remainder).

### Known open
- ~~Thumb leak~~ ✅ FIXED (commit below) — no open thumb issue.
- ~~Seek-bar bug (UI moves, playback doesn't)~~ ✅ **FIXED + USER-CONFIRMED on RKM-HP** — the Plex-style HLS/MSE player (below) resolved it.
- ~~Subtitles: selectable but not applying~~ ✅ **FIXED** (commit `82cb5f7`) — VTT URL shape 404'd on Jellyfin 10.11 (`…/Subtitles/{n}/0/Stream.vtt` is the live-verified form) + cold-start timeout 12→45 s. **Redeploy `.\\bootstrap.ps1` to go live.**
- ~~Subtitle track at index 0 unselectable (50 First Dates external SUBRIP)~~ ✅ **FIXED** (commit `16c104e`) — Subs "Off" was value 0, colliding with track 0; Off is now `""`. Note: (500) Days genuinely has 0 subtitle streams in the file.
- ▶ **NEXT (approved): Plex-style UI revamp — DONE Phases 1–3 (commits `4831da9` + `f2dc060`), headless-accepted.** ⚠ **Deploy `.\\bootstrap.ps1` on RKM-HP**, then click a card → detail overlay and confirm metadata/Play/Resume/episodes feel right (see the LATEST SESSION record below; backend + frontend both changed → rebuild required). Parked: Bazarr subtitles-for-missing-subs (user: "lets park it for later").

## ▶ DONE + USER-CONFIRMED on RKM-HP — Plex-style UI revamp (backend `4831da9` + frontend `f2dc060`)
User deployed `.\bootstrap.ps1` and confirmed the preplay overlay works ("yes it works"), then gave direction for later: **wants Plex-style navigation — each title opening in its own dedicated view/page (not an overlay) + Movies / TV Shows folders in the left sidebar.** That direction is captured in a plan and **PARKED for a future session**: `PLEX_VIEWS_PLAN.md` (Phases 0–3; expected to need no backend/contract change and no new npm deps).
- ▶ **Parked (future): Plex-style views & navigation** — dedicated item pages + sidebar Movies/TV Shows folders. Plan: `PLEX_VIEWS_PLAN.md`.
- ▶ **Parked (future): Bazarr auto-subtitles** for files with no subs (needs OpenSubtitles account; user deferred).
- ▶ **Open roadmap (unchanged):** item 4 — library & discovery (in-library search, filters/sort, "Because you watched"); item 5 — transcode/playback robustness; React-parity ports for discover/watchlist/search/suggest (still `/legacy/`).

## ▶ LATEST SESSION (2026-09-06) — subtitle index-0 fix + user Q&A (audio transient; movie subs explained) ✅
**Follow-up after user confirmation.** (1) Audio on 3BP episodes: sandbox measured real audio energy on the `Transcode (audio)` HLS stream (RMS 617–1596, muted=false, vol=1) and the user re-tested: **sound works in Original quality too** — the earlier silence was a transient cold-start glitch, not a routing bug. (2) Movie subtitles: **(500) Days of Summer has ZERO subtitle tracks in the file** (`subs=[]` live) — nothing to select; external `.srt` beside the media would appear. **50 First Dates subtitle is index 0** (`Undefined - SUBRIP - External`) and the player's Subs dropdown used 0 as "Off" → the track was unselectable. Fixed: Off is now an empty-string option, track 0 selectable (committed `16c104e`); verified live (dialogue cues render).
- vitest 40/40 · tsc clean · build ok (frontend-only change).
## ▶ LATEST SESSION (2026-09-06) — subtitles FIXED: VTT URL shape + cold-start timeout ✅ (user-confirmed seek fix, follow-up)
**User reported subtitles still broken after the HLS deploy ("can select the subtitle but it's not being applied"). Root-caused live: the subtitle proxy fetched `/Videos/{id}/{src}/Subtitles/{index}/Stream?format=vtt` — which 404s on Jellyfin 10.11.11. The live-verified working shape is `/Videos/{id}/{src}/Subtitles/{index}/0/Stream.vtt` (extra `/0/` path segment; format as file extension).** Also raised the upstream timeout 12 s → 45 s (Jellyfin converts embedded tracks to VTT on first request — cold conversions took >12 s and 502'd; warm ≈0.05 s).

- **Verified end-to-end in the real UI** (headless Chromium → bundled Jellyfin): select Subtitle 3 (English SDH) → HTTP 200 → overlay renders real dialogue cues at the right timeline position ("Einstein went to the American Imperialists and helped them build the atomic bomb!"). Regression test pins the new URL shape.
- **274 pytest** · ruff clean · vitest 40/40 · tsc clean (frontend untouched).
- Committed `82cb5f7`; pushed to GitHub (below, after commit).
- ⚠ **Backend change → redeploy needed**: `.\\bootstrap.ps1` on RKM-HP, then pick a subtitle mid-play and confirm text overlays appear.

## ▶ LATEST SESSION (2026-09-06) — HLS player: **USER-CONFIRMED FIXED on RKM-HP** ✅ plan COMPLETE (plan: `HLS_PLAYER_PLAN.md`)
**User deployed `.\\bootstrap.ps1` on RKM-HP and confirmed: "YES THE PROGRESS BAR BUG IS FIXED NOW".** The Plex-style HLS/MSE player (Phases 0–3, commits `0b330aa`→`714aaf7`) is fully live: every non-direct title now plays through same-origin HLS (hls.js on Chrome/Edge/Firefox, native on Apple mobile); seeking asks the server for the segment at the clicked time, so the silent no-op that plagued progressive restart-seek is structurally gone. No open player issues.

## ▶ NEXT SESSION — (open) HLS player: none — complete. Optional follow-ups: ABR ladder (out of scope v1), Safari/iOS native-HLS device check, revisit roadmap items 4/5.

## ▶ LATEST SESSION (2026-09-06) — HLS player Phase 2: hls.js engine in Player + Phase 3 headless acceptance PASS ✅ + latent mark-unwatched fix (plan: `HLS_PLAYER_PLAN.md`)
**The Plex-style player is built and the original bug is structurally gone.** `npm i hls.js`; Player branches direct (unchanged native path) vs **HLS (hls.js on Chrome/Firefox/Edge; native on Apple mobile)**; the offset/restart-seek machinery (`baseRef`/`startAt`/`start_time_ticks`/transition-restart) is **deleted** — position = plain `video.currentTime`, seek = plain `currentTime` set, so hls.js asks the server for the segment at the clicked time (a silent no-op seek is impossible). Subs overlay aligns trivially. Audio-aware HLS ladder (`transcode_audio → transcode`); mode chip stays.

- **lib.ts** (+4 helpers, unit-tested): `usesHls`, `HLS_LADDER`, `nextHlsMode`, `hlsEngineFor`, `hlsModeLabel`; **client.ts** `hlsMasterUrl`.
- **Harness found two real bugs, both fixed:** (1) recent desktop Chromium advertises native HLS (`canPlayType` "maybe") but its TS demuxer fails on Jellyfin segments while hls.js transmuxes cleanly → `hlsEngineFor` now returns native ONLY on Apple-mobile UAs; (2) a leftover `v.removeAttribute("src")` after `hls.attachMedia` killed the MSE pipeline (no segments fetched) — removed.
- **Verification:** vitest **40/40** (+4) · tsc clean · vite build ok · pytest **274** + ruff clean (backend untouched this phase). **Headless acceptance on real bundled Jellyfin 10.11.11:** real 3BP episode via hls.js (mode=transcode_audio copy+aac — decodes, currentTime advances, sequential .ts fetches through the proxy); seek-bar click **10:05 → currentTime 605 (aria 605) PASS**, **30:00 → 1800 → continued 1804 PASS**, **40:00 → 2400 → continued 2404 PASS**. Harness-mutated library state restored afterwards.
- **Latent bug fixed live:** mark-unwatched POSTed `UnplayedItems/{id}` which 404s on Jellyfin 10.11 — now `DELETE PlayedItems/{id}` (both live-verified); regression test updated to pin the route.
- Committed `7ea25ff`; pushed to GitHub (below, after commit).

## ▶ NEXT SESSION — HLS player: user live check on RKM-HP (plan §8)
**Phases 0–2 DONE + headless Phase 3 acceptance PASSED.** Remaining: deploy + real-device check.
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\bootstrap.ps1
# or web image only after frontend-only changes:
docker compose -p rkm-bundled up -d --build web
```
Then on RKM-HP: play a 3 Body Problem episode and the 2 movies — click the seek bar mid-play and confirm the video genuinely jumps (the original bug). If anything smells stale, compare the bundle filename in the network tab vs `web/dist`.

## ▶ LATEST SESSION (2026-09-06) — HLS player Phase 1: backend same-origin HLS proxy ✅ live-verified (plan: `HLS_PLAYER_PLAN.md`)
**Executed Phase 1 of the HLS/MSE plan. The progressive/restart-seek transport now has its replacement backend: a same-origin HLS proxy the browser hands to hls.js/native HLS. Seek-by-segment is now structurally possible — clicking a position asks the server for the segment at that time.**

- **`api/routes/jellyfin_hls.py`** (new, registered in `api/main.py`) — `GET /api/jellyfin/hls/{item_id}/master.m3u8` takes the stream-route vocabulary (`mode=remux|transcode_audio|transcode` + `audio_stream_index`/`max_bitrate`, legacy `transcode_audio=true`, `media_source_id` default = item id) and maps to the Jellyfin codec pair Phase 0 proved correct: remux→copy-copy, transcode_audio→**copy+aac** (EAC3 etc.), transcode→h264+aac. Default (no mode) = transcode; `direct` → 400 (not an HLS mode).
- **Playlist rewriting** — Jellyfin embeds `api_key` in EVERY URI line (master, media, segments; Phase-0 verified). The proxy strips it from every body and leaves URIs relative, so hls.js resolves them against the same-origin master URL and the passthrough route catches them. **No secret ever reaches the browser.**
- **Passthrough** `GET /api/jellyfin/hls/{item_id}/{rest}` — re-injects the server token server-side, drops any client-supplied `api_key` (defence in depth), forwards the query verbatim (MediaSourceId + codec params + `runtimeTicks`/segment ticks), streams `.ts` as `video/mp2t` with Range passthrough (206 verified).
- **Contract 30 → 32 paths** (additive) — snapshot + `types.ts` regenerated (141 lines added, frontend untouched).
- **Tests +10** — master URL mapping per mode (incl. legacy flag + default-transcode), api_key stripped from rewritten bodies, passthrough re-injection + client-key drop, segment Range 206 + MIME, media-playlist rewrite preserves runtimeTicks, 400 unknown/direct, 503 unconfigured. **274 pytest** · production ruff clean.
- **Live-verified end-to-end (sandbox uvicorn → real bundled Jellyfin 10.11.11):** `master.m3u8?mode=transcode_audio` → CODECS `avc1.4D4028,mp4a.40.2` (browser-safe) → media playlist (442-seg VOD) → first segment HTTP 200 `video/mp2t` 4,829,156 bytes (file(1): "MPEG transport stream") → Range request 206 + Content-Range. **Zero api_key leaks in any body** (grep-verified).
- **Frontend gates**: vitest 36/36 · `tsc` clean · `vite build` ok (types additive).
- Committed `2b0fdfc`; pushed to GitHub (below, after commit).

## ▶ NEXT SESSION — HLS player Phase 2: frontend hls.js engine (plan §5, §3b/§3c)
**Phases 0–1 DONE.** `npm i hls.js` in `web/`, then:
1. `lib.ts`: extend routing — `usesHls(mode)`, HLS capability detection (native Safari vs hls.js), master-URL builder (`/api/jellyfin/hls/{id}/master.m3u8?mode=…&audio_stream_index=…&max_bitrate=…`). Pure + unit-tested.
2. `Player.tsx`: branch playback engine on mode — direct → existing `<video>` (unchanged); hls → `new Hls({ startPosition: resume })`, attach video, `Hls.Events.ERROR` → escalate the **audio-aware ladder** (§3b/§3c: transcode_audio → transcode etc.), destroy on unmount/switch; Safari native (`video.src = masterUrl`).
3. **Delete** the offset/restart machinery (`baseRef`/`startAt`/`pendingSeekRef`, transition-restart, scrub-commit special-casing stays only for direct) — HLS position = plain `video.currentTime`; subs overlay trivially aligned; chip stays.
4. Phase 3 harness verify (click 10:05 → currentTime ≈ 605 s) + user live test on RKM-HP (deploy: `.\\bootstrap.ps1`).

## ▶ LATEST SESSION (2026-09-06) — HLS player Phase 0: live probes + durable harness ✅ (plan: `HLS_PLAYER_PLAN.md`)
**Executed the plan's Phase 0 ("verify before building") against the real bundled Jellyfin (10.11.11) — one probe episode (3 Body Problem S1E4 'Our Lord', the actual reported title) + all HLS output shapes captured. No player code changed.**

- **Episode facts** — container **mkv** · video h264 Main 1080p 8-bit (~5.4 Mbps) · audio[1] **EAC3 5.1+Atmos** (768 kbps). So `pickStreamMode` sends every episode down the `transcode_audio` chunked-progressive path today — the exact path whose restart-seek is the bug. HLS must carry every 3BP episode (confirmed).
- **HLS shapes (all MIME `application/vnd.apple.mpegurl`)** — master is a 3-line single-variant playlist (`#EXT-X-STREAM-INF` + one **relative** `main.m3u8?…` URI; no ABR ladder even with `MaxStreamingBitrate`); media playlist is full VOD (442 × 6.006 s segments, `#EXT-X-ENDLIST`); segment URIs `hls1/main/N.ts?…` carry `api_key` + `MediaSourceId` + codec params + `runtimeTicks` + `actualSegmentLengthTicks` (relative too); segments are `video/mp2t` and **Range-capable upstream** (206). **`api_key` is embedded in EVERY playlist URI** → the Phase-1 proxy must strip it (server-side token only).
- **Critical routing discovery** — `VideoCodec=copy&AudioCodec=copy` (remux HLS) advertises `CODECS="avc1.4D4028,ec-3"` — **EAC3 survives copy HLS and Chrome MSE can't decode `ec-3`**. For EAC3/AC3/DTS/TrueHD titles HLS must start at **`copy+aac`** (advertises `mp4a.40.2`, browser-safe), not copy-copy; `h264+aac` is the full-transcode fallback. Plan §2/§4/§5 amended to an **audio-aware ladder**.
- **Resume is client-side** — `StartTimeTicks=600000000` master probe returns the same full VOD playlist (segments echo the param; no truncation) → hls.js `startPosition: resume` as planned.
- **Durable harness** — `scripts/probe_jellyfin_hls.py` committed (auth → playback-info → master/media/segment/StartTimeTicks probes; output fully redacted — verified 0 token leaks). Reusable for Phase 1 verification + future Jellyfin upgrades.
- Frontend/backend product code untouched; **no pytest/vitest change** (script is stdlib-only, not imported by tests).
- Committed `0b330aa`; pushed to GitHub (below, after commit).

## ▶ NEXT SESSION — HLS player Phase 1: backend same-origin HLS proxy (plan §4, §3b)
**Phase 0 DONE** (probes + durable harness above). Next: `api/routes/jellyfin_hls.py` — same token-server-side pattern as `jellyfin_stream.py`, **additive contract paths only**:
1. `GET /api/jellyfin/hls/{item_id}/master.m3u8` → fetch Jellyfin master, **strip every embedded `api_key`**, rewrite relative URIs (media playlist + segments) to `/api/jellyfin/hls/{item_id}/…` keeping `MediaSourceId` + codec params + `runtimeTicks`/`actualSegmentLengthTicks`; passthrough MIME (`application/vnd.apple.mpegurl`, `video/mp2t`) + Range.
2. Media-playlist + segment passthrough routes; query mirrors stream route (`mode=remux|transcode_audio|transcode`, `audio_stream_index`, `max_bitrate`) with the §3b codec-pair mapping.
3. Contract snapshot regen + `npm run generate:types`; full pytest + ruff gates (§7).
4. Phase 2 after that: hls.js engine in `Player.tsx` (delete offset/restart machinery; audio-aware HLS ladder; native HLS on Safari); Phase 3 harness verify.

Gates + deploy + out-of-scope: plan doc §7–9.

## ▶ NEXT SESSION — seek-bar ROOT fix follow-up (SUPERSEDED by the HLS plan above)
**Do NOT continue patching the progressive/restart-seek player.** After redeploying `f74ceba` the user confirmed the seek bug still affects every episode of 3 Body Problem (and movies). Root cause is the transport model — see the HLS plan (`HLS_PLAYER_PLAN.md`), which replaces this effort.

## ▶ LATEST SESSION (2026-09-06) — seek-bar ROOT fix: custom div bar replaces the native range input ✅
**"The bar moves to where I click but the video keeps playing from the old position" — reproduced and root-caused in a headless Chromium harness against the live Jellyfin.** Two rounds of input-event fixes didn't cure it because the control itself was the problem:

- A native `<input type=range>` has a ~6 px hit area and its pointer events can be swallowed (recorded **zero** events reaching the input during real mouse drags while anything overlays the bottom strip).
- A *controlled* range input keeps its thumb visually wherever you clicked whenever React state doesn't change — so with a failed/silent seek the bar permanently shows the clicked point while playback continues from the old spot: exactly the reported symptom.

**Fix (`Player.tsx`):** custom `<div role="slider">` seek bar with pointer capture. Drag previews the fill/thumb; release commits exactly ONE seek (byte-range on direct, restart-at-`StartTimeTicks` on remux/transcode). Fill + thumb are rendered from player state only — the UI can never desync from real position again. Click target ~20 px + pointer capture (immune to overlays); arrows ±10 s, Home/End; click-vs-video-toggle isolated via stopPropagation.

**Verified in the harness:** real mouse drag on the bar previewed during the gesture and committed a single restart-seek at the released position (`start_time_ticks=34220000000` for a 60% click on a 5704 s title; `aria-valuenow` matched). The remaining headless limitation (this sandbox's Chrome can't decode the Jellyfin streams — demux error → error overlay) does not affect real browsers.
- **vitest 36/36** · `tsc` clean · `vite build` ok (frontend-only).
- Committed `f74ceba`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).

## ▶ LATEST SESSION (2026-09-06) — player bug-fix pass: one-commit scrubbing + subtitle overlay ✅
**Live-use bugs:** (1) clicking the seek bar on remux/transcode streams restarted the video — every `input` event during a drag fired a full stream RESTART at `StartTimeTicks` (how chunked streams seek), so a single gesture triggered many reloads; a paused seek also force-played. (2) Selecting a subtitle did nothing — dynamically swapping a native `<track>` after the media resource had loaded is unreliable in browsers, and native tracks align to the media element's *local* clock (wrong for restart-seek streams starting at an offset).

- **Scrub now commits once** — the slider previews while dragging (`scrub` state) and fires exactly ONE seek on pointer-up; plain clicks + keyboard arrows seek directly. The reload path honours the previous play/pause state (`autoPlayRef`), so seeking while paused stays paused, and `canplay` clears the "Preparing stream…" spinner when autoplay is blocked.
- **Subtitles render via overlay** — native `<track>` removed. Selecting a sub fetches the VTT proxy stream, parses it into item-time cues (`parseVtt`/`parseVttTime`; tags + STYLE/REGION/NOTE skipped), and the player draws the active cue aligned to the offset position model — correct across remux/transcode restarts and scrubs.
- **Tests** — +4 frontend (VTT timestamp parsing incl. comma decimals, multi-line cues + tag stripping + settings suffix, NOTE/STYLE/CRLF tolerance, active-cue lookup). **vitest 36/36** (+4) · `tsc` clean · `vite build` ok (no backend change).
- Committed `ffb7905`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).

## ▶ LATEST SESSION (2026-09-06) — Tier 1: honest stream routing — direct / remux / transcode_audio / transcode + REAL quality & audio pickers ✅
**The pickers were decoration.** Verified live: under `Static=true` Jellyfin **ignores** `AudioStreamIndex` + `MaxStreamingBitrate` (identical 206 responses with/without). So Quality and Audio did nothing unless the audio-transcode path happened to be on. Fixed with a full routing ladder + codec-aware auto-decisions; the player now plays the cheapest mode that actually works and says which one it's using.

- **Stream modes** (`/api/jellyfin/stream`, additive): `mode=direct` (Static file, range-seekable) · `remux` (copy/copy → mp4 — solves MKV-style containers the browser can't index up-front) · `transcode_audio` (video copy + AAC) · `transcode` (H.264 + AAC, honours `max_bitrate`). New `start_time_ticks` = restart-seek for chunked non-direct streams (probed live: remux/transcode return chunked `200` MP4 with `ftyp` first — duration resolves instantly but byte-range seeking doesn't exist). Legacy `transcode_audio=true` still maps. Unknown mode → 400.
- **Routing facts** — `playback_info` now returns `container` + first video stream (`codec/profile/width/height/bit_depth/bit_rate`, codecs lowercased). `pickStreamMode()` (frontend): quality ≠ Original → transcode; unsafe video codec (HEVC / 10-bit H.264) → transcode; unsafe audio (EAC3/AC3/DTS/TrueHD) → transcode_audio; non-mp4 container → remux; else direct. **Choosing an audio track forces non-direct** (Static can't honour it).
- **Player** — offset-position model: direct seeks by byte range; remux/transcode RESTART at `StartTimeTicks` mid-position so bar + resume stay seamless. Mode chip (Direct play / Remux / Transcode) in the header + control bar; media errors escalate the ladder (`direct → remux → transcode_audio → transcode`) before a friendly give-up; "Preparing stream…" spinner during mode/quality switches; progress reports now carry the true `PlayMethod` (DirectPlay/DirectStream/Transcode).
- **Tests** — +4 backend (remux URL, transcode URL + bitrate, legacy bool mapping, unknown mode 400, direct ignores params; provider video/container parse) + 6 frontend (routing decisions incl. 10-bit/HEVC/forceNonDirect, labels, play methods). **264 pytest** (+4) · ruff clean · **vitest 32/32** (+6) · `tsc` clean · `vite build` ok. Contract snapshot + `types.ts` regenerated (30 paths, additive).
- Committed `208fc3d`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).
- **Next tier options:** warm-start/prefetch + double-buffered episode switching; autohide controls/gestures/PiP/pref persistence; or HLS/hls.js adaptive (supersedes restart-seek for transcode).

## ▶ LATEST SESSION (2026-09-06) — player seek-bar fix: total from API runtime, custom controls ✅
**"When I start an episode the progress bar doesn't show the correct status — no length shown." Root cause: the player used the NATIVE `<video controls>` bar, and direct-play containers the browser can't index up-front report `duration = Infinity`. With no finite total the native bar broke: no end-length, position math wrong a few seconds in. Jellyfin's scan metadata (runtime on every movie/episode) was ALREADY correct end-to-end (probed live: `RunTimeTicks` + `UserData.PlaybackPositionTicks` present on items, episodes and Resume; the repo provider parses them right) — the player just never used it.**

- **`Player.tsx`** — native `controls` removed; custom bar whose total = `barTotal(stream duration once finite, else the API runtime hint)` → length + % correct from the first frame even while the stream duration is still unknown. Adds: play/pause, seek slider, `cur / total` time (mm:ss / h:mm:ss), volume + mute, fullscreen, click-video-to-toggle, keyboard (space, ←/→ ±10 s, m, f, Esc). Resume-seek + 5 s-throttled `/api/jellyfin/progress` reporting unchanged.
- **Length plumbing** — `QueueEntry` carries `runtime` (from `episodeQueue`), `LibraryView` threads it into the Player for movie / episode / Up-Next paths, so every play path seeds the correct total (e.g. *3 Body Problem* S1E4 shows 0:00 / 44:08, not `/ --:--`).
- **Helpers + tests** — pure `fmtTime` / `isFiniteDuration` / `barTotal` (stream-first, hint fallback) / `clampSeek`; queue test now asserts runtime travels with the entry. **vitest 26/26** (+4) · `tsc` clean · `vite build` ok.
- Committed `d950c8a`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).
- **Note:** seeking still depends on the browser being able to map time→bytes once buffered; for containers where even Jellyfin's own web player must transcode to seek, a future "force remux" option would be the lever (item 5 territory).

## ▶ LATEST SESSION (2026-09-06) — audio-transcode follow-up: EAC3/AC3/DTS/TrueHD → AAC (video copy) ✅
**In-app playback went silent on any Jellyfin title whose audio track the browser can't decode — direct play (`Static=true`) served EAC3/AC3/DTS/TrueHD untouched. Follow-up to item 3 lands automatic audio transcoding, fully additive (`/api` frozen → one new query param, no new path).**

- **Backend** (`api/routes/jellyfin_stream.py`): `GET /api/jellyfin/stream/{id}` accepts `transcode_audio=true` → swaps `Static=true` direct play for Jellyfin's on-the-fly stream with `VideoCodec=copy` (video untouched) + `AudioCodec=aac` + `MaxAudioChannels=2`. `audio_stream_index` / `max_bitrate` forward in both modes.
- **Codec surfacing** (`services/library/jellyfin.py`): `playback_info` audio tracks now carry `codec` (from the Jellyfin media-source `Codec` field) so the player decides without extra round-trips.
- **Frontend**: `audioCodecNeedsTranscode()` whitelists browser-safe codecs (`aac/mp3/opus/vorbis/flac/pcm_s16le/pcm_s24le/pcm_mulaw/alac`; unknown/missing → false — never over-transcode); `Player.tsx` derives `transcode` from the active track (first by default, re-evaluates on audio-track switch) and shows a subtle "⚠ audio transcoding (codec)" hint; `streamUrl` passes `transcode_audio`.
- **Contract**: OpenAPI snapshot + `types.ts` regenerated — additive, 30 paths unchanged, `transcode_audio` query param added.
- **Tests**: +2 backend (transcode URL asserts no `Static=true` + `VideoCodec=copy`/`AudioCodec=aac`/`MaxAudioChannels=2`/`AudioStreamIndex` forwarded; codec surfaced in track list), +1 frontend (codec whitelist: `eac3/ac3/dts/TRUEHD` → true, `aac/AAC/opus/flac` → false, case-insensitive, unknown/null → false). **260 pytest** (was 259) · production `ruff` clean · **vitest 22/22** · `tsc` clean · `vite build` ok.
- Committed `1bc9940`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).
- **Roadmap:** this lands the *audio-codec* slice of transcode robustness ahead of schedule; item 5 (full transcode-fallback engine — auto-open Jellyfin when direct play fails) remains its focus.

## ▶ LATEST SESSION (2026-09-06) — Roadmap item 3: player features — speed / audio / subtitle / quality pickers + autoplay-next + backdrop ✅
**Item 3 lands on the new modular structure.** The in-app player gains a full control surface, all same-origin (`/api` additive-only, no secret leaks).

- **Backend (additive):**
  - `JellyfinLibraryProvider.playback_info(item_id)` — probes `POST /Items/{id}/PlaybackInfo`, normalises the first media source into audio + **text-only** subtitle track lists (image/PGS subtitle streams are excluded — a browser `<track>` can't render them). ABC default + `LibraryService` aggregate added.
  - `GET /api/jellyfin/playback-info?id=` (via service) + `GET /api/jellyfin/subtitle?id=&ms=&index=` (WebVTT proxy, token server-side).
  - `GET /api/jellyfin/backdrop?id=` — `get_poster` gained a `kind` param (Primary/Backdrop/…) with a shared `_proxy_image` helper.
  - `GET /api/jellyfin/stream/{id}` now accepts `audio_stream_index` + `max_bitrate` (audio switching + the quality picker) — absent by default, forwarded when set.
  - **Contract 27 → 30 paths** (backdrop, playback-info, subtitle) + `types.ts` regenerated (additive, no drift).
- **Frontend:** `Player.tsx` adds **Speed** (0.5–2×), **Quality** (Original/1080p/720p/480p), **Audio** (track picker) and **Subs** (`<track>` VTT, default-on) controls; a 16:9 **backdrop** behind the player; **autoplay-next** — a cancellable 8s countdown auto-advances the series queue on `ended` (manual Play-next + Cancel kept).
- **Tests:** +2 provider (playback_info normalisation, excludes image subs; not-configured → None), +4 routes (stream params, backdrop kind, playback-info, subtitle VTT), +3 frontend (rates, quality mapping, autoplay delay). **259 pytest** (was 253) · production `ruff` clean · **vitest 21/21** · `tsc` clean · `vite build` 99 modules.
- **Deferred to item 5 (its focus):** the Jellyfin transcode-fallback *engine* (auto-open Jellyfin when direct-play fails). Item 3 shipped the quality picker UI; item 5 owns fallback robustness.
- **Roadmap status:** items 1–3 ✅. Items 4 (library & discovery) and 5 (transcode robustness) remain.

## ▶ LATEST SESSION (2026-09-06) — fix: Jellyfin `thumb` aspect-ratio leak ✅
**One-line fix + regression test. `thumb=it.get("Thumb","") or it.get("PrimaryImageAspectRatio","") or ""` emitted the *numeric aspect ratio* (e.g. `0.666`) as the item's thumb whenever Jellyfin returned no `Thumb` (banner) image — which is most titles. That float-string leaked into every `/api` `thumb` field. Now: `thumb=it.get("Thumb","") or ""` (matches the Emby provider); the React cards were unaffected (they build posters from `item.id` via the `/api/jellyfin/poster` id-proxy → `Primary`), so this was purely the API-shape/wrong-value fix.**

- `services/library/jellyfin.py` `_parse_item` — drop the `PrimaryImageAspectRatio` fallback (a ratio, not a path).
- `tests/test_jellyfin_provider.py` — new `test_parse_item_thumb_never_leaks_aspect_ratio`: thumb preserved when present; empty (never a numeric ratio) when absent.
- Verify: **253 pytest passed** (was 252) · production `ruff check` clean · no contract/`types.ts` regen needed (field stays a plain `string`; the bug was a *value*, not a type).
- Pushed to GitHub — `experiment/bundled-docker-stack` tip `8dc174a` (verified origin matches local, 0 behind). CI workflow file left out of scope per user.

## ▶ LATEST SESSION (2026-09-06) — Roadmap item 2: watch-state — mark watched/unwatched + Recently Watched + play count ✅

**Item 2 of the Plex roadmap lands** on the new modular structure (as planned — it lives in the library/playback feature area). Additive backend endpoint + contract regen + frontend.

- **Backend** (`services/library/jellyfin.py`): added `play_count` + `last_played` to `_item_public` (surfaced on every library serializer, additive contract fields); new `recently_watched(limit)` capability → played items sorted by `UserData.LastPlayedDate` desc; new `mark_state(item_id, watched)` → Jellyfin `Users/{uid}/PlayedItems|UnplayedItems`, invalidates the scan cache, returns fresh `{played, play_count}`.
- **ABC + service**: `LibraryProvider` gains `recently_watched`/`mark_state` (default `[]`/`None`); `LibraryService` aggregates to the first provider that supports it.
- **Routes** (additive): `GET /api/library/recently-watched` + `POST /api/library/{item_id}/state` `{watched}`. Snapshot **regen → 27 paths**; `types.ts` regenerated.
- **Frontend**: `client.ts` (`getRecentlyWatched`, `mutateItemState`); `useRecentlyWatched` + `useMutateItemState` (invalidates all library/episodes queries so the ticks move everywhere); **MediaCard** gets a **Mark-watched / ✓ Marked watched** toggle + **play-count**; **LibraryView** adds a **Recently Watched** row and wires toggles across grid / Continue Watching / Recently.
- **Tests**: +4 backend (`recently_watched` sort/filter, `mark_state` POST played+unplayed, both routes). **252 pytest** · ruff clean · frontend tsc/build/vitest 18/18.
- **Roadmap status:** item 2 ✅. Items 3–5 remain (player features, library/discovery, transcode robustness).

## ▶ LATEST SESSION (2026-09-06) — Phase 3b: `playback` slice — real in-app player + episode picker ✅

**Player core ported, frontend-only (no contract change — `reportProgress`/`streamUrl` hit the existing frozen `/api`).** Movies play in-app with resume + progress reporting; series get the episode picker with per-episode resume + Up Next.

- **`features/playback/Player.tsx`** — same-origin `/api/jellyfin/stream/{id}`; seeks saved resume on `loadedmetadata`; reports `/api/jellyfin/progress` (`start` / 5s-throttled `timeupdate` / pause·ended·error → `stopped`) via `postJson`, with the **resume-guard** that never POSTs 0 while a fresh stream sits at the start (mirrors legacy `_reportPos`); codec-failure fallback note; **Up Next** overlay from the series queue (Play next → switch).
- **`features/playback/EpisodePicker.tsx`** — season-grouped rows, per-episode thumb, ✓ watched tick, **Play/Resume/Replay** (start-position-aware), Escape/backdrop close.
- **`features/playback/lib.ts`** — pure `groupBySeason`/`nextEpisode`/`episodeQueue`/`playLabel`/`startPosition`/`episodeThumbUrl` exactly mirroring legacy; **+6 unit tests** (18 total).
- **`client.ts`** — added `postJson`, `ProgressPayload`, `reportProgress`, `streamUrl`. Endpoint already in the frozen contract → **no `types.ts` regen, no drift**.
- **`LibraryView`** — movie → Player; series → EpisodePicker → Player (Up-Next queue); Player keyed by item so an episode switch remounts cleanly.
- **Verify:** `tsc` clean · `vite build` 99 modules · `vitest` **18/18**.
- **Deferred (item 2 watch-state):** mark watched/unwatched, Recently Watched row, play count — needs an **additive backend endpoint** (`POST /api/library/{id}/state`) + contract regen; its own pass.

## ▶ LATEST SESSION (2026-09-06) — Phase 3a: `library` feature slice ported to React ✅

**`/library` now renders in the React shell at legacy parity** — poster wall + Continue Watching + scan wiring. Legacy `app.js` untouched.

- **`features/library/api.ts`** — `useLibraryItems`/`useContinueWatching` (TanStack Query) + `useScanLibrary` mutation that invalidates library queries on success (drive-the-backend).
- **`features/library/lib.ts`** — pure helpers mirroring legacy `app.js` exactly: `posterUrl` (Jellyfin poster proxy → Plex thumb proxy fallback), `playbackMarker` (watched tick vs amber resume % vs none — copied logic), `isContinueWatching` filter, `isSeries`. **10 unit tests** pins parity.
- **`MediaCard.tsx`** — poster, MOVIE/TV badge, watched/resume markers, primary **Play in RKM** (movie) / **Episodes** (series) + Jellyfin deeplink; **`ContinueWatchingRow.tsx`** + **`LibraryView.tsx`** (title counts, Scan button, series-play notice, poster grid).
- **`Player.tsx`** — minimal same-origin `/api/jellyfin/stream` video so movies actually play; **full playback slice (resume reporting, mark-watched, up-next, episode picker) = Phase 3b** (roadmap item 2 lands there).
- `client.ts` `MediaItem` aligned to the real item shape; `router.tsx` `/library → LibraryView`.
- **Verify:** `tsc` clean · `vite build` 96 modules · `vitest` **12/12**.

## ▶ LATEST SESSION (2026-09-06) — Phase 2: `web/` React/TS shell + typed client + flag ✅

**`web/` builds and serves a working shell showing `/api/config` health behind a flag.** Legacy `app.js` untouched, still the prod default.

- **Shell** (`web/`, React 18 + TS + Vite 5 + Tailwind 3): `main.tsx` → `RouterProvider` (react-router-dom) → `AppShell` (Sidebar/Header/Outlet) with routes `settings` (real) + `library`/`playback`/`discover`/`watchlist`/`search`/`suggest` (PortedPlaceholder stubs for Phase 3).
- **Typed client** — `src/lib/api/types.ts` **machine-generated from the frozen contract** (`npm run generate:types`, openapi-typescript over `docs/api/openapi.v1.json`, 1,817 lines = source of truth); `src/lib/api/client.ts` hand-tunes the narrow stable surface (config/health/library/episodes) keyed to the `@/` alias; same-origin `/api/*` (nginx→FastAPI, secrets stay server-side).
- **Feature flag** — `lib/flags.ts` (`VITE_ENABLE_REACT`): `npm run dev` shows the shell; a prod build without the env keeps the legacy app serving (LegacyPlaceholder) until Phase-4 cutover.
- **ConfigHealthView** — TanStack Query hooks (`features/settings/api.ts`) read `/api/config` + `/api/health`; per-service configured/ok badges + degraded banner. TanStack Query already the server-state layer.
- **CI** — added the **frontend job** to `.github/workflows/ci.yml`: `npm ci` → `typecheck` → `vitest` → `build` → **contract-drift guard** (`npm run generate:types && git diff --exit-code types.ts`).
- **Verify:** `tsc --noEmit` clean · `vite build` 90 modules, dist 0.44kB html + 252kB js / 9.5kB css · `vitest` **2/2** · `vite preview` serves `/`, js, css all **200**. (7 npm audit vulns = dev-deps; not force-fixed to avoid breakage.)

**Caveat (dev-proxy):** `vite.config.ts` proxies `/api → http://127.0.0.1:8000` for dev; point `VITE_API_PROXY` at a running backend (e.g. the bundled Jellyfin stack) to see live config health in `npm run dev`.

## ▶ LATEST SESSION (2026-09-06) — Phases 0 + 1a executed (CI + contract freeze + ABC capability surface) ✅

**Following `modular-scalable-architecture.md`.** Not just documenting — executed Phase 0 fully and Phase 1's core (ABC capability surface). Both committed + verified green; **push to GitHub blocked on a token scope** (below).

### Phase 0 — CI + contract freeze + docs reset ✅ (`dc6c72a`)
- **`.github/workflows/ci.yml`** — backend job on every push: `ruff check` (F/pyflakes grade on production packages per `ruff.toml`) + `python -m pytest tests/ -q`. Frontend `tsc`+`vitest`+build job added in Phase 2 when `web/` exists.
- **Frozen contract** — `docs/api/openapi.v1.json` (25 paths) via new `scripts/snapshot_openapi.py` (idempotent, path-safe); `/api` = immutable v1, additive-only (ADR-0001).
- **ADRs** — `docs/adr/ADR-0001` (freeze /api) · `0002` (React/TS frontend) · `0003` (keep-Python, consolidate don't rewrite).
- **Docs reset** — README + ARCHITECTURE status pointers to the plan/contract/ADRs.
- **6 latent bugs fixed** (ruff F baseline) so the lint gate is genuinely green: `F823`/`UnboundLocalError` `urllib` used before the function-local import in `api/routes/search.py` + `services/plex.py` (real runtime bug); `F811` duplicate `has_jellyfin` in `config/settings.py`; `F402` dataclasses `field` shadowed by a loop var in `services/watchlist.py`; dead `entry`/`in_watchlist` vars in `api/routes/suggest.py`. Plus 55 safe ruff `--fix` cleanups (imports/vars) across prod packages.
- **Verify:** `ruff check` (prod) clean · **247 pytest passed**.

### Phase 1a — ABC capability surface + route cleanup ✅ (`ba32448`)
- `LibraryProvider` ABC now declares `all_items`/`continue_watching`/`episodes`/`refresh_library`/`get_poster` with harmless defaults (`[]`/`False`/`None`) — **uniform provider surface**.
- `LibraryService` gained **aggregate collapse** methods: each capability returns the first provider with a **meaningful** result, so a Plex defaulting to `[]` can't shadow a Jellyfin that implements it.
- Routes `/api/library/items`, `/library/continue-watching`, `/library/series/{id}/episodes`, and `/api/jellyfin/poster` now call the **service**, not `getattr`/`hasattr`; deleted `_first_provider_with` feature-detection.
- Tests re-targeted to the service seam (response shapes unchanged) + **1 new regression test** pinning the collapse behavior.
- **Verify:** ruff clean · **248 pytest passed** (+1).

### Phase 1b — facade "consolidation" finding ⚠ design refinement
The plan assumed parallel duplicate service modules to delete. **The audit shows they're NOT duplicates**:
- `services/plex.py` (`PlexService`), `services/radarr.py` (`RadarrService`), `services/sonarr.py` (`SonarrService`) are the **canonical low-level clients**; the canonical packages are thin adapters *over* them — e.g. `RadarrAcquisitionProvider` wraps `RadarrService` (`from services.radarr import RadarrService`); `services/library/plex.py` wraps `PlexService`. §43 "one implementation per rule" **already holds** — no parallel logic.
- `services/recommendations.py` (`RecommendationService`) + `services/media_status.py` (`MediaStatusService`) are already thin delegates to canonical `services/recommendation/` + `services/reconciliation/`.

**Recommendation:** Phase 1's "consolidation" is really **optional relocation** (move clients into their domain packages + re-export stubs), which buys organization but **not** dedup, and adds churn/risk. **Recommend low priority / defer** — it doesn't block the React port. The genuine Phase 1 value (uniform provider SPI + route-via-service) is DONE.

### ⚠ Push blocker (deployment-action needed)
Commits `dc6c72a`, `ba32448` are **local only**. `git push` to GitHub is refused because the new `.github/workflows/ci.yml` requires the token to hold the **`workflow`** scope, and the sandbox `GITHUB_TOKEN` (in `/workspace/.env`) lacks it.
```powershell
# GitHub → Settings → Developer settings → PAT (classic) → select the token used as
# GITHUB_TOKEN in /workspace/.env → add the "workflow" checkbox (keep "repo") → Update.
#   (or: gh auth refresh -s workflow)
# Then re-run the sandbox push; Phase 0+1a go up and CI actually runs on GitHub.
```

### NEXT (prioritized)
1. **Unblock the token** (`workflow` scope) → push Phase 0 + 1a → confirm CI green on GitHub.
2. Decide **Phase 1b** (defers relocation — recommend skip/defer).
3. **Phase 2** — `web/` React/TS shell + `openapi-typescript` typed client + feature flag.

## ▶ LATEST SESSION (2026-09-06) — Modular & Scalable re-platform: PLAN adopted (no code) ✅

**Decision:** keep the sound FastAPI/Python backend (consolidate facades + extend the ABC — no rewrite); rewrite the **frontend** to **React 18 + TypeScript + Vite + Tailwind** behind a **frozen `/api` contract**. The contract is the seam that de-risks the re-platform. Full plan committed at **`modular-scalable-architecture.md`** (decisions table, risks, open questions, phases, validation).

**Why now (the constraint):** `app.js` is a **2,191-line single-file monolith** (+ `api.js` 124, `app.css` 967) — global render functions + delegated handlers, global state (`DATA`/`RES`/`LIBALL`/`LIBWATCH`) — not maintainable past a handful of screens. Backend is modular but carries **BC-facade debt** (`services/plex.py`, `emby.py`, `radarr.py`, `sonarr.py`, `recommendations.py`, `media_status.py` coexist with canonical `services/library|acquisition|recommendation|reconciliation/`) and the Jellyfin-only capability methods (`all_items`, `continue_watching`, `episodes`, `refresh_library`, `get_poster`) are **not declared in the `LibraryProvider` ABC** — routes call `getattr(provider, …)`. No CI, no typed API contract, stale root docs.

**Phases (each ends committed + a working demo):**
0. **CI + contract freeze + docs reset** — GH Actions (ruff/mypy + `pytest`; frontend `tsc`+`vitest`+build once `web/` exists); snapshot `openapi.json` → `docs/api/openapi.v1.json` (v1 immutable, additive-only); rewrite `README.md`/`ARCHITECTURE.md` + ADRs.
1. **Consolidate backend facades + ABC capability surface** — delete BC shims (re-export stubs w/ `DeprecationWarning` → remove); add `all_items`/`continue_watching`/`episodes`/`refresh_library`/`get_poster` to the ABC/mixin (Plex/Emby default `[]`/`False`); routes call the ABC. Target 250+ pytest.
2. **`web/` shell + typed client + flag** — Vite React/TS app, router, `AppShell`/`Sidebar`/`Header`, Tailwind; `types.ts` generated via `openapi-typescript`; `lib/api/client.ts`; TanStack Query (server state, tied to scan invalidation) + light Zustand; feature-flag routing behind a config toggle. Exit: shell builds + shows `/api/config` health.
3. **Port features to slices (parity each, behind the flag)** — `library` (poster wall, Continue Watching, scan wiring) → `playback` (player, resume, progress reporting, up-next, mark-watched — **roadmap item 2 lands here**) → `discover` (hero + rows) → `watchlist`/`search`/`suggest`/`settings`. Old app serves not-yet-ported views.
4. **Cut over + retire legacy** — flip default to React; delete `app.js`/`api.js`/legacy CSS.
5. **Items 2–5 on the new structure** — built once on the right foundation; multi-user (item 6) slots into `auth`/`playback` slices.

**Decisions (rationale + alternatives in the doc):** React 18+TS+Vite (matches your senior stack) · TanStack Query (cache + auto-invalidation tied to scan/job runs) + light Zustand · **keep Python/FastAPI** (already sound; rewriting is the classic trap) · **frozen `/api` + generated client** · **monorepo** (one repo, `web/` + backend dirs) · remove legacy **only at feature parity behind a flag**.

**Big-rewrite-smell risk + mitigations (highest risk):** (a) freeze `/api` first, (b) backend unchanged, (c) feature-flagged incremental port, (d) parity-check each view before retirement. Contract drift → closed by openapi-typescript + CI typecheck. Facade-deletion breakage → closed by one-release re-export stubs.

**Open questions (answer by Phase 2):** multi-user/auth? runtime = same nginx volume mount serving `web/dist/`? keep `dashboard.html`/`dashboard-data.json` legacy? testing bar (vitest + a few Playwright smoke)?

**Recommended next session: Phase 0 + 1** (CI + backend consolidation + contract freeze) — low-risk, immediately validates the modularity thesis, and makes the React port far safer.

## ▶ LATEST SESSION (2026-09-05, round 5) — TV shows: episodes + per-episode resume + Up Next ✅

**Item 1 of the Plex-like roadmap.** TV cards no longer "play" a non-playable Series id — they open an episode picker.

- **Backend (`services/library/jellyfin.py`):** `episodes(series_id)` lists every episode via `/Users/{uid}/Items?ParentId={seriesId}&IncludeItemTypes=Episode&SortBy=IndexNumber,ParentIndexNumber&Fields=…UserData…`, each with `{id,name,season,episode,thumb,played,playback_position,runtime}` (per-episode UserData → per-episode resume/watched). Route `GET /api/library/series/{id}/episodes` in `api/routes/library.py` (`_first_provider_with`).
- **Frontend (`app.js`/`app.css`/`api.js`):** `cardPrimaryPlay(itemId, position, isTv, title)` — movies → `data-act="play"` ("Play in RKM"), **TV → `data-act="series"` ("Episodes")**. Global handler `data-act="series"` + modal `data-role="episodes-jellyfin"` → `openEpisodes(seriesId,title)` modal: groups by season, each row has a thumb (`/api/jellyfin/poster`), watched/reume state, a per-episode **Play/Resume/Replay** button (`data-act="play"` + `data-resume`) → `openPlayer` reuses everything. `Up Next`: `_episodeQueue` (ordered episodes) + `nextEpisode(id)`; on `ended` the player shows an "Up Next" overlay with a Play-next button. Episode Stream proxy works per-episode-id (no new streaming code).
- **Note on TV testing:** the bundled library has **0 shows**, so this is unit-tested (grouping/sort/watched/resume/next) and the Jellyfin episodes endpoint was confirmed live (returns 200/400-shape, needs a real `ParentId`). Real TV can only be exercised once a show is added to the library.
- **Tests:** backend `test_episodes_lists_and_sorts_per_season` + `test_series_episodes_route`; frontend `cardPrimaryPlay` movie/TV, `playInRkmMarkup` TV role, `renderEpisodes` grouping/order/watched/resume, `nextEpisode` (phase26 now 25). **238 pytest + phase11/18/25/26 node green.**
- **To go live:** rebuild `.\bootstrap.ps1` (new backend route) + hard-refresh. Then a TV card's "Episodes" → pick a season/episode → plays in-app, resumes where you left it, and offers Up Next at the end.

## Automatic library scan (once/day) — small add-on

**Daily Jellyfin library scan inside RKM** so media dropped into the library folders gets scanned+indexed even when the app is idle.

- **Backend:** `JellyfinLibraryProvider.refresh_library()` → `POST {JELLYFIN_URL}/Library/Refresh` (verified 204 live). New `jobs/library_scan.py` (`LibraryScanJob.run` + `run_library_scan()`), records a `job_runs` audit row, returns `JobResult` (counts `{jellyfin, scanned}`). When Jellyfin isn't configured it reports cleanly (`{jellyfin:false, scanned:0}`) instead of erroring.
- **Scheduling:** added to the in-process scheduler (`jobs/scheduler.py`) as a **once/day** task at `DAILY_JOB_HOUR`, gated on `config.has_jellyfin()` (so Plex/Emby-only stacks skip it; independent of `AUTO_ADD_ENABLED`). Bundled stack already runs the scheduler (`WATCHLIST_SCHEDULER=true` in `render_config.py`). **On-demand** trigger too: `POST /api/jobs/library_scan/run` (registered in `api/routes/jobs.py`).
- **Tests:** provider refresh (204→True, not-configured→False), job not-configured/reconfigured, scheduler wiring, endpoint (6 new). **244 pytest + all node suites green.**
- **To go live:** rebuild `.\bootstrap.ps1`. After that it scans automatically every day; you can also hit `POST /api/jobs/library_scan/run` (or the refresh button wiring later) to force a scan. All job runs are visible on `GET /api/jobs`.
- **Cache bug that hid newly-added shows (FIXED, 247 pytest):** `JellyfinLibraryProvider` had a **single shared `_item_cache_expiry` for Movie AND Series**. Every fetch of Movies (e.g. any `/api/library` view) renewed that one deadline, so a Series cache populated **empty** at boot never refreshed — newly-added TV stayed invisible until a rebuild, despite Jellyfin having scanned it. Fix: **per-type expiry** (dict keyed by item type) + `refresh_library()` now calls `invalidate()` after a successful scan so results update immediately. Regression tests `test_per_type_cache_does_not_hide_series` + `test_refresh_library_invalidates_cache`. **This fix is backend — needs `.\bootstrap.ps1` to go live.**

## ▶ LATEST SESSION (2026-09-05, round 4) — Full library grid + Continue Watching ✅

**Poster-wall library + a Discover "Continue Watching" row**, completing the 1→3 roadmap. Branch **pushed to GitHub**.

- **Backend (`services/library/jellyfin.py`):** factored a shared serializer `_item_public(item)` (used by `recently_added`), a raw fetcher `_fetch_raw(url)`, and `_parse_item(it, type)` (dedupes the old inline item parsing). New **`all_items(limit=None)`** → every Movie+Series with playback facts (feeds the grid). New **`continue_watching(limit=12)`** → started-and-unfinished titles (**by filtering the already-fetched library scan for `position_ticks>0 and not played` — NOT Jellyfin's `/Items/Resume`, which returned 0 items despite a 21% position**; Jellyfin's resume endpoint is finicky about how it computes in-progress). Plex/Emby lack these methods → routes return `[]` gracefully.
- **Routes (`api/routes/library.py`):** `GET /api/library/items` and `GET /api/library/continue-watching`, thin — `_first_provider_with(service, attr)` picks the first provider exposing the method; failure-safe.
- **Frontend (`api.js`/`app.js`/`app.css`):** `API.getLibraryItems()` / `API.getContinueWatching()`; `loadLibrary()` caches `LIBALL` + `LIBWATCH`. `renderDiscover()` inserts a **Continue Watching** row right after the hero (from `LIBWATCH`, filtered, reusing `libraryCard` → resume bar + Play-in-RKM). `renderLibraryView()` adds a **Full Library poster-wall** `<div class="grid">` (from `LIBALL`) below the stats + recently-added strip.
- **Live-verified Jellyfin persistence:** a controlled `start`+`timeupdate(600s)` sequence stuck at **600s** in UserData and survived a `Stopped` call (the earlier "wiped back to 0" was a transient/library-scan artifact, not the reporting); the resume % bar reads this position.
- **Tests:** provider `test_all_items_lists_entire_library` + `test_continue_watching_filters_in_progress`; route `test_library_items_route_returns_all` + `test_library_continue_watching_route`; frontend `continueWatchingRowMarkup`×2 + `fullLibraryGridMarkup` (phase26 now 18 assertions). **236 pytest + phase11/18/25/26 node all green.**
- **To go live:** rebuild `.\bootstrap.ps1`, hard-refresh — Library tab becomes a poster wall; Discover shows a Continue Watching row for partially-watched titles.

## ▶ LATEST SESSION (2026-09-05, round 3) — Watched / progress (Jellyfin UserData) built + verified ✅

**Resume % bar + watched tick** driven by Jellyfin `UserData`, AND in-app playback now reports back so the markers actually move.

- **Backend data source:** `JellyfinItem` now captures `UserData.Played`, `UserData.PlaybackPositionTicks`, and item `RunTimeTicks`. `_match_from` → metadata gains `played` / `playback_position` / `runtime` (10ms ticks → seconds via `_ticks_to_sec()`); `recently_added()` emits the same three keys (so **`/api/library` recent** carries them → Library cards). `WatchLink` gains `played`/`playback_position`/`runtime` filled from `match.metadata` and emitted in `to_dict()` → `WatchEntryModel` (grid/modal via resource API).
- **Backend progress reporting:** `POST /api/jellyfin/progress` (in `jellyfin_stream.py`) takes `{item_id, position_ticks, is_paused, event}` and forwards to Jellyfin **Sessions** via the server-side key — `start`→`/Sessions/Playing`, `timeupdate`→`/Sessions/Playing/Progress`, `stopped`→`/Sessions/Playing/Stopped`. **Verified live:** these endpoints return `204` with `?api_key=…` + JSON body, and one progress call moved (500) Days to **1200s/5705s (21%)** in the server's UserData.
- **Critical finding:** a plain `<video>` (in-app playback) does NOT report to Jellyfin, so `UserData` stayed at 0 even after playing. Without this reporting the resume/watch markers would never move — that's why the player now reports.
- **Frontend (`app.js`/`app.css`):** `playbackMarkup(info)` renders a **watched tick** (green circle) when `played`, else an amber **resume % bar** (bottom of poster, `width:%`) when `position>0 && runtime>0`. Wired into `libraryCard` (Library view) + `cardMarkup` (grid, from `s.watch.jellyfin`). `openPlayer()` now sends `start` on play, throttled `timeupdate` every 5s, and `stopped` on pause/ended/error via `reportProgress()` → `/api/jellyfin/progress`.
- **Tests:** backend `test_resource_watch_carries_playback_facts`, `test_recently_added_carries_playback_facts`, `test_watch_link_emits_playback_facts`, `test_progress_forwards_to_jellyfin_sessions`, `test_progress_uses_playing_for_start_event` (5 new); frontend `playbackMarkup`×3, `libraryCard` resume+watched, `cardMarkup` resume, `reportProgress` capture (6 new). **232 pytest + phase11/18/25/26 node all green.**
- **To go live:** rebuild the bundled stack `.\bootstrap.ps1`, then hard-refresh — watch a movie a couple of minutes, close it, and its card shows a resume bar.

## ▶ LATEST SESSION (2026-09-05, round 2) — In-app Jellyfin playback built + verified ✅

**Plays the library INSIDE the RKM app** (native `<video>`, no jump to Jellyfin). Same branch `experiment/bundled-docker-stack`.

- **Backend:** new `api/routes/jellyfin_stream.py` → `GET /api/jellyfin/stream/{item_id}` proxies Jellyfin **direct play** (`/Videos/{id}/stream?api_key=…&Static=true`), forwards the client `Range` header upstream and passes through the upstream status (206/200) + `Content-Type`/`Accept-Ranges`/`Content-Range` chunked. 503 if not configured. Registered in `api/main.py`. **Verified live against the running bundled Jellyfin (10.11.11, tailnet `:8098`):** `Range: bytes=0-1023` → `206` + `Content-Range: bytes 0-1023/1882377499`, `video/mp4`, H.264/AAC direct-play.
- **`item_id` plumbing:** `WatchLink` (services/library/watch_links.py) gains `item_id` (filled from `match.metadata["item_id"]`); surfaced through `WatchEntryModel.item_id` + `StatusEntry.jellyfinItemId`; `/_snapshot_to_media` + `/status` emit it. Frontend `st()` exposes `jellyfinItemId`; `/api/watchlist` (→ `_snapshot_to_media`) is what feeds the live grid.
- **Frontend (`app.js`/`app.css`, volume-mounted → live on hard-refresh):** when Jellyfin is the available source with an `item_id`, the card's primary action becomes **"▶ Play in RKM"** (`data-act="play"` → `openPlayer(itemId)`), with the Jellyfin deep-link kept as a secondary button; the detail modal prepends a `data-role="play-jellyfin"` "Play in RKM" button. `openPlayer()` builds a `.player-overlay` with a native `<video controls autoplay>` hitting `/api/jellyfin/stream/{itemId}`; codec-failure shows a friendly in-overlay error instead of a dead video.
- **Tests:** `tests/test_jellyfin_stream.py` (4: Range→206 passthrough, 200 full, 503 unconfigured, resource `item_id`) + `tests/phase26_jellyfin_play_frontend.test.mjs` (6: st.jellyfinItemId, card Play-in-RKM, deep-link fallback, playInRkmMarkup, modal play-first). **227 pytest + phase11/18/25/26 node all green.**
- **To go live:** backend route + item_id need the API container rebuilt on RKM-HP via **`.\bootstrap.ps1`** (the bundled api+web+Jellyfin stack — that's where `MEDIA_SERVER=jellyfin` + the Jellyfin key are injected, so `item_id` flows and the Play-in-RKM buttons render). Prod `.\run-rkm-cinema.ps1` uses the Plex/Emby backend, so it won't show Jellyfin playback. Frontend-only files (app.js/app.css) are live immediately via the volume mount.

## ▶ LATEST SESSION (2026-09-05) — Bundled Jellyfin stack ("Jellyfin client") built + verified ✅

**Branch `experiment/bundled-docker-stack`.** Self-contained Compose project **`rkm-bundled`** that runs its OWN Jellyfin + the RKM app (api+web) — no pre-existing media stack needed. Fully **isolated from prod** (network `rkm-exp`, own `./data`, non-colliding ports: Jellyfin `:8098`, dashboard `:8124`). Verified live: `/api/config` → `jellyfin: true`, `/api/library` → provider `jellyfin`, counts `{movie:2}`, Watch links open Jellyfin & play.

**Run (Windows, one command):** `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema; .\bootstrap.ps1` (zero-edit: TMDB auto-fills from canonical workspace `.env`; Jellyfin admin password auto-generates & persists to `rkm.config.toml`). Teardown: `docker compose -p rkm-bundled down` · full wipe: `down -v`.

**Files (on the branch):** `docker-compose.yml` (api+web+jellyfin, `fullstack` profile for radarr/sonarr/prowlarr/qbit), `render_config.py` (TOML→`.env`/`.rkm.env`), `rkm.config.example.toml`, `provisioner/provision.py` + Dockerfile, `bootstrap.ps1`/`.sh`, committed `index.html`. App changes: `JellyfinLibraryProvider` (`services/library/jellyfin.py`) + `build_library_service` factory (`services/library/factory.py`, `MEDIA_SERVER=jellyfin|emby|plex` — prod default Plex+Emby preserved, all call sites wired to the factory); settings `MEDIA_SERVER`/`JELLYFIN_BROWSER_URL` + runtime-config loader (`RKM_RUNTIME_PATH=/shared/runtime.json`); frontend `Watch on Jellyfin` (cards/modal/library) + tab re-order. Backend `api/routes/jellyfin_poster.py` proxies posters; deep links use Jellyfin-web `#/details` (NO `#!/` hashbang). **223 pytest + phase11/18/25 node green.**

**Jellyfin 10.11 provisioning gotchas (all banked in skill `media-server-stack` → `references/jellyfin-bundled-provisioning.md` — DO NOT re-derive):** wizard flag is `System/Info/Public.StartupWizardCompleted`; auth REQUIRES `X-Emby-Authorization` header (else `400 Error processing request`); `POST /Startup/User` sets-not-creates (needs `GET /Startup/User` first) + password is PLAINTEXT; `POST /Auth/Keys` flaky on 10.11 → fall back to **admin AccessToken as `?api_key=`**; libraries must use the `paths=` QUERY form (body PathInfos silently 204s w/o setting path) + verify `Locations`; after provisioning `up -d --force-recreate api` (Config is lru-cached per process). `x-media` compose anchor must be a scalar STRING.

### ▶ NEXT SESSION — prioritized next steps (recommended order, all incremental on current vanilla-JS UI)
1. ✅ **In-app Jellyfin playback** — DONE (round 2).
2. ✅ **Watched / progress** — DONE (round 3).
3. ✅ **Full library grid + Continue Watching** — DONE (round 4).
4. ✅ **TV shows (episodes + per-episode resume + Up Next)** — DONE (round 5, item 1 of Plex roadmap).
- **Plex-like roadmap (one item per session):** ⚠ **gated since 2026-09-06** — items 2–5 are now sequenced **after** the modular re-platform (Phase 5), so they get built once on the new structure. See top block; next session = Phase 0 + 1.
  - ✅ **item 1 TV shows** — DONE (round 5).
  - ▶ **item 2 Watch-state polish** — mark watched/unwatched buttons (cards + player), Recently Watched row, play count. **→ lands in the Phase 3 `playback` slice / Phase 5** (post-re-platform).
  - **item 3 Player features** — subtitle/audio-track/speed selectors, quality/transcode picker, player backdrops, autoplay-next.
  - **item 4 Library & discovery** — in-library search, filters/sort (unwatched/newest/type/genre), "Because you watched"/similar.
  - **item 5 Transcode/playback robustness** — Jellyfin transcode fallback + quality picker + auto-open Jellyfin player when direct-play fails.

## ▶ LATEST SESSION (2026-09-02, UI round) — lazy-load grids + smooth hover + in-Plex tick ✅

Frontend-only round (volume-mounted → **live on hard-refresh, no rebuild needed**). `app.js`/`app.css` only; backend + tests unchanged. 216 pytest + phase11/18/25 node green.

**1. Lazy loading (infinite scroll) for all big grids.** Movies, TV Shows, Watchlist and Downloaded now render the first **36** cards and append the next batch via an `IntersectionObserver` on a `#gridMore` sentinel (`rootMargin 900px`, i.e. prefetch just ahead of the viewport) until exhausted. DOM stays light for 296 titles. Genre filter in Movies/TV now **source-filters + re-renders** (was display-toggling, which couldn't work with lazy rendering). Sort/chips in Watchlist still full re-render. Keyboard arrow-nav delegated to `app` so it works on lazy-appended cards too.

**2. Smooth card hover/zoom.** `.card` + `.card img.poster` transitions switched from the snappy default ease to `cubic-bezier(0.22, 1, 0.36, 1)` (0.34s card, 0.55s poster zoom) + `will-change: transform` — lift and pinch now ease smoothly.

**3. In-Plex cards → bright-orange tick + hover actions.** Cards whose title is already in Plex (`state available|downloaded`) now show a **bright-orange circular tick** (top-right, glowing `#ff9500` radial) instead of the old translucent "✓ Available in Plex" text line. On hover the card-actions reveal **Watch on Plex** (gold) + **Trailer** stacked vertically, and the hover buttons got a solid dark blur backdrop + border + shadow so they read cleanly over bright posters. Emby-only cards get a purple Watch-on-Emby substitute. Reused the existing delegated click handling (`data-act=watch-plex|watch-emby|trailer`) — no new event wiring.

**Files:** `app.js` (`cardMarkup` in-Plex branch, `initLazyGrid/lazyAppend/lazyTeardown`, `renderGrid/renderWatchlist/renderDownloaded` lazy + genre re-render, delegated arrow-keynav), `app.css` (hover easings, `.plex-check`, `.card-actions.stacked`, button contrast, `.grid-more`), and regression tests in `tests/phase18_frontend.test.mjs` (in-Plex tick + Watch-on-Plex/Trailer/no-state-text, and not-added→Download).

**Deploy:** none needed for the UI round — `app.js`/`app.css` are volume-mounted. Hard-refresh (Ctrl+Shift+R). Ensure the backend image is current too if you've not run `run-rkm-cinema.ps1` (prod) / `bootstrap.ps1` (bundled) since the SQLite/504 work.

---

## ▶ LATEST SESSION (2026-09-02, follow-up) — Canonical store → SQLite + Suggest fresh-add card bug ✅

**User asked to move the watchlist off `watchlist.json` into a database, and to make it survive rebuilds.** The Phase 3 SQLite seam (spec §5) already existed but was idle; this session activated it and fixed a fresh-add card bug.

**1. Suggest fresh-add card showed no synopsis + no TMDB score (root-caused & fixed).**
`pushSuggestEntryToApp(entryFromWatchlistEntry(resp.entry))` maps the live-added card client-side, but `entryFromWatchlistEntry` read `w.overview` — which the persisted `WatchlistEntry` schema does NOT have (it stores the synopsis under `snippet`/`tmdb_overview`) and set `tmdb_score` (snake_case) while the modal reads `entry.tmdbScore`. So the fresh card's detail modal showed "No synopsis available yet." and no TMDB score. Existing dashboard cards were fine because `rebuild_dashboard.py` normalizes `overview = tmdb_overview || snippet` + camelCase `tmdbScore`.
**Fix (`app.js`, eslint-ok):** `entryFromWatchlistEntry` maps `overview = w.overview || w.snippet || w.tmdb_overview` and sets BOTH `tmdbScore` + `tmdb_score`. **Trailer:** the fresh card carries `trailerId` through (enrich persisted it); the modal `trailerButton` plays in-app if present, else "Search YouTube" fallback. Added regression test `tests/phase25_suggest_frontend.test.mjs`. Frontend is volume-mounted → **goes live on hard-refresh, no rebuild**.

**2. JSON → SQLite migration (activating the existing Phase 3 seam).**
- `.env` (canonical) now sets `WATCHLIST_STORE=sqlite` + `WATCHLIST_DB_PATH=/workspace/media/watchlist.db` — the DB lives on the **shared media volume** (/workspace/media, bind-mounted `:rw`), so `docker compose down`/rebuild no longer loses it (the old risk was the default `/app/watchlist.db`, which sits in the container's throwaway writable layer).
- **`scripts/migrate_json_to_sqlite.py`** (new, idempotent): JSON → SQLite, carries the recommendation seen-set (385 rows) across, round-trip verifies counts, re-exports watchlist.json as a one-time mirror, rebuilds the dashboard. **Ran successfully: 296 pending → SQLite, dashboard rebuilt (296 cards, 274 with trailers).**
- The whole app routes persistence through `build_repository()` (API, `rebuild_dashboard`, `add_watchlist_cron`, jobs, recommendation manager) — a flip requires no code changes; verified the API boots on the SQLite repo (`/api/health` + `/api/config` 200, "Using SQLite watchlist repository").
- **One test made deployment-immune:** `test_repository.test_build_repository_defaults_to_json` now forces an empty `WATCHLIST_STORE` env override (the checked-in `.env` previously carried it to sqlite). No test writes to the real DB — every other suite passes an explicit path.
- **216 pytest + phase11/18/25 node green.**

**⚠️ DEPLOY REQUIRED on RKM-HP** to bake the SQLite store + 504/suggest fixes into the running image:
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\setup-watchlist.ps1
```
The container reads `/workspace/.env` (env_file `../../.env`) and the shared `/workspace/media` volume, so the already-migrated `/workspace/media/watchlist.db` is picked up automatically. Verify `/api/health` 200 + entries still served after deploy.
**Note:** after the flip, `/workspace/media/watchlist.json` is a **frozen mirror** (last exported at migration). External media-stack scripts that read it directly still see pre-flip data until the next export — point them at the repository (or a fresh rebuild) if they must be live.

---

## ⭐ LATEST SESSION (2026-09-02) — 504 root-caused & fixed + Suggest UX round ✅
(previous latest session: 2026-08-28 below)

**Symptom:** `/api/status` + `/api/watchlist` returned **504 Gateway Timeout**; Suggest-search 404'd; the frontend hammered `/api/watchlist` every 15s.
**RCA (measured in-sandbox):** both endpoints ran a full `Reconciler().compute()` (all 292 entries) per request — fresh services each time ⇒ empty TTL caches ⇒ Plex re-scan + *arr lookups. All **155 TV entries are tmdb-only**, and each fired a **live Sonarr `/series/lookup?term=tmdb:<id>`** that TIMED OUT (12s × 3 retries) while indexers were down (AU s115a) ⇒ **58–84s per reconcile** against a 120s nginx window; the 15s poll then saturated the uvicorn threadpool ⇒ 504 everywhere. Suggest 404 = `api/routes/suggest.py` was **untracked** → not baked into the API image.

**Fixes — commit `e69e9f7`:**
- `Reconciler.compute_cached()` — process-level result cache (TTL **300s > 60s poll**, mtime-keyed, cleared on write & on `/media/{id}/request`) now backs `/api/status` + `/api/watchlist`. **Cold 58–84s → ~18s; warm poll 0.02s.**
- Sonarr tmdb→tvdb now via **TMDB `/tv/{id}/external_ids`** (lightweight, cached on disk at `/workspace/media/tmdb_to_tvdb.json`, 140 pre-resolved) instead of the live Sonarr lookup (the timeout source). Unresolved ids match by title+year against the cached Sonarr series list.
- Frontend status poll **15s → 60s** (`app.js`).
- Shipped Suggest (route + app): registered `suggest.router` in `api/main.py`, `POST /api/suggest`, `/api/suggest/add/{tmdb_id}`, `/api/suggest/detail/{tmdb_id}`.

**Suggest UX round — commits `1c8d9b1` (+last 3).** All next-session tasks were taken up this session:
1. ✅ **Search history — retain last 10.** `app.js` persists the last 10 filter sets to localStorage (`rkm_suggest_history`), rendered as clickable "Recent" chips in the Suggest tab (dedupe, most-recent-first).
2. ✅ **Add-to-Watchlist now lands TV as a TV Series.** Adds (Add **and** Download buttons) call `pushSuggestEntryToApp()`, which upserts the title into `DATA.entries` with `type:'tv'`/`isSeries:true` so it appears in the **TV Shows** tab (and Movies/Watchlist) immediately — no longer hidden until a dashboard rebuild. **Full card (not a stub):** `/api/suggest/add` now returns the enriched `entry` (poster, backdrop, genres, trailer, director, cast, imdb, tmdb_score, runtime) which the frontend maps via `entryFromWatchlistEntry()` — so a freshly-added title renders with poster + Trailer button + scores like every other card. From the Suggest UI now **216 pytest + phase11/18/25 node tests green**.

Three changes landed to get the watchlist unstuck (was frozen at 33 pending) and surface richer data:

### 1. Multi-strategy TMDB discover (un-stuck the 33-title plateau)
- **Symptom:** cron kept returning "0 added — all candidates already in Plex" because the generator ONLY ever queried `discover/movie` + `discover/tv` with `sort_by=popularity.desc` → always the same trending titles, which you already own.
- **Fix** (`services/recommendation/generator.py`): new `_DISCOVER_STRATEGIES` rotation — **popular** → **top-rated** → **hidden-gems** → **recent** — picked time-based (`int(time.time()) % 4`), so consecutive runs pull from different slices of the catalog. `_discover_tmdb` applies each strategy's `sort_by` + vote filters; strategy is logged.
- **Thresholds lowered** (`config/recommendations.yaml`): movies TMDB 7.5→**7.0**, IMDb 7.5→**7.0**, RT 80→**75**; series TMDB 7.5→**7.0**, IMDb 8.0→**7.5**, RT 85→**80**.
- **Result:** 33 → 47 pending (14 added in first run, tv-heavy because of rotation + ownership overlap; NOT a movies-are-blocked bug). **212 tests green.**

### 2. IMDb score for every title (was TMDB-only)
- Live entries had `imdb: 0.0` because TMDB discover carries no IMDb rating.
- **Fix:**
  - `services/tmdb.py` — detail calls now `append_to_response="...,external_ids"`, so `get_movie_details`/`get_show_details` return the IMDb id. New **`get_imdb_rating(imdb_id)`** (cached, OMDb free tier via `www.omdbapi.com`).
  - `services/recommendations.py` `enrich_metadata` — when TMDB yields an IMDb id, fetch + set `entry.imdb` (optional enrichment; gracefully skips failures/Mocks).
- **Result:** batch-enriched all 47 pending → **46 have IMDb scores** (1 missing: 2026 Avatar, no IMDb page yet). **212 tests green (incl. a Mock-guard update in `test_e2e_recommendation.py`).**

### 3. Plex dedup gap — owned titles could still be auto-added (fixed)
- **Symptom:** user flagged "The Dark Knight is already in my movies" after an auto-add — it (and 2 others) slipped through the Plex gate.
- **Root cause, two bugs in the matcher:**
  1. `services/library/plex.py` — the fuzzy subtitle fallback was **gated to title-only candidates** (`if not (identity.imdb_id or identity.tmdb_id)`). An id-bearing candidate whose Plex item exposes **no provider ids** AND has a title variant (`Batman: The Dark Knight` vs `The Dark Knight`) was treated as absent.
  2. `services/plex.py` `matches()` — strict year check (`if year is not None and self.year != year`) rejected a title match when the Plex item's year is **unknown (`0`)** (Dark Knight's Plex record has year=0 → failed vs candidate 2008).
- **Fix:** fuzzy substring fallback now runs for **any** candidate still having a title after the O(1) id + exact-title lookups miss (genuine last resort); `matches()` only rejects on year when the Plex item's year is actually **known** (`self.year != 0`). Applied to both `PlexMovie` and `PlexShow`.
- **Result:** The Dark Knight now correctly resolves to Plex `Batman: The Dark Knight`. Removed the 3 wrongly-added owned titles (**The Dark Knight, Avatar Aang 2026, Disclosure Day 2026**). Swept all pending — remaining 52 are legitimately new. **212 tests green.**

### Note — cron wrapper count
The auto-add job `1965aeb4af2e` is **`no_agent`** → it runs the shell wrapper `~/.hermes/scripts/rkm_watchlist_auto_add.sh` (NOT the Hermes prompt). The wrapper hardcodes `--count 20`; the strategy/threshold/dedup changes take effect there automatically (they're in the .py/.yaml it imports), but **`--count 30` would need a wrapper edit**. Cron schedule shown as `0 6 * * *` (daily 06:00 AEST).

## ▶ AUTO-ADD WATCHLIST CRON (2026-08-25) ✅ live

**Goal (user):** a scheduled job that picks movies/shows by criteria and adds them to the watchlist, using **Plex as source of truth** so owned titles are never re-added. Only **pending** watchlist entries are created — *no downloads* (user still approves Radarr/Sonarr in the UI).

**Mechanism:** reuses the Phase 12/13 refactor — `RecommendationManager` (TMDB discover → criteria → Plex gate → watchlist gate → history gate → rank) + `DailyWatchlistJob`. New **`scripts/add_watchlist_cron.py`** wires the manager with the Plex-backed `LibraryService` explicitly (the job's default manager has no library gate), runs the job, rebuilds the dashboard, prints a before/after summary. Backed by cron job **`1965aeb4af2e`** (Hermes, `no_agent`, weekly **Mon 09:00 AEST**, deliver=origin) → wrapper `~/.hermes/scripts/rkm_watchlist_auto_add.sh`.

- Usage: `python3 scripts/add_watchlist_cron.py [--count N] [--dry-run]`.
- Plex-gated: runs from sandbox against `PLEX_URL=192.168.65.254:32400` + `PLEX_TOKEN`; aborts if Plex unconfigured. TV dedup relies on title+year fallback (Plex show `provider_ids()` are `{}` — no external tmdb in the raw scan).
- **4 defects fixed** to make TMDB-discover actually work (commit `2f32130`, 210 green):
  1. `services/recommendation/generator.py` — `self._tmdb` **attr shadowed the `_tmdb()` method**, so the default (no injected tmdb) crashed "NoneType not callable". Renamed `_tmdb_injected`.
  2. `generator._discover_tmdb` — maps TMDB numeric `genre_ids` → **names** (new cached `TMDBService.genre_names()`) so name-based criteria (`exclude: ["horror"]`) fire on the TMDB path.
  3. `services/recommendation/criteria.py` — IMDb/RT anchor is now **skipped when both scores are unknown (0)**, the TMDB-discover case; TMDB rating gates alone. Keeps the curated IMDb/RT bar when scores are present (config unchanged).
  4. tmdb-only acceptance: `RecommendationService._validate_entry` requires a canonical id (**imdb OR tmdb**, not both); `check_watchlist_duplicate` + `WatchlistService.add_pending` dedup by either canonical id; `Candidate` + `verify_quality_gate` + `jobs/daily_watchlist._to_legacy_candidate` now carry `tmdb_score`/`vote_count`.
- **Manual live run occurred 2026-08-25** (during wrapper testing — NOT a pre-approved live run): added **15 titles** to the real watchlist as pending (7 films incl. recent 2026 release like Avatar Aang/Toy Story 5/Odyssey; 8 series incl. Rick & Morty, Grey's Anatomy, Simpsons, NCIS, CSI). Watchlist now **32 pending** (17 prior + 15 new). Plex gate skipped 10 owned. **Reversible** — remove pending tmdb ids if unwanted.

### Operations
- **Dry-run preview (no writes):** `cd /workspace/projects/rkm-cinema && python3 scripts/add_watchlist_cron.py --dry-run`
- **Live write:** `python3 scripts/add_watchlist_cron.py --count 20` (adds pending + rebuilds dashboard; runs against `/workspace/media/watchlist.json`)
- **Cron:** Hermes job `1965aeb4af2e` (weekly Mon 09:00 AEST). Pause/remove via cron. Wrapper at `~/.hermes/scripts/rkm_watchlist_auto_add.sh`.

---

## ▶ LATEST SESSION (2026-08-25) — Phase 17 API-test/§31 consolidation ✅

**Driving spec:** `RKM_Watchlist_Production_Refactor_Task.md` §31 (Phase 17) — API tests. **Before: 205 backend + 16 frontend green. After: 208 backend + 16 frontend green** (+3 in `tests/test_resource_api.py`). Test-only change; **no redeploy needed** (frontend volume-mounted, backend image unchanged — test files aren't shipped).

### §31 audit result
The §31 endpoint matrix was almost fully covered already by `test_resource_api.py` + `test_api.py`: `GET/POST /api/media/{id}`, `/api/watchlist`, `/api/reconcile`, `/api/jobs`, `/api/quality`, `/api/health` + the behavior asserts (AVAILABLE→can_download false, NOT_REQUESTED→can_download true, watch links exposed). The **one endpoint with zero coverage was `GET /api/library`**. Added 3 tests driving its Plex→Emby→partial fallback chain:

1. `test_library_plex_primary_success` — Plex healthy → full §18 Plex view (counts/recents/urls).
2. `test_library_plex_fail_falls_back_to_emby` — Plex down → Emby fallback, **200** with Emby counts.
3. `test_library_both_providers_fail_is_partial_not_error` — the §31 **"provider failure → partial response"** assert at API level: both providers down → **200 `provider=None available=False`**, never a 5xx (spec §28).

Fakes mock the provider boundary exactly (`PlexLibraryProvider` reaches `service.providers()` — a **method** returning a copy of `_providers`, not a bare attribute — and `provider._plex.get_library_counts()`/`runner._browser_base()`). No LAN, no keys.

### Next
**Phase 18 — Frontend tests/manual verification (spec §32)**: audit the Node suite against the §32 card-state matrix (NOT_REQUESTED/REQUESTED/DOWNLOADING/DOWNLOADED/AVAILABLE renders, can_download-gated Download button, plex/emby-gated buttons, **double-click Download → no duplicate request**). Then Phase 19 observability (§33), Phase 20 config cleanup (§34), Phase 21 frontend API boundary (§35), Phase 22 remove legacy duplication (§36).

---

## ▶ LATEST SESSION (2026-08-25) — Phase 16 testing/§30 consolidation ✅

**Driving spec:** `RKM_Watchlist_Production_Refactor_Task.md` §30 (Phase 16) — test requirements. **Before: 201 backend + 16 frontend green. After: 205 backend + 16 frontend green** (+4 in `tests/test_status.py` + `tests/test_recommendation_engine.py`). Test-only change; **no redeploy needed** (frontend volume-mounted, backend image unchanged — test files aren't shipped).

### §30 audit result
The spec's domain/identity/request/recommendation/watch-link test matrix was **already ~90% covered** by suites added across Phases 4–15 (a deliberate Phase 16 design: the tests came *with* the code). Audited each required case and found **3 genuine gaps**, all closed:

1. **Domain combos** (§30 "library available + downloading/requested → AVAILABLE"): `resolve_status` short-circuits on `in_plex` for every case, but no test pinned the two explicit combos. Added `test_library_wins_over_downloading` (in_plex + qbit_active → AVAILABLE, not DOWNLOADING) and `test_library_wins_over_requested` (in_plex + arr record → AVAILABLE, not REQUESTED).
2. **Watch link, Emby-only** (§30 "Plex link failure + Emby success → Emby button only"): only "Plex failure still AVAILABLE" was tested. Added `test_emby_button_only_when_plex_link_fails` — asserts AVAILABLE is preserved (spec §10: capability problem, never a state downgrade) with `plexUrl=""` and `embyUrl` intact.
3. **Recommendation watchlist exclusion** (§30 "already in watchlist → excluded"): the manager has a `watchlist_duplicates` counter but no test exercised it. Added `test_watchlist_exclusion` (candidate with `imdb_id` already pending → `watchlist_duplicates == 1`, `new_recommendations == 0`).

### Notes
- **Naming:** §30 writes the "nothing" state as `NOT_REQUESTED`; the codebase enum is `NOT_ADDED` (consistent since Phase 4, consumed by the resource API + frontend). Same state, different label — **no rename** to avoid churn across API/frontend. Documented in PROGRESS.
- Existing §30 cases confirmed present: domain available/downloading/requested/nothing + watch-link-availability (`test_status.py`); all identity forms (`test_identity.py`); request suite (`test_request_media.py`); rec pass/fail-rating/fail-genre/in-library/in-history/dup (`test_recommendation_engine.py`); Plex-match + Emby-match links (`test_watch_links.py`).

### Next
_Led into Phase 17 (now done). See the top-of-file Phase 17 block for the current next step._

---

## ▶ LATEST SESSION (2026-08-22) — refactor Phase 9 ✅ (idempotent request command)

**Driving spec: `RKM_Watchlist_Production_Refactor_Task.md`** §15 (Phase 9). THE checklist / §42 order / audit at `ARCHITECTURE_AUDIT.md`. **Baseline before: 117 green. After Phase 9: 128 green** (+11 in `tests/test_request_media.py`, all earlier suites untouched).

### What was built
- **`application/`** — new application (use-case) layer.
- **`application/commands/request_media.py`** — the idempotent request command (spec §15):
  - `RequestMediaCommand.run(media_id, *, title, year)` orchestrates the full §15 flow through the canonical services: parse identity → **re-check library (AVAILABLE, §1.2 library-always-wins)** → **check existing acquistion (ALREADY_REQUESTED)** → **route via `AcquisitionService` + request** → map outcome. No caller knows Radarr vs Sonarr.
  - `RequestMediaResult` dataclass with the exact spec §15 vocabulary: `state` ∈ {AVAILABLE, ALREADY_REQUESTED, REQUESTED, AMBIGUOUS, NOT_CONFIGURED, PROVIDER_UNAVAILABLE} + `success` property + `candidates`/`item` for disambiguation.
  - **Idempotent** — repeated requests hit the ALREADY_REQUESTED guard (or AVAILABLE) and never double-write.
  - `persist=` hook (callable(media_id, provider, state)) for acquisition-state persistence — decoupled so DB wiring lands in Phase 10/13 without changing the command; failures don't break the request.
  - Legacy `plex=`/`radarr=`/`sonarr=` DI args wrapped in providers (§43); new canonical `library=`/`acquisition=` params. Module-level `request_media()` convenience.
- **`domain/enums.RequestMediaState`** — the canonical §15 outcome enum.

### Tests (11 new)
- AVAILABLE when in library; ALREADY_REQUESTED when *arr already holds it; REQUESTED on success (movie→radarr, series→sonarr); AMBIGUOUS; PROVIDER_UNAVAILABLE; NOT_CONFIGURED (no provider / unparseable id); idempotency (no double write); persist hook invoked on REQUESTED; module convenience fn.

### Remaining
- **Phase 18 next — Frontend tests/manual verification** (spec §32): verify each card state (NOT_REQUESTED/REQUESTED/DOWNLOADING/DOWNLOADED/AVAILABLE) renders; Download button only when can_download; Plex button only when Plex link available; Emby button only when Emby link available; **double-click Download creates no duplicate request**. The Node-based frontend suite (`tests/phase11_frontend.test.mjs`, 16 green) already asserts the capability-driven branching + legacy fallback — audit the remaining §32 card-state renders and idempotent-download asserts against it, add what's missing. Then Phase 19 observability (§33 structured logging), Phase 20 config cleanup (§34), Phase 21 frontend API boundary (§35), Phase 22 remove legacy duplication (§36).
- The **scheduler is built + wired** (Phase 14) but **off by default** — to enable the container job loop set `WATCHLIST_SCHEDULER=true` in `.env` (plus `RECONCILE_INTERVAL_MIN`, `DAILY_JOB_HOUR`). The existing host cron (`scripts/daily_recommendations.py`) still runs; it now coexists until you flip to the in-container loop (spec §40 prefers container jobs).

---

## ▶ POST-DEPLOY USER-TESTING (2026-08-22) — 2 bugs found & fixed ✅

Phases 10+11 deployed → user tested adding titles live. Two backend bugs surfaced and fixed (both reproduced against the real stack from the sandbox before the fixes were committed).

### Bug 1 — API down after first Phase 10/11 redeploy (502 on every `/api/*`)
- **Symptom:** after `.\setup-watchlist.ps1`, "API not reachable — check 'docker compose logs api'"; all `/api/*` returned 502; UI showed "Download failed — Retry" for **any** title (not Ex Machina specifically). Frontend loaded (200) because it's volume-mounted; only the API was down.
- **Root cause:** the **`Dockerfile` did not `COPY application` or `COPY infrastructure`** — it only copied `api/ services/ domain/ core/ config/`. Phase 10/11 routes import `application.commands.request_media` (`api/routes/media.py`) and `infrastructure.database.repository` (`api/routes/jobs.py`) **at module load**, so uvicorn died at import (`ModuleNotFoundError: No module named 'application'`) → never bound :8000 → nginx 502. Old image predated these routes, so it only broke on the first build that included them.
- **Fix (commit `2c3cbed`):** added `COPY infrastructure /app/infrastructure` + `COPY application /app/application`. Verified by simulating the container build context (import + boot + `/api/health` `/api/jobs` `/api/reconcile` all 200).
- **Pitfall recorded** in the rkm-watchlist skill: **whenever a route imports a new top-level package, add the matching Dockerfile COPY line.** Sandbox tests pass (dirs exist locally) while the deployed image 502s — reproduce by copying only the Dockerfile's dirs to a temp dir and importing `api.main`.

### Bug 2 — "No Radarr match for imdb:" on There Will Be Blood
- **Symptom:** specific title failed to add; message "no radarr match for imdb".
- **Root cause:** canonical `media_id` is **tmdb-preferred** (`movie:tmdb:7345`), so `request_media` builds an identity with **`imdb_id=None`**. But `RadarrAcquisitionProvider.request` / `add_movie` only ever looked up **by IMDb id** (`identity.imdb_id or ""` → empty string) → empty `imdb:` lookup → no result; title-search fallback also had no title → "No Radarr match". Radarr itself resolved fine by both `imdb:tt0469494` and `tmdb:7345` (verified live) — the bug was the lookup call, not Radarr.
- **Fix (commit `072f46a`):** added `lookup_movie_by_tmdb()` / `lookup_series_by_tvdb()`; `add_movie()`/`add_series()` now accept `tmdb_id`/`tvdb_id` and resolve by TMDB/TVDB when there's no IMDb id (the canonical case), before the title fallback. Closes a quiet §43 inconsistency too (`find()` already used tmdb/tvdb; `request()` only used imdb).
- **Regression tests (2)** in `tests/test_acquisition.py` (tmdb-only movie, tvdb-only series) → **145 green**. **Live-verified** against real Radarr: `movie:tmdb:7345` → *"There Will Be Blood added to Radarr — download starting"*.
- **Outcome:** user re-deployed, tested, and confirmed **working as intended**. No further reports.

---

## ⚡ NEXT SESSION — RESUME EXACTLY HERE (Phase 17 done, next Phase 18)

**Do NOT skip ahead (§42; §43.3 no parallel implementations; §43.7 keep `pytest` green after every phase).**

1. ✅ **Phase 5 — Watch links** (**DONE**, commit `5eb55c9`). 92 green.
2. ✅ **Phase 6 — Canonical status resolver** (**DONE**, commit `bdd4c07`). 103 green.
3. ✅ **Phase 7 — Reconciler** (**DONE**). `services/reconciliation/reconciler.py` → `MediaSnapshot`; `api/routes/status.py` consumes snapshots. 109 green.
4. ✅ **Phase 8 — Acquisition abstraction** (**DONE**). `AcquisitionService` single router; Reconciler + DownloadService rewired. 117 green.
5. ✅ **Phase 9 — Idempotent request command** (**DONE**, commit `f438be3`). `request_media` → `RequestMediaResult`; idempotent guards. 128 green.
6. ✅ **Phase 10 — Resource API** (**DONE**, commit `478278f`). `GET /api/media/{id}` + `POST /api/media/{id}/request` + `/api/watchlist` + `/api/reconcile` + `/api/jobs`; §18 resources; `config`/`health`/`quality` off direct Radarr/Sonarr → `AcquisitionService`; `list_job_runs()`/`record_job_run()`. 143 green.
7. ✅ **Phase 11 — Frontend capability-driven** (**DONE**, this session) — `app.js`/`api.js` render off the §18 resource's `status` + `capabilities{can_download,can_watch}` + `watch.{plex,emby}.available`, **never** `if movie.radarr/plex` (spec §19/§20); NEVER shows Download when AVAILABLE. Primary data path = `/api/watchlist`; request path = `POST /api/media/{id}/request`; `_applyRequestResult` optimistic RES patch. `api.js` added `mediaIdOf()`/`legacyStatusToResource()` + resource methods. **Graceful legacy fallback** to `/api/status`+`/api/download` when new endpoints 404 (old image). `MediaResponse` gained `speed/eta/qbitState/qbitName` so §20 progress detail survives the resource path. Node-based frontend test `tests/phase11_frontend.test.mjs` (16 assertions: AVAILABLE→Watch never Download, capability/watch branching, legacy fallback). **Backend 143 green + frontend 16 green**.
8. ✅ **Phase 12 — Recommendation engine** (**DONE**, this session, commit `a70fb57`) — `services/recommendation/{criteria,generator,ranker,manager}.py`; criteria in `config/recommendations.yaml` (spec §22, config not Python); `CriteriaEngine.evaluate() -> CriteriaResult{passed, score, reasons}`; `CandidateGenerator` (TMDB discover + DI source_fn); `rank()` by score; `RecommendationManager` pipeline (normalize → criteria → dedupe → library → watchlist → history → rank → persist) → §25-shape result, idempotent. Repository `record_recommendation()`/`list_recommendation_history()` on the SQLite `recommendations` table (spec §23, idempotent UPSERT). Legacy `RecommendationService` gates now delegate to the CriteriaEngine (BC shim §43). PyYAML added to requirements. **160 green** (+15 in `tests/test_recommendation_engine.py`).
9. ✅ **Phase 13 — Scheduled jobs** (**DONE**, this session, commit `ec2537a`) — `jobs/base.py` (`JobRunner` records every run to the `job_runs` table, success AND error visible — spec "job execution is recorded"/"failures visible"), `jobs/daily_watchlist.py` (`DailyWatchlistJob` feeds the Phase 12 `RecommendationManager` then adds survivors to the watchlist, idempotent, §25-shaped counts), `jobs/reconcile.py` (`ReconcileJob` → `Reconciler.compute()` tallies statuses, NO new recs — spec §26). `POST /api/jobs/{name}/run` stable command route (thin Route → job, 404 unknown; spec §40 host cron calls a stable command). Dockerfile `COPY jobs`. **168 green** (+8 in `tests/test_jobs.py`).
10. ✅ **Phase 14 — Health / partial failure + scheduling** (**DONE**, this session, commit `11d8484`) — typed per-service errors in `core/exceptions.py` (Plex/Emby/Radarr/Sonarr/QBittorrent/TMDB Unavailable + AmbiguousMedia + MediaNotFound; one failed service never destroys the response — spec §28). `core/http_client.py` real retry + exponential backoff (GET: network+5xx, POST: network only). `services/health.py` `HealthChecker` — canonical per-service structured health (`configured/ok/detail/error`) + `degraded` flag, DI-injectable; `/api/health` thin route keeps BC `services` bool map AND adds `serviceDetail` + `degraded`. `jobs/scheduler.py` opt-in in-container job loop (frequent reconcile at `RECONCILE_INTERVAL_MIN` + daily job at `DAILY_JOB_HOUR`) wired from app startup under `WATCHLIST_SCHEDULER=true` (default off), each run via JobRunner → job_runs. **183 green** (+15 in `tests/test_health_and_scheduler.py`).
| 11. ✅ **Phase 15 — Caching** (**DONE**, commit `54b9d53`). `core/cache.py` `TTLCache` (monotonic TTL, invalidate/clear, thread-safe) — the ONE cache primitive (§43). `TMDBService` metadata long-TTL cache (`config.TMDB_CACHE_TTL`, default 6h; movie/show details + searches). Emby scan TTL corrected 300s→**60s** (`EmbyLibraryProvider.EMBY_SCAN_TTL`). *arr write-path invalidation fixed: `add_movie`/`add_series` now clear the URL-keyed `_http_cache` too (was left stale up to 45s) via `_invalidate_after_write()`; new `clear_cache()`. `invalidate()` hoisted: `LibraryProvider`/`AcquisitionProvider` ABCs (no-op default → fake-safe) + concrete Plex/Emby/Radarr/Sonarr providers + `LibraryService.invalidate()` + `AcquisitionService.invalidate()` + `Reconciler.invalidate()`; `request_media` invalidates acquisition after a successful write. **201 green** (+18 in `tests/test_caching.py`).
| 12. ✅ **Phase 16 — Testing/e2e consolidation** (**DONE**, commit `17d4acf`). **205 green** (201 backend + 4 new in `test_status.py` + `test_recommendation_engine.py`, frontend 16 green). Spec §30 audit: most cases already existed from Phases 4–15; closed 3 real gaps — (a) domain: **in-library + active qBittorrent → AVAILABLE** (`test_library_wins_over_downloading`) and **in-library + *arr record → AVAILABLE** (`test_library_wins_over_requested`), the explicit §30 "library available + downloading/requested" combos; (b) watch-link: **Plex link failure + Emby success → AVAILABLE carries ONLY the Emby button** (`test_emby_button_only_when_plex_link_fails`, spec §10 capability-not-state); (c) recommendation: **already-on-watchlist → excluded** (`test_watchlist_exclusion`, exercises the `watchlist_duplicates` counter). §30 domain/identity/request/rec/watch-link matrix now fully covered (NOT: the codebase enum is `NOT_ADDED`, which §30's wording calls "nothing → NOT_REQUESTED" — same state, different label; no rename so resource API/frontend stay stable).
| 13. ✅ **Phase 17 — API tests** (**DONE**, commit `14ba4b2`). **208 green** (205 + 3 new in `test_resource_api.py`, frontend 16 green). Spec §31 audit: media/request/watchlist/reconcile/health endpoints + the AVAILABLE→can_download false, NOT_REQUESTED→can_download true, watch-links-exposed asserts were already covered by `test_resource_api.py` + `test_api.py`. The one endpoint gap was **`GET /api/library`** — added 3 tests driving its Plex→Emby→partial fallback chain: `test_library_plex_primary_success` (Plex healthy → full Plex §18 view, counts/recents/urls), `test_library_plex_fail_falls_back_to_emby` (Plex down → Emby fallback, still 200 with Emby counts), `test_library_both_providers_fail_is_partial_not_error` — the §31 "provider failure → partial response" assert at API level (both providers down → **200** `provider=None available=False`, never a 5xx; spec §28). Fakes mock the provider boundary (no LAN); exercised `service.providers()` (note: a method returning a copy of `_providers`, not an attribute).
14. ✅ **Phase 18 — Frontend tests/manual verification** (**DONE**, this session) — **16 green**.

---

## ⚡ HOW TO PICK UP WORK HERE (pre-refactor context, superseded for the refactor task)

- **Current refactor source of truth = `RKM_Watchlist_Production_Refactor_Task.md` + `ARCHITECTURE_AUDIT.md`** (this). For the *current live modular backend*, `ARCHITECTURE.md` is the up-to-date map. The **old two-API-layer split is GONE**: the monolithic `api.py` is archived (`archive/api_legacy_monolith.py`) and the live backend is **`uvicorn api.main:app`**. Edit the modular tree — `api/routes/*` (thin), `services/*` (business logic), `domain/*` (state machine + media-type resolver), `infrastructure/database/*` (persistence).
- **Adding a feature** → follow ARCHITECTURE.md §12 ("Adding a feature").
- **Quick checklist:** backend change → edit `api/routes/*` + `services/*` (+ `domain/*` for rules, `infrastructure/database/*` for persistence), then `python -m pytest tests/ -q` (must stay green), then `scripts/rebuild_dashboard.py`, then deploy `.\setup-watchlist.ps1`. Frontend (`api.js`/`app.js`/`app.css`) is volume-mounted — no rebuild needed for UI-only changes.
- **Secrets** live in `/workspace/.env` (canonical). `.env` is git-ignored; use `.env.example` as the template. **Never commit real keys.**

## Latest session (2026-08-21) — curated batch of 8 added ✅

- **Scope:** solid curated batch (movies + series), verified live, added to pending + dashboard rebuilt. User picked this.
- **Ownership gate:** pulled Plex ground truth — **774 movies (incl. 132 kids) + 100 shows** (section keys: Movies 13, Kids 19, TV Shows 15). Candidates were deduped against this BEFORE selection. Many popular titles (Interstellar, Dune Pt2, Parasite, Whiplash, Chernobyl, Severance, Beef already-in-pending, etc.) rejected as owned.
- **Batch added (8):** Knives Out(tt8946378), Blade Runner 2049(tt1856101), Ex Machina(tt0470752), There Will Be Blood(tt0469494) [4 films] + The Expanse(tt3230854), Shōgun(tt2788316), Ozark(tt5071412), Scam 1992(tt12392504) [4 series, Hindi]. → **17 pending total (10 movies / 7 series).**
- **Scores live-verified** via r.jina.ai (IMDb) + RT direct/aggregate (BR2049=88, Shōgun=94, Expanse=85, Ozark=86, Knives=92, ExMachina=86, TWBB=86; Scam 1992 IMDb 9.2, not on RT → rt:0). All pass gates (OR).
- **All 8 TMDB↔IMDb IDs cross-verified OK** (Radarr/Sonarr lookups will resolve). Posters + trailerIds live-validated (HTTP 200 image/*).
- **Wrote via atomic tmp+os.replace, deduped by imdbId, validated pending[].** Rebuilt dashboard → live `:8123` already serves 17 (volume-mounted, no redeploy needed).
- Remaining entry-level gap: **The Night Agent (rt 74 / imdb 7.0) still in pending** — breaks the series gate (needs RT≥85 OR IMDb≥8.0); pre-existing, flag to user if they act on it.

## Latest session (2026-08-21) — Watch-Now links fix (2 backend bugs) ✅ verified live

**Symptom:** page showed "Download" on titles already in the Plex library instead of Watch links.
**Root cause:** `/api/status` **timed out at 30s+**, so the frontend never received `available` state → fell back to Download. The UI already renders Watch Now/Plex/Emby for `available`; it was the backend that never answered.

Two compounding backend bugs (modular API, both deployed):
1. **No Plex library caching** — `PlexService.get_all_movies()/get_all_shows()` did a FULL Plex scan (774→790 movies + 100 shows) on **every entry**. `/api/status` calls `has_media` on all 17 pending → 17 full rescans → blew the window. `_library_cache` was declared but never used. **Fix:** wired it up with a 60s TTL (first scan ~1.3s, cached ~0.2s; full status pass 4.8s). Committed `820f772`.
2. **Sonarr None crash** — for unmatched TV entries, `stats = rec.statistics` ran even when `rec is None` → `AttributeError`. **Fix:** `getattr(rec, "statistics", None) or {}`. Committed `3d50b4b`.

**Verified against LIVE services from sandbox:** 17 entries resolved in 4.8s → 2 downloading / 8 available / 7 not_added. Available titles carry correct deep links (`app.plex.tv/.../7780f377...` + Emby `#!/item?id=…`). Tests: 39 pass (ignoring fastapi-only modules).

**⚠️ DEPLOY REQUIRED on RKM-HP** to ship both fixes into the running image:
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\setup-watchlist.ps1
```
Then hard-refresh the page (Ctrl+Shift+R). Verify `/api/status` returns <5s and owned titles show Watch Now instead of Download.

## Latest session (2026-08-21) — Watch deep-links fixed to point at server web UI ✅

**Symptom:** Plex/Emby Watch links "don't open anything."
**Root cause:** Plex deep-links pointed at **`app.plex.tv`** (Plex's cloud app) which requires account login + remote relay and rarely auto-opens the item. Also `plexKey` was set to the full URL instead of the numeric ratingKey. Emby already deep-linked into the local server's web UI correctly.
**Fix (commit `ecf4b58`):**
- **Plex links now point at the server's OWN web UI** on the browser-reachable Tailscale HTTPS host: `https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html#!/server/{machineId}/details?key=/library/metadata/{ratingKey}` — **raw path, not `%2F`-encoded** (encoding broke Plex's hash router). Same idea Emby already uses. No cloud relay.
- **plexKey** now carries the numeric ratingKey (`320819`), not a URL.
- **Config-driven browser endpoints:** new optional `PLEX_BROWSER_URL` / `EMBY_BROWSER_URL` in `.env`; default safely to the Tailscale host (browser-reachable) even unset. LAN `PLEX_URL`/`EMBY_URL` (backend/API) are NOT used for deep links.
- `api/routes/library.py` hardcoded `app.plex.tv` + Emby URL cleaned up to the same config-driven builder.
- **New regression tests `tests/test_watch_links.py`** (7) + 2 library-cache tests in `test_plex_ownership.py` → **46 pure-logic tests pass**. Asserts: no app.plex.tv, raw `/library/metadata/`, numeric plexKey, Tailscale default fallback, search fallback, cached-scan reuse.
- **Live-verified:** available titles now emit `https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html#!/server/7780f…/details?key=/library/metadata/320819` (web UI HTTP 200) + Emby item links.

**⚠️ DEPLOY REQUIRED on RKM-HP** (same as above): `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema; .\setup-watchlist.ps1`, then hard-refresh.
**Optional .env addition (not required — defaults work):** `PLEX_BROWSER_URL=https://rkm-hp.tail8d5e8.ts.net:32400` and `EMBY_BROWSER_URL=https://rkm-hp.tail8d5e8.ts.net:8096` if you want them explicit.

## ⚡ HOW TO PICK UP WORK HERE

- **Start with `ARCHITECTURE.md`** — it's the up-to-date map. The **old two-API-layer split is GONE**: the monolithic `api.py` is archived (`archive/api_legacy_monolith.py`) and the live backend is now the **modular FastAPI app** (`uvicorn api.main:app`). Edit the modular tree — `api/routes/*` (thin), `services/*` (business logic), `domain/*` (state machine + media-type resolver). There is exactly ONE implementation of each rule.
- **Adding a feature** → follow ARCHITECTURE.md §12 ("Adding a feature").
- **Quick checklist:** backend change → edit `api/routes/*` + `services/*` (+ `domain/*` for rules), then `python -m pytest tests/ -q` (must stay green), then `scripts/rebuild_dashboard.py`, then deploy `.\setup-watchlist.ps1`. Frontend (`api.js`/`app.js`/`app.css`) is volume-mounted — no rebuild needed for UI-only changes.
- **Secrets** live in `/workspace/.env` (canonical). `.env` is git-ignored; use `.env.example` as the template. **Never commit real keys.**

## Latest session (2026-08-21) — production-grade refactor ✅

**Goal:** eliminate the two-backend problem and make the modular architecture the single source of truth.

- **Domain layer added (`domain/`):** `enums.py` (`MediaType`, `MediaStatus`, `DownloadResultState`), `models.py` (`DownloadResult`), `state_machine.py` (`resolve_status()` — the ONLY availability resolution: Plex→available, *arr hasFile→downloaded, qBittorrent→downloading, *arr record→requested, else not_added), `resolver.py` (`resolve_media_type()` — single movie/tv resolver).
- **Services stabilized (DI):** all services now accept injectable `config`/`http` (testable, no real LAN). Extracted **`QBittorrentService`** and **`MediaStatusService`** from the fat status route.
- **Routes thinned:** `status.py` delegates to `MediaStatusService`; `download.py` delegates to new **`DownloadService`** (routing + add + title-fallback + cross-service fallback + "pick one" ambiguity → typed `DownloadResult`). Added **`/api/plex/thumb`** route (via `PlexService.get_thumb`) so modular cutover doesn't break thumbnails.
- **Fixed latent bugs found by tests:** `UnboundLocalError` in both `RadarrService.add_movie` & `SonarrService.add_series` when no quality-profile override set; silent-guess ambiguity now returns **`ambiguous`** instead of picking a wrong title; `WatchlistService.update_status` to `recommended` now moves the entry out of pending into history.
- **Docker migration (Phase 5):** `Dockerfile` now copies `api/ services/ domain/ core/ config/` + `requirements.txt` and runs **`uvicorn api.main:app`**. `WatchlistService` auto-resolves `/app/watchlist.json` (container) vs `/workspace/media/watchlist.json` (sandbox). Verified the copied Docker tree imports and exposes all 8 endpoints.
- **Frontend (Phase 7):** new **`api.js`** centralized API client (`API.getJSON/getStatus/download/...`); `app.js` delegates all `/api/*`+`/dashboard-data.json` calls to it. `api.js` wired into `index.html` + `dashboard.html`. No rendering/behavior change.
- **Legacy removed (Phase 6):** `api.py` → `archive/api_legacy_monolith.py` (+ `archive/README.md`).
- **Tests: 47 passing, all mockable (no live LAN):** domain state machine, media-type resolver, Radarr/Sonarr routing + title fallback + ambiguity, download status, error handling, Plex ownership, duplicate prevention, trailer validation, recommendation pipeline, and API endpoints (`tests/test_api.py`).

**⚠️ DEPLOY REQUIRED:** all of the above is committed but the running site is still the OLD monolithic image. Run `.\setup-watchlist.ps1` on RKM-HP to build & start the modular backend (`uvicorn api.main:app`). Then verify `/api/health`, `/api/config`, `/api/status`, `/api/library`, `/api/plex/thumb`, download flow, and Plex/Emby watch buttons per ARCHITECTURE.md §11.

---

## Previous sessions

## Latest session (2026-08-20) — 9 fixes

### 8f. Emby links — HTTPS scheme fix ✅
- **Bug:** Emby deep links were built with `http://`, but the Tailscale Emby server is **HTTPS-only** — so clicking returned "Client sent an HTTP request to an HTTPS server" (400). Confirmed: `http://rkm-hp.tail8d5e8.ts.net:8096` → 400, `https://...` → 200.
- **Fix:** all Emby URL builders (legacy `api.py` `_emby_url_for`, library `urls.emby`, modular `services/plex.py` `emby_url_for`, `api/routes/library.py`) now use `https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html`. Verified: Banshees → `https://.../#!/item?id=67719&serverId=b54476...`.

### 8e. Emby Watch buttons — fixed deep-link format ✅
- **Bug:** Emby watch buttons used the search path `#!/search/<title>`, which doesn't deep-link to the item. The correct format is `#!/item?id=<itemId>&serverId=<serverId>`.
- **Fix:** backend now resolves the Emby **item id** for a title (via `/Users/<id>/Items?searchTerm=...`) and the **server id** (`/System/Info/Public` → `b54476cfb9054f389fcc0ce450f17c60`), then builds `#!/item?id=<id>&serverId=<sid>`.
- **Verified** for The Banshees of Inisherin → `#!/item?id=67719&serverId=b54476...`, exactly matching the URL Plex/Emby generates when you click the movie. Applies to legacy `api.py` (`_emby_url_for`, library `recent[]`), modular `services/plex.py` (`emby_url_for`/`_emby_item_id`/`_emby_server_id`), and frontend `libraryCard()` (uses backend-provided `embyUrl`).
- Note: Plex-library recents that are *seasons* resolve to the parent series item id in Emby (e.g. id 38373) — acceptable; movie/series top-level items resolve correctly.

### 8d. Plex is the source of truth for status ✅
- **Bug:** a title in Plex but with a stale/missing *arr record (e.g. `not_added` in Radarr yet present in Plex) showed `not_added`/`requested` because the status logic only reached `available`/`downloaded` when *arr reported `hasFile` — it never checked Plex first.
- **Fix (`api.py` + modular `api/routes/status.py`):** at the top of each entry evaluation, if the title exists in Plex it is immediately `available` with correct `plexUrl`/`embyUrl`, regardless of what Radarr/Sonarr report. Only titles *not* in Plex fall through to the *arr/qBittorrent pipeline.
- Added a ~45s-cached Plex library lookup (`_plex_library`) so repeated per-title checks don't re-scan 787 movies on every request (first status call ~2.4s, subsequent ~0.4s).
- **Verified:** Spider-Man, The Bear, Banshees, Mandalorian all now show `available` with working Plex links (they were `not_added` before).

### 8c. Plex Watch buttons — fixed deep-link format ✅
- **Two bugs in the generated Plex URLs:** (1) used the LAN host `192.168.65.254:32400` as the server id instead of the Plex **`machineIdentifier`** (`7780f37754c6ff144dd28c42b052e0187301dba1`); (2) passed a bare `key=320126` instead of the **URL-encoded `/library/metadata/320126`** (`%2Flibrary%2Fmetadata%2F320126`).
- **Fix:** backend now fetches and caches the machineIdentifier (`/identity`), builds `key=%2Flibrary%2Fmetadata%2F<ratingKey>`, and serves the correct `plexUrl` per item from `/api/library`. Verified the generated URL for The Mandalorian (key 320126) **exactly equals** the URL Plex itself produces when you click the show.
- Applies to: legacy `api.py` (`_plex_emby_urls`, library `recent[]`), modular `api/routes/status.py` + `services/plex.py` (new `server_id()`/`find_item()`/`plex_url_for()` helpers), and frontend `libraryCard()` (now uses the backend-provided `plexUrl` instead of building it client-side).

### 8b. Emby integration ✅
- Added `EMBY_URL=http://192.168.65.254:8096` + `EMBY_API_KEY` to `/workspace/.env` (user-provided key). The server at :8096 is **Emby** v4.9.5 (not Jellyfin).
- **Verified Emby API:** `Items/Counts` → **824 movies / 103 series / 5078 episodes** (shares the same library as Plex).
- Legacy `api.py`: added `EMBY_URL`/`EMBY_API_KEY` loading; `/api/library` now tries **Plex first** (richer view: recents + thumbnails + ratingKey deep links), then falls back to **Emby** for counts. Health/config report `emby: true`.
- Frontend: library cards show **both "▶ Plex" and "▶ Emby"** deep links; empty-state text updated. Since Plex and Emby share the library, Plex-primary gives the full view and Emby is a fully-working fallback.

### 8. Library fetch from Plex + click-to-watch buttons ✅
- **Root cause:** legacy `/api/library` called Plex **without** the `Accept: application/json` header, so Plex returned XML and JSON-parse failed → endpoint always returned `provider:null` (no library). 
- **Fix (`api.py`):** added the JSON header to all Plex library calls. Verified live: `/api/library` now returns real Plex data — **787 movies / 98 shows / 8 recent** with `ratingKey`.
- **Frontend (`app.js`):** library cards are now **clickable** — each recent item shows **"▶ Plex"** and **"▶ Emby"** buttons that deep-link to the item: Plex `app.plex.tv/desktop/#!/server/<host>/details?key=<ratingKey>` and Emby search via Tailscale MagicDNS. Thumbnails render through a new server-side proxy `/api/plex/thumb` (keeps the token secret; verified 200).
- **Emby note:** the server at `:8096` is **Emby** (v4.9.5) and now has a working API key (`EMBY_API_KEY` in `.env`), so both the Plex-primary library view **and** Emby fallback counts work — and every library card carries "▶ Plex" and "▶ Emby" watch buttons.

### 7. Watch Now buttons live-fix + Sonarr TV fallback ✅
- **`api.py` (legacy) status was returning HTTP 500** → that's exactly why no Plex/Emby buttons appeared: a `NameError` (`plexUrl` used as an unquoted dict key instead of `"plexUrl"`) broke `/api/status` for every request, so the frontend never got status data and never rendered the buttons. Fixed to string keys; verified `/api/status` now returns `available` with real `plexUrl`/`embyUrl` for in-Plex titles (Banshees, Mandalorian).
- **The Bear → "No Sonarr match for imdb"** — same root cause as the Radarr title: Sonarr's `imdb:tt10157119` lookup returns **0 results**, but a title search finds it (**tvdb 403294**). Added the same **title/year fallback** to `SonarrService.add_series` (+ `search_series`) and legacy `sonarr_add`. Verified: `The Bear` → added to Sonarr via title fallback (tvdb 403294).
- Card, hero, and modal buttons all render Watch-on-Plex/Emby for `available` state (frontend was already correct and volume-mounted).

### 5. Missing posters — TMDB artwork backfill ✅
- **Root cause:** many watchlist entries carried **fabricated/stale poster URLs** (e.g. `...9x9x9x9xX.jpg`, `...U9g3g7.jpg`) that 404 — the artwork was never validated against TMDB.
- **Fix:** new `scripts/backfill_tmdb_artwork.py` re-fetches the authoritative **poster + backdrop** from TMDB by each entry's `tmdbId` (movie or tv), updates `/workspace/media/watchlist.json` (the real API data source at the workspace root, per docker-compose mount), and rebuilds the dashboard.
- **Verified:** all 9 entries now have valid 200-returning TMDB posters. Also fixed a crash bug: `TMDBService` was raising `ServiceUnavailableError` with the wrong signature.

### 5b. Add-time self-healing posters ✅
- **Root cause:** `RecommendationService.enrich_metadata` copied `candidate.poster` verbatim and never overwrote it with TMDB — so any candidate carrying an empty/fabricated poster leaked straight into the watchlist at add-time.
- **Fix (`services/recommendations.py`):** enrichment now always sets `entry.poster` from the authoritative TMDB `poster` (movie or show), guarded by a new `_is_valid_poster()` — a real HEAD request requiring HTTP 200 + `image/*` content type. Fabricated/dead URLs are rejected.
- **Verified:** a candidate with `poster=...FAKE...9x9x9x9xX.jpg` is healed at enrich time → real `w500/6izwz...` TMDB poster. `_is_valid_poster`: valid→True, fabricated→False, empty→False.


### 4. "No Radarr match" — stale IMDb ID fallback (title search) ✅
- **Root cause:** the watchlist entry for *The Zone of Interest* had stale/wrong IDs — Radarr's `imdb:tt2197033` and `tmdb:457780` both returned **0 results**, while a **title search** found the correct movie (The Zone of Interest, 2023, **tmdb 467244**, imdb tt7160372).
- **Fix (`services/radarr.py`, `api.py`, `api/routes/download.py`, `api/models.py`, `app.js`):** when the stored IMDb lookup resolves nothing (or ambiguously), the backend now falls back to a **title (+year) search** in Radarr. Exact title/year match is preferred; multiple matches return a numbered "pick one" list with title · year · tmdbId for disambiguation (HTTP 404) instead of silently guessing or failing.
- `DownloadRequest` now carries optional `title`/`year`; the frontend sends them.
- Verified live: `tt2197033` + title/year → resolved to tmdb 467244 and added to Radarr.

### 1. YouTube trailer — NO API key required ✅
- **`services/youtube.py` rewritten** to scrape `youtube.com/results` directly (no YouTube Data API key).
- Parses `ytInitialData` JSON + fallback regexes; scores candidates for "official trailer" indicators, studio/distributor channel names, and verified badges; penalizes fan/noise videos.
- `has_youtube()` always True; `get_embed_url()` builds `youtube.com/embed/<id>` for **in-app playback**.
- Verified live: `Arrival` → `oGI9hSl0q-w` (Paramount official trailer); `Dune: Part Two` → `Way9Dexny3w` (official trailer).
- Frontend trailer button now **plays in-app** (opens the modal iframe) instead of opening a new YouTube tab.

### 2. Download routing — movies → Radarr, TV → Sonarr ✅
- Root cause: routing trusted the frontend `type` field; a missing/wrong type could send a movie to Sonarr.
- **`api.py` (legacy)**: added `_resolve_download_type()` — explicit type → watchlist `isSeries` → Radarr lookup (movie) then Sonarr lookup (series), defaulting to movie. A movie can no longer reach Sonarr.
- **`api/routes/download.py` (modular)**: same authoritative resolver + Radarr/Sonarr cross-fallback ("No Sonarr match" → retry as Radarr; "No Radarr match" → retry as Sonarr).
- Also fixed a latent bug: `RadarrService._get` / `SonarrService._get` now accept `timeout` (was raising `unexpected keyword argument` in modular download).
- Verified: `tt2543164` (Arrival, movie) → Radarr; `tt10157119` (The Bear, tv) → Sonarr; unknown → defaults to movie.

### 3. Plex/Emby "Watch" buttons for available content ✅
- **Legacy `api.py` status** now computes an `available` state (Radarr `hasFile`/Sonarr episodes downloaded AND present in Plex) and includes `plexUrl` + `embyUrl` deep links (Plex search/detail + Emby via Tailscale MagicDNS `rkm-hp.tail8d5e8.ts.net:8096`).
- **`app.js`**: hero + modal download buttons now render "Watch on Plex" / "Watch on Emby" / both for `available` state (cards already did).
- `services/emby.py` added as a service; config supports `EMBY_URL`/`EMBY_API_KEY` (`has_emby()`).

**Remaining before deploy:** run `setup-watchlist.ps1` on RKM-HP to ship backend changes; frontend files (app.js) go live via volume mount immediately.

## Status (2026-08-19)

- **NEW MODULAR ARCHITECTURE DEPLOYED**: Complete service layer with clean separation of concerns
  - `config/settings.py` - Centralized Config class (single source of truth for all env vars)
  - `core/http_client.py` - Shared HTTP client with caching, retry, structured errors
  - `core/logging.py` - Structured JSON logging
  - `core/exceptions.py` - Custom exception hierarchy
  - `services/plex.py` - Plex ownership verification (ground truth)
  - `services/radarr.py` - Movie management + quality profiles
  - `services/sonarr.py` - TV series management
  - `services/trailers.py` - TVDB v4 + TMDB trailer enrichment
  - `services/watchlist.py` - CRUD + state machine (atomic writes)
  - `services/recommendations.py` - Pipeline: category → gates → Plex → dedupe → enrich → add
  - `api/main.py` - FastAPI app factory with modular routes
  - `api/routes/` - Health, config, status, download, search, library, quality endpoints
  - `scripts/daily_recommendations.py` - Single orchestration entry point for daily cron
  - `scripts/auto_complete.py` - pending → recommended transition (hasFile + Plex)
  - `scripts/enrich_trailers.py` - Standalone trailer enrichment
  - `scripts/rebuild_dashboard.py` - Refactored build pipeline using services
  - Comprehensive test suite in `tests/`

- **Previous v2 stack still live** (needs redeploy to pick up new architecture):
  - `api` (FastAPI, :8000, secrets server-side) + `web` (nginx :8123)
  - qBittorrent status integration — DONE (code, needs redeploy)
  - PLEX_TOKEN in .env (user provided 2026-08-18)
  - .env consolidated: canonical `/workspace/.env` (= `D:\.env`); `/workspace/media/.env` is symlink
  - ⚠ Radarr indexers ALL down — The Father + 5 others at "requested"

- **7 pending titles** (same as before):
  | # | Title | Year | State |
  |---|---|---|---|
  | 0 | Arrival | 2016 | requested (waiting on indexers) |
  | 1 | The Grand Budapest Hotel | 2014 | requested (waiting on indexers) |
  | 2 | Mad Max: Fury Road | 2015 | requested (waiting on indexers) |
  | 3 | Prisoners | 2013 | requested (waiting on indexers) |
  | 4 | Nightcrawler | 2014 | requested (waiting on indexers) |
  | 5 | Whiplash | 2014 | not_added (user hasn't approved) |
  | 6 | The Father | 2020 | requested (waiting on indexers) |

- **Plex is ground truth for ownership** (user-ratified): all services now use Plex FIRST via PLEX_TOKEN

## New Architecture (modular service layer)

```
┌─────────────────────────────────────────────────────────────────┐
│                        DAILY CRON ORCHESTRATOR                   │
│  (scripts/daily_recommendations.py - single entry point)        │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   PlexSvc   │  │  RadarrSvc  │  │  SonarrSvc  │             │
│  │ (ownership) │  │  (movies)   │  │   (tv)      │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  RecoSvc    │  │ TrailerSvc  │  │ WatchlistSvc│             │
│  │ (recs+gates)│  │ (TVDB/TMDB) │  │  (CRUD+FSM) │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE / INFRASTRUCTURE                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Config    │  │    HTTP     │  │  Logging    │             │
│  │  (central)  │  │  (client)   │  │  (struct)   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SERVICES                           │
│  Plex · Radarr · Sonarr · Prowlarr · TVDB · TMDB · qBittorrent  │
└─────────────────────────────────────────────────────────────────┘
```

## File inventory (`/workspace/projects/rkm-cinema/`)

| File | Purpose |
|---|---|
| `config/settings.py` | **Centralized Config class** - all env vars, validation, defaults |
| `core/http_client.py` | Shared HTTP client with caching, retry, structured errors |
| `core/logging.py` | Structured JSON logging setup |
| `core/exceptions.py` | Custom exception hierarchy (ServiceUnavailableError, DuplicateError, etc.) |
| `services/base.py` | BaseService with common patterns |
| `services/plex.py` | Plex ownership verification (has_movie, has_show, has_media) |
| `services/radarr.py` | Radarr movie management, quality profiles, queue, indexer health |
| `services/sonarr.py` | Sonarr series management, quality profiles, queue |
| `services/trailers.py` | TVDB v4 + TMDB trailer enrichment, validation |
| `services/watchlist.py` | Watchlist CRUD, state machine, atomic persistence |
| `services/recommendations.py` | Recommendation pipeline (category, gates, Plex check, enrich) |
| `services/__init__.py` | Unified exports |
| `api/main.py` | FastAPI app factory |
| `api/models.py` | Pydantic request/response models |
| `api/routes/health.py` | GET /api/health |
| `api/routes/config.py` | GET /api/config |
| `api/routes/status.py` | GET /api/status (per-title state + qBit progress) |
| `api/routes/download.py` | POST /api/download (Radarr/Sonarr + qualityProfileId) |
| `api/routes/search.py` | GET /api/search (watchlist + TMDB) |
| `api/routes/library.py` | GET /api/library (Plex/Jellyfin) |
| `api/routes/quality.py` | GET /api/quality (quality profiles for download chooser) |
| `scripts/daily_recommendations.py` | **Daily cron orchestration** - single entry point |
| `scripts/auto_complete.py` | **Auto-complete** - pending → recommended when hasFile + Plex |
| `scripts/enrich_trailers.py` | Trailer enrichment (probe, dry-run, enrich) |
| `scripts/rebuild_dashboard.py` | Dashboard build using WatchlistService |
| `tests/test_*.py` | 7 test modules covering critical workflows |
| `app.js` / `app.css` | Frontend (volume-mounted, live immediately) |
| `index.html` / `dashboard.html` | Slim shell loading app.js |
| `Dockerfile` / `docker-compose.yml` | api image + nginx web |
| `setup-watchlist.ps1` | Windows deploy (rebuild + up) |
| `nginx/default.conf` | no-store headers; `/api/` → api:8000 |
| `watchlist.json` | **Data** — at `/workspace/media/watchlist.json` |
| `ARCHITECTURE.md` | Detailed architecture documentation |
| `README.md` | Project overview, setup, usage |
| `PROGRESS.md` | This file |

## Config — `.env`

Canonical: **`/workspace/.env`** (= `D:\.env`). `/workspace/media/.env` is a symlink. Variable names only:

`MEDIA_HOST, RADARR_URL, RADARR_API_KEY, SONARR_URL, SONARR_API_KEY, PROWLARR_URL, PROWLARR_API_KEY, PLEX_URL, PLEX_TOKEN, JELLYFIN_URL, JELLYFIN_API_KEY, BROWSER_RADARR_URL, BROWSER_SONARR_URL, QBITTORRENT_URL, GITHUB_TOKEN, RADARR_QUALITY_PROFILE_ID, SONARR_QUALITY_PROFILE_ID, TMDB_API_KEY, TVDB_API_KEY`

**MISSING (next session):**
- `TVDB_API_KEY` — **user has this key**; paste into `.env` → `python3 scripts/enrich_trailers.py --probe` → enrich → rebuild.
- `TMDB_API_KEY` — optional; second trailer source + poster fallback.

---

## FEATURE 1: Auto-complete (pending → available when downloaded + in Plex) ✅ COMPLETE

**Goal:** when a pending title's file lands (qBittorrent 100% → Radarr import → Plex scan), auto-move it from `pending[]` to `recommended[]` with a completion date, and notify Rajeev in chat. No manual "drop N" needed.

**Implementation Completed:**

1. ✅ **API status endpoint** - Detects `available` state when both *arr hasFile AND Plex has title
   - Movies: `rec.hasFile and in_plex` → `state: "available"` with Plex/Emby deep links
   - TV Series: `downloaded and in_plex` → `state: "available"` with deep links
   - Keeps `downloaded` for content in *arr but not yet scanned into Plex

2. ✅ **Frontend rendering** - Updated `app.js`:
   - `STATE_LABEL` includes `available: 'Available'`
   - `dlStateMarkup()` shows "Available in Plex" for available state
   - `downloadButton()`, `heroDownloadButton()`, `downloadButton()` all handle `available` state
   - `rerenderDownloadButtons()` updated for available state styling
   - Watch Now dropdown functionality added for Plex/Emby links

3. ✅ **Auto-complete integration** - Updated `scripts/daily_recommendations.py`:
   - Runs `auto_complete.py` FIRST before processing new recommendations
   - Reports auto-completed entries in results
   - Returns completion count for cron logging

**Next Steps:**
1. Deploy new architecture - Run `setup-watchlist.ps1` on RKM-HP
2. Verify PlexService integration against live Plex
3. Test `/api/status` against known-owned titles
4. Verification pass - Rebuild dashboard and confirm no regressions## NEXT SESSION — FEATURE 6: Download quality choice (1080p vs 4K before adding)

**Goal:** when clicking Download on a card, let Rajeev pick the quality profile (e.g. 1080p vs 2160p/4K) instead of silently using the default.

**IMPLEMENTATION STATUS: Backend COMPLETE in new architecture**

The following are **already implemented**:

1. ✅ **RadarrService.get_quality_profiles()** - Returns profiles with id, name, items
2. ✅ **SonarrService.get_quality_profiles()** - Returns profiles with id, name, items
3. ✅ **RadarrService.add_movie(imdb_id, quality_profile_id)** - Accepts optional qualityProfileId
4. ✅ **SonarrService.add_series(imdb_id, quality_profile_id)** - Accepts optional qualityProfileId
5. ✅ **API endpoint GET /api/quality** - Returns Radarr + Sonarr profiles (no secrets)
6. ✅ **API endpoint POST /api/download** - Accepts `qualityProfileId` in request body
7. ✅ **DownloadRequest model** - Includes `qualityProfileId: int | None`

**Remaining tasks (do in order):**

1. **Deploy new architecture** - Run `setup-watchlist.ps1` on RKM-HP
2. **Frontend — quality chooser on Download** - In `app.js`:
   - Fetch `/api/quality` once (cache in `QUALITY`)
   - On `doDownload`, if entry not yet added and profiles > 1 → show chooser (modal/dropdown): "1080p (HD-720p profile)" / "4K" / "Default"
   - Remember last pick in `localStorage` (`rkm_qp`) as default
   - Pass `qualityProfileId` in `postDownload` body
   - Keep single-click path when only one profile exists
3. **Quality profile hygiene** - Check Radarr has sensible 1080p and 2160p profiles (see `progress_download_selection.md` — profile 3 = "HD-720p", 720p/1080p capped 2GB; 4K profile may not exist yet)
4. **Verification pass** - Add test title with each profile choice → confirm `/api/v3/movie` reflects chosen `qualityProfileId`; rebuild dashboard; live-curl

---

## FEATURE 7: Watch Now - Plex/Emby deep links ✅ COMPLETE

**Goal:** When a movie/series reaches `available` state (downloaded + in Plex), replace the "Download" button with a **"Watch Now"** action that offers both **Plex** and **Emby** deep links using Tailscale MagicDNS URLs.

**Implementation Completed:**

1. ✅ **API Model Update** (`api/models.py`):
   - Added `plexUrl: Optional[str]` and `embyUrl: Optional[str]` to `StatusEntry` model

2. ✅ **API Endpoint Enhanced** (`api/routes/status.py`):
   - Extended `/api/status` to compute Plex deep links when `rec.hasFile and in_plex` is true
   - Generate Plex deep link via ratingKey if available, otherwise search link
   - Generate Emby deep link via Tailscale MagicDNS
   - Returns `plexUrl` and `embyUrl` fields in status response

3. ✅ **Frontend Handler** (`app.js`):
   - Enhanced `downloadButton()` to show "Watch Now ▼" dropdown for available state
   - Handles both Plex and Emby URLs with data attributes
   - Click handler processes `watch-plex`, `watch-emby`, and `watchnow` actions
   - Opens links in new tab

4. ✅ **Build Script Fixed** (`scripts/rebuild_dashboard.py`):
   - Fixed to work with current `WatchlistEntry` model
   - Added safe defaults for missing fields

**Priority:** High — completes the lifecycle UX (Recommended → Download → Available → Watch)## TVDB v4 integration plan (resume here)

Endpoint shapes NOT yet live-verified from the sandbox (oEmbed blocked; use `scripts/enrich_trailers.py --probe` first):

1. `POST https://api4.thetvdb.com/v4/login` body `{"apikey":"<TVDB_API_KEY>"}` → `data.token` (JWT ~30 days). Cache to `/workspace/media/.tvdb_token`; re-login on expiry.
2. `GET /v4/search?query=<title>&type=movie|series&year=<year>` → match `remoteids[]` to known `imdbId` → TVDB `id`.
3. `GET /v4/movies/{id}/extended` or `/v4/series/{id}/extended` → `artworks`, `trailers`, `genres`, `runtime`, `overview`.
4. Extract YouTube ID from `watch?v=ID` / `youtu.be/ID` / `/embed/ID`. Only YouTube embeds; else search-link fallback.
5. Fallback: TMDB `/movie/{tmdbId}/videos` (site=YouTube, type=Trailer).
6. Rule: NEVER write an unverified `trailerId` — empty → search link.

**Implemented in `services/trailers.py`** - Complete with token caching, search, extended, trailer extraction, validation.

---

## Operations

- **Rebuild dashboard:** `cd /workspace/projects/rkm-cinema && python3 scripts/rebuild_dashboard.py`
- **Rebuild + verify:** `python3 rebuild_verify.py` (legacy, still works)
- **Repair if corrupted:** `python3 fix_all.py` (legacy)
- **TVDB enrich:** `python3 scripts/enrich_trailers.py` (probe first: `--probe`)
- **Auto-complete:** `python3 scripts/auto_complete.py [--dry-run]`
- **Daily recommendations:** `python3 scripts/daily_recommendations.py [--candidates file.json] [--dry-run]`
- **Deploy (Windows PowerShell):** `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema; .\setup-watchlist.ps1` — REQUIRED to ship api.py changes (image rebuild); frontend files go live via volume mount immediately.
- **Run tests:** `cd /workspace/projects/rkm-cinema && pytest tests/ -v`
- **Cron:** job `0cd1d3c2c872` "RKM Watchlist daily rec", `0 18 * * *` AEST, LLM-driven, loads `weekly-media-recommendations` skill. Prompt updated 2026-08-18: Plex-first library check, r.jina.ai score verification, qBittorrent-aware. Approval always the user's — cron never POSTs to *arr.

---

## Known issues / next-session checklist

1. **DEPLOY PENDING (urgent — unblocks 504 fix + Suggest):** run `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema; .\setup-watchlist.ps1` on RKM-HP. Bakes the API-side 504 fixes (`compute_cached`, Sonarr-tmdb→tvdb) **and** the Suggest route (`api/routes/suggest.py` is committed now). Until deployed the running container still has the old slow reconciler + a 404 on `/api/suggest`. Web-side (app.js/app.css: 60s poll, hover buttons, search history, add-to-app) go live via the volume mount without a rebuild.
2. **Radarr/Sonarr indexers may still be down** — requested titles sit "requested"/"Waiting — search indexers down" until indexers recover (AU s115a). Not an app bug. The 504/status slowness is now decoupled from this, but a still-down indexer means downloads won't start.
3. **TVDB_API_KEY not in .env** — user has it; optional for TMDB-first tvdb resolution (fallback only).
4. **Verify post-deploy:** confirm `/api/watchlist` + `/api/status` return fast (<1s on a warm poll, ~18s after a write/expiry), `/api/suggest` returns 200, and TV suggestion-adds appear under **TV Shows**.
5. **Test Suggest search history persistence** across reloads (localStorage `rkm_suggest_history`) + hover-only card buttons on desktop vs always-visible on touch.
6. **Monitor the reconcile-cache invalidation on acquisition writes** — after a download request, next poll should reflect it quickly (mtime + route-clear).
7. **Host path mapping:** sandbox `/workspace` = `D:\hermes_agent\hermes-workspace` (9p mount, NOT `D:\media`). Any doc/skill mentioning `D:\media\...` is stale.
8. **Order of next-session work:** (a) push commits to GitHub, (b) deploy, (c) verify the 3 UX items above, (d) legacy-cleanup of old scripts now that suggest + resource API are the path.

---

## Lessons log

- **2026-08-28 (auto-add + dedup):**
  - **A single-source TMDB discover plateaus fast.** `discover/*` with only `popularity.desc` always returns your owned trending titles — the op looks "broken" (0 added) when it's really converging. Rotate strategies (popular/top-rated/hidden-gems/recent) so fresh candidates keep flowing.
  - **Never gate a title-matching fallback on the candidate carrying an id.** `PlexLibraryProvider.find()` skipped its fuzzy-substring fallback for id-bearing candidates, assuming id absence was authoritative — but Plex items often expose **no provider ids** (`provider_ids()={}`), so an owned title with a title variant (`Batman: The Dark Knight` vs `The Dark Knight`) was treated as unowned and re-added. Run the substring fallback as a genuine last resort for ANY candidate still lacking a match.
  - **Treat Plex `year=0` as "unknown", not a hard mismatch.** `matches()` rejected a title match whenever `self.year != candidate_year` — including year=0 (unknown). Only reject when the Plex year is actually known. Explicitly: `if year is not None and self.year and self.year != year`.
  - **TMDB discover yields no IMDb rating** — need `external_ids` on the detail call + a lookup (OMDb free tier) to show IMDb scores. Keep it optional/manually-guarded so Mocks/failures don't crash the enrich pipeline.
  - **`no_agent` cron runs the shell wrapper, not the Hermes prompt** — editing the job prompt changes nothing. To change `--count`, edit `~/.hermes/scripts/rkm_watchlist_auto_add.sh`.
- **2026-08-17:** `esc()` must `String(s ?? '')` (silent blank-page crash); posters center via `object-position`; atomic writes + publish guard against corruption; sandbox has NO Docker access (PS deploys) + inline mega-commands get blocklisted → write `.py` scripts.
- **2026-08-18:**
  - **PS 5.1 parse errors = encoding, not syntax.** UTF-8-no-BOM `.ps1` with em-dashes breaks: byte 0x94 reads as a smart quote, terminating strings mid-line ("missing terminator"). Scripts for Windows must be pure ASCII + CRLF.
  - **Docker Desktop cannot follow WSL symlinks.** After consolidating `.env`, compose `env_file: ../.env` hit `media\.env` (a WSL symlink) → "file cannot be accessed". Fix: `env_file: ../../.env` → the real canonical file at the workspace root. Sandbox-side scripts can use the symlink; Windows-side tooling must use the real path.
  - **Radarr ≠ ownership.** Plex had Spirited Away + Andhadhun that Radarr never tracked — Plex is ground truth; Radarr check alone created duplicate pending entries.
  - **qBittorrent is the real download truth.** Radarr queue can be empty while a torrent is active (or vice-versa) — status must read qBittorrent directly.
  - **urllib gotcha:** `timeout=` is a `urlopen()` kwarg, NOT `Request()` — qbit fetch failed silently (returned []) until fixed.
  - **Indexer outage = silent stall.** Requested titles sat static with no explanation; health-check awareness ("Waiting — search indexers down") is essential UX, not decoration.
  - **.env split was cruft** — consolidated to `D:\hermes_agent\hermes-workspace\.env` with `media/.env` symlink; compose env_file + hardcoded script paths keep working.
  - **Plex API shapes:** sections via `/library/sections`; movies = `<Video>` nodes, shows = `<Directory>` nodes in section dumps.
- **2026-08-19 (Architecture Refactor):**
  - **Service layer pattern works** - Clean separation makes testing, debugging, and maintenance vastly easier
  - **Centralized Config** - Single source of truth eliminates env loading bugs across scripts
  - **Atomic watchlist writes** - tmp + os.replace prevents corruption; validation before publish prevents empty dashboards
  - **State machine in WatchlistService** - Valid transitions enforced, prevents invalid states
  - **Structured logging** - JSON logs enable log aggregation and debugging
  - **Pydantic models for API** - Type safety, auto-documentation, validation
  - **Tests first** - Writing tests for plex ownership, radarr/sonarr routing, duplicates, trailers, status, e2e, errors caught design issues early
