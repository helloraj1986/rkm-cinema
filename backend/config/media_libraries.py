"""Configurable media libraries — parsed from ``MEDIA_LIBRARY_N_*`` .env keys.

The user-facing requirement (MEDIA_LIBRARIES_PLAN Phase 1): media folders are
declared in ONE place (the repo ``.env``) as an arbitrary list

    MEDIA_LIBRARY_1_NAME=Movies
    MEDIA_LIBRARY_1_PATH=/data/media/_movie
    MEDIA_LIBRARY_2_NAME=My Anime
    MEDIA_LIBRARY_2_PATH=F:/Media/Anime

Each entry models a library generically as ``MediaLibrary{name, path}`` where
``name`` is the user-facing label shown in the UI and ``path`` is the media
folder path on the media server (the same value the server reports for its own
library folder — RKM never scans folders itself). The internal key
(``MEDIA_LIBRARY_1_NAME``) is never displayed; only its value (``Movies``) is.

This module is the ONLY parser of these keys. ``config.settings.Config`` owns
loading the raw env; everything else consumes ``Config.media_libraries``. That
indirection keeps the source swappable later (a Settings UI / database can
produce the same ``MediaLibrary`` list without touching callers).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

#: Any positive index is allowed; scanning stops at the first N with no keys,
#: so the list stays free-form and extra trailing blank lines are harmless.
_MEDIA_LIBRARY_KEY = re.compile(r"^MEDIA_LIBRARY_(\d+)_(NAME|PATH|TYPE)$")


@dataclass(frozen=True)
class MediaLibrary:
    """One configured media library (generic — no hardcoded Movies/TV Shows)."""

    #: User-facing library name (what the sidebar shows). NEVER the env key.
    name: str
    #: Media folder path as the MEDIA SERVER sees it (Jellyfin container path,
    #: e.g. ``/data/Movies Kids``). Host-style paths (``D:/RKM_MEDIA/Movies``)
    #: are translated against ``RKM_MEDIA_PATH`` at parse time.
    path: str
    #: Optional Jellyfin collection type hint: movies | tvshows | mixed.
    #: Defaults to ``mixed`` (Jellyfin's neutral type) so the simple
    #: name+path model works without extra config.
    collection_type: str = "mixed"


#: Allowed collection types (Jellyfin), normalised. Anything else → ``mixed``.
_COLLECTION_TYPES = {
    "movie": "movies",
    "movies": "movies",
    "tv": "tvshows",
    "show": "tvshows",
    "shows": "tvshows",
    "tvshows": "tvshows",
    "series": "tvshows",
    "mixed": "mixed",
    "homevideos": "homevideos",
    "music": "music",
}


def normalize_collection_type(raw: str) -> str:
    """Normalise a MEDIA_LIBRARY_N_TYPE value (unknown/blank → ``mixed``)."""
    return _COLLECTION_TYPES.get(str(raw or "").strip().lower(), "mixed")


def translate_media_path(path: str, media_root: str = "") -> Tuple[str, str]:
    """Return ``(container_path, warning)`` for a configured PATH.

    The api + Jellyfin containers see the host media root (``RKM_MEDIA_PATH``)
    at ``/data``. So a PATH may be written EITHER way:

    - already container-style (``/data/Movies Kids``) → used as-is;
    - host-style under the media root (``D:/RKM_MEDIA/Movies Kids`` with
      ``RKM_MEDIA_PATH=D:/RKM_MEDIA``) → translated to ``/data/Movies Kids``.

    A host path OUTSIDE the media root cannot be mounted by the stack; it is
    returned unchanged with a clear warning (the directory+server match will
    then surface it as unresolved rather than pretending it works).
    """
    p = normalize_media_path(path)
    if not p:
        return "", ""
    if p.startswith("/"):
        return p, ""

    root = normalize_media_path(media_root)
    if not root:
        return p, ("PATH looks like a host path but RKM_MEDIA_PATH is not set — "
                   "cannot translate it to the container path Jellyfin uses")
    if p.casefold() == root.casefold():
        return "/data", ""
    prefix = root.casefold() + "/"
    if p.casefold().startswith(prefix):
        rel = p[len(root):].lstrip("/")
        return f"/data/{rel}", ""
    return p, (f"'{path}' is outside RKM_MEDIA_PATH ('{media_root}') — it cannot be "
               "mounted into the media containers, so Jellyfin cannot scan it")


def parse_media_libraries(env: Dict[str, str]) -> Tuple[List[MediaLibrary], List[str]]:
    """Parse every ``MEDIA_LIBRARY_N_NAME``/``MEDIA_LIBRARY_N_PATH`` pair.

    Returns ``(libraries, warnings)`` ordered by ascending N. Entries missing a
    NAME or a PATH are skipped with a clear warning (never silently dropped).
    Duplicate display names / duplicate paths also warn — the sidebar keys off
    the folder id, but humans expect unique names.

    ``PATH`` may be written as the media server's own container path
    (``/data/...``) or as a host path under ``RKM_MEDIA_PATH`` — both are
    normalised to the container path here, in the ONE config layer, so the api
    and the provisioner always agree. ``MEDIA_LIBRARY_N_TYPE`` (movies |
    tvshows | mixed) is an optional hint used when Jellyfin creates the
    library; it defaults to ``mixed``.
    """
    libraries: List[MediaLibrary] = []
    warnings: List[str] = []

    by_index: Dict[int, Dict[str, str]] = {}
    for key, value in (env or {}).items():
        m = _MEDIA_LIBRARY_KEY.match(key.strip())
        if not m:
            continue
        idx = int(m.group(1))
        by_index.setdefault(idx, {})[m.group(2)] = value.strip()

    if not by_index:
        return [], []

    media_root = str((env or {}).get("RKM_MEDIA_PATH") or "")

    for idx in sorted(by_index):
        pair = by_index[idx]
        name = pair.get("NAME", "")
        path = pair.get("PATH", "")
        if not name and not path:
            warnings.append(f"MEDIA_LIBRARY_{idx}: NAME and PATH are empty — library skipped")
            continue
        if not name:
            warnings.append(f"MEDIA_LIBRARY_{idx}: NAME is empty — library skipped")
            continue
        if not path:
            warnings.append(f"MEDIA_LIBRARY_{idx} ({name}): PATH is empty — library skipped")
            continue
        container_path, path_warning = translate_media_path(path, media_root)
        if path_warning:
            warnings.append(f"MEDIA_LIBRARY_{idx} ({name}): {path_warning}")
        libraries.append(MediaLibrary(
            name=name,
            path=container_path,
            collection_type=normalize_collection_type(pair.get("TYPE", "")),
        ))

    seen_names = set()
    for lib in libraries:
        key = lib.name.casefold()
        if key in seen_names:
            warnings.append(f"MEDIA_LIBRARY: duplicate library name '{lib.name}' — "
                            "sidebar names must be unique")
        seen_names.add(key)

    seen_paths = set()
    for lib in libraries:
        key = normalize_media_path(lib.path).casefold()
        if key in seen_paths:
            warnings.append(f"MEDIA_LIBRARY: duplicate media path '{lib.path}' — "
                            "two libraries cannot point at the same folder")
        seen_paths.add(key)

    return libraries, warnings


def normalize_media_path(path: str) -> str:
    """Normalise a media path for comparison only (never for display).

    - trims surrounding whitespace
    - unifies Windows backslashes to forward slashes
    - strips a single trailing slash (keeps ``/`` itself intact)
    Case is preserved here; callers may ``.casefold()`` when comparing.
    """
    p = (path or "").strip().replace("\\", "/")
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p
