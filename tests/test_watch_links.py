"""Regression tests for the Plex/Emby Watch deep-links.

Guards the fix where URLs must point at the local server's OWN web UI over the
browser-reachable Tailscale host (NOT app.plex.tv cloud), use the RAW
/library/metadata/<key> path (NOT %2F-encoded), and carry plexKey as the numeric
ratingKey (it was previously the full URL). Also verifies the URL is built from
the same cached library scan as ownership (no extra Plex rescans).
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.plex import PlexService


def _make_service(plex_browser_url="https://rkm-hp.tail8d5e8.ts.net:32400"):
    """Build a PlexService with a fake config + fake http via DI (no real LAN)."""
    cfg = SimpleNamespace(
        PLEX_URL="http://192.168.65.254:32400",
        PLEX_TOKEN="tok",
        PLEX_BROWSER_URL=plex_browser_url,
        EMBY_BROWSER_URL="https://rkm-hp.tail8d5e8.ts.net:8096",
        EMBY_URL="http://192.168.65.254:8096",
        EMBY_API_KEY="ek",
    )
    http = MagicMock()
    svc = PlexService(config=cfg, http=http)
    return svc, http


def _plex_scans(entries, machine_identifier="mid-abc123"):
    """Side-effect list: sections -> one movie section; content -> entries; identity."""
    return [
        {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
        {"MediaContainer": {"Metadata": entries}},
        {"MediaContainer": {"machineIdentifier": machine_identifier}},
    ]


class TestPlexWatchLinks:
    def test_plex_url_uses_browser_host_not_cloud(self):
        """Plex deep-link must hit the server's own web UI, NOT app.plex.tv."""
        svc, http = _make_service()
        http.get.side_effect = _plex_scans([
            {"title": "Mad Max: Fury Road", "year": 2015, "ratingKey": "320819", "type": "movie"}])
        url = svc.plex_url_for("Mad Max: Fury Road", 2015, False)
        assert "app.plex.tv" not in url
        assert url.startswith("https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html")
        # raw /library/metadata/<key> path, NOT %2F-encoded
        assert "/library/metadata/320819" in url
        assert "%2F" not in url
        assert "#!/server/mid-abc123/details?key=" in url

    def test_plex_key_is_numeric_rating_key(self):
        """plexKey must be the numeric ratingKey, not the full URL."""
        svc, http = _make_service()
        http.get.side_effect = [
            {"MediaContainer": {"Directory": [{"key": "2", "type": "show"}]}},
            {"MediaContainer": {"Metadata": [
                {"title": "The Bear", "year": 2022, "ratingKey": "888", "type": "show"}]}},
        ]
        key = svc.plex_key_for("The Bear", 2022, True)
        assert key == "888"
        assert key.isdigit()

    def test_plex_url_falls_back_to_search_when_no_rating_key(self):
        """If the item can't be found, fall back to a search link (no crash)."""
        svc, http = _make_service()
        http.get.side_effect = [
            {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
            {"MediaContainer": {"Metadata": []}},
            {"MediaContainer": {"machineIdentifier": "mid-abc123"}},
        ]
        url = svc.plex_url_for("Nonexistent Title 2099", 2099, False)
        assert "/web/search?query=" in url
        assert "Nonexistent%20Title" in url

    def test_plex_url_defaults_to_tailscale_when_no_browser_url(self):
        """Without PLEX_BROWSER_URL, still default to the Tailscale host (browser-reachable)."""
        svc, http = _make_service(plex_browser_url=None)
        http.get.side_effect = _plex_scans([
            {"title": "M", "year": 1999, "ratingKey": "7", "type": "movie"}])
        url = svc.plex_url_for("M", 1999, False)
        assert url.startswith("https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html")

    def test_plex_url_builds_from_cached_library(self):
        """plex_url_for reuses the cached library scan (no extra full rescans)."""
        svc, http = _make_service()
        # Only enough calls for ONE scan + identity. A second URL build must be
        # served entirely from cache (no additional http.get).
        http.get.side_effect = [
            {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
            {"MediaContainer": {"Metadata": [
                {"title": "Mad Max: Fury Road", "year": 2015, "ratingKey": "320819", "type": "movie"}]}},
            {"MediaContainer": {"machineIdentifier": "mid-abc123"}},
        ]
        svc.plex_url_for("Mad Max: Fury Road", 2015, False)
        svc.plex_url_for("Mad Max", 2015, False)  # 2nd -> fully cached
        assert http.get.call_count == 3  # sections + content + identity, nothing more


class TestEmbyWatchLinks:
    def test_emby_url_uses_browser_host_and_item_id(self):
        """Emby deep-link uses the browser-reachable host + item id + server id."""
        svc, http = _make_service()
        svc._emby_items_cache = {"the bear": "ITEM123"}
        svc._emby_sid = "SERVER456"
        url = svc.emby_url_for("The Bear")
        assert url.startswith("https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html")
        assert "#!/item?id=ITEM123&serverId=SERVER456" in url

    def test_emby_url_falls_back_to_search_without_ids(self):
        """Emby falls back to a search deep-link when no item/server id is known."""
        svc, http = _make_service()
        # Force item lookup to be empty (no real network).
        svc._emby_item_id = lambda title: ""
        svc._emby_server_id = lambda: ""
        url = svc.emby_url_for("Some Show")
        assert "#!/search?query=" in url


if __name__ == "__main__":
    pytest.main([__file__, "-v"])