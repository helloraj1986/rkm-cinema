"""Tests for the canonical status resolver, capabilities and snapshot (spec §12/§13).

Covers the pure, no-HTTP resolver in ``domain.status``:
- Priority: library availability always wins; then downloading -> requested ->
  downloaded -> not_requested.
- A failed watch link never flips AVAILABLE -> NOT_REQUESTED (spec §10).
- Capabilities.from_status maps status -> can_download / can_watch.
- MediaSnapshot.from_result wraps a StatusResult into the spec §13 canonical
  object the Phase 7 reconciler will emit.
"""
from domain.enums import MediaType, MediaStatus
from domain.status import (
    Capabilities,
    MediaSnapshot,
    StatusFacts,
    StatusResult,
    WatchLinks,
    allowed_transitions,
    resolve_status,
)
from domain.state_machine import (  # backwards-compat shim still exposes the same API
    StatusFacts as ShimFacts,
    resolve_status as shim_resolve,
    MediaSnapshot as ShimSnapshot,
)


class TestResolveStatus:
    def test_available_when_in_library_always_wins(self):
        """in_library trumps every other fact (even a record + download)."""
        f = StatusFacts(in_plex=True, arr_record_exists=True,
                        plex_links=WatchLinks(plex_url="http://p", emby_url="http://e"))
        r = resolve_status(f)
        assert r.state is MediaStatus.AVAILABLE
        assert r.plexUrl == "http://p"
        assert r.embyUrl == "http://e"

    def test_priority_order(self):
        assert resolve_status(StatusFacts(in_plex=False, qbit_active=True)).state is MediaStatus.DOWNLOADING
        assert resolve_status(StatusFacts(in_plex=False, arr_record_exists=True)).state is MediaStatus.REQUESTED
        assert resolve_status(StatusFacts(in_plex=False, arr_has_file=True)).state is MediaStatus.DOWNLOADED
        assert resolve_status(StatusFacts()).state is MediaStatus.NOT_ADDED

    def test_watch_link_failure_does_not_downgrade_available(self):
        """Spec §10: a missing/failed watch link leaves the item AVAILABLE."""
        r = resolve_status(StatusFacts(in_plex=True))  # no watch links at all
        assert r.state is MediaStatus.AVAILABLE
        assert r.plexUrl == ""

    def test_requested_detail_surfaces_indexer_issue(self):
        r = resolve_status(StatusFacts(in_plex=False, arr_record_exists=True,
                                       indexer_issue="Indexers down"))
        assert r.detail == "Waiting — search indexers down"

    def test_media_type_drives_service(self):
        assert resolve_status(StatusFacts(media_type=MediaType.TV)).service == "sonarr"
        assert resolve_status(StatusFacts()).service == "radarr"


class TestCapabilitiesAndSnapshot:
    def test_capabilities_from_status(self):
        assert Capabilities.from_status(MediaStatus.NOT_ADDED).can_download is True
        assert Capabilities.from_status(MediaStatus.AVAILABLE).can_watch is True
        assert Capabilities.from_status(MediaStatus.AVAILABLE).can_download is False

    def test_media_snapshot_from_result(self):
        res = StatusResult(state=MediaStatus.AVAILABLE, service="radarr",
                           detail="Available in Plex", plexUrl="http://p")
        snap = MediaSnapshot.from_result(res, media_id="movie:tmdb:603",
                                         watch_links={"plex": {"available": True, "url": "http://p"}})
        assert snap.media_id == "movie:tmdb:603"
        assert snap.status is MediaStatus.AVAILABLE
        assert snap.capabilities.can_watch is True
        assert snap.capabilities.can_download is False
        assert snap.watch_links["plex"]["url"] == "http://p"

    def test_transitions_spec_intent(self):
        assert allowed_transitions(MediaStatus.NOT_ADDED, MediaStatus.AVAILABLE) is True
        assert allowed_transitions(MediaStatus.AVAILABLE, MediaStatus.AVAILABLE) is True


class TestStateMachineShim:
    """domain.state_machine is now a BC shim over domain.status (§43)."""

    def test_shim_exposes_same_resolver(self):
        f = ShimFacts(in_plex=True)
        assert shim_resolve(f).state is MediaStatus.AVAILABLE
        assert ShimSnapshot is MediaSnapshot
        assert ShimFacts is StatusFacts