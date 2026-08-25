"""The mutator interface — how a blocked attack becomes a new one.

This is the session the submission rests on. Everything before it produces the
number every competitor also reports: attack success against a fixed script.
The number nobody publishes for payments is what happens when the attacker gets
to read the rejection and try again, and that gap is the product.

Two design decisions make the search reproducible and the results auditable:

**A variant is a recipe, not a chain.** Chains are built fresh from a seeded
range every episode, so storing a tampered chain would pin it to one range
instance. A `Variant` records *which attack and which strategies*, so it can be
rebuilt identically anywhere — that is what lets a judge re-run our campaign.

**Strategies target a named invariant.** The control tells the attacker exactly
which rule it enforced. The search uses that to pick strategies aimed at *that*
rule rather than mutating blindly, which is what "defense-aware attacker" means
in the adaptive-evaluation literature.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol

from praman.blue.verdict import Verdict
from praman.range.context import RangeContext
from praman.range.mandates import MandateChain
from praman.red.attacks.base import Attack, get_attack

__all__ = ["Strategy", "Mutator", "Variant", "MutatedAttack", "STRATEGIES", "register"]


class Strategy(ABC):
    """One idea for getting past one named check."""

    id: str
    targets: tuple[str, ...]
    """Invariant ids this strategy tries to evade."""
    rationale: str
    """Why it might work — quoted verbatim in the report when it does."""

    @abstractmethod
    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        """Return a further-tampered chain. Must re-sign what it changes."""

    def __repr__(self) -> str:
        return f"<{self.id}>"


STRATEGIES: dict[str, Strategy] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    if cls.id in STRATEGIES:
        raise ValueError(f"duplicate strategy id {cls.id!r}")
    STRATEGIES[cls.id] = cls()
    return cls


def strategies_for(invariant: str) -> list[Strategy]:
    """Every strategy aimed at a given rule, in a stable order."""
    return [s for s in STRATEGIES.values() if invariant in s.targets]


@dataclass(frozen=True)
class Variant:
    """A rebuildable attack: a seed technique plus the strategies layered on it.

    Frozen and hashable so the selector can deduplicate a population without
    comparing chains.
    """

    attack_id: str
    strategies: tuple[str, ...] = field(default=())

    @property
    def lineage(self) -> list[str]:
        return [self.attack_id, *self.strategies]

    @property
    def generation(self) -> int:
        return len(self.strategies)

    def extend(self, strategy: Strategy) -> Variant:
        return Variant(self.attack_id, (*self.strategies, strategy.id))

    def build(self) -> Attack:
        base = get_attack(self.attack_id)
        if not self.strategies:
            return base
        return MutatedAttack(base, tuple(STRATEGIES[s] for s in self.strategies))

    def __str__(self) -> str:
        return " -> ".join(self.lineage)


class MutatedAttack(Attack):
    """A base attack with strategies layered onto its tamper step.

    `plan` delegates to the base class's implementation *bound to this object*,
    so S-03's three-way race and S-04's replay keep their structure while the
    tampering underneath is the mutated one. Overriding `plan` here instead
    would silently flatten those attacks into single-chain ones.
    """

    def __init__(self, base: Attack, strategies: tuple[Strategy, ...]) -> None:
        self.base = base
        self.strategies = strategies
        self.id = base.id
        self.name = base.name
        self.attack_class = base.attack_class
        self.root_cause = base.root_cause
        self.concurrent = base.concurrent

    def __getattr__(self, item: str):
        """Attack-specific attributes (S-03's `redemptions`) come from the base."""
        return getattr(self.base, item)

    def prepare(self, ctx: RangeContext) -> None:
        self.base.prepare(ctx)

    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        mutated = self.base.apply(chain, ctx)
        for strategy in self.strategies:
            mutated = strategy.apply(mutated, ctx)
        return mutated

    def plan(self, honest: MandateChain, ctx: RangeContext) -> list[MandateChain]:
        return type(self.base).plan(self, honest, ctx)


class Mutator(Protocol):
    name: str

    def mutate(self, variant: Variant, verdict: Verdict) -> list[Variant]:
        """Given what the control said, propose variants that target that rule."""
