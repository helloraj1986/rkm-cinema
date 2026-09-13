# RKM Cinema — Architecture

> **Identity: read §11 and [`adr/ADR-0006`](adr/ADR-0006-delegated-identity-and-sessions.md) before
> touching anything that calls the media server.** Since 2026-09-12 the app has a session per browser
> and a *profile* per person, and the credential a call is made with is decided in ONE place
> (`api/session.py`). A route that skips that seam serves one household member another's library —
> silently, and with no error anywhere.

> ⚠ **2026-09-08:** repo restructured into a monorepo (`REPO_STRUCTURE_PLAN.md`)
> and the legacy vanilla app removed (branch `chore/remove-legacy-app`):
> **`backend/`** holds the FastAPI app + tests, **`frontend/`** the React/TS shell
> (renamed from `web/`) — now the only UI; the `/legacy` route, `frontend/legacy/`
> and the `rebuild_dashboard.py` static dashboard generator are gone (archived in
> `tools/archive/`). Deploy/infra + docs stay at the root. The authoritative
> project tree + commands live in `../README.md`.

> **Single codebase.** The monolithic `api.py` has been archived
> (`tools/archive/api_legacy_monolith.py`) and the production backend is now the
> modular FastAPI app: **`uvicorn api.main:app`** (see `backend/Dockerfile`). There is
> exactly ONE implementation of each business rule. Add features to the modular
> tree, not a parallel monolith.

---

## 1. What this is

A self-hosted **media library, player and acquisition dashboard** for one household. It:

- Shows what's in your **Jellyfin** library (source of truth for availability) and recently added.
- **Plays it in the browser** — same-origin HLS/MSE through the api, so no media URL or server
  credential is ever exposed to the client.
- Lets you **request** movies/series, which are added to **Radarr** (movies) or **Sonarr** (TV) and downloaded via **qBittorrent**.
- Tracks each title through a lifecycle: requested → downloading → downloaded → available → recommended (history).
- Deep-links each available title straight into **Jellyfin**'s own web UI.
- Fetches **posters/backdrops/genres** from **TMDB**, **trailers** by scraping `youtube.com` (no YouTube API key), and **subtitles** from OpenSubtitles.com (optional, ADR-0005).
- **Signs people in and keeps them apart.** One administrator holds the server session; everyone else
  picks a *profile* on the who's-watching screen, and each profile gets its own Continue Watching,
  history and subtitle choices. The watchlist (the acquisition queue) and the subtitle download
  quota stay deliberately **shared** — see §11.

Access is private over **Tailscale**, and — since `RKM_AUTH_REQUIRED` was armed — the app itself is
closed: the browser talks to nginx on :8124, nginx proxies `/api/*` to the FastAPI container (which
holds all secrets), and every route but `/api/health` and the sign-in routes needs a session.

---

## 2. High-level layout

```
 Browser (Tailnet device)
      │  http://rkm-hp.tail8d5e8.ts.net:8124
      ▼
 ┌──────────────────────────────┐
 │  nginx (web container) :8124 │   serves the React shell (frontend/)
 │  ─ proxies /api/* → api:8000 │
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐
 │  FastAPI  api  container     │   uvicorn api.main:app  (modular)
 │  /api/health /config /status │   holds RADARR_KEY, SONARR_KEY, JELLYFIN_KEY…
 │  /api/download /search       │
 │  /api/library /jellyfin/*    │
 │  /api/quality                │
 └───────┬──────────┬───────────┘
         │          │   read /write
         ▼          ▼
 ┌────────────┐  ┌───────────────────────────────┐
 │ watchlist  │  │  External: Jellyfin·Radarr     │
 │ .json (ro) │  │  Sonarr·TMDB·qBittorrent·YT    │
 └────────────┘  └───────────────────────────────┘
```

---

## 3. Repository layout

```
rkm-cinema/                       (full annotated tree in ../README.md)
├── backend/                      FastAPI app + pytest suite + Dockerfile
│   ├── api/                      main.py app factory + routes/ (thin routers)
│   ├── services/                 external integrations + app services
│   │   ├── library/ acquisition/ recommendation/ reconciliation/  (canonical)
│   │   ├── radarr.py sonarr.py tmdb.py youtube.py
│   │   ├── qbittorrent.py watchlist.py media_status.py recommendations.py
│   ├── domain/                   business layer: state machine + resolver
│   ├── core/  config/  infrastructure/  application/  jobs/
│   ├── scripts/                  daily pipeline + probes
│   ├── provisioner/              bundled-stack Jellyfin provisioner
│   └── tests/                    unit + API tests (mockable, no live LAN)
├── frontend/                     React 18 + TS + Vite shell (the only UI)
├── docs/                         architecture, plans, ADRs, API contract,
│                                 OPERATIONS.md, PROGRESS.md, ARCHITECTURE.md
├── nginx/  scripts/  tools/      web config; backup/restore; diagnostics
├── docker-compose.yml  bootstrap.ps1  bootstrap.sh  render_config.py  rkm-cinema.ps1
└── README.md  .env (single config)  .env.example (committed template)
```

Run everything from the subdirs: `cd backend && python -m pytest tests/ -q`,
`cd frontend && npm run typecheck && npx vitest run && npm run build`.
Deploy stays at the root (`.\\bootstrap.ps1`, wrapped by `.\\rkm-cinema.ps1 deploy`).

---

## 4. Dependency direction (the contract)

```
 React shell (frontend/src)
      ↓  /api/*            one client: frontend/src/lib/api/client.ts
 API routes (api/routes/*)         thin: validate → call service → map response
      ↓                           every app router publishes the identity (§11)
 Domain + app services (services/)  business rules once, in one place
      ↓
 External service clients (services/*, core/http_client)  isolated URL/auth/HTTP
      ↓
 Jellyfin · Radarr · Sonarr · TMDB · qBittorrent · YouTube
```

Rules:
- Routes **never** call external APIs directly or build raw `urllib` calls.
- Services **never** leak secrets; the browser never sees keys/URLs (nginx fronts `/api`).
- The `domain/` state machine + resolver are the **single owners** of status and movie/tv rules.
- **The credential a call is made with comes from `api/session.py` only** (`acting_media_token` /
  `owner_media_token`). Build a URL with a token from anywhere else and that call silently acts as the
  administrator — §11.

---

## 5. Endpoints — and what each one requires

**The frozen contract is the list** (`api/openapi.v1.json`, ADR-0001: additive-only). What matters
architecturally is the LEVEL of each route, and that is declared and enforced in
`tests/test_route_protection.py::ROUTE_LEVELS` — *the* inventory: it fails if a route ships without a
decision, and a second test fails if a session route is not on the Phase-5 dependency.

| Level | Count | Meaning |
|---|---|---|
| **PUBLIC** | 1 | `GET /api/health` — the Docker HEALTHCHECK calls it; a 401 here marks the api unhealthy and cascades |
| **auth-route** | 6 | `/api/auth/*` — reachable signed out (sign-in cannot require a session) and deliberately **not** behind the credential probe: they are the FIX for a refused credential |
| **session** | 36 | everything else in the app — the identity is published for the request (§11) |
| **ADMIN** | 11 | `require_admin_session`: a Jellyfin **administrator**, strictly, *even while* `RKM_AUTH_REQUIRED` is false. The 6 `/api/admin/*` household routes plus the four operational ones Phase E gated (`POST /api/download`, `POST /api/jobs/{name}/run`, `GET /api/library/scan`, `POST /api/reconcile`) |

Grouped by what they are for:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service up/down flags (radarr, sonarr, tmdb, qbit, jellyfin) + `degraded`. **Public** |
| `POST /api/auth/login\|logout` · `GET /api/auth/me` | The session: sign in (administrator only), revoke server-side, who am I |
| `GET /api/auth/profiles` · `POST /api/auth/profile` | "Who's watching?" — the picker's list and the switch (which re-authenticates as that profile) |
| `POST /api/auth/profile/password` | Change **your own** password (proves the current one). The administrator's reset of somebody else is a different route, by design |
| `GET /api/config` | Public-safe booleans + dashboard freshness (never keys/URLs) |
| `GET /api/status` | Per-title state via the `Reconciler` → `domain.status.resolve_status()`; includes the watch url + item id |
| `POST /api/download` | Add movie→Radarr / series→Sonarr (title fallback, "pick one" ambiguity). **Admin** |
| `GET /api/search` · `/api/search/global` | Watchlist + live TMDB search; owned media + discovery |
| `GET /api/library*` | Counts, folders, per-folder items, continue watching, recently watched, episodes |
| `GET /api/jellyfin/poster\|person\|backdrop` | Same-origin artwork proxy — the api key stays server-side |
| `GET /api/jellyfin/stream\|hls` · `POST /api/jellyfin/progress` | In-browser playback + watch-state reporting |
| `GET·POST /api/jellyfin/subtitle-*` | Subtitle search/select/disable (ADR-0005) |
| `GET /api/quality` | Radarr/Sonarr quality profiles for the download dialog |
| `GET /api/admin/*` | Household: list accounts, grant libraries, create/rename/policy/password/delete. **Admin**, and refused while somebody else's profile is selected |
| `POST /api/jobs/{name}/run` · `GET /api/library/scan` · `POST /api/reconcile` | Operational verbs (a full scan, a generic job, a reconcile pass). **Admin** |

---

## 6. Media status state machine

The canonical resolution lives in `domain/state_machine.py::resolve_status`:

```
 the server has it → AVAILABLE        (with the watch link + item id)
 else *arr has file → DOWNLOADED
 else qBittorrent active → DOWNLOADING (progress/speed/eta)
 else *arr queue  → DOWNLOADING
 else *arr record exists → REQUESTED ("waiting — indexers down" if health says so)
 else             → NOT_ADDED
```

**The media server (Jellyfin) is the source of truth** for availability. A title
it holds is `available` even if its *arr record is stale/missing. The `Reconciler`
gathers the external facts and feeds them to `resolve_status`; the domain module
decides. The `WatchLinks` value object carries `library_available`, `watch_url`
and `server_item_id` (the server's own item id, not a URL) for
`available`/`downloaded` titles.

> **Performance guard:** the Jellyfin provider caches its full item listing (60 s
> window) and the reconciler caches its whole result on the watchlist file's
> mtime. The status pass asks for every watchlist entry; without those caches one
> `/api/status` request re-scanned the library per entry and blew the request
> window.

---

## 7. Download flow

1. Frontend `POST /api/download` → `DownloadService.download(...)`.
2. Media type resolved by **`domain/resolver.py`** (single authoritative rule):
   explicit `type` → watchlist `isSeries` → Radarr/Sonarr lookup → default movie.
3. `RadarrService.add_movie` / `SonarrService.add_series`:
   - Lookup by `imdb` first; if it resolves nothing, **fall back to title (+year) search**.
   - Unique match → used. Multiple matches, none exact → **`ambiguous`** ("pick one" list), never a silent guess.
4. Cross-service fallback: a "No Radarr match" on a real series retries Sonarr (and vice-versa).
5. `DownloadResult` (typed domain object) maps to `DownloadResponse` with predictable HTTP codes (404 ambiguous, 502 unavailable, 503 not configured).

---

## 8. Watch links (Jellyfin only)

There is exactly ONE media server (Jellyfin, bundled) and it is the only source of
watch links — the Plex/Emby providers were removed on 2026-09-11
(`adr/ADR-0004-remove-plex-emby-support.md`).

Two ways to watch an available title, both same-origin:

- **In-app playback** (`jellyfinItemId`): the recorded item id drives
  `/api/jellyfin/stream|hls` through the same proxy the browser already talks to,
  so no token or cross-origin request is involved.
- **Deep link** (`jellyfinUrl`): `{browser base}/web/index.html#!/details?id={itemId}`
  on the browser-reachable host. The base is config-driven — `JELLYFIN_BROWSER_URL`
  (defaults to the Tailscale MagicDNS HTTPS host, see `TAILSCALE_HOSTING.md`). The
  container-internal `JELLYFIN_URL` is the api's own address and is **never** used
  to build a user link.

The `/api/status` payload therefore carries `jellyfinUrl` + `jellyfinItemId`; the
reconciler's snapshot keeps a `watch` map keyed by provider name, holding the
`jellyfin` entry's `available` / `url` / `item_id`.


## 9. External integrations

| Service | Responsibility |
|---|---|
| `RadarrService` | Movies, `lookup_movie`, `search_movies` (title fallback), `add_movie`, profiles/queue, indexer health |
| `SonarrService` | Series, `lookup_series`, `search_series` (title fallback), `add_series`, tvdb resolve, profiles/queue |
| `TMDBService` | Movie/show details, posters/backdrops/genres, search |
| `YouTubeService` | Scrape youtube.com for the official trailer (no API key) |
| `QBittorrentService` | Torrent list + download-state (used by status) |
| `TrailerService` | Legacy trailer fallback |
| `OpenSubtitlesClient` | Subtitle search/download/quota from OpenSubtitles.com (`services/opensubtitles.py`) — isolated: no Jellyfin imports, no app state. **The app's only credential besides the media server and TMDB**; its key reaches the api only (see ADR-0005) |
| `WatchlistService` | Atomic watchlist persistence + state validation |
| `MediaStatusService` | Per-entry status via the domain state machine |
| `DownloadService` | Movie/tv routing + add + fallback orchestration |
| `RecommendationService` | Quality gates, library/duplicate checks, enrichment, add |

All services accept injectable `config`/`http` (constructor DI) and are unit-tested
with fakes — **no test touches the live LAN**.

---

## 10. Config & data

- **`config/settings.py`** — single `Config` singleton from the repo `.env` (+ env overrides). Provides `has_jellyfin()`, `has_tmdb()`, `validate_required()`, etc. **Never returns secrets via `/api/config`.** Exposes the browser-reachable `JELLYFIN_BROWSER_URL` used only for deep-links (falls back to the Tailscale host when unset), and the ONE media-server rule `resolve_media_server()` — jellyfin is the default AND the fallback for a blank/unknown value, so a missing key can never select a retired backend. `validate_required()` deliberately does **not** demand a media-server credential (a fresh install has none until the provisioner writes it; `/api/health` reports that state).
- **`watchlist.json`** — the household acquisition queue; volume-mounted into the container at `/app/watchlist.json`. `WatchlistService` auto-resolves the correct path (container vs sandbox). Deliberately **shared** by every profile (§11).
- **Sessions** — `<media root>/rkm/sessions.json` beside the watchlist, so an api rebuild does not sign
  the household out. Written `0600`, atomically, and holding the **sha256** of each session id, never
  the id and never a Jellyfin token. Corrupt-tolerant: an unreadable file starts empty (everyone signs
  in again; nobody is stuck).
- **`.env`** — canonical at `/workspace/.env`, never committed; see `.env.example`. 

---

## 11. Identity: sessions, profiles, and the one place a credential comes from

Read [`adr/ADR-0006`](adr/ADR-0006-delegated-identity-and-sessions.md) first: this section is the same
model as built. The app owns **sessions**, Jellyfin owns **accounts**.

```
 browser ── rkm_session cookie (HttpOnly, opaque) ─┐
                                                   ▼
                                      api/session.py::require_live_credential     (per app router)
                                                   │  resolves the cookie → SessionContext
                                                   │  asks the media server: is this credential accepted?
                                                   ▼
                                       contextvar  ──►  acting_media_token()  ──►  provider / raw URLs
```

**The two identities in one session.** `user_*` is the account that signed in to the server (always an
administrator); `profile_*` is who is WATCHING. With no profile chosen the profile IS the owner, so an
old session behaves exactly as it did. `acting_media_token()` answers with the profile's token,
`owner_media_token()` with the account's — and the difference is the whole feature: media and watch
state use the first, account administration uses the second.

**The rail.** `session_context_from_request` RECORDS that a request arrived as somebody.
`_published_identity` then refuses (`UnpublishedIdentityError`) if a route resolved a session and
published nothing, instead of falling back to the app's own key — that fallback once wrote a password
to the wrong account while reporting success. Three states, three answers: no request context
(provisioner, scheduler, tools, tests) ⇒ the app's own key, unchanged; a request as nobody ⇒ the same;
a request as SOMEBODY with nothing published ⇒ an error. `owner_media_token` is the ONE deliberate
exception (its fallback *is* the administrator by definition).

**One dependency, per router.** `api/main.py::SESSION_SCOPED = [Depends(require_live_credential)]` —
not a `Depends` on ~40 endpoints, because a site that forgot it would silently serve one person's
library to another. It must be `async def`: a sync dependency runs in a worker thread whose context is
a COPY, so the contextvar would be discarded and every user would share one identity with no error
anywhere.

**Two 401s, two answers.** The dependency asks the media server whether the credential it is about to
act as is still accepted (`credential_is_accepted`, `/Users/<id>?api_key=…`, cached 20 s). A definite
refusal becomes `401` + `X-RKM-Auth-Problem`:

| Marker | What is wrong | What the app does |
|---|---|---|
| `session` (or no marker — an older api) | the cookie is gone or stale | the login view; the sign-out rule is unchanged |
| `profile-token` | the cookie is fine, the credential the PROFILE acts as is refused | keeps the session, drops the fetched rows, sends the person to "Who's watching?" with the server's sentence (`guardDecision({profileStale})`) |

Without this, a refused profile credential was **silent**: media calls came back empty and the app said
"you have no library". `/api/auth/*` is deliberately NOT behind the probe — it is the fix.

**One device per session.** Jellyfin invalidates the previous token of a `(device, user)` pair on every
login, so `new_session_device_id()` mints `rkm-cinema-web-<hex>` per sign-in and a profile switch
re-authenticates on it. A caller that NAMES a device keeps it — that is why the operation tools sign in
on `rkm-tools` (a diagnostic must not rotate the browser's token away).

**What stays shared (deliberate — do not "fix" these).** The watchlist (the household acquisition
queue), subtitle **usage** counts (they rank one download quota), and the server itself.

---

## 12. Frontend (React + TypeScript shell)

`frontend/` is a Vite + React 18 + TypeScript SPA — **the only UI** (the legacy `app.js`/`api.js` and
`frontend/legacy/` were deleted on 2026-09-08). It is **baked into the web image** by
`frontend/Dockerfile` (`npm run build` → `nginx:alpine`), so a UI change needs `.\\rkm-cinema.ps1 apply`
— it is not volume-mounted any more.

- **`src/lib/api/client.ts`** — the ONE HTTP client (`api.*`), `credentials: "same-origin"`, and the
  app's single auth rule: a 401 fires the sign-out handler **once per burst** (`noteUnauthorized`).
  Since Phase 5 that rule reads `X-RKM-Auth-Problem` and fires a *different* handler for
  `profile-token` — signing out there would throw a live session away. Auth-route calls pass
  `{ skipAuthRedirect: true }`: a wrong password is the form's business, and `me()` saying 401 is the
  ordinary signed-out answer.
- **`src/features/auth/`** — `AuthProvider` (session + profile state; purges the React Query cache on
  every identity change, so one person's rows can never flash for the next), `RequireSession` +
  `guardDecision` (**pure, unit-tested**: skeleton / login / picker / app), `LoginView`,
  `AccountMenu` (one menu off the avatar: Switch profile · My password · Household for administrators).
- **`/login` and `/profiles` sit OUTSIDE the app shell** for the same reason: they must render when
  nothing else can — including the day enforcement is armed and every other route is refusing.
- **Browser checks.** `frontend/harness/*.html` are frames that mount real views over a stubbed api;
  `tools/check_*.py` drive them headless (login flow, picker, nav access, household, password,
  library scan, subtitle panel). Run them against `npx vite --port 5199`.

---

## 13. Deployment

- Deploy (RKM-HP / Windows): **`.\\rkm-cinema.ps1`** — one script, every verb. `apply` (make the running stack match this folder: re-render `.env`, rebuild + restart `api`/`web`), `deploy` (`apply` + the Jellyfin provisioner), `auth on|off`, `status`, `logs`, `backup`/`restore`, `schedule`, `diagnose`, `reset-admin-password`. `bootstrap.ps1` and `rkm.ps1` are one-line forwarders to it, kept so older notes still work.
- Three containers: `api` (FastAPI modular, holds secrets) + `web` (nginx :8124, the built React shell + `/api` proxy, **including `location = /openapi.json`** so `tools/check_deployed.py` can compare the running api's contract), plus the bundled `jellyfin` media server.
- ⚠ **Editing `.env` alone changes nothing** — a container reads its environment when it STARTS. `apply` (or `auth on|off`) is what applies it.
- **The media server is reached over Tailscale** (HTTPS via the MagicDNS host); deep-links must target the browser-reachable `JELLYFIN_BROWSER_URL` host, not the container-internal `JELLYFIN_URL` (see §8).

---

## 14. Adding a feature (recommended path)

1. **Business rule (status/movie-tv)?** → put it in `backend/domain/` (state machine or resolver). Wire service gatherers in `backend/services/`.
2. **External integration?** → add a method on the relevant `backend/services/*` client; never in a route.
3. **Route?** → add a thin handler in `backend/api/routes/`, reuse a service, return a typed Pydantic model.
4. **UI?** → update the React shell (`frontend/src/`).
5. **Test it** → add a mockable pytest under `backend/tests/`; run `cd backend && python -m pytest tests/ -q`.
6. No static dashboard rebuild exists any more — the React shell reads the live `/api` (the old `rebuild_dashboard.py` static generator was removed with the legacy app).
7. Deploy with `.\\rkm-cinema.ps1 apply` (rebuilds `api` + `web` from this folder) and confirm with
   `.\\rkm-cinema.ps1 status` — the "Is the running api the code in THIS folder?" section answers MATCH
   or names the difference. A **new route** also needs a line in
   `tests/test_route_protection.py::ROUTE_LEVELS` (the test fails without one) and, if it touches the
   media server, to ride the session dependency (§11) — never its own token.

---

## 15. Testing

- `backend/tests/` cover: the status resolver + state machine, media-type resolver, Radarr/Sonarr routing + title fallback + ambiguity, duplicate prevention, error handling, trailer validation, the library provider + factory (one backend: Jellyfin), the `LibraryService` collapse and watch-link failure containment, the reconciler, recommendation pipeline, and API endpoints.
- All tests use **injected fakes** — no real LAN, no real API keys required.
- Run: `cd backend && python -m pytest tests/ -q` (all green; count moves with the suite — see `PROGRESS.md` for the current number).

---

## 16. Subtitles (OpenSubtitles) — additive, optional, never blocking

Read `adr/ADR-0005-opensubtitles-integration.md` before changing any of this. The shape:

```
  player picker  ──►  /api/jellyfin/subtitle-search   ──►  OpenSubtitles.com  (search: unmetered)
        │                    │                                  │
        │                    └──►  the item's OWN tracks  (always listed, never altered)
        │
        └── click a result ──►  /api/jellyfin/subtitle-select
                                     │  download (METERED — never retried)
                                     ├─► write  <video stem>.<lang>.srt  beside the media (atomic,
                                     │     UTF-8; reused if a same-language sidecar already exists)
                                     ├─► POST /Items/{id}/Refresh        (the ITEM — never a scan)
                                     └─► store the CHOICE (an identity, not an index) + count the use
                                                   │
  playback-info.preferred_subtitle  ◄──────────────┘   (ONE additive field: the player applies it on load)
```

The three rules that are easy to get wrong:

1. **Preferences store an IDENTITY, never a stream index.** Jellyfin's indices are
   positional and our own download shifts them; `resolveActiveSubtitle()` resolves the
   identity to the current index at load time and applies NOTHING when it no longer
   matches — never a different subtitle.
2. **The tick belongs on the row the user CLICKED.** A delivered subtitle arrives as a
   local track the server names generically ("English - SUBRIP - External"), so ticking the
   resolved index ticks a row the user never chose. `activeSubtitleRowKey()` (frontend,
   unit-tested) marks exactly one row: the chosen result, else the local track applying.
3. **A subtitle failure degrades the feature, never the app.** Every vendor failure is
   reported as a `warning` on a 200 listing (never a 500), the item's own subtitles are
   always returned, and only an action the user explicitly asked for (select) can fail the
   request — with an honest status: 503 not configured, 502 credentials/transport, 429
   quota/rate limit, 400 bad format. `tools/check_subtitle_panel.py --fail-search` proves
   the panel still lists and can still apply the local tracks with the vendor dead.

State: `<media root>/rkm/subtitles.json` — `prefs` (per item: provider, `subtitle_id`,
language, display title, `disabled`) and `usage` (per subtitle: count, last used). Atomic
writes, corrupt-tolerant, JSON by design. The quota is read from the API at runtime — never
hardcoded — and the UI shows a number only when the API has actually reported one.
