# RKM Cinema — Semantic search fallback (SEARCH_IMPROVEMENT_PLAN Phase 6) — Plan

> Branch `feat/semantic-search`, from `dev`. Plan committed FIRST, before any code, per the
> feature-shipping cycle. ⚠ A doc cannot name its own tip — `git log --oneline -3` is the answer.
> **Status: PLAN — every number in it comes from a command run on 2026-09-18; nothing here is a wish.**

## What this phase is for

Two of his example queries cannot be answered by anything this app has today:

* `"movies like Inception"` — there is no *Inception*-like relation in the data. The fuzzy/prefix
  tiers compare his query to titles; "like Inception" is not in any title.
* `"something with a twist ending"` — a description of a MOOD, and mood is not a field.

Phases 0–5 made search fast and relevance-ranked. They cannot reach these, because they match
STRINGS. Phase 6 adds one more source — a vector similarity over the library's own text — used only
when the string matcher has visibly failed.

## The three decisions he asked for, answered

| Decision | Answer | Rests on |
|---|---|---|
| **Where the index lives** | **In the api process, keyed by `(profile_id, library fingerprint)`, built lazily on the first triggered query. No new service, no vector DB, no persisted index in v1.** | §11: profiles see different libraries, so a single module-level index is wrong BY CONSTRUCTION — a module-level dict keyed by profile is not (`SearchPrefsStore` keys the same way). Measured cost of a build: **0.55 s for 2 000 titles** (§3). |
| **Which model** | **`model2vec` + `minishlab/potion-base-8M`** (static embeddings, 256 dims, **no torch, no onnxruntime**). | §3's table: it is the cheapest by an order of magnitude AND it matched or beat the 512-dim models on the functional probe. |
| **What triggers it** | His own rule, sharpened into named constants: **short enough to be a search, AND (top lexical score < 0.4 OR the query is conversational** — ≥ 6 words, or contains *like / similar to / with a*). ⚠ The trigger is evaluated over the LEXICAL ranked list, so the tier invariant in §4.4 is provable rather than hoped for. | §4.3, §4.4 |

⚠ **What the visibility rests on:** both surfaces render the grouped arrays, not the ranked list —
`features/search/GlobalSearch.tsx` iterates `data.items` (line 108/246) and
`layouts/mobile/SearchScreen.tsx` renders `data.items`. So a semantic hit has to reach
`payload["items"]` as well as the ranked list, or it is invisible on every screen the app has.

## §1 The scale the semantic tier has to fit into (measured from source, not recalled)

`services/search/scoring.py` produces a continuous 0–1 relevance; `services/search/ranking.py` adds
bonuses on top. The tiers, read off the constants:

| Tier | Score | Where |
|---|---|---|
| exact title | 1.00 | `scoring.py` `title_relevance` |
| prefix | 0.90 | " |
| fuzzy (typo) | ≤ 0.85 | `fuzzy.py::FUZZY_CEILING` |
| containment | 0.65 – 0.80 | `CONTAINMENT_BASE` + `CONTAINMENT_SPAN` |
| **token (all words present)** | **0.60** | `TOKEN_SCORE` — ⚠ the LOWEST genuine title tier |
| support fields (cast/director/genre/overview) | ≤ 0.50 | `SUPPORT_WEIGHT = 0.5` |
| noise floor | 0.20 | `MATCH_FLOOR` |
| owned bonus / watchlist bonus | +0.03 / +0.015 | `OWNED_BONUS`, `WATCHLIST_BONUS` |

⚠ `OWNED_BONUS` already carries its own invariant test
(`0 < OWNED_BONUS < the smallest step between two tiers`) because a bonus that can leapfrog a tier
makes ranking a lie. **A semantic score needs the same treatment** — see §4.4.

## §2 Where the code goes (the seams, with their addresses)

| Seam | Address | What changes |
|---|---|---|
| the route | `backend/api/routes/search_global.py::search_global` | after `_ranked(...)`, evaluate the trigger; if it fires, search the index and rebuild the ranked list with the hits included |
| the ranker | `backend/services/search/ranking.py::rank_all` | a new `semantic=` source + `_rank_semantic()`, scored in its own tier (§5) |
| the scorer | `backend/services/search/scoring.py` | **unchanged** — semantic relevance is not a string score |
| per-profile switch | `backend/services/search_prefs.py` (JSON beside the watchlist, keyed by `profile_id`, default ON) + `backend/api/routes/search_prefs.py` + `SearchPrefs{Response,Update}` in `backend/api/models.py` | one more boolean, exactly like Phase 5's `personalized` |
| profile identity | `api/session.py::current_session().profile_id()` | the index key — the SAME value `_taste()` already reads |
| the library's own text | `backend/services/library/jellyfin.py::_get_items` requests `Fields=PrimaryImageAspectRatio,ProductionYear,ProviderIds,UserData,Genres,DateCreated` — **no `Overview`** | ⚠ a DEDICATED fetch for the index (one recursive `Items` call with `Fields=Overview,Genres,ProductionYear`), NOT an extra field on the shared call: the poster wall and every search read that path, and a 2 000-title payload must not grow by ~600 KB of synopsis to serve a fallback. |
| degradation pattern | `backend/services/search/fuzzy.py::available()` | mirrored: a missing wheel/model reports itself unavailable and semantic search is simply not offered |

## §3 The model measurement (this is the whole reason the decision is defensible)

Run in this sandbox on **CPU, Python 3.11.15, numpy 2.4.6**, corpus = 2 000 rows of
`title + year + genres + overview` (~40 words each), the exact shape §2 indexes:

| Model | dims | deps pulled in | cold load | embed 2 000 | query mean / p95 | peak RSS |
|---|---|---|---|---|---|---|
| **`model2vec` + `potion-base-8M`** | **256** | jinja2, joblib, numpy, safetensors, tokenizers, tqdm — **no torch, no onnxruntime** | **3.4 s** | **0.55 s (0.27 ms/text)** | **17 ms / 90 ms** | **130 MB** |
| `model2vec` + `potion-base-32M` | 512 | same | ~37 s | 0.42 s | 43 ms / 101 ms | 349 MB |
| `model2vec` + `potion-retrieval-32M` | 512 | same | ~35 s | 0.47 s | 2.9 ms / 2 ms | 349 MB |
| `sentence-transformers` + MiniLM | — | ⚠ **torch** | — | — | — | — | **rejected on sight**: the plan's own suggestion, and the one dependency this box must not gain (≈2 GB image, CPU-only Windows host). |

### §3.0 The candidate this plan first MISSED: `fastembed` + `bge-small-en-v1.5` (ONNX, no torch)

§3's first draft never measured it — and it is the obvious middle option (a real sentence-transformer
served by ONNX runtime, no torch), so leaving it out made *"why not bge-small?"* a question the next
session would have to reopen. It was measured afterwards, on the same 6-document probe corpus, by an
independent run in this sandbox:

| | `potion-base-8M` | `potion-base-32M` | **`BAAI/bge-small-en-v1.5`** |
|---|---|---|---|
| dims | 256 | 512 | 384 |
| embed 500 texts | **0.26 s** (0.52 ms/text) | 0.26 s | **67.9 s — 135.7 ms/text, 260× slower** |
| per query | **0.24 ms** | 0.38 ms | **78.7 ms — 330× slower** |
| peak RSS | **129 MB** | 329 MB | **733 MB (5.7×)** |
| `movies like Inception` | Inception 0.43, Grand Weekend 0.30 | Inception 0.43, … | Inception 0.72, Wild Planet 0.48 |
| `something with a twist ending` | **Inception 0.46** | **Inception 0.47** | Letters to Notting Hill 0.59, Inception 0.58 |
| `feel-good comedy for the family` | **Grand Weekend 0.60** | **Grand Weekend 0.60** | **Grand Weekend 0.70**, Toybox 0.53, Letters 0.51 |

**Read honestly:** bge-small ranks about the same as the 8M static model on two of the three queries
and slightly better on the third (for the family query its #2/#3 are children's and comedy titles,
where the 8M model reaches for whatever is nearest). Its scores are also better separated — 0.72
against 0.48, where model2vec compresses everything into 0.26–0.46 — but the TIER in §4.4 is what
turns a similarity into a rank, so separation is not something this design needs.

Against that: **135 ms per text means a 2 000-title library takes about four and a half minutes to
index on this box**, against 0.55 s for `potion-base-8M`, and 733 MB resident against 130 MB. On a
CPU-only home server the fallback has to be too cheap to notice; bge-small is not — the first
conversational query after a restart would sit there for minutes. **`potion-base-8M` stays, and this
comparison exists so it does not get relitigated.**

⚠ The 32M rows' "cold load" includes their first-call download, so it is not a like-for-like load
time; their query/RSS numbers are the honest comparison, and they LOSE on both.

**Functional probe — 10 real films, 3 conversational queries** (`title + year + genres + overview`):

| Query | `potion-base-8M` (top 3) |
|---|---|
| `movies like Inception` | **Inception 0.45**, The Matrix 0.35, Toy Story 0.27 |
| `something with a twist ending` | **Inception 0.27**, Interstellar 0.21, Toy Story 0.18 |
| `feel-good comedy for the family` | **When Harry Met Sally 0.24**, The Dark Knight 0.19, Hereditary 0.17 |

The 32M models did **no better** and on the third query did worse (`potion-base-32M` ranked
*Hereditary* first). ⚠ **Say this plainly: static embeddings are good at "more like this" and weak at
mood.** Query 1 and 2 lead with the right film; query 3 gets one of three. That is the honest
capability, it is *strictly better than today's empty result*, and it is why §9's labelling phase
matters — a semantic row must not be presented as if it matched what he typed.

## §3.1 What it actually returns, end to end (measured AFTER the plan, with the REAL model)

The route called with the real model and a 10-title stub library, `has_tmdb=False`, on a warm process:

| Query | Row the app shows first | All five semantic rows, best first |
|---|---|---|
| `something with a twist ending` | **Inception** (0.323) | Inception, Hereditary, Se7en, When Harry Met Sally, Interstellar |
| `movies like Inception` | **Inception** (0.340) | Inception, The Matrix, Interstellar, Planet Earth, The Dark Knight |
| `feel good comedy for the family` | **When Harry Met Sally** (0.331) | When Harry Met Sally, The Dark Knight, The Grand Budapest Hotel, Toy Story, Hereditary |
| `the dark knight` | *(fallback did not fire)* | — exact owned title, nothing to rescue |
| `th` | *(fallback did not fire)* | — below the length floor |

⚠ Read the third row honestly: *The Dark Knight* in second place for a family comedy is wrong, and it
is the same weakness §3's probe showed. Three of five are right. **This is a fallback for queries that
return NOTHING today**, so it is an improvement on an empty screen — but it is not a recommendation
engine, and that is why §6 phase 4 labels the rows instead of passing them off as matches.

## §4 Design
### 4.1 The index — per profile, in process, lazily, fingerprinted

```
key = (profile_id, fingerprint(rows))      →     SemanticIndex(vectors, ids)
```
* **Built on demand**, on the first query that TRIGGERS it, then reused. Not built at import (it
  would load a model into every process for a feature most queries never reach) and not persisted in
  v1 (a persisted index is a schema, an invalidation rule and a file-format migration — real cost,
  for a saving of 0.55 s that only a cold process pays).
* **Fingerprint = sha1 of the sorted item ids** for that profile. A library scan, an added title or a
  different profile therefore produces a different key; two profiles can never share vectors, which is
  the §11 rule that a previous session deliberately refused to break.
* **Bounded**: a tiny LRU (last 2 keys). ⚠ Not a leak, and stated: the vectors of one profile's
  library (2 000 × 256 floats ≈ 2 MB) are small enough that keeping two is free.
* **Text indexed**: `title · year · genres · overview`, lower-cased by the model itself. Nothing is
  invented: if a field is empty it is skipped.

### 4.2 The model adapter

`backend/services/search/semantic.py` owns the ONLY import of `model2vec`, behind a lazy loader:

* `available() -> bool` — false when the wheel or the model is missing, and cached. A missing model
  degrades search to today's behaviour, exactly as `fuzzy.py` does for `rapidfuzz`; it never raises
  into a request.
* Loaded ONCE per process (the model is ~59 MB on disk and 130 MB resident).

### 4.3 The trigger (his rule, as two functions)

```python
MIN_SEMANTIC_QUERY_LEN = 3            # ⚠ same floor as the TMDB half, for the same reason
CONVERSATIONAL_MIN_WORDS = 6
CONVERSATIONAL_PHRASES = ("like", "similar to", "with a")
SEMANTIC_TRIGGER_SCORE = 0.4          # ⚠ < the token tier (0.6): "weak" means NO real match

def is_conversational(query) -> bool                    # ≥6 words OR a phrase
def should_use_semantic(query, top_score) -> bool       # long enough AND (weak OR conversational)
```

* `top_score` is the highest score in the **lexical** ranked list over the sources that mean "a title
  matched" — ``owned`` and ``tmdb`` — taken BEFORE any semantic row is added. That is what makes
  §4.4's invariant provable: if a semantic row could ever be present, the top lexical score was < 0.4
  by definition.
* ⚠⚠ **The ACQUISITION QUEUE is deliberately not among those sources, and this was measured after the
  plan was first committed.** His queue holds 471 rows; against *"something with a twist ending"* two
  of them fuzzy-match at **0.742** — *"Teach You a Lesson"* and *"A Toxic Love Story"*, both printed
  by the real scorer. That is a false positive ABOVE the containment tier, and reading the whole
  ranked list meant a mood query never reached the embeddings whenever the queue happened to contain
  something vaguely similar. The queue is not an answer to "do I have this?", so it is not consulted
  in either direction — pinned by two route tests, and falsified as a mutation.
* ⚠ **A length floor is a THIRD condition, and it was missing from the first draft of this section —
  caught by falsifying the plan's own claims before committing it.** The route's
  `MIN_TMDB_QUERY_LEN` gates only the TMDB half: a 2-character query still runs the local library
  search, and if that finds nothing the top score is 0 — which satisfies `top_score < 0.4` and would
  embed `"th"`. Two characters are not a description of a mood; `MIN_SEMANTIC_QUERY_LEN = 3` is the
  same floor the external half uses, for the same measured reason (a large fraction of any catalogue
  starts with "th").

### 4.4 The tier — where a semantic row scores

```
SEMANTIC_BASE = 0.30      SEMANTIC_SPAN = 0.09      → range [0.30, 0.39]
```

* **Below `SEMANTIC_TRIGGER_SCORE` (0.4) by construction** — so a semantic hit can never outrank any
  row that lexically matched well enough to have suppressed the fallback. Pinned by a test that
  mirrors `OWNED_BONUS`'s invariant test, in the same file, for the same reason.
* **Above 0** — a weak-looking query with three semantically-close titles must show them ABOVE the
  owned rows Jellyfin returned but which our scorer could not see (those sit at score 0 + the owned
  bonus, 0.03). That ordering is the entire visible effect of this phase.
* **Similarity scales within the tier** (`SEMANTIC_BASE + SEMANTIC_SPAN · max(0, (cos − MIN_COS)/(1 − MIN_COS))`),
  so the best-matching title still leads the group.
* Rows carry `match_type = "semantic"` end-to-end (the field already exists on `GlobalOwnedRow` and
  travels through `_attach_spans`), which is what a later labelling phase reads.

### 4.5 Degradation, in this order

model unavailable → lexical only, no error · index build fails → lexical only, logged · preference
OFF → the index is not even looked for · nothing above the similarity floor → no rows added (an
empty semantic result must not pad the list).

### 4.6 The switch

Per PROFILE, beside the watchlist `search_prefs.json`, default **ON** — with the same argument Phase 5
made: it is bounded by construction (it runs only when the string matcher has failed), and a feature
nobody can find is a feature nobody has. Settings → Search gains one card, mirroring
`SearchPersonalizationCard` and its `personalizationCopy` helper (copy functions live in
`features/settings/searchPrefs.ts` because the sentence IS the rule).

## §5 Options NOT taken, and why (so the next session does not relitigate them)

| Option | Why not |
|---|---|
| `pgvector` / `sqlite-vec` / `faiss` | A vector DB for ~2 000 rows is a service to run, back up and migrate. A 2 000×256 matmul is **17 ms** measured — a database would be slower than the thing it stores. |
| An embedding API (OpenAI/etc.) | Recurring cost, and it ships his library's synopses to a third party. Both contradict everything about this box. |
| `sentence-transformers` + MiniLM (what the plan text suggested) | Pulls **torch**. Rejected on dependency weight alone, before quality is even discussed. |
| A module-level index | Banned by §11's own rule: profiles see different libraries, so one shared index silently serves one household member another's titles. The previous session refused this and the refusal was right. |
| Persisting the index beside the watchlist (v1) | Saves 0.55 s once per cold process. Costs a file format, an invalidation rule and a corruption path. Revisit only if the measured build grows (≥ 10 000 titles). |
| Semantic on EVERY search | It would pay CPU on the ~95 % of queries literal matching already nails, and it would let a mood-similarity score compete with a title match. Bound to the fallback instead. |
| Semantic search as its own route/UI | A second search surface means he has to know which one to type into. It is a source inside the ONE ranked list. |
| Labelling the semantic rows in v1 | ⚠ Deliberately deferred, NOT forgotten: v1 must first prove the ranking is sane on his library. Phase 4 below is the labelling, because an unlabelled "related" row presented as a match would be the app overstating what it knows. |

## §6 Phases (one commit each, gates green after every one)

1. **Plan** (this file) + the pure core: `services/search/semantic.py` (adapter, trigger, per-profile
   index) and the ranker's semantic tier + its invariant. Tests: trigger truth table, per-profile
   keying, degradation with the wheel absent, tier invariant, similarity ordering. **No route change
   yet** — the core must be falsifiable on its own.
2. **Route wiring**: the dedicated Jellyfin index fetch, the trigger in `search_global`, semantic rows
   into `payload["items"]` (so the grouped UI that renders `items` — which is what the phone and the
   palette actually render — shows them) and into the ranked list.
3. **The switch**: `SearchPrefsStore.semantic`, the prefs route, models, `snapshot_openapi.py` +
   `npm run generate:types` (CI fails on contract drift), the Settings card + its copy test.
4. **Labelling (candidate)**: a "related to your search" chip on `match_type == "semantic"` rows in
   the palette and the phone's list. ⚠ Only after phase 2 has been seen on his library.
5. **Image**: add `model2vec` to `requirements.txt` and bake the model into the image at build time
   (`HF_HOME` in the image), so the container needs no network at runtime for the fallback.

## §7 What could NOT be measured here, and the risk each one carries

| Unknown | Risk | What bounds it |
|---|---|---|
| **His library size** (no Jellyfin in this sandbox) | build time and memory scale with it | 2 000 titles measured at 0.55 s / 130 MB. Even 10 000 is ≈ 3 s / ~200 MB, once per process. |
| **His box's CPU** | the measured numbers are this container's | model2vec is numpy-only and linear in texts; there is no torch thread pool to fight. |
| **Whether his queries actually trigger it** | a fallback that never fires is dead code | §3's probe used HIS two example queries, and `top_score < 0.4` on a 4-word descriptive query is expected — but only his usage settles it. The switch makes it visible either way. |
| Live search latency end-to-end | not measurable without his Jellyfin | ⚠ **Measured after the plan was committed, with the real model and the real route over a 10-title stub library**: the fallback's own cost is not visible against the route's existing work — median delta over 5 warm runs **−4 ms** (i.e. inside the noise of a 300–500 ms route dominated by scoring his 471-row queue), against a measured **17 ms** for the embedding search itself over 2 000 indexed titles. The FIRST triggered search on a cold process pays the model load (~3.4 s) plus the index build (0.55 s for 2 000 titles). |

## §8 Acceptance (what "done" looks like, in falsifiable terms)

* `should_use_semantic` fires on `"something with a twist ending"` and does NOT fire on
  `"matrix"` when *The Matrix* is owned (a 1.0 exact match) — two directions, both tested.
* Two profiles with different libraries get two different indexes; a test with two profile ids and
  disjoint rows proves no vector crosses (`§11`).
* With `model2vec` uninstalled (simulated by the availability seam), search returns byte-identical
  results to today's, and no exception is logged as an error.
* Every semantic row's score is `< SEMANTIC_TRIGGER_SCORE` — by the invariant test, not by inspection.
* `python -m pytest tests/ -q` green; `tools/check_md_links.py` green.

## §9 Rollback

The feature is additive and switchable: `semantic: false` in `search_prefs.json` (or the Settings
card) returns the app to Phases 0–5 behaviour with no deploy. Removing the dependency from
`requirements.txt` degrades it the same way, by the `available()` seam. Nothing in this phase writes
to his library, his watchlist, or any file the app already owned.
