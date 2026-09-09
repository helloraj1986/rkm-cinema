# Configurable Media Libraries — Plan

**Branch:** `feat/configurable-media-libraries` (from main @ `9328c9e`)
**Date:** 2026-09-10
**Spec:** RKM Cinema media folders fully configurable via `.env` (`MEDIA_LIBRARY_N_NAME` + `MEDIA_LIBRARY_N_PATH`); the sidebar renders configured library names and each library page lists media from its folder.

## Current state (verified)

- RKM reads media through a single **media-server provider** (`services/library/*`): Jellyfin (bundled stack), Emby or Plex. It does **not** scan folders itself — the server owns the libraries.
- The live bundled Jellyfin exposes exactly its server libraries via `GET /Library/VirtualFolders` (admin): `[{Name, CollectionType, Locations: ["/data/media/_movie"], ItemId, PrimaryImageItemId}]`. Live-probed 2026-09-10.
- Items **inside one library folder** come from `GET /Users/{uid}/Items?ParentId={folderItemId}&Recursive=true&IncludeItemTypes=Movie,Series&Fields=…` — live-verified: Movies folder (`f137a2dd…`) → 6 movies; TV Shows folder (`767bffe4…`) → 3 Body Problem.
- The UI today **hardcodes** a type-based split: sidebar Browse group has static `Movies` → `/library/movies` and `TV Shows` → `/library/shows`; `LibraryFolderView kind="movies"|"shows"` filters the **whole-server** `/api/library/items` list client-side (`libraryItemsByType`), which is wrong as soon as libraries are arbitrary folders (e.g. a mixed "Anime" folder, a "4K Movies" folder, or two movie folders).
- Config already has one central settings layer (`backend/config/settings.py`) — the single reader of `.env` → this is where the new keys are parsed (requirement: no direct `.env` reads elsewhere).

## Design decisions

1. **`.env` is the single declaration point** (per user clarification 2026-09-10): `MEDIA_LIBRARY_N_NAME` = user-facing name shown in the sidebar; `MEDIA_LIBRARY_N_PATH` = the **Jellyfin media path** for that library (the same value the server reports, e.g. `/data/media/_movie`). Arbitrary N (`_1`, `_2`, …). The internal key is **never** displayed.
2. **Configured PATH is matched to a real server folder** (by path first, normalised; name as a secondary fallback). A configured library that resolves → clicking it lists that folder's items (`ParentId` scope). One that does not resolve (or the server is unreachable) → still shown with a clear **warning** state (missing/unreachable folder), never a crash.
3. **Zero configured libraries = server folders as defaults** (sidebar shows the provider's own folder names, e.g. Movies / TV Shows). This keeps the current out-of-the-box experience with **no hardcoded names or paths** anywhere.
4. **Provider capability surface** (ABC defaults, additive): `library_folders()` and `items_in_folder(folder_id)`. Jellyfin implements both fully. Emby mirrors the Jellyfin `VirtualFolders`/`ParentId` shape. Plex keeps the ABC default (Plex is the legacy watch-link backend; the bundled/current library source is Jellyfin) — the UI degrades to the "no library folders" empty state when the provider can't enumerate.
5. **Item scoping is by folder, not by type.** The folder page fetches `…/folders/{folderId}/items` (movies + series **inside that folder**), replacing the client-side whole-server type split for library pages. Home/Discover/global search keep using the existing whole-server endpoints untouched (ADR-0001 additive-only).
6. **Path handling:** store values verbatim (spaces/drives safe — `.env` values are read whole, never split on whitespace); normalise only for comparison (trim, backslash→slash, trailing slash stripped, case-insensitive). No filesystem scanning inside the api container — the server's folder list is the source of truth for "exists".
7. **Future-proofing:** the config layer returns a plain `MediaLibrary(name, path)` list via `Config.media_libraries`; matching lives in a pure resolver — the env reader can later be swapped for a Settings UI/database without touching the UI or matching logic.

## API contract (additive, ADR-0001)

New paths (contract count +2):

- `GET /api/library/folders` → `{provider, folders: [{id, name, path, collection_type}], configured: [{name, path, folder_id, ok, warning}]}` — server folders + how configured libraries map onto them (drives the sidebar + warnings).
- `GET /api/library/folders/{folder_id}/items` → `{provider, folder_id, items: [MediaItem…]}` — one library folder's Movie+Series rows (same public item shape as `/api/library/items`, so cards/rows/player wiring reuse unchanged).

Existing endpoints are untouched.

## Phases (one commit per phase, gates green after every phase)

- **Phase 0 — probe (no commit):** VirtualFolders + ParentId item shapes live-verified (done above; documented in PROGRESS).
- **Phase 1 — config layer:** `MediaLibrary` dataclass + `parse_media_libraries()` in `backend/config/`; `Config.media_libraries` + warnings; env-keys override pass-through for `MEDIA_LIBRARY_*`; unit tests (spaces, drives, gaps, missing name/path, arbitrary N). No UI.
- **Phase 2 — provider folders:** ABC `library_folders()` / `items_in_folder()` (default `[]`); Jellyfin implementation (VirtualFolders + ParentId items, TTL-cached like `_get_items`); Emby mirror; pure `match_libraries()` resolver with path/name fallback + tests (fake provider + resolver unit tests).
- **Phase 3 — API:** models + `GET /api/library/folders`, `GET /api/library/folders/{folder_id}/items` in `routes/library.py` (first-provider-wins, partial-200 on failure like existing routes); route tests; regenerate `docs/api/openapi.v1.json`; contract count recorded.
- **Phase 4 — frontend client:** types + `getLibraryFolders()` / `getFolderItems(id)` in `client.ts`; hooks in `features/library/api.ts`; folder-scoped helpers in `lib.ts`.
- **Phase 5 — UI:** Sidebar replaces the hardcoded Browse Movies/TV Shows entries with a **Libraries** group rendered from the folders endpoint (configured names when present, else server folder names; warning glyph on unresolved); router: `/library/folder/:folderId` renders a kind-free folder page (heading = resolved name, folder-scoped items); `/library/movies` + `/library/shows` become aliases that resolve to the matching configured/server library (preserving `?genre=`), so global-search genre links keep working; MobileNav tabs become Home + first two libraries (icon by folder collection type); empty/error states for no folders.
- **Phase 6 — sweep + docs:** remove remaining type-split hardcodes where folders now own the pages (keep type-based helpers only where still used); `.env.example` media-libraries section; add the **live** two-library block to `.env` (Movies → `/data/media/_movie`, TV Shows → `/data/media/_tv` — matches the provisioner, so the deployed stack resolves cleanly); Settings/Config view gains the library warnings; PROGRESS.md record.

## Gates after every phase

- Backend: `cd backend && python -m pytest` · `ruff check .`
- Frontend: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`
- Contract: `python backend/scripts/snapshot_openapi.py` and confirm only the two additive paths.

## Acceptance (RKM-HP, user-driven)

`.\\bootstrap.ps1` (api + web both changed) → sidebar shows the configured **Libraries** group with the `.env` names (never `MEDIA_LIBRARY_1_NAME`); clicking each lists that folder's media; a deliberately-bad configured PATH shows the warning state without breaking the app. Then FF merge → main + `experiment/bundled-docker-stack` + push (user drives).
