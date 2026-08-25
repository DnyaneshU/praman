"""Tier orchestration — which layers run, in what order, and how long they took.

Deterministic where the attack is structural, learned where the pattern is
statistical, semantic only for the residual. Each tier sits where the evidence
says it survives, and the first one to object wins.

Tier 1 is the whole of it today. Tiers 2 and 3 arrive in Session 5 and slot in
behind the same `evaluate` call, so nothing upstream changes.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from praman.blue.invariants import STATEFUL, STATELESS, Invariant
from praman.blue.verdict import Verdict
from praman.range.context import RangeContext
from praman.range.mandates import MandateChain

__all__ = ["Defense"]


class Defense:
    """The control under test.

    `tiers=()` is a legitimate configuration: it is the undefended baseline,
    and being able to run the identical harness with no control is what makes
    every later number comparable.
    """

    def __init__(self, tiers: Sequence[int] = (1,)) -> None:
        self.tiers = tuple(tiers)

    def evaluate(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        started = time.perf_counter()
        verdict = self._tier1(chain, ctx) if 1 in self.tiers else Verdict.allow()
        verdict.latency_ms = round((time.perf_counter() - started) * 1000, 4)
        return verdict

    def _tier1(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        """Stateless checks first, then the one that consumes nonces.

        Short-circuiting on the first failure is not just an optimisation: it
        is what stops a chain that already failed a cheap check from burning a
        nonce it will never legitimately use.
        """
        for invariant in STATELESS:
            verdict = invariant.check(chain, ctx)
            if not verdict.allowed:
                return verdict
        for invariant in STATEFUL:
            verdict = invariant.check(chain, ctx)
            if not verdict.allowed:
                return verdict
        return Verdict.allow()

    def invariants(self) -> tuple[Invariant, ...]:
        return STATELESS + STATEFUL if 1 in self.tiers else ()
