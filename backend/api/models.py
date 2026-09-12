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


class SubtitleSelectRequest(BaseModel):
    """Choose a subtitle for an item (spec §3: discovery → apply → persist).

    ``file_id`` is the OpenSubtitles file id; ``subtitle_id`` (``os:<file_id>``) is
    what the store keeps, so the identity survives a stream-index change.
    """

    item_id: str = ""
    file_id: int = 0
    language: str = ""
    display_title: str = ""
    provider: str = "opensubtitles"


class SubtitleDisableRequest(BaseModel):
    """Turn subtitles off for an item without forgetting which one was chosen."""

    item_id: str = ""


class LoginRequest(BaseModel):
    """Sign in as a Jellyfin user (AUTH_MULTIUSER_PLAN §3.7, Phase 0).

    Identity is DELEGATED: these credentials are used once, against Jellyfin's
    ``/Users/AuthenticateByName``, and never stored. What the app keeps is the access
    token Jellyfin returned, behind an opaque id it invented itself.
    """

    username: str = ""
    password: str = ""


class SessionUser(BaseModel):
    """The signed-in user, as much of them as the browser is allowed to see."""

    id: str = ""
    name: str = ""


class LoginResponse(BaseModel):
    ok: bool = True
    user: SessionUser = Field(default_factory=SessionUser)
    #: ISO-8601 UTC; the cookie's Max-Age carries the same lifetime.
    expires: str = ""


class MeResponse(BaseModel):
    """``GET /api/auth/me`` — who this browser is, and which profile is in effect."""

    user: SessionUser = Field(default_factory=SessionUser)
    #: The profile in effect (the owner's own when none was chosen) — PLEX_PROFILE_AUTH_PLAN §3.
    profile: SessionUser = Field(default_factory=SessionUser)
    #: False while somebody else's profile is selected: administrative screens are refused then.
    on_own_profile: bool = True
    expires: str = ""


class ProfileUser(BaseModel):
    """One selectable profile, as the "Who's watching?" picker needs it.

    Deliberately carries no credential and no token: a profile's password is only ever *asked*
    for, never returned (PLEX_PROFILE_AUTH_PLAN §4).
    """

    id: str = ""
    name: str = ""
    is_admin: bool = False
    has_password: bool = False
    disabled: bool = False
    last_login: str = ""


class ProfilesResponse(BaseModel):
    """``GET /api/auth/profiles`` — every profile on the server, for the picker."""

    profiles: List[ProfileUser] = Field(default_factory=list)
    #: Which profile is in effect right now.
    current: ProfileUser = Field(default_factory=ProfileUser)
    warning: str = ""


class SelectProfileRequest(BaseModel):
    """``POST /api/auth/profile`` — switch this session to a profile.

    ``password`` is that profile's own password (its Jellyfin credential): optional for a
    password-less profile, **required for the administrator's own profile** so a shared device
    cannot walk into it (decision 3, 2026-09-12).
    """

    user_id: str = ""
    password: str = ""


class SelectProfileResponse(BaseModel):
    """The profile now in effect, and the libraries it may see."""

    ok: bool = True
    profile: ProfileUser = Field(default_factory=ProfileUser)
    libraries: List[dict] = Field(default_factory=list)


class AdminCreateUserRequest(BaseModel):
    """Create a household account (AUTH_MULTIUSER_PLAN Phase 1b).

    ``password`` is OPTIONAL and often empty on purpose: the user decided (2026-09-12)
    that a household member is created WITHOUT one, signing in with just their username.
    ``library_ids`` is the folder selection: ``None`` means every library (the creating
    administrator's own access), an empty list means none.
    """

    name: str = ""
    password: str = ""
    library_ids: Optional[List[str]] = None


class AdminUserPolicyRequest(BaseModel):
    """Change what an account may see, and/or whether it is enabled.

    ``None`` on either field means "leave it alone" — the policy is read-modify-written,
    never replaced wholesale from a partial body.
    """

    library_ids: Optional[List[str]] = None
    disabled: Optional[bool] = None


class AdminSetPasswordRequest(BaseModel):
    """Set or reset another account's password. Never echoed anywhere."""

    new_password: str = ""


class AdminDeleteUserRequest(BaseModel):
    """Deleting is irreversible, so it needs the account's NAME typed out."""

    confirm_name: str = ""


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
    #: The item's total runtime in ticks, when the player knows it. Lets a
    #: ``stopped`` report near the end be treated as "finished" (mark watched)
    #: instead of leaving a resume point at the credits.
    runtime_ticks: int = 0


class StatusEntry(BaseModel):
    state: str
    service: str
    detail: Optional[str] = None
    progress: Optional[int] = None
    speed: Optional[float] = None
    eta: Optional[int] = None
    qbitState: Optional[str] = None
    qbitName: Optional[str] = None
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


class LibraryFolder(BaseModel):
    """One library folder the media server actually exposes (MEDIA_LIBRARIES_PLAN)."""

    id: str                       # server ItemId — the ParentId scope for items
    name: str                     # server folder name (display fallback only)
    collection_type: str = ""     # movies | tvshows | mixed | …
    path: str = ""                # primary (first) location


class ConfiguredLibrary(BaseModel):
    """One sidebar library — the user-facing view of a configured library.

    ``name`` is ALWAYS the configured value (never the MEDIA_LIBRARY_N_ key);
    ``folder_id`` is set when the configured PATH resolved to a real server
    folder; ``ok``/``warning`` tell the UI whether this library is live.
    """

    name: str
    path: str = ""
    folder_id: Optional[str] = None
    collection_type: str = ""
    ok: bool = False
    warning: str = ""


class LibrariesResponse(BaseModel):
    """GET /api/library/folders — the sidebar's libraries + server folders."""

    provider: Optional[str] = None
    folders: List[LibraryFolder] = Field(default_factory=list)
    #: Sidebar list: resolved configured libraries when MEDIA_LIBRARY_N_* are
    #: present, otherwise the server's own folders (no hardcoded names).
    libraries: List[ConfiguredLibrary] = Field(default_factory=list)
    #: Config-level structural warnings (empty/duplicate entries).
    warnings: List[str] = Field(default_factory=list)


class FolderItemsResponse(BaseModel):
    """GET /api/library/folders/{folder_id}/items — one folder's poster wall."""

    provider: Optional[str] = None
    folder_id: str
    items: List[Dict[str, Any]] = Field(default_factory=list)


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