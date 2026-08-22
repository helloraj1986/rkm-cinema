"""Quality profiles endpoint for download quality selection.

Thin route: reads quality profiles through the acquisition facade (spec §14);
no caller touches RadarrService/SonarrService directly (§43). Each backend is
keyed by its provider name with a safe empty-list fallback on outage.
"""
from fastapi import APIRouter
from api.models import QualityProfilesResponse, QualityProfileResponse
from config.settings import get_config
from services.acquisition import build_acquisition_service

router = APIRouter()


@router.get("/quality", response_model=QualityProfilesResponse)
def get_quality_profiles():
    """Get quality profiles from Radarr and Sonarr via the acquisition facade."""
    cfg = get_config()
    acq = build_acquisition_service(config=cfg)
    profiles = acq.quality_profiles()

    radarr_profiles = [
        QualityProfileResponse(id=p["id"], name=p["name"], items=p.get("items", []))
        for p in profiles.get("radarr", [])
    ]
    sonarr_profiles = [
        QualityProfileResponse(id=p["id"], name=p["name"], items=p.get("items", []))
        for p in profiles.get("sonarr", [])
    ]

    return QualityProfilesResponse(radarr=radarr_profiles, sonarr=sonarr_profiles)