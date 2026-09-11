# ADR-0005: Subtitles from OpenSubtitles.com, delivered as sidecar files by the api

- **Status:** Accepted
- **Date:** 2026-09-12
- **Phase:** `feat/subtitles-opensubtitles` (`SUBTITLES_OPENSUBTITLES_PLAN.md`, phases 0–5)

## Context

The app could already *serve* subtitles it did not own: it lists an item's text-subtitle
tracks and proxies them to the browser as WebVTT (`/api/jellyfin/playback-info`,
`/api/jellyfin/subtitle`). What it could not do was **find, fetch and keep** a subtitle for a
title that has none — the user had to leave the app, visit a subtitle site, download a file,
name it correctly and place it beside the media on the right drive. The request was to make
that happen inside the player, with the choice remembered per title.

Four measurements shaped the decision, all taken before any code was written:

1. **The bundled Jellyfin has NO subtitle provider installed.** `/Plugins` lists AudioDB,
   MusicBrainz, OMDb, Studio Images and TMDb only, and
   `GET /Items/{id}/RemoteSearch/Subtitles/eng` returns `[]`. The server-side route that
   looks like the obvious answer is dead until something is installed into Jellyfin.
2. **OpenSubtitles.com's REST API requires an `Api-Key` header on every call** — an
   application identity, free to register, separate from the *user* login
   (`/login` → JWT, needed for `/download` and `/infos/user`). The original request listed
   only a username/password, which cannot work on its own. This was raised with the user
   rather than silently compensated for.
3. **The api's media mounts are read-write.** The same container paths Jellyfin reports as
   an item's `Path` (`/data/Movies/…`) are writable from the api container, so the api can
   deliver a subtitle *as a file* — no server plugin, no upload API, no transcoding.
4. **Usage is metered and the quota is not a constant.** Downloads count (searching does
   not): anonymous is 5 per 24 h per IP, a signed-in free account is higher, VIP higher
   again, and three sources disagreed on the exact number. `/download` returns `remaining`
   + a reset time, and `/infos/user` returns `allowed_downloads`/`remaining_downloads`.

Stream indices in Jellyfin are **positional**: attaching a subtitle shifts every index after
it, so a subtitle choice cannot be stored as an index.

## Decision

**Option A — the api owns an isolated OpenSubtitles client and hands Jellyfin a sidecar
`.srt` beside the media file.** No Jellyfin plugin is installed.

- `services/opensubtitles.py` — the vendor client: login (JWT cached, one re-login on 401),
  id-keyed search (`tmdb_id` → `imdb_id` → `title`+`year`, episode by series title +
  season/episode), `download(file_id)` → bytes, `user_info()`, and a typed error taxonomy
  (`NotConfigured`, `AuthFailed`, `QuotaExhausted`, `RateLimited`, `NoResults`,
  `UnsupportedFormat`, `Transport`). A `/download` POST is **never retried** — it may
  already have been charged; GETs, including 5xx, get exactly one retry. A raw network
  failure is wrapped into `TransportError` so no caller has to know which layer raised it.
- `services/subtitles.py` — delivery: write `<video stem>.<lang>.srt` beside the media
  atomically (UTF-8, encoding-normalised), **reuse** an existing same-language sidecar, fall
  back to `POST /Videos/{itemId}/Subtitles` (JSON + base64 `Data`) when the file cannot be
  written, refresh the **ITEM** (never a library scan), then resolve the stored identity to
  the current index.
- `services/subtitle_store.py` — one JSON file (`<media root>/rkm/subtitles.json`, atomic,
  corrupt-tolerant) holding per-item **preferences** (an identity: provider + `subtitle_id` +
  language + display title) and per-subtitle **usage counts** (ours, global — they rank
  results and drive "Used N times"). JSON rather than SQLite deliberately: it matches the
  live watchlist store, needs no migration and can be extended by a future bulk fetcher
  without a schema change.
- **Credentials stay in `.env`** and reach the api only, through the render step into
  `.rkm.env`. Nothing about them — key, login, or the pre-signed download link — ever
  reaches the browser or a log line.
- **The quota is read at runtime, never hardcoded.** The panel shows "N downloads left
  today" only once the API has actually said so; before the first download the number is
  genuinely unknown and the UI stays silent rather than inventing one.

API surface is **additive only** (ADR-0001): `GET /api/jellyfin/subtitle-search`,
`POST /api/jellyfin/subtitle-select`, `POST /api/jellyfin/subtitle-disable`, plus ONE new
field on the existing `playback-info` (`preferred_subtitle`, so the player applies the
choice on load without a second round trip). Contract 38 → 41 paths.

## Alternatives rejected

- **Install the Jellyfin OpenSubtitles plugin and drive `RemoteSearch/Subtitles`.**
  Rejected. It needs its own manual catalogue install outside `bootstrap.ps1`; it keeps the
  credentials in Jellyfin's config rather than `.env`; the quota is invisible to the api, so
  "downloads left today" could not be shown honestly; and it has a documented history of
  opaque sign-in failures (`jellyfin-plugin-opensubtitles` issues #109/#159 — endless
  spinner, "Authentication to OpenSubtitles failed", "API rate limit exceeded" with nothing
  in the log).
- **Bazarr** (a dedicated subtitle container). Out of scope here — it has no in-player
  picker and no per-subtitle usage tracking. It stays a future option for *bulk* fetching;
  the store is shaped so a bulk fetcher could reuse it unchanged.
- **Storing the chosen stream index.** Rejected outright: indices are positional and our own
  download shifts them.

## Consequences

- The feature is **optional and never blocking**. Without `OPENSUBTITLES_API_KEY` everything
  else works and the picker says why the online list is empty; with the vendor down, out of
  quota, or answering something unexpected, the item's own subtitles are still listed and
  still play, and the failure appears as a non-blocking notice.
- One more **external dependency** and one more **metered quota** to live with. The quota is
  the user's real limit; the plan's live checks deliberately spend downloads one at a time
  and say so.
- The api **writes into the media folders** (sidecar files). Files we did not create are
  never rewritten or deleted, and an existing same-language sidecar is reused rather than
  replaced.
- A new `.env` key still only reaches the api through the render step, so a **credential
  change needs a full `deploy`**, not `up -d --build api`.
- The tick in the picker shows **the result the user clicked**, not the local track the
  subtitle arrived as (the server names a delivered track "English - SUBRIP - External",
  which reads as an unrelated embedded subtitle). This cost one round of user-visible
  confusion before the rule was written down and tested — see the Phase 4/`5ba203a` records
  in `PROGRESS.md`.
