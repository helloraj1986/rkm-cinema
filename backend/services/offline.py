"""Offline downloads — the SERVER half: staging, packaging, and byte-range serving.

Phase **B1** of ``docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md`` (§4.2 packaging, §4.3
contract). It exists because the E1 spike answered the one question this design
hung on — ``apple/SPIKE_E1_E2.md``: a file served over ``http://127.0.0.1``
**plays inside the app's WKWebView, with seeking**, and a ``WKURLSchemeHandler``
does not. So the device's job is to obtain a real file it can keep and serve
locally; this module's job is to hand it one over HTTP, byte-ranged, verifiable,
and resumable.

**The five decisions that shape everything here** (full reasoning: `ADR-0007`):

1. **Staging lives on the api's own ``rkm_shared`` volume** (``/shared/offline``),
   which every rebuild keeps and which needs no compose change. It is deliberately
   NOT inside a media root: a directory of downloadable films under ``D:\\RKM_MEDIA``
   is a directory Jellyfin would scan and index as library items.
2. **A direct-playable item is NOT copied.** Its artefact IS the library file,
   recorded in the manifest as ``borrowed``; ``prepare`` does no I/O for it and
   ``delete`` never unlinks it. §4.2's "the file as-is — no server CPU" taken
   literally, and it avoids duplicating a 40 GB film to hand the same bytes to a
   phone.
3. **Packaging drives Jellyfin's own transcode pipe into a file** — the mode ladder
   the player already uses (``jellyfin_stream.py``), so the api image gains no
   dependency (no ffmpeg). A transcode pipe is tied to a playback session, which is
   the wrong lifetime for a download; the FILE is the thing that outlives it.
4. **Atomic publish: ``.part`` → ``os.replace``.** The final path exists only when
   the transfer finished, so ``ready`` and ``Content-Length`` cannot describe a
   half-film. A crash leaves a ``.part``, never a serveable fragment.
5. **State is DERIVED FROM DISK**, not from an in-memory registry: a manifest plus
   whatever the filesystem says right now. An api restart therefore cannot lose a
   download, and a packaging job that died is reported as ``failed`` rather than
   spinning ``packaging`` forever (`_STALL_SECONDS`, and only when no live writer
   exists for it).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("rkm.services.offline")

#: Where packaged renditions live. On the api's own persistent volume (see D1).
STAGING_DEFAULT = "/shared/offline"
#: Hours a staged file survives after its last access (§4.2's staging TTL).
TTL_HOURS_DEFAULT = 48
#: Cap on staged (non-borrowed) bytes. 12 GiB, because the staging volume is the
#: Docker host's disk and NOT the media drive — a household download must never
#: be able to fill it. 0 disables the cap.
MAX_BYTES_DEFAULT = 12 * 1024 ** 3

_CHUNK = 1 << 16  # 64 KiB — the same read size the stream proxy uses
#: A packaging job with no live writer AND no byte written for this long is
#: reported ``failed`` instead of ``packaging``. Five minutes: Jellyfin can spend a
#: while cold-starting a transcode before the first byte, and that case still has a
#: live writer, which is checked FIRST.
_STALL_SECONDS = 300
#: How often a served request rewrites its manifest's ``last_access``.
_TOUCH_EVERY = 60

#: The rendition ladder, exactly the modes ``jellyfin_stream.py`` already speaks.
MODES = ("direct", "remux", "transcode_audio", "transcode")
AUTO = "auto"

#: Manifest states. ``missing`` is DERIVED at read time, never stored.
READY = "ready"
PACKAGING = "packaging"
FAILED = "failed"
MISSING = "missing"

#: What WebKit can be trusted to play — MIRRORED from the player's own ladder
#: (`frontend/src/features/playback/lib.ts::pickStreamMode`, the routing the app
#: already streams with). This is deliberately not re-derived: a downloaded film is
#: played by the SAME WKWebView that streams it, so a download the player would have
#: transcoded must be transcoded here too, or the device keeps a file it cannot play.
#: ⚠ HEVC is NOT in the safe set — the player transcodes it — and H.264 with a 10-bit
#: depth or a "high 10" profile is refused for the same reason.
SAFE_VIDEO_CODECS = ("h264", "avc1", "vp9", "av01", "vp8", "theora")
BROWSER_SAFE_AUDIO = ("aac", "mp3", "opus", "vorbis", "flac",
                      "pcm_s16le", "pcm_s24le", "pcm_mulaw", "alac")

#: ⚠⚠ THE CONTAINER IS NOT AN EXTENSION, AND THIS WAS MEASURED THE HARD WAY (2026-09-16,
#: 60 real library items through the DEPLOYED api): Jellyfin reports `Container` as
#: ffprobe's ``format_name``, a **comma-separated demuxer list** — an ordinary MP4
#: arrives as **``"mov,mp4,m4a,3gp,3g2,mj2"``** (39 of the 60 sampled titles), while an
#: MKV arrives as plain ``"mkv"``. So a direct-play check against bare extensions
#: (`{"mp4","m4v","mov"}`) **never matches a real MP4**, and every MP4 would take the
#: remux rung: a full re-copy of the film through Jellyfin plus a full-size staging file,
#: for a file the device can hold and play as-is. Hence: match the FAMILY, not the string.
#: ⚠ The same mismatch exists today in the PLAYER's own `DIRECT_CONTAINERS`
#: (`frontend/src/features/playback/lib.ts`), which is where this list came from —
#: reported to the user rather than changed here, because changing player routing is a
#: live playback behaviour change and this phase's file is the backend.
MP4_FAMILY = ("mov", "mp4", "m4a", "m4v", "3gp", "3g2", "mj2")
#: ffprobe names the WebM demuxer ``matroska,webm`` — the SAME string an MKV gives, so
#: the codec decides: WebKit demuxes Matroska for the WebM codecs and nothing else.
MATROSKA_FAMILY = ("matroska", "webm")
WEBM_VIDEO_CODECS = ("vp8", "vp9", "av01")
#: ⚠ ffprobe spells the codec **``av1``**; the ISO/RFC tag (and the player's own safe set)
#: is **``av01``**. Measured live: one library title reports `av1`, and the player's
#: `SAFE_VIDEO_CODECS` would therefore treat it as unsafe. Both spellings are accepted.
VIDEO_CODEC_ALIASES = {"av1": "av01", "x264": "h264", "x265": "hevc"}

_SINGLE_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_UNSAFE_ID = re.compile(r"[^A-Za-z0-9_-]")

UNSATISFIABLE = "unsatisfiable"


# --------------------------------------------------------------------------- ranges

def parse_range(header: str, size: int) -> Any:
    """Interpret one ``Range`` header against a known file size.

    Returns ``(start, end)`` **inclusive** for a satisfiable single range, ``None``
    when the header must be IGNORED (absent, another unit, unparseable, or a
    multi-range list — ``multipart/byteranges`` is deliberately not implemented,
    and answering the whole file is the safe reading of "unsatisfiable-or-complex"),
    or :data:`UNSATISFIABLE` when the range is well-formed and cannot be met, which
    is a ``416`` with ``Content-Range: bytes */size`` per RFC 9110 §14.1.2.

    ``size`` is the CURRENT file size (``os.stat``), never the manifest's recorded
    one — a Content-Length that disagrees with the file is the bug this whole
    module is shaped to avoid.
    """
    if not header:
        return None
    match = _SINGLE_RANGE.match(header.strip())
    if match is None:
        return None
    first, last = match.group(1), match.group(2)
    if not first and not last:
        return None
    if size <= 0:
        return UNSATISFIABLE
    if not first:
        # "bytes=-N": the LAST N bytes.
        suffix = int(last)
        if suffix <= 0:
            return UNSATISFIABLE
        start = max(0, size - suffix)
        return (start, size - 1)
    start = int(first)
    if start >= size:
        return UNSATISFIABLE
    if not last:
        return (start, size - 1)
    end = min(int(last), size - 1)
    if end < start:
        # A reversed range ("bytes=500-100") is not satisfiable.
        return UNSATISFIABLE
    return (start, end)


def container_family(container: str) -> str:
    """ffprobe's demuxer list → the container as a FAMILY (see ``MP4_FAMILY`` above).

    ``"mov,mp4,m4a,3gp,3g2,mj2"`` → ``"mp4"`` · ``"mkv"`` → ``"mkv"`` ·
    ``"matroska,webm"`` → ``"matroska"`` · unknown/absent → ``""`` (which the ladder reads
    as "attempt the cheap path", the same rule the player uses for an unknown container).

    ⚠ Order matters: an MP4's list is checked BEFORE Matroska, because the family strings
    can share tokens and the MP4 list is the one that means "WebKit plays this as-is".
    """
    tokens = [t.strip().lower() for t in str(container or "").split(",") if t.strip()]
    if not tokens:
        return ""
    if any(t in MP4_FAMILY for t in tokens):
        return "mp4"
    if any(t in MATROSKA_FAMILY for t in tokens):
        return "matroska"
    return tokens[0]


def normalise_video_codec(codec: str) -> str:
    """ffprobe's spelling → the tag the player's safe set uses (see aliases above)."""
    lowered = (codec or "").lower()
    return VIDEO_CODEC_ALIASES.get(lowered, lowered)


def video_needs_transcode(codec: str, *, profile: str = "", bit_depth: int = 0) -> bool:
    """The player's ``videoNeedsTranscode``, in Python (see the constants above).

    Unknown/absent facts answer ``False`` — attempt the cheaper rendition and let the
    player's own error ladder escalate, exactly as the streaming path does.
    """
    codec = normalise_video_codec(codec)
    if codec and codec not in SAFE_VIDEO_CODECS:
        return True
    if codec in ("h264", "avc1"):
        if int(bit_depth or 0) >= 10:
            return True
        if "10" in (profile or "").lower():
            return True
    return False


def audio_needs_transcode(codecs) -> bool:
    """True when ANY track must be re-encoded (a film has one audio track that plays)."""
    for codec in codecs or []:
        codec = str(codec or "").lower()
        if codec and codec not in BROWSER_SAFE_AUDIO:
            return True
    return False


def choose_mode(*, container: str, video_codec: str, audio_codecs,
                video_profile: str = "", video_bit_depth: int = 0) -> str:
    """Pick the cheapest rendition that will actually play — the player's own ladder.

    Pure, so the ladder is testable without a media server, and MIRRORED from
    ``pickStreamMode`` (``frontend/src/features/playback/lib.ts``) rather than
    re-invented: the same facts produce the same mode as the in-app player chooses,
    which is the only routing a downloaded file has been measured against. Facts come
    from ``LibraryService.playback_info``.

    ⚠ TWO CORRECTIONS to the mirrored rule, both measured against the live api
    (2026-09-16) rather than reasoned about: the container is matched by FAMILY, because
    Jellyfin reports ffprobe's demuxer list (see ``MP4_FAMILY``), and the codec is
    normalised, because ffprobe writes ``av1`` where the player's safe set says ``av01``.

    The player's first rung (``quality !== "Original" → transcode``) has no analogue
    here on purpose: a download always asks for the Original rendition. If a quality
    cap ever becomes a download option, this is where it lands.
    """
    family = container_family(container)
    if video_needs_transcode(video_codec, profile=video_profile,
                             bit_depth=video_bit_depth):
        return "transcode"
    if audio_needs_transcode(audio_codecs):
        return "transcode_audio"
    if family == "mp4" or family == "":
        return "direct"
    if family == "matroska" and normalise_video_codec(video_codec) in WEBM_VIDEO_CODECS:
        # A genuine WebM: WebKit demuxes Matroska for these codecs and no others.
        return "direct"
    # Right streams, wrong box (an MKV with H.264): copy both, no CPU.
    return "remux"


def needs_transcode(mode: str) -> bool:
    """Whether *mode* costs server CPU (the UI surfaces the cost, §4.2 row 4)."""
    return mode in ("transcode_audio", "transcode")


# --------------------------------------------------------------------------- model

@dataclass
class OfflineManifest:
    """One staged rendition: what it is, where it is, and how far along it is."""

    item_id: str
    mode: str
    state: str = PACKAGING
    #: The playable artefact. For a BORROWED (direct-play) rendition this is the
    #: library file itself.
    path: str = ""
    size: int = 0
    duration_s: float = 0.0
    title: str = ""
    container: str = ""
    #: True when ``path`` is the household's own library file — recorded so
    #: ``delete`` and the TTL sweep can never remove media they do not own.
    borrowed: bool = False
    created_at: float = 0.0
    last_access: float = 0.0
    error: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "OfflineManifest":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


class OfflineError(Exception):
    """A prepare that cannot proceed, with the HTTP status the route should use."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class OfflineRefused(OfflineError):
    """Staging is full or unavailable — 507, never a silent overrun."""

    def __init__(self, message: str, *, status: int = 507):
        super().__init__(message, status=status)


# --------------------------------------------------------------------------- store

class OfflineStore:
    """The staging directory: manifests, artefacts, TTL and the byte cap.

    Every method that reports a size or a state reads the FILESYSTEM. The manifest
    is the record of *what this is*; the filesystem is the record of *whether it is
    there*, and when the two disagree the filesystem wins.
    """

    def __init__(self, *, root: Optional[str] = None, config=None):
        cfg = config
        self._config = cfg
        if root is None:
            root = getattr(cfg, "RKM_OFFLINE_STAGING", "") or STAGING_DEFAULT
        self._root = Path(str(root))

    # -- policy ------------------------------------------------------------

    def ttl_seconds(self) -> int:
        """How long an untouched staged artefact survives (0 = keep forever)."""
        return _ttl_seconds(self._config)

    def resolve_expiry(self, manifest: OfflineManifest) -> float:
        """When the TTL will collect this artefact — 0 when the TTL is off.

        Reported so the device (and the Downloads screen) can show "expires in 2
        days" rather than letting a file vanish unexplained.
        """
        ttl = self.ttl_seconds()
        if ttl <= 0:
            return 0.0
        return (manifest.last_access or manifest.created_at or 0) + ttl

    # -- paths -------------------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    def ensure(self) -> Path:
        """Create the staging directory. Failure here is a real 507, not a 500."""
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # noqa: BLE001 - the volume may be read-only/full
            raise OfflineRefused(
                f"the offline staging directory {self._root} is not writable: {exc}",
                status=507) from exc
        return self._root

    def key(self, item_id: str, mode: str) -> str:
        """A safe, collision-free basename for (item, rendition).

        A media-server item id is hex today, but this is a path built from a value
        that arrives in a URL — so anything outside ``[A-Za-z0-9_-]`` is stripped
        and, when that changes the id, a short digest keeps two ids from colliding
        onto one file (the path-traversal-by-construction rule of §4.4).
        """
        return f"{self.safe_id(item_id)}.{mode}"

    def safe_id(self, item_id: str) -> str:
        """The id as it may appear in a filename — never ``..``, never ``/``."""
        safe = _UNSAFE_ID.sub("", str(item_id or ""))[:64]
        if not safe:
            raise OfflineError("missing item id", status=404)
        if safe != str(item_id):
            import hashlib
            safe += "-" + hashlib.sha1(str(item_id).encode("utf-8")).hexdigest()[:10]
        return safe

    def manifest_path(self, item_id: str, mode: str) -> Path:
        return self._root / f"{self.key(item_id, mode)}.json"

    def artefact_path(self, item_id: str, mode: str) -> Path:
        """The staged file for a PACKAGED rendition (never used for ``direct``)."""
        return self._root / f"{self.key(item_id, mode)}.mp4"

    def part_path(self, item_id: str, mode: str) -> Path:
        return self._root / f"{self.key(item_id, mode)}.part"

    # -- reads -------------------------------------------------------------

    def read(self, item_id: str, mode: Optional[str] = None) -> Optional[OfflineManifest]:
        """The manifest for (item, mode) — or the NEWEST one for the item.

        ``mode=None`` is what the page and the native side use: they know the item
        they are asking about, not which rendition the server chose for it.
        """
        if mode:
            return self._load(self.manifest_path(item_id, mode))
        candidates = [self._load(p) for p in self._root.glob(f"{self.safe_id(item_id)}.*.json")]
        found = [c for c in candidates if c is not None and c.item_id == item_id]
        if not found:
            return None
        return max(found, key=lambda m: (m.last_access, m.created_at))

    def _load(self, path: Path) -> Optional[OfflineManifest]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        try:
            return OfflineManifest.from_dict(data)
        except TypeError:
            return None

    def all(self) -> list[OfflineManifest]:
        found = [self._load(p) for p in sorted(self._root.glob("*.json"))]
        return [m for m in found if m is not None]

    def resolve(self, manifest: OfflineManifest) -> OfflineManifest:
        """Refresh ``state``/``size`` from disk. The ONLY place state is decided.

        ``missing`` and ``failed`` are answers *about the present*, so they are
        computed here and never persisted — a library file that comes back, or a
        packaging job that is retried, must not stay condemned by the record.
        """
        manifest.size = 0
        if manifest.state == FAILED:
            # ⚠ A failed job STAYS failed, with its reason, until something retries it.
            # The absent artefact is the CONSEQUENCE of the failure, not the story —
            # reporting `missing` here would throw away the only useful sentence
            # ("staging filled", "connection refused") and hide that a retry is the fix.
            return manifest
        if manifest.state == PACKAGING:
            part = self.part_path(manifest.item_id, manifest.mode)
            manifest.size = _size_of(part)
            if manifest.size == 0 and not Path(manifest.path).exists():
                # Nothing on disk yet at all: normal for the first seconds.
                pass
            if not _is_active(self.key(manifest.item_id, manifest.mode)):
                stalled = (time.time() - (manifest.last_access or manifest.created_at)) > _STALL_SECONDS
                if stalled:
                    manifest.state = FAILED
                    manifest.error = manifest.error or (
                        "packaging stopped before it finished (the api restarted, or the "
                        "transfer died) — prepare again to restart it")
            return manifest
        if not manifest.path or not Path(manifest.path).exists():
            manifest.state = MISSING
            manifest.size = 0
            return manifest
        manifest.size = _size_of(Path(manifest.path))
        return manifest

    def staged_bytes(self) -> int:
        """Bytes this feature owns — borrowed library files are NOT counted."""
        total = 0
        for manifest in self.all():
            if manifest.borrowed:
                continue
            total += _size_of(Path(manifest.path)) or _size_of(
                self.part_path(manifest.item_id, manifest.mode))
        return total

    # -- writes ------------------------------------------------------------

    def write(self, manifest: OfflineManifest) -> None:
        """Write a manifest atomically: a reader never sees half a JSON object."""
        self.ensure()
        target = self.manifest_path(manifest.item_id, manifest.mode)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, target)

    def touch(self, manifest: OfflineManifest, *, every: int = _TOUCH_EVERY) -> None:
        """Record an access, at most once per *every* seconds.

        This is what makes the TTL "48 h after last ACCESS" rather than after
        creation, so a film he is streaming from staging right now cannot be swept
        out from under the transfer.
        """
        now = time.time()
        if now - (manifest.last_access or 0) < every:
            return
        manifest.last_access = now
        try:
            self.write(manifest)
        except (OSError, OfflineRefused):  # a read must never fail on a write
            logger.warning("offline: could not touch %s", manifest.item_id)

    def delete(self, item_id: str, mode: Optional[str] = None) -> list[str]:
        """Drop the manifest, and the staged file only when we own it."""
        manifest = self.read(item_id, mode)
        if manifest is None:
            return []
        removed: list[str] = []
        if not manifest.borrowed:
            for path in (Path(manifest.path), self.part_path(manifest.item_id, manifest.mode)):
                if path and _unlink(path):
                    removed.append(str(path))
        target = self.manifest_path(manifest.item_id, manifest.mode)
        if _unlink(target):
            removed.append(str(target))
        return removed

    def sweep(self, *, ttl_seconds: int) -> list[str]:
        """Remove what the TTL owns: untouched manifests, their files, dropped parts.

        Called at the START of every ``prepare`` (see ``OfflineService.prepare`` for
        why that is the honest place rather than a timer): the moment stale bytes
        can block a new download is the moment they are collected, and the app
        gains no daemon thread or scheduler dependency. A manifest for a BORROWED
        rendition ages out too — but only the manifest; the library file is the
        household's.
        """
        if ttl_seconds <= 0:
            return []
        cutoff = time.time() - ttl_seconds
        removed: list[str] = []
        for manifest in self.all():
            last = manifest.last_access or manifest.created_at or 0
            if last and last >= cutoff:
                continue
            removed.extend(self.delete(manifest.item_id, manifest.mode))
        for orphan in self._root.glob("*.part"):
            try:
                if orphan.stat().st_mtime < cutoff:
                    if _unlink(orphan):
                        removed.append(str(orphan))
            except OSError:
                continue
        if removed:
            logger.info("offline: swept %d stale artefact(s)", len(removed))
        return removed


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:  # noqa: BLE001 - report, never raise, on cleanup
        logger.warning("offline: could not remove %s: %s", path, exc)
        return False


# --------------------------------------------------------------------------- writers

#: Which artefact path a writer is currently filling. One uvicorn worker runs the
#: app (the bundled stack's Dockerfile), so a process-local registry is enough; if
#: that ever becomes untrue, this is the thing to replace first — and `resolve()`
#: already treats "no live writer" as a fact to verify against the heartbeat rather
#: than as the whole answer.
_ACTIVE: dict[str, threading.Thread] = {}
_ACTIVE_LOCK = threading.Lock()


def _is_active(key: str) -> bool:
    with _ACTIVE_LOCK:
        thread = _ACTIVE.get(key)
        if thread is None:
            return False
        if thread.is_alive():
            return True
        _ACTIVE.pop(key, None)
        return False


def _run_in_thread(fn: Callable[[], None]) -> threading.Thread:
    """The default runner: a daemon thread, so ``prepare`` answers immediately.

    A test seam in the same spirit as ``build_library_service(http=…)`` — the tests
    run the work INLINE so the assertion that follows is about the result and not
    about scheduling.
    """
    thread = threading.Thread(target=fn, name="rkm-offline-packager", daemon=True)
    thread.start()
    return thread


# --------------------------------------------------------------------------- service

@dataclass
class PrepareOutcome:
    """What ``prepare`` did, in the terms the caller (and the test) needs."""

    manifest: OfflineManifest
    #: A packaging job was started BY THIS CALL.
    started: bool = False
    #: An existing READY artefact was returned untouched (the idempotent case).
    reused: bool = False
    #: What the request asked for vs what the ladder chose.
    requested_mode: str = AUTO
    #: Bytes on disk for this rendition right now.
    bytes: int = 0

    @property
    def mode(self) -> str:
        return self.manifest.mode

    @property
    def needs_transcode(self) -> bool:
        return needs_transcode(self.manifest.mode)


class OfflineService:
    """``prepare`` / ``status`` / ``delete`` over a staging directory."""

    def __init__(self, *, config=None, library=None, store: Optional[OfflineStore] = None,
                 runner: Optional[Callable[[Callable[[], None]], Any]] = None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        if store is None:
            store = OfflineStore(config=self.config)
        self.store = store
        if library is None:
            from services.library.factory import build_library_service
            library = build_library_service(self.config)
        self.library = library
        self._runner = runner or _run_in_thread

    # -- config knobs ------------------------------------------------------

    def ttl_seconds(self) -> int:
        return self.store.ttl_seconds()

    def max_bytes(self) -> int:
        return _as_int(getattr(self.config, "RKM_OFFLINE_MAX_BYTES", None), MAX_BYTES_DEFAULT)

    # -- planning ----------------------------------------------------------

    def plan(self, item_id: str, mode: str = AUTO) -> dict:
        """Resolve the mode ladder for one item, with everything a UI needs to ask.

        Pure reads; nothing is written. The SIZE comes from the library file, which
        is the honest answer for a direct/remux rendition and an over-estimate for a
        transcode — the safe direction for the "will this fit" question §4.2 asks
        before the device commits to a download.
        """
        info = self.library.playback_info(item_id) if self.library is not None else None
        if not info:
            raise OfflineError("no playback information for this title", status=404)
        chosen = self._resolve_mode(mode, info)
        detail = (self.library.item_detail(item_id) or {}) if self.library is not None else {}
        path = (self.library.item_path(item_id) or "") if self.library is not None else ""
        return {
            "item_id": item_id,
            "mode": chosen,
            "needs_transcode": needs_transcode(chosen),
            "container": info.get("container") or "",
            "video_codec": ((info.get("video") or {}).get("codec") or ""),
            "audio_codecs": [a.get("codec") or "" for a in (info.get("audio") or [])],
            "subtitles": info.get("subtitles") or [],
            "title": str(detail.get("name") or ""),
            "year": detail.get("year"),
            "type": str(detail.get("type") or ""),
            "series_id": str(((detail.get("series") or {}) or {}).get("id") or ""),
            "duration_s": float(detail.get("runtime") or 0.0),
            "path": path,
            "bytes": _size_of(Path(path)) if path else 0,
        }

    def _resolve_mode(self, mode: str, info: dict) -> str:
        mode = (mode or AUTO).strip().lower()
        if mode == AUTO or not mode:
            video = info.get("video") or {}
            return choose_mode(
                container=info.get("container") or "",
                video_codec=video.get("codec") or "",
                video_profile=video.get("profile") or "",
                video_bit_depth=int(video.get("bit_depth") or 0),
                audio_codecs=[a.get("codec") or "" for a in (info.get("audio") or [])])
        if mode not in MODES:
            raise OfflineError(f"unknown mode: {mode} (expected one of {', '.join(MODES)})",
                               status=400)
        return mode

    # -- prepare -----------------------------------------------------------

    def prepare(self, item_id: str, mode: str = AUTO) -> PrepareOutcome:
        """Make one title downloadable, or return the copy that already exists.

        **Idempotent by construction**: (item, rendition) names one artefact, and a
        READY artefact is returned untouched. A second call while the first is still
        packaging returns the same manifest with ``started=False`` — it never starts
        a competing writer for the same file.
        """
        if not item_id:
            raise OfflineError("missing item id", status=404)

        # Sweep FIRST: the moment stale bytes can block a new download is the moment
        # they are collected (and it costs one directory listing).
        self.store.ensure()
        self.store.sweep(ttl_seconds=self.ttl_seconds())

        plan = self.plan(item_id, mode)
        chosen = plan["mode"]
        key = self.store.key(item_id, chosen)

        existing = self.store.read(item_id, chosen)
        if existing is not None:
            existing = self.store.resolve(existing)
            if existing.state in (READY, PACKAGING) and Path(existing.path or "").exists():
                self.store.touch(existing)
                return PrepareOutcome(manifest=existing, started=False,
                                      reused=existing.state == READY,
                                      requested_mode=mode, bytes=existing.size)
            if existing.state == PACKAGING and _is_active(key):
                return PrepareOutcome(manifest=existing, started=False, reused=False,
                                      requested_mode=mode, bytes=existing.size)
            # FAILED or MISSING: fall through and rebuild it.

        if chosen == "direct":
            manifest = self._borrow(item_id, plan)
            self.store.write(manifest)
            return PrepareOutcome(manifest=manifest, started=False, reused=False,
                                  requested_mode=mode, bytes=manifest.size)

        manifest = OfflineManifest(
            item_id=item_id, mode=chosen, state=PACKAGING,
            path=str(self.store.artefact_path(item_id, chosen)),
            duration_s=float(plan.get("duration_s") or 0.0),
            title=str(plan.get("title") or ""), container=str(plan.get("container") or ""),
            created_at=time.time(), last_access=time.time(),
            extra={"requested_mode": mode, "needs_transcode": needs_transcode(chosen),
                   "video_codec": plan.get("video_codec") or "",
                   "audio_codecs": plan.get("audio_codecs") or []})
        self._check_cap(item_id, chosen, plan)
        # The record goes down BEFORE the writer starts, so a crash between the two
        # leaves a manifest that says "packaging" and a heartbeat that stops — which
        # `resolve()` reports honestly as failed rather than as nothing at all.
        self.store.write(manifest)

        def _work() -> None:
            self._package(manifest)

        if self._runner is _run_in_thread:
            thread = _run_in_thread(_work)
            with _ACTIVE_LOCK:
                _ACTIVE[key] = thread
        else:
            # A test seam: run it INLINE so the assertion that follows is about the
            # result, not about scheduling.
            self._runner(_work)
        refreshed = self.store.resolve(self.store.read(item_id, chosen) or manifest)
        return PrepareOutcome(manifest=refreshed, started=True, reused=False,
                              requested_mode=mode, bytes=refreshed.size)

    def _borrow(self, item_id: str, plan: dict) -> OfflineManifest:
        """A direct-play rendition: the library file IS the artefact (D2)."""
        path = plan.get("path") or (self.library.item_path(item_id)
                                    if self.library is not None else None)
        if not path:
            raise OfflineError(
                "the media server did not report a file path for this title, so it "
                "cannot be handed to the device", status=502)
        size = _size_of(Path(path))
        if size <= 0:
            raise OfflineError(
                f"the media file is not readable from the api container ({path}) — the "
                "media mount is missing or the file moved", status=502)
        now = time.time()
        return OfflineManifest(
            item_id=item_id, mode="direct", state=READY, path=str(path), size=size,
            duration_s=float(plan.get("duration_s") or 0.0),
            title=str(plan.get("title") or ""), container=str(plan.get("container") or ""),
            borrowed=True, created_at=now, last_access=now,
            extra={"requested_mode": plan.get("mode"),
                   "needs_transcode": False})

    def _check_cap(self, item_id: str, mode: str, plan: dict) -> None:
        """Refuse BEFORE writing when this rendition would overrun the staging cap.

        ⚠ **TWO different refusals live here, and telling them apart is the whole point** (his report,
        2026-09-18: *"on any poster clicking on download says servers download storage is full"*). The
        old text said "offline staging is full" for both — a lie in the common case:

          * **The DISK is genuinely full.** Space on the Docker host behind the staging root cannot
            hold this title. That is the only case where "full" is true, so it is checked first.
          * **The BUDGET is too small.** `RKM_OFFLINE_MAX_BYTES` is the app's own budget for staged
            bytes (12 GiB by default). Nothing is "full" — a policy number is simply smaller than this
            film, and for a title bigger than the whole budget the old message was unanswerable advice:
            the knob could not even be set, because the renderer never passed it to the container
            (fixed in `render_config.py` the same day). It is passed now, so the sentence names a
            knob that actually exists.

        ⚠ The estimate is the LIBRARY FILE's size — the honest number for a direct/remux rendition and
        an over-estimate for a transcode, which is the safe direction for a refusal. A single title
        larger than the budget is refused here BEFORE a byte is written, deliberately: that download
        could never complete.
        """
        estimate = int(plan.get("bytes") or 0)

        # 1. The disk — the only "full" that is really full.
        try:
            free = shutil.disk_usage(self.store.root).free
        except OSError:
            free = None  # an unreadable root is the writer's own 507 to report, not this check's
        if estimate and free is not None and estimate > free:
            raise OfflineRefused(
                f"the staging disk is full: this title needs about {_gb(estimate)} and only "
                f"{_gb(free)} is free on the disk behind {self.store.root}. Free space on the Docker "
                "host, or point RKM_OFFLINE_STAGING at a roomier disk.")

        # 2. The app's own budget.
        cap = self.max_bytes()
        if cap <= 0:
            return
        used = self.store.staged_bytes()
        if not estimate or used + estimate <= cap:
            return
        if estimate > cap:
            raise OfflineRefused(
                f"this title alone is about {_gb(estimate)}, which is larger than the entire offline "
                f"budget of {_gb(cap)} (RKM_OFFLINE_MAX_BYTES) — it can never be staged while that "
                "budget stands. Raise the budget, or set it to 0 for no budget at all.")
        raise OfflineRefused(
            f"the offline budget is full: {_gb(used)} of {_gb(cap)} is already staged and this title "
            f"needs about {_gb(estimate)}. Delete a downloaded title, raise RKM_OFFLINE_MAX_BYTES, or "
            "set it to 0 for no budget at all.")

    # -- packaging ---------------------------------------------------------

    def upstream_url(self, item_id: str, mode: str) -> str:
        """The Jellyfin URL that produces the rendition (D3).

        The SAME query shape the player's proxy builds (``jellyfin_stream.py``), so a
        download and a stream of the same title are the same bytes — and the api
        image needs no ffmpeg. ``acting_media_token`` is used because packaging runs
        inside a session-scoped request: the file a member may download is bounded by
        the library they may watch.
        """
        from api.session import acting_media_token
        cfg = self.config
        url = (f"{cfg.JELLYFIN_URL}/Videos/{item_id}/stream?api_key={acting_media_token(cfg)}")
        if mode == "direct":
            return url + "&Static=true"
        url += f"&Static=false&MediaSourceId={item_id}&Container=mp4"
        if mode == "remux":
            url += "&VideoCodec=copy&AudioCodec=copy"
        elif mode == "transcode_audio":
            url += "&VideoCodec=copy&AudioCodec=aac&MaxAudioChannels=2"
        else:
            url += "&VideoCodec=h264&AudioCodec=aac&MaxAudioChannels=2&VideoBitRate=120000000"
        return url

    def _package(self, manifest: OfflineManifest) -> None:
        """Stream one rendition into ``.part``, then publish it atomically (D4)."""
        item_id, mode = manifest.item_id, manifest.mode
        part = self.store.part_path(item_id, mode)
        final = Path(manifest.path)
        cap = self.max_bytes()
        ceiling = 0 if cap <= 0 else cap - (self.store.staged_bytes() - manifest.size)
        try:
            self.store.ensure()
            url = self.upstream_url(item_id, mode)
            req = urllib.request.Request(url, method="GET")
            written = 0
            with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
                while True:
                    block = resp.read(_CHUNK)
                    if not block:
                        break
                    out.write(block)
                    written += len(block)
                    manifest.size = written
                    if ceiling and written > ceiling:
                        raise OfflineRefused(
                            "offline staging filled while packaging this title — the "
                            "partial file was discarded (RKM_OFFLINE_MAX_BYTES)")
                    # Heartbeat: the manifest's own mtime is what `resolve()` reads to
                    # tell "still working" from "died", so it is updated DURING the
                    # transfer, not only at the end.
                    manifest.last_access = time.time()
                    self.store.write(manifest)
                out.flush()
                os.fsync(out.fileno())
            if written <= 0:
                raise OfflineError("the media server returned no bytes for this title",
                                   status=502)
            os.replace(part, final)
            manifest.state = READY
            manifest.size = _size_of(final)
            manifest.error = ""
            manifest.last_access = time.time()
            self.store.write(manifest)
            logger.info("offline: packaged %s (%s) %d B", item_id, mode, manifest.size)
        except Exception as exc:  # noqa: BLE001 - the failure IS the outcome
            logger.warning("offline: packaging %s (%s) failed: %s", item_id, mode, exc)
            _unlink(part)
            manifest.state = FAILED
            manifest.error = str(getattr(exc, "message", None) or exc)
            manifest.size = 0
            try:
                self.store.write(manifest)
            except Exception:  # noqa: BLE001 - never raise out of a worker thread
                logger.exception("offline: could not record the failure for %s", item_id)

    # -- read-back ---------------------------------------------------------

    def status(self, item_id: str, mode: Optional[str] = None) -> Optional[OfflineManifest]:
        manifest = self.store.read(item_id, mode)
        if manifest is None:
            return None
        return self.store.resolve(manifest)

    def artefact(self, item_id: str, mode: Optional[str] = None):
        """``(manifest, path, size)`` for serving — or ``None`` when not downloadable."""
        manifest = self.status(item_id, mode)
        if manifest is None or manifest.state != READY:
            return None
        path = Path(manifest.path)
        size = _size_of(path)
        if size <= 0:
            return None
        self.store.touch(manifest)
        return manifest, path, size


# --------------------------------------------------------------------------- helpers

def _as_int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _gb(n: int) -> str:
    """Bytes as GB with one decimal — the unit a person budgets in, not a raw integer.

    ⚠ The old refusal printed both numbers as plain bytes ("12884901888 B cap"), which is the one form
    nobody can compare against a film's size. It also printed them under the word "full", which is why
    a policy limit read as a full disk.
    """
    return f"{n / 1024 ** 3:.1f} GB"


def _ttl_seconds(config) -> int:
    """TTL in seconds from ``RKM_OFFLINE_TTL_HOURS`` (accepting ``0`` = never sweep)."""
    raw = getattr(config, "RKM_OFFLINE_TTL_HOURS", None)
    if raw is None or str(raw).strip() == "":
        return TTL_HOURS_DEFAULT * 3600
    try:
        return max(0, int(float(str(raw).strip()) * 3600))
    except (TypeError, ValueError):
        return TTL_HOURS_DEFAULT * 3600


def build_offline_service(config=None, *, store=None, library=None, runner=None) -> OfflineService:
    """The one place the service is constructed, so routes and tests agree."""
    return OfflineService(config=config, store=store, library=library, runner=runner)
