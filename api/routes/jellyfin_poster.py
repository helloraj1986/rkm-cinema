"""Jellyfin poster proxy endpoint — serves artwork without leaking the token."""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response
from config.settings import get_config
from services.library.factory import build_library_service

router = APIRouter()


@router.get("/jellyfin/poster")
def jellyfin_poster(id: str = Query(default=""), width: int = Query(default=500, ge=16, le=2000)):
    """Proxy a Jellyfin item's primary image so the browser can render it.

    Keeps the Jellyfin token/credential server-side: the browser only ever hits
    this same-origin /api route. Phase 1: routed through the ``LibraryService``
    ``get_poster`` capability (first provider able to serve it wins).
    """
    return _proxy_image(id, width, "Primary")


@router.get("/jellyfin/person")
def jellyfin_person(id: str = Query(default=""), width: int = Query(default=300, ge=16, le=2000)):
    """Proxy a Jellyfin person's headshot (``People.Id`` → Primary image).

    Live-verified on Jellyfin 10.11.11: person images live at the same
    ``/Items/{id}/Images/Primary`` shape as items, so this is the existing
    poster proxy with a ``person`` semantic — lets the cast row render lazy
    headshots without leaking the token. People with no headshot 404 (the
    detail payload's ``has_image`` flag lets the UI skip those requests).
    """
    return _proxy_image(id, width, "Primary")


@router.get("/jellyfin/backdrop")
def jellyfin_backdrop(id: str = Query(default=""), width: int = Query(default=1600, ge=16, le=4000)):
    """Proxy a Jellyfin item's 16:9 backdrop (keyart) for rich player backdrops."""
    return _proxy_image(id, width, "Backdrop")


def _proxy_image(id: str, width: int, kind: str):
    """Shared artwork proxy: resolve through the service and stream it back."""
    cfg = get_config()
    if not id:
        return Response(status_code=404)
    service = build_library_service(cfg)
    try:
        result = service.get_poster(id, width, kind=kind) if service is not None else None
    except Exception:
        result = None
    if not result:
        return Response(status_code=404)
    return Response(content=result["content"], media_type=result["content_type"])