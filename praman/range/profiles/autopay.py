"""UPI Autopay — the rail that is live in Indian banks today.

Recurring mandates with an amount cap, a frequency, a nominated merchant and a
pre-debit notification. NPCI has been tightening Collect and Autopay rules
after fraud from misleading and involuntarily created mandates, and RBI has
asked NPCI to examine erroneous deductions and unclear consent — so the abuse
this profile models is current, not hypothetical.

Running the demo on this profile first is what answers "is this real or
speculative" with a demonstration instead of an argument.
"""

from __future__ import annotations

from praman.range.catalog import Task
from praman.range.mandates import IntentMandate
from praman.range.profiles.base import RailProfile, _new_intent, register


@register
class AutopayProfile(RailProfile):
    name = "autopay"
    description = "UPI Autopay recurring mandate — live today"
    ttl_seconds = 1800

    def build_intent(self, task: Task) -> IntentMandate:
        return _new_intent(task, self.expiry())
