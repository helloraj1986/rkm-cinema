"""Pydantic models for API requests/responses."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


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