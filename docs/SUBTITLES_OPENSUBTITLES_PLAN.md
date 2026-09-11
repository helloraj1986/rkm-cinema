# OpenSubtitles + Jellyfin Subtitle Integration Plan — `feat/subtitles-opensubtitles`

**Status: SCOPED 2026-09-12, NOT STARTED. Option A CONFIRMED by the user (2026-09-12); an OpenSubtitles API key is the only outstanding input.** Branch `feat/subtitles-opensubtitles` cut from `main`
(`ceddc50`) with this plan as its first commit. Execute phase by phase, one commit each, gates green
after every phase — same cycle as every other branch in this repo.

Executes the user's spec (2026-09-12): discover, apply and **persist** subtitles for movies and TV
episodes, with a Plex-like in-player subtitle panel and per-subtitle usage counts.

**Scope discipline (the user's words):** do not implement unrelated features and do not refactor
unrelated parts of the application. Every change below belongs to subtitles.

---

## 1. Definition of done — the spec's acceptance criteria, each with a proof

| # | Criterion (from the spec) | Proof the executing session must show |
|---|---|---|
| 1 | Credentials work through `.env` | `docker compose -p rkm-bundled exec api python -c "from config.settings import get_config as g; c=g(); print(bool(c.OPENSUBTITLES_API_KEY), bool(c.OPENSUBTITLES_USERNAME))"` → `True True`; and `grep -rin "opensubtitles" frontend/dist` → 0 hits, `/api/config` exposes no credential field |
| 2 | Relevant subtitles discovered for movies AND episodes | live `GET /api/jellyfin/subtitle-search?id=<movie id>` and `?id=<episode id>` → results with language + provider + download_count |
| 3 | User can select a subtitle from the player | panel screenshot/manual check: pick a result → subtitle applies without leaving the player |
| 4 | Selection survives subsequent playback | store file contains the item; re-open the item → same subtitle listed as selected |
| 5 | Previously selected subtitle is automatically enabled | playback #2 starts with that subtitle active, before the user touches anything |
| 6 | User can disable or change it | "Off" row → persisted; next playback applies nothing. Changing → new selection wins |
| 7 | Usage count persisted and displayed | `POST subtitle-select` twice → `usage.count == 2` in the store; the panel shows "Used 2 times" |
| 8 | Frequently used subtitles can be ranked | search results ordered by our count desc, then OpenSubtitles `download_count` (unit-tested) |
| 9 | Existing local subtitles keep working | embedded + on-disk `.srt` still listed and playable via the existing VTT proxy; no file of ours touched |
| 10 | OpenSubtitles failures never break playback | with credentials blanked / quota exhausted: playback, seek and local subs all still work; only the search section degrades |
| 11 | Credentials never reach the frontend | grep of the served bundle + `/api/config` + every new response body (unit-tested: no token/password/link fields) |
| 12 | Modular, tested, production-ready | new code lives in `services/opensubtitles.py` + `services/subtitle_store.py`; unit tests with a fake transport; ADR; docs; PROGRESS record |

---

## 2. Measured inventory (probed live 2026-09-12 against RKM-HP, Jellyfin 10.11.11)

### 2.1 What Jellyfin already offers (from the server's own OpenAPI)

```
GET    /Items/{itemId}/RemoteSearch/Subtitles/{language}      provider search (needs a provider)
POST   /Items/{itemId}/RemoteSearch/Subtitles/{subtitleId}    download via provider + attach
GET    /Providers/Subtitles/Subtitles/{subtitleId}            provider metadata for one result
POST   /Videos/{itemId}/Subtitles                             upload/attach a subtitle file
DELETE /Videos/{itemId}/Subtitles/{index}                     remove an attached subtitle
GET    /Videos/{itemId}/{mediaSourceId}/Subtitles/{index}/Stream.{format}
```

- **No OpenSubtitles provider is installed.** `/Plugins` lists AudioDB, MusicBrainz, OMDb, Studio
  Images, TMDb only — so `GET /Items/{id}/RemoteSearch/Subtitles/eng` returns `[]` today. The remote
  path is dead until a provider exists.
- The user's Jellyfin configuration carries **no subtitle keys** (`/Users/{uid}/Configuration`), i.e.
  no global subtitle preference has ever been set on this server.
- Local subtitle streams are already fully usable by the app (see 2.2).

### 2.2 What the app already has — build on this, do not rebuild it

- `backend/api/routes/jellyfin_tracks.py`
  - `GET /api/jellyfin/playback-info?id=` → audio + **text**-subtitle tracks + `media_source_id`
    (what the player's pickers read today).
  - `GET /api/jellyfin/subtitle?id=&ms=&index=` → proxies a Jellyfin text subtitle as **WebVTT**.
    Live-verified path: `/Videos/{id}/{src}/Subtitles/{index}/0/Stream.vtt` (the extra `/0/` matters —
    the `Stream?format=vtt` form 404s).
- `frontend/src/features/playback/Player.tsx`
  - Fetches real subtitle cues and paints its own overlay; settings overlay already renders
    `info.subtitles.map(...)` — **the list the new OpenSubtitles results must join**.
  - Persists volume/mute/speed/quality in `rkm.playerPrefs.v1`; **subtitle choice is not persisted
    anywhere**.
- Persistence precedent to copy: `backend/infrastructure/database/repository.py` →
  `JsonWatchlistRepository` (**atomic tmp file + `os.replace` + mtime cache**). A
  `SqliteWatchlistRepository` also exists but is **not** the live backing store.
- `docker-compose.yml`: the **api mounts the media roots read-write**
  (`x-media: &media "${RKM_MEDIA_PATH:-./data}:/data"`, `x-media2`, `x-media3` — no `:ro`), at the
  same container paths Jellyfin reports as item `Path`. The watchlist already proves writes from the
  api land on the host drive in production.

### 2.3 External facts (verified 2026-09-12)

**OpenSubtitles.com REST API v1** — sources: opensubtitles.stoplight.io (docs), apidog.com guide,
`github.com/opensubtitles-dev/opensubs-cli`:

- **`Api-Key` header is MANDATORY on every call** (one key per application, free to register), plus a
  descriptive `User-Agent` (`RKM Cinema vX.Y`). Missing either → 4xx.
- `POST /api/v1/login {username,password}` → **JWT** (required for `/download` and `/infos/user`).
- `GET /api/v1/subtitles?imdb_id=|tmdb_id=&languages=en&season_number=&episode_number=` — **searches are
  not metered**.
- `POST /api/v1/download {file_id}` → `{link, file_name, remaining, reset_time}`; then GET `link`.
- **Quotas (verified 2026-09-12 against OpenSubtitles' own help centre + the login response):**
  **searching is unmetered**; only downloads count. **Anonymous = 5 downloads / 24h per IP**; an
  authenticated user gets more "depending on rank — from 10 for regular users to 1000 for VIP" (a
  free "Sub leecher" account reports `allowed_downloads: 20`). Consumers flagged "Under
  Development" get ~100/day temporarily (official docs) — useful while developing. **Counters reset
  at midnight UTC** (= 10:00 AEST). Rate-limit headers `X-RateLimit-*`; `429` carries `Retry-After`.
  ⚠ A website VIP purchase does not reliably lift the *API* quota (forum reports of VIP accounts
  still capped at 5/day) — never spend money expecting API headroom.
- **Runtime source of truth:** `POST /login` and `GET /infos/user` return `allowed_downloads` +
  `remaining_downloads`, and every `/download` response carries `remaining` + `reset_time`/
  `reset_time_utc`. Phase 1 reads these so the UI can show "N downloads left today" instead of us
  hardcoding a number that varies by rank (and changes over time).
- Results carry `attributes.download_count`, `feature_details.imdb_id/title`, `files[].file_id`,
  `language`, `release`, `hearing_impaired`.

> ⚠ **FINDING THAT CHANGES THE SPEC** — the spec's `.env` block lists only username/password. That is
> **not sufficient**: the API key is mandatory, and `/download` needs the login JWT. So `.env` gains
> `OPENSUBTITLES_API_KEY` (plus the existing two). Flagged to the user rather than silently adopted;
> everything else in the spec's snippet is used verbatim.

**Jellyfin's own OpenSubtitles plugin** exists (installed from the plugin catalogue, then given the
opensubtitles.com account details in its plugin config page). It is **not installed** on this server.
Its config class carries **only `Username`/`Password`** — the user-facing API-key field was removed at
OpenSubtitles' request and the plugin now uses **its own single API key**, so Option B needs *no* API key
from the user, but it still needs their opensubtitles.com **account** credentials typed into Jellyfin's
UI (it cannot run anonymously). Known-good caveat for Option B: the plugin's own sign-in path has a
documented history of failing opaquely (`jellyfin-plugin-opensubtitles` issues #109/#159: endless
spinner, `Authentication to OpenSubtitles failed`, `API rate limit exceeded` with "no activity in the
log file").

### 2.4 Architecture decision

| Option | What it means | Verdict |
|---|---|---|
| **A — api owns the OpenSubtitles client; Jellyfin stores/serves the file** | `services/opensubtitles.py` logs in, searches, downloads; the file is written beside the media file as `<name>.<lang>.srt` and the item is refreshed, so Jellyfin indexes it as a normal external subtitle; the player keeps using the existing VTT proxy | ✅ **RECOMMENDED** |
| B — install Jellyfin's OpenSubtitles plugin, drive `RemoteSearch/Subtitles` | least app code in our repo; Jellyfin downloads + attaches; **no API key needed** (the plugin ships its own — it has no API-key field at all), but the user's opensubtitles.com username/password must be typed into Jellyfin's plugin page | ❌ rejected: credentials would live in Jellyfin's plugin config, **not `.env`** (so the spec's first requirement would be met only by surgical writes into an undocumented plugin XML); the install is a manual dashboard step outside our bootstrap, and while it survives `up -d --build` (it lives in the `jellyfin-config` volume) it **silently disappears on the `down -v` / fresh-provision resets this stack has already needed** (2026-09-10); the spec's usage counts are ours to build either way; the plugin's quota state isn't exposed to our api, and its own sign-in path has a history of opaque failures (issues #109/#159) |
| C — Bazarr container | battle-tested *background* automation | ❌ out of scope for this spec: it has no "pick a subtitle from the player" UX and no usage tracking. Stays a future option for bulk fetching (see §8) |

Why A satisfies the spec: credentials stay server-side in `.env`; all OpenSubtitles logic is isolated in
one service module; **Jellyfin still owns subtitle storage, indexing and serving** (we do not touch the
VTT proxy or the player's rendering); the on-disk `.srt` sidecar is exactly how Jellyfin's own provider
and Bazarr deliver subtitles, so existing local subtitles behave identically.

---

## 3. Design

### 3.1 Config & plumbing (`.env` → `.rkm.env` → api only)

```env
OPENSUBTITLES_API_KEY=          # REQUIRED for any call (free at opensubtitles.com)
OPENSUBTITLES_USERNAME=         # enables the 20/day quota (vs 5/day anonymous)
OPENSUBTITLES_PASSWORD=
OPENSUBTITLES_LANGUAGES=en      # comma list; UI default language
OPENSUBTITLES_ENABLED=auto      # auto = on when API key present; false = off
```

- `backend/config/settings.py`: **declare the attributes on `Config`** (the env passthrough only
  forwards *declared* keys — the 2026-09-10 `RKM_MEDIA_PATH` bug was exactly this), read them in
  `_load()`, and add `has_opensubtitles()`.
- `render_config.py`: pass them into `.rkm.env` (the api container's `env_file`) **only** — never into
  the web build args or the frontend bundle.
- `validate_required()`: **do not** require them (graceful degradation is in the spec). Log ONE clear
  startup line instead, next to the existing "Missing required config" line:
  `OpenSubtitles not configured — subtitle search disabled`.
- `.env.example`: document all five with the quota note and where to get the key.

> ⚠ **How a new `.env` key actually reaches the api — the render step.** The api container has no `.env`
> file at all (it mounts `/app`, `/shared`, `/data`, `/media2`, `/media3`); its configuration arrives as
> environment variables from `.rkm.env`, which is *generated* by `render_config.py` during
> `bootstrap.ps1` / `.\rkm-cinema.ps1 deploy`. So editing `.env` and running only
> `docker compose … up -d --build api` will **not** activate a new key — the container env is stale.
> Activating these credentials needs a **full deploy**. Two consequences to document in OPERATIONS:
> (a) bootstrap re-runs the provisioner, which **cancels an in-flight library scan** — deploy when the
> scan is idle; (b) the stopgap for a scan-in-progress window is to append the same keys to `.rkm.env`
> by hand (that file is the api's `env_file`) and restart just the api. Phase 5 must state this in the
> deploy note, because "pasted the key, rebuilt api, nothing happened" is the exact failure this repo
> has hit before (a value that never arrives, with a green deploy).

### 3.2 Service — `backend/services/opensubtitles.py` (isolated, no Jellyfin imports)

- `OpenSubtitlesClient(config)`: `login()` (JWT cached with TTL, re-login on 401), `search(...)`,
  `download(file_id)` → **bytes**, `user_info()` → remaining quota.
- Search keying, in priority order (spec §2): `tmdb_id` → `imdb_id` → `title`+`year`(+`season`/`episode`).
  IDs come from Jellyfin's `ProviderIds` (the provider already reads `Tmdb`/`Imdb` for similar titles).
- Mandatory `Api-Key`, `User-Agent: RKM Cinema v<app version>`, `Accept: application/json`.
- Error taxonomy → typed exceptions, never a raw stack: `NotConfigured`, `AuthFailed`,
  `QuotaExhausted` (429 / `remaining == 0`), `RateLimited` (with `Retry-After`),
  `NoResults`, `UnsupportedFormat`, `TransportError`.
- Timeouts (5s connect / 15s read) and **one** retry on transport errors; everything else fails fast.
- Never log the password, the JWT, or the download `link` (it embeds a token).

### 3.3 Delivery to Jellyfin — `attach_subtitle(...)`

1. Resolve the media file path from Jellyfin's item `Path` (already a container path the api shares).
2. Write `<video stem>.<lang>.srt` beside it (atomic tmp + `os.replace`, same as the watchlist writer),
   converting to UTF-8; if a sidecar for that language already exists, **reuse it** unless the user
   picked a different subtitle (then overwrite the file we own, and never touch files we did not write).
3. `POST /Items/{item_id}/Refresh` (`MetadataRefreshMode=FullRefresh`? — Phase 2 decides the lightest
   refresh that surfaces the new stream. **Never** a library-wide scan: it is expensive and cancels an
   in-flight scan.) Fallback if the write fails: `POST /Videos/{itemId}/Subtitles` upload.
4. Re-read `playback-info` and return the new track list so the player can apply it immediately.

### 3.4 Persistence — `backend/services/subtitle_store.py`

One JSON file beside the watchlist (`<media root>/rkm/subtitles.json`), written atomically, corrupt-file
tolerant (log + start empty, never crash), and never rewritten by hand:

```json
{
  "prefs": {
    "<jellyfin item id>": {"subtitle_id": "os:123456", "language": "en", "provider": "opensubtitles",
                           "display_title": "Movie.2019.1080p.WEB-DL", "disabled": false,
                           "updated": "2026-09-12T04:00:00Z"}
  },
  "usage": {
    "123456": {"media_id": "<jellyfin item id>", "subtitle_id": "os:123456", "language": "en",
               "provider": "opensubtitles", "display_title": "...", "count": 24,
               "last_used": "2026-09-12T04:00:00Z"}
  }
}
```

- `count` increments on select; `last_used` updates. Ranking = our `count` desc, then OpenSubtitles
  `download_count` desc.
- **JSON, not SQLite**, deliberately: it matches the live store (`JsonWatchlistRepository`) and its
  atomic-write pattern, adds no dependency and no schema migration — which the scope discipline
  forbids. The `SqliteWatchlistRepository` in the tree stays untouched (its activation is a separate,
  unrelated decision). *Open decision for the user — see §9.*

### 3.5 API surface (additive only — ADR-0001)

| Endpoint | Purpose |
|---|---|
| `GET /api/jellyfin/subtitle-search?id=&language=` | merged list: the item's **local** tracks + **OpenSubtitles** results, each with `used_count` + `last_used` + `active` flag |
| `POST /api/jellyfin/subtitle-select` | `{item_id, subtitle_id, language, provider, display_title}` → download + attach + persist + increment; returns the refreshed track list |
| `POST /api/jellyfin/subtitle-disable` | `{item_id}` → persist `disabled: true` |
| `playback-info` (existing) | **additive** field `preferred_subtitle` (`null` when none/disabled) so the player needs no extra round trip on load |

Contract: 38 → **41 paths**; regenerate `docs/api/openapi.v1.json` + `frontend/src/lib/api/types.ts`
(`npm run generate:types`) in the same commit, diff reviewed as additions only.

### 3.6 Auto-apply resolution — indices are POSITIONAL, identity is not

The trap that will otherwise bite: a Jellyfin subtitle stream `Index` changes when tracks are added or
removed (exactly what our own download does). So:

- Persist the **identity**: `provider` + `subtitle_id` + `language` + `display_title`.
- On load, resolve identity → current index: exact `display_title` match → else same-language match
  among external tracks → else **apply nothing** and show the picker (never silently substitute a
  different subtitle).
- `disabled: true` → apply nothing, do not clear the record (so re-enabling is one tap).
- Embedded/in-container subtitles are never modified.

### 3.7 Player UX (spec §4)

In the existing settings overlay, the Subtitles block becomes:

```
Subtitles
  ( ) Off                                    ← persisted disable
  (•) English · embedded                     ← local, as today
  ( ) English · OpenSubtitles · Used 24 times ← ours
      [ Search OpenSubtitles (English) ]      ← inline, does not leave the player
```

- Results show language · provider · `Used N times` · release (and OpenSubtitles `download_count` as
  secondary info, clearly ours vs theirs).
- In-flight state: per-row spinner; errors as toasts ("Daily download limit reached (20/day) — try
  again after <reset>"), never a blocked player.
- The active row is marked; applying happens immediately via the existing cue-loading path.

---

## 4. Traps (measured or repo-proven — read before coding)

1. **A BOM in `.env` breaks the first key.** Measured: `render_config.py:101,122` read the env file with
   `encoding="utf-8"` (not `utf-8-sig`), and the user's spec snippet literally starts with a BOM. If the
   key is pasted with one, the parsed name becomes `\ufeffOPENSUBTITLES_API_KEY` and the feature dies
   silently. Fix in Phase 0: strip a leading BOM in the parser (and tolerate BOMs) so a pasted block
   cannot do this.
2. **The two env parsers do not agree on quoting.** Measured: `render_config.parse_env_file()` handles
   comments, `export`, and quotes (a quoted value is taken verbatim; an unquoted one has its inline
   comment stripped), while `settings.py::_load()`'s file path does a bare `partition("=")` + `strip()`
   with **no quote handling** — so `KEY='p#ss'` reaches a bare-checkout api with the quotes included.
   In the bundled stack the rendered `.rkm.env` is what the api actually receives, so production is fine
   — but a dev run without docker would see different values. Phase 0: make the container-side read
   agree with the renderer, and document the quoting rule. Matters here because a password containing
   `#` (or a space) is otherwise truncated.
3. **Config passthrough only forwards DECLARED keys.** A new env var that isn't declared on `Config` is
   dropped before the app ever sees it — this exact bug (2026-09-10, `RKM_MEDIA_PATH`) produced "all
   libraries disabled" from a green deploy.
4. **Stream indices are positional** → §3.6. Store identity, resolve the index at playback time.
5. **Never send the OpenSubtitles `link` to the browser.** It carries a token in the query string. The
   api downloads the bytes and hands back only our own metadata.
6. **The quota is the user's real limit** (20/day signed in). Surface `remaining` in the UI, and never
   spend downloads in automated tests — unit tests use a fake transport; the live check spends exactly
   one, deliberately.
7. **Do not fight local subtitles.** Existing `.srt`/embedded tracks keep their behaviour; our store only
   expresses a preference. Never rewrite or delete a subtitle file we did not create.
8. **Deduplicate.** Skip a download when (item, provider, `file_id`) is already attached, or a sidecar for
   that language already exists and is the one recorded.
9. **Text formats only.** `.srt/.vtt/.ass/.ssa` are usable; `.sub/.idx` (bitmap) and `.zip` are not —
   detect and reject with a clear message rather than attaching something unplayable.
10. **Encoding.** Prefer UTF-8; detect a BOM; verify the VTT proxy handles one non-UTF-8 sample (Phase 2).
11. **Refresh the ITEM, not the library.** A library scan is expensive and (per OPERATIONS.md) cancels an
    in-flight scan — the exact way to break the user's indexing.
12. **Write access from the api container** is assumed from the rw mounts and proven by the watchlist, but
    Phase 0 must confirm a write lands on the host drive (Windows bind mounts via Docker Desktop can be
    quirky), before the design leans on it.
13. **Single-user assumption.** The app is one-user; prefs are per item, not per user. Do not build
    multi-user scoping (that is an unrelated roadmap item).

## 5. Phases (one commit each; gates green after every phase)

Gate per phase: `cd backend && python -m pytest -q && python -m ruff check .`; from Phase 3 also
`cd frontend && npx tsc --noEmit && npx vitest run && npm run build`.

- **Phase 0 — config plumbing + probe (no behaviour).** Declare the five settings; render them into
  `.rkm.env`; BOM tolerance in the env parser; `has_opensubtitles()`; one startup log line; `.env.example`
  documented. Confirm: keys visible inside the api container, **absent** from the built frontend bundle
  and `/api/config`, and a test write from the api container lands on the media drive.
  *Gate proof:* `grep -rin opensubtitles frontend/dist` → 0; new config tests.
- **Phase 1 — `services/opensubtitles.py` + tests.** Login/JWT cache, search (id-first keying), download,
  `user_info`, typed error taxonomy, quota/rate-limit handling, redaction. Unit tests with a fake
  transport cover: success, bad key (401), bad login, 429 with `Retry-After`, `remaining == 0`, timeout,
  empty results, non-text format. **No live calls in the suite.**
- **Phase 2 — attach to Jellyfin + dedupe.** Sidecar write (atomic, UTF-8), item refresh (lightest that
  works), `POST /Videos/{itemId}/Subtitles` fallback, re-read playback-info. Live-verify with exactly ONE
  real download against RKM-HP: the new track appears in `playback-info` and plays through the existing
  VTT proxy. Record the quota cost in the commit message.
- **Phase 3 — store + routes + contract.** `services/subtitle_store.py` (atomic, corrupt-tolerant, usage
  increment, ranking) + the three endpoints + the additive `playback-info.preferred_subtitle`; regenerate
  snapshot + typed client; route/store tests.
- **Phase 4 — player UX.** Panel section as §3.7 (Off / local / OpenSubtitles rows, inline search,
  per-row busy, toasts, active marker), auto-apply on load via the resolution rules, pure helpers
  (`rankSubtitleResults`, `resolveActiveSubtitle`, `usedCountLabel`) unit-tested with vitest, plus the
  harness still passing `tools/measure_player_layout.py` (10/10 viewports).
- **Phase 5 — hardening + docs + record.** Failure paths end-to-end (creds blanked, quota exhausted,
  network down): playback, seek and local subs unaffected. Docs: `.env.example`, README, ARCHITECTURE
  (§ subtitle flow), OPERATIONS (symptom→command row), **ADR-0005** (new external dependency +
  credential handling + why the plugin was rejected), PROGRESS record, then the user's rebuild + eyeball.

## 6. Verification commands (the plan's own checks)

```bash
# credentials configured, server-side only
docker compose -p rkm-bundled exec api python -c "from config.settings import get_config as g;c=g();print(c.has_opensubtitles(), bool(c.OPENSUBTITLES_API_KEY))"
grep -rin "opensubtitles" frontend/dist frontend/src/lib/api/types.ts   # expect: no credential fields

# discovery works for a movie and an episode (live)
python3 tools/probe_subtitles.py "3 Deewarein"        # local tracks + provider status
curl -s "http://localhost:8124/api/jellyfin/subtitle-search?id=<item>&language=en" | head -c 400

# contract is additive only
python -c "import json;d=json.load(open('docs/api/openapi.v1.json'));print(len(d['paths']),'paths')"   # 41

# store integrity + usage
python3 -c "import json;d=json.load(open('<media root>/rkm/subtitles.json'));print(list(d),{'counts':[v['count'] for v in d['usage'].values()]})"

# existing behaviour untouched
cd frontend && npx vitest run && cd .. && python3 tools/measure_player_layout.py   # 10/10 viewports
```

## 7. Non-goals (explicitly out of scope)

- Replacing/absorbing Bazarr, or any library-wide *automatic* subtitle downloading (§8).
- Subtitle synchronisation/offset shifting, OCR of bitmap subs, or transcoding subtitles.
- Uploading subtitles to OpenSubtitles, or any contribution flow.
- Multi-user preference scoping; changing the watchlist store; activating the SQLite repository.
- Any change to the existing VTT proxy, cue rendering, or the player layout.
- Installing Jellyfin plugins (Option B) — rejected, see §2.4.

## 8. Roadmap note

The parked 2026-09-09 item *"Bazarr auto-subtitles (needs an OpenSubtitles account)"* is **not**
superseded, it is **split**: this branch delivers the on-demand in-player path (spec above); bulk
background fetching for the whole library remains a separate, later decision. The store in §3.4 is
designed so a future bulk fetcher could reuse it without a schema change.

## 9. Sizing

| Phase | Effort |
|---|---|
| 0 config + probe | short (one sitting, mostly plumbing + the BOM fix) |
| 1 service + tests | one sitting (the real work: API client + error taxonomy) |
| 2 attach + dedupe | one sitting; riskiest step (write permissions, refresh behaviour, format/encoding edge cases) |
| 3 store + routes + contract | one sitting |
| 4 player UX | 1–2 sittings (panel + auto-apply + helpers) |
| 5 hardening + docs | short |
| **Total** | **~4–6 sittings**, new code ≈ 600–800 lines incl. tests |

Riskiest single step: **Phase 2's attach/refresh** — it writes to the user's media drive and must surface
the stream without triggering a library scan.

## 10. Open decisions (status as of 2026-09-12)

1. ✅ **DECIDED — Option A** (the user confirmed it): the api owns the OpenSubtitles client; **no Jellyfin
   plugin is installed**. Do not revisit §2.4.
2. **API key** — still needed, but smaller than first written: an **anonymous** consumer works for
   **5 downloads / 24h**, so Phase 1–2 can go live with just the key; adding the opensubtitles.com
   username/password lifts it to ~20/day and is recommended before the user relies on it. Register at
   opensubtitles.com → *API Consumers* → new consumer named e.g. `RKM Cinema`; put it in the repo `.env`
   (gitignored) as `OPENSUBTITLES_API_KEY=...`. Phase 1 reads `allowed_downloads`/`remaining_downloads`
   at runtime, so the UI reports the real number rather than a hardcoded one.
3. **Store**: JSON sibling file (recommended, no migration) vs the existing SQLite repository.
4. **Default languages**: `en` only, or also others (e.g. `hi`, `ta`)? Drives the UI default list.
