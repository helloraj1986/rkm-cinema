"""
Add watchlist job (spec §24: recommendation generation and auto-add).
"""

from __future__ import annotations

import logging

from jobs.base import JobResult
from core.logging import log_event

logger = logging.getLogger("rkm.jobs.add_watchlist")


def run_add_watchlist(*, count: int = 20, dry_run: bool = False) -> JobResult:
    """
    Run the add watchlist cron job (records job_run).
    
    Args:
        count: Number of candidates to fetch per media type
        dry_run: If True, score/dedupe but do NOT write to watchlist
    
    Returns:
        JobResult with outcome
    """
    from pathlib import Path
    import sys
    import time
    
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    
    start_time = time.time()
    
    try:
        # Import and run the add_watchlist_cron script's main function
        from scripts.add_watchlist_cron import main
        
        # We need to simulate command line arguments
        import sys as sys_module
        original_argv = sys_module.argv
        sys_module.argv = [
            'add_watchlist_cron.py',
            f'--count={count}'
        ]
        if dry_run:
            sys_module.argv.append('--dry-run')
        
        try:
            result_code = main()
            elapsed = time.time() - start_time
            
            if result_code == 0:
                status = "success"
                error = None
            else:
                status = "error"
                error = f"Script exited with code {result_code}"
                
        finally:
            # Restore original argv
            sys_module.argv = original_argv
        
        log_event(
            logger, 
            "add_watchlist.job.complete", 
            status=status,
            count=count,
            dry_run=dry_run,
            elapsed=elapsed
        )
        
        return JobResult(
            name="add_watchlist",
            status=status,
            items_processed=count,  # Approximate
            error=error,
            counts={
                "count": count,
                "dry_run": dry_run,
                "elapsed_seconds": round(elapsed, 1)
            }
        )
        
    except Exception as e:  # noqa: BLE001
        logger.exception("add_watchlist job failed: %s", e)
        return JobResult(
            name="add_watchlist",
            status="error",
            error=str(e),
            items_processed=0,
            counts={"count": count, "dry_run": dry_run}
        )
