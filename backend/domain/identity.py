"""Canonical media identity.

The spec (§1.1, §4) forbids using ``title`` as the primary key. The stable,
normalized identity of a piece of media is a provider ID (TMDB > IMDb > TVDB)
combined with its media type. This module is the SINGLE source of that rule.

``media_id`` is the canonical string form the rest of the app keys on, e.g.::

    movie:tmdb:603        -> The Matrix
    movie:imdb:tt0133093  -> the same film, identity known via IMDb only
    series:tmdb:1396      -> Breaking Bad

Ambiguous or unresolvable identities are an explicit error state, never a
silent guess.
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.enums import MediaType


@dataclass(frozen=True, eq=True)
class MediaIdentity:
    """A normalized, stable identity for a piece of media.

    At least one provider ID must be present. IDs are normalized at construct
    time (TMDB/TVDB coerced to int, IMDb kept as a string "ttNNNNNNNN").
    """

    media_type: MediaType
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None

    def __post_init__(self) -> None:
        # Normalize provider IDs so "605", 605 and 605.0 all collapse to 605.
        if self.tmdb_id is not None:
            object.__setattr__(self, "tmdb_id", self._coerce_int(self.tmdb_id))
        if self.tvdb_id is not None:
            object.__setattr__(self, "tvdb_id", self._coerce_int(self.tvdb_id))
        if self.imdb_id is not None:
            object.__setattr__(self, "imdb_id", self._normalize_imdb(self.imdb_id))

    @staticmethod
    def _coerce_int(value: int | str | float | None) -> int | None:
        if value is None:
            return None
        try:
            if isinstance(value, float) and not value.is_integer():
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_imdb(value: str | None) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        if not s.lower().startswith("tt"):
            s = "tt" + s
        return s

    @property
    def media_id(self) -> str:
        """Canonical string id, preferring TMDB then IMDb then TVDB."""
        if self.tmdb_id is not None:
            return f"{self.media_type.value}:tmdb:{self.tmdb_id}"
        if self.imdb_id:
            return f"{self.media_type.value}:imdb:{self.imdb_id}"
        if self.tvdb_id is not None:
            return f"{self.media_type.value}:tvdb:{self.tvdb_id}"
        raise ValueError("MediaIdentity requires a stable provider ID")

    @property
    def has_any_id(self) -> bool:
        return self.tmdb_id is not None or bool(self.imdb_id) or self.tvdb_id is not None

    def preferred(self) -> str:
        """The single best provider id for *arr lookups: TMDB > IMDb > TVDB."""
        if self.tmdb_id is not None:
            return f"tmdb:{self.tmdb_id}"
        if self.imdb_id:
            return self.imdb_id
        if self.tvdb_id is not None:
            return f"tvdb:{self.tvdb_id}"
        raise ValueError("MediaIdentity requires a stable provider ID")

    @classmethod
    def from_parts(
        cls,
        *,
        media_type: MediaType,
        tmdb_id: int | str | None = None,
        imdb_id: str | None = None,
        tvdb_id: int | str | None = None,
    ) -> "MediaIdentity":
        """Build an identity. Raises ``ValueError`` if no provider ID is present."""
        identity = cls(
            media_type=media_type,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            tvdb_id=tvdb_id,
        )
        if not identity.has_any_id:
            raise ValueError("Media identity requires a stable provider ID")
        return identity


def parse_media_id(media_id: str) -> MediaIdentity:
    """Parse a canonical ``<type>:<provider>:<id>`` string back into MediaIdentity.

    Raises ``ValueError`` for an unparseable or unknown-provider string.
    """
    if not media_id:
        raise ValueError("Empty media_id")
    parts = media_id.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid media_id: {media_id!r}")
    type_str, provider, raw_id = parts
    try:
        media_type = MediaType(type_str)
    except ValueError:
        # Accept the display-friendly 'series' alias -> TV.
        if type_str.lower() in ("series", "show", "tv"):
            media_type = MediaType.TV
        else:
            raise ValueError(f"Unknown media type: {type_str!r}")

    if provider not in ("tmdb", "imdb", "tvdb"):
        raise ValueError(f"Unknown identity provider: {provider!r}")

    if provider == "imdb":
        imdb = MediaIdentity._normalize_imdb(raw_id)
        if not imdb:
            raise ValueError(f"Invalid imdb id: {raw_id!r}")
        return MediaIdentity(media_type=media_type, imdb_id=imdb)
    try:
        numeric = int(raw_id)
    except ValueError:
        raise ValueError(f"Invalid {provider} id: {raw_id!r}") from None
    if provider == "tmdb":
        return MediaIdentity(media_type=media_type, tmdb_id=numeric)
    return MediaIdentity(media_type=media_type, tvdb_id=numeric)