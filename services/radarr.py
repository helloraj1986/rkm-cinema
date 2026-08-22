"""Radarr service for movie management."""
import logging
from typing import Any, Optional
from dataclasses import dataclass

from config.settings import get_config
from core.http_client import get_http_client
from core.exceptions import ServiceUnavailableError, NotFoundError, DuplicateError
from services.base import BaseService


logger = logging.getLogger("rkm.radarr")


@dataclass
class RadarrMovie:
    id: int
    tmdbId: int
    title: str
    year: int
    hasFile: bool
    monitored: bool
    qualityProfileId: int
    imdbId: str = ""


@dataclass
class RadarrQueueItem:
    id: int
    movieId: int
    status: str
    size: float
    sizeleft: float
    downloadId: str


@dataclass
class QualityProfile:
    id: int
    name: str
    items: list


@dataclass
class RootFolder:
    path: str


@dataclass
class AddResult:
    success: bool
    movie: Optional[RadarrMovie]
    message: str
    state: str  # "requested", "unavailable", etc.


class RadarrService(BaseService):
    """Radarr integration for movie management."""

    def __init__(self, *, config=None, http=None):
        super().__init__("radarr", config=config, http=http)
        self._movies_cache: list = []
        self._movies_cache_expiry: float = 0
        self._queue_cache: list = []
        self._queue_cache_expiry: float = 0
        self._profiles_cache: list = []
        self._profiles_cache_expiry: float = 0
        self._roots_cache: list = []
        self._roots_cache_expiry: float = 0
        self._indexer_health_cache: tuple = (0, None)  # (expiry, message)

    def _get(self, endpoint: str, params: dict = None, use_cache: bool = False, cache_ttl: int = 45, timeout: Optional[int] = None) -> Any:
        """GET request to Radarr API."""
        import time
        url = f"{self.config.RADARR_URL}/api/v3{endpoint}"
        headers = self._radarr_headers()

        if use_cache:
            now = time.time()
            cache_key = f"{url}:{str(params)}"
            if hasattr(self, '_http_cache') and cache_key in self._http_cache:
                expiry, data = self._http_cache[cache_key]
                if expiry > now:
                    return data

        try:
            data = self.http.get(url, headers=headers, params=params, timeout=timeout)
            if use_cache:
                if not hasattr(self, '_http_cache'):
                    self._http_cache = {}
                self._http_cache[cache_key] = (time.time() + cache_ttl, data)
            return data
        except Exception as e:
            self._handle_http_error(f"GET {endpoint}", e)

    def _post(self, endpoint: str, body: dict) -> Any:
        """POST request to Radarr API."""
        url = f"{self.config.RADARR_URL}/api/v3{endpoint}"
        headers = self._radarr_headers()
        try:
            return self.http.post(url, body, headers=headers)
        except Exception as e:
            self._handle_http_error(f"POST {endpoint}", e)

    def health_check(self) -> bool:
        """Check if Radarr is reachable."""
        try:
            self._get("/system/status")
            return True
        except Exception:
            return False

    def get_movies(self, use_cache: bool = True) -> list[RadarrMovie]:
        """Get all movies in Radarr."""
        import time
        now = time.time()
        if use_cache and self._movies_cache and now < self._movies_cache_expiry:
            return self._movies_cache

        data = self._get("/movie", use_cache=use_cache)
        movies = [
            RadarrMovie(
                id=m["id"],
                tmdbId=m["tmdbId"],
                title=m["title"],
                year=m.get("year", 0),
                hasFile=m.get("hasFile", False),
                monitored=m.get("monitored", False),
                qualityProfileId=m.get("qualityProfileId", 0),
            )
            for m in data
        ]
        self._movies_cache = movies
        self._movies_cache_expiry = now + 45
        return movies

    def get_queue(self, use_cache: bool = True) -> list[RadarrQueueItem]:
        """Get Radarr download queue."""
        import time
        now = time.time()
        if use_cache and self._queue_cache and now < self._queue_cache_expiry:
            return self._queue_cache

        data = self._get("/queue", params={"page": 1, "pageSize": 200}, use_cache=use_cache)
        records = data.get("records", []) if isinstance(data, dict) else data
        queue = [
            RadarrQueueItem(
                id=q["id"],
                movieId=q.get("movieId", 0),
                status=q.get("status", ""),
                size=float(q.get("size", 0)),
                sizeleft=float(q.get("sizeleft", 0)),
                downloadId=q.get("downloadId", ""),
            )
            for q in records
        ]
        self._queue_cache = queue
        self._queue_cache_expiry = now + 45
        return queue

    def get_quality_profiles(self, use_cache: bool = True) -> list[QualityProfile]:
        """Get quality profiles."""
        import time
        now = time.time()
        if use_cache and self._profiles_cache and now < self._profiles_cache_expiry:
            return self._profiles_cache

        data = self._get("/qualityprofile", use_cache=use_cache)
        profiles = [
            QualityProfile(id=p["id"], name=p["name"], items=p.get("items", []))
            for p in data
        ]
        self._profiles_cache = profiles
        self._profiles_cache_expiry = now + 600  # 10 min
        return profiles

    def get_root_folders(self, use_cache: bool = True) -> list[RootFolder]:
        """Get root folders."""
        import time
        now = time.time()
        if use_cache and self._roots_cache and now < self._roots_cache_expiry:
            return self._roots_cache

        data = self._get("/rootfolder", use_cache=use_cache)
        roots = [RootFolder(path=r["path"]) for r in data]
        self._roots_cache = roots
        self._roots_cache_expiry = now + 600
        return roots

    def lookup_movie(self, imdb_id: str) -> Optional[RadarrMovie]:
        """Lookup movie by IMDb ID."""
        data = self._get("/movie/lookup", params={"term": f"imdb:{imdb_id}"}, timeout=20)
        if not data:
            return None
        m = data[0]
        return RadarrMovie(
            id=0,  # Not in Radarr yet
            tmdbId=m.get("tmdbId", 0),
            title=m.get("title", ""),
            year=m.get("year", 0),
            hasFile=False,
            monitored=True,
            qualityProfileId=0,
        )

    def lookup_movie_by_tmdb(self, tmdb_id: int) -> Optional[RadarrMovie]:
        """Lookup movie by TMDB ID (canonical ids are often tmdb-only)."""
        try:
            data = self._get("/movie/lookup", params={"term": f"tmdb:{tmdb_id}"}, timeout=20)
        except Exception:
            return None
        if not data:
            return None
        m = data[0]
        return RadarrMovie(
            id=0,
            tmdbId=m.get("tmdbId", tmdb_id),
            title=m.get("title", ""),
            year=m.get("year", 0),
            hasFile=False,
            monitored=True,
            qualityProfileId=0,
        )

    def search_movies(self, title: str, year: Optional[int] = None) -> list[RadarrMovie]:
        """Search Radarr by title (and optionally year). Returns candidate matches."""
        if not title:
            return []
        term = str(title).strip()
        if year:
            term = term + f" {year}"
        try:
            data = self._get("/movie/lookup", params={"term": term}, timeout=20)
        except Exception:
            return []
        result = []
        for m in data or []:
            if not isinstance(m, dict):
                continue
            result.append(RadarrMovie(
                id=0,
                tmdbId=m.get("tmdbId", 0),
                title=m.get("title", ""),
                year=m.get("year", 0),
                hasFile=False,
                monitored=True,
                qualityProfileId=0,
                imdbId=m.get("imdbId", ""),
            ))
        return result

    def find_movie_by_tmdb(self, tmdb_id: int) -> Optional[RadarrMovie]:
        """Find existing movie by TMDB ID."""
        movies = self.get_movies()
        for m in movies:
            if m.tmdbId == tmdb_id:
                return m
        return None

    def add_movie(self, imdb_id: str, quality_profile_id: Optional[int] = None,
                  title: str = "", year: Optional[int] = None,
                  tmdb_id: Optional[int] = None) -> AddResult:
        """Add movie to Radarr.

        Lookup priority: IMDb ID first, then TMDB ID (canonical media ids are
        often ``movie:tmdb:*`` with no IMDb id), then a title/year search as a
        last resort so a valid movie is never rejected just because its id is
        stale/absent.
        """
        # Lookup by IMDb ID first.
        lookup = None
        if imdb_id:
            lookup = self.lookup_movie(imdb_id)
        # Canonical ids are frequently tmdb-only -> fall back to TMDB lookup.
        if (not lookup or not lookup.tmdbId) and tmdb_id:
            lookup = self.lookup_movie_by_tmdb(tmdb_id)
        candidates = []
        if not lookup or not lookup.tmdbId:
            # Imdb+tmdb lookup failed -> try title/year search
            candidates = self.search_movies(title, year) if title else []
            if len(candidates) == 1:
                lookup = candidates[0]
            elif len(candidates) > 1:
                # Ambiguous -> pick an exact year match if one exists, else
                # return AMBIGUOUS rather than silently guessing (spec: never
                # silently select a potentially incorrect movie).
                exact = None
                for c in candidates:
                    if year and c.year == year:
                        exact = c
                        break
                if exact:
                    lookup = exact
                else:
                    msg = ("Multiple Radarr matches — pick one: " +
                           "; ".join(f"{c.title} ({c.year}, tmdb:{c.tmdbId})" for c in candidates[:10]))
                    return AddResult(False, None, msg, "ambiguous")

        if not lookup or not lookup.tmdbId:
            msg = f"No Radarr match for imdb:{imdb_id}"
            if candidates:
                msg = ("Multiple Radarr matches — pick one: " +
                       "; ".join(f"{c.title} ({c.year}, tmdb:{c.tmdbId})" for c in candidates[:10]))
                return AddResult(False, None, msg, "ambiguous")
            return AddResult(False, None, msg, "unavailable")

        # Check existing
        existing = self.find_movie_by_tmdb(lookup.tmdbId)
        if existing:
            return AddResult(True, existing, f"{existing.title} is already in Radarr", "requested")

        # Get quality profile
        profiles = self.get_quality_profiles()
        qp = None
        if quality_profile_id:
            qp = next((p for p in profiles if p.id == quality_profile_id), None)
            if not qp:
                return AddResult(False, None, f"Quality profile {quality_profile_id} not found", "unavailable")
        else:
            # Use env override or first profile
            qp_id = self.config.RADARR_QUALITY_PROFILE_ID
            if qp_id:
                qp = next((p for p in profiles if p.id == qp_id), None)
        if not qp:
            qp = profiles[0] if profiles else None
        if not qp:
            return AddResult(False, None, "Radarr has no quality profiles configured", "unavailable")

        # Get root folder
        roots = self.get_root_folders()
        if not roots:
            return AddResult(False, None, "Radarr has no root folder configured", "unavailable")
        root = roots[0]

        # Add movie
        body = {
            "tmdbId": lookup.tmdbId,
            "title": lookup.title,
            "qualityProfileId": qp.id,
            "rootFolderPath": root.path,
            "monitored": True,
            "addOptions": {"searchForMovie": True},
        }
        try:
            created = self._post("/movie", body)
            movie = RadarrMovie(
                id=created["id"],
                tmdbId=created["tmdbId"],
                title=created["title"],
                year=created.get("year", 0),
                hasFile=created.get("hasFile", False),
                monitored=created.get("monitored", True),
                qualityProfileId=created.get("qualityProfileId", qp.id),
            )
            # Invalidate cache
            self._movies_cache = []
            return AddResult(True, movie, f"{movie.title} added to Radarr — download starting", "requested")
        except Exception as e:
            return AddResult(False, None, f"Failed to add to Radarr: {e}", "unavailable")

    def has_file(self, tmdb_id: int) -> bool:
        """Check if Radarr has the movie file."""
        movie = self.find_movie_by_tmdb(tmdb_id)
        return movie.hasFile if movie else False

    def get_indexer_health(self) -> Optional[str]:
        """Check Radarr health for indexer issues."""
        import time
        now = time.time()
        expiry, msg = self._indexer_health_cache
        if expiry > now:
            return msg

        try:
            data = self._get("/health", timeout=8)
            for item in data or []:
                src = (item.get("source") or "").lower()
                if "indexer" in src and item.get("type") in ("warning", "error"):
                    msg = (item.get("message") or "Indexers unavailable").strip()
                    self._indexer_health_cache = (now + 120, msg)
                    return msg
        except Exception:
            pass
        self._indexer_health_cache = (now + 120, None)
        return None