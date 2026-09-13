# RKM stack operations

**One command does everything.** From the repo root on RKM-HP:

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 help
```

| Command | What it does | Use it when |
|---|---|---|
| `.\rkm-cinema.ps1 status` | Containers, state volumes, app + Jellyfin health, library counts, scan state, **and whether sign-in is required** | Anything looks off — **start here** |
| `.\rkm-cinema.ps1 apply` | Make the running stack match this folder: re-render `.env`, rebuild + restart `api` and `web` | **You edited `.env`, or pulled new code** |
| `.\rkm-cinema.ps1 deploy [-NoBackup]` | `apply` **plus** the Jellyfin provisioner | First run, or new libraries/keys |
| `.\rkm-cinema.ps1 auth` | Is sign-in required right now? | You are unsure whether the lock is on |
| `.\rkm-cinema.ps1 auth on` | Require sign-in for everything (except `/api/health` and sign-in) | You want the app private |
| `.\rkm-cinema.ps1 auth off` | Back to open | **You locked yourself out** |
| `.\rkm-cinema.ps1 backup` | Archive Jellyfin state to `D:\RKM_BACKUPS` (keeps newest 7) | Before anything risky |
| `.\rkm-cinema.ps1 restore -Archive <file>` | Replace current state from an archive | Something was lost / a bad upgrade |
| `.\rkm-cinema.ps1 schedule` | Install the nightly 04:00 backup task | Once, per machine |
| `.\rkm-cinema.ps1 diagnose` | Classify every TV series: watched vs episodes present | Shows look watched, or episodes are missing |
| `.\rkm-cinema.ps1 reset-admin-password [-DryRun]` | Set a new administrator password using the stack's own API key | Locked out of the account itself |
| `.\rkm-cinema.ps1 logs [service]` | Tail api + web + jellyfin | Right after an `apply` that reported problems |

⚠ **Editing `.env` alone changes nothing** — a container reads its environment when it *starts*. That
is the whole reason `apply` exists, and why `auth on|off` applies for you.

Only `rkm-cinema.ps1` is meant to be run. `render_config.py`, `tools\*.py` and `scripts\*.ps1` are its
internals; `bootstrap.ps1` and `rkm.ps1` are one-line forwarders kept so older notes still work.

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
[jellyfin] using the stored API key - no admin password needed (administrator: admin)
[jellyfin] libraries to wire: ['Movies Kids', 'Movies', 'TV Shows'] (source: configured)
[jellyfin] triggered library scan (POST /Library/Refresh) -> 204
```

`using the stored API key` is what every run AFTER the first one says: the key minted on the first
run lives in the `rkm_shared` volume, so **bootstrap needs no admin password at all**
(ADMIN_CREDENTIALS_PLAN.md §6). On the very FIRST run you instead see
`[jellyfin] admin created + authenticated 'admin'`, immediately followed by a boxed

```
======================================================================
 JELLYFIN ADMIN PASSWORD - SHOWN ONCE. Record it now.
   user:     admin
   password: <the generated password>
======================================================================
```

**Record it then** (a password manager, or paper): it is shown once, it is NOT written to `.env`,
and `.env` is not the place to go looking for it. It is rotatable at any time in the app
(`Settings -> Household -> Reset password`). `RKM_JELLYFIN_ADMIN_PASSWORD` still works if you set it
— it overrides both, and it is also what the local Python tools sign in with.

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

## Locked out? The ladder, in order

Nobody-knows-the-password is the ONE failure with no UI way out: you cannot reach Household without
an administrator, and you cannot be an administrator without the password. The break-glass removes
the need for it.

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 reset-admin-password -DryRun   # read-only: names the account it would reset
.\rkm-cinema.ps1 reset-admin-password           # then this, and type the new password twice
```

What it does, and why it can: the stack's own **API key** lives in the `rkm_shared` volume (written
by the provisioner, never typed by a human, never `.env`), and an administrator's **privilege** is
what authorises a password reset — the old password is not needed and not asked for. It then **proves
the change by signing in** with the new password, and says so only if that worked.

| You are locked out of | Do this |
|---|---|
| **The administrator account** (this stack) | `.\rkm-cinema.ps1 reset-admin-password` — one command, no old password |
| **A member's password** | Sign in as the administrator → **avatar → Household → Reset password**. (Or that person changes it themselves: avatar → My password.) Resetting a member from the break-glass is refused on purpose — it is the lockout recovery, not a household tool |
| **The administrator, and no API key in the volume** (`rkm_shared` wiped) | `.\rkm-cinema.ps1 deploy` — the provisioner re-provisions and, on a stack with no admin, **prints a new admin password once**. Watch the bootstrap output, not `.env` |
| **Everything** (state volume also lost) | `.\rkm-cinema.ps1 restore` from the newest archive in `D:\RKM_BACKUPS` — the archive carries the accounts, so the passwords come back as they were |
| **Everything, and no backup** | Out of scope here, and destructive: the accounts live in Jellyfin's own database (`jellyfin-config` volume). Nothing in this repo does that automatically — do not improvise it. Ask me, or see Jellyfin's own recovery docs |
| **`rkm`, because you renamed it and forgot the name** | `.\rkm-cinema.ps1 reset-admin-password -DryRun` prints the account it would reset, whatever it is called (the tool finds administrators by POLICY, never by the name `admin`) |

Two things it deliberately does NOT do: it never takes the password as a command-line argument (that
would sit in your PowerShell history and the process list), and it never prints it. `ResetPassword:
true` appears nowhere in it — that flag is a silent no-op that **clears** a password rather than
setting one (measured, `ADMIN_CREDENTIALS_PLAN.md` §6c).

## When something looks wrong

| Symptom | Run | Most likely cause |
|---|---|---|
| Library rows greyed out / disabled | `.\rkm-cinema.ps1 status` | App has no Jellyfin credential, or the library path does not resolve — `status` prints the exact warning |
| Every show shows as watched | `.\rkm-cinema.ps1 diagnose` | Series with no episodes attached read as "all played" (Jellyfin's own logic). Healthy series print `played=False` |
| Episodes missing under a show | `.\rkm-cinema.ps1 diagnose` | Scan mid-flight, or a cancelled scan — check scan state with `status` |
| Posters reload every visit | — | Fixed in `c654d8a`; if it returns, the `web` image did not rebuild |
| A show won't appear at all | `python tools\probe_media_files.py --dir "/media2/TV Shows/<folder>"` | Folder naming, or the file is unplayable (ffprobe failure) |
| Deploy stopped at the provisioner | `.\rkm-cinema.ps1 logs` | Read the `[jellyfin]` line it stopped on — the messages name the cause |
| No online subtitles offered / "not configured" | `python tools\probe_subtitle_selection.py "<title>"` | No `OPENSUBTITLES_API_KEY`, or the vendor is down — the warning in the panel names which |
| "It says added" but the picker shows no tick | `python tools\probe_subtitle_selection.py "<title>"` | Compares the stored choice, the panel's rows and the server's tracks — it prints which row is marked active |
| Subtitle download refused | — | Daily limit reached; the message carries the reset time (counters reset 00:00 UTC = 10:00 AEST) |
| Subtitles stopped applying after a change | `python tools\probe_subtitle_selection.py "<title>"` | The chosen identity no longer matches a track (re-indexed, file removed) — nothing is applied rather than something wrong |

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
| `rkm-cinema.ps1` | **the only script you run** — every verb, including `apply`, `deploy` and `auth on\|off` |
| `bootstrap.ps1` | one-line forwarder to `rkm-cinema.ps1 deploy` (old name, kept so notes still work) |
| `rkm.ps1` | one-line forwarder to `rkm-cinema.ps1` (old name) |
| `tools\set_env_value.py` | the tested `.env` editor behind `auth on\|off` (backup + comment-preserving) |
| `scripts\backup-rkm-state.ps1` | archive state volumes (verifies + prunes) — internal, via `backup` |
| `scripts\restore-rkm-state.ps1` | restore an archive (pre-backs-up the current state) — internal, via `restore` |
| `scripts\install-backup-task.ps1` | nightly 04:00 task, runs as you (Docker Desktop is session-scoped) — internal, via `schedule` |
| `tools\rkm_status.py` | the deep status behind `.\rkm-cinema.ps1 status` |
| `tools\diagnose_series_state.py` | watched-vs-episodes classifier |
| `tools\probe_media_files.py` | what the *server* sees in a folder + ffprobe errors |
| `tools\probe_jellyfin_state.py` | scan state, per-library counts, log errors |
| `tools\diagnose_episode_linkage.py` | series/episode record linkage |
| `tools\rebuild_jellyfin_library.py` | delete + re-create one library (`--yes` required) |
| `tools\probe_subtitle_selection.py` | read-only: the server's subtitle tracks, every picker row (active/local/index/used) and `playback-info`'s `preferred_subtitle` |
| `tools\probe_subtitles.py` | read-only recon: which subtitle endpoints/plugins the server has at all |
| `PROGRESS.md` | session-by-session history |

Notes: the tools find the stack themselves (inside the sandbox via
`host.docker.internal`, on Windows via `localhost`), so they work either side.
`Limit=0` in Jellyfin means *return zero items* — count with `TotalRecordCount`,
never `len(Items)`.

⚠ **Some tools read the APP, not just Jellyfin** (`rkm_status.py`, `diagnose_series_state.py`,
`probe_continue_watching.py`, `verify_progress_reporting.py`, `probe_subtitle_selection.py`,
`prove_profile_isolation.py`). Since 2026-09-13 those **sign in first** — see below.

## Arming `RKM_AUTH_REQUIRED` (the switch)

`false` (today) = the app answers anyone who can reach it: a request with **no session at all** is
served as the stack's own credential, so the libraries, playback and watch state work signed out.
`true` = all 36 app routes need a session. Only these stay reachable signed out, both by design:

* `GET /api/health` — the Docker HEALTHCHECK; a 401 here marks the api unhealthy and cascades;
* the six `/api/auth/*` routes — sign-in cannot require a session to be reachable.

**To arm it — one command:**

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 auth on
```

That edits `.env` (with a timestamped backup), applies it, and then **proves it** by asking the api
for a route that needs a session — so you are told `401` (armed) or `200` (still open), never left
guessing. `.\rkm-cinema.ps1 auth` on its own reports the current state without changing anything.

**To go back — the recovery, one command:**

```powershell
.\rkm-cinema.ps1 auth off
```

Underneath, `auth on|off` is just: `tools\set_env_value.py RKM_AUTH_REQUIRED <value>` followed by
`.\rkm-cinema.ps1 apply` (which is what recreates the containers — editing `.env` alone does nothing).
If you prefer the manual path it is those two commands, but the switch is the one place where being
*proved* rather than assumed is worth having. Locked out of the **account** as well?
`.\rkm-cinema.ps1 reset-admin-password` is the break-glass (see the ladder above).

**What changes:** the browser sends no session → the app shows the login view (the frontend discovers
enforcement from the first 401; no frontend change is involved). Sessions last **30 days, refreshed on
use**, so a TV or tablet does not re-ask every time.

**What to know before you flip it:** anything that is not the browser must sign in. That is:

| Who | Signs in how |
|---|---|
| the web app | the login screen; nothing to do |
| the tools listed above | **already do** — they sign in as the administrator from `.env`, on their own device id (`rkm-tools`) |
| the Jellyfin-direct probes (`probe_jellyfin_*.py`, `probe_media_files.py`, `reset_admin_password.py`) | nothing to do — they never call the app over HTTP |
| the scheduler and the provisioner | nothing to do — they call the services in-process, not over HTTP |

**Why the tools use their own device id:** Jellyfin invalidates the previous token of a
*(device, user)* pair on every login, so a tool authenticating on the app's device
(`rkm-cinema-web`) would rotate the **browser's** token away and leave it answering 401 on every
media call. Their credentials come from `.env` (`RKM_JELLYFIN_ADMIN_USER` /
`RKM_JELLYFIN_ADMIN_PASSWORD`); only an administrator may sign in, so a member's account cannot be
used here.

Merge to `main` is parked until the user verifies on RKM-HP.
