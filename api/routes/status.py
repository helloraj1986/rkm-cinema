"""Status endpoint - per-title download state computation."""
import logging
from fastapi import APIRouter
from api.models import StatusResponse, StatusEntry
from config.settings import get_config
from services import RadarrService, SonarrService, PlexService
from services.watchlist import WatchlistService

router = APIRouter()
logger = logging.getLogger("rkm.api.status")


def _qbit_torrents():
    """Get qBittorrent torrents."""
    import urllib.request
    import json
    cfg = get_config()
    url = f"{cfg.QBITTORRENT_URL}/api/v2/torrents/info"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RKM-Cinema/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)
    except Exception:
        return []


def _qbit_match(title: str, year: str = "") -> dict | None:
    """Find qBittorrent torrent matching title."""
    import re
    STOP = {"the", "and", "for", "not", "but", "are", "all", "any", "was", "you",
            "your", "his", "her", "with", "from", "that", "this", "have", "has"}
    key = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    words = {w for w in key.split() if len(w) > 3 and w not in STOP}
    if not words:
        return None

    best, best_score = None, 0
    for t in _qbit_torrents():
        name = re.sub(r"[^a-z0-9]+", " ", (t.get("name") or "").lower())
        nwords = set(name.split())
        score = len(words & nwords)
        if score > best_score:
            best_score, best = score, t

    if best and best_score >= 1 and best_score / len(words) >= 0.5:
        return best
    return None


def _qbit_state(t: dict) -> dict:
    """Compact download-state from qBittorrent torrent."""
    prog = round(float(t.get("progress") or 0) * 100)
    speed = float(t.get("dlspeed") or 0) / 1e6  # MB/s
    eta = int(t.get("eta") or -1)
    return {
        "progress": prog,
        "speed": round(speed, 2),
        "eta": eta if eta >= 0 else None,
        "qbitState": t.get("state") or "",
        "qbitName": (t.get("name") or "")[:60],
    }


def _queue_pct(q: dict) -> int:
    """Calculate queue progress percentage."""
    try:
        total = float(q.get("size") or 0)
        left = float(q.get("sizeleft") or 0)
        if total <= 0:
            return 0
        return max(0, min(99, int((1 - left / total) * 100)))
    except Exception:
        return 0


@router.get("/status", response_model=StatusResponse)
def get_status():
    """Per-title Radarr/Sonarr state with qBittorrent enrichment."""
    cfg = get_config()

    wl = WatchlistService()
    data = wl.load()
    entries = data.pending + data.recommended

    radarr = RadarrService() if cfg.RADARR_API_KEY else None
    sonarr = SonarrService() if cfg.SONARR_API_KEY else None
    plex = PlexService() if cfg.PLEX_URL and cfg.PLEX_TOKEN else None

    r_movies = radarr.get_movies() if radarr else []
    r_queue = radarr.get_queue() if radarr else []
    s_series = sonarr.get_series() if sonarr else []
    s_queue = sonarr.get_queue() if sonarr else []

    queue_by_movie = {str(q.movieId): q for q in r_queue}
    queue_by_series = {str(q.seriesId): q for q in s_queue}

    indexer_issue = radarr.get_indexer_health() if radarr else None

    statuses = {}

    for entry in entries:
        imdb = entry.imdbId
        tmdb_id = entry.tmdbId
        is_series = entry.isSeries

        # --- Plex is the source of truth ---
        # If the title is already in Plex, it is available regardless of what
        # Radarr/Sonarr report (a stale/not_added *arr record is irrelevant).
        if plex and plex.has_media(entry.title, entry.year, is_series):
            plex_url = plex.plex_url_for(entry.title, entry.year, is_series) if plex else None
            emby_url = plex.emby_url_for(entry.title) if plex else None
            statuses[imdb] = StatusEntry(
                state="available",
                service="sonarr" if is_series else "radarr",
                detail="Available in Plex",
                plexUrl=plex_url or "",
                embyUrl=emby_url or "",
            )
            continue

        if is_series:
            # TV series via Sonarr
            tvdb_id = sonarr.resolve_tvdb_id(imdb) if sonarr else None
            rec = next((s for s in s_series if s.tvdbId == tvdb_id), None) if tvdb_id else None

            if not rec:
                statuses[imdb] = StatusEntry(state="not_added", service="sonarr")
                continue

            q = queue_by_series.get(str(rec.id))
            stats = rec.statistics or {}
            downloaded = int(stats.get("episodeFileCount", 0)) > 0

            if downloaded:
                # Get Plex and Emby deep links
                plex_url = plex.plex_url_for(entry.title, entry.year, True) if plex else None
                emby_url = plex.emby_url_for(entry.title) if plex else None
                statuses[imdb] = StatusEntry(
                    state="available", service="sonarr",
                    detail="Available in Plex", plexKey=rec.id,
                    plexUrl=plex_url or "",
                    embyUrl=emby_url or ""
                )
            elif downloaded:
                statuses[imdb] = StatusEntry(
                    state="downloaded", service="sonarr",
                    detail="In library"
                )
            elif q:
                statuses[imdb] = StatusEntry(
                    state="downloading", service="sonarr",
                    progress=_queue_pct(q.__dict__ if hasattr(q, '__dict__') else q)
                )
            else:
                detail = "Requested"
                if indexer_issue:
                    detail = f"Waiting — search indexers down"
                statuses[imdb] = StatusEntry(state="requested", service="sonarr", detail=detail)

        else:
            # Movie via Radarr
            rec = next((m for m in r_movies if m.tmdbId == tmdb_id), None)

            if not rec:
                statuses[imdb] = StatusEntry(state="not_added", service="radarr")
                continue

            q = queue_by_movie.get(str(rec.id))

            if rec.hasFile:
                # Get Plex and Emby deep links
                plex_url = plex.plex_url_for(entry.title, entry.year, False) if plex else None
                emby_url = plex.emby_url_for(entry.title) if plex else None
                statuses[imdb] = StatusEntry(
                    state="downloaded", service="radarr",
                    detail="In library",
                    plexUrl=plex_url or "",
                    embyUrl=emby_url or ""
                )
            elif q and q.status != "completed":
                st = StatusEntry(
                    state="downloading", service="radarr",
                    progress=_queue_pct(q.__dict__ if hasattr(q, '__dict__') else q)
                )
                # Enrich with qBittorrent if downloadId matches
                t = next((x for x in _qbit_torrents() if x.get("hash") == q.downloadId), None)
                if t:
                    st.progress = _qbit_state(t)["progress"]
                    st.speed = _qbit_state(t)["speed"]
                    st.eta = _qbit_state(t)["eta"]
                    st.qbitState = _qbit_state(t)["qbitState"]
                    st.qbitName = _qbit_state(t)["qbitName"]
                statuses[imdb] = st
            elif q and q.status == "completed":
                statuses[imdb] = StatusEntry(
                    state="downloaded", service="radarr",
                    detail="In library", progress=100
                )
            else:
                # Check qBittorrent directly
                t = _qbit_match(rec.title, str(rec.year))
                if t and float(t.get("progress") or 0) < 1.0:
                    qs = _qbit_state(t)
                    statuses[imdb] = StatusEntry(
                        state="downloading", service="radarr",
                        **qs, detail="Active in qBittorrent"
                    )
                elif t and float(t.get("progress") or 0) >= 1.0:
                    qs = _qbit_state(t)
                    statuses[imdb] = StatusEntry(
                        state="downloaded", service="radarr",
                        progress=100, **qs, detail="Downloaded — awaiting import"
                    )
                else:
                    detail = "Requested"
                    if indexer_issue:
                        detail = f"Waiting — search indexers down"
                    statuses[imdb] = StatusEntry(state="requested", service="radarr", detail=detail)

    return StatusResponse(statuses=statuses, indexerIssue=indexer_issue)