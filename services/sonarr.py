"""Sonarr service for TV series management."""
import logging
from typing import Any, Optional
from dataclasses import dataclass

from config.settings import get_config
from core.http_client import get_http_client
from core.exceptions import ServiceUnavailableError, NotFoundError
from services.base import BaseService


logger = logging.getLogger("rkm.sonarr")


@dataclass
class SonarrSeries:
    id: int
    tvdbId: int
    title: str
    year: int
    monitored: bool
    qualityProfileId: int
    languageProfileId: int
    statistics: dict
    imdbId: str = ""


@dataclass
class SonarrQueueItem:
    id: int
    seriesId: int
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
class LanguageProfile:
    id: int
    name: str


@dataclass
class AddResult:
    success: bool
    series: Optional[SonarrSeries]
    message: str
    state: str


class SonarrService(BaseService):
    """Sonarr integration for TV series management."""

    def __init__(self, *, config=None, http=None):
        super().__init__("sonarr", config=config, http=http)
        self._series_cache: list = []
        self._series_cache_expiry: float = 0
        self._queue_cache: list = []
        self._queue_cache_expiry: float = 0
        self._profiles_cache: list = []
        self._profiles_cache_expiry: float = 0
        self._roots_cache: list = []
        self._roots_cache_expiry: float = 0
        self._langs_cache: list = []
        self._langs_cache_expiry: float = 0
        self._tvdb_cache: dict = {}  # imdb_id -> tvdb_id

    def _get(self, endpoint: str, params: dict = None, use_cache: bool = False, cache_ttl: int = 45, timeout: Optional[int] = None) -> Any:
        """GET request to Sonarr API."""
        import time
        url = f"{self.config.SONARR_URL}/api/v3{endpoint}"
        headers = self._sonarr_headers()

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
        """POST request to Sonarr API."""
        url = f"{self.config.SONARR_URL}/api/v3{endpoint}"
        headers = self._sonarr_headers()
        try:
            return self.http.post(url, body, headers=headers)
        except Exception as e:
            self._handle_http_error(f"POST {endpoint}", e)

    def health_check(self) -> bool:
        """Check if Sonarr is reachable."""
        try:
            self._get("/system/status")
            return True
        except Exception:
            return False

    def get_series(self, use_cache: bool = True) -> list[SonarrSeries]:
        """Get all series in Sonarr."""
        import time
        now = time.time()
        if use_cache and self._series_cache and now < self._series_cache_expiry:
            return self._series_cache

        data = self._get("/series", use_cache=use_cache)
        series = [
            SonarrSeries(
                id=s["id"],
                tvdbId=s["tvdbId"],
                title=s["title"],
                year=s.get("year", 0),
                monitored=s.get("monitored", False),
                qualityProfileId=s.get("qualityProfileId", 0),
                languageProfileId=s.get("languageProfileId", 0),
                statistics=s.get("statistics", {}),
            )
            for s in data
        ]
        if use_cache:
            self._series_cache = series
            self._series_cache_expiry = now + 45
        return series

    def get_queue(self, use_cache: bool = True) -> list[SonarrQueueItem]:
        """Get Sonarr download queue."""
        import time
        now = time.time()
        if use_cache and self._queue_cache and now < self._queue_cache_expiry:
            return self._queue_cache

        data = self._get("/queue", params={"page": 1, "pageSize": 200}, use_cache=use_cache)
        records = data.get("records", []) if isinstance(data, dict) else data
        queue = [
            SonarrQueueItem(
                id=q["id"],
                seriesId=q.get("seriesId", 0),
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
        self._profiles_cache_expiry = now + 600
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

    def get_language_profiles(self, use_cache: bool = True) -> list[LanguageProfile]:
        """Get language profiles."""
        import time
        now = time.time()
        if use_cache and self._langs_cache and now < self._langs_cache_expiry:
            return self._langs_cache

        data = self._get("/languageprofile", use_cache=use_cache)
        langs = [LanguageProfile(id=l["id"], name=l["name"]) for l in data]
        self._langs_cache = langs
        self._langs_cache_expiry = now + 600
        return langs

    def lookup_series(self, imdb_id: str) -> Optional[SonarrSeries]:
        """Lookup series by IMDb ID."""
        data = self._get("/series/lookup", params={"term": f"imdb:{imdb_id}"}, timeout=20)
        if not data:
            return None
        s = data[0]
        return SonarrSeries(
            id=0,
            tvdbId=s.get("tvdbId", 0),
            title=s.get("title", ""),
            year=s.get("year", 0),
            monitored=True,
            qualityProfileId=0,
            languageProfileId=0,
            statistics={},
            imdbId=s.get("imdbId", ""),
        )

    def lookup_series_by_tvdb(self, tvdb_id: int) -> Optional[SonarrSeries]:
        """Lookup series by TVDB ID (canonical tv:tvdb:* ids are common)."""
        try:
            data = self._get("/series/lookup", params={"term": f"tvdb:{tvdb_id}"}, timeout=20)
        except Exception:
            return None
        if not data:
            return None
        s = data[0]
        return SonarrSeries(
            id=0,
            tvdbId=s.get("tvdbId", tvdb_id),
            title=s.get("title", ""),
            year=s.get("year", 0),
            monitored=True,
            qualityProfileId=0,
            languageProfileId=0,
            statistics={},
            imdbId=s.get("imdbId", ""),
        )

    def search_series(self, title: str, year: Optional[int] = None) -> list[SonarrSeries]:
        """Search Sonarr by title (and optionally year). Returns candidate matches."""
        if not title:
            return []
        term = str(title).strip()
        if year:
            term = term + f" {year}"
        try:
            data = self._get("/series/lookup", params={"term": term}, timeout=20)
        except Exception:
            return []
        result = []
        for s in data or []:
            if not isinstance(s, dict):
                continue
            result.append(SonarrSeries(
                id=0,
                tvdbId=s.get("tvdbId", 0),
                title=s.get("title", ""),
                year=s.get("year", 0),
                monitored=True,
                qualityProfileId=0,
                languageProfileId=0,
                statistics={},
                imdbId=s.get("imdbId", ""),
            ))
        return result

    def resolve_tvdb_id(self, imdb_id: str) -> Optional[int]:
        """Resolve IMDb ID to TVDB ID (cached)."""
        if imdb_id in self._tvdb_cache:
            return self._tvdb_cache[imdb_id]
        series = self.lookup_series(imdb_id)
        if series and series.tvdbId:
            self._tvdb_cache[imdb_id] = series.tvdbId
            return series.tvdbId
        return None

    def find_series_by_tvdb(self, tvdb_id: int) -> Optional[SonarrSeries]:
        """Find existing series by TVDB ID."""
        series_list = self.get_series()
        for s in series_list:
            if s.tvdbId == tvdb_id:
                return s
        return None

    def add_series(self, imdb_id: str, quality_profile_id: Optional[int] = None,
                   title: str = "", year: Optional[int] = None,
                   tvdb_id: Optional[int] = None) -> AddResult:
        """Add series to Sonarr.

        Lookup priority: IMDb ID first, then the given TVDB ID (canonical
        ``tv:tvdb:*`` ids), then a title/year search as a last resort so a
        valid series is never rejected just because its id is stale/absent.
        """
        # Lookup by IMDb ID first.
        lookup = None
        if imdb_id:
            lookup = self.lookup_series(imdb_id)
        # Canonical ids are often tvdb/tmdb-only -> fall back to TVDB lookup.
        if (not lookup or not lookup.tvdbId) and tvdb_id:
            lookup = self.lookup_series_by_tvdb(tvdb_id)
        candidates = []
        if not lookup or not lookup.tvdbId:
            # IMDb lookup failed -> try title/year search
            candidates = self.search_series(title, year) if title else []
            if len(candidates) == 1:
                lookup = candidates[0]
            elif len(candidates) > 1:
                # Ambiguous -> pick an exact year (or exact title) match if
                # one exists, else return AMBIGUOUS rather than guessing.
                ltitle = str(title).strip().lower()
                exact = None
                for c in candidates:
                    if year and c.year == year:
                        exact = c
                        break
                if exact is None and ltitle:
                    exact = next((c for c in candidates if c.title.strip().lower() == ltitle), None)
                if exact:
                    lookup = exact
                else:
                    msg = ("Multiple Sonarr matches — pick one: " +
                           "; ".join(f"{c.title} ({c.year}, tvdb:{c.tvdbId})" for c in candidates[:10]))
                    return AddResult(False, None, msg, "ambiguous")

        if not lookup or not lookup.tvdbId:
            msg = f"No Sonarr match for imdb:{imdb_id}"
            if candidates:
                msg = ("Multiple Sonarr matches — pick one: " +
                       "; ".join(f"{c.title} ({c.year}, tvdb:{c.tvdbId})" for c in candidates[:10]))
                return AddResult(False, None, msg, "ambiguous")
            return AddResult(False, None, msg, "unavailable")

        tvdb_id = lookup.tvdbId

        # Check existing
        existing = self.find_series_by_tvdb(tvdb_id)
        if existing:
            return AddResult(True, existing, f"{existing.title} is already in Sonarr", "requested")

        # Get quality profile
        profiles = self.get_quality_profiles()
        qp = None
        if quality_profile_id:
            qp = next((p for p in profiles if p.id == quality_profile_id), None)
            if not qp:
                return AddResult(False, None, f"Quality profile {quality_profile_id} not found", "unavailable")
        else:
            qp_id = self.config.SONARR_QUALITY_PROFILE_ID
            if qp_id:
                qp = next((p for p in profiles if p.id == qp_id), None)
        if not qp:
            qp = profiles[0] if profiles else None
        if not qp:
            return AddResult(False, None, "Sonarr has no quality profiles configured", "unavailable")

        # Get language profile
        langs = self.get_language_profiles()
        lang = langs[0] if langs else None
        if not lang:
            return AddResult(False, None, "Sonarr has no language profiles configured", "unavailable")

        # Get root folder
        roots = self.get_root_folders()
        if not roots:
            return AddResult(False, None, "Sonarr has no root folder configured", "unavailable")
        root = roots[0]

        # Add series
        body = {
            "tvdbId": tvdb_id,
            "title": lookup.title,
            "qualityProfileId": qp.id,
            "languageProfileId": lang.id,
            "rootFolderPath": root.path,
            "monitored": True,
            "addOptions": {"searchForMissingEpisodes": True},
        }
        try:
            created = self._post("/series", body)
            series = SonarrSeries(
                id=created["id"],
                tvdbId=created["tvdbId"],
                title=created["title"],
                year=created.get("year", 0),
                monitored=created.get("monitored", True),
                qualityProfileId=created.get("qualityProfileId", qp.id),
                languageProfileId=created.get("languageProfileId", lang.id),
                statistics=created.get("statistics", {}),
            )
            self._series_cache = []
            return AddResult(True, series, f"{series.title} added to Sonarr — downloads starting", "requested")
        except Exception as e:
            return AddResult(False, None, f"Failed to add to Sonarr: {e}", "unavailable")

    def has_episodes(self, tvdb_id: int) -> bool:
            """Check if Sonarr has episode files for the series."""
            # Get series list without caching to get fresh data
            print(f"[has_episodes] Calling get_series(use_cache=False)")
            series_list = self.get_series(use_cache=False)
            print(f"[has_episodes] Got series list with {len(series_list)} items")
            for series in series_list:
                print(f"[has_episodes] Checking series: tvdbId={series.tvdbId}, statistics={series.statistics}")
                if series.tvdbId == tvdb_id:
                    stats = series.statistics or {}
                    result = int(stats.get("episodeFileCount", 0)) > 0
                    print(f"[has_episodes] Found series {tvdb_id}, episodeFileCount={stats.get('episodeFileCount', 0)}, returning {result}")
                    return result
            print(f"[has_episodes] Series {tvdb_id} not found")
            return False