# Plan: per-user identity via Jellyfin + app sessions (multi-user)

**Status: SCOPED 2026-09-12, NOT STARTED.** Branch `feat/auth-multiuser`, cut from `main`; this plan is
the branch's first commit. Execute phase by phase, ONE commit per phase, gates green after every phase.

**User decisions (2026-09-12):** this is the next feature; the goal is **real per-user state for the
household, with identity delegated to Jellyfin** (not a shared password, not app-owned accounts).
Native Jellyfin collections (app-authored, visible in Jellyfin's own apps) is **queued behind this plan**.

---

## 1. What this delivers, in one line

Every request is made **as the signed-in Jellyfin user**, so Continue Watching, resume positions,
watched flags and library visibility become per-person for free — because Jellyfin already models all of
them per user — while the app's own stores gain a user key only where they genuinely need one.

## 2. Why delegated identity (and why now)

- **Jellyfin is already a multi-user media server.** `/Users/{uid}/Items`, `/Items/Resume`,
  `/Users/{uid}/PlayedItems/{id}`, `/Users/{uid}/Items/{id}/UserData` and `/Users/{uid}/Views` are all
  per-user. The app currently calls every one of them with the **single admin token** from
  `runtime.json`, so the whole household shares one watch history.
- **Measured inventory (2026-09-12, live against RKM-HP):**
  - Jellyfin users on the server: **1** (`admin`, administrator, enabled) — so "household" also means
    *creating Jellyfin users* and granting them library access.
  - `/Users/{uid}/Views` for `admin` returns `['Movies', 'Movies Kids', 'TV Shows']` — per-user library
    visibility is a real, already-populated thing.
  - The api surface: **41 contract paths**, **20 registered routers**, and the Jellyfin provider builds
    its URLs with one token at **21 `api_key=` sites**.
  - `build_library_service(config, *, http=None)` is called **18 times** across the routes — always
    per request, never once at startup. That is what makes per-request identity feasible without a
    rewrite.
  - The app's own stores are **single-user by construction**: `data/rkm/watchlist.json` has no user key,
    and subtitle preferences are per **item** (the subtitle plan says so explicitly: "prefs per item,
    not per user").
  - **No auth exists anywhere:** no security dependency or session code in `backend/api/**`,
    no `auth_basic`/`auth_request` in `nginx/default.conf`, and CORS is `allow_origins=["*"]`.
    Reachability is the only protection today (`docs/TAILSCALE_HOSTING.md`: `tailscale serve`,
    tailnet-only, never funnel).
  - The frontend has **no** 401 handling, no login route, no session concept.
  - The PowerShell tooling calls the app on exactly two paths: `GET /api/health` and
    `GET /api/library/folders` (from `scripts/*.ps1` via `tools/rkm_status.py`).

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
   the store holds `sha256(id) → {user_id, user_name, jellyfin_token, created, expires, last_seen}`.
   Why: logout is a real revocation (delete the row), the Jellyfin token never reaches the browser, and
   a container rebuild does not log everyone out (the store lives on the bind-mounted media root).
   Same trust level as `runtime.json` (`/shared/runtime.json`, verified as the api's token source) —
   write it `0600`. The store path follows the existing convention `/data/rkm/<name>.json`, i.e. on the
   bind-mounted media root, which is also why it survives a rebuild.
   A signed-cookie design was rejected: revocation would need a second mechanism, and the token would
   then travel on every request.
2. **`services/auth.py`** — the session store: create / lookup / touch / revoke / prune, atomic writes
   (same discipline as `subtitle_store.py`), corrupt-tolerant, and **never logs a token or a password**.
3. **FastAPI dependency** `require_session` — resolves the cookie, refreshes `last_seen`, and publishes
   the session into a `contextvar`. The app's paths depend on it; `/api/health` and `/api/auth/*` do not.
4. **Token resolution in the provider**: `_token()` returns the contextvar's token when one is set,
   else `config.JELLYFIN_API_KEY`. This keeps **one** diff point instead of threading a token through
   18 call sites and 21 URL builds — and it fails safe: no request context (provisioner, tools, tests)
   behaves exactly as today.
5. **Per-user caches are already isolated**: `_item_cache`, `_folders_cache`, `_server_id_value` and
   `_user_id_value` live on the provider instance, which is built per request. Confirm no global cache
   is keyed by item id alone before relying on this.
6. **Machine access** for the repo's own tooling: `RKM_API_TOKEN`, generated by `render_config.py` the
   same way `RKM_JELLYFIN_ADMIN_PASSWORD` is, sent as `X-RKM-Token`. The PowerShell verbs keep working
   unchanged in behaviour. An IP/localhost bypass was rejected: the api sits behind nginx **and is not
   published on the host at all** (verified: `docker-compose.yml` maps only `web:8124` and jellyfin's
   port — nothing for `api`), so it cannot see a trustworthy client address to trust.
7. **Frontend**: a `/login` route outside the authenticated shell, an `AuthProvider` reading
   `GET /api/auth/me`, a global 401 → redirect-to-login handler in `lib/api/client.ts`, a user chip with
   **Sign out** in the header, and `queryClient.clear()` on login/logout so no household member's data
   flashes for the next one.
8. **Per-user libraries**: the sidebar is config-driven (`MEDIA_LIBRARY_*`). It will be **filtered to the
   user's own `/Users/{uid}/Views`**, so a restricted Jellyfin user sees a restricted app.

## 4. What is per-user and what stays shared (the deliberate calls)

| Thing | Decision | Why |
|---|---|---|
| Continue Watching, resume, watched flags, play count | **Per user** (free — Jellyfin's own) | It is the whole point; no app-side model needed |
| Library visibility | **Per user** (filtered by that user's Views) | Otherwise a kids' account sees everything |
| Subtitle **preferences** | **Per user** (additive migration, old key read as a fallback) | "My subtitle for this film", not the household's |
| Subtitle **usage counts** | **Shared/household** (unchanged) | They rank results and spend ONE shared download quota — a per-user count would misreport it |
| Watchlist (`watchlist.json`) | **Shared** (unchanged) | It is the household ACQUISITION queue: one request per film, not one per person |
| Player prefs (volume/speed/quality) | **Per browser** (localStorage, already) | Nothing to do |
| Download/acquisition actions | Any signed-in user | Same as today's behaviour, now attributable |

## 5. Phases (one commit each; gates green after every one)

Gate: `cd backend && python -m pytest -q && python -m ruff check .`; from Phase 3 also
`cd frontend && npx tsc --noEmit && npx vitest run && npm run build`.

- **Phase 0 — session store + endpoints (purely additive, nothing enforced).** `services/auth.py`;
  `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`; cookie set/clear; the
  `require_session` dependency and the contextvar seam exist but no route uses them yet. Contract
  41 → 44 paths; snapshot + typed client regen. Tests: login success/failure, cookie flags, revocation,
  expiry, corrupt store, and that no response or log line ever carries the Jellyfin token or password.
  **Proof it is additive:** every existing test and the whole app behave identically; `status` unchanged.
- **Phase 1 — enforcement + machine access.** Every app path requires a session; `/api/health` and
  `/api/auth/*` stay public; `X-RKM-Token` grants machine access; `render_config.py` generates
  `RKM_API_TOKEN` into `.rkm.env` (and `.env.example` documents it); `tools/rkm_common.py` sends it.
  Tests: 401 without a cookie, 401 with a bad/expired one, machine token works, **the Docker
  `HEALTHCHECK` still passes** (it calls `/api/health`), and `tools/rkm_status.py` still reports.
- **Phase 2 — per-request Jellyfin identity.** `_token()` resolution, `_user_id()` follows the session's
  user, per-user `Views` filtering for the sidebar. Live verification with **two** Jellyfin users:
  different Continue Watching, different resume positions, watched flags that do not bleed between them.
- **Phase 3 — frontend.** Login view, auth guard, 401 handling, user chip + sign out, cache clearing on
  switch. Gates + a harness/DOM check for the login → player path.
- **Phase 4 — per-user subtitle preferences.** Additive migration with a read-fallback to the flat key;
  usage counts stay shared. Tests for the fallback and for two users holding different choices.
- **Phase 5 — docs + record.** `ARCHITECTURE.md` (auth section + endpoint table), `OPERATIONS.md`
  (symptom rows: locked out, add a household member, token rotation), `README.md` (features + config),
  `.env.example`, **ADR-0006** (this is a BREAKING contract change — ADR-0001 requires it be explicit and
  recorded), PROGRESS record, then the user's deploy + eyeball with two accounts on two devices.

## 6. Acceptance criteria (each with its proof)

1. Without a session, every app path answers **401**; `/api/health` still answers 200 — proof: pytest +
   `docker compose … ps` showing the api healthy.
2. Signing in as two different Jellyfin users gives **two different Continue Watching rails** — proof: the
   two-browser live check, with the item ids printed for each.
3. Watched flags and resume positions do not bleed between users — proof: mark watched as A, read as B.
4. The Jellyfin token never reaches the browser: no cookie value, response body or log line contains it —
   proof: a test that asserts the token string is absent from every response of the auth flow.
5. Sessions survive an `api` rebuild — proof: log in, `docker compose up -d --build api`, the cookie still
   works (the store is on the media root).
6. The repo's own tooling keeps working — `.rkm-cinema.ps1 status` reports normally — proof: its output.
7. A restricted Jellyfin user sees only their libraries — proof: compare `/api/library/folders` per user.
8. Existing local subtitles keep working per user; a user's own choice is theirs — proof: two users, two
   different choices on one item.

## 7. Traps (measured or already-paid-for in this repo)

1. **`allow_origins=["*"]` + credentials is invalid.** Browsers reject `*` when credentials are included.
   The UI is same-origin behind nginx (the cookie flows regardless), so CORS must either list explicit
   dev origins or stay credential-free. Decide this in Phase 0, not after a mystery failed login.
2. **Never put the Jellyfin token in the cookie.** Opaque id + server store; the store hash is what is
   compared, so a leaked store does not yield usable session ids.
3. **Keep the admin token as the fallback.** `runtime.json`'s token is what the provisioner, the
   bootstrap health checks and every tool use. If `_token()` has no request context it MUST fall back —
   otherwise a bootstrap breaks the app it just built.
4. **`/api/health` must stay public.** `backend/Dockerfile`'s `HEALTHCHECK` calls it; requiring a session
   would mark the container unhealthy, and with `depends_on` that cascades to the rest of the stack.
5. **Cookie domain vs Tailscale hostname.** `localhost`, `192.168.x.x` and `rkm-hp.<tailnet>.ts.net` are
   three different cookie jars — expected, but say so in OPERATIONS so a "logged out on my phone" report
   has an answer.
6. **`SameSite=Lax`, not `None`**, and no `Secure` flag while the tailnet is plain http (Tailscale already
   encrypts the transport); flipping `Secure` on would silently break login over http.
7. **Purge the react-query cache on login/logout.** Otherwise the previous user's rows can flash.
8. **Don't scope the subtitle USAGE counts per user.** They rank a shared download quota; per-user counts
   would misreport "how often we used this" and misrank the list.
9. **Two users, two per-user stores, one stale-cache risk**: any provider-level cache added later must be
   keyed by user, or it will serve one person's items to another.
10. **Do not make the watchlist per-user by reflex.** It is the acquisition queue (see §4) — that is a
    deliberate product decision, not an oversight.

## 8. Non-goals

- No app-owned password store, no password reset flow, no self-service signup (Jellyfin owns accounts).
- No household restrictions/quotas beyond what Jellyfin already enforces per user.
- No change to acquisition (`/api/download`, Radarr/Sonarr) semantics — same behaviour, now attributable.
- No OAuth/SSO, no 2FA (Jellyfin has no TOTP API of its own here).
- No public exposure: the app stays tailnet-only (`docs/TAILSCALE_HOSTING.md`).

## 9. Sizing & risk

~4–6 sittings. New code ≈ 500–700 lines including tests; the frontend is the smaller half. **Riskiest
step: Phase 2** — threading identity into a provider whose 21 URL builds assume one token, and proving
two users genuinely do not see each other's state. Second risk: Phase 1's enforcement breaking the
repo's own tooling (mitigated by `RKM_API_TOKEN` + keeping `/api/health` public).

## 10. Open decisions (recommendations applied unless the user says otherwise)

1. **Session lifetime**: 30 days sliding, refreshed on use (recommended). Shorter means re-logging in on
   the TV browser; longer means a lost device stays signed in.
2. **Sidebar scope**: filter to the user's own `Views` (recommended — that is what per-user means).
3. **Watchlist**: household-shared (recommended, §4).
4. **An admin "add Jellyfin user" flow** (create a user + grant libraries from inside the app, Jellyfin
   admins only): **include as an optional Phase 5** — without it, adding a household member is a Jellyfin
   dashboard chore. It is additive and can ship separately.
5. **Which household members** get accounts (the app needs at least one non-admin user to *verify* per-user
   behaviour, so Phase 2's live check requires a second Jellyfin user to exist).
