"""Pure helpers for the global-search endpoint (GLOBAL_SEARCH_PLAN Phases 1–2).

Ownership scoring, TMDB-discovery dedupe, and per-row state (watch / resume /
watch_again / next_episode) are pure so the route stays thin and the rules are
unit-tested. All functions operate on the normalized provider rows produced by
``JellyfinLibraryProvider.search_items``/``episodes``.
"""
from __future__ import annotations

from typing import Iterable, Optional

# ⚠ The scoring primitives MOVED to ``services/search/`` (SEARCH_IMPROVEMENT_PLAN Phase 0) and are
# re-exported here so this module's public surface — which the route and the tests both import — is
# unchanged. Relevance logic lives in ONE place; this file keeps only the global-search-specific rules
# (the ownership gate, discovery dedupe, and the per-row action state).
from services.search.normalize import normalize_title  # noqa: F401  (re-export)
from services.search.scoring import (  # noqa: F401  (re-export)
    EXACT_TITLE_SCORE,
    best_relevance,
    owned_strong_match,
    score_item,
    title_match_score,
)


def is_duplicate_discovery(candidate: dict, owned: Iterable[dict]) -> bool:
    """True when a TMDB candidate is already owned (drop it from DISCOVER).

    Matches by TMDB provider id first — the strongest identity signal, always decisive — then by
    title. ⚠ The title path needs ``EXACT_TITLE_SCORE``, not containment: an owned "Sholay —
    Special Ops" would otherwise swallow the real "Sholay" (1975), and it does so **whenever the
    owned row carries no year**, because the remake guard below cannot fire without two years
    (measured 2026-09-13: dropped_as_duplicate=True for exactly that pair). Same-name remakes of a
    different year remain distinct on both paths.
    """
    cand_tmdb = candidate.get("tmdb_id")
    for row in owned or []:
        pids = row.get("provider_ids") or {}
        if cand_tmdb is not None:
            try:
                if int(pids.get("tmdb") or 0) == int(cand_tmdb):
                    return True
            except (TypeError, ValueError):
                pass
        score = title_match_score(candidate.get("title", ""), row.get("title", ""),
                                  query_year=candidate.get("year"), title_year=row.get("year"))
        if score >= EXACT_TITLE_SCORE:
            return True
    return False


def next_episode_facts(episodes: Iterable[dict]) -> Optional[dict]:
    """The episode a series "Continue/Play" should target.

    Prefers an in-progress episode (resume), else the first unwatched; returns
    ``None`` when every episode is watched. Episodes are expected ordered by
    (season, episode) with id/name/season/episode/played/playback_position.
    """
    resume = None
    nxt = None
    for ep in episodes or []:
        if ep.get("played"):
            continue
        if resume is None and (ep.get("playback_position") or 0) > 0:
            resume = ep
        if nxt is None:
            nxt = ep
    target = resume or nxt
    if not target:
        return None
    return {
        "id": str(target.get("id", "")),
        "name": str(target.get("name", "")),
        "season": int(target.get("season") or 0),
        "episode": int(target.get("episode") or 0),
        "position": int(target.get("playback_position") or 0),
        "remaining": max(0, int(target.get("runtime") or 0) - int(target.get("playback_position") or 0)),
        "kind": "continue" if resume is not None else "play",
    }


def owned_state(row: dict, next_ep: Optional[dict] = None) -> str:
    """Primary-action state for an owned row: watch / resume / watch_again /
    next_episode (series with a resume/next episode target)."""
    if row.get("kind") == "show":
        if next_ep is not None:
            return "next_episode"
        if row.get("played"):
            return "watch_again"
        if (row.get("playback_position") or 0) > 0:
            return "resume"
        return "watch"
    if row.get("played"):
        return "watch_again"
    if (row.get("playback_position") or 0) > 0:
        return "resume"
    return "watch"
