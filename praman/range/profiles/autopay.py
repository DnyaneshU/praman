"""UPI Autopay — the rail that is live in Indian banks today.

Recurring mandates with an amount cap, a nominated merchant and a pre-debit
notification. NPCI has been tightening Collect and Autopay rules after fraud
from misleading and involuntarily created mandates, and RBI has asked NPCI to
examine erroneous deductions and unclear consent — so the abuse this profile
models is current, not hypothetical.

Running the demo on this profile first is what answers "is this real or
speculative" with a demonstration instead of an argument.
"""

from __future__ import annotations

from praman.range.profiles.base import RailProfile, register


@register
class AutopayProfile(RailProfile):
    name = "autopay"
    description = "UPI Autopay recurring mandate — live today"
    ttl_seconds = 1800
