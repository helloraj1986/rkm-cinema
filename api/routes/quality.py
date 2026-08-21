"""Quality profiles endpoint for download quality selection."""
from fastapi import APIRouter
from api.models import QualityProfilesResponse, QualityProfileResponse
from config.settings import get_config
from services import RadarrService, SonarrService

router = APIRouter()


@router.get("/quality", response_model=QualityProfilesResponse)
def get_quality_profiles():
    """Get quality profiles from Radarr and Sonarr."""
    cfg = get_config()

    radarr_profiles = []
    sonarr_profiles = []

    if cfg.RADARR_API_KEY:
        try:
            radarr = RadarrService()
            for p in radarr.get_quality_profiles():
                radarr_profiles.append(QualityProfileResponse(
                    id=p.id, name=p.name, items=p.items
                ))
        except Exception:
            pass

    if cfg.SONARR_API_KEY:
        try:
            sonarr = SonarrService()
            for p in sonarr.get_quality_profiles():
                sonarr_profiles.append(QualityProfileResponse(
                    id=p.id, name=p.name, items=p.items
                ))
        except Exception:
            pass

    return QualityProfilesResponse(radarr=radarr_profiles, sonarr=sonarr_profiles)