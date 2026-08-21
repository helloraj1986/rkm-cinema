#!/usr/bin/env python3
"""Daily recommendation orchestration script.

Single entry point for the 18:00 AEST cron job.
Performs: category rotation -> candidate selection -> quality gates -> Plex check
-> duplicate check -> trailer enrichment -> watchlist add -> dashboard rebuild.
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
from services import RecommendationService, WatchlistService
from services.watchlist import WatchlistEntry


setup_logging(level="INFO", json_format=True)
logger = logging.getLogger("rkm.daily_recommendations")


def load_candidates_from_skill(category: str) -> list[dict]:
    """
    In production, this would use TMDB discover or the weekly-media-recommendations skill.
    For now, we expect the cron job to provide candidates via the skill's logic.
    This function is a placeholder - the actual candidates come from the LLM-driven cron.
    """
    # The cron job (LLM-driven) will call this script with candidates already selected
    # and pass them via stdin or a temp file. For standalone testing, we return empty.
    return []


def run_daily_recommendations(candidates: list[dict] = None) -> dict:
    """
    Main orchestration function.

    Args:
        candidates: List of candidate dicts with keys:
            title, year, category, lang, imdb, rt, is_series, imdb_id, tmdb_id,
            director, cast, snippet, poster

    Returns:
        Dict with results: added, rejected, errors
    """
    logger.info("Starting daily recommendation run")

    cfg = get_config()
    missing = cfg.validate_required()
    if missing:
        logger.error("Missing required config: %s", missing)
        return {"success": False, "error": f"Missing config: {missing}"}

    reco = RecommendationService()
    wl = WatchlistService()

    # 1. Rotate category
    old_category = reco.get_current_category()
    new_category = reco.rotate_category()
    logger.info("Category rotated: %s -> %s", old_category, new_category)

    results = {
        "timestamp": datetime.now().isoformat(),
        "category": new_category,
        "candidates_processed": 0,
        "added": [],
        "rejected": [],
        "errors": [],
        "auto_completed": [],
    }

    # 2. Run auto-complete FIRST (move completed downloads to recommended)
    logger.info("Running auto-complete check...")
    try:
        from scripts.auto_complete import run_auto_complete
        auto_results = run_auto_complete(dry_run=False)
        if auto_results.get("success"):
            completed = auto_results.get("completed", [])
            results["auto_completed"] = completed
            logger.info("Auto-completed %d titles", len(completed))
        else:
            logger.error("Auto-complete failed: %s", auto_results.get("error"))
            results["errors"].append({"step": "auto_complete", "error": auto_results.get("error")})
    except Exception as e:
        logger.error("Auto-complete exception: %s", e)
        results["errors"].append({"step": "auto_complete", "error": str(e)})

    # 3. Process candidates (from cron skill or provided)
    if candidates is None:
        candidates = load_candidates_from_skill(new_category)

    if not candidates:
        logger.warning("No candidates provided for category %s", new_category)
        results["rejected"].append({"reason": "no_candidates", "category": new_category})
    else:
        for cand_data in candidates:
            results["candidates_processed"] += 1
            try:
                # Build Candidate object
                from services.recommendations import Candidate
                candidate = Candidate(
                    title=cand_data["title"],
                    year=cand_data["year"],
                    category=cand_data.get("category", new_category),
                    lang=cand_data.get("lang", "English"),
                    imdb=cand_data.get("imdb", 0.0),
                    rt=cand_data.get("rt", 0),
                    is_series=cand_data.get("is_series", False),
                    imdb_id=cand_data["imdb_id"],
                    tmdb_id=cand_data.get("tmdb_id", 0),
                    director=cand_data.get("director", ""),
                    cast=cand_data.get("cast", []),
                    snippet=cand_data.get("snippet", ""),
                    poster=cand_data.get("poster", ""),
                )

                # Process through pipeline
                entry = reco.process_recommendation(candidate)
                if entry:
                    results["added"].append({
                        "title": entry.title,
                        "year": entry.year,
                        "imdbId": entry.imdbId,
                        "state": entry.state,
                    })
                    logger.info("ADDED: %s (%d)", entry.title, entry.year)
                else:
                    results["rejected"].append({
                        "title": candidate.title,
                        "year": candidate.year,
                        "reason": "pipeline_rejected",
                    })
                    logger.info("REJECTED: %s (%d)", candidate.title, candidate.year)

            except Exception as e:
                logger.error("Error processing candidate %s: %s", cand_data.get("title"), e)
                results["errors"].append({
                    "title": cand_data.get("title"),
                    "error": str(e),
                })

    # 3. Rebuild dashboard
    try:
        import subprocess
        rebuild_result = subprocess.run(
            ["python3", "/workspace/media/watchlist/scripts/rebuild_dashboard.py"],
            capture_output=True, text=True, timeout=120, cwd="/workspace/media/watchlist"
        )
        if rebuild_result.returncode != 0:
            logger.error("Dashboard rebuild failed: %s", rebuild_result.stderr)
            results["errors"].append({"step": "rebuild_dashboard", "error": rebuild_result.stderr})
        else:
            logger.info("Dashboard rebuilt: %s", rebuild_result.stdout.strip())
    except Exception as e:
        logger.error("Dashboard rebuild exception: %s", e)
        results["errors"].append({"step": "rebuild_dashboard", "error": str(e)})

    logger.info("Daily recommendation run complete: added=%d, rejected=%d, errors=%d",
               len(results["added"]), len(results["rejected"]), len(results["errors"]))
    return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="RKM Watchlist Daily Recommendations")
    parser.add_argument("--candidates", help="Path to JSON file with candidates")
    parser.add_argument("--dry-run", action="store_true", help="Process but don't save")
    args = parser.parse_args()

    candidates = None
    if args.candidates:
        with open(args.candidates) as f:
            candidates = json.load(f)

    if args.dry_run:
        logger.info("DRY RUN MODE - no changes will be saved")
        # TODO: Implement dry-run by mocking WatchlistService.save

    results = run_daily_recommendations(candidates)

    # Output results as JSON for cron logging
    print(json.dumps(results, indent=2))

    # Exit code based on errors
    sys.exit(1 if results["errors"] else 0)


if __name__ == "__main__":
    main()