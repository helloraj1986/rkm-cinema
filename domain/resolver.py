"""Authoritative movie-vs-TV resolver.

This is the single place that decides whether a title is a movie or a TV
series. No route may independently re-derive this. A movie must never route to
Sonarr, and a series must never route to Radarr.
"""
from __future__ import annotations

from typing import Optional

from domain.enums import MediaType


def resolve_media_type(
    *,
    requested_type: Optional[str] = None,
    watchlist_is_series: Optional[bool] = None,
    radarr_match: bool = False,
    sonarr_match: bool = False,
) -> MediaType:
    """Resolve the media type with a fixed, deterministic priority:

    1. Explicit requested type (movie/tv) wins.
    2. Watchlist entry's stored isSeries.
    3. Radarr lookup hit -> movie; else Sonarr lookup hit -> tv.
    4. Default to movie (the common case).
    """
    explicit = MediaType.from_request(requested_type)
    if explicit is not None:
        return explicit

    if watchlist_is_series is True:
        return MediaType.TV
    if watchlist_is_series is False:
        return MediaType.MOVIE

    if radarr_match:
        return MediaType.MOVIE
    if sonarr_match:
        return MediaType.TV

    return MediaType.MOVIE
