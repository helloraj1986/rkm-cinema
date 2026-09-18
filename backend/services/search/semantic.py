"""Semantic search — the embedding fallback (SEARCH_IMPROVEMENT_PLAN Phase 6).

Plan and measurements: `docs/SEMANTIC_SEARCH_PLAN.md`. This module is the feature's CORE and it is
free of the route: it decides (a) WHEN an embedding search is worth paying for, (b) what text each
library row is indexed AS, and (c) how a per-profile index is built, cached and searched.

⚠⚠ THREE RULES, AND NONE OF THEM IS A PREFERENCE:

1. **Per PROFILE, never global.** Profiles see different libraries (ARCHITECTURE §11), so an index
   that is not keyed by the profile that asked silently answers one household member with another
   member's titles — the exact bug a previous session refused to introduce. The key is
   ``(profile_id, fingerprint of that profile's own rows)``; the fingerprint is there so a library
   scan or an added title cannot be answered from a stale vector set.

2. **Optional at RUNTIME.** ``model2vec`` (and the model's files) may be absent — on a box installed
   before this phase, or in a container that never fetched the model. :func:`available` reports that
   and every caller degrades to lexical-only search, the same contract
   :mod:`services.search.fuzzy` keeps for ``rapidfuzz``. **Nothing here may raise into a request.**

3. **No invented relevance.** A cosine similarity is a similarity; what it is WORTH is the tier in
   :mod:`services.search.ranking` (deliberately below every lexical tier). The floor here rejects
   near-orthogonal noise and nothing more — calibrating it is Phase 7's job, not a guess made in a
   ranker. The measured probe is in the plan: this model leads with the right film for
   *"movies like Inception"* and *"something with a twist ending"*, and gets ONE of three for
   *"feel-good comedy for the family"*. Mood is where it is weak, and the code says so rather than
   pretending otherwise.

The model: ``model2vec`` + ``minishlab/potion-base-8M`` — 256 dims, static embeddings, and no torch
and no onnxruntime on a CPU-only box. Measured here (2 000 rows): 0.55 s to embed the whole library,
17 ms per query, 130 MB resident, 59 MB on disk.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence

from services.search.ranking import SEMANTIC_MIN_COS, SEMANTIC_TRIGGER_SCORE
from services.search.scoring import TOKEN_SCORE

logger = logging.getLogger("rkm.search.semantic")

__all__ = [
    "CONVERSATIONAL_MIN_WORDS",
    "CONVERSATIONAL_PHRASES",
    "MIN_SEMANTIC_QUERY_LEN",
    "MODEL_NAME",
    "SEMANTIC_LIMIT",
    "SemanticIndex",
    "available",
    "clear_cache",
    "fingerprint",
    "get_index",
    "index_text",
    "is_conversational",
    "row_id",
    "semantic_hits",
    "should_use_semantic",
    "unavailable_reason",
]

#: The model. ⚠ Changing this changes EVERY vector, so it is named once, here, and the plan records
#: why this one (measured against two larger variants that were not better and cost 2.7x the RAM).
MODEL_NAME = "minishlab/potion-base-8M"

#: How many neighbours the fallback may contribute to one search. Small on purpose: the fallback is a
#: guess about INTENT, and a guess deserves a short list — not a second page of results.
SEMANTIC_LIMIT = 5

#: ⚠ The shortest query allowed to reach the index, the same floor the TMDB half uses and for the
#: same measured reason: two characters are a prefix, not a description of a mood, and a 2-character
#: query that matches nothing has top score 0 — which would otherwise satisfy the weak-score rule and
#: embed "th".
MIN_SEMANTIC_QUERY_LEN = 3

#: A query this long, or containing one of these phrases, is asking for something rather than naming
#: it. His rule from the plan text ("…or the query is conversational (>6 words, contains 'like',
#: 'similar to', 'with a')").
CONVERSATIONAL_MIN_WORDS = 6
CONVERSATIONAL_PHRASES = ("like", "similar to", "with a")

#: ⚠ The score at which the string matcher's EVIDENCE overrules the conversational heuristic: the
#: weakest genuine TITLE tier (``scoring.TOKEN_SCORE``). Above it the query demonstrably names
#: something in his library, so a nine-word film title is not treated as a request for a mood.
TITLE_MATCH_FLOOR = TOKEN_SCORE

#: How many indexes stay warm, keyed by (profile, fingerprint). ⚠ Two is deliberate: one profile's
#: library is ~2 MB of vectors, and the second slot is what stops a household switch from paying the
#: build twice. Not a leak — a stated bound.
MAX_CACHED_INDEXES = 2

EncodeFn = Callable[[Sequence[str]], Any]
"""``texts -> (n, dims) array``. Injected in tests; the real one is :func:`_model_encode`."""


# --------------------------------------------------------------------------- the trigger (pure)

def is_conversational(query: str) -> bool:
    """Is this query DESCRIBING something rather than naming it?

    ⚠ Length alone is not enough and neither is a phrase alone. "the girl with a pearl earring" is
    five words and names a film; "something with a twist" is four and describes one. The phrase list
    is what catches the second, and the word count catches the long rambling case the phrases miss.
    """
    q = str(query or "").strip().lower()
    if not q:
        return False
    if len(q.split()) >= CONVERSATIONAL_MIN_WORDS:
        return True
    return any(phrase in q for phrase in CONVERSATIONAL_PHRASES)


def should_use_semantic(query: str, top_score: float) -> bool:
    """Whether the embedding fallback is worth running for this query — his rule, in one place.

    ⚠ Pure, and it takes ``top_score`` rather than measuring it: the caller knows the LEXICAL ranked
    list, and evaluating the rule against that list (before any semantic row exists) is what makes
    "a semantic hit can never outrank a lexical match" a fact about every response instead of a hope.

    Three answers, in order:
      · nothing the string matcher found reached ``SEMANTIC_TRIGGER_SCORE`` (0.4) — a weak result; OR
      · the query reads as a DESCRIPTION rather than a name — but only while the string matcher has
        not matched a title tier. ⚠ **Evidence overrules the heuristic**: *"The Lord of the Rings:
        The Fellowship of the Ring"* is nine words and is a FILM, and a 0.6+ match proves the query
        names something, so a long exact title does not drag five neighbours into a search that
        already succeeded;
      · ⚠ and the query is at least ``MIN_SEMANTIC_QUERY_LEN`` characters, always. "th" matches
        nothing, which looks exactly like "the string matcher failed" to a score test.
    """
    q = str(query or "").strip()
    if len(q) < MIN_SEMANTIC_QUERY_LEN:
        return False
    score = float(top_score)
    if score < SEMANTIC_TRIGGER_SCORE:
        return True
    if score >= TITLE_MATCH_FLOOR:
        return False
    return is_conversational(q)


# --------------------------------------------------------------------------- the index's inputs

def row_id(row: dict) -> str:
    """A library row's own item id (the provider's, not a TMDB id)."""
    return str(row.get("item_id") or row.get("id") or "")


def index_text(row: dict) -> str:
    """What one library row is indexed AS: title · year · genres · overview.

    ⚠ Ordered by how much each part tells the model, and every part is OPTIONAL — a row with no
    genres and no synopsis is still indexed by its title rather than skipped, because a title alone is
    what most semantic queries ("movies like Inception") actually key off.
    """
    parts = [str(row.get("title") or row.get("name") or "").strip()]
    year = row.get("year")
    if year:
        parts.append(str(year))
    genres = row.get("genres") or []
    if isinstance(genres, (list, tuple)) and genres:
        parts.append(", ".join(str(g) for g in genres if g))
    overview = str(row.get("overview") or "").strip()
    if overview:
        parts.append(overview)
    return ". ".join(p for p in parts if p).strip()


def fingerprint(rows: Iterable[dict]) -> str:
    """A stable signature of WHICH rows an index was built from.

    ⚠ Ids only, sorted — not the texts. The question this answers is "is this still the same
    library?", and ids settle that without hashing megabytes of synopses on every search.
    """
    ids = sorted(i for i in (row_id(row) for row in rows or ()) if i)
    digest = hashlib.sha1()
    digest.update(f"{len(ids)}:".encode("utf-8"))
    for item_id in ids:
        digest.update(item_id.encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()[:16]


# --------------------------------------------------------------------------- the model

_model: Any = None
_model_error: str = ""
_model_lock = threading.Lock()


def _load_model(name: str = MODEL_NAME) -> Any:
    """Load the model ONCE per process. Raises on failure — :func:`available` is what swallows it.

    ⚠ The import is INSIDE the function on purpose: a deployment without the dependency must be able
    to import this module (and therefore the search route) without it.
    """
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from model2vec import StaticModel  # ⚠ the ONLY import of the dependency in the codebase

            _model = StaticModel.from_pretrained(name)
    return _model


def unavailable_reason() -> str:
    """Why semantic search is off (``""`` when it is on). For logs, never for a control flow test."""
    return _model_error


def available() -> bool:
    """Is the embedding fallback usable in this process?

    ⚠ It LOADS the model, so call it LAST: after the preference and the trigger have both said yes.
    The result is cached either way, including the failure, so a box without the wheel pays for the
    import error once and every later search is a boolean.
    """
    global _model_error
    if _model is not None:
        return True
    if _model_error:
        return False
    try:
        _load_model()
        return True
    except Exception as e:  # noqa: BLE001 — a missing wheel, a bad cache, no disk: all the same here
        _model_error = f"{type(e).__name__}: {e}"
        logger.warning("semantic search unavailable (%s) — searches stay lexical", _model_error)
        return False


def _model_encode(texts: Sequence[str]) -> Any:
    """The real encoder: the model's own ``encode``, returned as a float32 array."""
    import numpy as np

    model = _load_model()
    vectors = np.asarray(model.encode(list(texts)), dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors.reshape(1, -1)
    return vectors


def _unit(vectors: Any) -> Any:
    """L2-normalise rows so a dot product IS the cosine similarity."""
    import numpy as np

    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.clip(norms, 1e-9, None)


# --------------------------------------------------------------------------- the index

@dataclass
class SemanticIndex:
    """One profile's library, as unit vectors plus the item ids they belong to.

    ⚠ ``ids`` and the vector ROWS are the same order — that pairing is the whole data structure, and
    it is why ``search`` returns ids rather than positions.
    """

    ids: tuple[str, ...]
    vectors: Any
    dims: int

    def search(self, query: str, *, limit: int = SEMANTIC_LIMIT,
               min_cos: float = SEMANTIC_MIN_COS, encoder: Optional[EncodeFn] = None) -> list[tuple[str, float]]:
        """The ``limit`` closest neighbours of *query*, best first, above ``min_cos``."""
        import numpy as np

        if not self.ids or not str(query or "").strip():
            return []
        enc = encoder or _model_encode
        query_vector = _unit(enc([str(query)])).reshape(-1)
        if query_vector.shape[0] != self.dims:
            # ⚠ A dims mismatch means the index and the query came from different models — a bug, not
            # a search. Say so and return nothing rather than raising into a request.
            logger.error("semantic dims mismatch: index %s vs query %s", self.dims, query_vector.shape[0])
            return []
        sims = self.vectors @ query_vector
        order = np.argsort(-sims)[: max(1, int(limit))]
        out: list[tuple[str, float]] = []
        for position in order:
            cos = float(sims[position])
            if cos < min_cos:
                continue
            out.append((self.ids[int(position)], cos))
        return out


_CACHE: "OrderedDict[tuple[str, str], SemanticIndex]" = OrderedDict()
_cache_lock = threading.Lock()


def clear_cache() -> None:
    """Drop every cached index (a library change, or a test)."""
    with _cache_lock:
        _CACHE.clear()


def get_index(profile_id: str, rows: Sequence[dict], *,
              encoder: Optional[EncodeFn] = None) -> Optional[SemanticIndex]:
    """The index for THIS profile and THIS library, building and caching it if needed.

    ⚠ The key is ``(profile_id, fingerprint(rows))``. Two profiles can therefore never share vectors
    even when their rows look alike, and a library that changed is a MISS rather than a stale hit.
    ⚠ No profile, no index: a request whose identity was never published gets ``None`` and falls back
    to lexical search, because there is no key that could honestly represent "whoever this is".
    """
    key_profile = str(profile_id or "").strip()
    usable = [row for row in rows or () if row_id(row)]
    if not key_profile or not usable:
        return None
    key = (key_profile, fingerprint(usable))
    with _cache_lock:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return hit
    vectors = _unit((encoder or _model_encode)([index_text(row) for row in usable]))
    index = SemanticIndex(ids=tuple(row_id(row) for row in usable), vectors=vectors,
                          dims=int(vectors.shape[1]))
    with _cache_lock:
        _CACHE[key] = index
        while len(_CACHE) > MAX_CACHED_INDEXES:
            _CACHE.popitem(last=False)
    logger.info("semantic index built for profile %s: %d rows, %d dims", key_profile,
                len(index.ids), index.dims)
    return index


def semantic_hits(profile_id: str, query: str, rows: Sequence[dict], *,
                  limit: int = SEMANTIC_LIMIT, encoder: Optional[EncodeFn] = None
                  ) -> list[tuple[dict, float]]:
    """``[(row, cosine)]`` for this query, ready for ``rank_all(semantic=…)``.

    ⚠ The ONLY raising path is a broken model, and it is caught here: the caller is a search route,
    and a search must answer even when this feature cannot.
    """
    try:
        index = get_index(profile_id, rows, encoder=encoder)
        if index is None:
            return []
        by_id = {row_id(row): row for row in rows or () if row_id(row)}
        return [(by_id[item_id], cos) for item_id, cos in index.search(query, limit=limit, encoder=encoder)
                if item_id in by_id]
    except Exception as e:  # noqa: BLE001
        logger.warning("semantic search failed (%s) — falling back to lexical only", e)
        return []
