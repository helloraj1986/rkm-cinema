# Admin credentials — provision without a stored password, rename the account, self-service password

**Status:** SCOPED 2026-09-12 (nothing built yet). Absorbs **Phase D** of
`PLEX_PROFILE_AUTH_PLAN.md` (rename + the profile's own change-my-password) by the user's decision of
2026-09-12, and follows **Phase C** (`5e303e0`), which is what makes per-profile identity real.

## 1. What the user asked for, in his words

> *"ideally the password should not be in .env file ... can we provision it so that user can set it
> from ui... and then we can remove it from .env file .. we have to be careful so that we dont lock
> ourself out"*

> *"also the admin can change its user name... the role should only be admin rather than the actual
> name saying admin"*

and, revising the fresh-install question the same day:

> *"or we can do like ths fresh install will create a admin with password.. which bootstrap.ps1 will
> let the user know so that it can record it and in that way there will be no fear of loosing the
> password"*

## 2. Decisions (user, 2026-09-12 — all inputs, not recommendations)

1. **A fresh install creates the admin WITH a strong generated password, printed ONCE by the
   bootstrap so it can be recorded.** Nothing is written to `.env`; nothing is generated or printed
   on later runs. **This replaces** the earlier "create it with no password" choice, and §4 records
   what that choice would have cost — the reversal is what removes the risky phase.
2. **The admin account can be RENAMED**, and the UI must present a **role** ("Administrator") rather
   than leaning on the literal name `admin`. Nothing may depend on that name.
3. **`.env` keeps `RKM_JELLYFIN_ADMIN_PASSWORD` as OPTIONAL** — never generated, never required by
   compose, never read by the provisioner after the first run; documented as "leave blank unless you
   want the local Python tools to sign in". A different arrangement for the tools is a LATER
   investigation, recorded here so it is not forgotten.
4. **This workstream absorbs Phase D** — the rename UI and the self-service "change my password"
   screen are built here, not separately.

## 3. Measured inventory — what actually needs that password (live, 2026-09-12)

| Consumer | Needs it? | Evidence |
|---|---|---|
| **The api container** | **NO** | its Jellyfin credential is **`JELLYFIN_API_KEY`**, minted by the provisioner into the `rkm_shared` volume (`runtime.json`, `RKM_RUNTIME_PATH`). `JELLYFIN_ADMIN_PASSWORD` is passed to the **provisioner service only** (`docker-compose.yml` §provisioner) |
| The provisioner | **once**, on a brand-new `jellyfin-config` | `provision.py::run_startup()` posts the startup wizard (`POST /Startup/User {Name, Password}`) — the ONLY place a password is *created*; afterwards `ensure_admin()` merely authenticates |
| `docker-compose.yml` | as a **GATE** | `JELLYFIN_ADMIN_PASSWORD: "${…:?…}"` — compose REFUSES to start the provisioner when unset. **The first thing that must change** (`:?` → `:-`) |
| `render_config.py` | it **generates and writes it back** | `if backend == "jellyfin" and not admin_pw: admin_pw = secrets.token_urlsafe(18); write_env_key(ENV_PATH, …)` — how the value got there, and why "just delete the line" does not stick. **The generation already produces a strong password; where it goes is the whole change** |
| Local tools | yes | `tools/rkm_common.py::Jellyfin._login` (so `probe_stack`, `diag_household_gate`, `prove_profile_isolation`, the diagnostic probes) and `backend/scripts/probe_jellyfin_{detail,hls}.py` |
| The bootstrap console | **no log file** | `grep` for `Tee-Object`/`Out-File`/`Start-Transcript` in `bootstrap.ps1`, `rkm-cinema.ps1` and `scripts/*.ps1` finds none — a printed password is not written to disk, which is what makes §2 decision 1 safe. (It does live in the terminal scrollback, and in anything the console output is pasted into.) |

### 3a. The break-glass credential, MEASURED

**A Jellyfin API key satisfies elevation.** `GET /Library/VirtualFolders` answers **200 with an API
key** and **403 with a non-administrator's session token** (both measured on 10.11.11, 2026-09-12).
The key lives in the `rkm_shared` volume, survives rebuilds, is never typed by a human and is never
in a repo file — so it is the credential a **recovery command** can rely on when every password is
forgotten. This is the real answer to "no fear of losing the password": recording the printed value
is convenience, the volume key is the guarantee.

⚠ Still to be PROVEN (not assumed), on the throwaway stack of §7: that an API key is accepted by
`POST /Users/Password?userId=…` with `ResetPassword: true` (`/Users/Password` is in the server's own
contract; Jellyfin expresses its elevation policy in code, not in the OpenAPI document, so the
proxy above is strong evidence and not proof).

## 4. The lockout that the REJECTED design would have produced (kept as history — it is why §2 decision 1 was reversed)

The first decision was to create the admin with **no password** and force one from the UI. Measured
against the code, that combination had a guaranteed dead end:

* `POST /api/auth/login` **succeeds** with a blank password (supported — `401a3c7`, pinned by
  scenario D of `tools/check_login_flow.py`), and the session is created with the administrator as
  its owner;
* then the picker appears — and `POST /api/auth/profile` refuses a blank attempt on the
  administrator's own profile **unconditionally**:

  ```python
  wants_admin = bool(target.get("is_admin"))
  if wants_admin and not payload.password:
      raise HTTPException(status_code=401, detail="Enter the administrator's password to switch to that profile")
  ```

  That rule is decision 3 of the profile model, chosen deliberately so a guest cannot walk into the
  admin's profile on a shared device. It does **not** consult `has_password`.

So a fresh install would have let the administrator in the front door and then stranded them at a
picker where **no profile could be selected**. Fixing that would have required a mandatory
set-password gate between sign-in and the picker, server-enforced, plus the state to back it — the
riskiest thing in the workstream.

**Generating the password at creation time removes all of it:** the admin has a password from the
first second, the picker behaves exactly as it does today, and there is no new gate to get wrong.

## 5. The second trap: the literal name `admin`

Renaming the account breaks anything that assumes the name:

* `RKM_JELLYFIN_ADMIN_USER` (`.env`, default `admin`) is what the provisioner authenticates with and
  what every tool signs in as;
* `ensure_admin()` looks that name up; a rename leaves it authenticating as a user that no longer
  exists → `wizard_pending() is False` + auth fails → **fail fast naming the password** (a confusing
  message for a rename problem).

**Rule for the implementation:** resolve the administrator by **id** (from the stored identity /
`runtime.json`) wherever the credential is the API key, and treat `RKM_JELLYFIN_ADMIN_USER` as a
**first-run hint only**. A rename must not require an `.env` edit.

## 6. Phases (one sitting each, one commit each, gates green every time)

| Phase | Content | Gate |
|---|---|---|
| **0** | This plan + the throwaway-stack recipe (§7); amend `PLEX_PROFILE_AUTH_PLAN.md` §7 rows D/E to point here | docs links |
| **1** | **No password needed after the first run, and the first-run one is PRINTED, never stored.** The generation MOVES from `render_config` (which runs on every bootstrap and cannot tell a fresh install from a re-run) to `provision.py::run_startup()` (which knows it is creating the admin because that is what it is doing): generate `token_urlsafe(18)`, set it on the account, and print it in a boxed, unmissable notice **only when the wizard step actually succeeded** (`200/204`), never on a re-run. `ensure_admin()` tries the STORED credential first (`JELLYFIN_API_KEY` / `runtime.json`) and resolves the admin by id; compose `:?` → `:-`; `render_config` stops generating or writing the key; `.env.example` documents it as OPTIONAL (tooling) with the reason. If it IS set in `.env`, it is used and nothing is printed — the manual override survives | pytest (provisioner: fresh install prints + sets; re-run prints nothing and needs no password; a rename does not break it), ruff, docs links |
| **2** | **Household: role vs name.** An **Administrator** badge and the account's real name; rename (`POST /Users?userId=`) with the rails; the picker/header/sidebar never label a person by their role | tsc, vitest, `check_household_ui.py` + `check_profile_picker.py` (new scenarios), build |
| **3** | **Self-service password screen** for every profile (Phase D's other half): change my own password with `CurrentPw` + `NewPw`; honest messaging for a password-less member | gates + DOM check |
| **4** | **Recovery, documented and tested**: `rkm-cinema.ps1 reset-admin-password` → reads the API key from the volume (never from `.env`), prompts for a new password, calls `POST /Users/Password?userId=…&ResetPassword=true`, then VERIFIES by signing in; `OPERATIONS.md` gains the runbook and the "forgot everything" ladder | the tool's own verification output; pytest for its pure parts |
| **5** | ADR (the credential model), docs truth pass (`ARCHITECTURE`, `OPERATIONS`, `README`), PROGRESS record | full suite + docs links |

⚠ **There is no forced-set-password phase any more** — that row existed only to rescue §4's rejected
design. Do not add it back "for symmetry".

## 7. Verification, and how we avoid locking ourselves out

**The fresh-install path CANNOT be tested in the sandbox** (no Docker daemon there) and must not be
tested against the real stack (a fresh `jellyfin-config` means losing the household's watch state —
the documented escalation, and unacceptable for a test). So it runs on a **throwaway stack on
RKM-HP**: the same repo with its own project name, ports and volumes.

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
$env:RKM_PROJECT="rkm-test"; $env:RKM_DASHBOARD_PORT="8125"; $env:RKM_JELLYFIN_PORT="8099"
.\bootstrap.ps1                          # exactly how it is invoked is Phase 1's business
docker compose -p rkm-test down -v        # the volumes go; none of yours was ever in them
```

What must be PROVEN there, in order, with the console output quoted in the record:

1. an empty `jellyfin-config` creates the admin, and the **printed password signs in** (blank fails);
2. a SECOND run needs no password, prints nothing, and provisions normally (the API-key-first path);
3. an API key resets that password (`ResetPassword: true`) — proving the break-glass rail;
4. **renaming** the admin does not break the next bootstrap run (the id-not-name rule);
5. `down -v`, and the real stack is untouched.

Then, on the REAL stack (safe, but not free): after Phase 1, one `bootstrap.ps1` run with NO password
in `.env` must provision normally. Run it when no library scan is in progress — the provisioner
issues `/Library/Refresh`, which cancels a running scan.

## 8. Escape hatches (unchanged, and stated so nobody "improves" them away)

* **The API key in `rkm_shared`** — the break-glass credential (§3a), and what the recovery command
  uses. This is the guarantee; a recorded password is the convenience.
* **`RKM_JELLYFIN_ADMIN_PASSWORD` in `.env`** — still honoured as the first-run password and by the
  tools. Nothing removes that ability; it is the documented manual override.
* **The app itself** — an administrator can set or reset any account's password from
  `Settings → Household` today (`Reset password`), including their own, and Phase 3 adds the
  self-service screen for everybody else.
* **`RKM_AUTH_REQUIRED` stays `false`** unless he arms it; nothing here flips it.
* **Jellyfin's own dashboard** on the host knows nothing about this app — but it needs the admin's
  password too, so it is NOT first-line recovery: the volume API key is.

## 9. Honest open questions (answers needed before the phase that uses them)

1. Should the **rename** be available for members too (Household already lists them), or only for the
   administrator's own account? (Phase 2 assumes both, since the rail is the same.)
2. Does a member's **self-service** password change need the administrator's approval to be
   discoverable, or is it simply a Settings entry every profile sees? (Phase 3 assumes the latter.)
3. Is a **one-time printed password** acceptable for the throwaway-stack test, or does the test need a
   fixed value to script against? (Phase 1 assumes it can be read from the console; a fixed value can
   always be supplied via the `.env` override when scripting.)

## 10. Risks

1. **Lockout** — the design that carried this risk was rejected (§4). What remains: a mistyped or
   lost printed password, answered by the app's own reset (already built) and by the volume key
   (§3a).
2. **A rename breaking provisioning** — mitigated by the id-not-name rule (§5).
3. **`.env` regrowth** — if any code path still generates the key, the value comes back and the whole
   change is cosmetic; Phase 1 removes the generation AND asserts its absence in a test.
4. **The printed password leaking** — no log file (§3), but the console is a transcript: the notice
   says plainly that it is shown once, and the value is rotatable in the app in seconds.
5. **Tools losing their login** — accepted deliberately (§2 decision 3): the key stays optional and
   documented; the workaround for a password-less-by-default world is a LATER investigation.
