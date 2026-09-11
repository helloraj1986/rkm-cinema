# ADR-0004: Remove Plex/Emby support — drop `/api/plex/thumb` and the Plex/Emby response fields

- **Status:** Accepted
- **Date:** 2026-09-11
- **Phase:** `refactor/remove-plex-emby` (`docs/REMOVE_PLEX_EMBY_PLAN.md`)

## Context

ADR-0001 froze `/api` as immutable v1 and required **any** breaking change to be explicit and
recorded. The deployment that could select Plex/Emby was already retired
(`chore/retire-prod-stack`, 2026-09-11): `run-rkm-cinema.ps1` was deleted, `MEDIA_SERVER` resolves
through one rule (`config.settings.resolve_media_server`) that maps a blank/unknown/legacy value to
`jellyfin`, and the provisioner has been writing `MEDIA_SERVER: "jellyfin"` into
`shared/runtime.json` for some time. What remained was the **code**: the Plex/Emby providers, the
Plex-only artwork route, and Plex-flavoured vocabulary in the domain, the API models and the
contract — including a `Config.validate_required()` that demanded `PLEX_TOKEN` and so logged a
false `Missing required config: ['PLEX_TOKEN']` on every boot of a Jellyfin-only stack.

Three facts made the removal safe rather than hopeful:

1. **The React client reads none of the fields being removed.** `plexUrl`/`embyUrl`/`plexKey`
   appear in `frontend/src/lib/api/types.ts` only because they are generated from the snapshot;
   no component reads `plexKey`, and the watch UI keys off `jellyfinUrl`/`jellyfinItemId` (and the
   provider-keyed `watch.jellyfin` map entry).
2. **`/api/plex/thumb` has no caller in the app.** The poster path is
   `frontend/src/features/library/lib.ts::posterUrl()` → the library item's own id →
   `/api/jellyfin/poster`; the `plex/thumb` branch was a fallback for items with no library id.
3. **No data migration is involved.** The app's own store (`data/rkm/watchlist.json`) holds
   Jellyfin ids and contains zero plex/emby references — verified before starting.

## Decision

Ship the removal as a recorded breaking change, in the phased plan's order:

- **Delete** the Plex/Emby providers and their orphaned surface:
  `services/plex.py`, `services/plex_check.py`, `services/emby.py`,
  `services/library/plex.py`, `services/library/emby.py`, `api/routes/plex_thumb.py`,
  `scripts/verify_plex.py`, `scripts/add_with_plex_check.py` and their tests.
- **`/api/plex/thumb` is removed** (the route and its registration). The OpenAPI snapshot moves
  **39 → 38 paths**; nothing else in the contract moves.
- **`plexUrl`, `embyUrl`, `plexKey` are removed** from `StatusEntry`. `jellyfinUrl` and
  `jellyfinItemId` stay — they are what the client actually uses.
- **Server-neutral domain vocabulary**: `in_library`, `library_available`, `watch_url`,
  `server_item_id`. The provider-keyed `watch` map keeps its `jellyfin` key.
- **A retired `MEDIA_SERVER` value is still tolerated.** Deleting the *keys* must not make an
  un-updated `.env` on the Windows box fail to deploy: the value is still accepted and still
  resolves to Jellyfin, and the code can no longer wire a second provider.
- Regenerate `docs/api/openapi.v1.json` (`python backend/scripts/snapshot_openapi.py`) and the
  typed client (`cd frontend && npm run generate:types`) in the same change.

### What deliberately survives

- **`X-Emby-Authorization`** in `provisioner/provision.py` and the probe scripts: that *is*
  Jellyfin's own auth header (Jellyfin forked Emby). Removing it breaks provisioning.
- **"Emby-derived API shape" notes**: Jellyfin genuinely shares Emby's `/Items`,
  `/System/Info/Public` and `Imdb`/`Tmdb`/`Tvdb` provider ids.
- **"Plex-style" as a UI idiom** (preplay/detail/player design references, incl.
  `docs/PLEX_UI_PLAN.md` / `PLEX_VIEWS_PLAN.md`): a design reference, not a server.
- **The `LibraryService`/`LibraryProvider` abstraction.** Jellyfin implements it, every call site
  goes through it, and design-spec §43 ("no direct-route service branch") depends on it. This ADR
  removes two *providers*, not the seam.

## Consequences

- The contract loses one path and three optional fields. A client that read them would break; the
  only client is in this repo and does not. This is why the change is versioned by ADR rather than
  by an `/api/v1` re-cut.
- `/api/health` and `/api/config` no longer report `plex`/`emby` services; the Settings page
  renders whatever the endpoint returns, so its cards (and its `SERVICES` list) shrink with it.
- Backend test count drops with the deleted providers (502 → 476 at the time of writing); the
  surviving abstraction keeps its multi-provider collapse and failure-containment coverage via
  name-agnostic doubles.
- The retired-`MEDIA_SERVER` tolerance is now a *tested* property, not a hope: a `.env` that still
  says `MEDIA_SERVER=plex` must render AND resolve to Jellyfin.
