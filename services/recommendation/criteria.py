"""Recommendation criteria engine (spec §22 Phase 12).

Criteria live in ``config/recommendations.yaml`` — NOT hardcoded in Python. The
:class:`CriteriaEngine` loads them once and evaluates a normalized candidate,
returning a :class:`CriteriaResult` with ``passed`` + a 0-100 ``score`` + the
``reasons`` for each PASS/FAIL (spec §22 shows the exact shape).

Candidates are :class:`RecommendationCandidate` (a normalized shape produced by
the generator). The engine is pure: no HTTP, no side effects, fully testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from domain.enums import MediaType

try:
    import yaml
except ImportError:  # pragma: no cover - container has PyYAML via requirements
    yaml = None

__all__ = [
    "RecommendationCandidate",
    "CriteriaResult",
    "RecommendationCriteria",
    "CriteriaEngine",
    "DEFAULT_CONFIG_PATH",
]

DEFAULT_CONFIG_PATH = Path("config/recommendations.yaml")


@dataclass
class RecommendationCandidate:
    """A normalized candidate for the criteria engine (generator output shape)."""

    media_type: MediaType
    title: str = ""
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    imdb_id: str = ""
    tmdb_score: float = 0.0
    vote_count: int = 0
    imdb: float = 0.0
    rt: int = 0
    genres: list[str] = field(default_factory=list)
    category: str = ""
    lang: str = ""
    snippet: str = ""
    poster: str = ""

    @property
    def media_id(self) -> str:
        """Canonical media_id (best available provider id)."""
        src = None
        if self.tmdb_id:
            src = f"tmdb:{self.tmdb_id}"
        elif self.imdb_id:
            im = self.imdb_id if self.imdb_id.lower().startswith("tt") else "tt" + self.imdb_id
            src = f"imdb:{im}"
        elif self.title:
            src = f"title:{self.title.strip()[:64]}"
        kind = "tv" if self.media_type is MediaType.TV else "movie"
        return f"{kind}:{src}" if src else f"{kind}:title:unknown"


@dataclass
class CriteriaResult:
    """Outcome of evaluating one candidate against criteria (spec §22)."""

    passed: bool
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class _MediaCriteria:
    min_tmdb_rating: float = 7.5
    min_vote_count: int = 0
    years: list[int] = field(default_factory=list)
    genres_include: list[str] = field(default_factory=list)
    genres_exclude: list[str] = field(default_factory=list)
    min_imdb: float = 0.0
    min_rt: int = 0
    rt_any: bool = True
    score_weight: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> "_MediaCriteria":
        genres = d.get("genres") or {}
        return cls(
            min_tmdb_rating=float(d.get("min_tmdb_rating", 7.5)),
            min_vote_count=int(d.get("min_vote_count", 0)),
            years=[int(y) for y in (d.get("years") or [])],
            genres_include=[str(g).strip().lower() for g in (genres.get("include") or [])],
            genres_exclude=[str(g).strip().lower() for g in (genres.get("exclude") or [])],
            min_imdb=float(d.get("min_imdb", 0.0)),
            min_rt=int(d.get("min_rt", 0)),
            rt_any=bool(d.get("rt_any", True)),
            score_weight=float(d.get("score_weight", 1.0)),
        )


@dataclass
class RecommendationCriteria:
    """Loaded criteria for both media types + scoring anchors."""

    movies: _MediaCriteria = field(default_factory=_MediaCriteria)
    series: _MediaCriteria = field(default_factory=_MediaCriteria)
    score_tmdb_weight: float = 0.6
    score_imdb_weight: float = 0.3
    score_recent_bonus: float = 0.1

    def for_type(self, media_type: MediaType) -> _MediaCriteria:
        return self.series if media_type is MediaType.TV else self.movies

    @classmethod
    def from_dict(cls, raw: dict) -> "RecommendationCriteria":
        rec = raw.get("recommendations") or {}
        score = rec.get("score") or {}
        return cls(
            movies=_MediaCriteria.from_dict(rec.get("movies") or {}),
            series=_MediaCriteria.from_dict(rec.get("series") or {}),
            score_tmdb_weight=float(score.get("tmdb_weight", 0.6)),
            score_imdb_weight=float(score.get("imdb_weight", 0.3)),
            score_recent_bonus=float(score.get("recent_bonus", 0.1)),
        )


class CriteriaEngine:
    """Loads criteria from YAML and evaluates candidates (pure, spec §22)."""

    def __init__(self, criteria: Optional[RecommendationCriteria] = None,
                 config_path: Optional[Path] = None):
        self.criteria = criteria if criteria is not None else self._load(config_path)

    # ------------------------------------------------------------- loading
    @staticmethod
    def _load(config_path: Optional[Path]) -> RecommendationCriteria:
        path = Path(config_path or DEFAULT_CONFIG_PATH)
        if not yaml:
            raise RuntimeError("PyYAML is not installed (add 'PyYAML' to requirements.txt)")
        if not path.exists():
            raise FileNotFoundError(f"Recommendation criteria file not found: {path}")
        raw = yaml.safe_load(path.read_text()) or {}
        return RecommendationCriteria.from_dict(raw)

    def load_from_dict(self, raw: dict) -> None:
        """Replace criteria from an in-memory dict (tests / config injection)."""
        self.criteria = RecommendationCriteria.from_dict(raw)

    # ------------------------------------------------------------ evaluate
    def evaluate(self, cand: RecommendationCandidate) -> CriteriaResult:
        """Run the candidate through criteria; return passed + score + reasons.

        Mirrors the old hardcoded gates (film imdb≥7.5 / rt≥80, series imdb≥8.0 /
        rt≥85) but sourced from config. Library/watchlist/history exclusions are
        separate pipeline steps in the manager — criteria only scores quality.
        """
        reasons: list[str] = []
        mc = self.criteria.for_type(cand.media_type)

        # 1. TMDB rating gate — enforced only when the score is known (>0).
        #    tmdb_score == 0 means "unknown" (legacy candidates carry no TMDB
        #    rating), so it neither passes nor fails on that gate.
        if cand.tmdb_score > 0:
            if cand.tmdb_score >= mc.min_tmdb_rating:
                reasons.append(f"TMDB rating {cand.tmdb_score:.1f} >= {mc.min_tmdb_rating:.1f}")
            else:
                reasons.append(f"TMDB rating {cand.tmdb_score:.1f} < {mc.min_tmdb_rating:.1f}")

        # 2. Vote count gate (only enforced when known).
        if cand.vote_count > 0:
            if cand.vote_count >= mc.min_vote_count:
                reasons.append(f"Vote count {cand.vote_count:,} >= {mc.min_vote_count:,}")
            else:
                reasons.append(f"Vote count {cand.vote_count:,} < {mc.min_vote_count:,}")

        # 3. Year gate (only when years configured).
        if mc.years:
            if cand.year is not None and cand.year in mc.years:
                reasons.append(f"Year {cand.year} in allowed years")
            else:
                reasons.append(f"Year {cand.year or 'unknown'} not in allowed years")

        # 4. Genre include (any one of the include list).
        cg = [g.strip().lower() for g in cand.genres]
        if mc.genres_include:
            hit = set(cg) & set(mc.genres_include)
            if hit:
                reasons.append(f"Genre matches {', '.join(sorted(hit))}")
            else:
                reasons.append(f"No genre in {', '.join(mc.genres_include)} ({', '.join(cg) or 'none'})")

        # 5. Genre exclude (hard fail on any).
        excl = set(cg) & set(mc.genres_exclude)
        if excl:
            reasons.append(f"Excluded genre {', '.join(sorted(excl))}")

        # 6. IMDb / RT anchor (mirrors old gates; rt_any = either suffices).
        imdb_ok = mc.min_imdb > 0 and cand.imdb >= mc.min_imdb
        rt_ok = mc.min_rt > 0 and cand.rt >= mc.min_rt
        if mc.min_imdb > 0 or mc.min_rt > 0:
            if mc.rt_any:
                if imdb_ok or rt_ok:
                    reasons.append(f"IMDb {cand.imdb:.1f} or RT {cand.rt}% passes quality anchor")
                else:
                    reasons.append(f"IMDb {cand.imdb:.1f} < {mc.min_imdb:.1f} and RT {cand.rt}% < {mc.min_rt}%")
            else:
                if imdb_ok:
                    reasons.append(f"IMDb {cand.imdb:.1f} >= {mc.min_imdb:.1f}")
                if rt_ok:
                    reasons.append(f"RT {cand.rt}% >= {mc.min_rt}%")

        # Aggregate pass = all enforced gates non-negative.
        passed = True
        if cand.tmdb_score > 0 and cand.tmdb_score < mc.min_tmdb_rating:
            passed = False
        if cand.vote_count > 0 and cand.vote_count < mc.min_vote_count:
            passed = False
        if mc.years and (cand.year is None or cand.year not in mc.years):
            passed = False
        if mc.genres_include and not (set(cg) & set(mc.genres_include)):
            passed = False
        if excl:
            passed = False
        # IMDb/RT anchor: when configured it is a real gate. rt_any -> either
        # passes; otherwise BOTH must pass. Mirrors the old hardcoded gates.
        if mc.min_imdb > 0 or mc.min_rt > 0:
            if mc.rt_any:
                if not (imdb_ok or rt_ok):
                    passed = False
            else:
                if not (imdb_ok and rt_ok):
                    passed = False

        score = self._score(cand, mc, passed)
        return CriteriaResult(passed=passed, score=round(score, 1), reasons=reasons)

    # -------------------------------------------------------------- score
    def _score(self, cand: RecommendationCandidate, mc: _MediaCriteria, passed: bool) -> float:
        """0-100 quality score combining TMDB, IMDb, recency (config weights)."""
        c = self.criteria
        base = 0.0
        tmdb_n = min(cand.tmdb_score, 10.0) / 10.0
        imdb_n = min(cand.imdb, 10.0) / 10.0 if cand.imdb else 0.0
        base += tmdb_n * c.score_tmdb_weight
        base += imdb_n * c.score_imdb_weight
        # Recent bonus: newer titles within ~6 years get a small nudge.
        if cand.year:
            age = 2026 - cand.year
            if 0 <= age <= 6:
                base += (1 - age / 6.0) * c.score_recent_bonus
        weighted = base / (c.score_tmdb_weight + c.score_imdb_weight + c.score_recent_bonus)
        score = weighted * 100.0 * mc.score_weight
        if not passed:
            score = min(score, 49.9)  # failing candidates cap below 50
        return score