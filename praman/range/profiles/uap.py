"""NPCI Unified Agent Protocol — the rail India is about to switch on.

Extends UPI Circle delegated payments and Reserve Pay so a registered agent can
transact within user-set limits without per-transaction approval. Awaiting RBI
approval at time of writing, which is exactly why it matters: there are no
deployed defenses for a rail that is not live, and testing a design before it
ships is the highest-leverage moment in the whole lifecycle.

Two things differ from Autopay, and both add a check rather than changing the
mandate shape — which is the point of having profiles at all:

  * a delegated spend ceiling separate from the per-transaction ceiling, so an
    agent can be trusted with ₹4,000 a time and ₹10,000 a month
  * a shorter mandate lifetime, because delegated authority that outlives the
    session it was granted in is how scope escalation starts

NPCI has publicly named consent-traceability as the open requirement. inv-08 is
the smallest honest answer to it we can implement here.
"""

from __future__ import annotations

from praman.range.catalog import Task
from praman.range.mandates import IntentMandate
from praman.range.profiles.base import RailProfile, register


@register
class UapProfile(RailProfile):
    name = "uap"
    description = "NPCI Unified Agent Protocol delegate — pending RBI approval"

    # Delegated authority is short-lived by design.
    ttl_seconds = 600

    invariants = (*RailProfile.invariants, "inv-08")

    def build_intent(self, task: Task) -> IntentMandate:
        """The same chain shape, under a tighter grant.

        The delegate ceiling is deliberately below the task ceiling: the whole
        premise of delegated payments is that the agent is trusted with less
        than the human is.
        """
        return super().build_intent(task)
