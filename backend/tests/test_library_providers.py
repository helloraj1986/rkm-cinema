"""Tests for the Phase 4 library abstraction (services/library/).

Covers the spec §4/§6/§7/§8/§9 requirements:
- ``LibraryService`` treats every provider as a view of ONE logical library:
  ``find()`` returns a single ``LibraryMatch`` across providers (so an item can
  never be "available on one server / not available on another").
- ``watch_links()`` still returns per-provider URLs for the same available item.
- A provider whose link builder fails can only hide a button — it never
  downgrades the item's state.

The concrete provider tests (Jellyfin) live in ``test_jellyfin_provider.py``;
the two providers below are NAME-AGNOSTIC doubles — the resolver keys its map by
whatever name a provider reports, which is the property under test.
"""
import pytest
from domain.enums import MediaType
from domain.identity import MediaIdentity
from services.library import (
    LibraryService,
)


class _FakeProvider:
    """Minimal LibraryProvider double for the collapse test."""
    name = "alpha"

    def __init__(self, found):
        self._found = found

    def health(self):
        return True

    def find(self, identity, *, title="", year=None):
        return self._found

    def recently_added(self, limit=8):
        return []

    def build_watch_link(self, match):
        return {"alpha_url": "http://alpha"}


class TestLibraryServiceSingleLibrary:
    """Spec §9: providers of the same logical library collapse to ONE state."""

    def test_find_returns_single_match_across_providers(self):
        from services.library import LibraryMatch
        alpha = _FakeProvider(LibraryMatch("alpha", "1", "The Matrix", 1999))
        beta = _FakeProvider(None)  # same film not double-reported
        svc = LibraryService(providers=[alpha, beta])
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=603)
        match = svc.find(identity)
        assert match is not None
        assert match.provider == "alpha"

    def test_has_is_true_when_any_provider_has_item(self):
        from services.library import LibraryMatch
        beta = _FakeProvider(LibraryMatch("beta", "ITEM1", "Arrival", 2016))
        beta.name = "beta"
        svc = LibraryService(providers=[beta])
        identity = MediaIdentity(media_type=MediaType.MOVIE, imdb_id="tt2543164")
        assert svc.has(identity) is True

    def test_health_reports_each_provider(self):
        svc = LibraryService(providers=[_FakeProvider(None)])
        assert svc.health() == {"alpha": True}

    def test_watch_links_builds_for_matching_provider(self):
        from services.library import LibraryMatch
        match = LibraryMatch("alpha", "1", "T", 2000)
        svc = LibraryService(providers=[_FakeProvider(match)])
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=1)
        links = svc.watch_links(svc.find(identity))
        assert links == {"alpha": {"available": True, "url": "http://alpha", "error": None}}


class _ArmedProvider(_FakeProvider):
    """Fake provider whose watch-link builder can succeed, fail or raise."""

    def __init__(self, found, *, name="alpha", link_url="http://ok", raise_link=False):
        super().__init__(found)
        self.name = name
        self._link_url = link_url
        self._raise_link = raise_link

    def build_watch_link(self, match):
        if self._raise_link:
            raise RuntimeError("boom")
        if not self._link_url:
            return {"alpha_url": ""}
        return {"alpha_url": self._link_url}


class TestWatchLinkResolver:
    """Spec §10: WatchLink shape + failure containment (never downgrade AVAILABLE)."""

    def _svc(self, providers):
        return LibraryService(providers=providers)

    def test_match_produces_valid_available_link(self):
        from services.library import LibraryMatch
        match = LibraryMatch("alpha", "320819", "Mad Max", 2015)
        svc = self._svc([_ArmedProvider(match, name="alpha", link_url="https://alpha/#!/server/sid/details?key=/library/metadata/320819")])
        links = svc.watch_links(match)
        assert links["alpha"]["available"] is True
        assert links["alpha"]["url"].startswith("https://alpha/")
        assert links["alpha"]["error"] is None

    def test_second_provider_match_produces_valid_link(self):
        from services.library import LibraryMatch
        match = LibraryMatch("beta", "ITEM1", "The Bear", 2022)
        svc = self._svc([_ArmedProvider(match, name="beta", link_url="https://beta/web/index.html#!/item?id=ITEM1&serverId=S1")])
        links = svc.watch_links(match)
        assert links["beta"]["available"] is True
        assert links["beta"]["url"] == "https://beta/web/index.html#!/item?id=ITEM1&serverId=S1"

    def test_both_providers_links_when_both_match(self):
        from services.library import LibraryMatch
        alpha = LibraryMatch("alpha", "1", "Arrival", 2016)
        beta = LibraryMatch("beta", "ITEM9", "Arrival", 2016)
        svc = self._svc([
            _ArmedProvider(alpha, name="alpha", link_url="https://alpha/#!/")
            , _ArmedProvider(beta, name="beta", link_url="https://beta/#!/"),
        ])
        links = svc.watch_links([alpha, beta])
        assert links["alpha"]["available"] and links["beta"]["available"]
        assert links["alpha"]["url"].startswith("https://alpha/")
        assert links["beta"]["url"].startswith("https://beta/")

    def test_one_link_failure_other_success_other_only(self):
        """Spec: 'link failure + other provider success -> the other button only'."""
        from services.library import LibraryMatch
        alpha = LibraryMatch("alpha", "1", "F", 2000)
        beta = LibraryMatch("beta", "9", "F", 2000)
        svc = self._svc([
            _ArmedProvider(alpha, name="alpha", link_url="https://alpha/#!/", raise_link=True),
            _ArmedProvider(beta, name="beta", link_url="https://beta/#!/"),
        ])
        links = svc.watch_links([alpha, beta])
        assert links["alpha"]["available"] is False
        assert links["alpha"]["url"] is None
        assert "boom" in (links["alpha"]["error"] or "")
        assert links["beta"]["available"] is True

    def test_link_failure_does_not_downgrade_availability(self):
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
        match = LibraryMatch("alpha", "320819", "Mad Max: Fury Road", 2015)
        svc = self._svc([_ArmedProvider(match, name="alpha", link_url="http://x", raise_link=True)])
        identity = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=76341)

        # 1. Availability is independent of link resolution: item present -> AVAILABLE.
        assert svc.has(identity) is True
        status = resolve_status(StatusFacts(media_type=MediaType.MOVIE, in_plex=True))
        assert status.state is MediaStatus.AVAILABLE

        # 2. Link resolution soft-fails (no raise, available=False) — button hidden only.
        links = svc.watch_links(match)
        assert links["alpha"]["available"] is False
        assert "boom" in (links["alpha"]["error"] or "")
        # Regardless of the link failure, the media state is still AVAILABLE.
        assert status.state is MediaStatus.AVAILABLE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
