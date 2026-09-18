# RKM Cinema Search Functionality

## Overview
Search in RKM Cinema combines multiple data sources to provide a unified search experience across the user's personal library and external discovery services.

## API Endpoints

### `GET /api/search`
- **Purpose**: Search the user's watchlist (acquisition queue) + live TMDB search
- **Scope**: Personal acquisition queue + TMDB discovery
- **Authentication**: Requires valid session
- **Query Parameters**:
  - `q` (string, required): Search query (minimum length 1)
- **Response**: `SearchResponse` model containing:
  - `watchlist`: List of `SearchResult` from user's watchlist (max 6 items)
  - `tmdb`: List of `SearchResult` from live TMDB search (max 8 items)
  - `tmdbKey`: Boolean indicating if TMDB is configured
  - `servicesDown`: Boolean indicating if Radarr/Sonarr API keys are missing

### `GET /api/search/global`
- **Purpose**: Library-first global search with ownership scoring and discovery
- **Scope**: 
  - Owned media library (Jellyfin integration) - prioritized
  - People/Genre/BoxSet hints from library
  - Actor/director drill-down titles
  - TMDB discovery (only when library has no exact match)
- **Authentication**: Requires valid session
- **Query Parameters**:
  - `q` (string, required): Search query (minimum length 1)
- **Response**: `SearchGlobalResponse` model containing:
  - `query`: Original search query
  - `provider`: Media library provider name (e.g., "jellyfin")
  - `tmdb_key`: Boolean indicating if TMDB discovery is configured
  - `strong_match`: Boolean indicating if library has EXACT title match (score >= 3)
  - `items`: List of `GlobalOwnedRow` (owned movies/shows/episodes with playback facts)
  - `people`: List of `GlobalHint` (Person hints from library)
  - `person_titles`: List of `GlobalOwnedRow` (titles featuring top person hint)
  - `genres`: List of `GlobalHint` (Genre hints from library)
  - `collections`: List of `GlobalHint` (BoxSet/Collection hints from library)
  - `discovery`: List of `GlobalDiscoveryRow` (deduplicated TMDB results)

## Backend Services

### Global Search Service (`services/global_search.py`)
- Provides pure helper functions for the global-search endpoint:
  - `normalize_title()`: Case/punctuation-insensitive title normalization
  - `title_match_score()`: Scores how strongly a title matches a query (0-3 scale)
  - `owned_strong_match()`: Finds best title match score across owned items
  - `is_duplicate_discovery()`: Checks if TMDB candidate is already owned
  - `next_episode_facts()`: Determines which episode to target for "Continue/Play"
  - `owned_state()`: Determines primary action state (watch/resume/watch_again/next_episode)

### TMDB Service (`services/tmdb.py`)
- Responsible for external content discovery
- Provides `search_multi()` method for searching movies and TV shows
- Used for live search results in both search endpoints
- Includes proper headers, retries, and error handling

### Radarr Service (`services/radarr.py`)
- Handles movie-related operations
- Includes `search_movies()` method for title fallback searches
- Used during download workflows when IMDB lookup fails

### Sonarr Service (`services/sonarr.py`)
- Handles series/TV-related operations
- Includes `search_series()` method for title fallback searches
- Used during download workflows when TVDB lookup fails

### Watchlist Service (`services/watchlist.py`)
- Manages the personal acquisition queue
- Provides atomic persistence and state validation
- Source for personal search results in `/api/search`

### Library Service (`services/library/`)
- Provides access to owned media library via `build_library_service()`
- Integrates with Jellyfin as the source of truth for availability
- Used for searching owned content in `/api/search/global`

## Frontend Implementation

### Feature Location
- Located in `frontend/src/features/search/`
- Part of the bounded contexts architecture alongside library, playback, discover, etc.

### Search UI
- Integrated into the main navigation/search bar
- Provides real-time search suggestions as user types
- Displays results from all three sources with visual distinction:
  - Owned media (with playback state indicators)
  - People/Genre hints
  - TMDB discovery (marked as not in library)
  - Watchlist items (marked for download vs add)

## Search Workflow

### `/api/search` Endpoint:
1. **User Input**: User enters search query in search bar (min 1 char)
2. **API Call**: Frontend calls `/api/search?q={query}`
3. **Backend Processing**:
   - Load watchlist data via `WatchlistService()`
   - Match query against watchlist entries (title, category, director, snippet, cast, year)
   - Perform live TMDB search via `TMDBService().search_multi(query)` (if TMDB configured)
   - Format results into `SearchResponse` model
4. **Response**: Returns watchlist matches (max 6) and TMDB results (max 8)
5. **Display**: Frontend shows combined results with source attribution

### `/api/search/global` Endpoint:
1. **User Input**: User enters search query in search bar (min 1 char)
2. **API Call**: Frontend calls `/api/search/global?q={query}`
3. **Backend Processing**:
   - Check cache for normalized query (300s TTL for TMDB results)
   - Search library service for exact matches, people, genres, collections
   - Enrich up to 3 series items with episode facts (resume/next-episode)
   - Determine if library has EXACT match (score >= 3) via `owned_strong_match()`
   - If TMDB configured AND no exact library match:
     - Search TMDB with cached results
     - Filter by media_type (movie/tv only)
     - Check watchlist membership for in_watchlist flag
     - Deduplicate against owned items using TMDB ID or exact title match
   - Build `SearchGlobalResponse` with all components
4. **Response**: Returns structured library-first results with discovery section
5. **Display**: Frontend shows:
   - Owned items with primary action (watch/resume/watch_again/next_episode)
   - People/Genre/Collection hints for drill-down
   - Actor-director titles featuring top person
   - TMDB discovery results (only when library lacks exact match)

## Key Characteristics

- **Library-First Approach**: `/api/search/global` prioritizes owned content
- **Exact Match Gating**: TMDB discovery only shown when library has NO exact match (score < 3)
- **Scoring System**: 
  - 3 = exact normalized title match
  - 2 = containment with compatible year or no year
  - 1 = every significant token contained (min 5 chars)
  - 0 = no match
- **Smart Discovery**: External search suppressed when owned title merely contains query (prevents hiding real content)
- **Deduplication**: TMDB results filtered by ID first, then exact title+year to avoid duplicates
- **Caching**: TMDB search results cached per normalized query for 5 minutes (search-only endpoint)
- **Real-time Updates**: Library half never cached to show fresh playback state/progress
- **Graceful Degradation**: Falls back to library-only/TMDB-only when services fail (with logging)
- **Security**: All API keys and credentials remain server-side only
- **Performance**: Search cache TTL 5 minutes, library search uncached for freshness

## Data Models

### SearchResult (used in `/api/search`):
- `title`: string
- `year`: optional integer
- `type`: string ("movie" or "tv")
- `imdbId`: string
- `tmdbId`: optional integer
- `poster`: string (URL)
- `inWatchlist`: boolean
- `director`: string
- `cast`: list of strings
- `snippet`: string
- `voteAverage`: optional float

### GlobalOwnedRow (used in `/api/search/global`):
- `id`: string (library item ID)
- `kind`: string ("movie", "show", or "episode")
- `title`: string
- `year`: optional integer
- `genres`: list of strings
- `rating`: optional float
- `played`: boolean
- `playback_position`: integer
- `runtime`: integer
- `play_count`: integer
- `series_id`: optional string
- `series_name`: optional string
- `season`: optional integer
- `episode`: optional integer
- `state`: string ("watch", "resume", "watch_again", or "next_episode")
- `remaining`: optional integer
- `next_episode`: optional GlobalEpisodeFacts

### GlobalDiscoveryRow (used in `/api/search/global`):
- `tmdb_id`: integer
- `media_type`: string ("movie" or "tv")
- `title`: string
- `year`: optional integer
- `poster`: string (URL)
- `overview`: string
- `in_watchlist`: boolean

## Authentication & Security

- All search endpoints require valid user session via HttpOnly cookie
- No search functionality exposes sensitive data or credentials
- External API keys (TMDB) remain server-side only
- Jellyfin credentials never exposed to client
- Services degrade gracefully (e.g., TMDB failures return library-only results)
- All errors logged server-side for debugging without exposing details to client
