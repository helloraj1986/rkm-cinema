"""Subtitle search / select / disable (SUBTITLES_OPENSUBTITLES_PLAN §3.5, Phase 3).

Additive only (ADR-0001): three new paths, and ONE new field on the existing
``playback-info`` response so the player needs no extra round trip to apply the user's
choice on load.

Division of labour, deliberately:

* the **api** owns the OpenSubtitles credential and the store; nothing about either
  reaches the browser (criterion 11);
* a vendor failure degrades THIS route only — local embedded/on-disk subtitles keep
  working and playback is never blocked (criterion 10), so a search error is reported
  as a ``warning`` in a 200 payload rather than failing the request. Only an ACTION the
  user explicitly asked for (select) can fail the request.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.models import SubtitleDisableRequest, SubtitleSelectRequest
from config.settings import get_config
from services.library.factory import build_library_service
from services.opensubtitles import (AuthFailedError, NotConfiguredError, NoResultsError,
                                    OpenSubtitlesError, QuotaExhaustedError,
                                    RateLimitedError, TransportError,
                                    UnsupportedFormatError, build_opensubtitles_client)
from services.subtitle_store import SubtitleStore
from services.subtitles import SubtitleService, merge_subtitle_rows, search_keywords

router = APIRouter()
logger = logging.getLogger("rkm.api.subtitles")


def _http_for(exc: OpenSubtitlesError) -> HTTPException:
    """Map the client's error taxonomy onto honest status codes.

    Each of these is a state the USER can act on, so none of them may surface as a
    500: not configured (503), credentials rejected (502), throttled vs out of daily
    downloads (429, the latter with the reset time in the message), nothing usable
    found (400), upstream/network (502).
    """
    if isinstance(exc, NotConfiguredError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, AuthFailedError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, QuotaExhaustedError):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, RateLimitedError):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return HTTPException(status_code=429, detail=str(exc), headers=headers)
    if isinstance(exc, (NoResultsError, UnsupportedFormatError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, TransportError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/jellyfin/subtitle-search")
def subtitle_search(
    id: str = Query(default="", description="Jellyfin item id (movie or episode)"),
    language: str = Query(default="", description="ISO code; blank = the configured default"),
    limit: int = Query(default=30, ge=1, le=100),
):
    """Every subtitle choice for an item: its LOCAL tracks, then OpenSubtitles results.

    Local tracks are always returned and never altered (criterion 9). Each row carries
    our own usage count and ``active`` so the panel can mark the user's choice without a
    second call; remote rows are ranked by our usage first, then the provider's
    popularity (criterion 8).
    """
    cfg = get_config()
    if not id:
        raise HTTPException(status_code=404, detail="Missing item id")
    library = build_library_service(cfg)
    service = SubtitleService(library=library, config=cfg)
    store = SubtitleStore(config=cfg)

    tracks = service.local_tracks(id)
    stored = store.preference(id) or {}
    preferred = store.preferred_subtitle(id, tracks)
    counts = store.usage_counts()
    # Per-row "last used" so the panel can show recency, not just a count.
    usage_rows = (store.load().get("usage") or {})
    last_used = {str(row.get("subtitle_id") or f"os:{key}"): str(row.get("last_used") or "")
                 for key, row in usage_rows.items() if isinstance(row, dict)}

    enabled = bool(cfg.has_opensubtitles())
    remote, warning, remaining = [], "", None
    language = (language or "").strip().lower() or (cfg.opensubtitles_languages() or ["en"])[0]
    if enabled:
        keywords = search_keywords(library.subtitle_search_context(id) or {})
        if keywords:
            try:
                client = build_opensubtitles_client(cfg)
                remote = client.search(languages=[language], limit=limit, **keywords)
                remaining = client.last_quota()
                del client
            except OpenSubtitlesError as exc:
                # Degrade, never break: the local tracks are still a complete answer.
                logger.info("subtitle search degraded for %s: %s", id, exc)
                warning = str(exc)
            except Exception:  # a PASSIVE listing must never 500 (Phase 5 hardening)
                # An UNEXPECTED failure — a vendor payload shape change, a parser bug —
                # must still not take the picker down: the item's own tracks are already
                # a complete answer, and the player must keep working. Logged with a
                # traceback so it is visible, reported as a warning so the user knows why
                # the online list is empty instead of silently seeing nothing.
                logger.exception("subtitle search failed unexpectedly for %s", id)
                warning = "Subtitle search failed — see the api log"
        else:
            warning = "Could not determine a title to search for this item"
    else:
        warning = ("OpenSubtitles is not configured — set OPENSUBTITLES_API_KEY in .env "
                   "to search online subtitles")

    return JSONResponse({
        "item_id": id,
        "enabled": enabled,
        "language": language,
        "languages": cfg.opensubtitles_languages(),
        "results": merge_subtitle_rows(tracks, remote, counts=counts,
                                       active_index=(preferred or {}).get("index"),
                                       active_subtitle_id=(preferred or {}).get("subtitle_id"),
                                       last_used=last_used),
        "local_count": len(tracks),
        "remote_count": len(remote),
        "preferred_subtitle": preferred,
        "disabled": bool(stored.get("disabled")),
        "remaining_downloads": remaining,
        "warning": warning,
    })


@router.post("/jellyfin/subtitle-select")
def subtitle_select(payload: SubtitleSelectRequest):
    """Download, attach and REMEMBER a subtitle, then return the refreshed tracks.

    One call does the whole user action: fetch the bytes, write them beside the media
    (or upload them), refresh the item, persist the choice and increment its usage
    count. A repeat selection of something already attached is a no-op download-wise
    (the delivery layer reuses it), so the usage count reflects deliberate choices.
    """
    cfg = get_config()
    item_id = (payload.item_id or "").strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    if not payload.file_id:
        raise HTTPException(status_code=400, detail="file_id is required")
    language = (payload.language or "").strip().lower() or \
        (cfg.opensubtitles_languages() or ["en"])[0]

    # Construct the client HERE and inject it: the route is the single place that owns
    # the OpenSubtitles credential wiring, which also keeps the delivery layer free of
    # any notion of how a client is built (and lets a test inject a fake one).
    service = SubtitleService(client=build_opensubtitles_client(cfg),
                              library=build_library_service(cfg), config=cfg)
    try:
        result = service.attach(item_id=item_id, file_id=int(payload.file_id),
                                language=language, display_title=payload.display_title or "")
    except OpenSubtitlesError as exc:
        logger.info("subtitle select failed for %s: %s", item_id, exc)
        raise _http_for(exc)

    store = SubtitleStore(config=cfg)
    store.set_preference(item_id, subtitle_id=result.subtitle_id, language=result.language,
                         provider="opensubtitles", display_title=result.display_title)
    used = store.record_use(item_id, subtitle_id=result.subtitle_id,
                            language=result.language, display_title=result.display_title)
    return JSONResponse({
        "ok": True,
        "delivered": result.delivered,
        "reused": result.reused,
        "subtitles": result.tracks,
        "used_count": used,
        "remaining_downloads": result.remaining,
        "preferred_subtitle": store.preferred_subtitle(item_id, result.tracks),
    })


@router.post("/jellyfin/subtitle-disable")
def subtitle_disable(payload: SubtitleDisableRequest):
    """Turn subtitles off for an item, KEEPING the choice (re-enable is one tap)."""
    cfg = get_config()
    item_id = (payload.item_id or "").strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    store = SubtitleStore(config=cfg)
    store.disable(item_id)
    return JSONResponse({"ok": True, "disabled": True, "preferred_subtitle": None})
