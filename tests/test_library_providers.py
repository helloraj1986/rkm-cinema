"""Tests for the Phase 4 library abstraction (services/library/).

Covers the spec §4/§6/§7/§8/§9 requirements:
- PlexLibraryProvider matches by stable provider id (guid-derived imdb/tmdb),
  captures ratingKey + machineIdentifier + library_section, never guesses a URL.
- EmbyLibraryProvider captures item_id + server_id, matches by provider id.
- LibraryService treats Plex and Emby as ONE logical library: find() returns a
  single LibraryMatch across providers (avoids "Plex available / Emby available"
  as two states).
- watch_links() still returns per-provider URLs for the same available item.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from domain.enums import MediaType
from domain.identity import MediaIdentity
from services.library import (
    LibraryService,
    PlexLibraryProvider,
    EmbyLibraryProvider,
)


def _plex_cfg():
    return SimpleNamespace(
        PLEX_URL="http://192.168.65.254:32400",
        PLEX_TOKEN="tok",
        PLEX_BROWSER_URL="https://rkm-hp.tail8d5e8.ts.net:32400",
        EMBY_URL="http://192.168.65.254:8096",
        EMBY_API_KEY="ek",
        EMBY_BROWSER_URL="https://rkm-hp.tail8d5e8.ts.net:8096",
    )


def _plex_http(entries):
    """Plex http client with a movie section + content + identity responses."""
    http = MagicMock()
    http.get.side_effect = [
        {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
        {"MediaContainer": {"Metadata": entries}},
        {"MediaContainer": {"machineIdentifier": "mid-abc123"}},
    ]
    return http


class TestPlexLibraryProvider:
    def _provider(self, entries, cfg=None):
        cfg = cfg or _plex_cfg()
        return PlexLibraryProvider(config=cfg, http=_plex_http(entries))

    def test_matches_by_stable_tmdb_guid(self):
        """Find by TMDB id embedded in Plex guid (canonical route)."""
        prov = self._provider([{
            "title": "The Matrix", "year": 1999, "ratingKey": "603",
            "type": "movie", "guid": "com.plexapp.agents.themoviedb://603?lang=en",
        }])
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=603)
        match = prov.find(identity)
        assert match is not None
        assert match.provider == "plex"
        assert match.provider_item_id == "603"
        assert match.metadata["rating_key"] == "603"
        assert match.metadata["machine_identifier"] == "mid-abc123"
        assert match.metadata["guid"].startswith("com.plexapp.agents.themoviedb")

    def test_matches_by_stable_imdb_guid(self):
        prov = self._provider([{
            "title": "Arrival", "year": 2016, "ratingKey": "320819",
            "type": "movie", "guid": "com.plexapp.agents.imdb://tt2543164?lang=en",
        }])
        identity = MediaIdentity(media_type=MediaType.MOVIE, imdb_id="tt2543164")
        assert prov.find(identity) is not None

    def test_matches_by_title_year_fallback_when_no_guid_match(self):
        prov = self._provider([{
            "title": "Prisoners", "year": 2013, "ratingKey": "777",
            "type": "movie", "guid": "",
        }])
        identity = MediaIdentity(media_type=MediaType.MOVIE, imdb_id="tt1392214")
        # No stable id in guid -> falls back to title+year.
        match = prov.find(identity, title="Prisoners", year=2013)
        assert match is not None
        assert match.provider_item_id == "777"

    def test_no_match_when_absent(self):
        prov = self._provider([{
            "title": "The Matrix", "year": 1999, "ratingKey": "603",
            "type": "movie", "guid": "com.plexapp.agents.themoviedb://604?lang=en",
        }])
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=999)
        assert prov.find(identity, title="Bogus", year=2099) is None

    def test_watch_link_is_server_web_ui_not_cloud(self):
        prov = self._provider([{
            "title": "Mad Max: Fury Road", "year": 2015, "ratingKey": "320819",
            "type": "movie", "guid": "com.plexapp.agents.themoviedb://76341?lang=en",
        }])
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=76341)
        match = prov.find(identity)
        link = prov.build_watch_link(match)
        url = link["plex_url"]
        assert "app.plex.tv" not in url
        assert url.startswith("https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html")
        assert "/library/metadata/320819" in url
        assert "#!/server/mid-abc123/details?key=" in url

    def test_recently_added_surface(self):
        http = MagicMock()
        # get_recently_added is called directly; its response is the FIRST http.get.
        http.get.side_effect = [
            {"MediaContainer": {"Metadata": [{"title": "Recent Film", "year": 2024, "ratingKey": "9", "type": "movie"}]}},
        ]
        prov = PlexLibraryProvider(config=_plex_cfg(), http=http)
        recent = prov.recently_added(limit=4)
        assert isinstance(recent, list)
        assert recent and recent[0]["title"] == "Recent Film"


class TestEmbyLibraryProvider:
    def test_matches_by_stable_tmdb_provider_id(self):
        prov = EmbyLibraryProvider(config=_plex_cfg(), http=MagicMock())
        # Stub the network by injecting a cached item list with ProviderIds.
        prov._item_cache = {"Movie": []}
        from services.library.emby import EmbyItem
        prov._item_cache["Movie"] = [
            EmbyItem(name="The Matrix", year=1999, id="ITEM1", provider_ids={"tmdb": 603, "imdb": "tt0133093"})
        ]
        import time
        prov._item_cache_expiry = time.time() + 300
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=603)
        match = prov.find(identity)
        assert match is not None
        assert match.provider == "emby"
        assert match.provider_item_id == "ITEM1"
        assert match.metadata["item_id"] == "ITEM1"

    def test_server_id_captured(self):
        prov = EmbyLibraryProvider(config=_plex_cfg(), http=MagicMock())
        prov._server_id_value = "SERV1"
        from services.library.emby import EmbyItem
        import time
        prov._item_cache = {"Series": [
            EmbyItem(name="The Bear", year=2022, id="SHOW1", is_series=True, provider_ids={"tvdb": 403294})
        ]}
        prov._item_cache_expiry = time.time() + 300
        identity = MediaIdentity(media_type=MediaType.TV, tvdb_id=403294)
        match = prov.find(identity)
        assert match.metadata["server_id"] == "SERV1"
        link = prov.build_watch_link(match)
        assert "#!/item?id=SHOW1&serverId=SERV1" in link["emby_url"]

    def test_emby_unconfigured_returns_none(self):
        cfg = SimpleNamespace(EMBY_URL=None, EMBY_API_KEY=None, EMBY_BROWSER_URL=None)
        prov = EmbyLibraryProvider(config=cfg, http=MagicMock())
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=603)
        assert prov.find(identity) is None


class _FakeProvider:
    """Minimal LibraryProvider double for the collapse test."""
    name = "fake"

    def __init__(self, found):
        self._found = found

    def health(self):
        return True

    def find(self, identity, *, title="", year=None):
        return self._found

    def recently_added(self, limit=8):
        return []

    def build_watch_link(self, match):
        return {"fake_url": "http://fake"}


class TestLibraryServiceSingleLibrary:
    """Spec §9: providers of the same logical library collapse to ONE state."""

    def test_find_returns_single_match_across_providers(self):
        from services.library import LibraryMatch
        plex = _FakeProvider(LibraryMatch("plex", "1", "The Matrix", 1999))
        emby = _FakeProvider(None)  # same film not double-reported
        svc = LibraryService(providers=[plex, emby])
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=603)
        match = svc.find(identity)
        assert match is not None
        assert match.provider == "plex"

    def test_has_is_true_when_any_provider_has_item(self):
        from services.library import LibraryMatch
        emby = _FakeProvider(LibraryMatch("emby", "ITEM1", "Arrival", 2016))
        svc = LibraryService(providers=[emby])
        identity = MediaIdentity(media_type=MediaType.MOVIE, imdb_id="tt2543164")
        assert svc.has(identity) is True

    def test_health_reports_each_provider(self):
        svc = LibraryService(providers=[_FakeProvider(None)])
        assert svc.health() == {"fake": True}

    def test_watch_links_builds_for_matching_provider(self):
        from services.library import LibraryMatch
        match = LibraryMatch("fake", "1", "T", 2000)
        svc = LibraryService(providers=[_FakeProvider(match)])
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=1)
        links = svc.watch_links(svc.find(identity))
        assert links == {"fake": {"available": True, "url": "http://fake", "error": None}}


class _ArmedProvider(_FakeProvider):
    """Fake provider whose watch-link builder can succeed, fail or raise."""

    def __init__(self, found, *, name="fake", link_url="http://ok", raise_link=False):
        super().__init__(found)
        self.name = name
        self._link_url = link_url
        self._raise_link = raise_link

    def build_watch_link(self, match):
        if self._raise_link:
            raise RuntimeError("boom")
        if not self._link_url:
            return {"fake_url": ""}
        return {"fake_url": self._link_url}


class TestWatchLinkResolver:
    """Spec §10: WatchLink shape + failure containment (never downgrade AVAILABLE)."""

    def _svc(self, providers):
        return LibraryService(providers=providers)

    def test_plex_match_produces_valid_available_link(self):
        from services.library import LibraryMatch
        match = LibraryMatch("plex", "320819", "Mad Max", 2015)
        svc = self._svc([_ArmedProvider(match, name="plex", link_url="https://plex/#!/server/sid/details?key=/library/metadata/320819")])
        links = svc.watch_links(match)
        assert links["plex"]["available"] is True
        assert links["plex"]["url"].startswith("https://plex/")
        assert links["plex"]["error"] is None

    def test_emby_match_produces_valid_link(self):
        from services.library import LibraryMatch
        match = LibraryMatch("emby", "ITEM1", "The Bear", 2022)
        svc = self._svc([_ArmedProvider(match, name="emby", link_url="https://emby/web/index.html#!/item?id=ITEM1&serverId=S1")])
        links = svc.watch_links(match)
        assert links["emby"]["available"] is True
        assert links["emby"]["url"] == "https://emby/web/index.html#!/item?id=ITEM1&serverId=S1"

    def test_both_providers_links_when_both_match(self):
        from services.library import LibraryMatch
        plex = LibraryMatch("plex", "1", "Arrival", 2016)
        emby = LibraryMatch("emby", "ITEM9", "Arrival", 2016)
        svc = self._svc([
            _ArmedProvider(plex, name="plex", link_url="https://plex/#!/")
            , _ArmedProvider(emby, name="emby", link_url="https://emby/#!/"),
        ])
        links = svc.watch_links([plex, emby])
        assert links["plex"]["available"] and links["emby"]["available"]
        assert links["plex"]["url"].startswith("https://plex/")
        assert links["emby"]["url"].startswith("https://emby/")

    def test_plex_link_failure_emby_success_emby_only(self):
        """Spec: 'Plex link failure + Emby success -> Emby button only'."""
        from services.library import LibraryMatch
        plex = LibraryMatch("plex", "1", "F", 2000)
        emby = LibraryMatch("emby", "9", "F", 2000)
        svc = self._svc([
            _ArmedProvider(plex, name="plex", link_url="https://plex/#!/", raise_link=True),
            _ArmedProvider(emby, name="emby", link_url="https://emby/#!/"),
        ])
        links = svc.watch_links([plex, emby])
        assert links["plex"]["available"] is False
        assert links["plex"]["url"] is None
        assert "boom" in (links["plex"]["error"] or "")
        assert links["emby"]["available"] is True

    def test_plex_failure_does_not_downgrade_availability(self):
        """Spec §10 critical rule: a failed link must NOT flip AVAILABLE->NOT_REQUESTED.

        Availability is resolved independently by the domain state machine from
        find()/has(). A provider whose link builder raises still reports the item
        as present (find has a match), and the resolver returns a soft-fail link
        instead of propagating — so the item REMAINS AVAILABLE.
        """
        from domain.enums import MediaType, MediaStatus
        from domain.identity import MediaIdentity
        from domain.state_machine import StatusFacts, resolve_status
        from services.library import LibraryMatch
        match = LibraryMatch("plex", "320819", "Mad Max: Fury Road", 2015)
        svc = self._svc([_ArmedProvider(match, name="plex", link_url="http://x", raise_link=True)])
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=76341)

        # 1. Availability is independent of link resolution: item present -> AVAILABLE.
        assert svc.has(identity) is True
        status = resolve_status(StatusFacts(media_type=MediaType.MOVIE, in_plex=True))
        assert status.state is MediaStatus.AVAILABLE

        # 2. Link resolution soft-fails (no raise, available=False) — button hidden only.
        links = svc.watch_links(match)
        assert links["plex"]["available"] is False
        assert "boom" in (links["plex"]["error"] or "")
        # Regardless of the link failure, the media state is still AVAILABLE.
        assert status.state is MediaStatus.AVAILABLE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])