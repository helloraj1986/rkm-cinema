"""Jellyfin video-stream proxy — plays the bundled library INSIDE the RKM app.

Mirrors ``jellyfin_poster.py``: keeps the Jellyfin credential server-side and
serves a same-origin ``/api`` URL the browser can hand straight to a native
``<video>`` element. Uses Jellyfin **direct play** (``Static=true``) so HTTP
Range / seeking stay intact and no server-side transcoding is needed for the
bundled H.264/AAC MP4 library.

Range requests are forwarded verbatim upstream and the upstream's status plus
``Content-Range`` / ``Accept-Ranges`` / ``Content-Type`` are passed through
unchanged (verified live: ``GET /Videos/{id}/stream?Static=true`` returns
``206`` + ``Content-Range: bytes 0-1023/1882377499`` for ``Range: bytes=0-1023``).
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from config.settings import get_config

router = APIRouter()
logger = logging.getLogger("rkm.api.jellyfin_stream")

_CHUNK = 65536

# Header names we pass through from the upstream stream response. Content-Length
# is intentionally NOT forwarded — the browser streams via chunked transfer
# encoding and relies on Content-Range + Accept-Ranges for seeking instead.
_PASSTHROUGH = ("Content-Type", "Accept-Ranges", "Content-Range")


def _iter_chunks(resp):
    """Read the upstream response body in bounded chunks, closing on exit."""
    try:
        while True:
            block = resp.read(_CHUNK)
            if not block:
                break
            yield block
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001 - best-effort close on abort
            pass


@router.get("/jellyfin/stream/{item_id}")
def jellyfin_stream(item_id: str, request: Request):
    """Proxy one Jellyfin item's video to the browser for in-app playback.

    Forwarded headers: the client's ``Range`` (so seeking works). Returned:
    the upstream status (``206`` for a range, ``200`` for full) plus the
    ``Content-Type`` / ``Accept-Ranges`` / ``Content-Range`` pass-throughs.
    """
    cfg = get_config()
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        raise HTTPException(status_code=503, detail="Jellyfin not configured")
    if not item_id:
        raise HTTPException(status_code=404, detail="Missing item id")

    up = f"{cfg.JELLYFIN_URL}/Videos/{item_id}/stream?api_key={cfg.JELLYFIN_API_KEY}&Static=true"
    headers: dict[str, str] = {}
    rng = request.headers.get("range")
    if rng:
        headers["Range"] = rng

    req = urllib.request.Request(up, headers=headers, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        # Upstream responded with an error status (e.g. 404/403) — surface it.
        raise HTTPException(status_code=e.code, detail=e.reason or "Jellyfin stream error")
    except Exception as e:  # noqa: BLE001 - transport failure
        logger.warning("jellyfin stream(%s) upstream failed: %s", item_id, e)
        raise HTTPException(status_code=502, detail="Jellyfin stream unavailable")

    status = int(getattr(resp, "status", 200))
    out_headers = {h: resp.headers.get(h) for h in _PASSTHROUGH if resp.headers.get(h)}
    return StreamingResponse(_iter_chunks(resp), status_code=status, headers=out_headers)