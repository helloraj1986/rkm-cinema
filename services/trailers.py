"""Trailer enrichment service (TVDB v4 + TMDB fallback)."""
import json
import logging
import re
import time
import urllib.parse
from typing import Optional
from dataclasses import dataclass

from config.settings import get_config
from core.http_client import get_http_client, HTTPError
from core.exceptions import TrailerError


logger = logging.getLogger("rkm.trailers")


@dataclass
class TrailerInfo:
    trailer_id: str
    trailer_title: str
    source: str  # "tvdb" or "tmdb"


class TrailerService:
    """Trailer enrichment using TVDB v4 (primary) and TMDB (fallback)."""

    TVDB_BASE = "https://api4.thetvdb.com/v4"
    TMDB_BASE = "https://api.themoviedb.org/3"

    def __init__(self):
        self.config = get_config()
        self.http = get_http_client()
        self._tvdb_token: Optional[str] = None
        self._tvdb_token_expiry: float = 0
        self._tvdb_token_path = "/workspace/media/.tvdb_token"

    def _load_tvdb_token(self) -> Optional[str]:
        """Load cached TVDB token."""
        try:
            with open(self._tvdb_token_path) as f:
                data = json.load(f)
                if data.get("expires", 0) > time.time():
                    return data["token"]
        except Exception:
            pass
        return None

    def _save_tvdb_token(self, token: str) -> None:
        """Save TVDB token to cache."""
        try:
            with open(self._tvdb_token_path, "w") as f:
                json.dump({"token": token, "expires": time.time() + 25 * 86400}, f)
        except Exception as e:
            logger.warning("Failed to save TVDB token: %s", e)

    def _get_tvdb_token(self) -> Optional[str]:
        """Get valid TVDB JWT token."""
        if self._tvdb_token and time.time() < self._tvdb_token_expiry:
            return self._tvdb_token

        # Try cached
        cached = self._load_tvdb_token()
        if cached:
            self._tvdb_token = cached
            self._tvdb_token_expiry = time.time() + 25 * 86400
            return cached

        # Login
        if not self.config.TVDB_API_KEY:
            return None

        try:
            data = self.http.post(
                f"{self.TVDB_BASE}/login",
                {"apikey": self.config.TVDB_API_KEY},
                headers={"Content-Type": "application/json"},
            )
            token = data["data"]["token"]
            self._tvdb_token = token
            self._tvdb_token_expiry = time.time() + 25 * 86400
            self._save_tvdb_token(token)
            return token
        except Exception as e:
            logger.error("TVDB login failed: %s", e)
            return None

    def _tvdb_headers(self) -> dict:
        token = self._get_tvdb_token()
        if not token:
            raise TrailerError("TVDB token not available")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def _extract_youtube_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL."""
        match = re.search(r"(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)([\w-]{11})", url or "")
        return match.group(1) if match else None

    def _tvdb_search(self, title: str, year: int, is_series: bool) -> Optional[dict]:
        """Search TVDB for a title."""
        kind = "series" if is_series else "movies"
        query = urllib.parse.quote(title)
        url = f"{self.TVDB_BASE}/search?query={query}&type={kind}&year={year}"
        try:
            data = self.http.get(url, headers=self._tvdb_headers())
            return data.get("data", [])
        except Exception as e:
            logger.error("TVDB search failed for %s: %s", title, e)
            return None

    def _tvdb_extended(self, tvdb_id: int, is_series: bool) -> Optional[dict]:
        """Get extended info including trailers."""
        kind = "series" if is_series else "movies"
        url = f"{self.TVDB_BASE}/{kind}/{tvdb_id}/extended"
        try:
            data = self.http.get(url, headers=self._tvdb_headers())
            return data.get("data", {})
        except Exception as e:
            logger.error("TVDB extended failed for %s: %s", tvdb_id, e)
            return None

    def get_tvdb_trailer(self, title: str, year: int, is_series: bool, imdb_id: str) -> Optional[TrailerInfo]:
        """Get trailer from TVDB."""
        if not self.config.TVDB_API_KEY:
            return None

        results = self._tvdb_search(title, year, is_series)
        if not results:
            return None

        # Match by IMDb ID in remoteids
        for result in results:
            remote_ids = result.get("remoteids", [])
            imdb_matches = [str(r.get("id", "")) for r in remote_ids if r.get("sourceName") == "imdb"]
            if imdb_id in imdb_matches:
                tvdb_id = result.get("id")
                if not tvdb_id:
                    continue

                extended = self._tvdb_extended(tvdb_id, is_series)
                if not extended:
                    continue

                trailers = extended.get("trailers", [])
                for trailer in trailers:
                    yt_id = self._extract_youtube_id(trailer.get("url", ""))
                    if yt_id:
                        return TrailerInfo(
                            trailer_id=yt_id,
                            trailer_title=trailer.get("name") or "Official Trailer",
                            source="tvdb"
                        )
        return None

    def get_tmdb_trailer(self, tmdb_id: int, is_series: bool) -> Optional[TrailerInfo]:
        """Get trailer from TMDB (fallback)."""
        if not self.config.TMDB_API_KEY:
            return None

        kind = "tv" if is_series else "movie"
        url = f"{self.TMDB_BASE}/{kind}/{tmdb_id}/videos"
        params = {"api_key": self.config.TMDB_API_KEY}
        try:
            data = self.http.get(url, params=params)
            for video in data.get("results", []):
                if video.get("site") == "YouTube" and video.get("type") == "Trailer":
                    return TrailerInfo(
                        trailer_id=video["key"],
                        trailer_title=video.get("name") or "Official Trailer",
                        source="tmdb"
                    )
        except Exception as e:
            logger.error("TMDB trailer failed for %s: %s", tmdb_id, e)
        return None

    def validate_trailer(self, trailer_id: str) -> bool:
        """Validate YouTube trailer ID format."""
        if not trailer_id:
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", trailer_id))

    def enrich_entry(self, entry: dict) -> dict:
        """Enrich a watchlist entry with trailer info."""
        # Check existing trailer
        existing_trailer = entry.get("trailerId")
        if existing_trailer and self.validate_trailer(existing_trailer):
            return entry  # Already has valid trailer

        # Clear invalid trailer ID
        if existing_trailer and not self.validate_trailer(existing_trailer):
            entry["trailerId"] = ""
            entry["trailerTitle"] = ""

        imdb_id = entry.get("imdbId", "")
        tmdb_id = entry.get("tmdbId")
        is_series = entry.get("isSeries", False)
        title = entry.get("title", "")
        year = entry.get("year", 0)

        # Try TVDB first
        trailer = self.get_tvdb_trailer(title, year, is_series, imdb_id)

        # Fallback to TMDB
        if not trailer and tmdb_id:
            trailer = self.get_tmdb_trailer(tmdb_id, is_series)

        if trailer:
            entry["trailerId"] = trailer.trailer_id
            entry["trailerTitle"] = trailer.trailer_title
            logger.info("Enriched %s with trailer %s (source: %s)", title, trailer.trailer_id, trailer.source)
        else:
            logger.info("No verified trailer found for %s", title)

        return entry

    def probe(self) -> dict:
        """Test TVDB/TMDB endpoints and return diagnostic info."""
        results = {
            "tvdb_key_present": bool(self.config.TVDB_API_KEY),
            "tmdb_key_present": bool(self.config.TMDB_API_KEY),
            "tvdb_login": False,
            "tvdb_search": False,
            "tvdb_extended": False,
            "tmdb_videos": False,
        }

        if not self.config.TVDB_API_KEY:
            return results

        try:
            token = self._get_tvdb_token()
            results["tvdb_login"] = bool(token)
            if token:
                # Test search
                data = self.http.get(
                    f"{self.TVDB_BASE}/search?query=Prisoners&type=movie&year=2013",
                    headers=self._tvdb_headers(),
                )
                results["tvdb_search"] = bool(data.get("data"))
                if data.get("data"):
                    first = data["data"][0]
                    tvdb_id = first.get("id")
                    results["remoteids_sample"] = first.get("remoteids", [])[:3]
                    if tvdb_id:
                        ext = self.http.get(
                            f"{self.TVDB_BASE}/movies/{tvdb_id}/extended",
                            headers=self._tvdb_headers(),
                        )
                        results["tvdb_extended"] = bool(ext.get("data"))
                        if ext.get("data"):
                            results["trailers_sample"] = ext["data"].get("trailers", [])[:2]
        except Exception as e:
            results["tvdb_error"] = str(e)

        if self.config.TMDB_API_KEY:
            try:
                data = self.http.get(
                    f"{self.TMDB_BASE}/movie/146233/videos",
                    params={"api_key": self.config.TMDB_API_KEY},
                )
                results["tmdb_videos"] = bool(data.get("results"))
            except Exception as e:
                results["tmdb_error"] = str(e)

        return results