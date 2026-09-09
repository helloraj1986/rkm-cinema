"""API tests for the configurable media-libraries endpoints (MEDIA_LIBRARIES_PLAN Phase 3).

Mock at the service boundary (house style — no live LAN): patch
``api.routes.library.build_library_service`` with a fake service exposing
``library_folders()`` / ``items_in_folder()``, and patch the config singleton
the route reads for ``media_libraries`` / ``media_library_warnings``.
"""
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import api.main

FOLDERS = [
    {"id": "f137a2dd21bbc1b99aa5c0f6bf02a805", "name": "Movies",
     "collection_type": "movies", "path": "/data/media/_movie",
     "locations": ["/data/media/_movie"]},
    {"id": "767bffe4f11c93ef34b805451a696a4e", "name": "TV Shows",
     "collection_type": "tvshows", "path": "/data/media/_tv",
     "locations": ["/data/media/_tv"]},
]

ITEMS = [
    {"item_id": "m1", "type": "movie", "title": "M1", "year": 2020,
     "thumb": "", "jellyfin_url": "", "played": False},
    {"item_id": "s1", "type": "tv", "title": "S1", "year": 2021,
     "thumb": "", "jellyfin_url": "", "played": True},
]


def _fake_service():
    svc = SimpleNamespace(
        providers=[SimpleNamespace(name="jellyfin", health=lambda: True)],
        library_folders=lambda: {"provider": "jellyfin", "folders": FOLDERS},
        items_in_folder=lambda fid: {"provider": "jellyfin", "folder_id": fid, "items": ITEMS},
    )
    return svc


def _cfg(media_libraries=(), warnings=()):
    return SimpleNamespace(media_libraries=list(media_libraries),
                           media_library_warnings=list(warnings))


def test_folders_returns_configured_names_not_keys():
    """Configured libs resolve to server folders; env keys never leak as names."""
    from config.media_libraries import MediaLibrary
    cfg = _cfg(media_libraries=[
        MediaLibrary(name="Movies", path="/data/media/_movie"),
        MediaLibrary(name="My Anime", path="F:/Media/Anime"),
    ])
    with patch("api.routes.library.build_library_service", return_value=_fake_service()), \
         patch("api.routes.library.get_config", return_value=cfg):
        client = TestClient(api.main.app)
        r = client.get("/api/library/folders")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "jellyfin"
    assert len(body["folders"]) == 2
    libs = body["libraries"]
    assert [l["name"] for l in libs] == ["Movies", "My Anime"]
    assert all("MEDIA_LIBRARY" not in l["name"] for l in libs)
    movies = libs[0]
    assert movies["ok"] is True
    assert movies["folder_id"] == "f137a2dd21bbc1b99aa5c0f6bf02a805"
    anime = libs[1]
    assert anime["ok"] is False
    assert anime["folder_id"] is None
    assert "does not match" in anime["warning"]


def test_folders_without_config_falls_back_to_server_folder_names():
    """No MEDIA_LIBRARY_N_* → the sidebar shows the server's own folders."""
    cfg = _cfg(media_libraries=[])
    with patch("api.routes.library.build_library_service", return_value=_fake_service()), \
         patch("api.routes.library.get_config", return_value=cfg):
        client = TestClient(api.main.app)
        r = client.get("/api/library/folders")
    assert r.status_code == 200
    libs = r.json()["libraries"]
    assert [l["name"] for l in libs] == ["Movies", "TV Shows"]
    assert all(l["ok"] for l in libs)


def test_folders_surfaces_config_warnings():
    cfg = _cfg(media_libraries=(), warnings=["MEDIA_LIBRARY_2: PATH is empty — library skipped"])
    with patch("api.routes.library.build_library_service", return_value=_fake_service()), \
         patch("api.routes.library.get_config", return_value=cfg):
        client = TestClient(api.main.app)
        body = client.get("/api/library/folders").json()
    assert any("PATH is empty" in w for w in body["warnings"])


def test_folders_degrade_when_service_missing():
    cfg = _cfg(media_libraries=[])
    with patch("api.routes.library.build_library_service", return_value=None), \
         patch("api.routes.library.get_config", return_value=cfg):
        client = TestClient(api.main.app)
        body = client.get("/api/library/folders").json()
    assert body["provider"] is None
    assert body["folders"] == []
    assert body["libraries"] == []


def test_folder_items_returns_folder_scoped_poster_wall():
    cfg = _cfg(media_libraries=[])
    with patch("api.routes.library.build_library_service", return_value=_fake_service()), \
         patch("api.routes.library.get_config", return_value=cfg):
        client = TestClient(api.main.app)
        r = client.get("/api/library/folders/f137a2dd21bbc1b99aa5c0f6bf02a805/items")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "jellyfin"
    assert body["folder_id"] == "f137a2dd21bbc1b99aa5c0f6bf02a805"
    assert len(body["items"]) == 2
    assert body["items"][0]["item_id"] == "m1"


def test_folder_items_empty_when_service_missing_or_failing():
    cfg = _cfg(media_libraries=[])
    with patch("api.routes.library.build_library_service", return_value=None), \
         patch("api.routes.library.get_config", return_value=cfg):
        client = TestClient(api.main.app)
        body = client.get("/api/library/folders/abc/items").json()
    assert body["provider"] is None
    assert body["items"] == []

    boom = SimpleNamespace(
        library_folders=lambda: {"provider": "jellyfin", "folders": FOLDERS},
        items_in_folder=lambda fid: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with patch("api.routes.library.build_library_service", return_value=boom), \
         patch("api.routes.library.get_config", return_value=cfg):
        client = TestClient(api.main.app)
        body = client.get("/api/library/folders/abc/items").json()
    assert body["provider"] is None
    assert body["items"] == []
