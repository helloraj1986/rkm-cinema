#!/usr/bin/env python3
"""Trailer enrichment script - enrich watchlist entries with TVDB/TMDB trailers."""
import json
import logging
import sys
import time
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, "/workspace/media/watchlist")

from config.settings import get_config
from core.logging import setup_logging
from services import WatchlistService, TrailerService

setup_logging(level="INFO", json_format=True)
logger = logging.getLogger("rkm.enrich_trailers")


def run_enrichment(probe: bool = False, dry_run: bool = False) -> dict:
    """
    Enrich pending entries missing trailers.

    Args:
        probe: Test API endpoints only
        dry_run: Process but don't save

    Returns:
        Dict with results.
    """
    logger.info("Starting trailer enrichment (probe=%s, dry_run=%s)", probe, dry_run)

    cfg = get_config()

    if probe:
        trailers = TrailerService()
        results = trailers.probe()
        logger.info("Probe results: %s", results)
        return {"success": True, "probe": results}

    if not cfg.TVDB_API_KEY and not cfg.TMDB_API_KEY:
        logger.warning("Neither TVDB_API_KEY nor TMDB_API_KEY configured")
        return {"success": True, "enriched": 0, "message": "No API keys configured"}

    wl = WatchlistService()
    data = wl.load()
    trailers = TrailerService()

    enriched = 0
    skipped = 0
    errors = []

    for entry in data.pending:
        if entry.trailerId and trailers.validate_trailer(entry.trailerId):
            skipped += 1
            continue

        try:
            enriched_entry = trailers.enrich_entry(entry.to_dict())
            if enriched_entry.get("trailerId") != entry.trailerId:
                # Update the entry
                entry.trailerId = enriched_entry.get("trailerId", "")
                entry.trailerTitle = enriched_entry.get("trailerTitle", "")
                enriched += 1
                logger.info("Enriched %s with trailer %s", entry.title, entry.trailerId)
            else:
                skipped += 1
        except Exception as e:
            logger.error("Failed to enrich %s: %s", entry.title, e)
            errors.append({"title": entry.title, "error": str(e)})

        time.sleep(0.3)  # Rate limiting

    if enriched > 0 and not dry_run:
        data.updated = time.strftime("%Y-%m-%dT%H:%M:%S")
        wl.save(data)
        logger.info("Watchlist saved with %d enriched entries", enriched)

        # Rebuild dashboard
        try:
            rebuild_result = subprocess.run(
                ["python3", "/workspace/media/watchlist/scripts/rebuild_dashboard.py"],
                capture_output=True, text=True, timeout=120, cwd="/workspace/media/watchlist"
            )
            if rebuild_result.returncode != 0:
                logger.error("Dashboard rebuild failed: %s", rebuild_result.stderr)
                errors.append({"step": "rebuild_dashboard", "error": rebuild_result.stderr})
            else:
                logger.info("Dashboard rebuilt: %s", rebuild_result.stdout.strip())
        except Exception as e:
            logger.error("Dashboard rebuild exception: %s", e)
            errors.append({"step": "rebuild_dashboard", "error": str(e)})

    result = {
        "success": True,
        "enriched": enriched,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
    }

    logger.info("Trailer enrichment complete: enriched=%d, skipped=%d, errors=%d",
               enriched, skipped, len(errors))
    return result


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="RKM Watchlist Trailer Enrichment")
    parser.add_argument("--probe", action="store_true", help="Test API endpoints only")
    parser.add_argument("--dry-run", action="store_true", help="Process but don't save")
    args = parser.parse_args()

    results = run_enrichment(probe=args.probe, dry_run=args.dry_run)
    print(json.dumps(results, indent=2))
    sys.exit(1 if results.get("errors") else 0)


if __name__ == "__main__":
    main()