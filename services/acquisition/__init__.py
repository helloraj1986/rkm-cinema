"""Acquisition package (spec §14 Phase 8) — single movie/series routing.

Callers use :class:`AcquisitionService` (routes by media type) and never
branch on ``if movie: radarr else: sonarr``. Radarr/Sonarr low-level HTTP
clients live behind the :class:`AcquisitionProvider` facades.
"""
from services.acquisition.service import (
    AcquisitionProvider,
    AcquisitionService,
    AcquisitionStatus,
    AcquisitionRequestResult,
)
from services.acquisition.radarr import RadarrAcquisitionProvider
from services.acquisition.sonarr import SonarrAcquisitionProvider

__all__ = [
    "AcquisitionProvider",
    "AcquisitionService",
    "AcquisitionStatus",
    "AcquisitionRequestResult",
    "RadarrAcquisitionProvider",
    "SonarrAcquisitionProvider",
]