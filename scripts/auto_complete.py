#!/usr/bin/env python3
"""Auto-complete script: move pending → recommended when downloaded + in Plex.

Checks each pending entry:
- Radarr hasFile (movie) OR Sonarr has episode files (series)
- Plex has the title (ground truth)
If both true, move to recommended with completed date.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, "/workspace/media/watchlist")

from config.settings import get_config
from core.logging import setup_logging
from services import RadarrService, SonarrService, PlexService, WatchlistService

setup_logging(level="INFO", json_format=True)
logger = logging.getLogger("rkm.auto_complete")


def run_auto_complete(dry_run: bool = False) -> dict:
    """
    Check pending entries and auto-complete those that are available in Plex.

    Returns:
        Dict with completed entries and any errors.
    """
    logger.info("Starting auto-complete run (dry_run=%s)", dry_run)

    cfg = get_config()
    missing = cfg.validate_required()
    if missing:
        logger.error("Missing required config: %s", missing)
        return {"success": False, "error": f"Missing config: {missing}"}

    wl = WatchlistService()
    data = wl.load()

    if not data.pending:
        logger.info("No pending entries to check")
        return {"success": True, "completed": [], "checked": 0}

    radarr = RadarrService() if cfg.RADARR_API_KEY else None
    sonarr = SonarrService() if cfg.SONARR_API_KEY else None
    plex = PlexService() if cfg.PLEX_URL and cfg.PLEX_TOKEN else None

    if not plex:
        logger.error("Plex not configured - cannot verify ownership")
        return {"success": False, "error": "Plex not configured"}

    completed = []
    errors = []
    checked = 0

    for entry in data.pending:
        checked += 1
        imdb_id = entry.imdbId
        title = entry.title
        year = entry.year
        is_series = entry.isSeries
        tmdb_id = entry.tmdbId

        try:
            # Check Radarr/Sonarr for file
            has_file = False
            if is_series:
                if sonarr:
                    tvdb_id = sonarr.resolve_tvdb_id(imdb_id)
                    if tvdb_id:
                        has_file = sonarr.has_episodes(tvdb_id)
            else:
                if radarr and tmdb_id:
                    has_file = radarr.has_file(tmdb_id)

            if not has_file:
                logger.debug("%s: No file in *arr yet", title)
                continue

            # Check Plex (ground truth)
            in_plex = plex.has_media(title, year, is_series)
            if not in_plex:
                logger.debug("%s: File in *arr but not yet in Plex", title)
                continue

            # Both conditions met - auto-complete
            completed_date = datetime.now().date().isoformat()
            logger.info("AUTO-COMPLETE: %s (%d) -> recommended (completed: %s)", title, year, completed_date)

            if not dry_run:
                success = wl.move_to_recommended(imdb_id, completed_date)
                if success:
                    completed.append({
                        "title": title,
                        "year": year,
                        "imdbId": imdb_id,
                        "completed": completed_date,
                        "type": "tv" if is_series else "movie",
                    })
                else:
                    errors.append({"title": title, "error": "move_to_recommended returned False"})
            else:
                completed.append({
                    "title": title,
                    "year": year,
                    "imdbId": imdb_id,
                    "completed": completed_date,
                    "type": "tv" if is_series else "movie",
                    "dry_run": True,
                })

        except Exception as e:
            logger.error("Error checking %s: %s", title, e)
            errors.append({"title": title, "error": str(e)})

    # Rebuild dashboard if changes made
    if completed and not dry_run:
        try:
            import subprocess
            rebuild_result = subprocess.run(
                ["python3", "/workspace/media/watchlist/scripts/rebuild_dashboard.py"],
                capture_output=True, text=True, timeout=120, cwd="/workspace/media/watchlist"
            )
            if rebuild_result.returncode != 0:
                logger.error("Dashboard rebuild failed: %s", rebuild_result.stderr)
                errors.append({"step": "rebuild_dashboard", "error": rebuild_result.stderr})
            else:
                logger.info("Dashboard rebuilt after auto-complete")
        except Exception as e:
            logger.error("Dashboard rebuild exception: %s", e)
            errors.append({"step": "rebuild_dashboard", "error": str(e)})

    result = {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "checked": checked,
        "completed": completed,
        "errors": errors,
        "dry_run": dry_run,
    }

    logger.info("Auto-complete complete: checked=%d, completed=%d, errors=%d",
               checked, len(completed), len(errors))
    return result


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="RKM Watchlist Auto-Complete")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't modify watchlist")
    args = parser.parse_args()

    results = run_auto_complete(dry_run=args.dry_run)

    # Output results as JSON for cron logging
    print(json.dumps(results, indent=2))

    # Exit code
    sys.exit(1 if results["errors"] else 0)


if __name__ == "__main__":
    main()