"""Tests for the Jellyfin library provider + the MEDIA_SERVER factory.

Mocks at the provider boundary (urllib.urlopen via patch) — no live server.
Verifies: stable provider-id matching, title fallback, watch-link/detail URL
shape, per-backend selection in build_library_service, and the runtime-config
loader (chicken-and-egg: provisioner writes /shared/runtime.json).
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from domain.identity import MediaIdentity
from domain.enums import MediaType
from config.settings import Config


def _cfg(**over):
    vals = dict(
        JELLYFIN_URL="http://jellyfin:8096",
        JELLYFIN_API_KEY="jkey",
        JELLYFIN_BROWSER_URL="http://localhost:8098",
        MEDIA_SERVER="jellyfin",
        PLEX_URL="", PLEX_TOKEN="", EMBY_URL="", EMBY_API_KEY="",
    )
    vals.update(over)
    cfg = SimpleNamespace(**vals)
    cfg.has_jellyfin = lambda: bool(cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY)
    cfg.has_emby = lambda: bool(cfg.EMBY_URL and cfg.EMBY_API_KEY)
    return cfg


class _FakeJson:
    def __init__(self, payload):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._p).encode()


def _mock_users_and_items(items):
    """urlopen -> /Users first (user list), then /Users/{id}/Items (items)."""
    def side_effect(url, *args, **kwargs):
        u = url if isinstance(url, str) else getattr(url, "full_url", "")
        if "/System/Info/Public" in u:
            return _FakeJson({"Id": "srv-abc", "ServerName": "rkm-jf", "Version": "10.10"})
        if u.endswith("/Users?api_key=jkey"):
            return _FakeJson([{"Id": "user-1", "Name": "admin"}])
        return _FakeJson({"Items": items})
    return side_effect


def _make_provider(side_effect=None):
    from services.library.jellyfin import JellyfinLibraryProvider
    with patch("urllib.request.urlopen", side_effect=side_effect or _mock_users_and_items([])):
        return JellyfinLibraryProvider(config=_cfg())


def test_jellyfin_match_by_imdb_id_and_watch_link():
    from services.library.jellyfin import JellyfinLibraryProvider
    items = [{
        "Id": "itm-1", "Name": "Prisoners", "ProductionYear": 2013,
        "ProviderIds": {"Imdb": "tt1392214", "Tmdb": 146233},
        "Thumb": "http://x/thumb.jpg",
    }]
    side = _mock_users_and_items(items)
    with patch("urllib.request.urlopen", side_effect=side):
        p = JellyfinLibraryProvider(config=_cfg())
        ident = MediaIdentity(media_type=MediaType.MOVIE, imdb_id="tt1392214")
        m = p.find(ident, title="Prisoners", year=2013)
    assert m is not None
    assert m.provider == "jellyfin"
    assert m.provider_item_id == "itm-1"
    assert m.metadata["server_id"] == "srv-abc"
    link = p.build_watch_link(m)
    # Jellyfin web 10.10+ uses `#/details` (no `#!/` hashbang).
    assert link["jellyfin_url"].startswith("http://localhost:8098/web/index.html#/details?id=itm-1")
    assert "serverId=srv-abc" in link["jellyfin_url"]


def test_jellyfin_absent_returns_none():
    from services.library.jellyfin import JellyfinLibraryProvider
    side = _mock_users_and_items([])  # empty library
    with patch("urllib.request.urlopen", side_effect=side):
        p = JellyfinLibraryProvider(config=_cfg())
        ident = MediaIdentity(media_type=MediaType.MOVIE, imdb_id="tt9999999")
        assert p.find(ident, title="Nobody", year=2021) is None


def test_jellyfin_not_configured_is_absent():
    from services.library.jellyfin import JellyfinLibraryProvider
    p = JellyfinLibraryProvider(config=_cfg(JELLYFIN_API_KEY=""))
    ident = MediaIdentity(media_type=MediaType.MOVIE, imdb_id="tt1")
    assert p.find(ident, title="X", year=1999) is None


def test_factory_selects_jellyfin_when_configured():
    from services.library.factory import build_library_service
    svc = build_library_service(_cfg(MEDIA_SERVER="jellyfin", JELLYFIN_API_KEY="jkey"))
    assert svc is not None and len(svc.providers) == 1
    assert svc.providers[0].name == "jellyfin"


def test_factory_jellyfin_not_configured_returns_none():
    from services.library.factory import build_library_service
    assert build_library_service(_cfg(MEDIA_SERVER="jellyfin", JELLYFIN_API_KEY="")) is None


def test_factory_default_is_plex_emby_when_no_media_server():
    from services.library.factory import build_library_service
    cfg = SimpleNamespace(MEDIA_SERVER="", PLEX_URL="http://p:32400", PLEX_TOKEN="pt",
                          EMBY_URL="http://e:8096", EMBY_API_KEY="ek")
    svc = build_library_service(cfg)
    assert [p.name for p in svc.providers] == ["plex", "emby"]


def test_runtime_loader_merges_runtime_json(monkeypatch, tmp_path):
    """The provisioner-written runtime.json supplies JELLYFIN_API_KEY post-boot."""
    runtime = {"JELLYFIN_API_KEY": "rt-key", "MEDIA_SERVER": "jellyfin"}
    rt = tmp_path / "runtime.json"
    rt.write_text(json.dumps(runtime), encoding="utf-8")
    monkeypatch.setenv("RKM_RUNTIME_PATH", str(rt))
    cfg = Config()
    assert cfg.JELLYFIN_API_KEY == "rt-key"
    assert cfg.MEDIA_SERVER == "jellyfin"

def test_recently_added_carries_playback_facts():
    """recently_added() exposes UserData playback facts (seconds) for the UI."""
    from services.library.jellyfin import JellyfinItem, JellyfinLibraryProvider
    prov = JellyfinLibraryProvider(config=_cfg())

    # Seed a partially-watched movie and a fully-watched one.
    prov._get_items = lambda itype: {
        "Movie": [
            JellyfinItem(name="Half Seen", year=2001, id="m1",
                         played=False, position_ticks=30_000_000_000,  # 3000s
                         runtime_ticks=100_000_000_000),              # 10000s
            JellyfinItem(name="Done Film", year=2002, id="m2",
                         played=True, position_ticks=0,
                         runtime_ticks=90_000_000_000),
        ],
        "Series": [],
    }[itype]
    prov._item_web = lambda iid: "http://jf/x#/details?id=" + iid

    recent = prov.recently_added(limit=8)
    by_title = {x["title"]: x for x in recent}
    assert by_title["Half Seen"]["playback_position"] == 3000   # ticks/1e7
    assert by_title["Half Seen"]["runtime"] == 10000
    assert by_title["Half Seen"]["played"] is False
    assert by_title["Done Film"]["played"] is True


def test_watch_link_emits_playback_facts():
    """A Jellyfin match's playback facts flow into WatchLink.to_dict()."""
    from services.library.jellyfin import JellyfinItem, JellyfinLibraryProvider
    from services.library.service import LibraryService
    from services.library.watch_links import WatchLinkResolver

    prov = JellyfinLibraryProvider(config=_cfg())
    prov._server_id = lambda: "srv"
    prov._browser_base = lambda: "http://localhost:8098/web/index.html"

    item = JellyfinItem(name="Half Seen", year=2001, id="m1",
                        played=False, position_ticks=30_000_000_000,
                        runtime_ticks=100_000_000_000)
    match = prov._match_from(item)
    svc = LibraryService(providers=[prov])
    watch = WatchLinkResolver(svc).resolve(match)
    jf = watch["jellyfin"]
    assert jf["available"] is True
    assert jf["item_id"] == "m1"
    assert jf["played"] is False
    assert jf["playback_position"] == 3000
    assert jf["runtime"] == 10000


def test_all_items_lists_entire_library():
    """all_items() returns every movie + series with playback facts."""
    from services.library.jellyfin import JellyfinItem, JellyfinLibraryProvider
    prov = JellyfinLibraryProvider(config=_cfg())
    prov._get_items = lambda itype: {
        "Movie": [JellyfinItem(name="M1", year=2001, id="m1",
                               played=False, position_ticks=0, runtime_ticks=60_000_000_000)],
        "Series": [JellyfinItem(name="S1", year=2002, id="s1",
                                is_series=True, played=True, position_ticks=0, runtime_ticks=0)],
    }[itype]
    prov._item_web = lambda iid: "http://jf/x#/details?id=" + iid

    items = prov.all_items()
    by_id = {x["item_id"]: x for x in items}
    assert set(by_id) == {"m1", "s1"}
    assert by_id["m1"]["runtime"] == 6000
    assert by_id["m1"]["playback_position"] == 0
    assert by_id["s1"]["played"] is True
    assert by_id["s1"]["type"] == "tv"


def test_continue_watching_filters_in_progress():
    """continue_watching() returns started-but-unfinished titles (position>0, not played)."""
    from services.library.jellyfin import JellyfinItem, JellyfinLibraryProvider
    prov = JellyfinLibraryProvider(config=_cfg())
    prov._get_items = lambda itype: {
        "Movie": [
            JellyfinItem(name="Half", year=2001, id="m1",
                         played=False, position_ticks=30_000_000_000, runtime_ticks=100_000_000_000),
            JellyfinItem(name="Done", year=2002, id="m2",
                         played=True, position_ticks=0, runtime_ticks=90_000_000_000),
            JellyfinItem(name="Fresh", year=2003, id="m3",
                         played=False, position_ticks=0, runtime_ticks=80_000_000_000),
        ],
        "Series": [],
    }[itype]
    prov._item_web = lambda iid: "http://jf/x#/details?id=" + iid

    items = prov.continue_watching(limit=12)
    assert [x["item_id"] for x in items] == ["m1"], [x["item_id"] for x in items]
    assert items[0]["playback_position"] == 3000


def test_episodes_lists_and_sorts_per_season():
    """episodes() lists a series' episodes ordered by (season, episode) w/ playback facts."""
    from services.library.jellyfin import JellyfinLibraryProvider
    prov = JellyfinLibraryProvider(config=_cfg())
    seen = {}

    def fake_user_id():
        return "u1"

    def fake_configured():
        return True

    def fake_fetch(url):
        seen["url"] = url
        return [
            {"Name": "S1E2", "Id": "e2", "ParentIndexNumber": 1, "IndexNumber": 2,
             "UserData": {"Played": False, "PlaybackPositionTicks": 0},
             "RunTimeTicks": 30_000_000_000},
            {"Name": "S1E1", "Id": "e1", "ParentIndexNumber": 1, "IndexNumber": 1,
             "UserData": {"Played": False, "PlaybackPositionTicks": 20_000_000_000},
             "RunTimeTicks": 40_000_000_000},
            {"Name": "S2E1", "Id": "e3", "ParentIndexNumber": 2, "IndexNumber": 1,
             "UserData": {"Played": True, "PlaybackPositionTicks": 0},
             "RunTimeTicks": 30_000_000_000},
        ]

    prov._user_id = fake_user_id
    prov._configured = fake_configured
    prov._fetch_raw = fake_fetch

    eps = prov.episodes("series1")
    assert [e["id"] for e in eps] == ["e1", "e2", "e3"], eps  # season then episode
    assert "ParentId=series1" in seen["url"]
    assert "IncludeItemTypes=Episode" in seen["url"]
    assert eps[0]["season"] == 1 and eps[0]["episode"] == 1
    assert eps[0]["playback_position"] == 2000   # 20s
    assert eps[0]["runtime"] == 4000
    assert eps[2]["played"] is True               # S2E1 watched
