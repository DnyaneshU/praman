"""The victim — an AI shopping agent acting under delegated authority.

The agent holds signing authority for payments on the user's behalf. That is
what "agentic payment" means, and it is why a manipulated agent produces a
chain in which *every signature verifies* and the money is still gone.

The model behind the agent is a **variable, not a constant**. Semantic
susceptibility is heavily model-dependent — cost-optimised models sat at
99-100% in the published 1,440-trial study, alignment-trained ones at 0% — so
every episode records which model ran it and rates are reported per tier.
Structural attacks succeed against all of them, which is the finding that
argues the fix belongs at the control layer rather than the model layer.

`ScriptedAgent` is the default and needs no credential. The LLM-backed agent
arrives in Session 5 and changes only which tier is being measured.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from praman.range.catalog import Task
from praman.range.context import RangeContext
from praman.range.mandates import MandateChain
from praman.range.purchase import build_chain, choose_product

__all__ = ["VictimAgent", "ScriptedAgent"]


@runtime_checkable
class VictimAgent(Protocol):
    model_name: str

    def shop(self, task: Task, ctx: RangeContext) -> MandateChain:
        """Turn a task into a signed mandate chain, ready to settle."""


class ScriptedAgent:
    """A deterministic, well-behaved shopper.

    Takes the top-ranked affordable product and builds an honest chain. It has
    no judgement to subvert, which makes it the right baseline: anything that
    succeeds against this agent is a flaw in the *control*, not a lapse by the
    model.
    """

    model_name = "scripted"

    def shop(self, task: Task, ctx: RangeContext) -> MandateChain:
        return build_chain(task, choose_product(task, ctx), ctx)
