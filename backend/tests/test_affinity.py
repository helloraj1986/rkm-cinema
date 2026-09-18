"""Tests for taste affinity (SEARCH_IMPROVEMENT_PLAN Phase 5).

The property under test throughout is SUBTLETY. Personalization that can outrank a
better title match is not intelligence, it is a bug the user experiences as "search
ignored what I typed" — so most of what follows pins the bound, not the ranking.
"""
import pytest

from services.search.affinity import (
    MAX_AFFINITY_BONUS,
    MAX_HISTORY,
    RECENCY_DECAY,
    build_affinity,
    empty_affinity,
)
from services.search.fuzzy import FUZZY_CEILING
from services.search.scoring import CONTAINMENT_BASE, CONTAINMENT_SPAN


def _watched(title, genres, play_count=1):
    return {"title": title, "genres": genres, "play_count": play_count, "played": True}


# --------------------------------------------------------------------------- the bound
def test_affinity_bonus_is_smaller_than_a_tier_step():
    """⚠ The invariant that makes this feature safe, not just the number.

    Same bound as ``ranking.OWNED_BONUS``: strictly less than the gap between two
    adjacent relevance tiers, so taste can reorder equally-relevant rows and can
    NEVER promote one past a better match. At or above the step, a genre he likes
    outranks a title he typed — which is the "reads as wrong, not smart" failure the
    plan warns about.
    """
    tier_step = FUZZY_CEILING - (CONTAINMENT_BASE + CONTAINMENT_SPAN)
    assert 0 < MAX_AFFINITY_BONUS < tier_step, (MAX_AFFINITY_BONUS, tier_step)


def test_the_bonus_is_an_absolute_score_not_a_percentage():
    """⚠ The plan says "max +10–15% of base score"; on THIS scale that is not subtle.
    12% of a 0.66 containment match is 0.08 — half again the 0.05 tier step."""
    affinity = build_affinity([_watched("X", ["Comedy"])])
    best = affinity.bonus(["Comedy"])
    assert best == MAX_AFFINITY_BONUS
    # A percentage would grow with the base score; this does not.
    worst_title_match = 0.66
    assert best < worst_title_match * 0.12, "a 12% multiplier would exceed the tier step"


def test_the_bonus_is_capped_however_many_genres_match():
    affinity = build_affinity([_watched("X", ["Comedy", "Drama", "Action"])])
    assert affinity.bonus(["Comedy", "Drama", "Action"]) == MAX_AFFINITY_BONUS
    assert affinity.bonus(["Comedy"]) == MAX_AFFINITY_BONUS


# --------------------------------------------------------------------------- the profile
def test_an_empty_history_is_a_working_value_that_adds_nothing():
    """⚠ Not a special case: "switched off", "nothing watched" and "the lookup
    failed" all have to travel the identical path through the ranker, or one of
    them ends up with its own branch and its own bug."""
    for empty in (empty_affinity(), build_affinity([]), build_affinity(None)):
        assert empty.is_empty()
        assert empty.strength(["Comedy"]) == 0.0
        assert empty.bonus(["Comedy"]) == 0.0
        assert empty.top == ()


def test_the_strongest_genre_is_normalised_to_one():
    """The profile is a SHAPE, not a magnitude — how much television somebody has
    watched is not evidence about which of two films they want tonight."""
    affinity = build_affinity([
        _watched("A", ["Comedy"]), _watched("B", ["Comedy"]), _watched("C", ["Drama"]),
    ])
    assert affinity.weights["comedy"] == 1.0
    assert 0 < affinity.weights["drama"] < 1.0
    assert affinity.top[0] == "Comedy"


def test_recency_decay_favours_what_was_watched_lately():
    """The provider hands history over newest-first, so POSITION is the recency
    signal and the most recently watched genre takes the top slot.

    ⚠ Stated as an order-symmetry assertion on purpose: comparing one recent title
    against forty old ones would prove nothing about decay — forty comedies SHOULD
    describe a comedy viewer. What the decay has to guarantee is that two otherwise
    identical histories differ by which was watched last.
    """
    comedy_last = build_affinity([_watched("New", ["Horror"]), _watched("Old", ["Comedy"])])
    horror_last = build_affinity([_watched("New", ["Comedy"]), _watched("Old", ["Horror"])])
    assert comedy_last.top[0] == "Horror"
    assert horror_last.top[0] == "Comedy"
    assert comedy_last.weights["horror"] > comedy_last.weights["comedy"]
    assert RECENCY_DECAY < 1.0


def test_without_decay_the_order_would_not_matter():
    """The falsification direction: set the decay to 1.0 and the symmetry above
    collapses — which is what proves the assertion is testing the decay and not
    something else in the profile."""
    flat = build_affinity([_watched("New", ["Horror"]), _watched("Old", ["Comedy"])], decay=1.0)
    assert flat.weights["horror"] == flat.weights["comedy"]


def test_recency_decay_shrinks_an_old_title_by_an_order_of_magnitude():
    """The curve itself, stated as the ratio it produces — and the two things it has
    to balance: the newest title is not drowned to nothing, while 35 comedies still
    describe a comedy viewer."""
    assert RECENCY_DECAY ** 35 == pytest.approx(0.115, abs=0.005)  # ≈ a tenth of the newest

    rows = [_watched("Newest", ["Horror"])] + [_watched(f"Old {i}", ["Comedy"]) for i in range(35)]
    affinity = build_affinity(rows)
    assert affinity.weights["horror"] > 0.05, "the newest title must not be drowned out"
    assert affinity.top[0] == "Comedy", "…but 35 comedies still describe a comedy viewer"


def test_a_rewatch_counts_for_more():
    once = build_affinity([_watched("A", ["Comedy"]), _watched("B", ["Drama"])])
    thrice = build_affinity([_watched("A", ["Comedy"], play_count=3), _watched("B", ["Drama"])])
    assert thrice.weights["drama"] < once.weights["drama"]  # comedy grew, drama did not


def test_history_is_bounded():
    """Beyond the bound the decay has made the contribution negligible, so a huge
    library cannot build a profile out of noise — and the loop stays cheap."""
    rows = [_watched(f"T{i}", ["Comedy"]) for i in range(MAX_HISTORY * 3)]
    affinity = build_affinity(rows)
    assert affinity.weights["comedy"] == 1.0
    # The 400th title contributes nothing measurable either way.
    truncated = build_affinity(rows[:MAX_HISTORY])
    assert truncated.weights == affinity.weights


# --------------------------------------------------------------------------- tolerance
def test_rows_without_genres_are_skipped_not_counted_as_empty():
    affinity = build_affinity([_watched("No tags", []), {"title": "No key at all"}])
    assert affinity.is_empty()


@pytest.mark.parametrize("bad", [None, "", "not a number", -3])
def test_a_missing_or_junk_play_count_still_counts_once(bad):
    """⚠ A multiplier of 0 would silently drop the row from the profile, and
    "played with no count recorded" is a normal Jellyfin answer."""
    affinity = build_affinity([{**_watched("A", ["Comedy"]), "play_count": bad}])
    assert affinity.weights.get("comedy") == 1.0


def test_genres_match_case_and_punctuation_insensitively():
    affinity = build_affinity([_watched("A", ["Sci-Fi & Fantasy"])])
    assert affinity.strength(["sci fi & fantasy"]) == 1.0
    assert affinity.strength(["Sci-Fi & Fantasy"]) == 1.0


def test_strength_takes_the_best_genre_not_the_sum():
    """A title tagged with five of his genres is not five times as appealing — and
    summing would let a broadly-tagged title run away with the ranking."""
    affinity = build_affinity([
        _watched("A", ["Comedy"]), _watched("B", ["Comedy"]),
        _watched("C", ["Drama"]), _watched("D", ["Action"]),
    ])
    one = affinity.strength(["Comedy"])
    many = affinity.strength(["Comedy", "Drama", "Action"])
    assert one == many == 1.0


def test_an_unknown_genre_adds_nothing():
    affinity = build_affinity([_watched("A", ["Comedy"])])
    assert affinity.strength(["Documentary"]) == 0.0
    assert affinity.strength([]) == 0.0
    assert affinity.strength(None) == 0.0
