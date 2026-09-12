# Plan: per-user identity via Jellyfin + app sessions (multi-user)

**Status: SCOPED 2026-09-12, NOT STARTED.** Branch `feat/auth-multiuser` (cut from `main`), this plan is
the branch's first commit. Execute phase by phase — **ONE commit per phase, gates green after every one**,
and a `docs(status)` PROGRESS record at the end.

**User decisions (2026-09-12):** this is the next feature; the goal is **real per-user state for the
household, with identity DELEGATED to Jellyfin** (not a shared password, not app-owned accounts). Native
Jellyfin collections (app-authored, visible in Jellyfin's own apps) is **queued behind this plan**.

---

## 1. What this delivers, in one line

Every request is made **as the signed-in Jellyfin user**, so Continue Watching, resume positions, watched
flags and library visibility become per-person for free — because Jellyfin already models all of them per
user — while the app's own stores gain a user key only where they genuinely need one.

## 2. Why delegated identity (the measurements behind it)

- **Jellyfin is already a multi-user media server.** `/Users/{uid}/Items`, `/Items/Resume`,
  `/Users/{uid}/PlayedItems/{id}`, `/Users/{uid}/Items/{id}/UserData` and `/Users/{uid}/Views` are all
  per-user. The app currently calls every one of them with the **single admin token** from
  `runtime.json`, so the whole household shares one watch history.
- **Measured inventory (2026-09-12, live against RKM-HP):**
  - Jellyfin users on the server: **1** (`admin`, administrator, enabled) — so "household" also means
    *creating* Jellyfin users and granting them library access.
  - `/Users/{uid}/Views` for `admin` returns `['Movies', 'Movies Kids', 'TV Shows']` — per-user library
    visibility is real and already populated server-side.
  - The api surface: **41 contract paths**, **20 registered routers**; the Jellyfin provider builds URLs
    with one token at **21 `api_key=` sites**.
  - `build_library_service(config, *, http=None)` is called **18 times** across the routes — always per
    request, never once at startup. That is what makes per-request identity feasible without a rewrite.
  - The app's own stores are **single-user by construction**: `data/rkm/watchlist.json` has no user key,
    and subtitle preferences are per **item** (the subtitle plan says so explicitly).
  - **No auth exists anywhere:** no security dependency or session code in `backend/api/**` (only CORS);
    no `auth_basic`/`auth_request` in `nginx/default.conf`; CORS is `allow_origins=["*"]`. Reachability is
    the only protection (`docs/TAILSCALE_HOSTING.md`: `tailscale serve`, tailnet-only, never funnel).
  - **The api is not published on the host at all** — `docker-compose.yml` maps `web:8124` and jellyfin's
    port only (verified), so the api is reachable only through nginx.
  - The frontend has **no** 401 handling, no login route, no session concept.
  - The PowerShell tooling touches the app on exactly two paths: `GET /api/health` and
    `GET /api/library/folders` (via `tools/rkm_status.py`).
  - `backend/Dockerfile`'s `HEALTHCHECK` literally calls `http://127.0.0.1:8000/api/health`.

## 3. Architecture

```
  browser ──POST /api/auth/login {username,password}──► api ──► Jellyfin /Users/AuthenticateByName
     ▲                                                    │            │
     │  Set-Cookie: rkm_session=<opaque>  (httpOnly)       │            └─► {User, AccessToken}
     │                                                    ▼
     └── every later request carries the cookie ──► session lookup ──► contextvar: (token, user_id)
                                                                          │
                              JellyfinLibraryProvider._token() ───────────┘
                              (falls back to the admin token when no request context exists —
                               provisioner, bootstrap, tools and unit tests are untouched)
```

1. **Server-side sessions**, not a signed cookie carrying the token. The cookie holds an **opaque id**;
   the store keeps `sha256(id) → {user_id, user_name, jellyfin_token, created, expires, last_seen}`.
   Why: logout is a real revocation (delete the row), the Jellyfin token never reaches the browser, and a
   container rebuild does not log everyone out. Same trust level as `runtime.json`
   (`/shared/runtime.json`, verified as the api's token source) — write it `0600`, and follow the existing
   state-path convention `/data/rkm/<name>.json` (the bind-mounted media root).
   A signed-cookie design was rejected: revocation would need a second mechanism and the token would then
   travel on every request.
2. **`services/auth.py`** — the session store *and* the Jellyfin authentication call.
3. **`api/session.py`** — the `require_session` dependency and the contextvar seam.
4. **Token resolution in the provider**: `_token()` returns the contextvar's token when one is set, else
   `config.JELLYFIN_API_KEY`. One diff point instead of threading a token through 18 call sites and 21 URL
   builds — and it fails safe: no request context (provisioner, tools, tests) behaves exactly as today.
5. **Per-user caches are already isolated**: `_item_cache`, `_folders_cache`, `_server_id_value` and
   `_user_id_value` live on the provider instance, which is built per request.
6. **Machine access** for the repo's own tooling: `RKM_API_TOKEN`, generated by `render_config.py` the way
   `RKM_JELLYFIN_ADMIN_PASSWORD` is, sent as `X-RKM-Token`. An IP/localhost bypass was rejected: the api
   sits behind nginx and is not published on the host, so it cannot see a trustworthy client address.
7. **Frontend**: a `/login` route outside the authenticated shell, an auth provider reading
   `GET /api/auth/me`, a global 401 → redirect handler in `lib/api/client.ts`, a user chip with **Sign out**,
   and `queryClient.clear()` on login/logout so one person's rows cannot flash for the next.
8. **Per-user libraries**: the sidebar is config-driven (`MEDIA_LIBRARY_*`); it will be **filtered to the
   user's own `/Users/{uid}/Views`**, so a restricted Jellyfin user sees a restricted app.

## 4. What is per-user and what stays shared (deliberate calls — do not "fix" these)

| Thing | Decision | Why |
|---|---|---|
| Continue Watching, resume, watched flags, play count | **Per user** (free — Jellyfin's own) | The whole point; no app-side model needed |
| Library visibility | **Per user** (filtered by that user's `Views`) | Otherwise a kids' account sees everything |
| Subtitle **preferences** | **Per user** (additive migration, old key read as a fallback) | "My subtitle for this film", not the household's |
| Subtitle **usage counts** | **Shared/household** (unchanged) | They rank results and spend ONE shared download quota — per-user counts would misreport it |
| Watchlist (`watchlist.json`) | **Shared** (unchanged) | It is the household ACQUISITION queue: one request per film, not one per person |
| Player prefs (volume/speed/quality) | **Per browser** (localStorage, already) | Nothing to do |
| Download/acquisition actions | Any signed-in user | Same behaviour as today, now attributable |

---

## 5. Execution order, prerequisites and the lockout rule

**Phase order is deliberate: the login UI ships BEFORE anything is enforced**, so an enforcement deploy can
never lock the user out of an app with no way to sign in. Order: **0 store+endpoints → 1 login UI →
2 enforcement → 3 identity → 4 subtitle prefs → 5 docs/record**.

**UPDATED 2026-09-12 (user request): a new Phase 1b — household accounts managed from inside the app — slots in
after Phase 1 and before Phase 3**, so the SECOND Jellyfin user Phase 3's live proof needs is created from the
app's own UI rather than the Jellyfin dashboard. Its full plan (routes, live admin check, the measured endpoint
shapes, the traps) is [HOUSEHOLD_USERS_PLAN.md](HOUSEHOLD_USERS_PLAN.md). Phase 1b does not need enforcement:
its routes are session-strict from day one, independent of `RKM_AUTH_REQUIRED`.

**Prerequisites to START Phase 0** (nothing else blocks):
- `main` is at `c0ae65e` (subtitles complete) and the user's subtitle eyeball has either passed or is still
  outstanding — that must not be silently skipped, but it does not block this branch (this branch touches
  no subtitle code).
- Branch `feat/auth-multiuser` exists at `d62ce52` (this plan). Work from it; rebase on `main` only if
  `main` moves.

**Prerequisite for Phase 3's live proof:** a **second Jellyfin user must exist** (the app's per-user
behaviour cannot be *proven* with one account). Creating Jellyfin users changes the user's server, so it is
his call: either he creates one in the Jellyfin dashboard (Admin → Users → Add user, grant the libraries),
or we build the optional in-app flow first (see Phase 5 §optional). **Ask him before assuming it exists.**

**The lockout rule (read before Phase 2).** Enforcement is a switch: `RKM_AUTH_REQUIRED` (default `false`).
Phase 2 flips the DEFAULT to true in `.env.example`, while the live `.env` keeps its own value — so the
escape hatch is always available:

```powershell
# if you ever cannot get in:  set RKM_AUTH_REQUIRED=false in .env, then
docker compose -p rkm-bundled up -d --build api    # (no render needed: the value is read per request)
```

Any phase that changes `.env`/`render_config.py` needs a **full deploy** (`.\.rkm-cinema.ps1 deploy`) — the
api container has no `.env`; its config is the rendered `.rkm.env`.

---

## 6. Phase detail

Gate per phase: `cd backend && python -m pytest -q && python -m ruff check .`.
From Phase 0 onward also the frontend gate, because the typed client is regenerated every time the contract
changes: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build`.
Contract check every phase: `python -c "import json;d=json.load(open('docs/api/openapi.v1.json'));print(len(d['paths']),'paths')"`.

### Phase 0 — session store + `/api/auth/*` endpoints **(additive; nothing enforced)**

**Commit:** `feat(auth): server-side sessions + login/logout/me endpoints (no enforcement yet)`

| Item | Detail |
|---|---|
| New | `backend/services/auth.py` — `SessionStore` + `authenticate_jellyfin(cfg, username, password)`; `backend/api/session.py` — `require_session`, `current_session()`, the contextvar; `backend/api/routes/auth.py` — the router |
| Store API | `create(user_id, user_name, token) -> (session_id, record)`, `lookup(session_id) -> record|None` (expiry check + touch), `revoke(session_id)`, `prune()`, `count()`, `records()` (never returns the raw token) |
| Path | `default_session_path()` mirroring `services/subtitle_store.default_store_path()`: `<state dir>/rkm/sessions.json` |
| Hardening | `sha256(id)` as the stored key (a leaked file yields no usable session ids); file mode `0600`; atomic tmp + `os.replace`; corrupt file ⇒ log + start empty (never 500); **never log or return a token or password** |
| Endpoints | `POST /api/auth/login` `{username, password}` → `{ok, user:{id,name}, expires}` + `Set-Cookie: rkm_session=<opaque>; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000` (**no `Secure`** while the tailnet is plain http); `POST /api/auth/logout` → revoke + clear cookie; `GET /api/auth/me` → the session's user or 401 |
| Auth call | copy the **proven** header/body from `tools/rkm_common.py::Jellyfin._login` (`X-Emby-Authorization: MediaBrowser Client="rkm-…", Device=…, DeviceId=…, Version=…`) against `/Users/AuthenticateByName`; a failed login is a generic 401 (never distinguish unknown user from bad password, never echo the password) |
| Config | `RKM_AUTH_REQUIRED` declared on `Config`, annotated, read in `_load()`, present in `_get_all_keys()` — **no passthrough list edits** (annotate the class; that is the repo's rule) |
| Models | `LoginRequest`, `LoginResponse`, `MeResponse` in `backend/api/models.py` (snake_case for new fields, as the subtitle endpoints do) |
| Contract | 41 → **44 paths**; `python backend/scripts/snapshot_openapi.py`; regenerate the typed client (`npm run generate:types`); both must be **purely additive** |
| Tests | `backend/tests/test_auth_store.py`: create/lookup/expire/revoke/prune, corrupt file, 0600 mode, and that the **raw token is not the stored key**; `backend/tests/test_auth_api.py`: login success on a fake Jellyfin transport, wrong password ⇒ 401, cookie flags exactly as above, `/me` before/after, logout revokes (a second `/me` is 401), and **no response body or log record contains the token or the password** |
| Proof | `print(len(d['paths']))` → 44 · the sweep test below stays green because enforcement is off · a curl with no cookie still returns 200 (unchanged behaviour) |
| Risk | Low — nothing is enforced, so the running app cannot break. The one real risk is **storing the session id unhashed** or returning the token in a body; both are test-pinned |

### Phase 1 — frontend login screen + guard **(still nothing enforced)**

**Commit:** `feat(auth): login view, auth provider, sign out and 401 handling (not enforced yet)`

| Item | Detail |
|---|---|
| New | `frontend/src/features/auth/LoginView.tsx`, `frontend/src/features/auth/AuthProvider.tsx` (or `app/auth.tsx`), `frontend/src/features/auth/lib.ts` (pure: `loginErrorMessage`, `isAuthenticated`) + `lib.test.ts` |
| Router | `/login` **outside** the shell (no sidebar/header), so it renders when nothing else can |
| Client | `lib/api/client.ts`: `login()`, `logout()`, `me()`; `credentials: "same-origin"`; a single **401 interceptor** that clears the auth state and routes to `/login` (once, not per request) |
| Header | user chip (name) + **Sign out**; `queryClient.clear()` on both login and logout |
| Guard | while `me()` is pending show a skeleton (never a flash of the app); on 401 render the login view |
| Gates | `tsc`, `vitest` (new pure helpers get tests), `npm run build`; plus a DOM check: `tools/check_login_flow.py` (new, Playwright, mirrors `check_subtitle_panel.py`) driving login → Home → sign out against a stubbed api |
| Proof | With enforcement OFF the app still works signed-out; the login page loads, a wrong password shows an error, a good one lands on Home, sign out returns to `/login` |
| Risk | Medium-low; isolated to the frontend until Phase 2. **Do not** flip enforcement in this phase |

### Phase 2 — enforcement + machine token + the 401 sweep **(the lockout-risk phase)**

**Commit:** `feat(auth): require a session on every app path (escape hatch: RKM_AUTH_REQUIRED=false)`

| Item | Detail |
|---|---|
| Wire | `require_session` added to each `app.include_router(...)` call **except** `health` and `auth` (explicit beats clever; a middleware with an allow-list is the rejected alternative) |
| Public paths | `/api/health` (Docker HEALTHCHECK — verified in `backend/Dockerfile`), `/api/auth/login`, `/api/auth/logout` (`/api/auth/me` requires a session) |
| Machine token | `RKM_API_TOKEN` generated + persisted by `render_config.py::build_api_vars` exactly like `RKM_JELLYFIN_ADMIN_PASSWORD` (`write_env_key`), declared on `Config`, documented in `.env.example`, sent by `tools/rkm_common.py` as `X-RKM-Token` for app-base calls; compare with `secrets.compare_digest` |
| CORS | `allow_origins=["*"]` is **invalid together with credentials** — switch to an explicit list (`RKM_CORS_ORIGINS`, default the local vite origins) + `allow_credentials=True`. The production UI is same-origin behind nginx, so nothing else changes |
| Tests | ⭐ **`test_every_path_is_protected`**: enumerate `docs/api/openapi.v1.json` paths and assert each returns **401 without a cookie**, against the public allow-list. This is the guard that catches a future router that forgets the dependency — write it FIRST and watch it fail |
| Tests | machine token works on `/api/library/folders`; a WRONG token 401s; `/api/health` stays 200 (container health); `RKM_AUTH_REQUIRED=false` ⇒ the old behaviour returns; a valid cookie reaches a normal path |
| Gate | pytest + ruff + frontend gate |
| User step | **full deploy** (`.\.rkm-cinema.ps1 deploy` — `render_config.py` changed), then sign in once per device/browser origin (`localhost`, LAN IP and the Tailscale host are three different cookie jars — expected, document it) |
| Proof | `curl -s -o /dev/null -w '%{http_code}' http://localhost:8124/api/library` → **401**; `curl` with `X-RKM-Token` → 200; `.\.rkm-cinema.ps1 status` still reports normally |
| Risk | **Highest of the plan**: enforcement can lock the user out. Mitigations: `RKM_AUTH_REQUIRED=false` escape hatch (§5), `/api/health` public, the machine token for tooling, and the login UI already shipped in Phase 1 |

### Phase 3 — per-request Jellyfin identity + per-user libraries **(the payoff)**

**Commit:** `feat(auth): make every Jellyfin call as the signed-in user`

| Item | Detail |
|---|---|
| Provider | `JellyfinLibraryProvider._token()` → contextvar token, else `config.JELLYFIN_API_KEY`; replace the 21 `api_key={self.config.JELLYFIN_API_KEY}` sites with `api_key={self._token()}`; `_user_id()` resolves the **session's** user id (keep the admin lookup only when there is no session) |
| Cache safety | confirm no provider/global cache is keyed by item id alone (they are per-instance: `_item_cache`, `_folders_cache`, `_server_id_value`, `_user_id_value`) — add a test that two users' providers do not share results |
| Libraries | `/api/library/folders` and the sidebar are filtered to the session user's `/Users/{uid}/Views` |
| Tests | token preference/fallback unit tests; per-user `_user_id()`; two users ⇒ two different `Views` filters |
| Live proof | **needs the 2nd Jellyfin user** (see §5): A and B each play part of the same film ⇒ **two different Continue Watching rails**, two different resume positions, and marking watched as A leaves B's flags alone. Print the item ids per user as evidence |
| Risk | High-ish: a wrong `_user_id()` would silently show one user another's history. The fallback must stay for the provisioner/bootstrap, and the live check must use TWO accounts |

### Phase 4 — per-user subtitle preferences (usage counts stay shared)

**Commit:** `feat(subtitles): per-user preferences (usage counts stay household-wide)`

| Item | Detail |
|---|---|
| Store | `services/subtitle_store.py`: `prefs[user_id][item_id]`; **read-fallback** to the existing flat `prefs[item_id]` (so the current choice is not lost on upgrade); writes always go to the user-scoped form |
| Usage | **unchanged** — one global counter per subtitle (ranks one shared download quota) |
| Routes | `/api/jellyfin/subtitle-search|select|disable` take the user from the session, not a parameter |
| Tests | fallback read (old record visible to the user who set it), two users holding different choices on ONE item, usage shared across users, and the migration is additive/no data loss |
| Proof | two users, one film, two different subtitles applied on load; the usage count is the household total |
| Risk | Low; the fallback is the safety net, and a bogus fallback would surface as "my old choice vanished" |

### Phase 5 — docs, ADR-0006, record, and the optional add-user flow

**Commit:** `docs(auth): ADR-0006, operations runbook, and the multi-user record`

| Item | Detail |
|---|---|
| ADR | **ADR-0006** — this is a **BREAKING contract change** (every app path now requires a session), which ADR-0001 requires be explicit and recorded: the decision, the rejected alternatives (shared password; app-owned accounts; IP bypass), the cookie/session design, the machine token, and the escape hatch |
| Docs | `ARCHITECTURE.md` (auth section + endpoint table + the contextvar rule), `OPERATIONS.md` (symptom rows: **locked out**, add a household member, rotate `RKM_API_TOKEN`, "logged out on my phone" = different cookie jar), `README.md` (features + config rows), `.env.example` (`RKM_AUTH_REQUIRED`, `RKM_API_TOKEN`, `RKM_CORS_ORIGINS`) |
| Record | PROGRESS block + mark this plan EXECUTING→COMPLETE |
| **MOVED FORWARD** | The admin-only **"add Jellyfin user"** flow (`POST /Users/New` + grant libraries) was the *optional* item here; the user asked for it explicitly on 2026-09-12 ("from the UI"), so it is now its own phase — **Phase 1b**, planned in full in [HOUSEHOLD_USERS_PLAN.md](HOUSEHOLD_USERS_PLAN.md), running after Phase 1 and before Phase 3. Nothing else about this phase changes. |
| Eyeball | user deploys and signs in as **two accounts on two devices**: separate Continue Watching, separate subtitle choices, sign out works, and `status` still works |

---

## 7. Verification commands (the plan's own checks)

```bash
# contract grows by exactly the auth paths (44 after Phase 0)
python -c "import json;d=json.load(open('docs/api/openapi.v1.json'));print(len(d['paths']),'paths')"

# Phase 2: the app is closed, the container stays healthy, the tooling still works
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8124/api/library          # 401
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8124/api/health           # 200
curl -s -H "X-RKM-Token: <token>" http://localhost:8124/api/library/folders | head -c 200

# Phase 3: two users, two rails (item ids printed per user)
python tools/rkm_status.py                                       # the deep status behind .\rkm-cinema.ps1 status
curl -s -b /tmp/a.jar http://localhost:8124/api/library/continue-watching | head -c 300
curl -s -b /tmp/b.jar http://localhost:8124/api/library/continue-watching | head -c 300

# no secret ever reaches the browser
grep -rin "jellyfin_token\|rkm_session" frontend/dist | head    # expect nothing sensitive
python -m pytest backend/tests/test_auth_api.py -q               # token/password never in a body or log
```

## 8. Traps (measured or already paid for in this repo)

1. **Do NOT enforce before the login UI exists.** Enforcing first locks the user out of an app with no way
   to sign in — the reason for the phase order in §5 and the `RKM_AUTH_REQUIRED` escape hatch.
2. **`allow_origins=["*"]` + credentials is invalid.** Browsers reject `*` when credentials are included;
   decide CORS in Phase 2 rather than debugging a mystery failed login.
3. **Never put the Jellyfin token in the cookie.** Opaque id + server store, hashed at rest.
4. **Keep the admin token as the fallback.** `runtime.json`'s token is what the provisioner, the bootstrap
   health checks and every tool use; no request context MUST mean "behave as today".
5. **`/api/health` must stay public** (the Dockerfile HEALTHCHECK calls it; an unhealthy api cascades).
6. **Cookie domain vs hostname**: `localhost`, `192.168.x.x` and `rkm-hp.<tailnet>.ts.net` are three cookie
   jars — expected, but OPERATIONS must say so.
7. **`SameSite=Lax`, no `Secure`** while the tailnet is plain http (Tailscale already encrypts transport).
8. **Purge the react-query cache on login/logout**, or the previous user's rows can flash.
9. **Never scope subtitle USAGE counts per user** — they rank one shared download quota (§4).
10. **Do not make the watchlist per-user by reflex** — it is the household acquisition queue (§4).
11. **Protect new routers by construction**: the 401 sweep test (§6 Phase 2) is what stops the next router
    from silently shipping unprotected.
12. **Any new cache must be keyed by user** — a provider cache added later would serve one person's items
    to another.

## 9. Non-goals

- No app-owned password store, no password reset, no self-service signup (Jellyfin owns accounts).
- No household quotas/limits beyond Jellyfin's own per-user settings.
- No change to acquisition (`/api/download`, Radarr/Sonarr) semantics — same behaviour, now attributable.
- No OAuth/SSO, no 2FA.
- No public exposure: the app stays tailnet-only (`docs/TAILSCALE_HOSTING.md`).

## 10. Sizing & risk

~5–7 sittings. New code ≈ 550–750 lines including tests; the frontend is the smaller half.
**Riskiest phases: 2** (enforcement can lock the user out — mitigated by the escape hatch, the public
health route, the machine token and the login UI shipping first) and **3** (identity threading; a wrong
user id silently shows one person another's history, so the live proof must use two accounts).

## 11. Open decisions (recommendations applied unless the user says otherwise)

1. **Session lifetime**: 30 days sliding, refreshed on use (recommended). Shorter means re-logging in on the
   TV browser; longer means a lost device stays signed in.
2. **Sidebar scope**: filter to the user's own `Views` (recommended — that is what per-user means).
3. **Watchlist**: household-shared (recommended, §4).
4. **In-app "add Jellyfin user" flow**: optional Phase 5 (recommended: yes eventually).
5. **Which household members get accounts** — and **who creates the second Jellyfin user** for Phase 3's
   live proof (dashboard is 2 minutes; the in-app flow is the nicety). **Ask before Phase 3.**

## 12. Definition of done (what the next session must leave behind)

- All six phases committed, one per phase, each with its gate green, and pushed.
- `main` fast-forwarded to the auth branch tip, `experiment/bundled-docker-stack` FF'd to match, all three
  refs verified equal; PROGRESS record inserted at the top and this plan marked COMPLETE.
- The user has signed in as **two accounts on two devices** and confirmed separate Continue Watching,
  separate subtitle choices and a working sign out.
- `RKM_AUTH_REQUIRED=false` is documented in OPERATIONS as the lockout recovery, and the machine token's
  rotation steps are written down.
