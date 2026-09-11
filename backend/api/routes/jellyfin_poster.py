"""Jellyfin artwork proxy endpoints — serve images without leaking the token.

Caching (2026-09-10): artwork used to go out with no cache policy at all (and
nginx then stamped every ``/api/`` response ``no-store``), so the browser
re-downloaded every poster on every navigation — a 140-title folder cost ~13 MB
per visit, straight through this proxy to Jellyfin. Artwork is immutable for a
given ``(item id, kind, width)``, so it is served with a real browser cache
policy plus the upstream validators (``Last-Modified``/``ETag``), letting a
revalidating browser take a bodiless 304.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from config.settings import get_config
from services.library.factory import build_library_service

router = APIRouter()

#: Browser cache policy for artwork: a week of freshness, then background
#: revalidation (``stale-while-revalidate``) so a poster never blocks a paint
#: while it re-checks. Jellyfin itself serves images with a 1-year cache; this
#: stays shorter so changed artwork still surfaces.
ARTWORK_CACHE_CONTROL = "public, max-age=604800, stale-while-revalidate=604800"


@router.get("/jellyfin/poster")
def jellyfin_poster(
    request: Request,
    id: str = Query(default=""),
    width: int = Query(default=500, ge=16, le=2000),
):
    """Proxy a Jellyfin item's primary image so the browser can render it.

    Keeps the Jellyfin token/credential server-side: the browser only ever hits
    this same-origin /api route. Phase 1: routed through the ``LibraryService``
    ``get_poster`` capability (first provider able to serve it wins).
    """
    return _proxy_image(request, id, width, "Primary")


@router.get("/jellyfin/person")
def jellyfin_person(
    request: Request,
    id: str = Query(default=""),
    width: int = Query(default=300, ge=16, le=2000),
):
    """Proxy a Jellyfin person's headshot (``People.Id`` → Primary image).

    Live-verified on Jellyfin 10.11.11: person images live at the same
    ``/Items/{id}/Images/Primary`` shape as items, so this is the existing
    poster proxy with a ``person`` semantic — lets the cast row render lazy
    headshots without leaking the token. People with no headshot 404 (the
    detail payload's ``has_image`` flag lets the UI skip those requests).
    """
    return _proxy_image(request, id, width, "Primary")


@router.get("/jellyfin/backdrop")
def jellyfin_backdrop(
    request: Request,
    id: str = Query(default=""),
    width: int = Query(default=1600, ge=16, le=4000),
):
    """Proxy a Jellyfin item's 16:9 backdrop (keyart) for rich player backdrops."""
    return _proxy_image(request, id, width, "Backdrop")


def _proxy_image(request: Request, id: str, width: int, kind: str):
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
        # A MISSING image is never cached: the artwork may appear later (a fresh
        # scan, or Jellyfin fetching it), so the browser must be free to retry.
        return Response(status_code=404)
    return artwork_response(result, request)


def artwork_response(result: dict, request: Request) -> Response:
    """Build the artwork response: cacheable, and 304 on a matching validator.

    ``result`` is a provider payload (``content`` + ``content_type``, optionally
    ``etag``/``last_modified``) — optional on purpose, so providers that cannot
    report validators still get the cache policy.
    """
    headers = {"Cache-Control": ARTWORK_CACHE_CONTROL}
    etag = result.get("etag")
    last_modified = result.get("last_modified")
    if etag:
        headers["ETag"] = etag
    if last_modified:
        headers["Last-Modified"] = last_modified
    if _not_modified(request, etag, last_modified):
        return Response(status_code=304, headers=headers)
    return Response(content=result["content"], media_type=result["content_type"],
                    headers=headers)


def _not_modified(request: Request, etag: str | None, last_modified: str | None) -> bool:
    """True when the browser's cached copy is still current (→ 304, no bytes)."""
    if etag:
        sent = request.headers.get("if-none-match")
        if sent and _etag_matches(sent, etag):
            return True
    if last_modified:
        ims = request.headers.get("if-modified-since")
        if ims and ims.strip() == last_modified.strip():
            return True
    return False


def _etag_matches(header_value: str, etag: str) -> bool:
    """``If-None-Match`` may carry several tags, and may be weak (``W/"…"``)."""
    target = _etag_core(etag)
    return any(_etag_core(part) == target for part in header_value.split(",") if part.strip())


def _etag_core(value: str) -> str:
    return value.strip().lstrip("W/").strip('"')
