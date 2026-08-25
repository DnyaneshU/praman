"""Turning a mandate chain into numbers Tier 2 can learn from.

Extracted on every mediation, whether or not Tier 2 is enabled, and recorded on
the episode. Two reasons that matters: the training set is then just the
campaign JSONL, and the arena can show why a chain scored badly without
re-running it.

The feature set is deliberately *behavioural*, not semantic. Tier 2's job is
the pattern a rule cannot state — a merchant eleven days old with no signed
listings taking a payment that happens to be structurally perfect. Meaning is
Tier 3's problem, and mixing the two would leave neither tier with a clear
account of what it caught.
"""

from __future__ import annotations

from decimal import Decimal

from praman.range.context import RangeContext
from praman.range.mandates import MandateChain

__all__ = ["FEATURE_NAMES", "extract"]

FEATURE_NAMES: tuple[str, ...] = (
    # Absolute: who is being paid.
    "merchant_reputation",
    "merchant_age_days",
    "merchant_signed_listings",
    # Relational: how this choice compares to the ones that were available.
    "reputation_vs_best",
    "chosen_is_top_ranked",
    "price_vs_best_available",
    # Shape of the cart itself.
    "price_to_ceiling",
    "item_count",
    "hidden_item_count",
)
"""Absolute features alone do not generalise.

A held-out evaluation caught this: trained without ever seeing one merchant,
a model built on reputation, age and signed-listings scored **0% recall** on
that merchant. With a handful of merchants, `merchant_reputation` is a unique
key, and the model memorises values rather than learning a pattern.

The relational features fix that by describing the *decision* instead of the
identity. "The agent paid a merchant it should not have ranked first" transfers
to a merchant the model has never seen; "reputation is 0.42" does not.
"""


def extract(chain: MandateChain, ctx: RangeContext) -> dict[str, float]:
    """Behavioural signals about who is being paid, how much, and versus what.

    Every value is a float so the vector round-trips through JSONL without a
    Decimal-to-float surprise later. Money ratios are computed in Decimal and
    converted once, at the end.
    """
    cart, intent = chain.cart, chain.intent
    merchant = ctx.catalog.merchants.get(cart.merchant_id)
    reputation = float(merchant.reputation) if merchant else 0.0

    ceiling = intent.max_amount or Decimal(1)
    alternatives = _alternatives(intent, ctx)
    best = alternatives[0] if alternatives else None
    best_reputation = ctx.catalog.merchant(best.merchant_id).reputation if best else reputation

    return {
        # An unknown merchant is more suspicious than a poor one, so absent
        # metadata scores worse than the worst merchant we know about.
        "merchant_reputation": reputation,
        "merchant_age_days": float(merchant.age_days) if merchant else 0.0,
        "merchant_signed_listings": float(bool(merchant and merchant.signed_listings)),
        "reputation_vs_best": reputation - float(best_reputation),
        "chosen_is_top_ranked": float(bool(best and best.merchant_id == cart.merchant_id)),
        "price_vs_best_available": float(cart.total / best.price) if best and best.price else 1.0,
        "price_to_ceiling": float(cart.total / ceiling),
        "item_count": float(len(cart.items)),
        "hidden_item_count": float(sum(not i.visible for i in cart.items)),
    }


def _alternatives(intent, ctx: RangeContext):
    """What an honest agent could have bought for this intent, best first.

    The same ranking the victim agent uses, so "did the agent pick what it
    should have" is answerable without re-running the agent.
    """
    for category in intent.allowed_categories:
        found = ctx.catalog.search(category, intent.max_amount)
        if found:
            return found
    return []


def vector(features: dict[str, float]) -> list[float]:
    """Features in a fixed order. Training and scoring must agree on it."""
    return [features.get(name, 0.0) for name in FEATURE_NAMES]
