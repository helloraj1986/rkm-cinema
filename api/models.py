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
    services: Dict[str, bool]


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