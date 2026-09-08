# RKM Watchlist — Production Architecture Refactor & Implementation Plan

## 0. Objective

Refactor RKM Watchlist from a dashboard/API-centric application into a **desired-state media orchestration system**.

The system must continuously answer:

> What media do I want, what do I already have, what am I currently acquiring, and what can I watch right now?

The implementation must be **idempotent, resilient to external-service failures, testable without a live LAN, and deterministic**.

### Core lifecycle

```text
Daily Recommendation Job
        |
        v
Generate candidates
        |
        v
Apply configured criteria
        |
        v
Resolve canonical media identity
        |
        v
Check Plex/Emby shared library
        |
        +---- Already available ---> Do not recommend
        |
        v
Add/update watchlist
        |
        v
User sees "Download"
        |
        v
POST /api/media/{id}/request
        |
        v
Re-check library
        |
        +---- Already available ---> AVAILABLE
        |
        v
Radarr or Sonarr
        |
        v
Indexer / download client
        |
        v
Media downloaded
        |
        v
Plex/Emby indexes media
        |
        v
AVAILABLE
        |
        +---- Watch on Plex
        |
        +---- Watch on Emby
```

---

# 1. Non-negotiable architectural invariants

The agent MUST preserve these rules.

## 1.1 Canonical media identity

Titles are for display and search only.

Media identity must use stable provider IDs whenever available:

- TMDB ID
- IMDb ID
- TVDB ID
- media type

Preferred canonical ID examples:

```text
movie:tmdb:12345
series:tmdb:54321
```

Do not use:

```text
movie:The Matrix
series:Breaking Bad
```

as the primary identity.

---

## 1.2 Plex/Emby library is the authority for availability

If the media exists in the shared Plex/Emby library, the canonical status is:

```text
AVAILABLE
```

This remains true even if:

- Radarr has a stale record
- Sonarr has a stale record
- qBittorrent still contains an old torrent
- the watchlist says it was previously requested
- one provider is temporarily unavailable

The application must never show `DOWNLOAD` for media that is already confirmed in the library.

---

## 1.3 Acquisition belongs to Radarr/Sonarr

RKM Watchlist orchestrates acquisition.

It must NOT duplicate Radarr/Sonarr's responsibilities.

Flow:

```text
RKM
  -> Radarr/Sonarr
  -> Indexers
  -> Download Client
  -> Filesystem
  -> Plex/Emby
```

Do not implement a second torrent/indexer management system inside RKM.

---

## 1.4 Requests are idempotent

Clicking Download once or ten times must produce the same result.

Example:

```text
User clicks Download
User clicks Download again
User refreshes
User clicks Download again
```

Must NOT create duplicate Radarr/Sonarr acquisitions.

Expected result:

```text
ONE acquisition request
status = REQUESTED
```

---

## 1.5 Recommendation jobs are idempotent

Running the daily recommendation job twice must not create duplicate recommendations.

The job must use upsert/deduplication semantics.

---

## 1.6 Availability and watchability are different

A media item can be:

```text
AVAILABLE
```

while:

```text
Plex watch link = unavailable
Emby watch link = available
```

This must NOT turn the media back into `DOWNLOAD`.

Example:

```json
{
  "status": "AVAILABLE",
  "capabilities": {
    "can_download": false,
    "can_watch": true
  },
  "watch": {
    "plex": {
      "available": false,
      "url": null
    },
    "emby": {
      "available": true,
      "url": "https://..."
    }
  }
}
```

The UI should show:

```text
AVAILABLE

[ Watch on Emby ]
```

---

# 2. Target architecture

Refactor toward:

```text
watchlist/
├── api/
│   ├── main.py
│   └── routes/
│       ├── health.py
│       ├── media.py
│       ├── watchlist.py
│       ├── library.py
│       ├── acquisition.py
│       ├── recommendations.py
│       └── jobs.py
│
├── application/
│   ├── commands/
│   │   ├── request_media.py
│   │   └── reconcile_media.py
│   └── queries/
│       ├── get_media_status.py
│       ├── get_watchlist.py
│       └── get_library.py
│
├── domain/
│   ├── identity.py
│   ├── media.py
│   ├── status.py
│   ├── watch.py
│   ├── recommendation.py
│   └── acquisition.py
│
├── services/
│   ├── library/
│   │   ├── service.py
│   │   ├── plex.py
│   │   └── emby.py
│   │
│   ├── acquisition/
│   │   ├── service.py
│   │   ├── radarr.py
│   │   └── sonarr.py
│   │
│   ├── download/
│   │   └── qbittorrent.py
│   │
│   ├── metadata/
│   │   ├── tmdb.py
│   │   └── youtube.py
│   │
│   ├── recommendation/
│   │   ├── generator.py
│   │   ├── criteria.py
│   │   ├── ranker.py
│   │   └── manager.py
│   │
│   ├── reconciliation/
│   │   └── reconciler.py
│   │
│   └── watchlist/
│       └── repository.py
│
├── infrastructure/
│   ├── database/
│   ├── http/
│   ├── cache/
│   └── logging/
│
├── jobs/
│   ├── daily_watchlist.py
│   └── reconcile.py
│
├── tests/
└── frontend/
    ├── index.html
    ├── api.js
    ├── app.js
    └── app.css
```

Do not create a second implementation of an existing business rule.

Before adding code, search the repository for the existing implementation and consolidate it.

---

# 3. Phase 1 — Repository audit

## Task

Before modifying code:

1. Inspect the complete repository.
2. Identify:
   - current API routes
   - Plex logic
   - Emby logic
   - Radarr logic
   - Sonarr logic
   - qBittorrent logic
   - recommendation logic
   - watchlist persistence
   - state machine
   - URL/deep-link generation
   - cron/scheduled jobs
   - frontend state handling
3. Identify duplicate implementations.
4. Identify all places where media identity is resolved.
5. Identify all places where Plex/Emby availability is determined.
6. Identify all places where download requests are created.
7. Identify all direct `fetch()` calls outside `api.js`.
8. Identify all direct external HTTP calls outside service classes.

### Deliverable

Create/update:

```text
docs/ARCHITECTURE_AUDIT.md
```

Document:

```text
Existing implementation
Target implementation
Duplicate logic
Risky logic
Files to delete/merge
Files to migrate
```

Do not begin a large rewrite until this audit is complete.

---

# 4. Phase 2 — Canonical media identity

Create:

```text
domain/identity.py
```

Example:

```python
from dataclasses import dataclass
from enum import Enum


class MediaType(str, Enum):
    MOVIE = "movie"
    SERIES = "series"


@dataclass(frozen=True)
class MediaIdentity:
    media_type: MediaType
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None

    @property
    def media_id(self) -> str:
        if self.tmdb_id:
            return f"{self.media_type.value}:tmdb:{self.tmdb_id}"

        if self.imdb_id:
            return f"{self.media_type.value}:imdb:{self.imdb_id}"

        if self.tvdb_id:
            return f"{self.media_type.value}:tvdb:{self.tvdb_id}"

        raise ValueError("Media identity requires a stable provider ID")
```

## Requirements

- Never use title as canonical identity.
- Preserve all known provider IDs.
- Normalize provider IDs at ingestion time.
- Do not silently convert ambiguous title searches into identities.
- If identity cannot be resolved safely, return an explicit ambiguity/error state.

---

# 5. Phase 3 — Introduce a persistent application store

The application now has enough state that JSON should no longer be the authoritative database.

Use SQLite.

Create:

```text
infrastructure/database/
```

Recommended tables:

```text
media
watchlist
recommendations
library_items
acquisitions
watch_links
job_runs
```

## `media`

```text
id
media_type
title
year
tmdb_id
imdb_id
tvdb_id
created_at
updated_at
```

## `watchlist`

```text
media_id
active
reason
criteria_score
priority
added_at
updated_at
```

## `library_items`

```text
media_id
provider
provider_item_id
title
year
matched_at
last_seen
```

## `acquisitions`

```text
media_id
provider
provider_item_id
status
requested_at
updated_at
```

## `watch_links`

```text
media_id
provider
provider_item_id
url
status
last_validated
```

## `job_runs`

```text
job_name
started_at
completed_at
status
items_processed
error
```

### Important

Keep `watchlist.json` temporarily for backward compatibility if required, but introduce a repository abstraction:

```python
class WatchlistRepository:
    def get_active(self):
        ...

    def add(self, media):
        ...

    def remove(self, media_id):
        ...

    def contains(self, media_id):
        ...
```

The rest of the application must not read `watchlist.json` directly.

---

# 6. Phase 4 — Create the library abstraction

Create:

```text
services/library/service.py
```

with provider interfaces:

```python
class LibraryProvider:
    async def health(self):
        ...

    async def find(self, identity):
        ...

    async def recently_added(self):
        ...

    async def build_watch_link(self, match):
        ...
```

Implement:

```text
services/library/plex.py
services/library/emby.py
```

and:

```text
LibraryService
    ├── PlexLibraryProvider
    └── EmbyLibraryProvider
```

---

# 7. Plex implementation requirements

Plex must be treated as a library provider, not a URL generator.

When matching media, capture the actual Plex identity:

```text
rating_key
machine_identifier
guid
title
year
library_section
```

Do not generate a watch URL from only:

```text
title
year
```

Do not assume:

```text
ratingKey + guessed URL
```

is always valid.

The Plex provider should return a structured result:

```python
@dataclass
class LibraryMatch:
    provider: str
    provider_item_id: str
    title: str
    year: int | None
    metadata: dict
```

---

# 8. Emby implementation requirements

Emby must follow the same abstraction.

Capture:

```text
item_id
server_id
title
year
```

Do not make the rest of the application know Emby's URL format.

---

# 9. Shared Plex/Emby library matching

Because Plex and Emby share the same underlying library, the application must prevent duplicate recommendations.

Example:

```text
TMDB:
    movie 12345

Plex:
    finds movie 12345

Emby:
    finds movie 12345
```

The application should have:

```text
media_id = movie:tmdb:12345
library = AVAILABLE
```

not:

```text
Plex available
Emby available
two different media states
```

Plex and Emby are providers of the same logical library.

---

# 10. Phase 5 — Robust watch links

Create:

```text
services/library/watch_links.py
```

or equivalent.

The responsibilities are:

```text
Library match
    ↓
Provider-specific watch-link resolver
    ↓
WatchLink
```

Example:

```python
@dataclass
class WatchLink:
    provider: str
    available: bool
    url: str | None
    error: str | None = None
```

The API should return:

```json
{
  "watch": {
    "plex": {
      "available": true,
      "url": "..."
    },
    "emby": {
      "available": true,
      "url": "..."
    }
  }
}
```

## Important

Do not let a failed watch-link resolver change:

```text
AVAILABLE
```

to:

```text
NOT_REQUESTED
```

Watch-link failure is a capability problem, not a media availability problem.

---

# 11. Watch-link configuration

Use explicit configuration:

```env
PLEX_BROWSER_URL=https://...
EMBY_BROWSER_URL=https://...
```

Separate:

```text
Backend/API URL
Browser URL
```

Never construct browser links from the backend's internal LAN URL.

Example:

```text
PLEX_URL
```

is for backend communication.

```text
PLEX_BROWSER_URL
```

is for user-facing links.

Same for Emby.

Never hard-code the Tailscale hostname in Python source.

---

# 12. Phase 6 — Canonical status resolver

Create:

```text
domain/status.py
```

The resolver should operate on facts, not perform HTTP calls.

Example input:

```python
MediaFacts(
    in_library=True,
    acquisition_requested=True,
    downloading=True,
    downloaded=True,
)
```

Example output:

```python
MediaStatus.AVAILABLE
```

Recommended statuses:

```text
NOT_REQUESTED
REQUESTED
DOWNLOADING
DOWNLOADED
AVAILABLE
ERROR
AMBIGUOUS
```

Resolution priority:

```text
if in_library:
    AVAILABLE

elif downloading:
    DOWNLOADING

elif acquisition_requested:
    REQUESTED

elif downloaded:
    DOWNLOADED

else:
    NOT_REQUESTED
```

Library availability always wins.

---

# 13. Phase 7 — Build Media Reconciliation

Create:

```text
services/reconciliation/reconciler.py
```

The reconciler gathers facts from external systems:

```text
MediaIdentity
      |
      +---- LibraryService
      |
      +---- AcquisitionService
      |
      +---- qBittorrentService
      |
      v
MediaFacts
      |
      v
Domain status resolver
      |
      v
MediaSnapshot
```

Example:

```python
snapshot = reconciler.get_snapshot(media_id)
```

Returns:

```python
MediaSnapshot(
    media_id="movie:tmdb:12345",
    status=MediaStatus.AVAILABLE,
    capabilities=Capabilities(
        can_download=False,
        can_watch=True,
    ),
    watch_links=...
)
```

This snapshot becomes the canonical object consumed by API routes.

---

# 14. Phase 8 — Acquisition abstraction

Create:

```text
services/acquisition/service.py
services/acquisition/radarr.py
services/acquisition/sonarr.py
```

Example interface:

```python
class AcquisitionProvider:
    async def find(self, identity):
        ...

    async def request(self, identity):
        ...

    async def get_status(self, identity):
        ...
```

Then:

```text
AcquisitionService
    |
    +---- Radarr
    |
    +---- Sonarr
```

The application layer should not contain:

```python
if movie:
    radarr...
else:
    sonarr...
```

everywhere.

That routing belongs in one acquisition service.

---

# 15. Phase 9 — Implement idempotent media request

Create:

```text
application/commands/request_media.py
```

The command must perform:

```text
1. Resolve media identity
2. Re-check library
3. If available -> return AVAILABLE
4. Check existing acquisition
5. If already requested -> return REQUESTED
6. Determine Radarr/Sonarr
7. Resolve exact provider item
8. If ambiguous -> AMBIGUOUS
9. Request acquisition
10. Persist acquisition state
11. Return REQUESTED
```

Example:

```python
result = await request_media(media_id)
```

Possible results:

```text
AVAILABLE
ALREADY_REQUESTED
REQUESTED
AMBIGUOUS
NOT_CONFIGURED
PROVIDER_UNAVAILABLE
```

---

# 16. Radarr/Sonarr identity resolution

Preferred lookup order:

```text
TMDB ID
    ↓
IMDb/TVDB ID where supported
    ↓
Exact title + year
    ↓
Ambiguous
```

Do not silently choose between multiple title matches.

Example:

```text
Search:
"The Thing"

Results:
The Thing (1982)
The Thing (2011)

Result:
AMBIGUOUS
```

The UI should show a selection dialog if needed.

---

# 17. Phase 10 — API redesign

Prefer resource-oriented endpoints.

Example:

```text
GET  /api/media/{media_id}
POST /api/media/{media_id}/request

GET  /api/watchlist
GET  /api/library
GET  /api/recommendations

POST /api/reconcile
GET  /api/jobs
GET  /api/health
```

Avoid adding more generic endpoints such as:

```text
POST /api/download
```

if a more explicit resource command is possible.

---

# 18. API media response

The frontend should receive one complete object:

```json
{
  "id": "movie:tmdb:12345",
  "title": "Example Movie",
  "year": 2026,
  "type": "movie",
  "status": "AVAILABLE",

  "capabilities": {
    "can_download": false,
    "can_watch": true
  },

  "watch": {
    "plex": {
      "available": true,
      "url": "https://..."
    },
    "emby": {
      "available": true,
      "url": "https://..."
    }
  },

  "acquisition": {
    "provider": "radarr",
    "status": "completed"
  }
}
```

The frontend should not reconstruct this state.

---

# 19. Phase 11 — Frontend becomes declarative

`app.js` must render based on:

```text
status
capabilities
watch
```

Do not implement external-service logic in JavaScript.

Do not make frontend decisions based on:

```javascript
if (movie.radarr)
if (movie.plex)
if (movie.emby)
```

Instead:

```javascript
if (movie.capabilities.can_download) {
    renderDownloadButton();
}

if (movie.watch.plex?.available) {
    renderPlexButton();
}

if (movie.watch.emby?.available) {
    renderEmbyButton();
}
```

---

# 20. Required UI states

## NOT_REQUESTED

```text
Example Movie
8.2 ★

[ Download ]
```

## REQUESTED

```text
Example Movie
⏳ Requested

Waiting for Radarr
```

## DOWNLOADING

```text
Example Movie
⬇ Downloading

72%
8.4 MB/s
ETA 18m
```

## DOWNLOADED

```text
Example Movie
✓ Downloaded
⏳ Waiting for Plex/Emby
```

## AVAILABLE

```text
Example Movie
✓ Available

[ Watch on Plex ] [ Watch on Emby ]
```

Never display Download when:

```text
status == AVAILABLE
```

This must be enforced by both backend capabilities and frontend rendering.

---

# 21. Phase 12 — Recommendation engine

Separate recommendation generation from media reconciliation.

Create:

```text
services/recommendation/
    generator.py
    criteria.py
    ranker.py
    manager.py
```

Pipeline:

```text
Candidate sources
       |
       v
Normalize identity
       |
       v
Apply criteria
       |
       v
Remove duplicates
       |
       v
Check library
       |
       v
Check active watchlist
       |
       v
Check recommendation history
       |
       v
Rank
       |
       v
Persist recommendations
```

---

# 22. Criteria must be configuration

Do not hard-code recommendation criteria in Python.

Example:

```yaml
recommendations:
  movies:
    min_tmdb_rating: 7.5
    min_vote_count: 1000
    years:
      - 2024
      - 2025
      - 2026

    genres:
      include:
        - science_fiction
        - thriller

      exclude:
        - horror

  series:
    min_tmdb_rating: 8.0
    min_vote_count: 500
```

The criteria engine should return both:

```text
PASS / FAIL
```

and reasons.

Example:

```json
{
  "passed": true,
  "score": 91,
  "reasons": [
    "TMDB rating 8.4 >= 7.5",
    "Vote count 12,400 >= 1,000",
    "Genre matches science fiction",
    "Not in library",
    "Not already recommended"
  ]
}
```

---

# 23. Recommendation history

Persist history.

Example:

```json
{
  "media_id": "movie:tmdb:12345",
  "first_seen": "2026-08-22T02:00:00Z",
  "last_seen": "2026-08-22T02:00:00Z",
  "decision": "accepted",
  "score": 91
}
```

This prevents the daily job from recommending the same title repeatedly.

---

# 24. Daily cron job

Create:

```text
jobs/daily_watchlist.py
```

The job must:

```text
1. Start job_run
2. Load recommendation criteria
3. Fetch candidate media
4. Normalize identity
5. Deduplicate
6. Check Plex/Emby library
7. Exclude available media
8. Check active watchlist
9. Exclude existing watchlist entries
10. Check recommendation history
11. Apply ranking
12. Persist new recommendations
13. Update job_run
14. Emit structured logs
```

It must be safe to execute repeatedly.

---

# 25. Daily job example

Input:

```text
143 candidates
```

Processing:

```text
143 candidates
 ↓
27 pass criteria
 ↓
12 already in Plex/Emby
 ↓
8 already recommended
 ↓
7 new recommendations
```

Persist:

```text
7 new watchlist records
```

Job result:

```json
{
  "status": "success",
  "candidates": 143,
  "passed_criteria": 27,
  "already_in_library": 12,
  "already_recommended": 8,
  "new_recommendations": 7
}
```

---

# 26. Phase 13 — Scheduled reconciliation

In addition to the daily recommendation job, run a more frequent reconciliation job.

Recommended:

```text
Daily:
    recommendation generation

Every 5-15 minutes:
    acquisition/library reconciliation
```

The frequent job should update:

```text
REQUESTED
DOWNLOADING
DOWNLOADED
AVAILABLE
```

without generating new recommendations.

This means a user does not need to refresh or click anything to discover that a download has become available.

---

# 27. Reconciliation job example

```text
Every 10 minutes:

Watchlist:
    20 active items

Check library:
    3 newly available

Check Radarr:
    4 requested

Check Sonarr:
    2 requested

Check qBittorrent:
    3 downloading

Update snapshots.

Result:
    3 items changed to AVAILABLE
    2 items changed to DOWNLOADING
```

---

# 28. Phase 14 — Health and partial failure

Every external service must have:

```text
timeout
retry
backoff
structured error
health status
```

Recommended typed errors:

```text
PlexUnavailable
EmbyUnavailable
RadarrUnavailable
SonarrUnavailable
QBittorrentUnavailable
TMDBUnavailable
AmbiguousMedia
MediaNotFound
```

One failed service must not destroy the entire response.

Example:

```text
Plex: unavailable
Emby: available
Radarr: available
Sonarr: available
qBittorrent: available
```

Result:

```text
AVAILABLE

[ Watch on Emby ]
```

not:

```text
ERROR
```

---

# 29. Phase 15 — Caching

Cache expensive provider operations.

Especially:

```text
Plex full library scan
Emby full library scan
Plex machine identifier
Emby server ID
TMDB metadata
Radarr/Sonarr profiles
```

Use explicit TTLs.

Example:

```text
Plex library: 60 seconds
Emby library: 60 seconds
TMDB metadata: hours/days
Server IDs: long-lived cache
```

Do not allow one status request to trigger repeated full-library scans.

---

# 30. Phase 16 — Testing requirements

No test may require:

```text
Plex LAN
Emby LAN
Radarr LAN
Sonarr LAN
qBittorrent LAN
real API keys
```

Use fake providers.

## Required domain tests

Test:

```text
library available -> AVAILABLE
downloading -> DOWNLOADING
requested -> REQUESTED
nothing -> NOT_REQUESTED
library available + downloading -> AVAILABLE
library available + requested -> AVAILABLE
```

## Identity tests

Test:

```text
TMDB ID -> canonical ID
IMDb ID -> canonical ID
TVDB ID -> canonical ID
missing IDs -> explicit error
```

## Request tests

Test:

```text
request unavailable movie -> Radarr
request unavailable series -> Sonarr
request already available -> no Radarr/Sonarr call
request already requested -> no duplicate
ambiguous lookup -> AMBIGUOUS
```

## Recommendation tests

Test:

```text
passes criteria -> candidate
fails rating -> excluded
fails genre -> excluded
already in library -> excluded
already in watchlist -> excluded
already in history -> excluded
duplicate candidate -> one record
```

## Watch-link tests

Test:

```text
Plex match -> valid Plex link
Emby match -> valid Emby link
Plex link failure + Emby success -> Emby button only
Plex failure -> media remains AVAILABLE
```

---

# 31. Phase 17 — API tests

Test:

```text
GET /api/media/{id}
POST /api/media/{id}/request
GET /api/watchlist
GET /api/library
POST /api/reconcile
GET /api/health
```

Verify that:

```text
AVAILABLE -> can_download false
NOT_REQUESTED -> can_download true
AVAILABLE -> watch links exposed
provider failure -> partial response
```

---

# 32. Phase 18 — Frontend tests/manual verification

Verify each card state:

```text
NOT_REQUESTED
REQUESTED
DOWNLOADING
DOWNLOADED
AVAILABLE
```

Verify:

```text
Download button appears only when can_download == true
Plex button appears only when Plex link available
Emby button appears only when Emby link available
```

Verify that clicking Download twice does not create duplicate requests.

---

# 33. Phase 19 — Observability

Use structured logging.

Example:

```text
media.request.start
media.request.already_available
media.request.already_requested
media.request.radarr
media.request.sonarr
media.request.ambiguous

library.match
library.provider_unavailable

recommendation.job.start
recommendation.job.complete

reconciliation.start
reconciliation.complete
```

Every job should have a correlation/job ID.

Example:

```text
job_id=20260822-020000
media_id=movie:tmdb:12345
```

Never log:

```text
RADARR_API_KEY
PLEX_TOKEN
EMBY_API_KEY
```

---

# 34. Phase 20 — Configuration cleanup

Centralize configuration.

Example:

```env
RADARR_URL=http://radarr:7878
RADARR_API_KEY=...

SONARR_URL=http://sonarr:8989
SONARR_API_KEY=...

QBITTORRENT_URL=http://qbittorrent:8080

PLEX_URL=http://plex:32400
PLEX_TOKEN=...
PLEX_BROWSER_URL=https://...

EMBY_URL=http://emby:8096
EMBY_API_KEY=...
EMBY_BROWSER_URL=https://...

TMDB_API_KEY=...
```

Separate:

```text
internal service URL
browser-facing URL
```

Never expose secrets through `/api/config`.

---

# 35. Phase 21 — Frontend API boundary

`api.js` is the only frontend network layer.

Allowed:

```javascript
API.getMedia(id)
API.getWatchlist()
API.requestMedia(id)
API.getLibrary()
API.getHealth()
```

Not allowed elsewhere:

```javascript
fetch("/api/...")
fetch("http://plex...")
fetch("http://radarr...")
```

`app.js` should only deal with application state and rendering.

---

# 36. Phase 22 — Remove legacy duplication

After migration:

1. Remove duplicate status resolution.
2. Remove duplicate media-type resolution.
3. Remove duplicate Plex URL builders.
4. Remove duplicate Emby URL builders.
5. Remove duplicate Radarr/Sonarr lookup logic.
6. Remove old download orchestration.
7. Remove direct watchlist JSON manipulation.
8. Remove dead legacy routes.
9. Keep the archived monolith only as historical reference.

Do not leave two active implementations "for compatibility".

---

# 37. Phase 23 — Recommended API contract

Use this conceptual response:

```json
{
  "id": "movie:tmdb:12345",
  "type": "movie",
  "title": "Example Movie",
  "year": 2026,

  "status": "AVAILABLE",

  "capabilities": {
    "can_download": false,
    "can_watch": true
  },

  "library": {
    "available": true,
    "providers": ["plex", "emby"]
  },

  "watch": {
    "plex": {
      "available": true,
      "url": "https://..."
    },
    "emby": {
      "available": true,
      "url": "https://..."
    }
  },

  "acquisition": {
    "provider": "radarr",
    "status": "completed"
  }
}
```

The frontend should not need to understand how any of these values were discovered.

---

# 38. Phase 24 — Failure scenarios that MUST work

## Scenario A — Movie already in Plex

```text
User opens watchlist
        ↓
Library match found
        ↓
AVAILABLE
        ↓
No Download button
        ↓
Plex / Emby watch buttons
```

---

## Scenario B — Movie already in Emby

Same result:

```text
AVAILABLE
```

Do not recommend it again.

---

## Scenario C — Radarr has movie but Plex doesn't

```text
REQUESTED
```

Show:

```text
Waiting for Radarr
```

Do not show Download again.

---

## Scenario D — qBittorrent downloading

```text
DOWNLOADING
```

Show progress if available.

---

## Scenario E — File downloaded but Plex has not indexed it

```text
DOWNLOADED
```

Do NOT show Download.

---

## Scenario F — Plex unavailable, Emby available

```text
AVAILABLE
```

Show:

```text
[ Watch on Emby ]
```

---

## Scenario G — Both Plex and Emby temporarily unavailable

If the library was previously confirmed but current providers cannot be queried, do not incorrectly turn it into `NOT_REQUESTED`.

Use an explicit degraded state/cache policy such as:

```text
AVAILABLE
library_last_seen = ...
library_check = DEGRADED
```

Never automatically initiate a new acquisition solely because the library provider timed out.

---

## Scenario H — User clicks Download twice

First:

```text
REQUESTED
```

Second:

```text
ALREADY_REQUESTED
```

No duplicate Radarr/Sonarr request.

---

## Scenario I — Daily cron runs twice

First:

```text
7 new recommendations
```

Second:

```text
0 new recommendations
```

No duplicates.

---

# 39. Phase 25 — Security requirements

Never expose:

```text
Plex token
Emby API key
Radarr API key
Sonarr API key
TMDB API key
qBittorrent credentials
```

to the frontend.

All external service calls happen server-side.

The browser only receives:

```text
media metadata
status
capabilities
watch URLs
safe operational information
```

---

# 40. Phase 26 — Deployment

Maintain:

```text
api container
web/nginx container
```

The API container owns:

```text
database
secrets
external integrations
jobs
reconciliation
```

The web container owns:

```text
static frontend
nginx reverse proxy
```

Prefer running jobs in the API container or a dedicated worker/job container rather than depending on the host's ad-hoc cron configuration.

If host cron is retained, it should invoke a stable API/job command, not contain business logic.

---

# 41. Definition of done

The refactor is complete only when all of the following are true.

## Architecture

- [ ] No active monolithic backend implementation.
- [ ] One canonical media identity implementation.
- [ ] One canonical status resolver.
- [ ] One acquisition orchestration service.
- [ ] One library abstraction.
- [ ] One recommendation pipeline.
- [ ] No business rules in API routes.
- [ ] No external HTTP calls in API routes.
- [ ] No direct watchlist JSON manipulation outside repository layer.

## Library

- [ ] Plex library matching works by stable identity.
- [ ] Emby library matching works by stable identity.
- [ ] Plex and Emby are treated as providers of the same library.
- [ ] Existing library media is never recommended again.
- [ ] Existing library media never shows Download.

## Watch links

- [ ] Plex links are generated from real Plex library matches.
- [ ] Emby links are generated from real Emby library matches.
- [ ] Browser URLs are configuration-driven.
- [ ] Internal service URLs are never exposed as watch links.
- [ ] Watch-link failure does not change media availability.
- [ ] Plex and Emby buttons are independently rendered.

## Acquisition

- [ ] Movie requests route to Radarr.
- [ ] Series requests route to Sonarr.
- [ ] Stable IDs are preferred over title matching.
- [ ] Title/year fallback is supported.
- [ ] Ambiguous results require explicit selection.
- [ ] Requests are idempotent.
- [ ] Duplicate Radarr/Sonarr requests are impossible through the application.

## Recommendation

- [ ] Criteria are configurable.
- [ ] Candidate identity is normalized.
- [ ] Library items are excluded.
- [ ] Active watchlist items are excluded.
- [ ] Recommendation history prevents unwanted repeats.
- [ ] Daily job is idempotent.
- [ ] Job execution is recorded.
- [ ] Job failures are visible.

## Reconciliation

- [ ] Acquisition status is reconciled periodically.
- [ ] Library availability is reconciled periodically.
- [ ] Downloading -> Downloaded -> Available transitions work.
- [ ] External service failures degrade gracefully.
- [ ] Cached library data prevents repeated full scans.

## Testing

- [ ] Domain tests pass.
- [ ] Identity tests pass.
- [ ] Acquisition tests pass.
- [ ] Recommendation tests pass.
- [ ] Plex tests pass.
- [ ] Emby tests pass.
- [ ] Watch-link tests pass.
- [ ] API tests pass.
- [ ] No test requires the real LAN.
- [ ] No test requires real API keys.

---

# 42. Implementation order

The agent MUST implement in this order.

```text
PHASE 1
Repository audit
        ↓
PHASE 2
Canonical media identity
        ↓
PHASE 3
Repository/database abstraction
        ↓
PHASE 4
Library abstraction
        ↓
PHASE 5
Robust Plex/Emby matching + watch links
        ↓
PHASE 6
Canonical status resolver
        ↓
PHASE 7
Media reconciliation
        ↓
PHASE 8
Acquisition abstraction
        ↓
PHASE 9
Idempotent request-media command
        ↓
PHASE 10
API contracts
        ↓
PHASE 11
Frontend capability-driven rendering
        ↓
PHASE 12
Recommendation engine
        ↓
PHASE 13
Daily recommendation job
        ↓
PHASE 14
Periodic reconciliation job
        ↓
PHASE 15
Observability
        ↓
PHASE 16
Tests
        ↓
PHASE 17
Remove legacy duplication
        ↓
PHASE 18
Production verification
```

Do not skip ahead to frontend fixes while the underlying state model is incorrect.

---

# 43. Agent execution rules

For every phase:

1. Inspect existing code first.
2. Reuse working code where it fits.
3. Do not create parallel implementations.
4. Keep domain logic independent of FastAPI.
5. Keep external APIs behind service/provider interfaces.
6. Add tests with every business-rule change.
7. Run the full test suite after each major phase.
8. Do not silently change behavior to make tests pass.
9. Prefer explicit typed results over magic dictionaries.
10. Prefer idempotent operations.
11. Prefer stable IDs over title matching.
12. Never make availability depend on watch-link construction.
13. Never make a temporary provider outage trigger a new download.
14. Never expose secrets to the frontend.
15. Never make the frontend responsible for business-state decisions.

---

# 44. Final production architecture

The completed application should conceptually look like:

```text
                    ┌─────────────────────┐
                    │  Daily Recommendation│
                    │        Job           │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Recommendation       │
                    │ Engine               │
                    │ criteria + ranking   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Watchlist Repository │
                    │ Desired State        │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Media Reconciler     │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼─────────────────┐
              ▼                ▼                 ▼
       ┌────────────┐   ┌─────────────┐   ┌────────────┐
       │ Plex/Emby  │   │ Radarr/     │   │ qBittorrent│
       │ Library    │   │ Sonarr      │   │            │
       └─────┬──────┘   └──────┬──────┘   └─────┬──────┘
             │                 │                 │
             └─────────────────┼─────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │ Canonical Media      │
                    │ Snapshot / Status    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ FastAPI             │
                    │ typed API           │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Frontend            │
                    │ capability-driven   │
                    └─────────────────────┘
```

The key principle is:

> **RKM Watchlist should not try to be Plex, Emby, Radarr, Sonarr, or qBittorrent. It should be the reliable orchestration and reconciliation layer that understands what the user wants, observes what the media stack is doing, and presents one canonical state to the user.**

---

# 45. Required final verification

Before declaring the implementation complete, manually verify this exact scenario:

### Movie not in library

```text
Watchlist
  -> movie appears
  -> Download button visible
```

Click Download:

```text
RKM
  -> Radarr
  -> download client
```

UI changes:

```text
REQUESTED
```

Then:

```text
DOWNLOADING
```

Then:

```text
DOWNLOADED
```

Then Plex/Emby indexes it:

```text
AVAILABLE
```

UI changes to:

```text
[ Watch on Plex ] [ Watch on Emby ]
```

Download button disappears.

Now refresh the page.

The state must remain:

```text
AVAILABLE
```

Run the daily recommendation job.

The movie must NOT appear as a new recommendation.

Finally, click both watch buttons and verify they open the actual item directly in the configured browser-facing Plex/Emby web interfaces.

Repeat the same test for a TV series through Sonarr.

Only after these end-to-end scenarios work should the old implementation be removed.
