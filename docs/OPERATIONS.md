# RKM stack operations

**One command does everything.** From the repo root on RKM-HP:

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 help
```

| Command | What it does | Use it when |
|---|---|---|
| `.\rkm-cinema.ps1 status` | Containers, state volumes, app + Jellyfin health, library counts, scan state | Anything looks off — **start here** |
| `.\rkm-cinema.ps1 deploy` | Build + refresh the stack, wire libraries, trigger a scan | You changed `.env`, or code, or want the stack rebuilt |
| `.\rkm-cinema.ps1 backup` | Archive Jellyfin state to `D:\RKM_BACKUPS` (keeps newest 7) | Before anything risky |
| `.\rkm-cinema.ps1 restore -Archive <file>` | Replace current state from an archive | Something was lost / a bad upgrade |
| `.\rkm-cinema.ps1 schedule` | Install the nightly 04:00 backup task | Once, per machine |
| `.\rkm-cinema.ps1 diagnose` | Classify every TV series: watched vs episodes present | Shows look watched, or episodes are missing |
| `.\rkm-cinema.ps1 logs` | Tail api + web + jellyfin | Right after a deploy that reported problems |

Every verb is a thin wrapper around a real script (`bootstrap.ps1`, `scripts\*.ps1`, `tools\*.py`), so the wrapper and the tool can never behave differently. Run either.

## The only three rules

1. **Don't run `down -v`** unless you truly want the watch history gone — it deletes the state volumes. (`docker compose -p rkm-bundled down` is safe and keeps them.)
2. **Don't restart the stack while a library scan is running** — a cancelled scan leaves shows present with no episodes attached, which reads as "everything watched". `.\rkm-cinema.ps1 status` shows scan state.
3. **Run compose with `-p rkm-bundled`** (bootstrap and `rkm-cinema.ps1` always do). A different project name creates *fresh empty* volumes and orphans the real ones.

## Fresh install / full rebuild

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema

# 1. Back up first (skipped automatically if no volumes exist yet)
.\rkm-cinema.ps1 backup

# 2. Build, wire libraries, start the scan
.\rkm-cinema.ps1 deploy

# 3. Confirm
.\rkm-cinema.ps1 status
```

Expected in the deploy output:

```
[env] media root: D:/RKM_MEDIA -> /data (ok)
[env] media root: B:/RKM_MEDIA -> /media2 (extra drive ...)
[jellyfin] admin created + authenticated 'admin'
[jellyfin] libraries to wire: ['Movies Kids', 'Movies', 'TV Shows'] (source: configured)
[jellyfin] triggered library scan (POST /Library/Refresh) -> 204
```

### Starting Jellyfin completely fresh (damaged database)

If state is corrupt and a rebuild cannot repair it (this happened 2026-09-10: a
config volume carrying another Jellyfin's database, with every show marked
watched):

```powershell
.\rkm-cinema.ps1 backup                      # last chance to keep it
docker compose -p rkm-bundled down
docker volume rm rkm-bundled_jellyfin-config # the database only
.\rkm-cinema.ps1 deploy                      # re-provisions from scratch
```

Media files are never touched by this. Watch state and library definitions go,
and a full scan takes **2-4 h** (~850 movies, 116 series, 5000+ episodes).

## When something looks wrong

| Symptom | Run | Most likely cause |
|---|---|---|
| Library rows greyed out / disabled | `.\rkm-cinema.ps1 status` | App has no Jellyfin credential, or the library path does not resolve — `status` prints the exact warning |
| Every show shows as watched | `.\rkm-cinema.ps1 diagnose` | Series with no episodes attached read as "all played" (Jellyfin's own logic). Healthy series print `played=False` |
| Episodes missing under a show | `.\rkm-cinema.ps1 diagnose` | Scan mid-flight, or a cancelled scan — check scan state with `status` |
| Posters reload every visit | — | Fixed in `c654d8a`; if it returns, the `web` image did not rebuild |
| A show won't appear at all | `python tools\probe_media_files.py --dir "/media2/TV Shows/<folder>"` | Folder naming, or the file is unplayable (ffprobe failure) |
| Deploy stopped at the provisioner | `.\rkm-cinema.ps1 logs` | Read the `[jellyfin]` line it stopped on — the messages name the cause |

## Where state lives, and what survives what

| Action | Jellyfin state (`jellyfin-config`) | Media files (`D:`/`B:`) |
|---|---|---|
| Container restart / reboot | kept | untouched |
| `.\rkm-cinema.ps1 deploy` (rebuild) | kept | untouched |
| `docker compose -p rkm-bundled down` | kept | untouched |
| `docker volume rm rkm-bundled_jellyfin-config` | **gone** | untouched |
| `down -v` | **gone** | untouched |
| Compose run under a different project name | **appears gone** (fresh volumes) | untouched |

The app's own watchlist is a JSON file at `D:\RKM_MEDIA\rkm\watchlist.json`
(`WATCHLIST_DB_PATH`), independent of Jellyfin.

## Layout

| Path | What |
|---|---|
| `.env` | single source of config; rendered to `.rkm.env` for the containers |
| `bootstrap.ps1` | build + provision + start (called by `deploy`) |
| `scripts\backup-rkm-state.ps1` | archive state volumes (verifies + prunes) |
| `scripts\restore-rkm-state.ps1` | restore an archive (pre-backs-up the current state) |
| `scripts\install-backup-task.ps1` | nightly 04:00 task, runs as you (Docker Desktop is session-scoped) |
| `tools\rkm_status.py` | the deep status behind `.\rkm-cinema.ps1 status` |
| `tools\diagnose_series_state.py` | watched-vs-episodes classifier |
| `tools\probe_media_files.py` | what the *server* sees in a folder + ffprobe errors |
| `tools\probe_jellyfin_state.py` | scan state, per-library counts, log errors |
| `tools\diagnose_episode_linkage.py` | series/episode record linkage |
| `tools\rebuild_jellyfin_library.py` | delete + re-create one library (`--yes` required) |
| `PROGRESS.md` | session-by-session history |

Notes: the tools find the stack themselves (inside the sandbox via
`host.docker.internal`, on Windows via `localhost`), so they work either side.
`Limit=0` in Jellyfin means *return zero items* — count with `TotalRecordCount`,
never `len(Items)`.

Merge to `main` is parked until the user verifies on RKM-HP.
