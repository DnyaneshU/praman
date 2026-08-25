"""Building an honest mandate chain, and settling one.

This is the path everything else deviates from. Session 2's victim agent calls
`build_chain`; every attack in the corpus takes the chain it produces and
tampers with exactly one link.
"""

from __future__ import annotations

from decimal import Decimal

from praman.money import fmt
from praman.range.catalog import Product
from praman.range.context import RangeContext
from praman.range.ledger import SettlementResult
from praman.range.mandates import (
    CartMandate,
    IntentMandate,
    LineItem,
    MandateChain,
    PaymentMandate,
    new_id,
    new_nonce,
)

__all__ = ["choose_product", "build_chain", "settle_chain", "summarise"]


def choose_product(intent: IntentMandate, ctx: RangeContext) -> Product:
    """Pick the top-ranked product the *intent* can afford.

    Deliberately the intent's ceiling, not the task's. Under a delegated rail
    the agent is granted less than its principal holds, and an agent that
    shopped to the human's budget would build carts its own authority cannot
    cover — every one of which the control would then refuse as a false
    positive. The grant is the budget.

    Ranking comes from the catalog (reputation, then price). M-08 attacks that
    ordering rather than the choice itself.
    """
    for category in intent.allowed_categories:
        matches = ctx.catalog.search(category, intent.max_amount)
        if matches:
            return matches[0]
    raise LookupError(f"nothing in {intent.allowed_categories} under {intent.max_amount}")


def build_chain(intent: IntentMandate, product: Product, ctx: RangeContext) -> MandateChain:
    """Assemble a signed, honest Intent -> Cart -> Payment chain."""
    item = LineItem(
        sku=product.sku,
        name=product.name,
        price=product.price,
        qty=1,
        category=product.category,
    )
    cart = CartMandate(
        mandate_id=new_id("cart"),
        intent_id=intent.mandate_id,
        merchant_id=product.merchant_id,
        items=[item],
        total=item.subtotal(),
        display_summary=summarise([item]),
        expires_at=ctx.profile.expiry(),
        nonce=new_nonce(),
    )
    payment = PaymentMandate(
        mandate_id=new_id("pay"),
        cart_id=cart.mandate_id,
        beneficiary=ctx.merchant_vpa(product.merchant_id),
        amount=cart.total,
        expires_at=ctx.profile.expiry(),
        nonce=new_nonce(),
    )

    return ctx.sign_chain(MandateChain(intent=intent, cart=cart, payment=payment))


def settle_chain(chain: MandateChain, ctx: RangeContext) -> SettlementResult:
    """Settle straight to the ledger, with no control in the way.

    Session 3 routes this through the out-of-band monitor instead. Until then,
    this is the undefended baseline every attack is measured against.
    """
    return ctx.ledger.settle(chain.payment, source=ctx.principal)


def summarise(items: list[LineItem]) -> str:
    """What the user is shown. Only visible lines appear — that gap is M-09."""
    visible = [i for i in items if i.visible]
    parts = [f"{i.name} x{i.qty} — {fmt(i.subtotal())}" for i in visible]
    total: Decimal = sum((i.subtotal() for i in visible), Decimal(0))
    return " · ".join(parts) + f"  |  total {fmt(total)}"
