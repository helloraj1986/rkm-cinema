#!/usr/bin/env python3
"""Cron driver: auto-add TMDB-discovered movies/shows to the RKM watchlist.

Wires the refactored recommendation pipeline with Plex as the source-of-truth
ownership gate (spec §1.2) so already-owned titles are never re-added, runs the
idempotent DailyWatchlistJob, rebuilds the dashboard, and prints a summary of
exactly what was added for Hermes cron to deliver.

Idempotent (spec §24): re-running never duplicates — the manager's
library/watchlist/history gates hold.

Usage:
    python3 scripts/add_watchlist_cron.py [--count N] [--dry-run]

Exit code 0 on success (even if nothing was added), nonzero on hard failure.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_pending_ids() -> set:
    """Set of canonical tmdb ids currently pending (for the before/after diff)."""
    from services.watchlist import WatchlistService
    wl = WatchlistService()
    return {int(e.tmdbId) for e in wl.load().pending if e.tmdbId}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20,
                        help="candidates to fetch per media type (default 20)")
    parser.add_argument("--dry-run", action="store_true",
                        help="score/dedupe but do NOT write to the watchlist")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger("rkm.cron.add_watchlist")

    from config.settings import get_config
    from services.library import LibraryService, PlexLibraryProvider
    from services.recommendation import RecommendationManager
    from jobs.daily_watchlist import DailyWatchlistJob

    cfg = get_config()

    # The configured library backend is the authority for ownership. Wire it
    # into the manager explicitly so already-owned titles are excluded BEFORE
    # any write (the manager's default has no library gate). Uses the factory
    # so a "jellyfin" MEDIA_SERVER works exactly like Plex here.
    from services.library import build_library_service
    library = build_library_service(cfg)
    if library is None:
        print("ERROR: library backend not configured (set MEDIA_SERVER + its URL/key)")
        return 1

    manager = RecommendationManager(config=cfg, library=library)
    job = DailyWatchlistJob(manager=manager, config=cfg, count=args.count)

    if args.dry_run:
        result = manager.run(count=args.count, persist_recommendations=False)
        print(_render(
            preview=True,
            candidates=getattr(result, "candidates", 0),
            passed=getattr(result, "passed_criteria", 0),
            owned=getattr(result, "already_in_library", 0),
            wl_dup=getattr(result, "watchlist_duplicates", 0),
            already=getattr(result, "already_recommended", 0),
            added_count=getattr(result, "new_recommendations", 0),
            added_titles=[r.candidate.title for r in result.recommended],
            elapsed=0.0,
        ))
        return 0

    before = _load_pending_ids()
    start = time.time()
    res = job.run()
    elapsed = time.time() - start

    if res.status == "error":
        print(f"ERROR: job failed: {res.error}")
        return 1

    # Rebuild dashboard (single source of truth for the UI data file).
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "rebuild_dashboard.py")],
                       check=True, capture_output=True)
    except Exception as e:  # noqa: BLE001
        logger.error("dashboard rebuild failed: %s", e)

    # Diff pending to surface exactly what this run added (with titles).
    from services.watchlist import WatchlistService
    now = {int(e.tmdbId) for e in WatchlistService().load().pending if e.tmdbId}
    new_ids = now - before
    by_id = {}
    for e in WatchlistService().load().pending:
        if int(e.tmdbId) in new_ids:
            by_id[int(e.tmdbId)] = f"{e.title} ({e.year})"

    c = res.counts or {}
    print(_render(
        preview=False,
        candidates=c.get("candidates", 0),
        passed=c.get("passed_criteria", 0),
        owned=c.get("already_in_library", 0),
        wl_dup=c.get("watchlist_duplicates", 0),
        already=c.get("already_recommended", 0),
        added_count=len(new_ids),
        added_titles=[by_id[i] for i in sorted(by_id) if i in by_id],
        elapsed=elapsed,
    ))
    return 0


def _render(*, preview: bool, candidates: int, passed: int, owned: int,
            wl_dup: int, already: int, added_count: int,
            added_titles: list[str], elapsed: float) -> str:
    kind = "PREVIEW (dry-run — nothing written)" if preview else \
        f"DONE in {elapsed:.1f}s"
    head = f"RKM Watchlist auto-add — {kind}"
    lines = [
        head,
        "=" * len(head),
        f"candidates scanned      : {candidates}",
        f"passed quality criteria : {passed}",
        f"already in Plex (skip)  : {owned}",
        f"already on watchlist    : {wl_dup}",
        f"already recommended     : {already}",
        f"{'WOULD ADD' if preview else 'ADDED'}                    : {added_count}",
    ]
    if added_titles:
        lines.append("")
        lines.append(f"{'would add' if preview else 'added'} titles:")
        for t in added_titles:
            lines.append(f"  • {t}")
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(130)