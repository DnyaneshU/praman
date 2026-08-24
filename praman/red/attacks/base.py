"""The Attack interface and its registry.

An attack takes an honest, signed mandate chain and returns a tampered one.
That is the entire contract — which is what lets the mutator in Session 4 treat
attacks as things to recombine rather than scripts to replay.

Two rules every attack in this package follows:

**Re-sign what you can legitimately sign.** The attacker holds its own key and
whatever it has compromised, never the user's or an honest merchant's. An
attack that forges the user's signature would be testing our signature check,
which already works — the interesting attacks are the ones where *every
signature still verifies* and the chain is broken anyway.

**Route harm to `ctx.attacker_vpa`.** Metrics read harm off that one account,
so an attack that moves money somewhere else registers as doing nothing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from praman.range.context import RangeContext
from praman.range.mandates import MandateChain

__all__ = ["Attack", "AttackClass", "ATTACKS", "register", "get_attack"]

AttackClass = Literal["structural", "semantic", "india"]


class Attack(ABC):
    id: str
    name: str
    attack_class: AttackClass
    root_cause: str
    """Published root cause this maps to (RC-1..RC-6), for the corpus table."""

    concurrent: bool = False
    """Settle this attack's chains simultaneously rather than in sequence.

    Only S-03 needs it, but it has to be genuine: a redemption race settled
    sequentially is not a race, and the finding would be theatre."""

    @abstractmethod
    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        """Return a tampered chain. Must not mutate the input in place."""

    def plan(self, honest: MandateChain, ctx: RangeContext) -> list[MandateChain]:
        """The chains to settle, in order.

        Most attacks are one tampered chain. Replays return the honest chain
        followed by the replay; races return the same chain several times.
        """
        return [self.apply(honest, ctx)]

    def __repr__(self) -> str:
        return f"<{self.id} {self.name}>"


ATTACKS: dict[str, type[Attack]] = {}


def register(cls: type[Attack]) -> type[Attack]:
    if cls.id in ATTACKS:
        raise ValueError(f"duplicate attack id {cls.id!r}")
    ATTACKS[cls.id] = cls
    return cls


def get_attack(attack_id: str) -> Attack:
    if attack_id not in ATTACKS:
        known = ", ".join(sorted(ATTACKS)) or "none registered"
        raise KeyError(f"unknown attack {attack_id!r}; known: {known}")
    return ATTACKS[attack_id]()
