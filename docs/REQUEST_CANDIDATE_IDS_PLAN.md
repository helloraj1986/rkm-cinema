# RKM Cinema — a PICKABLE ambiguity list (KNOWN_ISSUES §7, option (c)) — Plan

> Branch `feat/request-candidate-ids`, from `dev`. **Plan committed FIRST, before any code**, per the
> feature-shipping cycle — see `docs/SEMANTIC_SEARCH_PLAN.md` for the shape this follows.
> ⚠ A doc cannot name its own tip: `git log --oneline -3` is the answer.
> **Status: PARKED — written 2026-09-19, then dropped on his instruction the same day.** Nothing below has
> been implemented and **no code was written**: this commit is the plan and nothing else. ⚠ **Do not start
> phase 2 without reading §6** — it is blocked on a real sample of what his Radarr returns for an
> ambiguous title, which he was asked for and chose not to supply before parking the phase. Every address
> in §1 was READ from source on 2026-09-19, not recalled — and §1's findings are why this phase is bigger
> than its one-line description.

## What this is for

His decision, 2026-09-19, answering `KNOWN_ISSUES` §7 **(c)**:

> *"Put an id on each 409 candidate so the list becomes pickable."*

Today a request that matches more than one title **dead-ends**. The surface renders the server's own
sentence, a list of the matched titles — and then *"This app cannot tell which one you meant — add it
from Radarr or Sonarr instead."* That last sentence is the honest admission of the defect: the app has
nothing to re-request **with**, so the only way to act on the ambiguity is to leave the app.

## §1 The ground truth (read from source — and NOT what §7 assumed)

`KNOWN_ISSUES` §7 records that the server answers `409` with
`detail: {message, candidates: [{title, year}]}`. ⚠ **Measured: that array is EMPTY in production.** The
structured list — **which already carries tmdb ids** — is destroyed inside the Radarr service and never
reaches the wire. Walking it, bottom to top:

| # | Where | What actually happens |
|---|---|---|
| 1 | `services/radarr.py:13-22` | `RadarrMovie` has `id`, **`tmdbId`**, `title`, `year`, `imdbId`. The id **is** there. |
| 2 | `services/radarr.py:298-318` | `add_movie` builds `candidates = self.search_movies(title, year)` — a `list[RadarrMovie]`. |
| 3 | `services/radarr.py:316-318` and `:320-326` | Both ambiguous branches **build a human sentence** — `"Multiple Radarr matches — pick one: A (1999, tmdb:603); B (…)"` — and return `AddResult(False, None, msg, "ambiguous")`. ⚠ **`movie=None`: the list dies here.** |
| 4 | `services/radarr.py:47-51` | `AddResult` has exactly ONE record slot (`movie: Optional[RadarrMovie]`) and **nowhere to put a list**. |
| 5 | `services/acquisition/radarr.py:80-82` | The provider passes `item=add.movie` → `None`. Sonarr mirrors this exactly (`services/sonarr.py:377-384`, `services/acquisition/sonarr.py:152-154`). |
| 6 | `application/commands/request_media.py:179-185` | `_candidates()` reads `result.item`, gets `None`, returns `[]`. |
| 7 | `api/routes/media.py:112-119` | The route puts that `[]` on the wire. **So today the client is sent an empty list** and the tiles the person sees come from the message string alone. |

Two further facts that shape the phase:

* `core/exceptions.py:45-49` — `AmbiguousMediaError(candidates, message)` **already models a candidates
  list**, and is **raised nowhere in the live path** (one test constructs it, nothing else references it).
  Either it becomes the carrier, or it is dead code and should be deleted. §2 decides.
* ⚠ **The route takes no body and the router carries no auth dependency** —
  `def request_media_endpoint(media_id: str)` (`api/routes/media.py:79-80`), `router = APIRouter()`
  (`:31`). This phase must not change **who** may write; it adds an optional input to the same write.

And the client half is **already built and deliberately read-only** — this phase adds the id, it does not
rebuild the surface:

| Piece | Address | State |
|---|---|---|
| the structured payload survives the error | `lib/api/client.ts:382-405` (`ApiError.payload`, `ambiguousCandidates()`) | done 2026-09-18 (`47d2966`) |
| the shape a screen renders | `features/watchlist/actions.ts:25-46` (`AmbiguousMatch`, `ambiguousMatch()`) | done |
| the renderer, shared by both shells | `features/suggest/AmbiguousMatches.tsx` | **READ-ONLY on purpose** — its own docstring says the list is unusable and why |

## §2 Design

**One rule shapes everything: the client must never offer a pick the server cannot accept.** So the id
travels end-to-end, and the control appears **only** where a candidate carries one. Nothing here is
"add a button and hope".

**The wire, additive (nothing existing changes shape):**

```jsonc
// 409 — POST /api/media/{media_id}/request
{ "detail": {
    "message": "<the *arr sentence, unchanged>",
    "candidates": [
      { "title": "Sholay", "year": 1975, "tmdbId": 12259 },     // movie
      { "title": "Sholay", "year": 1975, "tvdbId": 12345  }     // series
    ] } }
```

**Choosing one — reuse the canonical identity, do not invent a second id space:**

```jsonc
// POST /api/media/{media_id}/request      (body now OPTIONAL; absent = exactly today's behaviour)
{ "chosen": "movie:tmdb:12259" }
```

`movie:tmdb:…` is the id form every other write in this app already parses, so the chosen candidate goes
back through the SAME `request_media()` with a canonical id — the idempotent path is not duplicated, and
the *arr lookup resolves by TMDB id rather than re-running the ambiguous title search
(`services/radarr.py:296-297` already prefers a TMDB lookup).

| Seam | Address | Change |
|---|---|---|
| the record result | `services/radarr.py:47-51` (+ the Sonarr twin) | add `candidates: list = field(default_factory=list)`; the two ambiguous branches return **the list they already hold** |
| the provider | `services/acquisition/radarr.py:80-82`, `sonarr.py:152-154` | pass `candidates=add.candidates` up |
| the normalized result | `services/acquisition/service.py:52-65` | add `candidates: list = field(default_factory=list)` |
| the flattening | `application/commands/request_media.py:179-185` | read the new field; emit `{title, year, tmdbId}` / `{title, year, tvdbId}`. ⚠ **Keep the `item` path for the success case** — `_candidates` is only reached on ambiguity, but the single-record shape must not be disturbed |
| the route | `api/routes/media.py:79-119` | optional body model; `chosen` present → resolve and re-request. No second route, no change to the no-body path |
| the contract | `api/models.py:611-619` + `snapshot_openapi.py` + `npm run generate:types` | document the id on a candidate. ⚠ CI fails on contract drift |
| the surface | `features/suggest/AmbiguousMatches.tsx` | **pickable iff every candidate carries an id**; otherwise exactly today's read-only sentence — no half-pickable list |
| the action | `features/watchlist/actions.ts` | one `onPickAmbiguous(chosenId)` that re-requests |

**Three rules to keep the control honest:**

1. **A candidate with no id is not pickable.** Mixed lists are treated as not pickable at all — a list
   where *some* rows act and others silently do nothing is worse than a read-only one.
2. **`chosen` must be one of the candidates we returned** for that call, or **422**. Silently adding a
   film the person was never shown would be the app taking a decision it was asked to hand over.
3. **The no-body path is byte-identical to today.** Old client + new server: extra fields ignored. New
   client + old server: no ids → read-only. ⚠ This is what makes the two halves independently shippable.

## §3 Options NOT taken, and why

| Option | Why not |
|---|---|
| A new route, e.g. `POST /api/media/request` | Two request paths to keep idempotent, and two places to get the identity rule wrong. The existing route already owns the idempotent behaviour. |
| The client re-searching by `title`+`year` and requesting the winner | The client would be **guessing which film the person meant** and spending a request on it. That is the opposite of this phase's point. |
| Carrying a candidate **index** instead of an id | The *arr lookup is LIVE, so the list is not stable between the 409 and the retry — an index could point at a different film on the second call. An id survives. |
| Raw `tmdb:603` (or a bare number) in the body | The canonical `movie:tmdb:603` parser exists and is what every other write uses. A second id form is a second place to get it wrong. |
| Raising `core/exceptions.py::AmbiguousMediaError` from the service | ⚠ **Decided: NO.** The route maps a **result** to HTTP, and raising from the service would cross a layer for a state that is already modelled as `RequestMediaState.AMBIGUOUS`. The exception stays dead — **and this phase deletes it**, with `test_health_and_scheduler.py:28`'s use, rather than leaving infrastructure that reads like the live path. If a later session needs it, git has it. |
| Putting the pick inside the toast | The toast is gone by the time a person decides. It belongs in the surface where they acted — which is where `AmbiguousMatches` already renders. |

## §4 Degradation, in order

no ids on the wire → **read-only list, no pick control, no error** (today's behaviour, unchanged) ·
some ids missing → treated as no ids (rule 1) · `chosen` unknown → 422 with a sentence, nothing written ·
*arr unreachable → the existing 502/503 mapping, untouched.

## §5 Phases (one commit each; gates green after every one)

1. **This plan.**
2. **The plumbing** — `AddResult.candidates`, `AcquisitionRequestResult.candidates`, both providers, and
   `_candidates()` emitting ids. Delete `AmbiguousMediaError`. Tests: an ambiguous Radarr **and** Sonarr
   result carries the ids; the success path is unchanged; the old empty-list behaviour is gone.
3. **The route** — the optional body, the validation, and 422. Tests: no body ⇒ byte-identical response;
   valid `chosen` ⇒ the *arr add resolves by that id; unknown `chosen` ⇒ 422 and **no write**.
4. **The client** — pickable rows, the pick action, `AMBIGUOUS_NO_PICK` only when unpickable, the
   contract regen (`snapshot_openapi.py` + `generate:types`).
5. **Gates + falsification** (§7), then the handoff block in `PROGRESS.md`.

## §6 What could NOT be measured here, and the risk each carries

1. ⚠ **There is no live Radarr or Sonarr in this sandbox.** Every ambiguity path is exercised with
   **fakes** — the *shapes* are real, the wiring to a real *arr is NOT. His box is the only place a
   genuinely ambiguous title exists.
2. ⚠⚠ **Nobody knows what his Radarr actually returns for an ambiguous title today.** The only sample in
   the repo is a test fixture (`backend/tests/test_api.py:66`). Phase 2 decides what the id keys are
   called and how the list is assembled — **so this plan asks for one real sample before phase 2 is
   written**: the sentence the app shows when a request comes back 409, and (from Radarr's own log or UI)
   the lookup results behind it. Without it, phase 2 pins a shape to a guess.
3. **Idempotency of the `chosen` path against a live *arr** — adding a film that already exists must
   still answer "already there", not a second add.
4. **Series are not a copy-paste of movies.** Sonarr keys on `tvdbId` (and `tmdbId` for lookups), so
   `tvdbId` is the id that must survive; the plan's wire shape carries whichever the provider has.

## §7 Acceptance — "done", in falsifiable terms

* `cd backend && python -m pytest tests/ -q` — green against the **1338** baseline.
* **an ambiguous result carries its ids** — falsified by emptying the list (a test that passes with the
  list cleared is a test of nothing).
* **the route honours `chosen`** — falsified by ignoring the body: the response must then differ.
* **an unknown `chosen` writes nothing** — falsified by asserting the *arr call count is 0.
* **browser, both directions** (`tools/check_mobile_suggest.py` already drives this 409 through the real
  sheet): with stubbed candidates **carrying ids** the rows are buttons and a real tap sends exactly one
  request naming the chosen id; with candidates **carrying no id** the rows stay inert, the read-only
  sentence is shown, and **no request is sent**. ⚠ The second direction is the one that keeps rule 1
  honest, and it must be run with the ids *removed* from the stub, not with the branch reverted.
* ⚠ **A control that cannot act must not be offered** — the §7 sentence is only correct while there is no
  pick, and a `data-testid` on the pick is how the check tells the two states apart.

## §8 Rollback

Additive end to end. Reverting the **client** alone returns the app to the read-only list with the
backend still carrying ids nobody reads; reverting the **backend** alone leaves a client that finds no ids
and therefore offers no pick. Neither half can leave the other broken — that is rule 3's whole purpose.
