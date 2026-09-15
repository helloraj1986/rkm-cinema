"""Offline downloads — the ``/api`` surface of phase **B1** (plan §4.3).

Six routes, and each one exists because a device doing something real needs it:

```
POST   /api/offline/prepare            commit: package this title for download
GET    /api/offline/bundle/{id}        preview + metadata: what it costs, what it is
GET    /api/offline/status/{id}        progress — read from DISK, never invented
HEAD   /api/offline/file/{id}          the size, before the device commits (see below)
GET    /api/offline/file/{id}          the bytes, byte-ranged and resumable
DELETE /api/offline/{id}               drop the staged copy (never the library file)
```

⚠ **``HEAD`` is an EXPLICIT route, and that is not decoration.** Measured 2026-09-14
(plan §4.3): a GET-only FastAPI route answers ``HEAD`` with **405**, so a size probe
would fail silently at the worst moment — after the device has decided to download.
The gate for this phase is a ``curl`` proof of exactly this: ``HEAD`` gives the size,
a ``Range`` request returns ``206`` + ``Content-Range``, and ``prepare`` is idempotent.

**Serving is done from the file, not from the manifest.** ``Content-Length``,
``Content-Range`` and the ETag all come from ``os.stat`` of the artefact the request
is about to read, so a length can never describe a file that is not there.

Auth: all six ride the router's ``SESSION_SCOPED`` dependency, i.e. the same level as
``POST /api/media/{id}/request`` — downloading a title is a HOUSEHOLD feature, not an
administrator action (ADR-0007 D6). The media-server credential is still one
credential: the FILE is not per-profile, and that is recorded as a decision rather
than left as an accident (§4.3).
"""
from __future__ import annotations

import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from api.models import OfflinePrepareRequest
from config.settings import get_config
from services.offline import (
    MISSING,
    PACKAGING,
    READY,
    UNSATISFIABLE,
    OfflineError,
    build_offline_service,
    parse_range,
)

router = APIRouter()
logger = logging.getLogger("rkm.api.offline")

_CHUNK = 1 << 16


def _service(config=None):
    """The one construction site. Tests patch THIS name (repo convention)."""
    return build_offline_service(config if config is not None else get_config())


def _iso(epoch: float) -> Optional[str]:
    if not epoch:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds")


def _manifest_json(manifest, *, expiry_epoch: Optional[float] = None) -> dict:
    return {
        "item_id": manifest.item_id,
        "mode": manifest.mode,
        "state": manifest.state,
        # `bytes` is what is on the server FOR THIS RENDITION right now (for a
        # packaging job that is the `.part` being written); `size` is the finished
        # artefact's size and stays 0 until it exists. Two fields on purpose: a
        # progress bar reads `bytes`, and `size` can never overstate what is ready.
        "bytes": manifest.size,
        "size": manifest.size if manifest.state == READY else 0,
        "duration_s": manifest.duration_s,
        "title": manifest.title,
        "container": manifest.container,
        "borrowed": manifest.borrowed,
        "needs_transcode": bool((manifest.extra or {}).get("needs_transcode")),
        "downloaded_at": _iso(manifest.created_at),
        "expires_at": _iso(expiry_epoch or 0),
        "error": manifest.error,
        "file_url": f"/api/offline/file/{manifest.item_id}",
    }


def _content_type(path: Path) -> str:
    """The artefact's real type — a borrowed ``.mkv`` must never claim to be MP4."""
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed and (guessed.startswith("video/") or guessed == "application/octet-stream"):
        return guessed
    return "video/mp4" if path.suffix.lower() in (".mp4", ".m4v", ".mov") \
        else "application/octet-stream"


def _file_headers(manifest, path: Path, size: int) -> dict:
    """Headers every file response carries, for both ``HEAD`` and ``GET``.

    A strong ETag (``size-mtime``) is honest here in a way it would not be on a
    transcode stream: the artefact is a finished file that only ever changes by being
    replaced whole, so "same ETag" really does mean "same bytes".
    """
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    return {
        "Content-Type": _content_type(path),
        "Accept-Ranges": "bytes",
        "ETag": f'"{size}-{mtime_ns}"',
        "Cache-Control": "no-store",
        "X-RKM-Offline-Mode": manifest.mode,
    }


def _iter_file(path: Path, start: int, end: int) -> Iterator[bytes]:
    """Yield ``[start, end]`` inclusive, in bounded chunks, closing on exit."""
    remaining = end - start + 1
    with open(path, "rb") as handle:
        handle.seek(start)
        while remaining > 0:
            block = handle.read(min(_CHUNK, remaining))
            if not block:
                break
            remaining -= len(block)
            yield block


# --------------------------------------------------------------------- prepare

@router.post("/offline/prepare")
def offline_prepare(payload: OfflinePrepareRequest):
    """Package one title for download — idempotent, and it never blocks on the work.

    Calling it twice for the same title returns the SAME artefact: a finished one is
    returned untouched (``reused: true``) and one still being built returns
    ``state: "packaging"`` instead of starting a second writer for the same file.
    """
    if not payload.item_id:
        raise HTTPException(status_code=400, detail="Missing item_id")
    service = _service()
    try:
        outcome = service.prepare(payload.item_id, payload.mode)
    except OfflineError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    manifest = outcome.manifest
    body = _manifest_json(manifest, expiry_epoch=service.store.resolve_expiry(manifest))
    body.update({
        "requested_mode": outcome.requested_mode or manifest.mode,
        "needs_transcode": outcome.needs_transcode,
        "started": outcome.started,
        "reused": outcome.reused,
    })
    return JSONResponse(body)


# --------------------------------------------------------------------- status

@router.get("/offline/status/{item_id}")
def offline_status(
    item_id: str,
    mode: Optional[str] = Query(default=None, description="which rendition; default = the newest"),
):
    """Where this download is — answered from DISK, so it survives an api restart."""
    service = _service()
    manifest = service.status(item_id, mode)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Nothing is staged for this title")
    return JSONResponse(_manifest_json(manifest,
                                       expiry_epoch=service.store.resolve_expiry(manifest)))


# --------------------------------------------------------------------- bundle

@router.get("/offline/bundle/{item_id}")
def offline_bundle(
    item_id: str,
    mode: str = Query(default="auto", description="auto | direct | remux | transcode_audio | transcode"),
):
    """Everything the device needs to write its own manifest — and to decide first.

    ⚠ This call does NOT package anything, and the size it reports is an ESTIMATE
    (``estimate_bytes``) taken from the library file. §4.2 asks for it before the
    download is committed to: "this is 2.1 GB, you have 41 GB free". The real size
    is only known once ``prepare`` has finished, and then it is ``size`` on
    ``prepare``/``status``.
    """
    service = _service()
    try:
        plan = service.plan(item_id, mode)
    except OfflineError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    manifest = service.status(item_id, plan["mode"])
    poster_item = plan["series_id"] or item_id
    body = {
        "v": 1,
        "item_id": item_id,
        "title": plan["title"],
        "year": plan["year"],
        "type": plan["type"],
        "series_id": plan["series_id"],
        "mode": plan["mode"],
        "needs_transcode": plan["needs_transcode"],
        "container": plan["container"],
        "video_codec": plan["video_codec"],
        "audio_codecs": plan["audio_codecs"],
        "duration_s": plan["duration_s"],
        "estimate_bytes": plan["bytes"],
        "state": manifest.state if manifest is not None else MISSING,
        "bytes": manifest.size if manifest is not None else 0,
        "size": manifest.size if manifest is not None and manifest.state == READY else 0,
        "borrowed": bool(manifest.borrowed) if manifest is not None else False,
        "subtitles": plan["subtitles"],
        "poster_url": f"/api/jellyfin/poster?id={poster_item}&width=500",
        "backdrop_url": f"/api/jellyfin/backdrop?id={poster_item}&width=1600",
        "file_url": f"/api/offline/file/{item_id}",
    }
    if manifest is not None:
        body["downloaded_at"] = _iso(manifest.created_at)
        body["expires_at"] = _iso(service.store.resolve_expiry(manifest))
    return JSONResponse(body)


# --------------------------------------------------------------------- the file

@router.head("/offline/file/{item_id}")
def offline_file_head(
    item_id: str,
    mode: Optional[str] = Query(default=None),
):
    """The artefact's size, without its body — what a downloader asks FIRST.

    A ``GET``-only FastAPI route answers HEAD with 405 (measured, §4.3), which would
    turn "how big is this?" into a silent failure. This is that route.
    """
    found = _service().artefact(item_id, mode)
    if found is None:
        _raise_not_ready(item_id, mode)
    manifest, path, size = found
    headers = _file_headers(manifest, path, size)
    headers["Content-Length"] = str(size)
    return Response(status_code=200, headers=headers)


@router.get("/offline/file/{item_id}")
def offline_file(
    item_id: str,
    request: Request,
    mode: Optional[str] = Query(default=None),
):
    """The artefact's bytes: ``200`` whole, ``206`` for a range, ``416`` when impossible.

    The device downloads this once and afterwards serves the SAME bytes from its own
    loopback server (that split is the whole point of the spike's two-network result:
    a downloaded film must play with the tailnet down).
    """
    found = _service().artefact(item_id, mode)
    if found is None:
        _raise_not_ready(item_id, mode)
    manifest, path, size = found
    headers = _file_headers(manifest, path, size)
    wanted = parse_range(request.headers.get("range", ""), size)

    if wanted is UNSATISFIABLE:
        # RFC 9110 §14.1.2: 416 carries the CURRENT length so the client can retry.
        headers["Content-Range"] = f"bytes */{size}"
        return Response(status_code=416, headers=headers)

    if wanted is None:
        headers["Content-Length"] = str(size)
        return StreamingResponse(_iter_file(path, 0, size - 1), status_code=200,
                                 headers=headers)

    start, end = wanted
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(_iter_file(path, start, end), status_code=206,
                             headers=headers)


def _raise_not_ready(item_id: str, mode: Optional[str]) -> None:
    """Distinguish "not asked for yet" from "still being built" — different answers.

    A downloader pointed at an item that is still packaging must be told to WAIT
    (409 + the state), not that the title does not exist (404).
    """
    manifest = _service().status(item_id, mode)
    if manifest is None:
        raise HTTPException(
            status_code=404,
            detail="Nothing is staged for this title — POST /api/offline/prepare first")
    if manifest.state == PACKAGING:
        raise HTTPException(
            status_code=409,
            detail=f"Still packaging ({manifest.size} B so far) — try again shortly")
    if manifest.state == MISSING:
        raise HTTPException(
            status_code=410,
            detail="The media file this rendition pointed at is gone from the server")
    raise HTTPException(
        status_code=409,
        detail=f"This rendition is not downloadable: {manifest.error or manifest.state}")


# --------------------------------------------------------------------- delete

@router.delete("/offline/{item_id}")
def offline_delete(
    item_id: str,
    mode: Optional[str] = Query(default=None),
):
    """Drop the staged copy. A ``direct`` (borrowed) rendition removes the RECORD only.

    ⚠ "Delete this download" must never delete the household's media file — for a
    direct-playable title the artefact IS the library file, so this route unlinks it
    only when the manifest says we own it (``borrowed: false``).
    """
    service = _service()
    manifest = service.status(item_id, mode)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Nothing is staged for this title")
    service.store.delete(item_id, manifest.mode)
    return JSONResponse({
        "ok": True,
        "item_id": item_id,
        "mode": manifest.mode,
        "removed_file": not manifest.borrowed,
    })
