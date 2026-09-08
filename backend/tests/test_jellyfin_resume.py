"""Tests for Continue-Watching EPISODES (docs/CONTINUE_WATCHING_EPISODES_PLAN.md
— backend Phase 1, Option A).

Covers ``JellyfinLibraryProvider.continue_watching`` now reading Jellyfin's
``/Items/Resume`` FIRST (episodes surface individually), merged with the old
scan filter + dedupe:

- Episode Resume rows parse to the public shape with ``kind: episode`` + the
  ``episode`` facet (number/season/series_id/series_name).
- Movie/Series Resume rows keep the existing item shape + additive ``kind``.
- Merge/dedupe: an item in both Resume and the scan filter appears once.
- Played episodes from Resume are excluded (honest in-progress only).
- Resume endpoint unavailable -> clean fallback to the scan filter.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

from services.library.jellyfin import JellyfinItem, JellyfinLibraryProvider


def _cfg(**over):
    vals = dict(
        JELLYFIN_URL="http://jellyfin:8096",
        JELLYFIN_API_KEY="jkey",
        JELLYFIN_BROWSER_URL="http://localhost:8098",
        MEDIA_SERVER="jellyfin",
        PLEX_URL="", PLEX_TOKEN="", EMBY_URL="", EMBY_API_KEY="",
    )
    vals.update(over)
    return SimpleNamespace(**vals)


class _FakeJson:
    def __init__(self, payload):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._p).encode()


def _resume_episode(**over):
    """Live-verified Resume episode shape (Jellyfin 10.11.11)."""
    it = {
        "Id": "ep1", "Name": "Our Lord", "Type": "Episode", "ProductionYear": 2024,
        "SeriesId": "ser1", "SeriesName": "3 Body Problem", "SeasonId": "sea1",
        "ParentIndexNumber": 1, "IndexNumber": 4, "RunTimeTicks": 26_480_000_000,
        "ImageTags": {"Primary": "imgtag"}, "Genres": ["Drama"],
        "UserData": {"Played": False, "PlaybackPositionTicks": 11_600_000_000,
                     "PlayCount": 1, "LastPlayedDate": "2026-09-08T10:00:00.0000000Z"},
    }
    it.update(over)
    return it


def _resume_movie(**over):
    it = {
        "Id": "m1", "Name": "Prisoners", "Type": "Movie", "ProductionYear": 2013,
        "RunTimeTicks": 91_920_000_000, "ProviderIds": {"Tmdb": "146233"},
        "Genres": ["Crime"], "UserData": {"Played": False,
                                          "PlaybackPositionTicks": 39_960_000_000,
                                          "PlayCount": 2},
    }
    it.update(over)
    return it


def _urlopen_side(resume_items):
    def side_effect(url, *args, **kwargs):
        u = url if isinstance(url, str) else getattr(url, "full_url", "")
        if "/System/Info/Public" in u:
            return _FakeJson({"Id": "srv-abc"})
        if u.endswith("/Users?api_key=jkey"):
            return _FakeJson([{"Id": "user-1", "Name": "admin"}])
        if "/Items/Resume" in u:
            return _FakeJson({"Items": resume_items})
        return _FakeJson({"Items": []})
    return side_effect


def _prov(resume_items):
    with patch("urllib.request.urlopen", side_effect=_urlopen_side(resume_items)):
        p = JellyfinLibraryProvider(config=_cfg())
        p._item_web = lambda iid: f"http://jf/x#/details?id={iid}"
        p._fake_resume = resume_items
        return p


def _call(prov, limit=12):
    with patch("urllib.request.urlopen",
               side_effect=_urlopen_side(prov._fake_resume)):
        return prov.continue_watching(limit=limit)


def test_continue_watching_lists_in_progress_episodes():
    """A half-watched episode surfaces with kind=episode + the episode facet."""
    prov = _prov([_resume_episode()])
    items = _call(prov)
    assert [x["item_id"] for x in items] == ["ep1"]
    ep = items[0]
    assert ep["kind"] == "episode"
    assert ep["type"] == "episode"
    assert ep["title"] == "Our Lord"
    assert ep["played"] is False
    assert ep["playback_position"] == 1160      # ticks / 1e7
    assert ep["runtime"] == 2648
    assert ep["episode"] == {"number": 4, "season": 1,
                             "series_id": "ser1", "series_name": "3 Body Problem"}
    assert ep["item_id"] == "ep1"
    assert ep["jellyfin_url"].endswith("#/details?id=ep1")


def test_continue_watching_movie_rows_keep_shape_with_kind():
    """Movie Resume rows keep the public item shape + additive kind=movie."""
    prov = _prov([_resume_movie()])
    items = _call(prov)
    assert len(items) == 1
    m = items[0]
    assert m["kind"] == "movie"
    assert m["type"] == "movie"
    assert m["item_id"] == "m1"
    assert m["playback_position"] == 3996
    assert "episode" not in m  # no episode facet on movies


def test_continue_watching_merges_resume_and_scan_without_dupes():
    """Resume rows first (server order), scan-filter rows fill in; dedupe by id."""
    prov = _prov([_resume_movie(), _resume_episode()])
    prov._get_items = lambda itype: {
        "Movie": [
            JellyfinItem(name="Prisoners", year=2013, id="m1",
                         played=False, position_ticks=39_960_000_000,
                         runtime_ticks=91_920_000_000),
            JellyfinItem(name="Other Half", year=2001, id="m9",
                         played=False, position_ticks=30_000_000_000,
                         runtime_ticks=100_000_000_000),
        ],
        "Series": [],
    }[itype]
    items = _call(prov)
    assert [x["item_id"] for x in items] == ["m1", "ep1", "m9"]
    # m1 came from Resume (kind set) — never duplicated by the scan fallback.
    assert items[0]["kind"] == "movie"


def test_continue_watching_excludes_played_episodes():
    """Resume episodes that are already Played are excluded (in-progress only)."""
    prov = _prov([
        _resume_episode(Id="ep-played", Played=True,
                        UserData={"Played": True, "PlaybackPositionTicks": 1}),
        _resume_episode(Id="ep-mid"),
    ])
    items = _call(prov)
    assert [x["item_id"] for x in items] == ["ep-mid"]


def test_continue_watching_series_rows_kind_show():
    prov = _prov([{
        "Id": "ser1", "Name": "3 Body Problem", "Type": "Series",
        "ProductionYear": 2024, "RunTimeTicks": 0,
        "UserData": {"Played": False, "PlaybackPositionTicks": 1},
    }])
    items = _call(prov)
    assert items and items[0]["kind"] == "show" and items[0]["type"] == "tv"


def test_continue_watching_falls_back_when_resume_unavailable():
    """Resume endpoint failing (e.g. provider older than Resume support) degrades
    to the scan filter — movies/series only, exactly the pre-change behaviour."""
    prov = JellyfinLibraryProvider(config=_cfg())
    prov._item_web = lambda iid: f"http://jf/x#/details?id={iid}"
    prov._get_items = lambda itype: {
        "Movie": [
            JellyfinItem(name="Half", year=2001, id="m1",
                         played=False, position_ticks=30_000_000_000,
                         runtime_ticks=100_000_000_000),
            JellyfinItem(name="Fresh", year=2002, id="m2",
                         played=False, position_ticks=0, runtime_ticks=80_000_000_000),
        ],
        "Series": [],
    }[itype]
    with patch("urllib.request.urlopen", side_effect=OSError("no network")):
        items = prov.continue_watching(limit=12)
    assert [x["item_id"] for x in items] == ["m1"]
    assert items[0]["kind"] == "movie"
    assert items[0]["playback_position"] == 3000


def test_continue_watching_honours_limit_across_both_sources():
    prov = _prov([_resume_episode(), _resume_episode(Id="ep2", IndexNumber=5)])
    prov._get_items = lambda itype: {
        "Movie": [JellyfinItem(name="A", year=2000, id="m1",
                               played=False, position_ticks=1,
                               runtime_ticks=100)],
        "Series": [],
    }[itype]
    items = _call(prov, limit=2)
    assert [x["item_id"] for x in items] == ["ep1", "ep2"]
