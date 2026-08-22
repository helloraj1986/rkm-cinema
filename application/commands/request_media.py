"""Idempotent media-request command (spec §15 Phase 9).

``request_media`` is the single use case for adding a title to the acquisition
(*arr) backend. It is **idempotent**: re-checking the library and the *arr
record happens before any write, so a repeated request never double-adds and
never downgrades an already-requested or already-available title.

Orchestration (all via the canonical services — no caller knows Radarr vs
Sonarr):

1. Resolve identity              -> ``MediaIdentity``
2. Re-check library              -> AVAILABLE if present (library always wins, §1.2)
3. Check existing acquisition    -> ALREADY_REQUESTED if *arr already has it
4. Route + resolve provider item -> AMBIGUOUS on multi-match
5. Request acquisition           -> REQUESTED on success
6. Persist acquisition record    -> via injected ``persist`` hook
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from domain.enums import MediaType, RequestMediaState
from domain.identity import MediaIdentity, parse_media_id
from services.acquisition import (
    AcquisitionRequestResult,
    AcquisitionService,
    RadarrAcquisitionProvider,
    SonarrAcquisitionProvider,
)
from services.library import (
    EmbyLibraryProvider,
    LibraryService,
    PlexLibraryProvider,
    resolve_library_identity,
)

logger = logging.getLogger("rkm.commands.request_media")

__all__ = ["RequestMediaResult", "request_media", "RequestMediaCommand"]


@dataclass
class RequestMediaResult:
    """Typed outcome of ``request_media`` (spec §15 vocab)."""

    state: RequestMediaState
    message: str
    media_id: str = ""
    media_type: MediaType = MediaType.MOVIE
    service: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    item: object = None

    @property
    def success(self) -> bool:
        """A terminal good outcome (requested / already-requested / available)."""
        return self.state in (
            RequestMediaState.REQUESTED,
            RequestMediaState.ALREADY_REQUESTED,
            RequestMediaState.AVAILABLE,
        )


class RequestMediaCommand:
    """DI-ready idempotent request use case."""

    def __init__(self, *, library=None, acquisition=None, persist: Optional[Callable[[str, str, str], None]] = None,
                 plex=None, radarr=None, sonarr=None, config=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self._persist = persist  # callable(id: str, provider: str, state: str) -> None

        self._library = library
        if self._library is None:
            providers = []
            if plex is not None:
                providers.append(PlexLibraryProvider(config=self.config, plex=plex))
            elif self.config.PLEX_URL and self.config.PLEX_TOKEN:
                providers.append(PlexLibraryProvider(config=self.config))
            if self.config.EMBY_URL and self.config.EMBY_API_KEY:
                providers.append(EmbyLibraryProvider(config=self.config))
            self._library = LibraryService(providers=providers) if providers else None

        self._acquisition = acquisition
        if self._acquisition is None:
            acq_providers = []
            if radarr is not None:
                acq_providers.append(RadarrAcquisitionProvider(service=radarr))
            elif self.config.RADARR_API_KEY:
                acq_providers.append(RadarrAcquisitionProvider(config=self.config))
            if sonarr is not None:
                acq_providers.append(SonarrAcquisitionProvider(service=sonarr))
            elif self.config.SONARR_API_KEY:
                acq_providers.append(SonarrAcquisitionProvider(config=self.config))
            self._acquisition = AcquisitionService(providers=acq_providers) if acq_providers else None

    # ------------------------------------------------------------------ run
    def run(self, media_id: str, *, title: str = "", year: Optional[int] = None) -> RequestMediaResult:
        """Execute the idempotent request for a canonical ``media_id``."""
        try:
            identity = parse_media_id(media_id)
        except ValueError as e:
            logger.warning("request_media: unparseable media_id=%r", media_id)
            return RequestMediaResult(
                state=RequestMediaState.NOT_CONFIGURED, message=str(e), media_id=media_id)

        # 2. Library always wins (spec §1.2) — never show/re-request available media.
        if self._library and self._library.has(identity, title=title, year=year):
            return RequestMediaResult(
                state=RequestMediaState.AVAILABLE,
                message="Already in the library",
                media_id=identity.media_id, media_type=identity.media_type)

        provider = self._acquisition.provider_for(identity.media_type) if self._acquisition else None
        if provider is None:
            return RequestMediaResult(
                state=RequestMediaState.NOT_CONFIGURED,
                message=f"{identity.media_type.value} acquisition is not configured",
                media_id=self._safe_id(identity), media_type=identity.media_type)

        # 3. Already requested (spec §15 step 5) — idempotency guard.
        if self._acquisition.find(identity, title=title, year=year) is not None:
            return RequestMediaResult(
                state=RequestMediaState.ALREADY_REQUESTED,
                message="Already requested",
                media_id=self._safe_id(identity), media_type=identity.media_type,
                service=provider.name)

        # 4-5. Request; explicit ambiguous handling (§16 never silently choose).
        result: AcquisitionRequestResult = self._acquisition.request(
            identity, title=title, year=year)

        if result.state == "ambiguous":
            return RequestMediaResult(
                state=RequestMediaState.AMBIGUOUS, message=result.message,
                media_id=self._safe_id(identity), media_type=identity.media_type,
                service=result.service, candidates=self._candidates(result))

        if result.success:
            if self._persist is not None:
                try:
                    self._persist(self._safe_id(identity), result.service, "requested")
                except Exception as e:  # persistence must not break the request
                    logger.warning("request_media persist failed: %s", e)
            return RequestMediaResult(
                state=RequestMediaState.REQUESTED, message=result.message,
                media_id=self._safe_id(identity), media_type=identity.media_type,
                service=result.service, item=result.item)

        # Reached a *arr but couldn't add it.
        return RequestMediaResult(
            state=RequestMediaState.PROVIDER_UNAVAILABLE, message=result.message,
            media_id=self._safe_id(identity), media_type=identity.media_type,
            service=result.service)

    # ------------------------------------------------------------- internals
    @staticmethod
    def _safe_id(identity: MediaIdentity) -> str:
        try:
            return identity.media_id
        except ValueError:
            return ""

    @staticmethod
    def _candidates(result: AcquisitionRequestResult) -> list[dict]:
        """Flatten an ambiguous result's candidates if the provider populated ``item``/message."""
        raw = getattr(result, "item", None)
        if raw is None:
            return []
        return [{"title": getattr(raw, "title", ""), "year": getattr(raw, "year", None)}]


def request_media(media_id: str, *, title: str = "", year: Optional[int] = None,
                  library=None, acquisition=None, persist=None, plex=None,
                  radarr=None, sonarr=None, config=None) -> RequestMediaResult:
    """Module-level convenience for the idempotent request command."""
    return RequestMediaCommand(
        library=library, acquisition=acquisition, persist=persist,
        plex=plex, radarr=radarr, sonarr=sonarr, config=config,
    ).run(media_id, title=title, year=year)