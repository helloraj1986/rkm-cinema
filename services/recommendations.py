"""Recommendation service - category rotation, quality gates, Plex check, metadata enrichment."""
import logging
import re
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from config.settings import get_config
from core.http_client import get_http_client
from core.exceptions import ValidationError, MetadataError
from domain.enums import MediaType
from domain.identity import MediaIdentity
from services.library import LibraryService, PlexLibraryProvider
from services.recommendation import CriteriaEngine, RecommendationCandidate
from services.trailers import TrailerService
from services.tmdb import TMDBService
from services.youtube import YouTubeService
from services.watchlist import WatchlistService, WatchlistEntry

logger = logging.getLogger("rkm.recommendations")


@dataclass
class Candidate:
    """A candidate recommendation before full enrichment."""
    title: str
    year: int
    category: str
    lang: str
    imdb: float
    rt: int
    is_series: bool
    imdb_id: str
    tmdb_id: int
    director: str
    cast: List[str]
    snippet: str
    poster: str = ""
    tmdb_score: float = 0.0     # TMDB rating (carried so the legacy gate can score
    vote_count: int = 0         # discover-sourced candidates, spec §22)


@dataclass
class EnrichedCandidate:
    """Fully enriched candidate ready for watchlist."""
    entry: WatchlistEntry


class RecommendationService:
    """Orchestrates the recommendation pipeline.

    Phase 12 (§22): the quality gates are now **config-driven** via the
    recommendation CriteriaEngine (config/recommendations.yaml) — the old
    hardcoded constants below are kept only as BC documentation and are not the
    source of truth. ``verify_quality_gate`` delegates to the CriteriaEngine
    (spec §43: criteria must be configuration, not Python).
    """

    # BC anchors (superseded by criteria config — kept for reference only).
    FILM_IMDB_GATE = 7.5
    FILM_RT_GATE = 80
    SERIES_IMDB_GATE = 8.0
    SERIES_RT_GATE = 85
    FOREIGN_IMDB_GATE = 8.0
    FOREIGN_RT_GATE = 85

    def __init__(self, *, config=None, http=None,
                 plex=None, library=None, trailers=None, tmdb=None, youtube=None, watchlist=None,
                 criteria=None):
        self.config = config if config is not None else get_config()
        self.http = http if http is not None else get_http_client()
        # Canonical ownership source = LibraryService. Legacy ``plex=`` (a
        # PlexService) is wrapped in a provider so every path funnels through
        # the library abstraction — no parallel PlexService branch (§43).
        self.library = library
        if self.library is None:
            providers = []
            if plex is not None:
                providers.append(PlexLibraryProvider(config=self.config, plex=plex))
            if providers:
                self.library = LibraryService(providers=providers)
        self._plex = plex  # kept only for BC-inspection; ownership uses `library`
        self.trailers = trailers if trailers is not None else TrailerService(config=self.config, http=self.http)
        self.tmdb = tmdb if tmdb is not None else TMDBService(config=self.config, http=self.http)
        self.youtube = youtube if youtube is not None else YouTubeService(config=self.config)
        self.watchlist = watchlist if watchlist is not None else WatchlistService()
        # §22 criteria engine (config-driven gates + scoring).
        self.criteria = criteria if criteria is not None else CriteriaEngine()

    def get_current_category(self) -> str:
        """Get current rotation category."""
        return self.watchlist.get_current_category()

    def rotate_category(self) -> str:
        """Rotate to next category."""
        return self.watchlist.rotate_category()

    def verify_quality_gate(self, candidate: Candidate) -> bool:
        """Verify candidate meets quality gates (config-driven, spec §22).

        Delegates to the CriteriaEngine. Builds a RecommendationCandidate from
        the legacy Candidate shape; the engine's tmdb/imdb/rt gates (from
        config/recommendations.yaml) decide PASS/FAIL.
        """
        rc = RecommendationCandidate(
            media_type=MediaType.TV if candidate.is_series else MediaType.MOVIE,
            title=candidate.title,
            year=candidate.year,
            tmdb_id=candidate.tmdb_id or None,
            imdb_id=candidate.imdb_id or None,
            tmdb_score=candidate.tmdb_score,
            vote_count=candidate.vote_count,
            imdb=candidate.imdb,
            rt=candidate.rt,
            lang=candidate.lang,
        )
        return self.criteria.evaluate(rc).passed

    def check_plex_ownership(self, candidate: Candidate) -> bool:
        """Check if media already exists in the library (ground truth).

        Uses the unified LibraryService (stable-identity match, spec §1.2
        library = authority). If no library is configured we conservatively say
        NOT owned so a recommendation isn't wrongly held back.
        """
        if not self.library:
            return False
        identity = MediaIdentity(
            media_type=MediaType.TV if candidate.is_series else MediaType.MOVIE,
            tmdb_id=candidate.tmdb_id or None,
            imdb_id=candidate.imdb_id or None,
        )
        return self.library.has(identity, title=candidate.title, year=candidate.year)

    def check_watchlist_duplicate(self, candidate: Candidate) -> bool:
        """Check if already in watchlist (pending or recommended), by either
        canonical id (imdb or tmdb). TMDB-discover candidates often carry only
        a tmdb id, so the imdb-only check alone would miss duplicates."""
        if candidate.imdb_id and self.watchlist.find_by_imdb(candidate.imdb_id):
            return True
        if candidate.tmdb_id and self.watchlist.find_by_tmdb(candidate.tmdb_id):
            return True
        return False

    def find_candidates(self, category: str, count: int = 2) -> List[Candidate]:
        """
        Find candidate titles for a category.
        In production, this would query TMDB discover or use a curated list.
        For now, returns a curated set per category.
        """
        # This is a placeholder - in reality you'd use TMDB discover API
        # or maintain a curated database. The cron job will provide candidates.
        logger.info("Finding candidates for category: %s (count=%d)", category, count)
        return []

    def enrich_metadata(self, candidate: Candidate) -> EnrichedCandidate:
        """Enrich candidate with poster, trailer, and validate all fields."""
        # Build base entry with candidate's basic info
        entry = WatchlistEntry(
            title=candidate.title,
            year=candidate.year,
            category=candidate.category,
            lang=candidate.lang,
            rt=candidate.rt,
            imdb=candidate.imdb,
            isSeries=candidate.is_series,
            imdbId=candidate.imdb_id,
            tmdbId=candidate.tmdb_id,
            cert=candidate.snippet,  # Will be replaced if we have cert from TMDB in the future
            snippet=candidate.snippet,
            cast=candidate.cast,
            director=candidate.director,
            poster=candidate.poster or "",
            trailerId="",
            trailerTitle="",
            added=datetime.now().date().isoformat(),
        )

        # 1. Enrich with TMDB metadata
        if candidate.tmdb_id:
            if candidate.is_series:
                tmdb_data = self.tmdb.get_show_details(candidate.tmdb_id)
            else:
                tmdb_data = self.tmdb.get_movie_details(candidate.tmdb_id)
            if tmdb_data:
                entry.tmdb_overview = tmdb_data.get("overview", "")
                entry.backdrop = tmdb_data.get("backdrop", "")
                entry.tmdb_score = tmdb_data.get("tmdb_score", 0.0)
                entry.runtime = tmdb_data.get("runtime", 0)
                entry.genres = tmdb_data.get("genres", [])
                # Authoritative artwork: always take the TMDB poster/backdrop so
                # candidates with empty or fabricated poster URLs never leak through.
                tmdb_poster = tmdb_data.get("poster", "")
                if self._is_valid_poster(tmdb_poster):
                    entry.poster = tmdb_poster
                # IMDb ID from external_ids + rating from OMDb
                ext_imdb_id = tmdb_data.get("imdb_id", "")
                if ext_imdb_id:
                    entry.imdbId = ext_imdb_id
                    try:
                        imdb_rating = self.tmdb.get_imdb_rating(ext_imdb_id)
                        if isinstance(imdb_rating, (int, float)) and imdb_rating > 0:
                            entry.imdb = imdb_rating
                    except Exception:
                        pass  # IMDb rating is optional enrichment

        # 2. Enrich with trailer: try YouTube first, then fallback to trailer service
        trailer_info = None
        if self.youtube.has_youtube():
            trailer_info = self.youtube.search_trailer(candidate.title, candidate.year, candidate.is_series)
        if not trailer_info:
            # Fallback to existing trailer service
            temp_entry = entry.to_dict()
            temp_entry = self.trailers.enrich_entry(temp_entry)
            if temp_entry.get("trailerId") and self.trailers.validate_trailer(temp_entry["trailerId"]):
                trailer_info = {
                    "trailer_id": temp_entry["trailerId"],
                    "trailer_title": temp_entry["trailerTitle"],
                    "source": "trailer_service"
                }

        if trailer_info:
            entry.trailerId = trailer_info["trailer_id"]
            entry.trailerTitle = trailer_info["trailer_title"]

        # 3. Validate required fields
        self._validate_entry(entry.to_dict())

        return EnrichedCandidate(WatchlistEntry.from_dict(entry.to_dict()))

    def _is_valid_poster(self, url: str) -> bool:
        """Self-healing poster check: must be a real image that resolves (HTTP 200).

        Rejects empty values and fabricated URLs by doing a real HEAD against the
        image so dead links never reach the dashboard. TMDB URLs are preferred.
        """
        if not url:
            return False
        try:
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "RKM-Cinema/3.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status != 200:
                    return False
                ctype = r.headers.get("Content-Type", "")
                return ctype.startswith("image/")
        except Exception:
            return False

    def _validate_entry(self, entry: dict) -> None:
        """Validate all required fields are present and valid.

        A canonical media id (imdbId OR tmdbId) is required — TMDB-discover
        yields tmdb-only titles, which is the canonical identity (§8/§9). Both
        are not needed simultaneously.
        """
        for field in ["title", "year", "added"]:
            if not entry.get(field):
                raise ValidationError(field, entry.get(field), "Required field missing")
        if not (entry.get("imdbId") or entry.get("tmdbId")):
            raise ValidationError("imdbId/tmdbId", None, "Required: a canonical media id (imdb or tmdb)")

        if entry.get("trailerId") and not self.trailers.validate_trailer(entry["trailerId"]):
            logger.warning("Invalid trailer ID for %s: %s", entry["title"], entry["trailerId"])
            entry["trailerId"] = ""
            entry["trailerTitle"] = ""

    def add_to_watchlist(self, enriched: EnrichedCandidate) -> WatchlistEntry:
        """Add enriched candidate to watchlist pending."""
        self.watchlist.add_pending(enriched.entry)
        logger.info("Added to watchlist: %s (%d)", enriched.entry.title, enriched.entry.year)
        return enriched.entry

    def process_recommendation(self, candidate: Candidate) -> Optional[WatchlistEntry]:
        """
        Full pipeline: quality gate -> Plex check -> duplicate check -> enrich -> add.
        Returns the added entry or None if rejected.
        """
        # 1. Quality gate
        if not self.verify_quality_gate(candidate):
            logger.info("REJECTED %s: Failed quality gate (IMDb=%.1f, RT=%d%%)",
                       candidate.title, candidate.imdb, candidate.rt)
            return None

        # 2. Plex ownership check (ground truth)
        if self.check_plex_ownership(candidate):
            logger.info("REJECTED %s: Already in Plex", candidate.title)
            return None

        # 3. Watchlist duplicate check
        if self.check_watchlist_duplicate(candidate):
            logger.info("REJECTED %s: Already in watchlist", candidate.title)
            return None

        # 4. Enrich metadata (trailer, etc.)
        try:
            enriched = self.enrich_metadata(candidate)
        except Exception as e:
            logger.error("Enrichment failed for %s: %s", candidate.title, e)
            return None

        # 5. Add to watchlist
        try:
            return self.add_to_watchlist(enriched)
        except Exception as e:
            logger.error("Failed to add %s to watchlist: %s", candidate.title, e)
            return None