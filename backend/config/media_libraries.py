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

#: ``RKM_MEDIA_PATH`` (index 1) + optional extra roots ``RKM_MEDIA_PATH_2``, ``_3``…
_MEDIA_ROOT_KEY = re.compile(r"^RKM_MEDIA_PATH(?:_(\d+))?$")

#: Where the PRIMARY media root (``RKM_MEDIA_PATH``) is mounted in the media
#: containers — the historical path every service already uses.
PRIMARY_CONTAINER_ROOT = "/data"


def container_mount_for(index: int) -> str:
    """Container mount point for media-root index (1 → ``/data``, 2 → ``/media2``…)."""
    return PRIMARY_CONTAINER_ROOT if index <= 1 else f"/media{index}"


@dataclass(frozen=True)
class MediaRoot:
    """One host folder exposed to the media containers.

    ``host`` is the path AS WRITTEN in ``.env`` (``D:/RKM_MEDIA``); ``container``
    is where the containers see it (``/data``). More than one root is normal —
    a second physical drive (movies on one, TV on another) is mounted at
    ``/media2`` and declared as ``RKM_MEDIA_PATH_2``.
    """

    host: str
    container: str

    @property
    def label(self) -> str:
        return f"{self.host} → {self.container}"


def media_roots(env: Dict[str, str]) -> Tuple[List["MediaRoot"], List[str]]:
    """``(roots, warnings)`` — every configured media root, primary first.

    ``RKM_MEDIA_PATH`` → ``/data``; ``RKM_MEDIA_PATH_2`` → ``/media2``;
    ``RKM_MEDIA_PATH_3`` → ``/media3`` … (the compose file mounts exactly these
    container paths). Blank keys are ignored. A host path configured twice keeps
    its FIRST mount and warns — the duplicate mount would only expose the same
    folders a second time (and would produce duplicate libraries).
    """
    entries: List[Tuple[int, str, str]] = []
    for key, value in (env or {}).items():
        m = _MEDIA_ROOT_KEY.match(str(key).strip())
        if not m:
            continue
        idx = int(m.group(1) or 1)
        host = normalize_media_path(str(value or ""))
        if not host:
            continue
        entries.append((idx, str(key).strip(), host))
    entries.sort(key=lambda t: t[0])

    roots: List[MediaRoot] = []
    warnings: List[str] = []
    seen: Dict[str, str] = {}
    for idx, key, host in entries:
        k = host.casefold()
        if k in seen:
            warnings.append(f"{key}: '{host}' is already mounted at {seen[k]} — "
                            "the duplicate media root is ignored")
            continue
        mount = container_mount_for(idx)
        seen[k] = mount
        roots.append(MediaRoot(host=host, container=mount))
    return roots, warnings


def _roots_from(arg: object) -> List[MediaRoot]:
    """Accept the historical single-root string OR a ``MediaRoot`` list."""
    if isinstance(arg, str):
        s = normalize_media_path(arg)
        return [MediaRoot(host=s, container=PRIMARY_CONTAINER_ROOT)] if s else []
    if not arg:
        return []
    return [
        r if isinstance(r, MediaRoot) else MediaRoot(host=normalize_media_path(str(r)),
                                                     container=PRIMARY_CONTAINER_ROOT)
        for r in arg  # type: ignore[union-attr]
    ]



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


def translate_media_path(
    path: str, media_root: object = ""
) -> Tuple[str, str]:
    """Return ``(container_path, warning)`` for a configured PATH.

    The media containers see each host media root at a FIXED container path:
    ``RKM_MEDIA_PATH`` at ``/data``, ``RKM_MEDIA_PATH_2`` at ``/media2`` … So a
    PATH may be written EITHER way:

    - already container-style (``/data/Movies Kids``, ``/media2/TV Shows``) →
      used as-is;
    - host-style under ANY configured root (``D:/RKM_MEDIA/Movies Kids`` with
      ``RKM_MEDIA_PATH=D:/RKM_MEDIA``, ``B:/RKM_MEDIA/TV Shows`` with
      ``RKM_MEDIA_PATH_2=B:/RKM_MEDIA``) → translated to that root's container
      path. When roots nest, the LONGEST matching host path wins.

    ``media_root`` accepts either the historical single host-path string (mapped
    to ``/data``) or the ``MediaRoot`` list from :func:`media_roots`.

    A host path OUTSIDE every configured root cannot be mounted by the stack; it
    is returned unchanged with a clear warning (the directory+server match will
    then surface it as unresolved rather than pretending it works).
    """
    p = normalize_media_path(path)
    if not p:
        return "", ""
    if p.startswith("/"):
        return p, ""

    roots = _roots_from(media_root)
    if not roots:
        return p, ("PATH looks like a host path but RKM_MEDIA_PATH is not set — "
                   "cannot translate it to the container path Jellyfin uses")

    best: Tuple[MediaRoot, str] | None = None
    for r in roots:
        h = r.host.casefold()
        if p.casefold() == h:
            rel = ""
        elif p.casefold().startswith(h + "/"):
            rel = p[len(r.host):].lstrip("/")
        else:
            continue
        if best is None or len(r.host) > len(best[0].host):
            best = (r, rel)

    if best is None:
        if len(roots) == 1:
            return p, (f"'{path}' is outside RKM_MEDIA_PATH ('{roots[0].host}') — it cannot "
                       "be mounted into the media containers, so Jellyfin cannot scan it "
                       "(a media folder on ANOTHER drive must first be declared as "
                       "RKM_MEDIA_PATH_2 in .env)")
        listing = ", ".join(r.label for r in roots)
        return p, (f"'{path}' is outside every configured media root ({listing}) — it "
                   "cannot be mounted into the media containers, so Jellyfin cannot "
                   "scan it (add the drive as RKM_MEDIA_PATH_2/3 in .env)")

    root, rel = best
    return (f"{root.container}/{rel}" if rel else root.container), ""


def parse_media_libraries(env: Dict[str, str]) -> Tuple[List[MediaLibrary], List[str]]:
    """Parse every ``MEDIA_LIBRARY_N_NAME``/``MEDIA_LIBRARY_N_PATH`` pair.

    Returns ``(libraries, warnings)`` ordered by ascending N. Entries missing a
    NAME or a PATH are skipped with a clear warning (never silently dropped).
    Duplicate display names / duplicate paths also warn — the sidebar keys off
    the folder id, but humans expect unique names.

    ``PATH`` may be written as the media server's own container path
    (``/data/...``, ``/media2/...``) or as a host path under ANY configured
    media root (``RKM_MEDIA_PATH``, ``RKM_MEDIA_PATH_2`` …) — both are
    normalised to the container path here, in the ONE config layer, so the api
    and the provisioner always agree. ``MEDIA_LIBRARY_N_TYPE`` (movies | tvshows
    | mixed) is an optional hint used when Jellyfin creates the library; it
    defaults to ``mixed``.
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

    roots, root_warnings = media_roots(env or {})
    warnings.extend(root_warnings)

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
        container_path, path_warning = translate_media_path(path, roots)
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
