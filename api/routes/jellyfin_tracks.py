"""Jellyfin playback-track routing — audio/subtitle enumeration + subtitle proxy.

Mirrors ``jellyfin_poster.py`` / ``jellyfin_stream.py``: the Jellyfin credential
stays server-side. Two narrow, same-origin endpoints the player slice hangs off:

- ``GET /api/jellyfin/playback-info?id=`` — driven by the ``LibraryService``
  ``playback_info`` capability (first provider able to answer wins); returns the
  audio + **text** subtitle tracks so the player can render track pickers.
- ``GET /api/jellyfin/subtitle?id=&ms=&index=`` — proxies a text subtitle stream
  (converted to WebVTT) so the browser's native ``<track>`` can display it.
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from config.settings import get_config
from services.library.factory import build_library_service

router = APIRouter()
logger = logging.getLogger("rkm.api.jellyfin_tracks")


def _require_jellyfin(cfg):
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        raise HTTPException(status_code=503, detail="Jellyfin not configured")
    return cfg


@router.get("/jellyfin/playback-info")
def jellyfin_playback_info(id: str = Query(default="")):
    """List an item's audio + text-subtitle tracks for the player track pickers."""
    cfg = get_config()
    if not id:
        raise HTTPException(status_code=404, detail="Missing item id")
    service = build_library_service(cfg)
    try:
        info = service.playback_info(id) if service is not None else None
    except Exception as e:  # noqa: BLE001 - a provider failure is a soft miss
        logger.warning("jellyfin playback-info(%s) failed: %s", id, e)
        info = None
    if not info:
        raise HTTPException(status_code=404, detail="No playback info")
    return JSONResponse(info)


@router.get("/jellyfin/subtitle")
def jellyfin_subtitle(
    id: str = Query(default=""),
    ms: str = Query(default="", description="MediaSourceId (defaults to the item id)"),
    index: int = Query(default=0),
):
    """Proxy a Jellyfin **text** subtitle stream as WebVTT for the browser.

    ``index`` is the subtitle stream's ``MediaStream.Index`` from playback-info.
    The ``ms``/media source falls back to the item id (single-source items), so
    ``/api/jellyfin/subtitle?id=<item>&ms=<source>&index=<n>`` just works.
    """
    cfg = _require_jellyfin(get_config())
    if not id:
        raise HTTPException(status_code=404, detail="Missing item id")
    source = ms or id
    up = (f"{cfg.JELLYFIN_URL}/Videos/{id}/{source}/Subtitles/{index}/Stream"
          f"?api_key={cfg.JELLYFIN_API_KEY}&format=vtt")
    try:
        resp = urllib.request.urlopen(up, timeout=12)
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=e.code, detail=e.reason or "Jellyfin subtitle error")  # noqa: BLE001
    except Exception as e:  # noqa: BLE001 - transport failure
        logger.warning("jellyfin subtitle(%s/%s) failed: %s", id, index, e)
        raise HTTPException(status_code=502, detail="Jellyfin subtitle unavailable")

    media_type = resp.headers.get("Content-Type", "text/vtt") or "text/vtt"
    if "text" not in media_type:
        media_type = "text/vtt"
    return StreamingResponse(_iter_body(resp), media_type=media_type, headers={
        "Cache-Control": "no-store",
    })


def _iter_body(resp):
    """Stream the upstream subtitle body in bounded chunks, closing on exit."""
    try:
        while True:
            block = resp.read(65536)
            if not block:
                break
            yield block
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001 - best-effort close on abort
            pass