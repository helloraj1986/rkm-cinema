"""
TMDB service for fetching metadata.
"""
import logging
from typing import Any, Dict, Optional

from config.settings import get_config
from core.http_client import get_http_client
from core.exceptions import ServiceUnavailableError

logger = logging.getLogger("rkm.tmdb")


class TMDBService:
    """TMDB integration for metadata and artwork."""

    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

    def __init__(self, *, config=None, http=None):
        self.config = config if config is not None else get_config()
        self.http = http if http is not None else get_http_client()
        # Metadata cache (spec §29 "TMDB metadata: hours/days"). TTL from
        # config (TMDB_CACHE_TTL, default 6h). Shared here so a multi-item
        # reconcile/daily job never re-fetches the same title's metadata.
        from core.cache import TTLCache
        self._cache = TTLCache(default_ttl=getattr(self.config, "TMDB_CACHE_TTL", 21600))

    def clear_cache(self) -> None:
        """Drop all cached metadata (e.g. before a forced refresh)."""
        self._cache.clear()

    def get_imdb_rating(self, imdb_id: str) -> float:
        """Fetch IMDb rating by IMDb ID (e.g. 'tt0133093').

        Uses OMDb API (free tier, 1000 req/day). Returns 0.0 on failure.
        """
        if not imdb_id or not imdb_id.startswith("tt"):
            return 0.0
        cache_key = f"imdb:{imdb_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            import urllib.request
            import urllib.parse
            import json as _json
            # OMDb free tier (limited but no key needed for basic lookups)
            # Falls back to 0.0 if unavailable
            url = f"http://www.omdbapi.com/?i={imdb_id}&apikey=trilogy"
            req = urllib.request.Request(url, headers={"User-Agent": "RKM-Cinema/3.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read())
                rating = float(data.get("imdbRating") or 0)
                if rating > 0:
                    self._cache.set(cache_key, rating)
                return rating
        except Exception as e:
            logger.debug("IMDb rating fetch failed for %s: %s", imdb_id, e)
            return 0.0

    def genre_names(self) -> dict[int, str]:
        """TMDB genre id -> name for movie + tv lists (merged, cached 6h).

        Lets the recommendation generator map the numeric ``genre_ids`` TMDB
        discover returns into names, so name-based criteria (e.g. exclude
        ["horror"]) actually fire on the TMDB path.
        """
        def _load():
            merged: dict[int, str] = {}
            for endpoint in ("genre/movie/list", "genre/tv/list"):
                data = self._request(endpoint)
                for g in (data or {}).get("genres", []) or []:
                    merged[int(g["id"])] = str(g["name"])
            return merged
        return self._cached("genres:all", _load) or {}

    def _cached(self, key: str, loader):
        """Return cached *key* or compute via *loader* and store it."""
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        value = loader()
        if value is not None:
            self._cache.set(key, value)
        return value

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a request to TMDB API."""
        if not self.config.TMDB_API_KEY:
            raise ServiceUnavailableError("TMDB API key not configured")

        if params is None:
            params = {}
        params["api_key"] = self.config.TMDB_API_KEY

        url = f"{self.BASE_URL}/{endpoint}"
        try:
            return self.http.get(url, params=params)
        except Exception as e:
            logger.error(f"TMDB request failed for {endpoint}: {e}")
            raise ServiceUnavailableError("tmdb", f"TMDB request failed: {e}") from e

    def get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information for a movie (cached)."""
        if not tmdb_id:
            return None
        return self._cached(f"movie:{tmdb_id}", lambda: self._get_movie_details(tmdb_id))

    def _get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        try:
            data = self._request(f"movie/{tmdb_id}", {
                "append_to_response": "credits,release_dates,external_ids"
            })
            result = self._parse_movie_data(data)
            # Attach IMDb ID from external_ids (for rating lookup)
            ext_ids = data.get("external_ids", {})
            if ext_ids and ext_ids.get("imdb_id"):
                result["imdb_id"] = ext_ids["imdb_id"]
            return result
        except Exception as e:
            logger.error(f"Failed to get movie details for TMDB ID {tmdb_id}: {e}")
            return None

    def get_show_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information for a TV show (cached)."""
        if not tmdb_id:
            return None
        return self._cached(f"show:{tmdb_id}", lambda: self._get_show_details(tmdb_id))

    def get_show_external_ids(self, tmdb_id: int) -> Optional[str]:
        """Resolve a TMDB show id to its TVDB id via the lightweight
        ``/tv/{id}/external_ids`` endpoint (fast, cached).

        Returns None when the id is missing or the fetch fails. Callers use this
        to map tmdb-only canonical ids (``tv:tmdb:*``) onto a TVDB id so the
        acquisition layer can match Sonarr's series list — far lighter than a
        full ``get_show_details`` and immune to the live Sonarr lookup timeout.
        """
        if not tmdb_id:
            return None
        try:
            data = self._cached(
                f"tv:{tmdb_id}:external_ids",
                lambda: self._request(f"tv/{tmdb_id}/external_ids"),
            )
        except Exception as e:
            logger.warning("tmdb external_ids lookup failed for %s: %s", tmdb_id, e)
            return None
        if not data:
            return None
        tvdb = (data or {}).get("tvdb_id")
        return str(tvdb) if tvdb else None

    def _get_show_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        try:
            data = self._request(f"tv/{tmdb_id}", {
                "append_to_response": "credits,content_ratings,external_ids"
            })
            result = self._parse_show_data(data)
            # Attach IMDb / TVDB ids from external_ids (for rating lookup +
            # tmdb→tvdb resolution; cache them both).
            ext_ids = data.get("external_ids", {})
            if ext_ids and ext_ids.get("imdb_id"):
                result["imdb_id"] = ext_ids["imdb_id"]
            if ext_ids and ext_ids.get("tvdb_id"):
                result["tvdb_id"] = ext_ids["tvdb_id"]
            return result
        except Exception as e:
            logger.error(f"Failed to get show details for TMDB ID {tmdb_id}: {e}")
            return None

    def _parse_movie_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse movie data from TMDB response."""
        # Extract genres
        genres = [g["name"] for g in data.get("genres", [])]

        # Extract poster and backdrop paths
        poster_path = data.get("poster_path")
        backdrop_path = data.get("backdrop_path")
        poster = f"{self.IMAGE_BASE_URL}/w500{poster_path}" if poster_path else ""
        backdrop = f"{self.IMAGE_BASE_URL}/w1280{backdrop_path}" if backdrop_path else ""

        # Extract release date and year
        release_date = data.get("release_date", "")
        year = int(release_date[:4]) if release_date and release_date[:4].isdigit() else 0

        # Extract runtime
        runtime = data.get("runtime", 0)

        # Extract vote average
        vote_average = data.get("vote_average", 0.0)
        vote_count = data.get("vote_count", 0)

        # Extract credits (cast and director)
        credits = data.get("credits", {})
        cast = [c["name"] for c in credits.get("cast", [])[:10]]  # Top 10 cast
        director = ""
        for crew in credits.get("crew", []):
            if crew.get("job") == "Director":
                director = crew.get("name", "")
                break

        # Extract overview
        overview = data.get("overview", "")

        # Extract certification
        cert = ""
        release_dates = data.get("release_dates", {}).get("results", [])
        for country in release_dates:
            if country.get("iso_3166_1") == "US":
                for cert_info in country.get("release_dates", []):
                    cert = cert_info.get("certification", "")
                    break
                break

        return {
            "tmdb_id": data.get("id"),
            "title": data.get("title", ""),
            "year": year,
            "genres": genres,
            "poster": poster,
            "backdrop": backdrop,
            "runtime": runtime,
            "tmdb_score": vote_average,
            "vote_count": vote_count,
            "overview": overview,
            "cert": cert,
            "cast": cast,
            "director": director,
        }

    def _parse_show_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse TV show data from TMDB response."""
        # Extract genres
        genres = [g["name"] for g in data.get("genres", [])]

        # Extract poster and backdrop paths
        poster_path = data.get("poster_path")
        backdrop_path = data.get("backdrop_path")
        poster = f"{self.IMAGE_BASE_URL}/w500{poster_path}" if poster_path else ""
        backdrop = f"{self.IMAGE_BASE_URL}/w1280{backdrop_path}" if backdrop_path else ""

        # Extract first air date and year
        first_air_date = data.get("first_air_date", "")
        year = int(first_air_date[:4]) if first_air_date and first_air_date[:4].isdigit() else 0

        # Extract episode runtime (use first episode's runtime or average?)
        # For simplicity, we'll use the episode_run_time from the first season if available
        runtime = 0
        episode_run_time = data.get("episode_run_time", [])
        if episode_run_time:
            runtime = episode_run_time[0]  # Use first episode runtime

        # Extract vote average
        vote_average = data.get("vote_average", 0.0)
        vote_count = data.get("vote_count", 0)

        # Extract credits (cast and creator/director)
        credits = data.get("credits", {})
        cast = [c["name"] for c in credits.get("cast", [])[:10]]  # Top 10 cast
        # For TV shows, we might look for creator or director; we'll use creator for simplicity
        creator = ""
        for crew in data.get("created_by", []):
            creator = crew.get("name", "")
            break
        # If no creator, look for director in crew
        if not creator:
            for crew in credits.get("crew", []):
                if crew.get("job") == "Director":
                    creator = crew.get("name", "")
                    break

        # Extract overview
        overview = data.get("overview", "")

        # Extract certification
        cert = ""
        content_ratings = data.get("content_ratings", {}).get("results", [])
        for rating in content_ratings:
            if rating.get("iso_3166_1") == "US":
                cert = rating.get("rating", "")
                break

        return {
            "tmdb_id": data.get("id"),
            "title": data.get("name", ""),
            "year": year,
            "genres": genres,
            "poster": poster,
            "backdrop": backdrop,
            "runtime": runtime,
            "tmdb_score": vote_average,
            "vote_count": vote_count,
            "overview": overview,
            "cert": cert,
            "cast": cast,
            "director": creator,  # Using creator as director for TV shows
        }

    def search_movie(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Search for a movie by title and year (cached)."""
        if not title:
            return None
        key = f"find:movie:{str(title).lower().strip()}:{year or ''}"
        return self._cached(key, lambda: self._search_movie(title, year))

    def _search_movie(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        params = {
            "query": title,
            "include_adult": "false",
        }
        if year:
            params["year"] = year
        try:
            data = self._request("search/movie", params)
            results = data.get("results", [])
            if results:
                # Return the first result
                return self._parse_movie_data(results[0])
        except Exception as e:
            logger.error(f"TMDB movie search failed for {title}: {e}")
        return None

    def search_show(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Search for a TV show by title and year (cached)."""
        if not title:
            return None
        key = f"find:show:{str(title).lower().strip()}:{year or ''}"
        return self._cached(key, lambda: self._search_show(title, year))

    def _search_show(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        params = {
            "query": title,
            "include_adult": "false",
        }
        if year:
            params["first_air_date_year"] = year
        try:
            data = self._request("search/tv", params)
            results = data.get("results", [])
            if results:
                # Return the first result
                return self._parse_show_data(results[0])
        except Exception as e:
            logger.error(f"TMDB show search failed for {title}: {e}")
        return None