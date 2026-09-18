# RKM Cinema — Search Relevance Improvement Plan

## Why current search doesn't feel like IMDb

Looking at `SEARCH.md`, both endpoints work like this today:

- `/api/search`: substring/field match against watchlist + a raw TMDB `search_multi()` call, results returned as two separate lists.
- `/api/search/global`: a **0–3 discrete score** (`title_match_score`) used only as a **gate** (`strong_match: score >= 3`) to decide whether TMDB discovery shows at all — not to rank anything.

Neither endpoint actually **ranks** results by relevance. There's no fuzzy matching (typos kill exact-match scoring), no weighting across fields (a cast match and a title match count the same), and no query understanding (a query like `"tom hanks 90s"` is just matched as one literal string). IMDb/Google-quality search "feels smart" because of three things, roughly in order of impact:

1. **Typo tolerance / fuzzy matching** — biggest perceived-quality win for the least effort.
2. **Weighted, continuous relevance scoring** merged into one ranked list, instead of a 4-value discrete score used as a gate.
3. **Query understanding** — pulling year/genre/person intent out of free text before matching.

Below is a phased plan ordered by effort-to-impact ratio. Each phase is independently shippable.

---

## Phase 0 — Foundation: a shared scoring module

Right now scoring logic (`title_match_score`, watchlist field matching, TMDB relevance) is scattered and endpoint-specific. Before improving relevance, consolidate it.

**Create `services/search/scoring.py`:**

```python
from dataclasses import dataclass

@dataclass
class FieldWeight:
    title: float = 10.0
    original_title: float = 8.0
    cast: float = 4.0
    director: float = 4.0
    genre: float = 2.0
    overview: float = 1.0
    collection: float = 3.0

@dataclass
class ScoredResult:
    item: object
    score: float
    matched_fields: list[str]
    match_type: str  # "exact" | "prefix" | "fuzzy" | "token" | "semantic"
```

**Agent tasks:**
- [ ] Extract all match logic from `global_search.py` and `watchlist.py` into `services/search/scoring.py`.
- [ ] Replace the 0–3 discrete `title_match_score` with a continuous 0.0–1.0 normalized score per field, then combine via `FieldWeight`.
- [ ] Keep `owned_strong_match()` as a thin wrapper that calls the new scorer and applies a threshold — don't let call sites depend on internals of the scorer.

This phase touches no user-facing behavior; it's a refactor that everything else builds on.

---

## Phase 1 — Fuzzy matching & typo tolerance
**(Highest perceived-quality win)**

Today, `"the dark knght"` or `"schwarzeneger"` returns nothing from library/watchlist matching because it's presumably doing `in` / normalized substring checks. TMDB's own API has some fuzzy tolerance, but your *owned library* search does not — which is backwards, since owned content should be your strongest, most confident source.

**Add to `requirements.txt`:** `rapidfuzz` (fast, C-accelerated, MIT-licensed — much faster than `python-Levenshtein` for this use case).

**Implementation in `scoring.py`:**

```python
from rapidfuzz import fuzz, process

def fuzzy_title_score(query: str, candidate: str) -> float:
    q, c = normalize_title(query), normalize_title(candidate)
    if q == c:
        return 1.0
    if c.startswith(q):
        return 0.9
    # token_sort_ratio handles word-order differences ("knight dark" vs "dark knight")
    # WRatio handles typos, partial matches, and length differences well
    ratio = fuzz.WRatio(q, c) / 100.0
    token_ratio = fuzz.token_sort_ratio(q, c) / 100.0
    return max(ratio, token_ratio) * 0.85  # cap below exact/prefix
```

**Agent tasks:**
- [ ] Apply `fuzzy_title_score()` to title matching in **both** watchlist search and library search — not just TMDB.
- [ ] Set a minimum fuzzy threshold (start at `0.55`) below which results are dropped, to avoid noise.
- [ ] For cast/director names, use `fuzz.partial_ratio` instead (names are matched as substrings more often — "pacino" should match "Al Pacino").
- [ ] Add a unit test file `tests/test_scoring.py` with real-world typo cases: transpositions, missing letters, phonetic misspellings of actor names.

---

## Phase 2 — Unified relevance ranking (kill the gate)

The `strong_match >= 3` gate on `/api/search/global` is the single biggest structural issue: it's a **binary cutoff** deciding whether discovery even runs, rather than **all results being scored and interleaved** by relevance. This is why the experience feels like "two separate searches stapled together" instead of one smart one.

**New response shape** — replace `strong_match` boolean gating with a single ranked, tagged list:

```python
@dataclass
class UnifiedResult:
    score: float
    source: str          # "owned" | "watchlist" | "tmdb"
    kind: str             # "movie" | "show" | "episode" | "person" | "genre" | "collection"
    payload: dict          # existing GlobalOwnedRow / GlobalDiscoveryRow / SearchResult shape
```

**Ranking logic — replace the gate with a score-based ownership bonus:**

```python
OWNED_BONUS = 0.3  # owned items always outrank equivalent-relevance discovery, but don't hide discovery entirely

def rank_all(owned, discovery, watchlist):
    results = []
    for item in owned:
        results.append(UnifiedResult(score=item.relevance + OWNED_BONUS, source="owned", ...))
    for item in watchlist:
        results.append(UnifiedResult(score=item.relevance + (OWNED_BONUS * 0.5), source="watchlist", ...))
    for item in discovery:
        # still dedup against owned via tmdb_id / exact title+year — keep this from current impl
        if not is_duplicate_discovery(item, owned):
            results.append(UnifiedResult(score=item.relevance, source="tmdb", ...))
    return sorted(results, key=lambda r: r.score, reverse=True)
```

**Why this matters concretely:** today, if you own *The Matrix* and search `"matrix"`, TMDB discovery for *The Matrix Resurrections* or *Animatrix* is fully suppressed because the library has an exact match. Under the new model, your owned copy ranks #1 (bonus applied) but related/sequel titles you *don't* own still surface below it — which is exactly the "IMDb knows what I mean" feeling you're after.

**Agent tasks:**
- [ ] Keep TMDB call **conditional on a lower bar** (e.g., always fire it, but only *block on* it — meaning wait for it before responding — when local score is weak; otherwise fire-and-attach-if-ready with a short timeout, so a strong local match doesn't get slowed down by a TMDB round-trip).
- [ ] Fold `people`, `genres`, `collections` hints into the same ranked list with their own smaller weight tier, rather than separate top-level arrays the frontend has to manually interleave.
- [ ] Preserve `next_episode_facts()` / `owned_state()` enrichment — it should decorate `UnifiedResult.payload`, not change ranking.

---

## Phase 3 — Query understanding (parse intent, don't just match strings)

IMDb-style search understands `"tom hanks movies 1994"` as: person=Tom Hanks, type=movie, year=1994 — not a literal string to substring-match. Right now every query goes straight into `title_match_score()` / `search_multi()` as one blob.

**Create `services/search/query_parser.py`:**

```python
import re
from dataclasses import dataclass, field

@dataclass
class ParsedQuery:
    raw: str
    title_terms: str          # remaining free text after extraction
    year: int | None = None
    year_range: tuple[int, int] | None = None  # "90s" -> (1990, 1999)
    media_type: str | None = None              # "movie" | "tv" from words like "show", "series", "film"
    person_hint: str | None = None             # matched against known cast/director names in library

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DECADE_RE = re.compile(r"\b(19|20)(\d)0s\b")
TYPE_HINTS = {"movie": "movie", "film": "movie", "show": "tv", "series": "tv", "episode": "tv"}

def parse_query(q: str, known_people: list[str] | None = None) -> ParsedQuery:
    remaining = q.lower()
    year = None
    year_range = None

    if m := DECADE_RE.search(remaining):
        decade_start = int(f"{m.group(1)}{m.group(2)}0")
        year_range = (decade_start, decade_start + 9)
        remaining = remaining.replace(m.group(0), "")
    elif m := YEAR_RE.search(remaining):
        year = int(m.group(0))
        remaining = remaining.replace(m.group(0), "")

    media_type = None
    for word, mtype in TYPE_HINTS.items():
        if word in remaining:
            media_type = mtype
            remaining = remaining.replace(word, "")
            break

    person_hint = None
    if known_people:
        match = process_best_match(remaining, known_people)  # rapidfuzz.process.extractOne
        if match and match[1] > 80:
            person_hint = match[0]

    return ParsedQuery(raw=q, title_terms=remaining.strip(), year=year, year_range=year_range,
                        media_type=media_type, person_hint=person_hint)
```

**Agent tasks:**
- [ ] Wire `parse_query()` into both endpoints as the first step, before any scoring.
- [ ] Use `year` / `year_range` as a **filter + score boost**, not a hard filter (a slightly-off year shouldn't zero out an otherwise-perfect title match).
- [ ] Use `person_hint` to boost the existing `person_titles` / actor-director drill-down path — this connects query parsing directly to functionality you already built.
- [ ] Pass `media_type` through to TMDB's `search_multi()` as a filter param if the API supports it, cutting irrelevant noise (e.g., a musical artist matching a movie query).

---

## Phase 4 — Instant search / autocomplete

Currently search appears to be request-per-keystroke against full scoring logic (per "real-time search suggestions as user types" in the frontend section). For this to feel fast *and* smart at every keystroke, you need a cheap prefix path and a debounce, or you'll hammer TMDB and your own scorer on every character.

**Agent tasks:**
- [ ] Frontend (`features/search/`): debounce input by ~150–200ms; cancel in-flight requests on new keystrokes (`AbortController`).
- [ ] Backend: for queries under ~3 characters, skip TMDB entirely and serve prefix-only matches from owned library + watchlist (cheap, in-memory, no network round trip) — TMDB relevance on 1–2 character queries is poor anyway.
- [ ] Build a lightweight in-memory prefix index for the owned library (title first-letters → list of item IDs) that refreshes on library sync, so autocomplete for owned content is near-instant and doesn't re-run full fuzzy scoring per keystroke.
- [ ] Highlight matched substrings in the frontend response (return match spans from the scorer, e.g. `matched_ranges: [(0, 4)]`, so the UI can bold "Dark" in "The Dark Knight").

---

## Phase 5 — Personalization (optional, high polish)

Once ranking is unified (Phase 2) and query parsing exists (Phase 3), personalization is a small additive step: bias ranking using data you already have in Jellyfin playback history.

**Agent tasks:**
- [ ] Build a lightweight genre/actor affinity profile from watched items (`play_count`, `played` fields already exist in `GlobalOwnedRow`) — e.g., a decayed count per genre.
- [ ] Add a small score multiplier (start at max +10–15% of base score) when a discovery result's genre overlaps with the user's top affinities. Keep this subtle — over-personalizing search (vs. recommendations) reads as "wrong," not "smart."
- [ ] Make this toggleable per-user in settings; some users want neutral search regardless of history.

---

## Phase 6 — Semantic search (stretch goal)

For queries like `"movies like Inception"` or `"something with a twist ending"` — true natural-language intent — literal/fuzzy matching can't help. This requires embeddings.

**Agent tasks:**
- [ ] Add `pgvector` if you're on Postgres, or a local `sqlite-vec` / `faiss` index if not — avoid standing up a separate vector DB service for a personal media server.
- [ ] Generate embeddings for owned titles from `overview` + `genres` + `cast` text (a small local sentence-transformer model, e.g. `all-MiniLM-L6-v2`, runs fine on CPU for a library-sized corpus — no need for an API call per search).
- [ ] Only trigger semantic search as a **fallback** when Phase 1–3 scoring returns weak results (e.g., top score < 0.4) or the query is long/conversational (>6 words, contains "like", "similar to", "with a"). This keeps normal searches fast and only pays the embedding-inference cost when literal matching has clearly failed.
- [ ] This is genuinely the last phase — it adds real infra complexity for a feature that matters for maybe 5% of queries. Don't start here.

---

## Phase 7 — Metrics & feedback loop

You can't tune relevance weights (Phase 0's `FieldWeight`) without knowing what "good" looks like for your own usage.

**Agent tasks:**
- [ ] Log `(query, results_shown, item_clicked, position_clicked)` server-side (no PII beyond your own single-user/household context — this is your own server).
- [ ] Build a small offline script that reports: average click position, % of searches with zero clicks (likely bad relevance), and most common zero-result queries.
- [ ] Use zero-result / low-click queries to manually retune `FieldWeight` and fuzzy thresholds every so often — this is the actual mechanism by which the system gets smarter over time, rather than a one-time tuning pass.

---

## Suggested implementation order for the agent

| Phase | Effort | Impact | Depends on |
|---|---|---|---|
| 0 — Scoring module | Low | Enables everything else | — |
| 1 — Fuzzy matching | Low | **Highest** | 0 |
| 2 — Unified ranking | Medium | **Highest** | 0 |
| 3 — Query parsing | Medium | High | 0, 1 |
| 4 — Instant search | Medium | High (perceived speed) | 2 |
| 5 — Personalization | Low | Medium | 2 |
| 6 — Semantic search | High | Medium (niche queries) | 1, 2, 3 |
| 7 — Metrics loop | Low | Compounds over time | 2 |

Ship 0 → 1 → 2 first. That combination alone — fuzzy matching plus one merged, continuously-scored ranking list instead of a 3-point gate — is what will make the biggest jump toward "feels like IMDb," since it directly fixes the two things that currently make search feel mechanical: typo-brittleness and the hard cutoff between owned and discovered content.
