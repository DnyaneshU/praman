"""Deciding which variants survive to the next round.

Fitness has two terms, in strict priority order:

**Money first.** A variant that moved rupees has already won; nothing else
competes with it.

**Then progress.** Among variants that took nothing, prefer the one the control
had to think longer about. A chain refused by the last check got further than
one refused by the first, and that difference is the gradient the search climbs.

The second term is why `mut-neutral` — which satisfies inv-02 and profits ₹0 —
does not get mistaken for a win. Passing a rule and taking money are different
outcomes, and a selector that conflated them would report a rising ASR while
the attacker learned nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from praman.blue.invariants import INVARIANTS
from praman.red.episode import Episode
from praman.red.mutator.base import Variant

__all__ = ["Candidate", "select", "fitness"]

_ORDER = {invariant.id: index for index, invariant in enumerate(INVARIANTS)}
_CLEARED_EVERY_CHECK = len(INVARIANTS)


@dataclass(frozen=True)
class Candidate:
    variant: Variant
    episode: Episode

    @property
    def succeeded(self) -> bool:
        return self.episode.succeeded


def progress(episode: Episode) -> int:
    """How far through the control this chain got before being refused."""
    if episode.violated_invariant is None:
        return _CLEARED_EVERY_CHECK
    return _ORDER.get(episode.violated_invariant, 0)


def fitness(episode: Episode) -> tuple[Decimal, int]:
    return episode.rupees_moved, progress(episode)


def select(candidates: list[Candidate], keep: int) -> list[Candidate]:
    """The fittest `keep` candidates, deduplicated by variant.

    Sorted deterministically — ties break on the variant's own lineage rather
    than on iteration order, so a campaign is reproducible from its seed.
    """
    best: dict[Variant, Candidate] = {}
    for candidate in candidates:
        existing = best.get(candidate.variant)
        if existing is None or fitness(candidate.episode) > fitness(existing.episode):
            best[candidate.variant] = candidate

    ranked = sorted(
        best.values(),
        key=lambda c: (fitness(c.episode), c.variant.lineage),
        reverse=True,
    )
    return ranked[:keep]
