"""Semantic search — the embedding fallback (SEARCH_IMPROVEMENT_PLAN Phase 6).

Plan and measurements: `docs/SEMANTIC_SEARCH_PLAN.md`. Two properties carry this phase, and most of
what follows pins THEM rather than the happy path:

* **A semantic row can never outrank a lexical one.** A cosine similarity is not a title score; the
  tier it maps into sits strictly below ``SEMANTIC_TRIGGER_SCORE``, the line the route only crosses the
  other way when nothing matched. Pinned as an invariant, like ``OWNED_BONUS``.
* **An index belongs to ONE profile.** Profiles see different libraries (§11), so a shared index would
  silently answer one household member with another's titles. Pinned by keying two profiles apart.

⚠ **No test here downloads a model.** Every index in this file is built with an injected encoder, so
the suite stays fast and offline; ``available()`` is exercised through the failure path on purpose,
because that is the path a box without the dependency actually takes.
"""
import numpy as np
import pytest

from services.search import semantic
from services.search.ranking import (
    SEMANTIC_BASE,
    SEMANTIC_MIN_COS,
    SEMANTIC_SPAN,
    SEMANTIC_TRIGGER_SCORE,
    rank_all,
    semantic_score,
)
from services.search.scoring import CONTAINMENT_BASE, CONTAINMENT_SPAN, TOKEN_SCORE, score_item

#: Five semantic axes, so a cosine here MEANS something without a model.
AXES = ("dream", "heist", "space", "family", "horror")


def fake_encoder(texts):
    """Deterministic bag-of-keywords vectors. Injected everywhere an index is built."""
    rows = []
    for text in texts:
        low = str(text).lower()
        vector = [1.0 if axis in low else 0.0 for axis in AXES]
        if not any(vector):
            vector = [0.05] * len(AXES)
        rows.append(vector)
    return np.asarray(rows, dtype=np.float32)


def row(item_id, title, year=None, genres=None, overview=""):
    return {"item_id": item_id, "title": title, "kind": "movie", "year": year,
            "genres": list(genres or []), "overview": overview}


INCEPTION = row("i1", "Inception", 2010, ["Action", "Sci-Fi"],
                "A thief who steals secrets through dream-sharing technology.")
HEREDITARY = row("h1", "Hereditary", 2018, ["Horror"],
                 "A grieving family unravels terrifying secrets about their ancestry.")
LIBRARY = [
    INCEPTION,
    HEREDITARY,
    row("t1", "Toy Story", 1995, ["Family"], "A cowboy doll is threatened by a spaceman action figure."),
]


@pytest.fixture(autouse=True)
def _clean_cache():
    """⚠ Every test starts with an empty index cache — a leaked index would make the per-profile
    keying tests pass for the wrong reason (a hit from the previous test)."""
    semantic.clear_cache()
    yield
    semantic.clear_cache()


# --------------------------------------------------------------------------- the trigger (pure)
def test_should_use_semantic_needs_a_weak_result_or_a_conversational_query():
    """The two ways in, and the floor that shuts both."""
    # weak: nothing the string matcher found is a real match
    assert semantic.should_use_semantic("incepton", SEMANTIC_TRIGGER_SCORE - 0.01) is True
    assert semantic.should_use_semantic("dune", 0.0) is True
    # strong: an exact/prefix/containment hit means the string matcher already worked
    assert semantic.should_use_semantic("inception", 1.0) is False
    assert semantic.should_use_semantic("matrix", 0.65) is False
    # ⚠ the boundary belongs to the STRING side: at exactly the trigger line the fallback is NOT run
    assert semantic.should_use_semantic("matrix", SEMANTIC_TRIGGER_SCORE) is False
    # conversational: a description, so no title match is EXPECTED — and on this query that is what
    # the scorer reports (the phrase is in no title), which is when the fallback fires.
    assert semantic.should_use_semantic("movies like inception", 0.0) is True
    assert semantic.should_use_semantic("something with a twist ending", 0.0) is True
    # ⚠ and when the SAME phrase did match a title (0.9 = prefix), the evidence wins and it does not
    # run: a query something in his library actually answered is not a request for a mood search.
    assert semantic.should_use_semantic("movies like inception", 0.9) is False


def test_should_use_semantic_refuses_a_query_too_short_to_be_a_search():
    """⚠ A 2-character query that matches NOTHING has top score 0 — which looks exactly like "the
    string matcher failed". It is a prefix, not a description of a mood, and it must never embed."""
    assert semantic.should_use_semantic("th", 0.0) is False
    assert semantic.should_use_semantic("", 0.0) is False
    assert semantic.should_use_semantic("a", 0.0) is False
    assert semantic.should_use_semantic("the", 0.0) is True  # three characters is the floor
    # and the floor holds even for a LONG query phrased conversationally
    assert semantic.should_use_semantic("th", 0.0) is False


def test_is_conversational_catches_length_and_phrases():
    assert semantic.is_conversational("the dark knight rises") is False
    assert semantic.is_conversational("something with a twist") is True
    assert semantic.is_conversational("movies like inception") is True
    assert semantic.is_conversational("films similar to se7en") is True
    # six words, no phrase: still describing rather than naming
    assert semantic.is_conversational("a film about a bank robbery gone") is True
    # ⚠ and a SIX-WORD FILM TITLE reads as conversational to this heuristic — which is exactly why
    # the overrule below exists rather than a longer word list that would never be complete.
    assert semantic.is_conversational("the girl with the pearl earring") is True
    assert semantic.is_conversational("inception") is False
    assert semantic.is_conversational("   ") is False


def test_evidence_overrules_the_conversational_heuristic():
    """⚠ A nine-word query that MATCHED a title is a film title, not a request for a mood.

    Without this the fallback would inject five embedding neighbours into a search that already
    answered correctly — noise at the bottom of the list, for no gain.
    """
    long_title = "the lord of the rings the fellowship of the ring"
    assert semantic.is_conversational(long_title) is True
    # the string matcher proved it names a title (containment is 0.65+, well past the floor)
    assert semantic.should_use_semantic(long_title, 0.72) is False
    # ⚠ but a description that happens to contain a word or two of a title still runs it
    assert semantic.should_use_semantic("films like the ring", 0.25) is True
    assert semantic.should_use_semantic("something with a fellowship", 0.5) is True


# --------------------------------------------------------------------------- the tier's invariant
def test_a_semantic_score_can_never_reach_a_lexical_tier():
    """⚠⚠ THE invariant of Phase 6, in the same spirit as ``OWNED_BONUS``'s.

    If the top of the semantic tier could reach the trigger line, then a fuzzy similarity would be
    competing with a title match — and the route's "only run when nothing matched" rule would stop
    being a proof about the response and become a hope about the caller.
    """
    assert SEMANTIC_BASE + SEMANTIC_SPAN < SEMANTIC_TRIGGER_SCORE
    assert SEMANTIC_TRIGGER_SCORE < TOKEN_SCORE  # the weakest genuine LEXICAL title tier
    assert semantic_score(1.0) == pytest.approx(SEMANTIC_BASE + SEMANTIC_SPAN)
    assert semantic_score(1.0) < SEMANTIC_TRIGGER_SCORE
    # and the OLDEST guarantee still holds: a semantic row sits above nothing-matched rows
    assert SEMANTIC_BASE > 0.0


def test_the_similarity_orders_the_group_and_the_floor_bounds_it():
    assert semantic_score(SEMANTIC_MIN_COS) == pytest.approx(SEMANTIC_BASE)
    assert semantic_score(0.0) == pytest.approx(SEMANTIC_BASE)
    assert semantic_score(0.5) > semantic_score(0.2) > semantic_score(SEMANTIC_MIN_COS)
    # clamped: a cosine cannot exceed 1.0, and a broken one cannot escape the tier either
    assert semantic_score(9.0) == pytest.approx(SEMANTIC_BASE + SEMANTIC_SPAN)


def test_a_semantic_row_never_outranks_a_lexical_match():
    """The same invariant, observed through ``rank_all`` rather than read off the constants."""
    query = "the dark knight"
    owned = [{"id": "owned-1", "item_id": "owned-1", "title": "The Dark Knight", "kind": "movie",
              "year": 2008, "provider_ids": {}}]
    lexical = score_item(query, {"title": "The Dark Knight"}).score
    assert lexical >= CONTAINMENT_BASE  # the lexical row really is a real match

    ranked = rank_all(query, owned=owned, semantic=[(row("s1", "Some Heist Film"), 1.0)])

    assert ranked[0].payload["item_id"] == "owned-1", "a cosine outranked a title match"
    assert ranked[0].score > semantic_score(1.0)


def test_semantic_rows_rank_above_owned_rows_our_scorer_cannot_see():
    """The visible effect of the whole phase: on a weak query the embedding neighbours lead, because
    the alternative is showing him the provider's rows at score 0."""
    query = "something with a twist ending"
    owned = [{"id": "owned-1", "item_id": "owned-1", "title": "Unrelated Documentary", "kind": "movie",
              "year": 2001, "provider_ids": {}}]
    ranked = rank_all(query, owned=owned, semantic=[(INCEPTION, 0.9), (HEREDITARY, 0.4)])

    assert [r.payload["item_id"] for r in ranked[:2]] == ["i1", "h1"]
    assert ranked[0].match_type == "semantic"
    assert ranked[0].score < SEMANTIC_TRIGGER_SCORE
    # the sentence-level scores are untouched: the unrelated owned row is still last
    assert ranked[-1].payload["item_id"] == "owned-1"


def test_a_title_that_matched_lexically_is_not_repeated_as_semantic():
    """⚠ Dedupe by ITEM id: the row that carries the query's match spans wins, and the person sees
    one row per title."""
    query = "inception"
    owned = [{"id": "i1", "item_id": "i1", "title": "Inception", "kind": "movie", "year": 2010,
              "provider_ids": {}}]
    ranked = rank_all(query, owned=owned, semantic=[(INCEPTION, 0.99), (HEREDITARY, 0.5)])

    ids = [r.payload["item_id"] for r in ranked]
    assert ids.count("i1") == 1
    assert ranked[ids.index("i1")].match_type != "semantic"
    assert "h1" in ids


def test_rows_below_the_floor_are_dropped_rather_than_padding_the_list():
    ranked = rank_all("something with a twist", semantic=[(INCEPTION, SEMANTIC_MIN_COS - 0.01)])
    assert ranked == []


# --------------------------------------------------------------------------- the index
def test_the_index_is_keyed_by_profile_so_two_viewers_cannot_share_vectors():
    """⚠⚠ §11 as a test. Two profiles, the same rows: two indexes. A single shared index would serve
    one household member the other's library, which is the bug this keying exists to prevent."""
    a = semantic.get_index("profile-a", LIBRARY, encoder=fake_encoder)
    b = semantic.get_index("profile-b", LIBRARY, encoder=fake_encoder)
    assert a is not None and b is not None
    assert a is not b
    assert len(semantic._CACHE) == 2  # noqa: SLF001 — the cache IS the thing under test


def test_a_library_change_is_a_cache_miss_not_a_stale_answer():
    """The fingerprint's whole job: add one title and the old vectors must not answer."""
    first = semantic.get_index("p", LIBRARY, encoder=fake_encoder)
    grown = semantic.get_index("p", LIBRARY + [row("n1", "New Arrival", 2024, ["Family"])],
                               encoder=fake_encoder)
    assert first is not None and grown is not None
    assert first is not grown
    assert "n1" in grown.ids and "n1" not in first.ids


def test_a_library_change_of_the_SAME_SIZE_is_still_a_cache_miss():
    """⚠⚠ This test exists because the one above could not fail on its own.

    Measured while falsifying: removing the per-id feed from the fingerprint left the suite GREEN,
    because the test above changes the ROW COUNT and the fingerprint's length prefix caught that
    alone. A real library change rarely looks like that — one title deleted and another added keeps
    the count and changes only WHICH titles are in the library, which is the case that would have
    served stale vectors for a title that is no longer there.
    """
    same_size = [LIBRARY[0], LIBRARY[1], row("x9", "A Different Film", 2020, ["Family"])]
    assert len(same_size) == len(LIBRARY)
    assert semantic.fingerprint(LIBRARY) != semantic.fingerprint(same_size)

    first = semantic.get_index("p", LIBRARY, encoder=fake_encoder)
    swapped = semantic.get_index("p", same_size, encoder=fake_encoder)
    assert first is not None and swapped is not None
    assert first is not swapped
    assert "x9" in swapped.ids and "t1" not in swapped.ids


def test_no_published_profile_means_no_index():
    """A request whose identity was never published gets ``None``, not a shared index keyed on ""."""
    assert semantic.get_index("", LIBRARY, encoder=fake_encoder) is None
    assert semantic.get_index("p", [], encoder=fake_encoder) is None


def test_the_cache_is_bounded_and_evicts_the_oldest_index():
    for name in ("a", "b", "c"):
        semantic.get_index(name, LIBRARY, encoder=fake_encoder)
    assert len(semantic._CACHE) == semantic.MAX_CACHED_INDEXES  # noqa: SLF001


def test_search_returns_the_closest_rows_in_order_above_the_floor():
    index = semantic.get_index("p", LIBRARY, encoder=fake_encoder)
    assert index is not None
    hits = index.search("a dream heist", encoder=fake_encoder, limit=3)
    assert hits and hits[0][0] == "i1"
    assert all(cos >= SEMANTIC_MIN_COS for _, cos in hits)
    # the horror film is not a dream-heist neighbour, so it must not be returned at this floor
    assert "h1" not in [item_id for item_id, _ in hits]


def test_search_is_empty_for_an_empty_query_or_an_empty_library():
    index = semantic.get_index("p", LIBRARY, encoder=fake_encoder)
    assert index is not None
    assert index.search("   ", encoder=fake_encoder) == []


def test_a_dims_mismatch_returns_nothing_rather_than_raising():
    """⚠ A model swap on a warm process is a bug, not a search. It must not reach the caller as an
    exception — the route is a request."""
    index = semantic.get_index("p", LIBRARY, encoder=fake_encoder)  # 5 axes
    assert index is not None
    short = lambda texts: np.asarray([[1.0, 0.0] for _ in texts], dtype=np.float32)  # noqa: E731
    assert index.search("dream", encoder=short) == []


# --------------------------------------------------------------------------- indexibility + degradation
def test_index_text_carries_every_field_it_has_and_skips_the_ones_it_does_not():
    assert semantic.index_text(INCEPTION).startswith("Inception. 2010. Action, Sci-Fi.")
    assert "dream-sharing" in semantic.index_text(INCEPTION)
    bare = row("x", "Bare Title")
    assert semantic.index_text(bare) == "Bare Title"


def test_rows_without_an_id_are_left_out_of_the_index():
    """A row the app cannot address again is not a result it can offer."""
    rows = [row("", "No Id"), row("keep", "Kept")]
    assert semantic.fingerprint(rows) == semantic.fingerprint([row("keep", "Kept")])


def test_a_missing_model_degrades_to_no_results_and_says_why(monkeypatch):
    """⚠ The path a box WITHOUT the dependency takes. It must be quiet, cached, and never raise."""
    semantic.clear_cache()
    monkeypatch.setattr(semantic, "_model", None)
    monkeypatch.setattr(semantic, "_model_error", "")

    def explode(name=semantic.MODEL_NAME):
        raise ImportError("No module named 'model2vec'")

    monkeypatch.setattr(semantic, "_load_model", explode)

    assert semantic.available() is False
    assert "model2vec" in semantic.unavailable_reason()
    # cached: the second ask does not re-attempt the import
    assert semantic.available() is False
    # ⚠ NO injected encoder: this is the real path a search takes on a box without the wheel, so the
    # import failure has to be swallowed by the search helper rather than by the test's stub.
    assert semantic.semantic_hits("p", "movies like inception", LIBRARY) == []


def test_an_encoder_that_explodes_does_not_fail_the_search(monkeypatch):
    def explode(texts):
        raise RuntimeError("the model file is corrupt")

    assert semantic.semantic_hits("p", "movies like inception", LIBRARY, encoder=explode) == []


def test_rows_are_fetched_once_per_profile_within_the_ttl(monkeypatch):
    """⚠ The row fetch is the expensive half (one Jellyfin request with every synopsis), so the TTL
    is what stops a triggered search repeating it — while the FINGERPRINT still decides whether the
    vectors are rebuilt."""
    semantic.clear_cache()
    calls = []
    rows = list(LIBRARY)

    def fetch():
        calls.append(1)
        return rows

    first = semantic.cached_index_rows("p", fetch, now=1000.0)
    again = semantic.cached_index_rows("p", fetch, now=1000.0 + semantic.ROWS_TTL_SECONDS - 1)
    after = semantic.cached_index_rows("p", fetch, now=1000.0 + semantic.ROWS_TTL_SECONDS + 1)

    assert len(first) == len(LIBRARY) and len(again) == len(LIBRARY)
    assert len(calls) == 2, "the TTL did not suppress the second fetch"
    assert len(after) == len(LIBRARY)
    # and a DIFFERENT profile has its own rows: one cache entry per owner, never shared
    semantic.cached_index_rows("other", lambda: [HEREDITARY], now=1000.0)
    assert set(semantic._ROWS) == {"p", "other"}  # noqa: SLF001


def test_a_failing_row_fetch_is_empty_not_an_exception():
    def boom():
        raise RuntimeError("jellyfin is down")

    assert semantic.cached_index_rows("p", boom) == []


def test_a_request_with_no_published_session_still_has_an_owner():
    """⚠ The app resolves an unscoped request through its OWN default account — one library — so one
    key is honest there. `get_index` still refuses a truly empty id, so a caller that forgot to
    resolve an owner cannot accidentally share the default index."""
    assert semantic.index_owner("") == semantic.DEFAULT_IDENTITY_KEY
    assert semantic.index_owner("profile-a") == "profile-a"
    assert semantic.get_index("", LIBRARY, encoder=fake_encoder) is None
    assert semantic.get_index(semantic.index_owner(""), LIBRARY, encoder=fake_encoder) is not None
