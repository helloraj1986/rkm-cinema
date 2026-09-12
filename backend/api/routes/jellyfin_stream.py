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
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.models import JellyfinProgressRequest
from api.session import acting_media_token
from config.settings import get_config
from services.library import build_library_service

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

    # Phase C: the profile's credential while one is selected — the proxy is the ONLY place the
    # browser's playback reaches Jellyfin, so this is where a member's stream is authorised.
    up = (f"{cfg.JELLYFIN_URL}/Videos/{item_id}/stream"
          f"?api_key={acting_media_token(cfg)}")
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
        # Jellyfin 10.11 sizes a genuine transcode's resolution/quality from
        # VideoBitRate (MaxStreamingBitrate alone is ignored — same finding as
        # the HLS route, live-verified 2026-09-08). Send the quality cap when
        # one is chosen; otherwise an unthrottled 120 Mbps cap so a full
        # re-encode (HEVC/AV1/10-bit) keeps the SOURCE resolution instead of
        # Jellyfin's tiny 256 kbps default.
        if mode == "transcode":
            vbr = max_bitrate if max_bitrate > 0 else 120_000_000
            up += f"&VideoBitRate={vbr}"
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


#: The events the player reports. Jellyfin's own stop handler treats "within 5%
#: of the end" as finished, and so do we (see FINISHED_FRACTION below).
_KNOWN_EVENTS = ("start", "timeupdate", "stopped")
FINISHED_FRACTION = 0.95


@router.post("/jellyfin/progress")
def jellyfin_progress(payload: JellyfinProgressRequest):
    """Record playback progress on the ITEM so Watched/resume UI updates.

    Keeps the Jellyfin credential server-side; the browser only POSTs JSON here.
    A report near the end of a ``stopped`` playback marks the item watched
    instead of storing a resume point at the credits.
    """
    # ⚠ Do NOT switch this back to Jellyfin's /Sessions/Playing* endpoints: they
    # only write when the report matches a live *device playback session*, and
    # in-app playback never is one (the app proxies the stream itself), so they
    # answer 204 and store nothing — which is exactly why Continue Watching
    # stopped updating (2026-09-11). Every shape was tried live on 10.11.11 (real
    # PlaySessionId, invented one, device header, X-Emby-Token, Authorization):
    # all accepted-and-dropped. The user-scoped user-data write inside
    # set_playback_position is the one that lands, verified by reading it back.
    cfg = get_config()
    if not payload.item_id:
        raise HTTPException(status_code=400, detail="Missing item_id")
    if payload.event not in _KNOWN_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unknown event: {payload.event}")

    service = build_library_service(cfg)
    if service is None:
        raise HTTPException(status_code=503, detail="Jellyfin not configured")

    finished = (
        payload.event == "stopped"
        and payload.runtime_ticks > 0
        and payload.position_ticks >= payload.runtime_ticks * FINISHED_FRACTION
    )
    try:
        if finished:
            played = bool((service.mark_state(payload.item_id, True) or {}).get("played"))
            if not played:
                raise HTTPException(status_code=502, detail="Jellyfin did not mark the item watched")
        elif not service.set_playback_position(payload.item_id, payload.position_ticks):
            # A 204 here would be the same lie the Sessions endpoint told: "we
            # accepted it" while nothing was stored. Say it did not land.
            raise HTTPException(status_code=502, detail="Jellyfin did not store the playback position")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 - transport failure
        logger.warning("jellyfin progress(%s/%s) failed: %s", payload.event, payload.item_id, e)
        raise HTTPException(status_code=502, detail="Jellyfin progress unavailable")
    return JSONResponse(status_code=204, content=None)