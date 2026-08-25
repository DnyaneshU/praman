"""NPCI Unified Agent Protocol — the rail India is about to switch on.

Extends UPI Circle delegated payments and Reserve Pay so a registered agent can
transact within user-set limits without per-transaction approval. Awaiting RBI
approval at time of writing, which is exactly why it matters: there are no
deployed defenses for a rail that is not live, and testing a design before it
ships is the highest-leverage moment in the lifecycle.

The substantive difference from Autopay is **delegated scope**. On Autopay the
mandate carries the user's own ceiling. Under UAP the agent is granted less
than the human has: a delegate cap, set when authority is handed over, that
binds every transaction the agent makes on its own.

That is not a cosmetic relabel. A lower ceiling changes what the agent can
afford, which changes which merchant it buys from, which changes the features
Tier 2 sees — so the two rails genuinely produce different campaigns rather
than the same numbers under a different heading.
"""

from __future__ import annotations

from decimal import Decimal

from praman.money import rupees
from praman.range.catalog import Task
from praman.range.mandates import IntentMandate
from praman.range.profiles.base import RailProfile, register

DELEGATE_CAP = rupees(2500)
"""What the human hands to the agent, which is less than the human holds.

The whole premise of delegated payments is that an agent is trusted with a
smaller amount than its principal. Modelling that is what makes scope
escalation (S-05) a meaningful attack on this rail rather than a slide."""


@register
class UapProfile(RailProfile):
    name = "uap"
    description = "NPCI Unified Agent Protocol delegate — pending RBI approval"

    # Delegated authority is short-lived by design: a grant that outlives the
    # session it was given in is where scope escalation starts.
    ttl_seconds = 600

    def build_intent(self, task: Task) -> IntentMandate:
        """The same chain shape, under the tighter of the two ceilings."""
        intent = super().build_intent(task)
        intent.max_amount = min(intent.max_amount, self.delegate_cap)
        return intent

    @property
    def delegate_cap(self) -> Decimal:
        return DELEGATE_CAP
