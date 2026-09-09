"""Pydantic models for API requests/responses."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DownloadRequest(BaseModel):
    imdbId: str = ""
    tmdbId: Optional[int] = None
    type: str = ""  # "movie" | "tv"
    qualityProfileId: Optional[int] = None
    title: str = ""  # optional, for Radarr title-search fallback
    year: Optional[int] = None  # optional, for fallback disambiguation


class DownloadResponse(BaseModel):
    ok: bool
    state: str
    message: str
    service: str


class HealthResponse(BaseModel):
    ok: bool
    updated: str
    titleCount: int
    services: Dict[str, bool] = Field(default_factory=dict)
    # Phase 14 (spec §28): structured per-service health + partial-failure flag.
    degraded: bool = False
    serviceDetail: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ConfigResponse(BaseModel):
    updated: str
    heroMode: str
    rotation: List[str]
    services: Dict[str, bool]


class JellyfinProgressRequest(BaseModel):
    """Playback progress reported by the in-app player (Jellyfin Sessions API).

    ``event`` maps to a Jellyfin session endpoint: ``start`` -> /Sessions/Playing,
    ``timeupdate`` -> /Sessions/Playing/Progress, ``stopped`` -> /Sessions/Playing/Stopped.
    ``position_ticks`` is in Jellyfin 10ms ticks (seconds * 1e7).
    """

    item_id: str = ""
    position_ticks: int = 0
    is_paused: bool = False
    event: str = "timeupdate"
    #: How the item is being played: DirectPlay | DirectStream | Transcode.
    play_method: str = "DirectPlay"


class StatusEntry(BaseModel):
    state: str
    service: str
    detail: Optional[str] = None
    progress: Optional[int] = None
    speed: Optional[float] = None
    eta: Optional[int] = None
    qbitState: Optional[str] = None
    qbitName: Optional[str] = None
    plexKey: Optional[str] = None
    plexUrl: Optional[str] = None
    embyUrl: Optional[str] = None
    jellyfinUrl: Optional[str] = None
    #: Jellyfin native item id for in-app playback (via /api/jellyfin/stream).
    jellyfinItemId: Optional[str] = None


class StatusResponse(BaseModel):
    statuses: Dict[str, StatusEntry]
    indexerIssue: Optional[str] = None


class SearchResult(BaseModel):
    title: str
    year: Optional[int]
    type: str
    imdbId: str
    tmdbId: Optional[int]
    poster: str
    inWatchlist: bool
    director: str
    cast: List[str]
    snippet: str
    voteAverage: Optional[float] = None


class SearchResponse(BaseModel):
    watchlist: List[SearchResult]
    tmdb: List[SearchResult]
    tmdbKey: bool
    servicesDown: bool


# --------------------------------------------------------------------------- global search
class GlobalEpisodeFacts(BaseModel):
    """Target for a series "Continue / Play" primary action (GLOBAL_SEARCH_PLAN)."""

    id: str
    season: int
    episode: int
    name: str
    position: int = 0
    remaining: int = 0
    #: "play" (first unwatched) | "continue" (in-progress episode).
    kind: str = "play"


class GlobalOwnedRow(BaseModel):
    """One owned playable result (movie/show/episode) with playback facts + state."""

    id: str
    kind: str  # movie | show | episode
    title: str
    year: Optional[int] = None
    genres: List[str] = Field(default_factory=list)
    rating: Optional[float] = None
    played: bool = False
    playback_position: int = 0
    runtime: int = 0
    play_count: int = 0
    series_id: Optional[str] = None
    series_name: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    #: Primary action: watch | resume | watch_again | next_episode.
    state: str = "watch"
    remaining: Optional[int] = None
    next_episode: Optional[GlobalEpisodeFacts] = None


class GlobalHint(BaseModel):
    """Intent hint (Person / Genre / BoxSet collection) from provider search."""

    id: str
    name: str
    kind: str  # person | genre | collection
    year: Optional[int] = None


class GlobalDiscoveryRow(BaseModel):
    """TMDB discovery row — ONLY when no strong owned match exists."""

    tmdb_id: int
    media_type: str  # movie | tv
    title: str
    year: Optional[int] = None
    poster: str = ""
    overview: str = ""
    #: True when the title is already on the watchlist (server truth — the UI
    #: then offers Download/Details instead of "Add to watchlist").
    in_watchlist: bool = False


class SearchGlobalResponse(BaseModel):
    query: str
    provider: Optional[str] = None
    #: Whether TMDB discovery is configured (False → discovery is empty by design).
    tmdb_key: bool = False
    #: A strong owned match exists → clients should NOT show the DISCOVER section.
    strong_match: bool = False
    items: List[GlobalOwnedRow] = Field(default_factory=list)
    people: List[GlobalHint] = Field(default_factory=list)
    #: Owned titles featuring the top Person hint (actor/director drill-down).
    person_titles: List[GlobalOwnedRow] = Field(default_factory=list)
    genres: List[GlobalHint] = Field(default_factory=list)
    collections: List[GlobalHint] = Field(default_factory=list)
    discovery: List[GlobalDiscoveryRow] = Field(default_factory=list)


class LibraryResponse(BaseModel):
    provider: Optional[str]
    available: bool
    counts: Dict[str, int]
    recent: List[Dict[str, Any]]
    server: Optional[str]
    urls: Optional[Dict[str, str]] = None


class QualityProfileResponse(BaseModel):
    id: int
    name: str
    items: List[Dict[str, Any]]


class QualityProfilesResponse(BaseModel):
    radarr: List[QualityProfileResponse]
    sonarr: List[QualityProfileResponse]


class WatchlistEntryResponse(BaseModel):
    imdbId: str
    tmdbId: Optional[int]
    tvdbId: Optional[int]
    title: str
    year: int
    type: str
    category: str
    genres: List[str]
    lang: str
    cert: str
    rt: Optional[int]
    imdb: Optional[float]
    tmdbScore: Optional[float]
    overview: str
    cast: List[str]
    director: str
    runtime: Optional[int]
    poster: str
    backdrop: str
    trailerId: str
    trailerTitle: str
    trailerUrl: str
    added: str
    source: str
    state: Optional[str] = None
    detail: Optional[str] = None
    progress: Optional[int] = None


class DashboardDataResponse(BaseModel):
    app: str
    version: int
    generatedAt: str
    updated: str
    heroMode: str
    refreshCron: str
    rotation: List[str]
    entries: List[WatchlistEntryResponse]


# --------------------------------------------------------------------------
# Phase 10 — resource API (spec §17/§18). One complete object per media item.
# --------------------------------------------------------------------------
class CapabilitiesModel(BaseModel):
    """Which user actions are available (spec §18 ``capabilities``)."""

    can_download: bool = False
    can_watch: bool = False


class WatchEntryModel(BaseModel):
    """One provider's watch link (spec §18 ``watch.<provider>``)."""

    available: bool = False
    url: Optional[str] = None
    error: Optional[str] = None
    #: Provider-native item id for in-app playback via /api/jellyfin/stream.
    item_id: Optional[str] = None
    #: Playback facts: watched flag + resume position/runtime (seconds).
    played: Optional[bool] = None
    playback_position: Optional[int] = None
    runtime: Optional[int] = None


class AcquisitionModel(BaseModel):
    """Acquisition backend facts for one item (spec §18 ``acquisition``)."""

    provider: Optional[str] = None
    status: Optional[str] = None


class MediaResponse(BaseModel):
    """The canonical single-item object the frontend renders from (§18).

    The frontend must NOT reconstruct status/capabilities from scattered
    fields — this is one complete, backend-derived resource.
    """

    id: str
    title: str = ""
    year: Optional[int] = None
    type: str = ""                      # "movie" | "tv"
    status: str = ""
    capabilities: CapabilitiesModel = Field(default_factory=CapabilitiesModel)
    watch: Dict[str, WatchEntryModel] = Field(default_factory=dict)
    acquisition: Optional[AcquisitionModel] = None
    detail: Optional[str] = None
    progress: Optional[int] = None
    speed: Optional[float] = None
    eta: Optional[int] = None
    qbitState: Optional[str] = None
    qbitName: Optional[str] = None


class RequestMediaResponse(BaseModel):
    """Outcome of POST /api/media/{media_id}/request (§15 vocab)."""

    ok: bool
    state: str
    message: str
    mediaId: str = ""
    service: str = ""
    candidates: List[Dict[str, Any]] = Field(default_factory=list)


class WatchlistResponse(BaseModel):
    """GET /api/watchlist — every pending + recommended entry as a resource."""

    entries: List[MediaResponse]
    indexerIssue: Optional[str] = None


class WatchlistEntriesResponse(BaseModel):
    """GET /api/watchlist/entries — every pending + recommended entry in the
    rich display shape the SPA renders (posters/backdrops/scores/synopsis/
    trailer/genres — legacy parity port source). Live from the authoritative
    store via the shared ``services/dashboard.to_rich_entry`` mapper; the
    static dashboard generator writes the same shape to dashboard-data.json."""

    updated: str = ""
    entries: List[WatchlistEntryResponse] = Field(default_factory=list)


class ReconcileResponse(BaseModel):
    """POST /api/reconcile — re-derive every entry's snapshot in one pass."""

    ok: bool
    entries: List[MediaResponse]
    indexerIssue: Optional[str] = None


class JobRunResponse(BaseModel):
    """One row from the job_runs table (spec Phase 13/14)."""

    jobName: str
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    status: str = ""
    itemsProcessed: int = 0
    error: Optional[str] = None


class JobsResponse(BaseModel):
    """GET /api/jobs — recent job_runs most-recent-first."""

    jobs: List[JobRunResponse]