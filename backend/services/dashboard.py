"""Dashboard/display mapping for watchlist entries.

Canonical seam between a persisted :class:`WatchlistEntry` and the rich SPA
entry shape the UIs render (posters, backdrops, scores, synopsis, trailer,
genres/category). Consumers:

- ``GET /api/watchlist/entries`` (the live rich-entry source the React shell
  uses for Discover/Watchlist parity)

One mapper, every consumer — never duplicate the normalisation.
"""
from __future__ import annotations

import re
import urllib.parse

from services.watchlist import WatchlistEntry

# Category -> genre hints used when an entry has no explicit genres yet.
GENRE_HINTS = {
    "Sci-Fi/Fantasy": ["Science Fiction", "Fantasy"],
    "Kids & Animation": ["Animation", "Family"],
    "Hindi/Indian Cinema": ["Drama", "Thriller"],
    "Classic/Essential": ["Classic"],
    "Documentary": ["Documentary"],
}

_TRAILER_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")


def to_rich_entry(entry: WatchlistEntry) -> dict:
    """Map one watchlist entry -> rich SPA entry. Pure data, no secrets.

    The output shape matches ``WatchlistEntryResponse`` (api/models.py) so an
    API route can return it directly and the dashboard generator can write it
    to JSON unchanged.
    """
    is_series = entry.isSeries
    title = entry.title
    year = entry.year
    cat = entry.category
    trailer_id = entry.trailerId or ""
    trailer_title = entry.trailerTitle or ""
    poster = entry.poster or ""
    backdrop = entry.backdrop or ""

    # Validate trailer ID format
    if trailer_id and not _TRAILER_ID_RE.fullmatch(str(trailer_id)):
        trailer_id = ""

    # Genres: use entry.genres, fallback to category hints if empty
    genres = entry.genres if entry.genres else GENRE_HINTS.get(cat, [cat] if cat else [])

    # Overview: prefer tmdb_overview, then snippet, then fallback
    overview = entry.tmdb_overview or entry.snippet or f"{title} ({year}) - {entry.category}"

    # tmdbScore: use entry.tmdb_score, fallback to imdb
    tmdb_score = entry.tmdb_score if entry.tmdb_score > 0 else (float(entry.imdb) if entry.imdb else 0.0)

    return {
        "imdbId": entry.imdbId,
        "tmdbId": entry.tmdbId,
        "tvdbId": None,
        "title": title,
        "year": int(year) if str(year).isdigit() else year,
        "type": "tv" if is_series else "movie",
        "category": cat,
        "genres": genres,
        "lang": entry.lang,
        "cert": entry.cert,
        "rt": entry.rt,
        "imdb": entry.imdb,
        "tmdbScore": tmdb_score,
        "overview": overview,
        "cast": entry.cast or [],
        "director": entry.director,
        "runtime": entry.runtime,
        "poster": poster,
        "backdrop": backdrop,
        "trailerId": trailer_id,
        "trailerTitle": trailer_title,
        "trailerUrl": (f"https://www.youtube.com/embed/{trailer_id}?autoplay=1&rel=0&color=white"
                       if trailer_id else
                       f"https://www.youtube.com/results?search_query="
                       f"{urllib.parse.quote(title + ' ' + str(year) + ' trailer')}"),
        "added": entry.added,
        "source": entry.source,
        # Status fields (populated by API at runtime)
        "state": entry.state,
        "detail": entry.detail,
        "progress": entry.progress,
    }
