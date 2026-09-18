"""Tests for the shared search scorer and typo tolerance.

SEARCH_IMPROVEMENT_PLAN Phase 0 (``services/search/scoring.py``) and Phase 1
(``services/search/fuzzy.py``).

⚠ The typo cases below are REAL-WORLD misspellings, not synthetic edits: a
transposition someone actually types, a dropped letter, a phonetic spelling of a
long surname, and a word-order reversal. Those are the queries this phase exists
to answer — a test that only checks ``"x" != "y"`` would pass against the broken
substring implementation too.
"""
import pytest

from services.search.fuzzy import (
    FUZZY_CEILING,
    FUZZY_FLOOR,
    MIN_FUZZY_LEN,
    available,
    fuzzy_name_score,
    fuzzy_title_score,
)
from services.search.normalize import normalize_title, year_factor
from services.search.scoring import (
    CONTAINMENT_BASE,
    CONTAINMENT_SPAN,
    EXACT_TITLE_SCORE,
    FieldWeight,
    best_relevance,
    name_relevance,
    owned_strong_match,
    row_fields,
    score_item,
    title_match_score,
    title_relevance,
)

# --------------------------------------------------------------------------- Phase 0 · primitives
def test_normalize_title_key():
    assert normalize_title("3 Body Problem:") == "3 body problem"
    assert normalize_title("  The   Matrix- Reloaded  ") == "the matrix reloaded"
    assert normalize_title("") == ""
    assert normalize_title(None) == ""


def test_year_factor_is_neutral_when_either_side_is_unknown():
    """⚠ The 2026-09-13 bug in one assertion: an owned row with NO year must not be
    punished for missing metadata — that is what hid the real *Sholay*."""
    assert year_factor(2021, 2021) == 1.0
    assert year_factor(None, 1984) == 1.0
    assert year_factor(2021, None) == 1.0
    assert year_factor(None, None) == 1.0
    assert year_factor(2021, "nonsense") == 1.0
    assert 0.0 < year_factor(2021, 1984) < 1.0


# --------------------------------------------------------------------------- Phase 0 · the legacy tiers did not move
def test_title_match_score_tiers_and_years():
    assert title_match_score("3 body problem", "3 Body Problem") == 3
    assert title_match_score("3 Body", "3 Body Problem") == 2
    assert title_match_score("dark", "Dark", query_year=2017, title_year=2017) == 3
    # same name, different year (remake) is NOT a strong match
    assert title_match_score("Cape Fear", "Cape Fear", query_year=1962, title_year=1991) == 0
    assert title_match_score("zzz", "No Match At All") == 0
    assert title_match_score("", "Anything") == 0


def test_owned_strong_match_keeps_returning_the_discrete_tier():
    """⚠ ``EXACT_TITLE_SCORE`` is a published contract; the refactor into
    ``services/search/`` must not have renumbered it."""
    owned = [{"title": "3 Body Problem", "year": 2024}, {"title": "Dark", "year": 2017}]
    assert owned_strong_match(owned, "3 body problem") == EXACT_TITLE_SCORE
    assert owned_strong_match(owned, "3 Body") == 2
    assert owned_strong_match(owned, "Something Else") == 0
    assert owned_strong_match(owned, "3 Body") < EXACT_TITLE_SCORE


# --------------------------------------------------------------------------- Phase 0 · continuous tiers and their ORDER
def test_title_relevance_tier_order():
    """The whole point of a continuous score: the tiers must be ordered, or ranking
    is the same coin-flip the 0–3 gate was."""
    exact = title_relevance("the dark knight", "The Dark Knight")[0]
    prefix = title_relevance("the dark", "The Dark Knight")[0]
    containment = title_relevance("dark knight", "The Dark Knight")[0]
    assert exact == 1.0
    assert exact > prefix > containment


def test_title_relevance_scores_a_typo_above_a_fragment():
    """Phase 1's headline behaviour: a mistyped FULL title is better evidence than a
    correct fragment of one."""
    typo = title_relevance("the dark knght", "The Dark Knight")
    fragment = title_relevance("dark", "The Dark Knight")
    assert typo[1] == "fuzzy" and typo[0] > fragment[0]
    assert typo[0] <= FUZZY_CEILING


def test_containment_is_weighted_by_how_much_of_the_title_it_covers():
    """⚠ Regression guard for the tie this phase found and fixed: a flat containment
    constant scored a film and its own sequel IDENTICALLY, so *The Matrix* and
    *The Matrix Reloaded* were inseparable for the query "matrix"."""
    film = title_relevance("matrix", "The Matrix")
    sequel = title_relevance("matrix", "The Matrix Reloaded")
    assert film[0] > sequel[0], (film, sequel)
    assert all(CONTAINMENT_BASE <= s[0] <= CONTAINMENT_BASE + CONTAINMENT_SPAN
               for s in (film, sequel))
    # …and the fuller query still wins its own title.
    assert title_relevance("matrix reloaded", "The Matrix Reloaded")[0] > film[0]


def test_year_mismatch_discounts_but_never_zeroes():
    """The plan's Phase 3 rule, pinned early: an off year must lose an argument, not
    the whole match."""
    same = title_relevance("dune", "Dune", query_year=2021, title_year=2021)[0]
    other = title_relevance("dune", "Dune", query_year=2021, title_year=1984)[0]
    assert same == 1.0
    assert 0.0 < other < same
    # …whereas the legacy discrete tier still hard-fails it.
    assert title_match_score("dune", "Dune", query_year=2021, title_year=1984) == 0


def test_no_match_scores_zero():
    assert title_relevance("zzzzzzzz", "The Dark Knight")[0] == 0.0
    assert title_relevance("", "The Dark Knight")[0] == 0.0


# --------------------------------------------------------------------------- Phase 0 · field weighting
def test_score_item_prefers_a_title_hit_over_a_synopsis_hit():
    """The reason weights exist: under the old watchlist substring test a hit in
    ``snippet`` counted exactly as much as a hit in ``title``."""
    title_hit = score_item("joker", {"title": "Joker", "overview": "A clown in Gotham."})
    synopsis_hit = score_item(
        "joker", {"title": "The Dark Knight", "overview": "Batman faces the Joker in Gotham."})
    assert title_hit.score > synopsis_hit.score
    assert title_hit.match_type == "exact"
    assert synopsis_hit.match_type == "token"
    assert synopsis_hit.matched_fields == ["overview"]


def test_score_item_person_fields_are_matched_as_substrings():
    """A person is matched by a fragment far more often than by a full name."""
    cast = {"title": "Heat", "cast": ["Al Pacino", "Robert De Niro"]}
    director = {"title": "Oppenheimer", "director": "Christopher Nolan"}
    assert score_item("pacino", cast).score > 0.0
    assert score_item("nolan", director).score > 0.0


def test_score_item_support_cannot_outrank_a_title_and_cannot_inflate_past_one():
    """The combination rule, both directions:
    a perfect cast with no title match scores SUPPORT_WEIGHT headroom only."""
    person_only = score_item("christopher nolan", {"title": "Tenet", "director": "Christopher Nolan"})
    title_and_cast = score_item("the dark knight", {
        "title": "The Dark Knight", "cast": ["Christian Bale"], "director": "Christopher Nolan"})
    assert person_only.score < title_and_cast.score
    assert title_and_cast.score == 1.0
    assert person_only.score <= 0.5 + 1e-9


def test_score_item_reports_where_it_matched():
    """Phase 4 renders these: the matched span in the RAW title, for highlighting."""
    scored = score_item("dark", {"title": "The Dark Knight"})
    assert scored.matched_fields == ["title"]
    assert scored.ranges == [(4, 8)]
    assert scored.match_type == "containment"


def test_score_item_has_no_ranges_for_a_person_only_match():
    """A highlight range is only meaningful for the title shown on the row."""
    scored = score_item("pacino", {"title": "Heat", "cast": ["Al Pacino"]})
    assert scored.ranges == []
    assert "cast" in scored.matched_fields


def test_score_item_no_match_is_a_score_of_zero_not_a_guess():
    scored = score_item("qqqqqqqq", {"title": "The Dark Knight", "overview": "Batman."})
    assert scored.score == 0.0 and scored.matched_fields == [] and scored.match_type == "none"


def test_score_item_unknown_field_names_are_ignored():
    """Never a guess, and never an exception: a provider that adds a key must not
    silently join the scoring."""
    scored = score_item("dark", {"title": "The Dark Knight", "not_a_weighted_field": "dark"})
    assert scored.matched_fields == ["title"]


def test_field_weights_decide_between_two_support_hits():
    """⚠ The weights are a RATIO, so they answer exactly one question: when TWO
    fields both matched, which one matters more? (With a single matched field the
    average cancels the weight out — by design; there is nothing to be relative
    to.) The old watchlist test could not express this at all: a ``snippet`` hit
    and a ``kind`` hit were the same ``in`` test."""
    fields = {"title": "Tenet", "cast": ["Al Pacino"], "overview": "Pacino investigates."}
    cast_heavy = score_item("pacino", fields, weights=FieldWeight(cast=50.0, overview=1.0))
    overview_heavy = score_item("pacino", fields, weights=FieldWeight(cast=1.0, overview=50.0))
    assert cast_heavy.score > overview_heavy.score
    assert cast_heavy.score > 0.0


def test_field_weights_do_not_change_the_ceiling():
    """A weight is not a licence to score above a perfect title match."""
    exact = score_item("the dark knight", {"title": "The Dark Knight"},
                       weights=FieldWeight(title=1000.0, overview=1000.0))
    assert exact.score == 1.0


def test_row_fields_maps_provider_shapes_once():
    assert row_fields({"title": "Alien", "genres": ["Horror"]})["genre"] == ["Horror"]
    assert row_fields({"name": "Alien"})["title"] == "Alien"
    assert row_fields({"snippet": "  "})["overview"] == "  "
    assert row_fields({"cast": ["A"]})["cast"] == ["A"]


def test_best_relevance_picks_the_strongest_row():
    """It is a MAX over rows, so an unrelated row can never LOWER the answer."""
    rows = [
        {"title": "The Matrix Reloaded", "year": 2003},
        {"title": "The Matrix", "year": 1999},
    ]
    assert best_relevance(rows, "the matrix") == 1.0
    assert best_relevance(rows + [{"title": "Unrelated", "year": 2001}], "the matrix") == 1.0
    # …and a query nothing answers is 0.0, never a guess.
    assert best_relevance(rows, "zzzzzzzz") == 0.0
    assert best_relevance([], "anything") == 0.0


# --------------------------------------------------------------------------- Phase 1 · fuzzy matching
@pytest.mark.skipif(not available(), reason="rapidfuzz not installed")
class TestFuzzy:
    def test_transposition_and_missing_letter_still_find_the_title(self):
        assert fuzzy_title_score("the dark knght", "The Dark Knight") > FUZZY_FLOOR
        assert fuzzy_title_score("the dark night", "The Dark Knight") > FUZZY_FLOOR
        assert fuzzy_title_score("intersteller", "Interstellar") > FUZZY_FLOOR

    def test_word_order_is_not_a_typo(self):
        """``token_sort_ratio`` exists for exactly this."""
        assert fuzzy_title_score("knight dark", "The Dark Knight") > FUZZY_FLOOR
        scored = score_item("knight dark", {"title": "The Dark Knight"})
        assert scored.score > 0.5 and scored.match_type == "fuzzy"

    def test_a_genuinely_different_title_is_still_dropped(self):
        """Typo tolerance must not become "everything matches everything"."""
        assert fuzzy_title_score("the dark knight", "Finding Nemo") == 0.0
        assert fuzzy_title_score("matrix", "Dune") == 0.0

    def test_short_queries_are_never_fuzzed(self):
        """⚠ Two characters are within typo distance of half the alphabet; the
        prefix path serves those instead (Phase 4)."""
        assert MIN_FUZZY_LEN >= 3
        assert fuzzy_title_score("th", "The Dark Knight") == 0.0
        assert fuzzy_title_score("da", "The Dark Knight") == 0.0

    def test_fuzzy_can_never_reach_an_exact_or_prefix_score(self):
        assert fuzzy_title_score("the dark knight", "the dark knight") <= 1.0
        assert fuzzy_title_score("the dark knght", "The Dark Knight") <= FUZZY_CEILING
        assert FUZZY_CEILING < 0.9

    def test_actor_names_match_on_a_fragment(self):
        """⚠ ``partial_ratio``, not ``WRatio``: these are the cases that motivated it."""
        assert fuzzy_name_score("schwarzeneger", "Arnold Schwarzenegger") > FUZZY_FLOOR
        assert fuzzy_name_score("pacino", "Al Pacino") > 0.85
        assert fuzzy_name_score("nolan", "Christopher Nolan") > 0.85
        assert fuzzy_title_score("pacino", "Al Pacino") < fuzzy_name_score("pacino", "Al Pacino")

    def test_a_wrong_name_does_not_match(self):
        assert fuzzy_name_score("pacino", "Meryl Streep") == 0.0

    def test_name_relevance_reports_the_kind_it_used(self):
        assert name_relevance("pacino", "Al Pacino") == (0.9, "containment")
        assert name_relevance("al pacino", "Al Pacino") == (1.0, "exact")
        assert name_relevance("zzzzzz", "Al Pacino")[0] == 0.0

    def test_the_library_path_answers_a_typo_end_to_end(self):
        """The phase's actual promise: ``"the dark knght"`` finds the film you OWN,
        not just a row from TMDB."""
        owned = {"title": "The Dark Knight", "year": 2008,
                 "cast": ["Christian Bale", "Heath Ledger"], "genres": ["Action"]}
        scored = score_item("the dark knght", row_fields(owned), item_year=owned["year"])
        assert scored.score > FUZZY_FLOOR
        assert scored.matched_fields[0] == "title"

    def test_a_typo_does_not_silently_become_a_different_owned_title(self):
        """Two films one letter apart must not be ranked identically."""
        real = score_item("the dark knght", {"title": "The Dark Knight"}, item_year=2008)
        other = score_item("the dark knght", {"title": "Dark Night"}, item_year=2016)
        assert real.score > other.score
