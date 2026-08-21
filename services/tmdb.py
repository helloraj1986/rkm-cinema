"""
TMDB service for fetching metadata.
"""
import logging
from typing import Any, Dict, List, Optional

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
        """Get detailed information for a movie."""
        if not tmdb_id:
            return None
        try:
            data = self._request(f"movie/{tmdb_id}", {
                "append_to_response": "credits,release_dates"
            })
            return self._parse_movie_data(data)
        except Exception as e:
            logger.error(f"Failed to get movie details for TMDB ID {tmdb_id}: {e}")
            return None

    def get_show_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information for a TV show."""
        if not tmdb_id:
            return None
        try:
            data = self._request(f"tv/{tmdb_id}", {
                "append_to_response": "credits,content_ratings"
            })
            return self._parse_show_data(data)
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
            "overview": overview,
            "cert": cert,
            "cast": cast,
            "director": creator,  # Using creator as director for TV shows
        }

    def search_movie(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Search for a movie by title and year."""
        if not title:
            return None
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
        """Search for a TV show by title and year."""
        if not title:
            return None
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