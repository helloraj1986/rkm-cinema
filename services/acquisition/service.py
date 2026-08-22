"""Acquisition abstraction (spec §14 Phase 8).

Centralizes the movie→Radarr / series→Sonarr routing that previously lived
in every caller. The app layer no longer writes ``if movie: radarr else:
sonarr`` — that branching lives HERE in :class:`AcquisitionService`, which
routes a ``MediaIdentity`` to the right :class:`AcquisitionProvider` by its
``media_type``.

The existing ``RadarrService`` / ``SonarrService`` stay as the low-level HTTP
clients; ``AcquisitionProvider`` subclasses wrap them (thin facade, §43 no
parallel implementation) so no caller reaches for Radarr/Sonarr directly.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from domain.enums import MediaType
from domain.identity import MediaIdentity

logger = logging.getLogger("rkm.acquisition")

__all__ = [
    "AcquisitionProvider",
    "AcquisitionStatus",
    "AcquisitionRequestResult",
    "AcquisitionService",
]


@dataclass
class AcquisitionStatus:
    """Facts an *arr provider reports for one media item (spec §14 get_status).

    Carries the raw record's title/year so the reconciler can cross-match it in
    qBittorrent (the download client matches by name, not provider id).
    """

    service: str = ""
    record_exists: bool = False        # item is already in *arr
    has_file: bool = False             # *arr reports a file on disk
    queue_active: bool = False         # a *arr queue entry is downloading
    queue_percent: Optional[int] = None
    record_title: str = ""
    record_year: Optional[int] = None


@dataclass
class AcquisitionRequestResult:
    """Normalized result of the idempotent ``request`` operation.

    ``state`` ∈ {"requested", "already_exists", "ambiguous", "unavailable"}.
    ``item`` is the *arr record (RadarrMovie / SonarrSeries) on success or
    ambiguity, else None.
    """

    success: bool
    state: str
    message: str
    media_type: MediaType
    service: str = ""
    item: object = None


class AcquisitionProvider(ABC):
    """Interface each *arr backend (Radarr / Sonarr) implements."""

    name: str = "base"
    media_type: MediaType = MediaType.MOVIE

    @abstractmethod
    def health(self) -> bool:
        """Whether the backend is reachable right now."""

    @abstractmethod
    def find(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None):
        """Return the existing *arr record matching *identity*, or None.

        Uses stable provider ids (TMDB/IMDb/TVDB) and falls back to title/year
        only when no stable id resolves (mirrors the library-provider rule).
        """

    @abstractmethod
    def request(self, identity: MediaIdentity, *, title: str = "",
                year: Optional[int] = None, quality_profile_id: Optional[int] = None) -> AcquisitionRequestResult:
        """Idempotently add the item to *arr and start the download search.

        Already-present items yield state="already_exists" (no double-add).
        """

    @abstractmethod
    def get_status(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None) -> AcquisitionStatus:
        """Report download/ownership facts for *identity*."""

    def indexer_issue(self) -> Optional[str]:
        """Optional per-backend indexer health warning (default: none)."""
        return None


class AcquisitionService:
    """Single acquisition facade that routes by media type (spec §14)."""

    def __init__(self, providers: Optional[list[AcquisitionProvider]] = None):
        self._providers: list[AcquisitionProvider] = providers or []

    def add_provider(self, provider: AcquisitionProvider) -> None:
        self._providers.append(provider)

    @property
    def providers(self) -> list[AcquisitionProvider]:
        return list(self._providers)

    def provider_for(self, media_type: MediaType) -> Optional[AcquisitionProvider]:
        """The single acquisition backend for a media type (THE router)."""
        for p in self._providers:
            if p.media_type is media_type:
                return p
        return None

    # ---------------------------------------------------------------- routed
    def find(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None):
        provider = self.provider_for(identity.media_type)
        if provider is None:
            return None
        try:
            return provider.find(identity, title=title, year=year)
        except Exception as e:  # one broken backend never blocks the caller
            logger.warning("acquisition %s find failed: %s", provider.name, e)
            return None

    def request(self, identity: MediaIdentity, *, title: str = "",
                year: Optional[int] = None, quality_profile_id: Optional[int] = None) -> AcquisitionRequestResult:
        provider = self.provider_for(identity.media_type)
        if provider is None:
            return AcquisitionRequestResult(
                success=False, state="unavailable",
                message=f"{identity.media_type.value} acquisition is not configured",
                media_type=identity.media_type, service="")
        return provider.request(identity, title=title, year=year,
                                quality_profile_id=quality_profile_id)

    def get_status(self, identity: MediaIdentity, *, title: str = "",
                   year: Optional[int] = None) -> Optional[AcquisitionStatus]:
        provider = self.provider_for(identity.media_type)
        if provider is None:
            return None
        try:
            return provider.get_status(identity, title=title, year=year)
        except Exception as e:
            logger.warning("acquisition %s get_status failed: %s", provider.name, e)
            return None

    def health(self) -> dict[str, bool]:
        return {p.name: p.health() for p in self._providers}

    def indexer_issue(self) -> Optional[str]:
        """Indexer health warning from the acquisition backends (Radarr reports it)."""
        radarr = self.provider_for(MediaType.MOVIE)
        if radarr is not None:
            return radarr.indexer_issue()
        return None

    # ------------------------------------------------------------ batch preload
    def preload(self) -> None:
        """Ask every provider to warm its caches (one bulk fetch per backend).

        Called before a multi-item reconcile so per-item ``get_status`` calls
        hit the 45s in-memory cache instead of re-scanning the *arr each time.
        """
        for p in self._providers:
            try:
                p.preload()
            except Exception as e:
                logger.warning("acquisition %s preload failed: %s", p.name, e)