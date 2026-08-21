"""Services package - unified exports."""
from services.base import BaseService
from services.plex import PlexService, PlexMovie, PlexShow
from services.radarr import RadarrService, RadarrMovie, RadarrQueueItem, QualityProfile as RadarrQualityProfile, RootFolder as RadarrRootFolder, AddResult as RadarrAddResult
from services.sonarr import SonarrService, SonarrSeries, SonarrQueueItem, QualityProfile as SonarrQualityProfile, RootFolder as SonarrRootFolder, LanguageProfile, AddResult as SonarrAddResult
from services.trailers import TrailerService, TrailerInfo
from services.tmdb import TMDBService
from services.emby import EmbyService, EmbyItem
from services.library.service import LibraryProvider, LibraryMatch, LibraryService
from services.library.plex import PlexLibraryProvider
from services.library.emby import EmbyLibraryProvider
from services.youtube import YouTubeService
from services.watchlist import WatchlistService, WatchlistEntry, WatchlistData, VALID_STATES, VALID_TRANSITIONS
from services.recommendations import RecommendationService, Candidate, EnrichedCandidate
from services.qbittorrent import QBittorrentService
from services.media_status import MediaStatusService, StatusSnapshot
from services.download import DownloadService

__all__ = [
    "BaseService",
    "PlexService", "PlexMovie", "PlexShow",
    "RadarrService", "RadarrMovie", "RadarrQueueItem", "RadarrQualityProfile", "RadarrRootFolder", "RadarrAddResult",
    "SonarrService", "SonarrSeries", "SonarrQueueItem", "SonarrQualityProfile", "SonarrRootFolder", "LanguageProfile", "SonarrAddResult",
    "TrailerService", "TrailerInfo",
    "TMDBService",
    "EmbyService", "EmbyItem",
    "LibraryProvider", "LibraryMatch", "LibraryService",
    "PlexLibraryProvider", "EmbyLibraryProvider",
    "YouTubeService",
    "WatchlistService", "WatchlistEntry", "WatchlistData", "VALID_STATES", "VALID_TRANSITIONS",
    "RecommendationService", "Candidate", "EnrichedCandidate",
    "QBittorrentService",
    "MediaStatusService", "StatusSnapshot",
    "DownloadService",
]