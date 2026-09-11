"""Artwork caching (2026-09-10): posters must be cacheable, and revalidation cheap.

Regression context: ``/api/jellyfin/poster`` went out with NO cache policy and
nginx stamped every ``/api/`` response ``no-store``, so the browser re-downloaded
every poster on every navigation (~13 MB for a 140-title folder). These tests pin
the api half of the fix; ``nginx/default.conf`` carries the other half (artwork
path opted out of the blanket no-store).

Mocked at the config/service boundary — no Jellyfin, no network.
"""
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.main
from api.routes.jellyfin_poster import ARTWORK_CACHE_CONTROL

client = TestClient(api.main.app)

JPEG = b"\xff\xd8\xff\xe0jpeg-bytes"
LAST_MODIFIED = "Thu, 10 Sep 2026 01:39:37 GMT"


def _cfg(**over):
    vals = {"JELLYFIN_URL": "http://jellyfin:8096", "JELLYFIN_API_KEY": "sekret"}
    vals.update(over)
    return SimpleNamespace(**vals)


def _poster_get(result, path="/api/jellyfin/poster?id=m1&width=500", **kw):
    """GET the poster route with the service stubbed to return ``result``."""
    import api.routes.jellyfin_poster as pmod
    monkeypatch_cfg = kw.pop("cfg", _cfg())
    with patch.object(pmod, "get_config", lambda: monkeypatch_cfg), \
            patch.object(pmod, "build_library_service",
                         return_value=SimpleNamespace(get_poster=lambda *a, **k: result)):
        return client.get(path, **kw)


def test_poster_is_cacheable_not_no_store():
    """The whole bug in one assertion: posters must not be no-store."""
    r = _poster_get({"content": JPEG, "content_type": "image/jpeg"})
    assert r.status_code == 200
    assert r.content == JPEG
    assert r.headers["cache-control"] == ARTWORK_CACHE_CONTROL
    assert "no-store" not in r.headers["cache-control"]
    assert "max-age=604800" in r.headers["cache-control"]


def test_upstream_validators_are_forwarded():
    """Jellyfin already sends Last-Modified/ETag — the proxy must pass them on."""
    r = _poster_get({"content": JPEG, "content_type": "image/jpeg",
                     "etag": '"abc123"', "last_modified": LAST_MODIFIED})
    assert r.headers["etag"] == '"abc123"'
    assert r.headers["last-modified"] == LAST_MODIFIED


def test_matching_last_modified_revalidates_to_304_without_bytes():
    r = _poster_get({"content": JPEG, "content_type": "image/jpeg",
                     "last_modified": LAST_MODIFIED},
                    headers={"If-Modified-Since": LAST_MODIFIED})
    assert r.status_code == 304
    assert r.content == b""
    assert r.headers["cache-control"] == ARTWORK_CACHE_CONTROL


def test_stale_last_modified_still_returns_the_image():
    r = _poster_get({"content": JPEG, "content_type": "image/jpeg",
                     "last_modified": LAST_MODIFIED},
                    headers={"If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT"})
    assert r.status_code == 200
    assert r.content == JPEG


def test_matching_etag_revalidates_to_304():
    r = _poster_get({"content": JPEG, "content_type": "image/jpeg", "etag": 'W/"abc123"'},
                    headers={"If-None-Match": 'W/"abc123"'})
    assert r.status_code == 304


def test_etag_list_and_plain_etag_both_match():
    """Browsers may send a list of tags, and weak tags lose their W/ prefix."""
    for sent in ('"other", "abc123"', '"abc123"', 'abc123'):
        r = _poster_get({"content": JPEG, "content_type": "image/jpeg", "etag": '"abc123"'},
                        headers={"If-None-Match": sent})
        assert r.status_code == 304, sent


def test_missing_id_is_404_and_never_cached():
    r = _poster_get(None, path="/api/jellyfin/poster?id=&width=500")
    assert r.status_code == 404
    assert "cache-control" not in r.headers


def test_provider_failure_is_404_and_never_cached():
    """Artwork that is missing now may appear later — the browser must retry."""
    r = _poster_get(None)
    assert r.status_code == 404
    assert "cache-control" not in r.headers


def test_backdrop_route_is_cacheable_too():
    r = _poster_get({"content": JPEG, "content_type": "image/jpeg"},
                    path="/api/jellyfin/backdrop?id=m1&width=1600")
    assert r.status_code == 200
    assert r.headers["cache-control"] == ARTWORK_CACHE_CONTROL


def test_person_route_is_cacheable_too():
    r = _poster_get({"content": JPEG, "content_type": "image/jpeg"},
                    path="/api/jellyfin/person?id=p1&width=300")
    assert r.status_code == 200
    assert r.headers["cache-control"] == ARTWORK_CACHE_CONTROL


def test_dynamic_api_json_stays_uncacheable_in_the_api_layer():
    """The library JSON is dynamic state; only artwork is cacheable."""
    r = client.get("/api/health")
    assert "no-store" not in r.headers.get("cache-control", "")
