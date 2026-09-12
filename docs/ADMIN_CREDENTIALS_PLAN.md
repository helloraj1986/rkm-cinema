# Admin credentials — provision without a stored password, rename the account, self-service password

**Status:** SCOPED 2026-09-12 (nothing built yet). Absorbs **Phase D** of
`PLEX_PROFILE_AUTH_PLAN.md` (rename + the profile's own change-my-password) by the user's decision of
2026-09-12, and follows **Phase C** (`5e303e0`), which is what makes per-profile identity real.

## 1. What the user asked for, in his words

> *"ideally the password should not be in .env file ... can we provision it so that user can set it
> from ui... and then we can remove it from .env file .. we have to be careful so that we dont lock
> ourself out"*

and, answering the fresh-install question: *"option c, also the admin can change its user name... the
role should only be admin rather than the actual name saying admin"*.

## 2. Decisions (user, 2026-09-12 — all four are inputs, not recommendations)

1. **Fresh install creates the admin with NO password.** The app then requires a password before
   anything else works (see §4 — this is the part that must be built in the right order).
2. **The admin account can be RENAMED**, and the UI must present a **role** ("Administrator") rather
   than leaning on the literal name `admin`. Nothing may depend on that name.
3. **`.env` keeps `RKM_JELLYFIN_ADMIN_PASSWORD` as OPTIONAL** — never generated, never required by
   compose, never read by the provisioner after the first run; documented as "leave blank unless you
   want the local Python tools to sign in". A different arrangement for the tools is a LATER
   investigation, and this plan records the intent so it is not forgotten.
4. **This workstream absorbs Phase D** — the rename UI and the self-service "change my password"
   screen are built here, not separately.

## 3. Measured inventory — what actually needs that password (live, 2026-09-12)

| Consumer | Needs it? | Evidence |
|---|---|---|
| **The api container** | **NO** | its Jellyfin credential is **`JELLYFIN_API_KEY`**, minted by the provisioner into the `rkm_shared` volume (`runtime.json`, `RKM_RUNTIME_PATH`). `JELLYFIN_ADMIN_PASSWORD` is passed to the **provisioner service only** (`docker-compose.yml` §provisioner) |
| The provisioner | **once**, on a brand-new `jellyfin-config` | `provision.py::run_startup()` posts the startup wizard (`POST /Startup/User {Name, Password}`) — that is the ONLY place a password is *created*; afterwards `ensure_admin()` merely authenticates |
| `docker-compose.yml` | as a **GATE** | `JELLYFIN_ADMIN_PASSWORD: "${…:?…}"` — compose REFUSES to start the provisioner when unset. **This is the first thing that must change** (`:?` → `:-`) |
| `render_config.py` | it **generates and writes it back** | `build_api_vars()`'s password block writes `RKM_JELLYFIN_ADMIN_PASSWORD` into the repo `.env` when blank — how the value got there, and why "just delete the line" does not stick |
| Local tools | yes | `tools/rkm_common.py::Jellyfin._login` (so `probe_stack`, `diag_household_gate`, `prove_profile_isolation`, the diagnostic probes) and `backend/scripts/probe_jellyfin_{detail,hls}.py` |

### 3a. The break-glass credential, MEASURED

**A Jellyfin API key satisfies elevation.** `GET /Library/VirtualFolders` answers **200 with an API
key** and **403 with a non-administrator's session token** (both measured on 10.11.11, 2026-09-12).
The key lives in the `rkm_shared` volume, survives rebuilds, is never typed by a human and is never
in a repo file — so it is the credential a **recovery command** can rely on when every password is
forgotten. This is what makes "no password in `.env`" safe rather than reckless.

⚠ Still to be PROVEN (not assumed), on the throwaway stack of §7: that an API key is accepted by
`POST /Users/Password?userId=…` with `ResetPassword: true` (`/Users/Password` is in the server's own
contract; Jellyfin expresses its elevation policy in code, not in the OpenAPI document, so the
proxy above is strong evidence and not proof).

## 4. ⚠ The lockout this design MUST avoid — option C and decision 3 collide

With an admin that has **no password**:

* `POST /api/auth/login` **succeeds** with a blank password (that is supported — `401a3c7`, pinned by
  scenario D of `tools/check_login_flow.py`), and the session is created with the administrator as its
  owner;
* then the picker appears — and `POST /api/auth/profile` refuses a blank attempt on the
  administrator's own profile **unconditionally**:

  ```python
  wants_admin = bool(target.get("is_admin"))
  if wants_admin and not payload.password:
      raise HTTPException(status_code=401, detail="Enter the administrator's password to switch to that profile")
  ```

  That rule is decision 3 of the profile model, chosen deliberately to stop a guest walking into the
  admin's profile on a shared device. It does **not** check `has_password`.

**Consequence:** a brand-new install would let the administrator in the front door and then strand
them at the picker, with **no profile they can select** — a guaranteed lockout, from the two
decisions combined rather than from either one.

**Therefore the required order is:**

    Server login (blank password, first run)
      → **SET YOUR PASSWORD** (mandatory; nothing else is reachable)
      → Who's watching? (a password now exists, so the normal rule applies)
      → the app

The picker's own `needsPassword()` already shows a lock on an administrator with no password of its
own (Phase B, `tools/check_profile_picker.py` scenario A), so the UI is consistent; it is the ORDER
that must be enforced server-side, not in the UI (user's standing rule: enforce server-side, never
UI-only).

## 5. The second trap this plan must handle: the literal name `admin`

Renaming the account breaks anything that assumes the name:

* `RKM_JELLYFIN_ADMIN_USER` (`.env`, default `admin`) is what the provisioner authenticates with and
  what every tool signs in as;
* `ensure_admin()` prints and looks up that name; a rename leaves it authenticating as a user that no
  longer exists → `wizard_pending() is False` + auth fails → **fail fast naming the password** (a
  confusing message for a rename problem).

**Rule for the implementation:** resolve the administrator by **id** (from the stored identity /
`runtime.json`) where the credential is the API key, and treat `RKM_JELLYFIN_ADMIN_USER` as a
**first-run hint only**. A rename must not require an `.env` edit.

## 6. Phases (one sitting each, one commit each, gates green every time)

| Phase | Content | Gate |
|---|---|---|
| **0** | This plan + the throwaway-stack recipe (§7); amend `PLEX_PROFILE_AUTH_PLAN.md` §7 rows D/E to point here | docs links |
| **1** | **Provisioner stops needing a password after the first run**: `ensure_admin()` tries the STORED credential first (`JELLYFIN_API_KEY` / `runtime.json`) and only falls to the wizard path when there is none; resolve the admin by id, not by name; compose `:?` → `:-`; `render_config` no longer generates or writes the key; `.env.example` documents it as OPTIONAL (tooling only) with the reason | pytest (provisioner tests incl. a fresh-install fake), ruff, docs links |
| **2** | **First-run set-password**: fresh install creates the admin password-less; the api exposes "your account has no password" as a **server fact** on `me()`; a signed-in session whose own account has no password may reach NOTHING but the set-password route and `/api/auth/*`; the self-service change route (`CurrentPw` + `NewPw`, empty `CurrentPw` allowed for a password-less own account) is what sets it | pytest (the gate refuses every media/admin router; a set publishes the flag as false), contract snapshot |
| **3** | **Household: role vs name.** The Household screen shows an **Administrator** badge and the account's real name; rename (`POST /Users?userId=`) with the rails (typed confirmation? not for a rename; the last-admin rail applies to policy changes only); the picker/header/sidebar never label a person by their role | tsc, vitest, `check_household_ui.py` + `check_profile_picker.py` (new scenarios), build |
| **4** | **Self-service password screen** for every profile (this is Phase D's other half): change my own password with `CurrentPw` + `NewPw`; honest messaging for a password-less account | gates + DOM check |
| **5** | **Recovery, documented and tested**: `rkm-cinema.ps1 reset-admin-password` → reads the API key from the volume (never from `.env`), prompts for a new password, calls `POST /Users/Password?userId=…&ResetPassword=true`, then VERIFIES by signing in; `OPERATIONS.md` gains the runbook and the "forgot everything" ladder | the tool's own verification output; pytest for its pure parts |
| **6** | ADR (the credential model), docs truth pass (`ARCHITECTURE`, `OPERATIONS`, `README`), PROGRESS record | full suite + docs links |

## 7. Verification, and how we avoid locking ourselves out

**The fresh-install path CANNOT be tested in the sandbox** (no Docker daemon there) and must not be
tested against the real stack (a fresh `jellyfin-config` means losing the household's watch state —
the documented escalation, and unacceptable for a test). So it runs on a **throwaway stack on
RKM-HP**, which is the same repo with its own project name, ports and volumes:

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
$env:RKM_PROJECT="rkm-test"; $env:RKM_DASHBOARD_PORT="8125"; $env:RKM_JELLYFIN_PORT="8099"
.\bootstrap.ps1 -Project rkm-test        # exactly how it is invoked is Phase 1's business
docker compose -p rkm-test down -v       # the volumes go; nothing of yours was ever in them
```

What must be PROVEN there, in order, with the console output quoted in the record:

1. an empty `jellyfin-config` provisions an admin **with no password**;
2. signing in with a blank password lands on **set-your-password**, and NO other route answers
   (media, household, library) until one is set;
3. setting it works, and the picker then behaves exactly as it does today;
4. an API key resets that password (`ResetPassword: true`), proving the break-glass rail;
5. **renaming** the admin does not break the next `bootstrap` run (the id-not-name rule);
6. the throwaway stack is destroyed with `down -v` and the real stack is untouched.

Only after that does the change touch his real `.env`.

## 8. Escape hatches (unchanged, and stated so nobody "improves" them away)

* **The API key in `rkm_shared`** — the break-glass credential (§3a), and what the recovery command uses.
* **`RKM_JELLYFIN_ADMIN_PASSWORD` left in `.env` with a value** — still honoured as the first-run
  password and by the tools. Nothing removes that ability; it is the documented manual override.
* **`RKM_AUTH_REQUIRED` stays `false`** unless he arms it; nothing here flips it (§4 of
  `PLEX_PROFILE_AUTH_PLAN.md`, user decision 2026-09-12).
* **Jellyfin's own dashboard** on the host remains a path that knows nothing about this app — but note
  it also needs the admin's password, so it is NOT the first-line recovery: the volume API key is.
* Arming enforcement while the admin has no password would be worse than useless — Phase 2's gate
  makes that state unreachable rather than merely discouraged.

## 9. Honest open questions (answers needed before Phase 2 ships, not before it is written)

1. Does Jellyfin's startup wizard accept an **empty** password (`POST /Startup/User {"Name": …, "Password": ""}`)?
   If it refuses, Phase 1 creates the admin with a random password and **immediately clears it** via
   the API key path — which would also prove §3a early.
2. Should the **rename** also be available for members (Household already lists them), or only for the
   administrator's own account? (Phase 3 assumes both, since the rail is the same.)
3. Does a member's **self-service** password change need the administrator's approval to be
   discoverable, or is it simply a Settings entry every profile sees? (Phase 4 assumes the latter.)

## 10. Risks

1. **Lockout (the whole point of the user's warning)** — mitigated by §4's mandatory order, §7's
   proof on a throwaway stack, and §8's break-glass. The failure mode to fear is not a wrong password;
   it is an account that can sign in but cannot select a profile.
2. **A rename breaking provisioning** — mitigated by the id-not-name rule (§5).
3. **`.env` regrowth** — if any code path still generates the key, the value comes back and the whole
   change is cosmetic; Phase 1 removes the generation AND asserts its absence in a test.
4. **Tools losing their login** — accepted deliberately (decision 2 of §2): the key stays optional and
   documented, and the workaround for a password-less-by-default world is a LATER investigation.
