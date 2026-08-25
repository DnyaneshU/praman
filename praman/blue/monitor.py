"""The out-of-band reference monitor.

This is the single architectural decision the project cannot trade away. The
monitor sits *beside* the agent and mediates every state-changing call, rather
than being a rule the agent applies to itself. In the adaptive-evaluation
literature that is the only defense family still standing under an attacker
that adapts — Progent went 25.8% undefended, 4.2% under standard attack, 2.6%
under adaptive attack, no increase, against ninefold jumps elsewhere.

An in-band control would quietly discard that result, so the property is
enforced rather than documented: attaching a monitor makes the ledger refuse
any settlement it did not approve. `test_monitor.py` calls the ledger directly
and asserts it raises.

Approval is thread-local. S-03 fires several settlements at once, and a shared
approval flag would be exactly the check-then-act race the attack is about.
"""

from __future__ import annotations

import threading

from praman.blue.defense import Defense
from praman.blue.verdict import Verdict
from praman.range.context import RangeContext
from praman.range.ledger import SettlementResult
from praman.range.mandates import MandateChain

__all__ = ["Monitor", "Mediation"]


class Mediation:
    """What the monitor decided, and what the ledger then did about it."""

    __slots__ = ("verdict", "settlement")

    def __init__(self, verdict: Verdict, settlement: SettlementResult | None) -> None:
        self.verdict = verdict
        self.settlement = settlement

    @property
    def allowed(self) -> bool:
        return self.verdict.allowed


class Monitor:
    """Mediates settlement for one range.

    Constructing a monitor arms the ledger. There is no way to disarm it — a
    control the range can switch off from the inside is not a control.
    """

    def __init__(self, defense: Defense, ctx: RangeContext) -> None:
        self.defense = defense
        self.ctx = ctx
        self._approval = threading.local()
        ctx.ledger.require_mediation(self)

    def approves(self, mandate_id: str) -> bool:
        """Called by the ledger. True only on the thread mid-`mediate`."""
        return getattr(self._approval, "mandate_id", None) == mandate_id

    def mediate(self, chain: MandateChain) -> Mediation:
        """Judge the chain, and settle it only if the verdict allows."""
        verdict = self.defense.evaluate(chain, self.ctx)
        if not verdict.allowed:
            return Mediation(verdict, None)

        self._approval.mandate_id = chain.payment.mandate_id
        try:
            settlement = self.ctx.ledger.settle(chain.payment, source=self.ctx.principal)
        finally:
            self._approval.mandate_id = None
        return Mediation(verdict, settlement)
