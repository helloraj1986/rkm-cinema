"""Tests for the same-origin HLS proxy (docs/HLS_PLAYER_PLAN.md Phase 1).

Covers:
- ``GET /api/jellyfin/hls/{item_id}/master.m3u8`` — builds the upstream Jellyfin
  master URL from the mode ladder (remux / transcode_audio / transcode),
  forwards audio index + bitrate, and rewrites the playlist so NO ``api_key``
  leaks to the browser (Phase 0: Jellyfin embeds the token in every URI).
- The media-playlist/segment passthrough route (``/{rest:path}``) — playlist
  bodies re-stripped of api_key; segment bytes stream through with MIME/Range
  headers; client-supplied api_key is dropped, server's added.
- 503 when Jellyfin is not configured; 400 for an unknown/non-HLS mode.

All mocked at the network/config boundary — no real LAN, no API keys.
"""
from types import SimpleNamespace
from unittest.mock import patch
import json
import urllib.parse

from fastapi.testclient import TestClient
import api.main

client = TestClient(api.main.app)

_MASTER_BODY = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=256000,AVERAGE-BANDWIDTH=256000,VIDEO-RANGE=SDR,CODECS="avc1.4D4028,mp4a.40.2",RESOLUTION=1920x1080,FRAME-RATE=23.976
main.m3u8?api_key=sekret&MediaSourceId=ep1&VideoCodec=copy&AudioCodec=aac&MaxAudioChannels=2
"""

_MEDIA_BODY = """#EXTM3U
#EXT-X-PLAYLIST-TYPE:VOD
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:7
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:6.006000, nodesc
hls1/main/0.ts?api_key=sekret&MediaSourceId=ep1&VideoCodec=copy&AudioCodec=aac&runtimeTicks=0&actualSegmentLengthTicks=60060000
#EXTINF:6.006000, nodesc
hls1/main/1.ts?api_key=sekret&MediaSourceId=ep1&VideoCodec=copy&AudioCodec=aac&runtimeTicks=60060000&actualSegmentLengthTicks=60060000
#EXT-X-ENDLIST
"""


class _FakeHeaders:
    def __init__(self, d):
        self._d = d

    def get(self, name, default=None):
        return self._d.get(name, default)


class _FakeResponse:
    """Mimic urllib's HTTPResponse: seeded body + status + headers."""

    def __init__(self, body: bytes | str, status=200, headers=None):
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")
        self._pos = 0
        self.status = status
        self.headers = _FakeHeaders(headers or {"Content-Type": "application/vnd.apple.mpegurl"})

    def read(self, n=-1):
        if self._pos >= len(self._body):
            return b""
        chunk = self._body[self._pos:self._pos + (n if n and n > 0 else len(self._body))]
        self._pos += len(chunk)
        return chunk

    def close(self):
        pass


def _cfg(**over):
    defaults = {
        "JELLYFIN_URL": "http://jellyfin:8096",
        "JELLYFIN_API_KEY": "sekret",
        "JELLYFIN_BROWSER_URL": "",
    }
    defaults.update(over)
    return SimpleNamespace(**defaults)


def _patch_config(monkeypatch, **over):
    fake = _cfg(**over)
    import api.routes.jellyfin_hls as route_mod
    monkeypatch.setattr(route_mod, "get_config", lambda: fake)
    return fake


def _patch_urlopen(fake_urlopen):
    return patch("api.routes.jellyfin_hls.urllib.request.urlopen", fake_urlopen)


# ------------------------------------------------------------- master route
def test_hls_master_builds_remux_url_and_strips_api_key(monkeypatch):
    """mode=remux → copy/copy master; the rewritten body never leaks api_key."""
    _patch_config(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        # Jellyfin echoes the requested codec params back in the variant URI.
        q = urllib.parse.parse_qs(req.full_url.split("?", 1)[1])
        codec = f"{q['VideoCodec'][0]}&AudioCodec={q['AudioCodec'][0]}"
        body = _MASTER_BODY.replace(
            "main.m3u8?api_key=sekret&MediaSourceId=ep1&VideoCodec=copy&AudioCodec=aac&MaxAudioChannels=2",
            f"main.m3u8?api_key=sekret&MediaSourceId=ep1&VideoCodec={codec}")
        return _FakeResponse(body)

    with _patch_urlopen(fake_urlopen):
        r = client.get("/api/jellyfin/hls/ep1/master.m3u8", params={"mode": "remux"})

    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/vnd.apple.mpegurl")
    u = captured["url"]
    assert u.startswith("http://jellyfin:8096/Videos/ep1/master.m3u8?")
    assert "api_key=sekret" in u
    assert "MediaSourceId=ep1" in u
    assert "VideoCodec=copy" in u and "AudioCodec=copy" in u
    # Playlist body: api_key stripped everywhere, codec params preserved.
    assert "api_key=sekret" not in r.text
    assert "main.m3u8?MediaSourceId=ep1&VideoCodec=copy&AudioCodec=copy" in r.text


def test_hls_master_transcode_audio_maps_copy_aac(monkeypatch):
    """EAC3/AC3/DTS/TrueHD titles must use copy+aac (not copy-copy: Phase 0)."""
    _patch_config(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(_MASTER_BODY)

    with _patch_urlopen(fake_urlopen):
        client.get("/api/jellyfin/hls/ep1/master.m3u8", params={"mode": "transcode_audio"})
    u = captured["url"]
    assert "VideoCodec=copy" in u
    assert "AudioCodec=aac" in u and "MaxAudioChannels=2" in u
    assert "MaxStreamingBitrate" not in u  # 0 bitrate = unthrottled


def test_hls_master_transcode_with_bitrate_and_audio_index(monkeypatch):
    """mode=transcode + max_bitrate + audio index → h264/aac upstream URL."""
    _patch_config(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(_MASTER_BODY)

    with _patch_urlopen(fake_urlopen):
        client.get("/api/jellyfin/hls/ep1/master.m3u8",
                   params={"mode": "transcode", "max_bitrate": 5_000_000,
                           "audio_stream_index": 2})
    u = captured["url"]
    assert "VideoCodec=h264" in u
    assert "AudioCodec=aac" in u and "MaxAudioChannels=2" in u
    assert "MaxStreamingBitrate=5000000" in u
    assert "AudioStreamIndex=2" in u


def test_hls_master_legacy_transcode_audio_flag(monkeypatch):
    """Legacy transcode_audio=true (no mode) → mode=transcode_audio."""
    _patch_config(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(_MASTER_BODY)

    with _patch_urlopen(fake_urlopen):
        client.get("/api/jellyfin/hls/ep1/master.m3u8", params={"transcode_audio": True})
    u = captured["url"]
    assert "VideoCodec=copy" in u and "AudioCodec=aac" in u


def test_hls_master_default_mode_is_transcode(monkeypatch):
    """No mode → browser-safe default (h264+aac); never silently direct."""
    _patch_config(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(_MASTER_BODY)

    with _patch_urlopen(fake_urlopen):
        client.get("/api/jellyfin/hls/ep1/master.m3u8")
    assert "VideoCodec=h264" in captured["url"] and "AudioCodec=aac" in captured["url"]


def test_hls_master_rejects_unknown_and_direct_modes(monkeypatch):
    _patch_config(monkeypatch)
    with patch("api.routes.jellyfin_hls.urllib.request.urlopen") as m:
        r = client.get("/api/jellyfin/hls/ep1/master.m3u8", params={"mode": "bogus"})
    m.assert_not_called()
    assert r.status_code == 400

    with patch("api.routes.jellyfin_hls.urllib.request.urlopen") as m2:
        r2 = client.get("/api/jellyfin/hls/ep1/master.m3u8", params={"mode": "direct"})
    m2.assert_not_called()
    assert r2.status_code == 400


def test_hls_503_when_not_configured(monkeypatch):
    _patch_config(monkeypatch, JELLYFIN_URL="", JELLYFIN_API_KEY="")
    with patch("api.routes.jellyfin_hls.urllib.request.urlopen") as m:
        r = client.get("/api/jellyfin/hls/ep1/master.m3u8")
    m.assert_not_called()
    assert r.status_code == 503


# ------------------------------------------------------- passthrough routes
def test_hls_media_playlist_passthrough_strips_api_key(monkeypatch):
    """main.m3u8 (referenced by the master) is served with api_key stripped."""
    _patch_config(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(_MEDIA_BODY)

    with _patch_urlopen(fake_urlopen):
        r = client.get("/api/jellyfin/hls/ep1/main.m3u8",
                       params={"MediaSourceId": "ep1", "VideoCodec": "copy",
                               "AudioCodec": "aac"})

    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/vnd.apple.mpegurl")
    assert "api_key=sekret" not in r.text
    assert "hls1/main/0.ts?MediaSourceId=ep1" in r.text
    assert "runtimeTicks=0" in r.text and "actualSegmentLengthTicks=60060000" in r.text
    assert "VideoCodec=copy" in r.text
    # Server api_key re-injected upstream; client query forwarded verbatim.
    assert "api_key=sekret" in captured["url"]
    assert "MediaSourceId=ep1" in captured["url"]
    assert "VideoCodec=copy" in captured["url"]


def test_hls_segment_passthrough_binary_and_range(monkeypatch):
    """A .ts segment streams through with MIME + Range headers (206)."""
    _patch_config(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["range"] = req.get_header("Range")
        return _FakeResponse(body=b"\x47TSBYTES", status=206,
                             headers={"Content-Type": "video/mp2t",
                                      "Accept-Ranges": "bytes",
                                      "Content-Range": "bytes 0-7/4829156"})

    with _patch_urlopen(fake_urlopen):
        r = client.get("/api/jellyfin/hls/ep1/hls1/main/0.ts",
                       params={"MediaSourceId": "ep1", "runtimeTicks": "0",
                               "actualSegmentLengthTicks": "60060000"},
                       headers={"Range": "bytes=0-7"})

    assert r.status_code == 206
    assert r.headers["Content-Type"] == "video/mp2t"
    assert r.headers["Accept-Ranges"] == "bytes"
    assert r.headers["Content-Range"] == "bytes 0-7/4829156"
    assert r.content == b"\x47TSBYTES"
    assert captured["range"] == "bytes=0-7"
    # Query forwarded with the server token.
    assert "api_key=sekret" in captured["url"]
    assert "runtimeTicks=0" in captured["url"]


def test_hls_passthrough_drops_client_supplied_api_key(monkeypatch):
    """Defence in depth: a client-supplied api_key is never forwarded."""
    _patch_config(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(_MEDIA_BODY)

    with _patch_urlopen(fake_urlopen):
        client.get("/api/jellyfin/hls/ep1/main.m3u8",
                   params={"MediaSourceId": "ep1", "api_key": "evil-client-token"})

    assert "api_key=evil-client-token" not in captured["url"]
    assert "api_key=sekret" in captured["url"]
