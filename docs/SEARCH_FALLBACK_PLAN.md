# Search: external metadata fallback — plan and measurements

**His report (2026-09-13), third bug:** *"Search only matches local library, doesn't surface
external/metadata matches"* — searching **"sholay"** returns only the one local row that contains the
string (`Sholay — Special Ops S1E8`) and never the real **Sholay (1975)**, with the stated root cause
*"Search is currently scoped to local library metadata only … There's no fallback to an external
metadata provider to resolve well-known titles that aren't in the library yet."*

## 0. ⚠ The stated root cause is NOT what this codebase does

The external fallback is **already built and working** — `GLOBAL_SEARCH_PLAN` Phases 1–3 shipped on
2026-09-09 (`48bd35c`, `03b7be5`). Measured against the real vendor, from this sandbox, with his own
key:

```
$ cd backend && python /workspace/tmp/probe_search.py
has_tmdb() = True   (TMDB_API_KEY present: True)
TMDB cache TTL = 21600s

--- the VENDOR: TMDBService.search_multi('sholay') (live) ---
  13 raw result(s)
  0: tmdb_id=12259 type=movie year=1975 pop=6.9047 title='Sholay'      <- the film he wants, result #0
  1: tmdb_id=586776 type=movie year=2019 pop=1.0803 title='The Sholay Girl'
  ...
```

So the vendor path works, ranks the right film first, and the dedupe rule would keep it:

```
--- would TMDB's Sholay survive dedupe against the owned show? ---
  'Sholay' (1975) type=movie -> dropped_as_duplicate=False
```

**What he got instead is a GATE, not a missing feature.** `backend/api/routes/search_global.py:105`:

```python
payload["strong_match"] = owned_strong_match(owned_raw, query) >= 2      # <- the bug
...
if cfg.has_tmdb() and not payload["strong_match"]:                       # <- discovery skipped
```

`owned_strong_match` is the best `title_match_score` across owned rows, and its tiers are
(`services/global_search.py`):

| score | meaning |
|---|---|
| 3 | **exact** normalised title |
| 2 | containment, len ≥ 3 — `q in t` OR `t in q` |
| 1 | every significant token contained, len ≥ 5 |

Measured with the real rule, on the titles his library could plausibly hold:

```
  owned title 'Sholay — Special Ops'   -> score 2   (gate needs >= 2 to HIDE discovery)
  owned title 'Sholay Special Ops'     -> score 2
  owned title 'Sholay'                 -> score 3
```

⇒ A TV episode whose **longer, different** title happens to contain "sholay" scores 2, which is
`>= 2`, which sets `strong_match` — and the route then **never asks TMDB at all**. The user-visible
result is exactly his symptom: one unrelated episode, no "not in your library" section.

⚠ **And there is a second gate in the frontend** — `GlobalSearch.tsx:234`:
`showDiscovery = Boolean(data && !data.strong_match && data.discovery.length)`. Two places decide the
same thing, so the backend could be fixed alone and the UI would still hide the rows. That is the same
drift pattern as the button sizing in bug 2: the same rule written twice.

⚠ **A latent landmine sits behind both** — the dedupe threshold is also 2:
`is_duplicate_discovery` drops a candidate whose title scores `>= 2` against an owned row. With the
**years** known (both sides) a remake guard fires first, which is why the probe above kept 'Sholay'
(1975) vs the owned show (2025). But if his row carries **no year**, the guard cannot fire and the real
Sholay would be dropped as a "duplicate" of the unrelated series — the fix would look like it did not
work on his data while passing every test written against a year-bearing fixture. Measured:

```
  'Sholay' (1975) vs owned {'title': 'Sholay — Special Ops'}   (no year) -> dropped_as_duplicate=True
```

## 1. What already exists (his "suggested implementation", audited)

| His suggestion | Status in the code today |
|---|---|
| two sections, library first | ✅ existing: `In your library` + `Discover · not in your library` |
| external rows differ visually, with Add/Request | ✅ existing: "not in your library" + `Add to watchlist` → `Download` (the Suggest card contract) |
| poster, year, type per external row | ✅ existing |
| debounce before the external query | ✅ 200 ms (`GlobalSearch.tsx:13`), plus `staleTime: 15s` |
| local first, then top 5–6 external ranked by provider relevance | ✅ existing (`search_multi` order, `[:6]`) |
| dedupe against owned titles | ✅ existing (`is_duplicate_discovery`) |
| fail gracefully, show local results only | ✅ existing (logged, degrades) |
| **cache external results 5–10 min** | ❌ **absent on purpose**: `TMDBService.search_multi` is documented *"Lightweight and uncached — /api/search should stay fresh"* |
| **TheTVDB for TV** | ❌ not wired, and **`TVDB_API_KEY` is not set** in either `.env`; `search_multi` already returns `media_type` `movie` **and** `tv` |

## 2. Decisions

1. **The library counts as having ANSWERED the query only on an EXACT title match** (`score == 3`).
   The gate's job is "does the library unambiguously have what was asked for?" — and "Sholay — Special
   Ops" is a different work from "Sholay", so containment must not suppress the external search. One
   named constant (`EXACT_TITLE_SCORE`) is used by **both** the gate and the dedupe, so the two cannot
   drift apart the way they just did.
   ⚠ **This knowingly relaxes a deliberate earlier decision** (`GLOBAL_SEARCH_PLAN` Phase 3: discovery
   appears *only* when no strong owned match exists, to keep the dropdown calm). Say so rather than
   pretend the old rule was a bug: the calm case survives — search "the matrix" while owning *The
   Matrix* and the library answers exactly, so nothing extra appears. Search a title the library only
   *contains* and the external section now appears, which is what this report asks for.
2. **Dedupe requires an exact title too**, which fixes the no-year landmine in both directions: a
   same-name remake (different year) and an unrelated longer title can no longer swallow the candidate.
   The **TMDB-id** path is untouched — the strongest identity signal stays strongest.
3. **One gate, not two.** The frontend renders the external section whenever the server sent rows;
   `strong_match` stops being a second decision point (it stays in the payload as documentation).
4. **Cache the EXTERNAL half server-side, 5 min, keyed on the normalised query** — his ask, and this
   change increases how often the path runs. Deliberately NOT cached: the local half. The client's
   `staleTime` stays 15 s because the local rows carry *playback state* (progress, next episode), so
   caching the merged response for 5–10 min — his literal suggestion — would show him stale watch
   progress. Metadata is stable for hours; progress is stale in seconds.
5. **No TheTVDB integration.** `TMDB_API_KEY` is set, `TVDB_API_KEY` is not, and TMDB's multi-search
   already covers TV — adding a second provider would mean a new key, a second ranking model to merge,
   and a second failure mode, for no measured gain (13/13 of his example query's rows came from TMDB).
6. **Debounce stays 200 ms.** The server-side cache is what protects the API; raising the client
   debounce only makes the search feel slower.

## 3. Acceptance (what the tests must pin, in both directions)

* `owned_strong_match(["Sholay — Special Ops"], "sholay") == 2` **and** the route still returns
  discovery rows for it (the falsification: with the old `>= 2` gate, discovery is `[]`).
* exact owned match (`"3 Body Problem"` against an owned *3 Body Problem*) still suppresses discovery.
* the no-year dedupe case: TMDB 'Sholay' (1975) survives against an owned "Sholay — Special Ops"
  **with no year and with a year**.
* two identical searches inside the TTL make **one** TMDB call.
* the frontend renders the external section when the server sends rows **with `strong_match: true`** —
  the assertion the old double gate fails.
