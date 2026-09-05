"""Library endpoint — unified library info for the configured backend(s).

Thin route: delegates to :meth:`services.library.build_library_service`, so it
serves Plex+Emby (default) OR a single Jellyfin/Emby (bundled stack) with no
provider-specific branches here. Preserves the legacy semantics: the first
provider that yields a valid read becomes the view; a provider failure falls
through to the next; if ALL fail the endpoint returns a partial 200
(``available=False``) — never an HTTP error. URL bases are owned by the
providers, not duplicated.
"""
from fastapi import APIRouter

from api.models import LibraryResponse
from config.settings import get_config
from services.library import build_library_service


router = APIRouter()


def _counts(provider) -> dict:
    """Counts from a provider; RAISES on failure so the route can fall through.

    Handles the three provider shapes generically: the Plex shape
    (``provider._plex.get_library_counts()``) or Emby/Jellyfin's ``_get_items``
    listing. We deliberately do NOT probe a provider-level ``get_library_counts``
    attribute, because some test fakes' ``__getattr__`` raises (not ``AttributeError``)
    and would trip the probe; the real backends are covered by the two branches here.
    """
    plex = getattr(provider, "_plex", None)
    if plex is not None and hasattr(plex, "get_library_counts"):
        return plex.get_library_counts() or {"movie": 0, "show": 0}
    if hasattr(provider, "_get_items"):
        return {
            "movie": len(provider._get_items("Movie")),
            "show": len(provider._get_items("Series")),
        }
    raise RuntimeError(f"{provider.name}: no counts source")


def _browser_base(provider) -> str:
    base = provider._browser_base()
    if not base.endswith("/web/index.html"):
        base = base.rstrip("/") + "/web/index.html"
    return base


@router.get("/library", response_model=LibraryResponse)
def get_library():
    """First provider to read successfully becomes the view; else partial 200."""
    cfg = get_config()
    service = build_library_service(cfg)

    if service is None or not service.providers:
        return LibraryResponse(
            provider=None, available=False,
            counts={"movie": 0, "show": 0}, recent=[], server=None, urls={})

    urls = {}
    for p in service.providers:
        try:
            urls[p.name] = _browser_base(p)
        except Exception:
            urls[p.name] = None

    for p in service.providers:
        try:
            counts = _counts(p)
            recent = p.recently_added(limit=8)
            return LibraryResponse(
                provider=p.name, available=True,
                counts=counts, recent=recent,
                server=p.name.capitalize(), urls=urls)
        except Exception:
            continue

    # Every provider failed → partial 200, not 5xx.
    return LibraryResponse(
        provider=None, available=False,
        counts={"movie": 0, "show": 0}, recent=[], server=None, urls=urls)