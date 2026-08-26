"""Health check endpoint (spec §28 Phase 14).

Thin route: delegates to the canonical HealthChecker, which reports each
external service independently. Returns the BC ``services`` bool map PLUS
structured ``serviceDetail`` and a ``degraded`` flag — one down provider never
fails the whole response.
"""
from fastapi import APIRouter
from api.models import HealthResponse
from config.settings import get_config
from services.health import HealthChecker
from services.watchlist import WatchlistService
from core.logging import log_event
import logging

logger = logging.getLogger("rkm.api.health")

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Service health (per-service, structured) and watchlist freshness."""
    log_event(logger, "health.check.start")
    cfg = get_config()

    report = HealthChecker(config=cfg).check()

    # Watchlist freshness (metadata only; never fatal).
    try:
        wl = WatchlistService()
        data = wl.load()
        title_count = len(data.pending) + len(data.recommended)
        updated = data.updated
    except Exception:
        title_count = 0
        updated = ""
        log_event(logger, "health.check.watchlist.error", error="failed to load watchlist")

    log_event(logger, "health.check.completed", 
              ok=True, 
              updated=updated, 
              titleCount=title_count, 
              degraded=report.degraded, 
              services=report.services)
    return HealthResponse(
        ok=True,
        updated=updated,
        titleCount=title_count,
        services=report.services,
        degraded=report.degraded,
        serviceDetail=report.serviceDetail,
    )