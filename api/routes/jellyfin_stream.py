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
import json
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.models import JellyfinProgressRequest
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
def jellyfin_stream(
    item_id: str,
    request: Request,
    audio_stream_index: int = Query(default=0, ge=0),
    max_bitrate: int = Query(default=0, ge=0, description="MaxStreamingBitrate (bps) for the quality picker; 0 = original"),
    transcode_audio: bool = Query(default=False, description="Transcode audio to AAC (video copied) — required for EAC3/AC3/DTS/TrueHD, which browsers can't decode"),
):
    """Proxy one Jellyfin item's video to the browser for in-app playback.

    Forwarded headers: the client's ``Range`` (so seeking works). Returned:
    the upstream status (``206`` for a range, ``200`` for full) plus the
    ``Content-Type`` / ``Accept-Ranges`` / ``Content-Range`` pass-throughs.

    **Direct play (default):** ``Static=true`` serves the container untouched —
    ideal for H.264/AAC. **Audio transcode (``transcode_audio=true``):** switches
    to Jellyfin's on-the-fly stream with ``VideoCodec=copy`` (video untouched)
    but ``AudioCodec=aac`` (audio re-encoded to browser-decodable AAC). The player
    picks this when the selected audio track is EAC3/AC3/DTS/TrueHD.

    ``audio_stream_index`` selects an embedded audio track; ``max_bitrate`` caps
    the stream. Both are omitted in the common default case.
    """
    cfg = get_config()
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        raise HTTPException(status_code=503, detail="Jellyfin not configured")
    if not item_id:
        raise HTTPException(status_code=404, detail="Missing item id")

    if transcode_audio:
        # Jellyfin progressive stream: copy video, transcode audio -> AAC 2.0.
        up = (f"{cfg.JELLYFIN_URL}/Videos/{item_id}/stream"
              f"?api_key={cfg.JELLYFIN_API_KEY}&MediaSourceId={item_id}"
              f"&VideoCodec=copy&AudioCodec=aac&MaxAudioChannels=2")
        if audio_stream_index > 0:
            up += f"&AudioStreamIndex={audio_stream_index}"
        if max_bitrate > 0:
            up += f"&MaxStreamingBitrate={max_bitrate}"
    else:
        up = (f"{cfg.JELLYFIN_URL}/Videos/{item_id}/stream"
              f"?api_key={cfg.JELLYFIN_API_KEY}&Static=true")
        if audio_stream_index > 0:
            up += f"&AudioStreamIndex={audio_stream_index}"
        if max_bitrate > 0:
            up += f"&MaxStreamingBitrate={max_bitrate}"
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


# Event -> Jellyfin Sessions endpoint. In-app playback won't move Jellyfin's
# UserData (played/resume %) unless the player reports back; these map 1:1.
_SESSION_PATHS = {
    "start": "/Sessions/Playing",
    "timeupdate": "/Sessions/Playing/Progress",
    "stopped": "/Sessions/Playing/Stopped",
}


@router.post("/jellyfin/progress")
def jellyfin_progress(payload: JellyfinProgressRequest):
    """Report playback position back to Jellyfin so Watched/resume UI updates.

    Keeps the Jellyfin credential server-side; the browser only POSTs JSON here.
    """
    cfg = get_config()
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        raise HTTPException(status_code=503, detail="Jellyfin not configured")
    if not payload.item_id:
        raise HTTPException(status_code=400, detail="Missing item_id")

    path = _SESSION_PATHS.get(payload.event)
    if not path:
        raise HTTPException(status_code=400, detail=f"Unknown event: {payload.event}")

    body: dict = {
        "ItemId": payload.item_id,
        "MediaSourceId": payload.item_id,
        "PositionTicks": int(payload.position_ticks),
        "CanSeek": True,
        "PlayMethod": "DirectPlay",
        "IsPaused": bool(payload.is_paused),
        "PlaybackRate": 1.0,
    }
    if payload.event == "timeupdate":
        body["EventName"] = "timeupdate"
    if payload.event == "start":
        body["PlaySessionId"] = f"rkm-{payload.item_id}"

    url = f"{cfg.JELLYFIN_URL}{path}?api_key={cfg.JELLYFIN_API_KEY}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=8).close()
    except urllib.error.HTTPError as e:
        logger.warning("jellyfin progress(%s/%s) -> %s", payload.event, payload.item_id, e.code)
        raise HTTPException(status_code=e.code, detail=e.reason or "Jellyfin progress error")
    except Exception as e:  # noqa: BLE001 - transport failure is a soft no
        logger.warning("jellyfin progress(%s/%s) failed: %s", payload.event, payload.item_id, e)
        raise HTTPException(status_code=502, detail="Jellyfin progress unavailable")
    return JSONResponse(status_code=204, content=None)