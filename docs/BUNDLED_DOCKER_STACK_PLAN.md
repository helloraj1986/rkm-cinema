# RKM Cinema — Bundled Self-Contained Stack (Preliminary Design / Exploration)

> ⚠️ **Status: PROPOSAL — nothing built yet.** This is the exploration + design document for an
> **experimentation branch** (`experiment/bundled-docker-stack`) that makes RKM Cinema a
> **fully self-contained, one-command deploy**: Sonarr + Radarr + Prowlarr + qBittorrent + a
> media server + the RKM app itself, **all in Docker Compose**, wired up automatically.
>
> A fresh user should be able to:
> ```bash
> git clone <repo> && cd rkm-cinema
> cp rkm.config.example.toml rkm.config.toml   # fill in TMDB key + an indexer
> ./bootstrap.sh                                 # everything else is automated
> ```
> and get a working discovery → download → watch pipeline with **zero manual service setup**.

---

## 0. The core question that shapes everything: which media server?

Your instinct ("plex can't run on docker") is **almost right but for the wrong reason**. Plex
**absolutely runs in Docker** (`plexinc/pms-docker`, ~35M+ pulls). The actual problem is
**friction and licensing**, and it decides the whole architecture. Full comparison below.

| Axis | **Plex** | **Emby** | **Jellyfin** |
|---|---|---|---|
| Docker image | `plexinc/pms-docker` | `emby/embyserver` | `jellyfin/jellyfin:10.11.x` |
| License | **Proprietary** (freemium) | **Proprietary** (was OSS) | **FOSS (GPLv2), 100% free** |
| Account required | **YES — mandatory** plex.tv account | No | **None** |
| First-run setup | plex.tv **claim token** (expires in **4 minutes**) + account, phones home | Web wizard, offline | Web wizard, **fully offline** |
| Hardware transcoding | **Paid** (Plex Pass $120) | **Paid** (Premiere $119) | **Free — included** |
| Docker networking | needs `network_mode: host` for discovery/DLNA (inflexible) | bridge OK | bridge OK |
| App integration today | **Primary / source-of-truth** — fully built | **Fallback** — fully built | ⚠️ **None** (only dead legacy `JELLYFIN_*` config keys) |
| Deep "Watch" links | Built (`/web/index.html#!/...`) | Built (`/web/index.html#!/item?...`) | Easy (`/web/index.html#!/details?id=...`) |

**Why this matters for "zero install":** a bundled stack that *defaults* to Plex forces every user
to create a plex.tv account, hand you a time-limited claim token, and accept telemetry — which
directly contradicts "user doesn't have to install anything / just run the script." Jellyfin is the
only one with **no account, no licence gate, no paid HW-transcode wall, runs fully offline** — it
is the philosophically and practically correct **default** for a distributable stack.

The catch is the **app's codebase**: RKM Cinema is written **Plex-first** (source of truth for
availability = Plex) with Emby as fallback. There is **no Jellyfin service**. So choosing Jellyfin
isn't free — it needs one small refactor on the branch.

---

## 1. Recommended answer: make the media backend **pluggable**, default **Jellyfin**

Rather than rebuild around one choice, do one clean refactor and keep all three:

```text
MEDIA_SERVER=jellyfin        # default (zero-friction, self-contained)
MEDIA_SERVER=plex            # existing Plex-first behaviour, zero app change
MEDIA_SERVER=emby            # existing Emby fallback
```

The branch introduces a small **`LibraryProvider`** interface in `services/library/` (pick one of
`JellyfinProvider`, `PlexProvider`, `EmbyProvider`) selected by config. The current
Plex-primary/Emby-fallback logic becomes "the configured provider(s), in order." This is the 
**single biggest piece of app work** and it's small because the app already isolates library work
behind `services/library/service.py`.

**Bottom line (viability):**
- **Jellyfin default** → cleanest "clone & run," real refactor (add ~1 provider).
- **Plex / Emby** → zero-to-minimal app change, but user pays the account/claim/licence cost and
  it's not truly "install nothing."

This table is the decision the doc funnels to; it's worth ~10 min of discussion before building
(see §11).

---

## 2. Target stack (all one Compose project)

```text
                    ┌───────────────────────────────────────────────┐
                    │            docker compose "rkm"               │
                    │                                               │
   browser ──► :8123 │  web (nginx)  ──/api──►  api  (rkm-cinema)    │
   (dashboard)      │      │                │   │   │   │   │   │    │
                    │      │                │   │   │   │   │   │    │
   direct ports     │      ▼                ▼   ▼   ▼   ▼   ▼   ▼    │
   :32400/:8096 :7878 :8989 :9696 :8080      └──┴──┴──┴──┴──┴──┴──┘  │
   jellyfin │ plex    radarr  sonarr prowlarr qbt    (all on the     │
   (or emby)                     │  ▲      │          same bridge)   │
        ▲                          │  └─────┘            ▲            │
        │            indexers ────►┘              ┌──────┴──────┐     │
        │                                          torrent data      │
   /data/media/{_tv,_movie}  ◄────────── hardlink/atomov ────┘     │
   (shared, identical path in every container)                      │
        └────────── RKM api reads Plex/Jellyfin for "is it here?" ─┘ │
                    +(TMDB metadata, youtube trailers: EXTERNAL)     │
                    └───────────────────────────────────────────────┘
```

| Service | Image | Internal | Purpose |
|---|---|---|---|
| `api` | `rkm-cinema-api` (build) | :8000 | RKM backend (unchanged logic, new provider + config loader) |
| `web` | `nginx:alpine` | :80 → host :8123 | UI + reverse-proxy `/api/*` |
| `radarr` | `linuxserver/radarr` (or `hotio/radarr`) | :7878 | Movies: search + download via qBittorrent |
| `sonarr` | `linuxserver/sonarr` | :8989 | Series: search + download via qBittorrent |
| `prowlarr` | `linuxserver/prowlarr` | :9696 | Single source of indexers, synced to Radarr/Sonarr |
| `qbittorrent` | `qbittorrentofficial/qbittorrent-nox` | :8080 | Torrent client (no GUI needed — `-nox`) |
| `jellyfin` **(default)** | `jellyfin/jellyfin` | :8096 | Media server + web UI |
| `plex` *(optional alt)* | `plexinc/pms-docker` | :32400 | If `MEDIA_SERVER=plex` |
| `emby` *(optional alt)* | `emby/embyserver` | :8096 | If `MEDIA_SERVER=emby` |
| `provisioner` | one-shot, runs then exits | — | Configures everything via each app's API |

All on one **bridge network named `rkm`**, so internals talk by **service name** — no LAN IPs
needed (`RADARR_URL=http://radarr:7878`, `PLEX_URL=http://jellyfin:8096`, etc.). That alone
removes the "I need a pre-existing media stack" prerequisite from today's app.

> Note on images: **linuxserver** images are the conventional, well-documented choice for the
> *arr stack and Prowlarr; **official nox** for qBittorrent; **official** for Jellyfin/Plex. Include
> PUID/PGID + timezone as config so Linux-host file ownership is sane.

---

## 3. The one honest prerequisite you cannot automate

Everything on the LAN is now bundled, but **external credentials cannot be invented by a script**:

1. **A TMDB API key** — free, from the TMDB settings page. Required for metadata/artwork/Suggest.
2. **At least one indexer** — the *arr apps need a torrent source. This is the app's only
   genuinely external dependency. Options, in order of automation ease:
   - **Public indexers** via Prowlarr (YTS, 1337x, RARBG-clones, TorrentLeech…). Many are
     keyless but fragile — note **Australian ISPs block many public torrent indexers** under
     s115a court orders (this stack's known failure mode; expect `CloudFlare blocked` /
     `403` / dead swarms). Packaged default = a small curated list in the config, all optional.
   - **Private trackers** (user already has accounts/API keys) — best reliability, required for
     an actually-working out-of-the-box experience for seeds.
   - This is exactly what the **config file's `[indexers]`** section is for (§5).
3. **Optional:** if `MEDIA_SERVER=plex`, a **plex.tv account + claim token** (grab from
   `plex.tv/claim` `right before` boot; it expires in 4 min).

Everything else — creating download clients, root folders, quality profiles, pointing Radarr →
Prowlarr → qBittorrent, creating the Jellyfin library, wiring RKM to all of it, seeding the cron —
the **provisioner** does automatically.

---

## 4. `bootstrap.sh` / `bootstrap.ps1` — the one command

Two thin launchers (bash + PowerShell — the repo already ships a `.ps1` style flow) that just:

```text
1. Check prerequisites: docker + docker compose present & daemon up (clear error otherwise)
2. If no rkm.config.toml  → copy example, print "edit me" checklist, exit (or --yes flag)
3. docker compose --profile "$MEDIA_SERVER" up -d --build     # starts every container
4. Wait for each /health (radarr/sonarr/prowlarr ping, jellyfin System/Info/Public, api /api/health)
5. docker compose run --rm provisioner                          # does ALL integration (below)
6. Recreate `api` so it re-reads the generated runtime config
7. Fire the first reconcile + a test Recommend/Suggest (optional)
8. Print: dashboard URL, each service URL, qBittorrent creds, jellyfin/plex first-login note
```

No Docker CLI reachable / daemon unreachable is a hard, informative error (the project already
knows Docker Desktop can be absent — see `run-rkm-cinema.ps1`).

---

## 5. Config file design: `rkm.config.toml` (one file configures the world)

The ask was "a docker config file can have all the configuration details." A **TOML** file is the
clearest for this; the bootstrap renders it into compose `environment:`/`env_file:` and into the
provisioner. Everything user-facing is here; nothing is hardcoded.

```toml
# ---- Identity / branding (feature request: app name etc.) ----
[app]
name = "RKM Cinema"
host_port = 8123            # dashboard port on host
timezone = "Australia/Melbourne"
puid = 1000
pgid = 1000

# ---- Storage ----
[storage]
base_path = "./data"        # single data root; MUST stay one filesystem for hardlinks
media_path = "media"        # → ./data/media  (subfolders _tv, _movie auto-created)
downloads_path = "downloads" # → ./data/downloads
# If you already have a media dir, point media_path at an absolute host path.

# ---- Media server backend (the §1 decision) ----
[media_server]
backend = "jellyfin"        # jellyfin | plex | emby
# jellyfin only:
jellyfin_admin_user = "admin"
jellyfin_admin_password = "CHANGE_ME"     # provisioner sets + creates an API key
# plex only (account + claim token, 4-min expiry):
plex_claim = "claim-REPLACE"              # from https://www.plex.tv/claim
# branch/Watch URLs for deep-links (leave blank → derive from host port):
browser_base_url = "http://localhost:8123"

# ---- Download automation ----
[*arr]
quality = "1080p"           # any of 480p/720p/1080p/2160p → creates quality profiles
# Optional quality-profile ID overrides (if you have existing profiles)
radarr_quality_profile_id = 0    # 0 = auto-create
sonarr_quality_profile_id = 0
root_tv = "_tv"             # folder names under media_path
root_movie = "_movie"
import_mode = "hardlink"    # hardlink | copy | move (hardlink preserves seeding + disk)
# Most download errors (double disk, import failing, seeding broken) come from getting this wrong.

[qbit]
webui_port = 8080           # host + internal
torrent_port = 6881
username = "admin"
password = "CHANGE_ME"      # if blank → provisioner generates a random one + prints it
# If you use a VPN container (AU s115a!), set this and the stack routes qbit through gluetun:
# vpn = true
# vpn_container = "gluetun"

# ---- Indexers (the one external dependency, §3.2) ----
[indexers]
# Prowlarr is bundled automatically; it just needs sources to feed it.
# Each entry: {name, definition (1337x/yts/etc), key (optional), base_url}
entries = [
  # { name = "yts",  definition = "YTS",  key = "" },
  # { name = "1337x", definition = "1337x", key = "" },
  # { name = "my-tracker", definition = "TorrentLeech", key = "PRIVATE_KEY" },
]
prefer_synced_indexers = true   # Radarr/Sonarr use Prowlarr as a single "All" indexer

# ---- Recommendation / AI-auto-add job (the question §6) ----
[recommend]
# The "AI agent cron job" = in-container scheduler (no host cron needed in the bundle).
auto_add_enabled = true
auto_add_hour = 18          # daily job time (24h)
reconcile_interval_min = 10
# If false, the Suggest tab (manual) is the only discovery path — no automation runs.

# ---- Metadata ----
[tmdb]
api_key = "REPLACE_ME"      # required
[tvdb]
api_key = ""                # optional
[trailers]
provider = "youtube_scrape" # no key needed; official trailers scraped

# ---- Hardware transcoding (media server) ----
[transcode]
# Free on Jellyfin; paid (Pass/Premiere) on Plex/Emby.
backend = "auto"            # auto|none|vaapi|qsv|nvdec ; pass /dev/dri or nvidia runtime when set
# docker auto-detects and injects: devices: - /dev/dri:/dev/dri   OR   runtime: nvidia
```

> Design rule: **the TOML is the source of truth**; the bootstrap generates `.env`/compose
> `environment` blocks from it, so there is one place to configure, not three. Secrets in TOML are
> git-ignored (the committed file is only `rkm.config.example.toml`).

---

## 6. "AI agent cron job if it chooses, otherwise Suggest tab takes care of it"

Maps cleanly onto the app's **existing** design — no new feature needed:

- **Auto path (AI recommendation job):** the app already has an **in-process scheduler**
  (`WATCHLIST_SCHEDULER=true` runs reconcile every N min + a daily TMDB-discover → Plex/Jellyfin-gate
  → auto-add job). Today in production that runs from a **host cron**. In the bundle the scheduler
  lives **inside the `api` container**, so **no host cron and no separate process**. Toggle with
  `[recommend] auto_add_enabled` — default **on**, so it's "if the user chooses to."
- **Manual path (Suggest tab):** unchanged; the user opens the dashboard and picks titles. When
  `auto_add_enabled = false`, Suggest is the only discovery entry point — exactly "otherwise the
  suggest tab can take care of it."
- The reconcile job (keeps status/facts fresh every 10 min) should stay on regardless.

This is arguably the strongest part of reusing RKM's architecture: **the hard 10% (desired-state
orchestration, idempotent recommendations, Plex-as-source-of-truth, trailer routing) is already
built**; the branch is mostly *plumbing* (provisioning + new provider + config plumbing).

---

## 7. The provisioner (the automated "integration" work)

A single one-shot container (small Python using `requests` — it's effectively a script the app
already knows) that configures every service **via its own public API** so a user never opens a UI:

1. **Prowlarr**: for each `[indexers].entries`, create the indexer (definition + key). Record the
   API key.
2. **Radarr**: create download client of type `QBittorrent` (host `qbittorrent`, port `:8080`,
   creds from config/generated), create root folder `/data/media/_movie` (if absent), create/match
   a quality profile (e.g. `1080p`), sync the "All" indexer from Prowlarr. Store `RADARR_API_KEY`.
3. **Sonarr**: same as Radarr for `/data/media/_tv` + `SONARR_API_KEY`.
4. **Media server** (per `MEDIA_SERVER`):
   - **Jellyfin**: create admin user (if absent), create an **API key**, create Media Libraries
     (`Movies` ← `/data/media/_movie`, `TV` ← `/data/media/_tv`) via `POST /Library/VirtualFolders`.
   - **Plex**: first boot claims via `PLEX_CLAIM`, then create sections + add folders, read back
     `PLEX_TOKEN` from `/identity`/config.
   - **Emby**: existing Emby library-create flow (app already speaks it).
5. **Write runtime config** to a shared volume (`/shared/runtime.json`): all service URLs (internal
   hostnames), API keys, qbit creds, media-server URL+token, quality profile IDs, root folders.
6. **RKM `api`** reads that runtime file (see §8) → last bootstrap step recreates `api` to pick it up.

Everything is **idempotent** (check-then-create; on re-run it reconciles, never duplicates) — same
discipline the app's recommendation/reconcile jobs already follow. The provisioner can also
re-run later via `docker compose run --rm provisioner` to repair drift.

---

## 8. How the app wires to the *new* in-bundle services (small changes)

Today `config/settings.py` reads `.env` URLs pointing at a `MEDIA_HOST` LAN IP and requires
`RADARR_API_KEY`, `SONARR_API_KEY`, `PLEX_TOKEN` to be preset. For the bundle:

1. **Internal hostnames** — the bundled `.env`/runtime sets `RADARR_URL=http://radarr:7878`,
   `SONARR_URL=http://sonarr:8989`, `PROWLARR_URL=http://prowlarr:9696`,
   `QBITTORRENT_URL=http://qbittorrent:8080`, and the media-server URL to the in-bundle host.
   The app already resolves these through the same `_normalize_url` path — **no provider needs a
   real host address**.
2. **Runtime-config loader** — add a tiny loader so `Config` can pull keys/URLs from the
   provisioner-written `/shared/runtime.json` (falling back to `.env` first, as today). This is the
   seam that lets the provisioner "install" the app's own credentials.
3. **Pluggable library provider** (§1) — `MEDIA_SERVER` selects `JellyfinProvider` (new) vs
   `PlexProvider`/`EmbyProvider` (existing) for availability + deep-links.
4. **qBittorrent auth** — today `services/qbittorrent.py` assumes **no auth** (port 1701). Bundled
   qbit should have a password. Add optional `QBITTORRENT_USERNAME/PASSWORD` support (two small
   changes) so the stack is secure by default.

These four are the *only* app-code deltas. The rest of RKM (domain state machine, recommend
criteria, request flow, trailer routing, dashboard) is untouched.

---

## 9. Storage & the hardlink rule (get this right or nothing imports)

The most common "everything's running but downloads never import" cause is **path mismatch between
download client, *arr, and media server**. The bundle avoids it by mounting **one host directory
with identical internal paths everywhere**:

```text
./data/
├── media/
│   ├── _tv/       ← seen as /data/media/_tv in sonarr AND jellyfin
│   └── _movie/    ← seen as /data/media/_movie in radarr AND jellyfin
└── downloads/     ← seen as /data/downloads in qbit, radarr, sonarr (for import)
```

Because they share one volume, Sonarr/Radarr can **hardlink** (inode link) a finished torrent from
`downloads/` into `_tv`/`_movie` — **no extra disk space, torrent keeps seeding**. `import_mode =
hardlink` is the default. If the user later splits to a second disk, they must set `copy`/`move`
and accept the trade-off (this is config-documented, not hardcoded).

---

## 10. Networking & external access

- **Internal:** everything on the `rkm` bridge → service names (`radarr`, `jellyfin`, …) work
  from the `api` container. Plex is the one caveat: `plexinc/pms-docker` is happiest on
  `network_mode: host`, which conflicts with shared-bridge DNS. → That's a real reason **Jellyfin
  is architecturally the cleaner default** (no host-networking requirement). If Plex is forced, the
  Plex container goes on `host` and everything else resolves it via the host IP.
- **External (browser) access:** dashboard on `:8123`; optionally Plex/Jellyfin on `:8096`/`:32400`.
  All host ports are configurable in TOML. The existing **Tailscale** story (deep-links point at a
  MagicDNS host; `browser_base_url` in TOML) carries over unchanged.
- The RKM `web` nginx already proxies `/api/*` → `api`; remote-access hardening (VPN, mTLS, or
  `tailscale serve`) is out of scope for v0 but documented.

---

## 11. Risks, trade-offs, and the honest "zero-install" caveat

**Verdict:** very viable and high leverage — the app is 90% built for this; the branch is ~10%
plumbing + ~1 refactor.

| Risk / trade-off | Mitigation |
|---|---|
| **Indexers are external & flaky** (esp. AU s115a blocks) | Config-driven curated list; clear "indexers down" surfacing already in the app; optional VPN container hook |
| **Plex forces account+claim token+host-net** (if chosen) | Default **Jellyfin**; keep Plex as opt-in alt |
| **qBittorrent auth** differs from today's no-auth | Small app change to support creds; generate strong password |
| **Provisioner chicken-and-egg** (needs services up before config exists) | Provisioner runs *after* health checks; `api` recreated last reads runtime config |
| **Hardware transcode passthrough** varies by host GPU | Config `[transcode] backend`; auto-inject `/dev/dri` or nvidia runtime; free on Jellyfin |
| **"Install nothing"** still needs Docker + external keys | Be explicit: ONE prerequisite (Docker Desktop) + TMDB + ≥1 indexer (and plex.tv account only if Plex) |
| Repo has no Jellyfin provider yet | Small `LibraryProvider` refactor + `jellyfin.py` (reuse Emby base) |
| Port collisions on host | All ports configurable in TOML |

---

## 12. Phased implementation plan on the branch

**Phase A — config + compose skeleton (small, testable)**
- `rkm.config.example.toml` + a `render_compose.py` that validates & writes `.env`/compose `environment`.
- `docker-compose.yml` with `radarr/sonarr/prowlarr/qbittorrent/jellyfin` + profiles for `plex`/`emby`.
- `bootstrap.sh` + `bootstrap.ps1` (health-gated startup).

**Phase B — provisioner**
- `provisioner/` one-shot container: Prowlarr→Radarr→Sonarr→Jellyfin→ runtime.json (all idempotent).
- Verify with the live in-bundle stack (smoke test: add a movie end-to-end in Docker).

**Phase C — app provider + config deltas**
- `LibraryProvider` refactor, `services/library/jellyfin.py`, `MEDIA_SERVER` config, runtime-loader,
  qBittorrent auth support. Keep all 216 existing tests green; add provider/loader tests.

**Phase D — recommend/auto-add wiring + polish**
- In-container scheduler on by default (`auto_add_enabled`), reconcile always on; Suggest unchanged.
- Smoke test the full loop headless: TMDB discover → auto-add → Radarr/Sonarr grab → qbit → import →
  Jellyfin indexes → status flips to `available` → Watch link renders.

**Phase E — docs + a README for the branch** (prereqs, config reference, FAQ, troubleshooting).

---

## 13. Open decisions to settle before Phase A (this is what we should discuss)

1. **Media backend default: Jellyfin (recommended) vs Plex vs keep-always-Plex.** This is the
   single decision that changes the refactor scope most.
2. **qBittorrent security: password by default (recommended) vs match today's no-auth.**
3. **AI auto-add: default ON (recommended, since you framed it "if user chooses") vs default OFF.**
4. **Indexers:** ship a curated *public* list + let users add private keys, or default empty and
   require the user to supply indexers? (Empty is the honest default but a worse first-run.)
5. Any **app-name/branding** defaults you want baked into the TOML `[app]` section.

Decisions 1–4 are config that radically change the *out-of-box experience*; the architecture itself
handles every value. Recommend we lock #1 = **Jellyfin default** and go.