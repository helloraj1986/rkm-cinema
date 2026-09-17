"""Phase B1 — the offline download API: staging, packaging, and byte-range serving.

**What this file is for.** B2 (the native downloader) and B3 (the device's own
loopback server) are written against the contract this pins, and the phase's own gate
is behavioural: *``HEAD`` gives the size, a ``Range`` request returns ``206`` +
``Content-Range``, and ``prepare`` is idempotent*. Each of those is a test here, plus
the things that would be silently wrong in production rather than loudly wrong in
development:

* **Idempotency is proved by the upstream call count**, not by comparing states —
  "packaging ran once" is the property, and a second ``prepare`` that quietly
  re-transcoded a 2 GB film would still return ``state: ready``.
* **A borrowed (direct-play) rendition is never deleted from disk.** ``delete``
  removes the RECORD; the household's media file is not ours to unlink.
* **The state is derived from disk**, so an artefact that vanished is reported
  ``missing`` and a packaging job with no live writer is reported ``failed`` — never
  a spinner over nothing.
* **Nothing serves a partial file.** A ``.part`` is not downloadable, and the length
  in every response comes from ``os.stat`` of the file about to be read.

All at the network/config boundary (the repo's usual seam): a stub library, a stub
upstream, a tmp staging directory, and the work run INLINE so the assertions that
follow are about the result and not about scheduling.
"""
from __future__ import annotations

import hashlib
import logging
import time
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.main
import api.routes.offline as offline_route
import services.offline as offline_mod
from services.offline import (
    FAILED,
    MISSING,
    PACKAGING,
    READY,
    UNSATISFIABLE,
    OfflineRefused,
    OfflineService,
    OfflineStore,
    choose_mode,
    container_family,
    normalise_video_codec,
    parse_range,
)

client = TestClient(api.main.app)

ITEM = "a1b2c3d4e5f6"


# --------------------------------------------------------------------------- stubs

class _Library:
    """The three provider calls B1 makes — and a counter for the interesting one."""

    def __init__(self, *, info=None, detail=None, path="", path_calls=None):
        self._info = info
        self._detail = detail if detail is not None else {}
        self._path = path
        self.path_calls = path_calls if path_calls is not None else []

    def playback_info(self, item_id):
        return self._info

    def item_detail(self, item_id):
        return self._detail

    def item_path(self, item_id):
        self.path_calls.append(item_id)
        return self._path


class _Upstream:
    """``urllib.request.urlopen`` — counts calls, yields a fixed body."""

    def __init__(self, body=b"", *, error=None):
        self.body = body
        self.error = error
        self.calls: list[str] = []

    def __call__(self, req, timeout=None):
        self.calls.append(getattr(req, "full_url", str(req)))

        class _Resp:
            def __init__(self, body, error):
                self._body = body
                self._pos = 0
                self.status = 200
                self.error = error

            def __enter__(self):
                if self.error is not None:
                    raise self.error
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n=-1):
                if self._pos >= len(self._body):
                    return b""
                size = n if n and n > 0 else len(self._body)
                block = self._body[self._pos:self._pos + size]
                self._pos += len(block)
                return block

            def close(self):
                pass

        return _Resp(self.body, self.error)


def _cfg(tmp_path, *, cap=None, ttl=None):
    return SimpleNamespace(
        # The two keys `upstream_url` needs. In the app the credential comes from
        # `acting_media_token` (the profile's while one is selected, the app's own key
        # outside a request) — a stub config is all this layer needs.
        JELLYFIN_URL="http://jellyfin:8096",
        JELLYFIN_API_KEY="sekret",
        RKM_OFFLINE_STAGING=str(tmp_path / "staging"),
        RKM_OFFLINE_TTL_HOURS=str(48 if ttl is None else ttl),
        RKM_OFFLINE_MAX_BYTES=str(0 if cap is None else cap),
    )


def _service(tmp_path, *, library, cap=None, ttl=None):
    """A service wired to a tmp staging dir, with the work run INLINE."""
    cfg = _cfg(tmp_path, cap=cap, ttl=ttl)
    store = OfflineStore(root=cfg.RKM_OFFLINE_STAGING, config=cfg)
    return OfflineService(config=cfg, library=library, store=store,
                          runner=lambda fn: fn())


def _remuxable_library(path=""):
    """An MKV/H.264/AAC title: the ladder's middle rung, so packaging (not direct)."""
    return _Library(
        info={"container": "mkv", "video": {"codec": "h264"},
              "audio": [{"codec": "aac"}], "subtitles": [{"index": 2, "language": "eng"}]},
        detail={"name": "Some Film", "year": 2019, "runtime": 6800.0, "type": "movie"},
        path=path)


def _patch_offline(monkeypatch, service):
    """Point the ROUTES at a service (the route module's own name, repo convention)."""
    monkeypatch.setattr(offline_route, "build_offline_service", lambda config=None: service)
    return service


# --------------------------------------------------------------------------- 1. the ladder

@pytest.mark.parametrize("container,video,audio,want", [
    # ⚠ The container strings below are the ones the DEPLOYED api actually reported on
    # 2026-09-16 (60 real library items), not tidy extensions: an MP4 is a comma-separated
    # ffprobe demuxer list, an MKV is plain "mkv", and WebM and MKV share "matroska,webm".
    ("mov,mp4,m4a,3gp,3g2,mj2", "h264", ["aac"], "direct"),
    ("mov,mp4,m4a,3gp,3g2,mj2", "h264", ["mp3"], "direct"),
    ("mp4", "h264", ["aac"], "direct"),
    ("m4v", "h264", ["aac"], "direct"),
    ("", "h264", ["aac"], "direct"),                      # unknown → attempt the cheap path
    ("matroska,webm", "vp9", ["opus"], "direct"),         # a genuine WebM
    ("mkv", "h264", ["aac"], "remux"),                    # right streams, wrong box
    ("mkv", "av1", ["opus"], "remux"),                    # ⚠ codec spelling: av1 → av01
    ("mov,mp4,m4a,3gp,3g2,mj2", "h264", ["eac3"], "transcode_audio"),
    ("mkv", "h264", ["dts"], "transcode_audio"),
    ("mkv", "h264", ["aac", "eac3"], "transcode_audio"),  # ONE bad track is enough
    ("mkv", "hevc", ["aac"], "transcode"),                # the player transcodes HEVC too
    ("mkv", "mpeg2", ["aac"], "transcode"),
    ("avi", "vc1", ["ac3"], "transcode"),
    ("matroska,webm", "h264", ["aac"], "remux"),          # Matroska H.264 is NOT WebM
])
def test_the_rendition_ladder_picks_the_cheapest_thing_that_plays(container, video, audio, want):
    assert choose_mode(container=container, video_codec=video, audio_codecs=audio) == want


def test_the_container_is_ffprobes_DEMUXER_LIST_not_an_extension():
    """⚠⚠ The finding that made this ladder wrong for 39 of 60 real titles.

    Measured against the deployed api (2026-09-16): Jellyfin's `Container` for an ordinary
    MP4 is `"mov,mp4,m4a,3gp,3g2,mj2"`. A direct-play check against bare extensions never
    matches it, so **every MP4** would take the remux rung — a full re-copy of the film
    through Jellyfin and a full-size staging file, for a file the device can hold and play
    as-is. This pins the family mapping, including the ambiguous Matroska string.
    """
    assert container_family("mov,mp4,m4a,3gp,3g2,mj2") == "mp4"
    assert container_family("mkv") == "mkv"
    assert container_family("matroska,webm") == "matroska"
    assert container_family("") == ""
    assert container_family("MOV,MP4") == "mp4", "the check must not be case-sensitive"


def test_the_codec_spelling_ffprobe_uses_is_normalised():
    """⚠ ffprobe writes `av1`; the player's safe set says `av01` — so the alias decides
    whether one real library title is remuxed or needlessly re-encoded."""
    assert normalise_video_codec("av1") == "av01"
    assert normalise_video_codec("h264") == "h264"
    assert choose_mode(container="mkv", video_codec="av1", audio_codecs=["opus"]) == "remux"
    assert choose_mode(container="matroska,webm", video_codec="av1", audio_codecs=["opus"]) \
        == "direct"


def test_the_ladder_matches_the_PLAYERS_own_routing():
    """⚠ The one property that makes a download playable at all.

    A downloaded film is played by the SAME WKWebView that streams it, so the mode
    the server packages must be the mode the player would have chosen. HEVC is the
    case that shows why this is mirrored rather than re-derived: iOS *can* decode
    HEVC-in-MP4, but the app's own ladder transcodes it (its safe set is
    h264/avc1/vp9/av01/vp8/theora), so a "clever" remux here would hand the device a
    file the player refuses.
    """
    assert choose_mode(container="mkv", video_codec="hevc", audio_codecs=["aac"]) == "transcode"
    # 10-bit / "high 10" H.264 is refused for the same measured reason.
    assert choose_mode(container="mp4", video_codec="h264", audio_codecs=["aac"],
                       video_bit_depth=10) == "transcode"
    assert choose_mode(container="mp4", video_codec="h264", audio_codecs=["aac"],
                       video_profile="High 10") == "transcode"
    # ...and 8-bit High profile stays on the cheap path.
    assert choose_mode(container="mp4", video_codec="h264", audio_codecs=["aac"],
                       video_profile="High", video_bit_depth=8) == "direct"
    # ⚠ Quality is deliberately NOT a rung here (a download asks for the Original
    # rendition) — pinned so a future session does not "restore" it by accident.
    import inspect
    assert "quality" not in inspect.signature(choose_mode).parameters


# --------------------------------------------------------------------------- 2. ranges

@pytest.mark.parametrize("header,size,want", [
    ("", 100, None),
    ("bytes=0-49", 100, (0, 49)),
    ("bytes=50-", 100, (50, 99)),
    ("bytes=-10", 100, (90, 99)),
    ("bytes=0-999", 100, (0, 99)),                    # clamped to the real end
    ("bytes=99-99", 100, (99, 99)),                   # the last byte
    ("bytes=100-", 100, UNSATISFIABLE),               # start == size
    ("bytes=200-300", 100, UNSATISFIABLE),
    ("bytes=50-10", 100, UNSATISFIABLE),              # reversed
    ("bytes=0-49,60-99", 100, None),                  # multi-range: ignored, whole file
    ("items=0-49", 100, None),                        # not bytes
    ("bytes=abc", 100, None),
    ("bytes=-0", 100, UNSATISFIABLE),
    ("bytes=0-", 0, UNSATISFIABLE),                   # an empty file has no first byte
])
def test_parse_range_is_exact(header, size, want):
    assert parse_range(header, size) == want


# --------------------------------------------------------------------------- 3. prepare

def test_prepare_packages_a_rendition_and_publishes_it_atomically(tmp_path, monkeypatch):
    """The middle rung: bytes are fetched into ``.part``, then published whole."""
    upstream = _Upstream(b"m" * 150_000)          # > 2 chunks, so the loop really loops
    monkeypatch.setattr(offline_mod.urllib.request, "urlopen", upstream)
    service = _service(tmp_path, library=_remuxable_library())

    outcome = service.prepare(ITEM)

    assert outcome.manifest.state == READY
    assert outcome.manifest.mode == "remux"
    assert outcome.started is True and outcome.reused is False
    artefact = Path(outcome.manifest.path)
    assert artefact.exists() and artefact.read_bytes() == b"m" * 150_000
    assert outcome.manifest.size == 150_000
    assert not service.store.part_path(ITEM, "remux").exists(), "a .part survived the publish"
    assert "VideoCodec=copy" in upstream.calls[0]


def test_prepare_is_idempotent_and_proved_by_the_upstream_call_count(tmp_path, monkeypatch):
    """⚠ The property is "packaging ran ONCE" — not "state reads ready twice".

    A second call that quietly re-transcoded the same film would return
    ``state: ready`` as well, and the only thing that catches it is counting.
    """
    upstream = _Upstream(b"z" * 90_000)
    monkeypatch.setattr(offline_mod.urllib.request, "urlopen", upstream)
    service = _service(tmp_path, library=_remuxable_library())

    first = service.prepare(ITEM)
    digest_before = hashlib.sha256(Path(first.manifest.path).read_bytes()).hexdigest()
    mtime_before = Path(first.manifest.path).stat().st_mtime_ns

    second = service.prepare(ITEM)

    assert len(upstream.calls) == 1, "the second prepare re-packaged the same title"
    assert second.reused is True and second.started is False
    assert second.manifest.path == first.manifest.path
    assert second.manifest.size == first.manifest.size == 90_000
    assert Path(first.manifest.path).stat().st_mtime_ns == mtime_before
    assert hashlib.sha256(Path(first.manifest.path).read_bytes()).hexdigest() == digest_before


def test_prepare_chooses_direct_for_a_direct_playable_title_and_copies_nothing(tmp_path):
    """§4.2 row 1 taken literally: no CPU, no duplicate of a multi-GB film."""
    library_file = tmp_path / "Film.mp4"
    library_file.write_bytes(b"d" * 4096)
    library = _Library(info={"container": "mp4", "video": {"codec": "h264"},
                             "audio": [{"codec": "aac"}], "subtitles": []},
                       detail={"name": "Film", "runtime": 120.0}, path=str(library_file))
    service = _service(tmp_path, library=library)

    outcome = service.prepare(ITEM)

    assert outcome.manifest.mode == "direct"
    assert outcome.manifest.borrowed is True
    assert outcome.manifest.path == str(library_file)
    assert outcome.manifest.size == 4096
    staged = list((tmp_path / "staging").glob("*.mp4"))
    assert staged == [], f"a direct rendition was copied into staging: {staged}"


def test_deleting_a_direct_rendition_never_deletes_the_media_file(tmp_path):
    """⚠ The one destructive mistake this feature could make, pinned."""
    library_file = tmp_path / "Film.mp4"
    library_file.write_bytes(b"d" * 2048)
    library = _Library(info={"container": "mp4", "video": {"codec": "h264"},
                             "audio": [{"codec": "aac"}], "subtitles": []},
                       detail={"name": "Film"}, path=str(library_file))
    service = _service(tmp_path, library=library)
    service.prepare(ITEM)

    service.store.delete(ITEM, "direct")

    assert library_file.exists(), "delete() removed the household's own media file"
    assert service.status(ITEM) is None


def test_a_packaged_rendition_is_deleted_from_staging(tmp_path, monkeypatch):
    monkeypatch.setattr(offline_mod.urllib.request, "urlopen", _Upstream(b"p" * 5_000))
    service = _service(tmp_path, library=_remuxable_library())
    outcome = service.prepare(ITEM)
    artefact = Path(outcome.manifest.path)
    assert artefact.exists()

    removed = service.store.delete(ITEM, "remux")

    assert not artefact.exists()
    assert str(artefact) in removed
    assert service.status(ITEM) is None


# --------------------------------------------------------------------------- 4. honesty

def test_a_failed_packaging_is_recorded_and_leaves_nothing_serveable(tmp_path, monkeypatch):
    upstream = _Upstream(error=urllib.error.URLError("connection refused"))
    monkeypatch.setattr(offline_mod.urllib.request, "urlopen", upstream)
    service = _service(tmp_path, library=_remuxable_library())

    outcome = service.prepare(ITEM)

    assert outcome.manifest.state == FAILED
    assert "refused" in outcome.manifest.error
    assert not service.store.part_path(ITEM, "remux").exists()
    assert service.artefact(ITEM) is None


def test_an_upstream_that_returns_no_bytes_is_a_failure_not_an_empty_film(tmp_path, monkeypatch):
    monkeypatch.setattr(offline_mod.urllib.request, "urlopen", _Upstream(b""))
    service = _service(tmp_path, library=_remuxable_library())

    outcome = service.prepare(ITEM)

    assert outcome.manifest.state == FAILED
    assert "no bytes" in outcome.manifest.error


def test_a_vanished_artefact_reads_as_missing_rather_than_ready(tmp_path):
    """§4.7 "housekeeping": the file went away, and the record must not pretend."""
    service = _service(tmp_path, library=_remuxable_library())
    store = service.store
    staged = store.artefact_path(ITEM, "remux")
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"q" * 10)
    store.write(offline_mod.OfflineManifest(
        item_id=ITEM, mode="remux", state=READY, path=str(staged), size=10,
        created_at=time.time(), last_access=time.time()))

    staged.unlink()

    status = service.status(ITEM)
    assert status.state == MISSING and status.size == 0
    assert service.artefact(ITEM) is None, "a missing file was offered for download"


def test_a_packaging_job_with_no_live_writer_and_a_stale_heartbeat_is_failed(tmp_path):
    """A killed api must not leave a spinner: the heartbeat is the evidence."""
    service = _service(tmp_path, library=_remuxable_library())
    store = service.store
    store.write(offline_mod.OfflineManifest(
        item_id=ITEM, mode="remux", state=PACKAGING,
        path=str(store.artefact_path(ITEM, "remux")),
        created_at=time.time() - 9999, last_access=time.time() - 9999))

    status = service.status(ITEM)

    assert status.state == FAILED
    assert "restart" in status.error or "prepare again" in status.error


def test_a_packaging_job_that_is_still_working_stays_packaging(tmp_path):
    """The other half of the rule — a fresh heartbeat is not a failure."""
    service = _service(tmp_path, library=_remuxable_library())
    store = service.store
    part = store.part_path(ITEM, "remux")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"w" * 1234)
    store.write(offline_mod.OfflineManifest(
        item_id=ITEM, mode="remux", state=PACKAGING,
        path=str(store.artefact_path(ITEM, "remux")),
        created_at=time.time(), last_access=time.time()))

    status = service.status(ITEM)

    assert status.state == PACKAGING
    assert status.size == 1234, "progress must be the .part's real size"


# --------------------------------------------------------------------------- 5. the cap

def test_prepare_refuses_when_staging_is_full(tmp_path, monkeypatch):
    big = tmp_path / "Big.mkv"
    big.write_bytes(b"b" * 50_000)
    service = _service(tmp_path, library=_remuxable_library(path=str(big)), cap=10_000)

    with pytest.raises(OfflineRefused) as caught:
        service.prepare(ITEM)

    assert caught.value.status == 507
    assert "RKM_OFFLINE_MAX_BYTES" in caught.value.message

    # ...and the same refusal reaches the caller as a 507, not a 500.
    _patch_offline(monkeypatch, service)
    r = client.post("/api/offline/prepare", json={"item_id": ITEM})
    assert r.status_code == 507
    assert "RKM_OFFLINE_MAX_BYTES" in r.json()["detail"]


def test_the_refusal_is_readable_in_the_SERVER_LOG(tmp_path, monkeypatch, caplog):
    """⚠ The sentence a refusal carries is the only statement of its cause, and until the client is
    rebuilt it shows just its canned half ("the download storage is full" — which cannot tell a full
    disk from a budget smaller than the film). The api's own log is therefore the one place a person
    can read the reason TODAY:

        docker compose logs --tail=50 api | grep "offline: prepare refused"

    That makes this a contract, not a nicety: the route used to log nothing at all, so the advice
    "the log now says which in words" was advice that did not work.
    """
    big = tmp_path / "Big.mkv"
    big.write_bytes(b"b" * 50_000)
    service = _service(tmp_path, library=_remuxable_library(path=str(big)), cap=10_000)
    _patch_offline(monkeypatch, service)

    with caplog.at_level(logging.WARNING, logger="rkm.api.offline"):
        r = client.post("/api/offline/prepare", json={"item_id": ITEM})

    assert r.status_code == 507
    said = [rec.getMessage() for rec in caplog.records]
    refused = [m for m in said if m.startswith("offline: prepare refused")]
    assert refused, f"the refusal was not logged at all: {said}"
    assert "507" in refused[0], "the status must be in the line"
    assert ITEM in refused[0], "which title was refused must be in the line"
    # ⚠ THE SENTENCE, not the status — a bare "507" logged is the bug this test exists for.
    assert "larger than the entire offline budget" in refused[0]


def test_a_title_bigger_than_the_whole_budget_says_THAT_not_full(tmp_path):
    """⚠ The classification his report turned up (2026-09-18).

    A film larger than the entire budget can never be staged, and the old message called that
    "offline staging is full" — a lie that sent him looking for a full disk. The sentence must name
    the budget, the film's size and the way out.
    """
    big = tmp_path / "Huge.mkv"
    big.write_bytes(b"h" * 50_000)
    service = _service(tmp_path, library=_remuxable_library(path=str(big)), cap=10_000)

    with pytest.raises(OfflineRefused) as caught:
        service.prepare(ITEM)

    assert caught.value.status == 507
    assert "larger than the entire offline budget" in caught.value.message
    assert "RKM_OFFLINE_MAX_BYTES" in caught.value.message
    # The numbers are GB, not the raw byte count nobody can compare against a film.
    assert "GB" in caught.value.message
    assert "full" not in caught.value.message.split("budget")[0]


def test_a_genuinely_full_DISK_still_says_full(tmp_path, monkeypatch):
    """The other half of the same pair: when the DISK is the constraint, "full" is the truth."""
    from collections import namedtuple

    usage = namedtuple("usage", "total used free")
    big = tmp_path / "Big.mkv"
    big.write_bytes(b"b" * 50_000)
    service = _service(tmp_path, library=_remuxable_library(path=str(big)), cap=0)  # no budget at all
    monkeypatch.setattr(offline_mod.shutil, "disk_usage",
                        lambda _p: usage(total=1_000_000, used=999_000, free=1_000))

    with pytest.raises(OfflineRefused) as caught:
        service.prepare(ITEM)

    assert caught.value.status == 507
    assert "staging disk is full" in caught.value.message
    # ⚠ With the budget disabled the refusal can ONLY be the disk — which is what makes this test
    # evidence that the two checks are separate rather than one message wearing two hats.
    assert "RKM_OFFLINE_MAX_BYTES" not in caught.value.message


def test_the_cap_is_enforced_DURING_packaging_too(tmp_path, monkeypatch):
    """The pre-check uses an estimate; this is the guarantee behind it."""
    monkeypatch.setattr(offline_mod.urllib.request, "urlopen",
                        _Upstream(b"c" * 200_000))
    # No path reported ⇒ no estimate ⇒ nothing can be refused up front, so the only
    # thing that can stop the write is the in-flight ceiling.
    service = _service(tmp_path, library=_remuxable_library(path=""), cap=100_000)

    outcome = service.prepare(ITEM)

    assert outcome.manifest.state == FAILED
    assert "staging" in outcome.manifest.error
    assert not service.store.part_path(ITEM, "remux").exists()
    assert not service.store.artefact_path(ITEM, "remux").exists()


# --------------------------------------------------------------------------- 6. the TTL

def test_the_sweep_collects_expired_renditions_and_keeps_the_library_file(tmp_path):
    library_file = tmp_path / "Film.mp4"
    library_file.write_bytes(b"d" * 512)
    library = _Library(info={"container": "mp4", "video": {"codec": "h264"},
                             "audio": [{"codec": "aac"}], "subtitles": []},
                       detail={"name": "Film"}, path=str(library_file))
    service = _service(tmp_path, library=library, ttl=48)
    store = service.store

    # One BORROWED rendition and one PACKAGED one, both untouched for a week.
    borrowed = service.prepare(ITEM)                      # direct ⇒ borrows the file
    store.write(offline_mod.OfflineManifest(
        item_id="stale01", mode="remux", state=READY,
        path=str(store.artefact_path("stale01", "remux")), size=99,
        created_at=time.time() - 7 * 86400, last_access=time.time() - 7 * 86400))
    Path(store.artefact_path("stale01", "remux")).write_bytes(b"o" * 99)

    removed = store.sweep(ttl_seconds=store.ttl_seconds())

    assert any("stale01" in path for path in removed)
    assert not store.artefact_path("stale01", "remux").exists()
    assert service.status("stale01") is None
    assert library_file.exists(), "the sweep deleted the household's media file"
    assert borrowed.manifest.borrowed is True
    assert service.status(ITEM) is not None, "the FRESH rendition was swept too"


def test_a_ttl_of_zero_sweeps_nothing(tmp_path):
    service = _service(tmp_path, library=_remuxable_library(), ttl=0)
    store = service.store
    store.write(offline_mod.OfflineManifest(
        item_id="keepme", mode="remux", state=READY,
        path=str(store.artefact_path("keepme", "remux")), size=1,
        created_at=time.time() - 999 * 86400, last_access=time.time() - 999 * 86400))

    assert store.sweep(ttl_seconds=store.ttl_seconds()) == []
    assert service.status("keepme") is not None


# --------------------------------------------------------------------------- 7. paths

def test_a_hostile_item_id_cannot_escape_the_staging_directory(tmp_path):
    service = _service(tmp_path, library=_remuxable_library())
    store = service.store
    escaped = store.artefact_path("../../etc/passwd", "remux")

    assert escaped.parent == store.root
    assert ".." not in str(escaped)
    assert "/etc/" not in str(escaped)


def test_two_ids_that_sanitise_alike_do_not_collide(tmp_path):
    service = _service(tmp_path, library=_remuxable_library())
    store = service.store
    assert store.artefact_path("ab/../cd", "remux") != store.artefact_path("abcd", "remux")


# --------------------------------------------------------------------------- 8. over HTTP

def test_head_gives_the_size_and_range_gives_206_with_content_range(tmp_path, monkeypatch):
    """⚠ THE PHASE'S OWN GATE, driven over real HTTP against a real file."""
    service = _service(tmp_path, library=_remuxable_library())
    store = service.store
    staged = store.artefact_path(ITEM, "remux")
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(bytes(range(256)) * 8)          # 2048 bytes, known content
    store.write(offline_mod.OfflineManifest(
        item_id=ITEM, mode="remux", state=READY, path=str(staged), size=2048,
        created_at=time.time(), last_access=time.time()))
    _patch_offline(monkeypatch, service)
    body = bytes(range(256)) * 8

    head = client.head(f"/api/offline/file/{ITEM}")
    assert head.status_code == 200
    assert head.headers["content-length"] == "2048"
    assert head.headers["accept-ranges"] == "bytes"
    assert head.headers["etag"].startswith('"2048-')

    get = client.get(f"/api/offline/file/{ITEM}", headers={"Range": "bytes=100-199"})
    assert get.status_code == 206
    assert get.headers["content-range"] == "bytes 100-199/2048"
    assert get.headers["content-length"] == "100"
    assert get.content == body[100:200]

    whole = client.get(f"/api/offline/file/{ITEM}")
    assert whole.status_code == 200
    assert len(whole.content) == 2048
    assert whole.content == body


def test_an_impossible_range_is_416_with_the_current_length(tmp_path, monkeypatch):
    service = _service(tmp_path, library=_remuxable_library())
    store = service.store
    staged = store.artefact_path(ITEM, "remux")
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"x" * 100)
    store.write(offline_mod.OfflineManifest(
        item_id=ITEM, mode="remux", state=READY, path=str(staged), size=100,
        created_at=time.time(), last_access=time.time()))
    _patch_offline(monkeypatch, service)

    r = client.get(f"/api/offline/file/{ITEM}", headers={"Range": "bytes=500-"})

    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */100"


def test_nothing_staged_is_404_a_partial_is_409_and_a_vanished_file_is_410(
        tmp_path, monkeypatch):
    """⚠ Three different answers, because a downloader reacts differently to each.

    ``404`` = nothing was ever asked for. ``409`` = WAIT, it is being built (and the
    partial bytes on disk must NOT be served — a half-film that plays as if complete is
    the failure this whole phase is shaped to avoid). ``410`` = the rendition's file is
    gone from the server, which is not something waiting can fix.
    """
    service = _service(tmp_path, library=_remuxable_library())
    _patch_offline(monkeypatch, service)

    assert client.get(f"/api/offline/file/{ITEM}").status_code == 404
    assert client.head(f"/api/offline/file/{ITEM}").status_code == 404
    assert client.get(f"/api/offline/status/{ITEM}").status_code == 404
    assert client.delete(f"/api/offline/{ITEM}").status_code == 404

    # Still packaging, WITH real bytes on disk in the .part file.
    part = service.store.part_path(ITEM, "remux")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"HALF-A-FILM" * 100)
    service.store.write(offline_mod.OfflineManifest(
        item_id=ITEM, mode="remux", state=PACKAGING,
        path=str(service.store.artefact_path(ITEM, "remux")),
        created_at=time.time(), last_access=time.time()))
    packaging = client.get(f"/api/offline/file/{ITEM}")
    assert packaging.status_code == 409
    assert b"HALF-A-FILM" not in packaging.content
    assert client.head(f"/api/offline/file/{ITEM}").status_code == 409
    assert client.get(f"/api/offline/status/{ITEM}").json()["state"] == PACKAGING

    # The artefact the record points at has been removed underneath us.
    absent = service.store.artefact_path("gone01", "remux")
    service.store.write(offline_mod.OfflineManifest(
        item_id="gone01", mode="remux", state=READY, path=str(absent), size=50,
        created_at=time.time(), last_access=time.time()))
    gone = client.get("/api/offline/file/gone01")
    assert gone.status_code == 410
    assert "gone" in gone.json()["detail"]


def test_the_bundle_answers_before_anything_is_staged_and_then_reports_the_file(
        tmp_path, monkeypatch):
    """The page's "Download — 1080p · 2.1 GB · remux" button reads exactly this."""
    cheap = tmp_path / "Cheap.mkv"
    cheap.write_bytes(b"c" * 4321)
    service = _service(tmp_path, library=_remuxable_library(path=str(cheap)))
    _patch_offline(monkeypatch, service)

    before = client.get(f"/api/offline/bundle/{ITEM}").json()
    assert before["mode"] == "remux"
    assert before["needs_transcode"] is False
    assert before["estimate_bytes"] == 4321
    assert before["state"] == MISSING
    assert before["size"] == 0
    assert before["poster_url"].startswith("/api/jellyfin/poster?id=")
    assert before["subtitles"][0]["language"] == "eng"

    monkeypatch.setattr(offline_mod.urllib.request, "urlopen", _Upstream(b"k" * 4321))
    assert client.post("/api/offline/prepare", json={"item_id": ITEM}).status_code == 200
    after = client.get(f"/api/offline/bundle/{ITEM}").json()
    assert after["state"] == READY and after["size"] == 4321


def test_prepare_reports_the_work_it_did_and_the_cost_it_will_have(tmp_path, monkeypatch):
    monkeypatch.setattr(offline_mod.urllib.request, "urlopen", _Upstream(b"n" * 2048))
    service = _service(tmp_path, library=_remuxable_library())
    _patch_offline(monkeypatch, service)

    first = client.post("/api/offline/prepare", json={"item_id": ITEM}).json()
    second = client.post("/api/offline/prepare", json={"item_id": ITEM,
                                                       "mode": "auto"}).json()

    assert first["state"] == READY and first["started"] is True and first["reused"] is False
    assert first["mode"] == "remux" and first["needs_transcode"] is False
    assert first["size"] == first["bytes"] == 2048
    assert first["file_url"] == f"/api/offline/file/{ITEM}"
    assert second["reused"] is True and second["started"] is False


def test_prepare_without_an_item_id_is_a_400(tmp_path, monkeypatch):
    _patch_offline(monkeypatch, _service(tmp_path, library=_remuxable_library()))
    assert client.post("/api/offline/prepare", json={}).status_code == 400


def test_an_unknown_mode_is_refused_not_guessed(tmp_path, monkeypatch):
    _patch_offline(monkeypatch, _service(tmp_path, library=_remuxable_library()))
    r = client.post("/api/offline/prepare", json={"item_id": ITEM, "mode": "download-it"})
    assert r.status_code == 400
    assert "unknown mode" in r.json()["detail"]


def test_a_title_with_no_playback_information_is_a_404(tmp_path, monkeypatch):
    service = _service(tmp_path, library=_Library(info=None))
    _patch_offline(monkeypatch, service)
    assert client.post("/api/offline/prepare", json={"item_id": ITEM}).status_code == 404
    assert client.get(f"/api/offline/bundle/{ITEM}").status_code == 404


def test_a_direct_rendition_is_served_from_the_library_file(tmp_path, monkeypatch):
    """The direct path end to end: borrow, HEAD, Range — and the library file stays."""
    library_file = tmp_path / "Film.mp4"
    library_file.write_bytes(b"h" * 3000)
    library = _Library(info={"container": "mp4", "video": {"codec": "h264"},
                             "audio": [{"codec": "aac"}], "subtitles": []},
                       detail={"name": "Film", "runtime": 60.0}, path=str(library_file))
    service = _service(tmp_path, library=library)
    _patch_offline(monkeypatch, service)

    prepared = client.post("/api/offline/prepare", json={"item_id": ITEM}).json()
    head = client.head(f"/api/offline/file/{ITEM}")
    part = client.get(f"/api/offline/file/{ITEM}", headers={"Range": "bytes=-10"})
    deleted = client.delete(f"/api/offline/{ITEM}").json()

    assert prepared["borrowed"] is True and prepared["mode"] == "direct"
    assert head.status_code == 200 and head.headers["content-length"] == "3000"
    assert part.status_code == 206 and part.headers["content-range"] == "bytes 2990-2999/3000"
    assert part.content == b"h" * 10
    assert deleted["removed_file"] is False
    assert library_file.exists()


def test_the_staging_directory_holding_the_renditions_is_never_inside_a_media_root():
    """A regression pin for ADR-0007 D1 — a D:\\RKM_MEDIA staging dir would be scanned."""
    assert not offline_mod.STAGING_DEFAULT.startswith(("/media", "/data/rkm/media"))
    assert offline_mod.STAGING_DEFAULT == "/shared/offline"
