# ADR-0007: Offline downloads are a staged, server-packaged, byte-ranged file

- **Status:** Accepted (phase B1 built; **B2 built** — see ADR-0008; B3–B5 not built)
- **Date:** 2026-09-16
- **Phase:** `feat/offline-api` (`NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.2/§4.3/§6, phase **B1**; depends on
  the B0 spike, `apple/SPIKE_E1_E2.md`)

## Context

The app's offline story on **iOS** ends at the tailnet — and that is **one client, two devices**:
the iPhone and the iPad run the same WKWebView shell, so this work is not device-specific (⚠ the E1
measurement it rests on was taken on an **iPhone 17 Pro** simulator). Every frame it plays is proxied from Jellyfin on RKM-HP, so
a plane, a train or a flaky hotel Wi-Fi is the end of it. Workstream B is "download a film to the
device and play it with the network off", and it hung on **one question only a device could answer**.

**It has been answered.** The B0 spike (2026-09-16, iPhone 17 Pro simulator) proved in ONE run that:

* media served from **`http://127.0.0.1`** inside the app's own `WKWebView` **plays, and SEEKS** —
  the wire shows `206 bytes=0-1/1128375` then the body range, WebKit reports
  `metadata ok 960x540 duration=5.01`, `seek to 2.51 -> ok`, `play=ok`;
* the same file through a **`WKURLSchemeHandler`** fails **for real** (`mediaError=code=4` with bytes
  served), so `§4.1`'s rejection of a custom scheme is measured rather than assumed;
* the WKWebView exposes **no `navigator.serviceWorker`**, even on a secure origin
  (`sw=false`, proved by `navigator.storage` existing on `127.0.0.1` and not on the HTTP origin) —
  so **A0's cache headers are the offline-shell story** and no service-worker work is planned.

So the device's job is to **obtain a real file and serve it to itself later**. That makes the server's
job precise, and it is what B1 builds:

> package one title into a file the device can hold, hand it over with real `Content-Length`, real
> `Range`/`206` (so the transfer is resumable), and be honest about every byte's state.

**Two networks are involved, deliberately.** The download rides the **tailnet** (`rkm-hp…:8124`,
≈3.8 MB/s measured — roughly 9 minutes for a 2 GB film), while playback is **loopback**, i.e. it works
with Tailscale down. Staging is therefore sized for tailnet transfer times, not LAN ones, and the
device needs Tailscale *connected* to download (which the app already requires today).

## Decision

**B1 = a staging store plus six session-scoped routes.** `POST /api/offline/prepare` packages a
title; `GET /api/offline/bundle/{id}` previews it; `GET /api/offline/status/{id}` answers from disk;
`HEAD`/`GET /api/offline/file/{id}` serve it byte-ranged; `DELETE /api/offline/{id}` drops the copy.

**D1 — staging lives on the api's own `rkm_shared` volume (`/shared/offline`), never inside a media
root.** A directory of downloadable films under `D:\RKM_MEDIA` is a directory **Jellyfin scans**, and
the household's library would grow phantom items — a self-inflicted bug with a delayed symptom. The
`/shared` volume is already mounted, already persistent across every rebuild, so **B1 needed no
compose change at all**. ⚠ The trade-off, stated plainly: `/shared` is the **Docker host's disk**, not
the media drive, which is why the byte cap below exists and why `RKM_OFFLINE_STAGING` is configurable
for the day he wants staging on a roomier disk.

**D2 — a direct-playable title is NOT copied: its artefact IS the library file.** §4.2's "the file as
it is — no server CPU" taken literally. Copying a 40 GB film so that the same bytes can be handed to
a phone is pure waste, and the api container has the media roots mounted read-write already. The
manifest records `borrowed: true`, and **both `delete` and the TTL sweep respect it** — "delete this
download" must never unlink the household's own media file. That is the single destructive mistake
this feature could make, and it is pinned by a test rather than by care.

**D3 — packaging drives Jellyfin's own transcode pipe into a file; the api image gains no
dependency.** The mode ladder is the **player's own** (`pickStreamMode`,
`frontend/src/features/playback/lib.ts`), mirrored rather than re-derived, because a downloaded film
is played by the *same* WKWebView that streams it. ⚠ That is why HEVC lands on `transcode`: the app's
ladder does not treat HEVC as safe, so a "clever" remux here would hand the device a file the player
refuses. The plan's own objection — "Jellyfin's transcode pipe is tied to a playback session, which
is the wrong lifetime for a download" — is exactly why the pipe **fills a file** rather than being
relayed: the pipe is transient, the file is not.

⚠⚠ **AND THE MIRRORED LADDER WAS WRONG IN TWO PLACES — FOUND BY THE LIVE GATE, NOT BY READING**
(2026-09-16, the deployed api, 15 real library items; the phase's step-5 `curl` gate):

| Live facts (Jellyfin's own values) | Mirrored rule said | Correct | Titles affected |
|---|---|---|---|
| `Container = "mov,mp4,m4a,3gp,3g2,mj2"`, h264, aac — **an ordinary MP4** | `remux` | **`direct`** | 13 of 13 MP4s sampled |
| `Container = "mkv"`, codec `av1`, opus | `transcode` (a full re-encode) | **`remux`** | 1 |

**Jellyfin's `Container` is ffprobe's `format_name`: a COMMA-SEPARATED DEMUXER LIST, not an
extension.** An MP4 arrives as `"mov,mp4,m4a,3gp,3g2,mj2"` and an MKV as plain `"mkv"`, so a
direct-play check against bare extensions (`{mp4, m4v, mov}`) **never matches a real MP4** — every MP4
took the remux rung, i.e. a **full re-copy of the film through Jellyfin plus a full-size staging
file**, for a file the device could hold and play as-is. And ffprobe spells the codec **`av1`** where
the ladder's safe set says **`av01`**, so one real title was being re-encoded instead of copied.
B1 therefore matches the container by **FAMILY** (mp4-family list first, then Matroska — ⚠ the WebM and
MKV demuxers share `"matroska,webm"`, so the codec decides which is direct) and normalises the codec
spelling. ⚠⚠ **The same container mismatch exists in the PLAYER's own `DIRECT_CONTAINERS`
(`frontend/src/features/playback/lib.ts`), which is where this list came from** — reported to the user
and NOT changed here: altering player routing changes live playback for every film, which is a
separate decision from this phase. **The claim is one line of arithmetic, so it is checkable rather
than asserted:** `Player.tsx` passes `info.container` (the `playback-info` value, unmodified) into
`pickStreamMode`, which lowercases it and asks `DIRECT_CONTAINERS.has(c)` — and
`"mov,mp4,m4a,3gp,3g2,mj2"` is **not** a member of `{"mp4","m4v","mov","webm"}`. Both call sites
(`Player.tsx:78` and `:289`) use the same raw value.

**D4 — publish atomically: `.part` → `os.replace`.** The final path exists only when the transfer
finished, so `ready` and `Content-Length` cannot describe half a film. A crash leaves a `.part`,
never a serveable fragment, and a download pointed at an unfinished rendition is answered **409
(wait)**, not 404 (absent) and not the partial bytes.

**D5 — the routes are keyed by ITEM, not by the plan's `job_id` (deviation, §4.3).** Both the page
and the native side know the title they are asking about; a job id would be a mapping with no user,
and a download that can be resumed must be addressable after a restart. `mode` is accepted on
`prepare`/`bundle` and echoed everywhere. **Also deferred, deliberately: `GET
/api/offline/subtitles/{id}`.** The device can already fetch a text track as WebVTT from the existing
`/api/jellyfin/subtitle` proxy at download time, so a second route would duplicate it; it gets added
in B4 only if the bundle turns out to need a stable per-language URL.

**D6 — every route is SESSION-scoped, and that is a decision, not an inheritance.** Downloading a
title is a **household** feature, exactly like `POST /api/media/{id}/request`. Promoting these to
`require_admin_session` would hide the feature from every member — and would also break the Phase-E
pin (`test_the_four_phase_E_routes_are_the_ones_that_changed`: the admin-gated set outside
`/api/admin/*` is those four routes and nothing else). ⚠ Recorded because the media server has **one
credential**, so the staged *file* is not per-profile: what is per-profile is which titles a member
may ask for, and the media call that packages them runs as the acting profile
(`acting_media_token`).

**D7 — state is derived from DISK, never from an in-memory registry.** A manifest says *what*
something is; the filesystem says *whether it is there*, and the filesystem wins. Sizes come from
`os.stat` of the file about to be read. A packaging job whose heartbeat has stopped **and** which has
no live writer is reported `failed` with its reason (an api restart cannot leave a spinner over
nothing), while a failed job *stays* failed until something retries it — reporting it as `missing`
would throw away the only useful sentence and hide that a retry is the fix.

**D8 — the TTL is swept lazily, at `prepare`, not by a timer.** 48 h after last **access**
(`RKM_OFFLINE_TTL_HOURS`, `0` = never). The moment stale bytes can block a new download is the moment
they are collected, and the app gains no daemon thread and no scheduler dependency. A file nobody
prepares again therefore survives past its TTL — that costs disk, not correctness, and the cap below
is what bounds it.

**D9 — two caps, both enforced, one of them mid-flight.** `RKM_OFFLINE_MAX_BYTES` (default 12 GiB)
bounds what this feature may occupy on the Docker host. It is checked **before** packaging (using the
library file's size as an estimate — exact for a remux, an over-estimate for a transcode, i.e. the
safe direction) **and during** it, where the partial file is discarded rather than overrunning. A
refusal is **507** with a sentence naming the knob.

## Consequences

* **The device's contract is fixed and tested.** `HEAD` gives the size (an *explicit* `@router.head`:
  measured 2026-09-14, a GET-only FastAPI route answers HEAD with **405**, so a size probe would fail
  silently exactly when the device has committed to a download), `Range` gives `206`+
  `Content-Range`, `416` carries `bytes */size`, and the ETag is strong because the artefact only
  ever changes by being replaced whole. B2/B3 are written against this.
* ✅ **VERIFIED LIVE 2026-09-16** (the phase's step-5 gate, against the deployed container through
  nginx, on a real 1,795 MB library film): `HEAD` → `200` + `Content-Length: 1882377499` + `Accept-Ranges: bytes`
  + a strong ETag + no body · `Range: bytes=0-99` → `206` + `Content-Range: bytes 0-99/1882377499` and
  exactly 100 bytes · a suffix range at EOF → `206` + 10 bytes · `bytes=<size+500>-` → `416` +
  `bytes */1882377499` · the whole file → `200` with all 1,882,377,499 bytes, and the payload really is
  an MP4 (`ftypisom` at offset 4) · `prepare` twice → `reused`, nothing re-packaged · `DELETE` →
  `removed_file: false` and the library file still intact behind a 404.
* **The scale of the ladder defect, in the owner's own numbers:** 13 of the 13 MP4s sampled were being
  routed to `remux`. At the measured tailnet rate (≈3.8 MB/s) that is roughly **8 minutes and a
  full-size staging file per film** that the fix removes entirely for the household's most common
  format.
* **Idempotency is a property, not a hope**: (item, rendition) names one artefact, a finished one is
  returned untouched, and a second `prepare` while the first is running starts no competing writer.
  The test proves it by counting upstream calls — a re-transcode would also return `state: ready`.
* **Which clients this serves — and it is not iPad-specific.** Every iOS client: the iPhone and the
  iPad run the same WKWebView shell, so B1–B5 are one body of work, not two. ⚠ And because these are
  plain HTTP routes with byte ranges, a **future native tvOS client uses the same contract** —
  `apple/README.md` already records that the TV player additionally needs the *bearer-token* work, not
  a different server design. What IS per-device is **storage**, not the protocol: the cap/eviction
  settings (B5) are the part that must be sized for an iPhone's smaller disk as well as an iPad's.
* **What B1 does NOT do, stated plainly:** no device work (B2/B3), no page affordances or Downloads
  screen (B4), no eviction/pin/delete-after-watch (B5), no server-side resume of a *packaging* job
  (a retry restarts from zero — the resumable leg is the device's download, which is the leg that
  crosses a network), and no per-profile file isolation (D6).
* **Still unverified after B1, and this is the honest list:** a **packaged** rendition (the remux /
  transcode_audio / transcode rungs) has never run against a real film — every live check above used a
  *borrowed* (direct) artefact, which packages nothing. ⚠ So the modes the ladder picks for the
  household's MKVs are reasoned and unit-tested but not yet measured end to end. The rest is
  pytest + the 17 falsifications recorded in `docs/PROGRESS.md`.
