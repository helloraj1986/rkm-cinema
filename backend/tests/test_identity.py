"""Tests for domain/identity.py (Phase 2 — canonical media identity)."""
import pytest

from domain.enums import MediaType
from domain.identity import MediaIdentity, parse_media_id


def test_tmdb_id_forms_canonical_media_id():
    i = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id="603")
    assert i.media_id == "movie:tmdb:603"


def test_imdb_id_forms_canonical_media_id():
    i = MediaIdentity(media_type=MediaType.MOVIE, imdb_id="tt0133093")
    assert i.media_id == "movie:imdb:tt0133093"


def test_tvdb_id_forms_canonical_media_id():
    i = MediaIdentity(media_type=MediaType.TV, tvdb_id="81189")
    assert i.media_id == "tv:tvdb:81189"


def test_tmdb_preferred_over_imdb():
    i = MediaIdentity(media_type=MediaType.TV, tmdb_id=1396, imdb_id="tt0903747")
    assert i.media_id == "tv:tmdb:1396"
    assert i.preferred() == "tmdb:1396"


def test_missing_ids_raise():
    with pytest.raises(ValueError):
        MediaIdentity(media_type=MediaType.MOVIE).media_id


def test_from_parts_requires_id():
    with pytest.raises(ValueError):
        MediaIdentity.from_parts(media_type=MediaType.MOVIE)


def test_from_parts_preserves_all_ids():
    i = MediaIdentity.from_parts(
        media_type=MediaType.MOVIE, tmdb_id=603, imdb_id="tt0133093", tvdb_id=None
    )
    assert i.tmdb_id == 603
    assert i.imdb_id == "tt0133093"


def test_id_normalization():
    # "605.0" string coerces to int 605
    assert MediaIdentity(media_type=MediaType.TV, tmdb_id="605").tmdb_id == 605
    # missing 'tt' prefix added for imdb
    assert MediaIdentity(media_type=MediaType.MOVIE, imdb_id="0133093").imdb_id == "tt0133093"


def test_parse_roundtrip():
    i = parse_media_id("movie:tmdb:603")
    assert i.media_type is MediaType.MOVIE
    assert i.tmdb_id == 603
    assert i.media_id == "movie:tmdb:603"


def test_parse_series_alias():
    i = parse_media_id("series:tmdb:1396")
    assert i.media_type is MediaType.TV


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_media_id("movie")
    with pytest.raises(ValueError):
        parse_media_id("movie:tmdb:not-a-number")
    with pytest.raises(ValueError):
        parse_media_id("movie:unknown:1")