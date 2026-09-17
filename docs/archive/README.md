# `docs/archive/` — superseded documents

⚠ **Nothing in this folder is current.** Each file here is kept for the audit trail: what was believed,
decided and planned at the time. If you arrived from an old comment, ADR or `PROGRESS.md` entry that
points into `docs/`, the file was moved here when it stopped being the truth.

**The current documents are `docs/ARCHITECTURE.md` (the map), `README.md` (how to run it), `docs/adr/`
(the decisions) and `docs/PROGRESS.md` (what is done).**

| File | What it was | Superseded by | Archived |
|---|---|---|---|
| `modular-scalable-architecture.md` | the plan that drove the restructure: freeze `/api`, rebuild the frontend in React/TS, consolidate the backend, CI, retire the legacy app. Phases 0–5 | **EXECUTED.** `docs/ARCHITECTURE.md` §19 (why the stack is what it is), §20 (ADR index); status lives in `docs/PROGRESS.md` | 2026-09-18 |
| `ARCHITECTURE_AUDIT.md` | the Phase-1 audit of the **legacy** app (Plex/Emby, the `app.js` monolith, "56 tests green") against the production-refactor spec | `docs/ARCHITECTURE.md` (most of its "gaps" have since shipped) | 2026-09-18 |
| `ARCHITECTURE_GUIDE.md` | an early architecture guide, written before the modular backend and the React shell existed | `docs/ARCHITECTURE.md` | earlier |
| `RKM_Watchlist_Production_Refactor_Task.md` | the 26-phase production-refactor spec that `ARCHITECTURE_AUDIT.md` audited against | the work it specified landed; the record is `docs/PROGRESS.md` + `docs/adr/` | earlier |
| `progress_download_selection.md` | an early progress/download-selection note | `docs/PROGRESS.md` | earlier |

⚠ **Rule for archiving** (see `docs/ARCHITECTURE.md` §21): a document that stops being current is MOVED
here (`git mv`, so history survives) and gets a banner at the top naming what replaced it. It is never
quietly left in `docs/` to be read as current, and it is never deleted while a comment, ADR or log entry
still points at it.
