"""Recommendation candidate generator (spec §21 Phase 12).

Turns candidate *sources* (TMDB discover/search endpoints, or an injected
curated list) into normalized :class:`RecommendationCandidate` objects. The
generator owns "where candidates come from"; the criteria engine decides
which survive. LAN-free in tests via a DI-injected ``tmdb``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from domain.enums import MediaType
from services.recommendation.criteria import RecommendationCandidate

logger = logging.getLogger("rkm.recommendation.generator")


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
        self._tmdb = tmdb
        self.source_fn = source_fn

    # ------------------------------------------------------------- sourcing
    def _tmdb(self):
        if self._tmdb is not None:
            return self._tmdb
        from services.tmdb import TMDBService
        self._tmdb = TMDBService(config=self.config)
        return self._tmdb

    def candidates(self, *, category: str = "", count: int = 20,
                   media_type: MediaType = MediaType.MOVIE) -> list[RecommendationCandidate]:
        """Fetch + normalize candidate media for a category.

        Uses the injected ``source_fn(media_type, category, count)`` when given
        (returns raw dicts); otherwise TMDB discover.
        """
        if self.source_fn is not None:
            raw = self.source_fn(media_type, category, count) or []
        else:
            raw = self._discover(media_type, count)
        return self._normalize_all(raw, media_type)

    def _discover(self, media_type: MediaType, count: int) -> list[dict]:
        """TMDB discover (popular/discovering) for the media type."""
        tmdb = self._tmdb()
        if not self.config.TMDB_API_KEY:
            logger.warning("generator: no TMDB API key; no live candidates")
            return []
        try:
            if media_type is MediaType.TV:
                return self._discover_tmdb(tmdb, "discover/tv", count)
            return self._discover_tmdb(tmdb, "discover/movie", count)
        except Exception as e:
            logger.warning("generator: TMDB discover failed: %s", e)
            return []

    @staticmethod
    def _discover_tmdb(tmdb, endpoint: str, count: int) -> list[dict]:
        params = {
            "sort_by": "popularity.desc",
            "vote_average.gte": 7.0,
            "page": 1,
            "include_adult": "false",
        }
        data = tmdb._request(endpoint, params)
        return (data or {}).get("results", [])[:count]

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