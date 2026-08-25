"""Tier orchestration — which layers run, in what order, and how long they took.

Deterministic where the attack is structural, learned where the pattern is
statistical, semantic only for the residual. Each tier sits where the evidence
says it survives, and the first one to object wins.

The ordering is not arbitrary. Tier 1 is arithmetic and costs nothing, so it
goes first and takes the whole model-independent structural class off the
table. Tier 2 only sees what Tier 1 allowed, which is why its training set is
the residual rather than a rulebook. Tier 3 is last because it is the only tier
that cannot decide on its own — it escalates.

Features are extracted on every mediation regardless of which tiers are
enabled, so a Tier-1-only campaign still produces the training data Tier 2
needs. That is the loop: Red's survivors become Blue's next lesson.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from praman.blue.anomaly import AnomalyTier
from praman.blue.divergence import DivergenceTier
from praman.blue.features import extract
from praman.blue.invariants import STATEFUL, STATELESS
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

    def __init__(
        self,
        tiers: Sequence[int] = (1,),
        *,
        anomaly: AnomalyTier | None = None,
        divergence: DivergenceTier | None = None,
    ) -> None:
        self.tiers = tuple(tiers)
        self.anomaly = anomaly or AnomalyTier()
        self.divergence = divergence or DivergenceTier()

    def evaluate(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        started = time.perf_counter()
        features = extract(chain, ctx)
        verdict = self._decide(chain, ctx, features)
        verdict.features = features
        verdict.latency_ms = round((time.perf_counter() - started) * 1000, 4)
        return verdict

    def _decide(
        self, chain: MandateChain, ctx: RangeContext, features: dict[str, float]
    ) -> Verdict:
        if 1 in self.tiers:
            verdict = self._tier1(chain, ctx)
            if not verdict.allowed:
                return verdict

        if 2 in self.tiers:
            verdict = self.anomaly.check(features)
            if not verdict.allowed:
                return verdict

        if 3 in self.tiers:
            verdict = self.divergence.check(chain)
            if not verdict.allowed:
                return verdict

        return Verdict.allow()

    def _tier1(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        """Stateless checks first, then the one that consumes nonces.

        Short-circuiting on the first failure is not just an optimisation: it
        is what stops a chain that already failed a cheap check from burning a
        nonce it will never legitimately use.
        """
        for invariant in (*STATELESS, *STATEFUL):
            verdict = invariant.check(chain, ctx)
            if not verdict.allowed:
                return verdict
        return Verdict.allow()
