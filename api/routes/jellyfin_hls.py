"""Jellyfin HLS/MSE proxy — same-origin playlists for the Plex-style player.

Replaces the progressive/restart-seek transport for non-direct titles
(see ``docs/HLS_PLAYER_PLAN.md``): the browser plays **HLS segments** via
hls.js (or native HLS on Safari), so clicking a position asks the server for
the segment at that time — a silent no-op seek is structurally impossible.

Mirrors ``jellyfin_stream.py``: the Jellyfin credential stays server-side and
the browser only ever sees same-origin ``/api`` URLs. Verified live against the
bundled Jellyfin 10.11.11 (Phase 0, ``scripts/probe_jellyfin_hls.py``):

- ``GET /Videos/{id}/master.m3u8`` returns a **3-line single-variant** master
  whose variant URI is relative (``main.m3u8?…``); the media playlist is a
  full VOD listing relative segment URIs ``hls1/main/N.ts?…``.
- **Every URI embeds ``api_key``** — this proxy strips it (server-side token
  only; nothing secret ever reaches the browser).
- Segments are ``video/mp2t`` and Range-capable upstream (206).
- Audio-aware codec routing (Phase 0 finding): copy-copy remux HLS keeps
  ``ec-3`` for EAC3 titles — Chrome MSE cannot decode it — so EAC3/AC3/DTS/
  TrueHD titles must use ``mode=transcode_audio`` (video copy + AAC), and
  ``mode=transcode`` (H.264 + AAC) is the browser-safe fallback.

Contract (additive): ``GET /api/jellyfin/hls/{item_id}/master.m3u8`` (mode
params translated to Jellyfin codec params) plus a passthrough
``GET /api/jellyfin/hls/{item_id}/{rest:path}`` for the media playlist and
segment URIs the rewritten playlists reference.
"""
from __future__ import annotations

import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from config.settings import get_config

router = APIRouter()
logger = logging.getLogger("rkm.api.jellyfin_hls")

_CHUNK = 65536
_MPEGURL = "application/vnd.apple.mpegurl"

#: Header names passed through from upstream segment responses (binary bodies
#: are streamed untouched). Content-Length is intentionally NOT forwarded —
#: the proxy streams via chunked transfer encoding (mirrors jellyfin_stream).
_PASSTHROUGH = ("Content-Type", "Accept-Ranges", "Content-Range")

#: HLS-capable routing modes — the non-direct half of the stream route's
#: ladder. ``direct`` is NOT an HLS mode (browser-seekable MP4 uses the stream
#: route); each maps to the Jellyfin codec pair Phase 0 verified live.
_HLS_MODES = ("remux", "transcode_audio", "transcode")

#: mode -> Jellyfin HLS codec params.
_MODE_CODECS = {
    # copy/copy into TS — fine when audio is browser-safe (AAC/MP3/Opus…).
    "remux": {"VideoCodec": "copy", "AudioCodec": "copy"},
    # video copied, audio re-encoded to AAC — REQUIRED for EAC3/AC3/DTS/TrueHD
    # (copy-copy HLS keeps `ec-3`, which Chrome MSE cannot decode).
    "transcode_audio": {"VideoCodec": "copy", "AudioCodec": "aac", "MaxAudioChannels": "2"},
    # full transcode — HEVC/10-bit video or a lower-bitrate quality choice.
    "transcode": {"VideoCodec": "h264", "AudioCodec": "aac", "MaxAudioChannels": "2"},
}

_API_KEY_RE = re.compile(r"api_key=[^&\s\"']*")


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


def _strip_api_keys(text: str) -> str:
    """Remove every ``api_key=…`` query param from playlist URI lines.

    Jellyfin embeds the credential in EVERY URI (master variant, media
    playlist, each segment). The proxy must delete it so the browser never
    sees the token; the passthrough route re-injects it server-side.
    """
    text = _API_KEY_RE.sub("", text)
    # Clean the leftover separators: "?&x=1" -> "?x=1", "x=1&" -> "x=1",
    # "?api_key=…&" (lone param) -> "".
    text = text.replace("?&", "?")
    text = re.sub(r"&{2,}", "&", text)
    text = re.sub(r"[?&]$", "", text, flags=re.M)
    return text


def _fetch_upstream(url: str, headers: dict[str, str] | None = None, timeout: int = 30):
    """GET upstream; return the urllib response or raise an HTTPException."""
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=e.code, detail=e.reason or "Jellyfin HLS error")  # noqa: BLE001
    except Exception as e:  # noqa: BLE001 - transport failure
        logger.warning("jellyfin hls upstream failed (%s): %s", url.split("?")[0], e)
        raise HTTPException(status_code=502, detail="Jellyfin HLS unavailable")


@router.get("/jellyfin/hls/{item_id}/master.m3u8")
def jellyfin_hls_master(
    item_id: str,
    mode: str | None = Query(default=None, description="remux (copy-copy) | transcode_audio (video copy + AAC, for EAC3 etc.) | transcode (h264+aac). Defaults to transcode unless the legacy transcode_audio=true flag is set"),
    audio_stream_index: int = Query(default=0, ge=0, description="AudioStreamIndex forwarded to Jellyfin (>0 only)"),
    max_bitrate: int = Query(default=0, ge=0, description="MaxStreamingBitrate (bps) on the transcode modes; 0 = unthrottled"),
    transcode_audio: bool = Query(default=False, description="Legacy alias for mode=transcode_audio"),
    media_source_id: str = Query(default="", description="MediaSourceId (defaults to the item id)"),
):
    """Same-origin HLS master playlist for one item.

    Fetches Jellyfin's ``/Videos/{id}/master.m3u8`` with the codec pair for the
    requested mode, then **rewrites every URI**: the embedded ``api_key`` is
    stripped and relative URIs are kept relative, so hls.js/native HLS resolve
    them against this same-origin URL — media playlists and segments then hit
    the passthrough route below and the token never leaves the server.

    ``mode`` mirrors the stream route's non-direct ladder:
    - ``remux`` → copy/copy TS (browser-safe audio only).
    - ``transcode_audio`` → video copied, audio → AAC (the Phase 0 finding for
      EAC3/AC3/DTS/TrueHD: copy-copy HLS keeps ``ec-3``, which Chrome MSE can't
      decode). Legacy ``transcode_audio=true`` maps here.
    - ``transcode`` → H.264 + AAC; honours ``max_bitrate`` / ``audio_stream_index``.

    Resume/seek needs no server param: the playlist is full VOD and hls.js
    seeks with ``startPosition``/``currentTime`` (Phase 0 verified
    ``StartTimeTicks`` does NOT truncate the playlist).
    """
    cfg = get_config()
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        raise HTTPException(status_code=503, detail="Jellyfin not configured")
    if not item_id:
        raise HTTPException(status_code=404, detail="Missing item id")

    if mode is None:
        mode = "transcode_audio" if transcode_audio else "transcode"
    if mode == "direct":
        raise HTTPException(status_code=400, detail="direct is not an HLS mode — use the stream route")
    if mode not in _HLS_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown HLS mode: {mode}")

    params: dict[str, str] = {
        "api_key": cfg.JELLYFIN_API_KEY,
        "MediaSourceId": media_source_id or item_id,
    }
    params.update(_MODE_CODECS[mode])
    if audio_stream_index > 0:
        params["AudioStreamIndex"] = str(audio_stream_index)
    if max_bitrate > 0 and mode in ("transcode_audio", "transcode"):
        params["MaxStreamingBitrate"] = str(max_bitrate)

    qs = urllib.parse.urlencode(params)
    up = f"{cfg.JELLYFIN_URL}/Videos/{item_id}/master.m3u8?{qs}"
    resp = _fetch_upstream(up)
    try:
        body = resp.read().decode("utf-8", errors="replace")
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001 - best-effort close
            pass
    return Response(content=_strip_api_keys(body), media_type=_MPEGURL, headers={
        "Cache-Control": "no-store",
    })


@router.get("/jellyfin/hls/{item_id}/{rest:path}")
def jellyfin_hls_resource(item_id: str, rest: str, request: Request):
    """Passthrough for the media playlist + segments the playlists reference.

    ``rest`` mirrors the upstream path suffix after ``/Videos/{item_id}/``
    (e.g. ``main.m3u8``, ``hls1/main/0.ts``). The client query — which carries
    ``MediaSourceId`` + codec params + ``runtimeTicks``/segment ticks exactly as
    Jellyfin emitted them in the playlist URIs — is forwarded unchanged, with a
    server-side ``api_key`` added; any client-supplied ``api_key`` is dropped
    (defence in depth; rewritten playlists never include one).

    Playlist bodies (``*m3u8``) are read fully and re-stripped of any embedded
    ``api_key``; segment bodies stream through with MIME + Range headers.
    """
    cfg = get_config()
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        raise HTTPException(status_code=503, detail="Jellyfin not configured")
    if not item_id or not rest:
        raise HTTPException(status_code=404, detail="Missing item id/path")

    # Forward the client query minus any client-supplied api_key; add ours.
    q = {k: v for k, v in request.query_params.items() if k != "api_key"}
    q["api_key"] = cfg.JELLYFIN_API_KEY
    qs = urllib.parse.urlencode(q)
    up = f"{cfg.JELLYFIN_URL}/Videos/{item_id}/{rest}?{qs}"
    headers: dict[str, str] = {}
    rng = request.headers.get("range")
    if rng:
        headers["Range"] = rng
    resp = _fetch_upstream(up, headers=headers, timeout=60)

    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "mpegurl" in ctype or rest.lower().endswith(".m3u8"):
        try:
            body = resp.read().decode("utf-8", errors="replace")
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001 - best-effort close
                pass
        return Response(content=_strip_api_keys(body), media_type=_MPEGURL, headers={
            "Cache-Control": "no-store",
        })

    status = int(getattr(resp, "status", 200))
    out_headers = {h: resp.headers.get(h) for h in _PASSTHROUGH if resp.headers.get(h)}
    return StreamingResponse(_iter_chunks(resp), status_code=status, headers=out_headers)
