# RKM Watchlist

A clean, maintainable media recommendation and download orchestration system for Radarr/Sonarr with Plex as the source of truth.

## Architecture

```text
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
│  │  RecoSvc    │  │  YouTubeSvc │  │  TMDBSvc    │             │
│  │ (recs+gates)│  │ (trailer)   │  │ (metadata)  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ EmbySvc     │  │ OldTrailerSvc│ │ WatchlistSvc│             │
│  │ (library)   │  │ (fallback)  │  │  (CRUD+FSM) │             │
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
│  Plex · Radarr · Sonarr · Prowlarr · TVDB · TMDB · YouTube · Emby · qBittorrent  │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```text
/workspace/media/watchlist/
├── config/
│   └── settings.py          # Centralized configuration (Config singleton, env-based)
├── core/
│   ├── http_client.py       # Shared HTTP client with caching/retry/structured errors
│   ├── logging.py           # Structured logging setup
│   └── exceptions.py        # Typed exception hierarchy
├── domain/                  # Business layer (state machine + media-type resolver)
│   ├── enums.py             # MediaType, MediaStatus, DownloadResultState
│   ├── models.py            # DownloadResult (typed)
│   ├── state_machine.py     # resolve_status(): THE availability state machine
│   └── resolver.py          # resolve_media_type(): single movie/tv resolver
├── services/                # External integrations + app services (DI-ready)
│   ├── base.py              # BaseService (config/http injectable)
│   ├── plex.py              # Plex: library, ownership, deep links, thumb proxy
│   ├── radarr.py            # Radarr: movies, lookup/add (title fallback), profiles
│   ├── sonarr.py            # Sonarr: series, lookup/add (title fallback), profiles
│   ├── emby.py              # Emby: library, deep links
│   ├── tmdb.py              # TMDB: metadata, artwork
│   ├── youtube.py           # YouTube trailer scraping (no API key)
│   ├── trailers.py          # Trailer enrichment (legacy fallback)
│   ├── qbittorrent.py       # qBittorrent torrents + download state
│   ├── watchlist.py         # Watchlist CRUD + atomic writes + state validation
│   ├── media_status.py      # MediaStatusService → domain state machine
│   ├── download.py          # DownloadService → movie/tv routing + add + fallback
│   └── recommendations.py   # Recommendation pipeline (rotation, gates, enrich)
├── api/                     # ⚡ LIVE FastAPI backend (modular)
│   ├── main.py              # App factory — uvicorn api.main:app
│   ├── models.py            # Pydantic request/response models
│   └── routes/ (health, config, status, download, search, library, quality, plex_thumb)
├── scripts/
│   ├── daily_recommendations.py  # Daily cron orchestration
│   ├── auto_complete.py          # pending → recommended transition
│   ├── backfill_tmdb_artwork.py  # Re-fetch posters/backdrops from TMDB
│   └── rebuild_dashboard.py      # Dashboard build pipeline
├── tests/                   # Mockable unit + API tests (no live LAN needed)
├── archive/                 # Legacy monolith (api_legacy_monolith.py) + old scripts
├── api.js / app.js / app.css # Frontend (served by nginx, volume-mounted; api.js = API client)
├── index.html / dashboard.html
├── requirements.txt / Dockerfile / docker-compose.yml / nginx/ / setup-watchlist.ps1
├── .env.example             # Documented env template (copy to .env)
├── ARCHITECTURE.md          # ⭐ Read this: how it works + what each file does
├── README.md                # This file
└── PROGRESS.md              # Project progress tracking
```

> ✅ **Single modular backend.** The legacy monolith `api.py` is archived
> (`archive/api_legacy_monolith.py`). Production runs `uvicorn api.main:app`
> (see `Dockerfile`). There is exactly one implementation of each business rule.
> See **ARCHITECTURE.md**.

## Features

### Recommendation Pipeline
- **Category rotation** - Weekly rotation through 12 categories
- **Quality gates** - IMDb/RT thresholds (films: 7.5/80%, series: 8.0/85%)
- **Plex-first ownership check** - Ground truth verification before adding
- **Duplicate prevention** - IMDb ID based deduplication
- **Metadata enrichment** - TMDB as primary source for title, posters, backdrops, synopsis, cast, genres, ratings, release dates, runtime, TMDB IDs
- **Trailer enrichment** - YouTube as primary source for official trailers (verified channels), stored as YouTube video ID, with in-app playback; falls back to legacy TVDB/TMDB trailer service if YouTube unavailable

### Watchlist State Machine
```text
PENDING → REQUESTED → DOWNLOADING → DOWNLOADED → AVAILABLE → RECOMMENDED
            ↘ FAILED ↗              ↗
```
- **PENDING**: User-approved, awaiting download
- **REQUESTED**: Added to Radarr/Sonarr, searching
- **DOWNLOADING**: Active in qBittorrent (with progress/speed/ETA)
- **DOWNLOADED**: File complete in Radarr/Sonarr (hasFile)
- **AVAILABLE**: Confirmed in Plex library (ground truth)
- **FAILED**: Service error or rejection
- **RECOMMENDED**: Completed lifecycle, moved to history

### Download Integration
- **Movie → Radarr** with quality profile selection
- **TV Series → Sonarr** with quality profile selection
- **Duplicate prevention** - Won't re-add existing items
- **Real-time status** - Polls qBittorrent for live progress

### Auto-Complete
- Hourly/daily check for completed downloads
- Verifies both Radarr/Sonarr hasFile AND Plex has title
- Atomically moves `pending → recommended` with completion date
- Rebuilds dashboard automatically

### Media Playback
- For media available in Plex or Emby, provides **Play** button in UI
- Clearly indicates source: **Play on Plex**, **Play on Emby**, or both
- Embedded playback investigated; falls back to direct playback/deep-link if embedding not feasible
- Trailer plays inside the application via YouTube iframe embed (official trailers only)

## Configuration

All configuration via `/workspace/.env` (canonical, host-backed at `D:\\.env`):

```bash
# Required
MEDIA_HOST=192.168.65.254
RADARR_URL=http://192.168.65.254:7878
RADARR_API_KEY=...
SONARR_URL=http://192.168.65.254:8989
SONARR_API_KEY=...
PLEX_URL=http://192.168.65.254:32400
PLEX_TOKEN=...
TMDB_API_KEY=...   # Now required for metadata

# Optional
TVDB_API_KEY=...   # Legacy fallback for trailers
JELLYFIN_URL=...
JELLYFIN_API_KEY=...
PROWLARR_URL=...
PROWLARR_API_KEY=...
QBITTORRENT_URL=http://192.168.65.254:1701
EMBY_URL=http://192.168.65.254:8096      # Emby (HTTPS-only over Tailscale)
EMBY_API_KEY=...

# Quality profile overrides (optional)
RADARR_QUALITY_PROFILE_ID=3
SONARR_QUALITY_PROFILE_ID=...
```

> **No YouTube API key is required** — official trailers are found by scraping
> `youtube.com` directly (`services/youtube.py`). A `YOUTUBE_API_KEY` is supported
> but never needed.

## Deployment

### Development (Sandbox)
```bash
cd /workspace/media/watchlist
python3 scripts/rebuild_dashboard.py
python3 -m api.main  # Runs on :8000
```

### Production (RKM-HP Windows)
```powershell
cd D:\hermes_agent\hermes-workspace\media\watchlist
.\setup-watchlist.ps1
```

This builds the `rkm-cinema-api` Docker image and starts:
- `api` container (FastAPI on :8000, holds all secrets)
- `web` container (nginx on :8123, serves UI + proxies `/api/*`)

Access via Tailscale: `http://rkm-hp.tail8d5e8.ts.net:8123/`

## Scheduled Jobs

### Daily Recommendations (18:00 AEST)
Runs `scripts/daily_recommendations.py` via cron:
1. Rotates category
2. Processes candidates (from weekly-media-recommendations skill)
3. Applies quality gates, Plex check, duplicate check
4. Enriches metadata (TMDB) + trailers (YouTube primary, legacy fallback)
5. Adds to watchlist pending
6. Rebuilds dashboard

### Auto-Complete (Hourly)
Runs `scripts/auto_complete.py`:
1. Checks each pending entry
2. Verifies Radarr/Sonarr hasFile + Plex ownership
3. Moves completed to recommended with date
4. Rebuilds dashboard if changes

### Trailer Enrichment (On-demand - Legacy Fallback)
```bash
python3 scripts/enrich_trailers.py [--probe] [--dry-run]
```
Note: This script is kept as a fallback; primary trailer enrichment now happens in the recommendation pipeline via YouTube service.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health + watchlist freshness |
| GET | `/api/config` | Public-safe config (no secrets) |
| GET | `/api/status` | Per-title download state + qBittorrent progress |
| POST | `/api/download` | Initiate Radarr/Sonarr download |
| GET | `/api/search` | Watchlist + TMDB search |
| GET | `/api/library` | Plex/Jellyfin library counts + recent |
| GET | `/api/quality` | Radarr/Sonarr quality profiles |

## Running Tests

```bash
cd /workspace/media/watchlist
pytest tests/ -v
```

## Key Design Principles

1. **Single source of truth** - `watchlist.json` with atomic writes
2. **Service layer** - All external integrations encapsulated in services
3. **Plex as ground truth** - Ownership verified against Plex, not Radarr/Sonarr
4. **No scattered scripts** - Single orchestration entry points
5. **Structured logging** - JSON logs for observability
6. **Type safety** - Pydantic models for API, dataclasses for internal
7. **Testability** - Services mockable, comprehensive test suite

## Development Workflow

1. Make changes in `/workspace/media/watchlist/`
2. Run tests: `pytest tests/ -v`
3. Rebuild dashboard: `python3 scripts/rebuild_dashboard.py`
4. Deploy to RKM-HP: `cd D:\hermes_agent\hermes-workspace\media\watchlist && .\setup-watchlist.ps1`
5. Verify at `http://rkm-hp.tail8d5e8.ts.net:8123/`

## Troubleshooting

### API not responding
```bash
docker compose logs api
curl http://localhost:8123/api/health
```

### Dashboard not updating
```bash
python3 scripts/rebuild_dashboard.py
# Check dashboard-data.json timestamp
```

### Recommendations not adding
- Check cron job output
- Verify TMDB API key in .env (now required)
- Trailers need **no YouTube API key** — they are scraped from youtube.com
- Check Plex token validity
- Check logs for service initialization errors

### Download button not working
- Verify Radarr/Sonarr API keys
- Check `/api/status` for indexer issues
- Check browser console for CORS errors

### Trailer not playing
- Trailers need **no YouTube API key** — the service scrapes youtube.com for the official trailer
- Check that the trailer ID is a valid YouTube video ID (11 chars)
- Ensure the trailer is from an official channel (service attempts to verify)
- If YouTube fails, legacy trailer service will attempt to provide a trailer ID

### Metadata missing
- Verify TMDB API key is set and valid (32 hex characters)
- Check that the TMDB ID exists in the watchlist entry
- Look for TMDB service errors in logs

## License

Private project - RKM Media Stack