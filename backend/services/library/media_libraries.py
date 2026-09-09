"""Resolve configured media libraries against a provider's real server folders.

MEDIA_LIBRARIES_PLAN design decision #2: the configured ``MEDIA_LIBRARY_N_PATH``
value is matched to a folder the media server actually exposes. The server is
the source of truth for "does this library exist" — RKM never scans folders
itself, so a configured library only becomes a live, clickable library page
when it resolves to a real server folder (``folder_id``).

Pure functions only (no I/O) so the resolution logic unit-tests without a
server. Callers feed it ``Config.media_libraries`` + the provider's
``library_folders()`` rows.
"""
from __future__ import annotations

from typing import List, Optional

from config.media_libraries import MediaLibrary, normalize_media_path


def _paths_of(folder: dict) -> List[str]:
    """Every location a server folder row reports (normalised for compare)."""
    raw = folder.get("locations") or folder.get("paths") or []
    if not raw and folder.get("path"):
        raw = [folder.get("path")]
    return [normalize_media_path(str(p)).casefold() for p in raw if str(p or "").strip()]


def match_libraries(
    configured: List[MediaLibrary],
    server_folders: List[dict],
) -> List[dict]:
    """Map configured libraries onto server folders.

    Each output row: ``{name, path, folder_id, collection_type, ok, warning}``.

    Matching order per configured library:
      1. a server folder whose reported location equals the configured PATH
         (normalised, case-insensitive);
      2. a server folder whose NAME equals the configured NAME (secondary
         fallback — some servers rename the on-disk folder);
      3. otherwise ``ok=False`` with a clear warning (the configured PATH does
         not exist on this server, or the server is unreachable/not enumerable).
    ``name`` is ALWAYS the user-facing configured value — never the env key.
    """
    out: List[dict] = []
    wanted = list(configured or [])
    if not wanted:
        return out

    folders = list(server_folders or [])
    for lib in wanted:
        row = {
            "name": lib.name,
            "path": lib.path,
            "folder_id": None,
            "collection_type": "",
            "ok": False,
            "warning": "",
        }
        target_path = normalize_media_path(lib.path).casefold()
        match = None
        for f in folders:
            if target_path and target_path in _paths_of(f):
                match = f
                break
        if match is None and lib.name:
            lname = lib.name.casefold()
            match = next((f for f in folders if str(f.get("name") or "").casefold() == lname), None)
        if match is not None:
            row["folder_id"] = str(match.get("id") or "")
            row["collection_type"] = str(match.get("collection_type") or "")
            row["ok"] = True
        else:
            if not folders:
                row["warning"] = (
                    f"'{lib.name}' could not be checked — the media server is not "
                    "reporting library folders (is it connected?)"
                )
            else:
                row["warning"] = (
                    f"'{lib.path}' does not match any library folder on the media "
                    "server — check MEDIA_LIBRARY path or the server's folders"
                )
        out.append(row)
    return out


def server_default_libraries(server_folders: List[dict]) -> List[dict]:
    """Sidebar fallback when NO libraries are configured in .env.

    Returns one row per real server folder (name/path come from the SERVER, so
    nothing is hardcoded): ``{name, path, folder_id, collection_type, ok: True}``.
    """
    out: List[dict] = []
    for f in server_folders or []:
        path = str(f.get("path") or "")
        if not path and f.get("locations"):
            path = str(f["locations"][0])
        out.append({
            "name": str(f.get("name") or ""),
            "path": path,
            "folder_id": str(f.get("id") or ""),
            "collection_type": str(f.get("collection_type") or ""),
            "ok": True,
            "warning": "",
        })
    return out


def find_folder_name(folders: List[dict], folder_id: Optional[str]) -> str:
    """Display name for a folder id (used by the folder view heading)."""
    if not folder_id:
        return ""
    for f in folders or []:
        if str(f.get("id") or "") == str(folder_id):
            return str(f.get("name") or "")
    return ""
