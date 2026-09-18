"""Taste affinity from what this person actually watched — SEARCH_IMPROVEMENT_PLAN Phase 5.

**The idea.** Search relevance and taste are different questions. "Which of these
answers what I typed?" is the scorer's job (Phases 0–3). "Which of the things I
did *not* type do I actually want?" is this module's — and the only honest source
for it is the history the media server already keeps: what he finished, how many
times, and how recently.

**The rule that keeps it from backfiring.** A personalization signal is
*subtle or it is wrong*. Over-personalized SEARCH reads as a bug, not as
intelligence — a query for "dune" that buries *Dune* because he mostly watches
comedies is a worse product than one with no personalization at all. So the
bonus is bounded by the SAME invariant as ``ranking.OWNED_BONUS``:

    0 < MAX_AFFINITY_BONUS < FUZZY_CEILING - (CONTAINMENT_BASE + CONTAINMENT_SPAN)

i.e. strictly less than the step between two adjacent relevance tiers, so taste
can reorder equally-relevant rows and can never promote one past a better match.

⚠ This is also why the boost is an ABSOLUTE score, not the plan's "max +10–15% of
base score". On this scale a percentage is not subtle at all: 12% of a 0.66
containment score is 0.08, half again the 0.05 tier step — so a genre match would
push a row into the tier above, which is exactly the failure the plan warns about.
The percentage is the right idea measured against the wrong scale.

Pure: no I/O, no config, no clock. Callers supply the history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from services.search.normalize import normalize_title

__all__ = [
    "Affinity",
    "MAX_AFFINITY_BONUS",
    "build_affinity",
    "empty_affinity",
]

#: ⚠ See the module docstring. Bounded by the tier step, exactly like OWNED_BONUS —
#: pinned by ``test_affinity_bonus_is_smaller_than_a_tier_step``.
MAX_AFFINITY_BONUS = 0.03

#: How fast a title's influence fades with its position in the history. The provider
#: hands over watched titles NEWEST FIRST, so position is a recency proxy: at 0.94 a
#: title 10 places back still counts for half, one 35 places back for a tenth, and a
#: decade-old DVD cannot outweigh last week's binge.
#:
#: ⚠ Deliberately a position decay rather than a date decay: it needs no clock, it
#: cannot drift with the container's timezone, and it is exactly as good as the
#: ordering the provider already guarantees. A title with no ``last_played`` sorts
#: last, so missing metadata costs it influence rather than granting it.
RECENCY_DECAY = 0.94

#: How much history is read. Beyond this the decay has made the contribution
#: negligible (0.94^120 ≈ 0.0006), so the bound costs nothing and keeps a 5000-title
#: library from building a profile out of noise.
MAX_HISTORY = 120


@dataclass(frozen=True)
class Affinity:
    """Normalised genre weights for one viewer, strongest first.

    ``weights`` maps a case/punctuation-insensitive genre key to 0.0–1.0, where the
    viewer's strongest genre is exactly 1.0. ``top`` is the same information as an
    ordered tuple, for display and debugging.
    """

    weights: Mapping[str, float] = field(default_factory=dict)
    top: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not self.weights

    def strength(self, genres: Iterable[Any] | None) -> float:
        """How strongly a candidate's genres overlap this viewer's taste (0.0–1.0).

        The MAX across the candidate's genres, not the sum: a title tagged with five
        of his genres is not five times as appealing as one tagged with his
        favourite, and summing would let a broadly-tagged title (or a badly-tagged
        one) run away with the ranking.
        """
        if not self.weights or not genres:
            return 0.0
        best = 0.0
        for genre in genres:
            key = normalize_title(genre)
            if key:
                best = max(best, float(self.weights.get(key, 0.0)))
        return best

    def bonus(self, genres: Iterable[Any] | None, *, maximum: float = MAX_AFFINITY_BONUS) -> float:
        """The absolute score bonus for a candidate, in ``[0, maximum]``."""
        return round(self.strength(genres) * maximum, 6)


#: The "no history / switched off" answer. ⚠ An empty Affinity is a working value,
#: not a special case: every call site can use it unconditionally, so switching the
#: feature off cannot route through different code than a person who has watched
#: nothing.
EMPTY = Affinity()


def empty_affinity() -> Affinity:
    """An affinity that adds nothing to any score."""
    return EMPTY


def build_affinity(items: Iterable[Mapping[str, Any]] | None, *,
                   decay: float = RECENCY_DECAY,
                   limit: int = MAX_HISTORY) -> Affinity:
    """Build a viewer's genre profile from their WATCHED history.

    ``items`` are the rows the library provider returns for watched titles —
    ``{genres: [...], play_count: int, played: bool}``, newest-watched first.
    """
    if not items:
        return EMPTY

    totals: dict[str, float] = {}
    names: dict[str, str] = {}
    for index, row in enumerate(list(items)[:limit]):
        genres = row.get("genres") or []
        if not genres:
            continue
        # ⚠ A title watched three times is three times the evidence — but never zero,
        # because "played with no count recorded" is a normal Jellyfin answer and a
        # multiplier of 0 would silently drop the item from the profile.
        try:
            repeats = max(1, int(row.get("play_count") or 0))
        except (TypeError, ValueError):
            repeats = 1
        weight = repeats * (decay ** index)
        for genre in genres:
            key = normalize_title(genre)
            if not key:
                continue
            totals[key] = totals.get(key, 0.0) + weight
            names.setdefault(key, str(genre))

    if not totals:
        return EMPTY

    # Normalised to the strongest genre, so the profile is a SHAPE and not a
    # magnitude: somebody who has watched 400 films and somebody who has watched 4
    # get the same bonus for the same overlap. The bonus is a tie-breaker between
    # equally-relevant results, and how much television a person has watched is not
    # evidence about which of two films they want tonight.
    peak = max(totals.values())
    weights = {key: round(value / peak, 6) for key, value in totals.items()}
    top = tuple(sorted(weights, key=lambda k: (-weights[k], k))[:5])
    return Affinity(weights=weights, top=tuple(names.get(k, k) for k in top))
