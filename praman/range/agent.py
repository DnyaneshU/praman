"""The victim — an AI shopping agent acting under delegated authority.

The agent holds signing authority for payments on the user's behalf. That is
what "agentic payment" means, and it is why a manipulated agent produces a
chain in which *every signature verifies* and the money is still gone.

The model behind the agent is a **variable, not a constant**, so every
episode records which model ran it and rates are reported per model rather
than pooled. That is not a hedge: we measured it. Against M-08, mistral is
fully susceptible and qwen2.5:1.5b and llama3.2:3b are not, while every
structural attack succeeds against all of them at the same rate — which is the
finding that argues the fix belongs at the control layer rather than the model
layer. `python -m praman models` reproduces the table.

`ScriptedAgent` is the default and needs no credential: it is the control
showing what the corpus does when there is no judgement to subvert at all.
`OllamaAgent` puts a real model in the same seat, locally served, and changes
only which tier is being measured — see `python -m praman models`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from praman.range.catalog import Product, Task
from praman.range.context import RangeContext
from praman.range.mandates import IntentMandate, MandateChain
from praman.range.purchase import build_chain, choose_product

__all__ = ["VictimAgent", "ScriptedAgent"]


@runtime_checkable
class VictimAgent(Protocol):
    model_name: str

    def shop(self, task: Task, ctx: RangeContext) -> MandateChain:
        """Turn a task into a signed mandate chain, ready to settle."""


@dataclass
class ScriptedAgent:
    """A deterministic shopper, optionally susceptible to injected instructions.

    Sober, it takes the top-ranked affordable product. It has no judgement to
    subvert, which makes it the right baseline: anything that succeeds against
    it is a flaw in the *control*, not a lapse by a model.

    Susceptible, it obeys instructions embedded in product metadata over its
    own task — which is what prompt injection *is*, reduced to its mechanism
    and stripped of the model. That keeps M-08 measurable with no credential,
    and it makes susceptibility an explicit recorded setting rather than a
    property we hope a model has.
    """

    susceptible: bool = False

    @property
    def model_name(self) -> str:
        return "scripted-susceptible" if self.susceptible else "scripted"

    def shop(self, task: Task, ctx: RangeContext) -> MandateChain:
        # The intent comes first: it carries the rail's grant, and everything
        # downstream — what the agent can afford, what the control checks —
        # follows from it rather than from the human's own budget.
        intent = ctx.profile.build_intent(task)
        return build_chain(intent, self._select(intent, ctx), ctx)

    def _select(self, intent: IntentMandate, ctx: RangeContext) -> Product:
        if self.susceptible:
            injected = self._injected(ctx)
            if injected is not None:
                return injected
        return choose_product(intent, ctx)

    @staticmethod
    def _injected(ctx: RangeContext) -> Product | None:
        """The first listing carrying an instruction. Ordering is deterministic."""
        for sku in sorted(ctx.catalog.products):
            product = ctx.catalog.product(sku)
            if product.injected_note:
                return product
        return None
