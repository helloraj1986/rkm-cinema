"""Jellyfin video-stream proxy — plays the bundled library INSIDE the RKM app.

Mirrors ``jellyfin_poster.py``: keeps the Jellyfin credential server-side and
serves a same-origin ``/api`` URL the browser can hand straight to a native
``<video>`` element. The default route is Jellyfin **direct play**
(``Static=true``) so HTTP Range / seeking stay intact; non-direct **modes**
(remux / transcode_audio / transcode) re-container or re-encode on Jellyfin's
side for containers/codecs the browser can't handle.

Range requests are forwarded verbatim upstream and the upstream's status plus
``Content-Range`` / ``Accept-Ranges`` / ``Content-Type`` are passed through
unchanged (verified live: ``GET /Videos/{id}/stream?Static=true`` returns
``206`` + ``Content-Range`` for a range request; remux/transcode return
chunked ``200`` MP4 whose ``ftyp`` header arrives first — duration resolves
instantly, and seeking those modes is done by restarting at ``StartTimeTicks``).
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

#: Stream routing modes (honest — verified live, see module docstring).
_VALID_MODES = ("direct", "remux", "transcode_audio", "transcode")


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
    max_bitrate: int = Query(default=0, ge=0, description="MaxStreamingBitrate (bps) — applied on the transcode modes; 0 = original"),
    transcode_audio: bool = Query(default=False, description="Legacy alias for mode=transcode_audio (video copied, audio → AAC)"),
    mode: str = Query(default="direct", description="direct (Static file, HTTP-range seekable) | remux (copy/copy → mp4) | transcode_audio (video copy + AAC) | transcode (H.264 + AAC, honours max_bitrate)"),
    start_time_ticks: int = Query(default=0, ge=0, description="Start the stream at this item offset (restart-seek for non-direct modes); seconds × 1e7"),
):
    """Proxy one Jellyfin item's video to the browser for in-app playback.

    Forwarded headers: the client's ``Range`` (so direct-play seeking works).
    Returned: the upstream status (``206`` for a range, ``200`` for full) plus
    the ``Content-Type`` / ``Accept-Ranges`` / ``Content-Range`` pass-throughs.

    **Routing modes** (verified live against the bundled Jellyfin):

    - ``direct`` (default) — ``Static=true`` serves the container untouched.
      HTTP-range seekable (``206``); the ideal path for browser-safe MP4.
      Jellyfin *ignores* ``AudioStreamIndex``/``MaxStreamingBitrate`` here
      (confirmed live), so those params are not forwarded — the pickers only
      take effect on a non-direct mode.
    - ``remux`` — copy/copy into an MP4 container (no re-encode). Needed when
      the container (e.g. MKV) can't be indexed up-front by the browser: the
      remuxed MP4 starts with ``ftyp``/``moov`` so duration + playback are
      correct immediately. Chunked (no byte ranges) — seek by restarting with
      ``start_time_ticks``.
    - ``transcode_audio`` — ``VideoCodec=copy`` + ``AudioCodec=aac``
      (video untouched, audio re-encoded) for EAC3/AC3/DTS/TrueHD tracks.
    - ``transcode`` — ``VideoCodec=h264`` + ``AudioCodec=aac``; honours
      ``max_bitrate``. Used when the video codec isn't browser-decodable
      (HEVC/10-bit) or the quality picker asks for a lower bitrate.

    Non-direct streams are chunked ``200`` MP4 (``ftyp`` first): seeking is done
    by restarting the stream at ``start_time_ticks``, not by byte ranges.
    """
    cfg = get_config()
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        raise HTTPException(status_code=503, detail="Jellyfin not configured")
    if not item_id:
        raise HTTPException(status_code=404, detail="Missing item id")

    # Legacy bool param maps onto the mode ladder.
    if transcode_audio and mode == "direct":
        mode = "transcode_audio"
    if mode not in _VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

    up = f"{cfg.JELLYFIN_URL}/Videos/{item_id}/stream?api_key={cfg.JELLYFIN_API_KEY}"
    if mode == "direct":
        # Static=true: Jellyfin serves the file untouched. Track/bitrate params
        # are no-ops here (verified live) — deliberately not forwarded.
        up += "&Static=true"
    else:
        up += f"&Static=false&MediaSourceId={item_id}&Container=mp4"
        if mode == "remux":
            up += "&VideoCodec=copy&AudioCodec=copy"
        elif mode == "transcode_audio":
            up += "&VideoCodec=copy&AudioCodec=aac&MaxAudioChannels=2"
        else:  # transcode
            up += "&VideoCodec=h264&AudioCodec=aac&MaxAudioChannels=2"
        if audio_stream_index > 0:
            up += f"&AudioStreamIndex={audio_stream_index}"
        if max_bitrate > 0 and mode in ("transcode_audio", "transcode"):
            up += f"&MaxStreamingBitrate={max_bitrate}"
        if start_time_ticks > 0:
            up += f"&StartTimeTicks={start_time_ticks}"
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
        "PlayMethod": payload.play_method or "DirectPlay",
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