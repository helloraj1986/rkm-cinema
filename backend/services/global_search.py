"""Pure helpers for the global-search endpoint (GLOBAL_SEARCH_PLAN Phases 1–2).

Ownership scoring, TMDB-discovery dedupe, and per-row state (watch / resume /
watch_again / next_episode) are pure so the route stays thin and the rules are
unit-tested. All functions operate on the normalized provider rows produced by
``JellyfinLibraryProvider.search_items``/``episodes``.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

_NON_WORD = re.compile(r"[^0-9A-Za-z]+")
_SPACES = re.compile(r"\s+")


def normalize_title(raw: Any) -> str:
    """Case/punctuation-insensitive title key ("3 Body Problem:" -> "3 body problem")."""
    s = _NON_WORD.sub(" ", str(raw or "")).strip().lower()
    return _SPACES.sub(" ", s)


def title_match_score(query: str, title: Any, *, query_year: Optional[int] = None,
                      title_year: Optional[Any] = None) -> int:
    """How strongly an owned title answers the query (0 = no match).

    3 = exact normalized title · 2 = containment (len>=3) with compatible year
    or no year either side · 1 = every significant token contained (len>=5).
    Years must agree when both are known so same-name remakes stay distinct.
    """
    q = normalize_title(query)
    t = normalize_title(title)
    if not q or not t:
        return 0
    try:
        y1 = int(query_year) if query_year is not None else None
        y2 = int(title_year) if title_year is not None else None
    except (TypeError, ValueError):
        y1, y2 = None, None
    # Same-name remakes of a different year are DISTINCT titles, never a match.
    if y1 is not None and y2 is not None and y1 != y2:
        return 0
    if q == t:
        return 3
    if len(q) >= 3 and (q in t or t in q):
        return 2
    words = q.split()
    if len(q) >= 5 and all(w in t for w in words):
        return 1
    return 0


def owned_strong_match(owned: Iterable[dict], query: str, *, query_year: Optional[int] = None) -> int:
    """Best ``title_match_score`` across owned rows (drives the library-first gate)."""
    best = 0
    for row in owned or []:
        best = max(best, title_match_score(query, row.get("title", ""), query_year=query_year,
                                           title_year=row.get("year")))
    return best


def is_duplicate_discovery(candidate: dict, owned: Iterable[dict]) -> bool:
    """True when a TMDB candidate is already owned (drop it from DISCOVER).

    Matches by TMDB provider id first, then by exact/containment title with
    year compatibility — same-name remakes of a different year stay distinct.
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
        if score >= 2:
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
