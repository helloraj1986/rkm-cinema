"""Recommendation candidate generator (spec §21 Phase 12).

Turns candidate *sources* (TMDB discover/search endpoints, or an injected
curated list) into normalized :class:`RecommendationCandidate` objects. The
generator owns "where candidates come from"; the criteria engine decides
which survive. LAN-free in tests via a DI-injected ``tmdb``.

Multi-strategy discover: each run rotates through 3 strategies to pull
from a wider pool — popular (trending), top-rated (critically acclaimed),
and hidden gems (high rating, lower vote count). This prevents the pipeline
from always returning the same popular content already in Plex.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from domain.enums import MediaType
from services.recommendation.criteria import RecommendationCandidate

from services.tmdb import TMDBService

logger = logging.getLogger("rkm.recommendation.generator")

# Discover strategies — each returns different slices of TMDB content.
# The index rotates each run (time-based) so consecutive runs don't repeat.
_DISCOVER_STRATEGIES = [
    # Popular: trending content, high visibility
    {"sort_by": "popularity.desc", "vote_average.gte": 7.0, "label": "popular"},
    # Top-rated: critically acclaimed, may be older
    {"sort_by": "vote_average.desc", "vote_count.gte": 500, "vote_average.gte": 7.5, "label": "top_rated"},
    # Hidden gems: high quality, fewer votes (lesser-known but excellent)
    {"sort_by": "vote_average.desc", "vote_count.gte": 100, "vote_count.lte": 2000,
     "vote_average.gte": 7.0, "label": "hidden_gems"},
    # Recent: newest releases (last 2 years)
    {"sort_by": "primary_release_date.desc", "vote_average.gte": 6.5,
     "vote_count.gte": 50, "label": "recent"},
]


@dataclass
class CandidateSource:
    """A batch of raw candidate media to normalize (from TMDB or a curated list)."""

    media_type: MediaType
    items: list[dict] = field(default_factory=list)  # raw TMDB/curated dicts


class CandidateGenerator:
    """Normalize raw candidate media into RecommendationCandidate objects.

    ``source_fn`` is injected for testability and to allow the cron job to pass
    a curated list; when absent it defaults to TMDB discover.
    """

    def __init__(self, *, tmdb=None, source_fn=None, config=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self._tmdb_injected = tmdb
        self.source_fn = source_fn

    # ------------------------------------------------------------- sourcing
    def _tmdb(self):
        if self._tmdb_injected is not None:
            return self._tmdb_injected
        self._tmdb_injected = TMDBService(config=self.config)
        return self._tmdb_injected

    def candidates(self, *, category: str = "", count: int = 20,
                   media_type: MediaType = MediaType.MOVIE) -> list[RecommendationCandidate]:
        """Fetch + normalize candidate media for a category.

        Uses the injected ``source_fn(media_type, category, count)`` when given
        (returns raw dicts); otherwise TMDB discover with multi-strategy rotation.
        """
        if self.source_fn is not None:
            raw = self.source_fn(media_type, category, count) or []
        else:
            raw = self._discover(media_type, count)
        return self._normalize_all(raw, media_type)

    def _discover(self, media_type: MediaType, count: int) -> list[dict]:
        """TMDB discover with multi-strategy rotation.

        Rotates through popular / top-rated / hidden-gems / recent strategies
        so consecutive runs pull from different slices of the catalog.
        """
        tmdb = self._tmdb()
        if not self.config.TMDB_API_KEY:
            logger.warning("generator: no TMDB API key; no live candidates")
            return []
        try:
            endpoint = "discover/tv" if media_type is MediaType.TV else "discover/movie"
            strategy = self._pick_strategy()
            logger.info("generator: using '%s' strategy for %s",
                        strategy["label"], media_type.value)
            return self._discover_tmdb(tmdb, endpoint, count, strategy)
        except Exception as e:
            logger.warning("generator: TMDB discover failed: %s", e)
            return []

    @staticmethod
    def _pick_strategy() -> dict:
        """Pick a discover strategy by rotating through the list (time-based)."""
        idx = int(time.time()) % len(_DISCOVER_STRATEGIES)
        return _DISCOVER_STRATEGIES[idx]

    @staticmethod
    def _discover_tmdb(tmdb, endpoint: str, count: int,
                       strategy: Optional[dict] = None) -> list[dict]:
        if strategy is None:
            strategy = _DISCOVER_STRATEGIES[0]  # popular (legacy default)

        params = {
            "sort_by": strategy["sort_by"],
            "page": 1,
            "include_adult": "false",
        }
        # Add optional filters from the strategy
        for key in ("vote_average.gte", "vote_count.gte", "vote_count.lte"):
            if key in strategy:
                params[key] = strategy[key]

        data = tmdb._request(endpoint, params)
        raw = list((data or {}).get("results", [])[:count])
        # Map the numeric genre_ids TMDB discover returns into names so the
        # name-based genre criteria (include/exclude) work on this path.
        names = getattr(tmdb, "genre_names", lambda: {})()
        for item in raw:
            ids = item.get("genre_ids") or []
            if ids and names:
                item["genres"] = [names.get(int(i), str(i)) for i in ids]
        return raw

    # -------------------------------------------------------- normalization
    def _normalize_all(self, raw: list[dict], media_type: MediaType) -> list[RecommendationCandidate]:
        out = []
        for r in raw:
            try:
                out.append(self._normalize(r, media_type))
            except Exception as e:
                logger.debug("generator: skip invalid candidate: %s", e)
        return out

    @staticmethod
    def _normalize(r: dict, media_type: MediaType) -> RecommendationCandidate:
        """Normalize a TMDB/curated dict into a RecommendationCandidate."""
        if media_type is MediaType.TV:
            date_key, id_key = "first_air_date", "id"
            title_key = "name"
            genre_key = "genre_ids"
        else:
            date_key, id_key = "release_date", "id"
            title_key = "title"
            genre_key = "genre_ids"

        year = 0
        date_str = r.get(date_key) or ""
        if date_str and str(date_str)[:4].isdigit():
            year = int(str(date_str)[:4])

        genres = [str(g) for g in (r.get("genres") or r.get(genre_key) or [])]

        return RecommendationCandidate(
            media_type=media_type,
            title=str(r.get(title_key) or r.get("title") or r.get("name") or ""),
            year=year or None,
            tmdb_id=r.get(id_key) or r.get("tmdb_id"),
            imdb_id=str(r.get("imdb_id") or "") or "",
            tmdb_score=float(r.get("vote_average") or r.get("tmdb_score") or 0.0),
            vote_count=int(r.get("vote_count") or 0),
            imdb=float(r.get("imdb") or 0.0),
            rt=int(r.get("rt") or 0),
            genres=genres,
            category=str(r.get("category") or ""),
            lang=str(r.get("lang") or r.get("original_language") or "English"),
            snippet=str(r.get("overview") or r.get("snippet") or ""),
            poster=str(r.get("poster_path") or r.get("poster") or ""),
        )
