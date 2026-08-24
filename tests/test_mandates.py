"""The three mandates and the chain that binds them."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from praman.money import rupees
from praman.range.mandates import (
    CartMandate,
    IntentMandate,
    LineItem,
    MandateChain,
    PaymentMandate,
    new_nonce,
)


def _later(minutes: int = 30) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def make_intent(**over) -> IntentMandate:
    kw = dict(
        mandate_id="int-001",
        principal="user:asha",
        description="Running shoes under 4000 from a reputable seller",
        max_amount=rupees(4000),
        allowed_categories=["footwear"],
        expires_at=_later(),
        nonce=new_nonce(),
    )
    kw.update(over)
    return IntentMandate(**kw)


def make_cart(**over) -> CartMandate:
    items = over.pop(
        "items",
        [LineItem(sku="SKU-1", name="Road Runner 7", price=rupees("3940.00"), qty=1)],
    )
    kw = dict(
        mandate_id="cart-001",
        intent_id="int-001",
        merchant_id="merchant_0031",
        items=items,
        total=sum((i.price * i.qty for i in items), Decimal(0)),
        display_summary="Road Runner 7 x1 — ₹3,940.00",
        expires_at=_later(),
        nonce=new_nonce(),
    )
    kw.update(over)
    return CartMandate(**kw)


def make_payment(**over) -> PaymentMandate:
    kw = dict(
        mandate_id="pay-001",
        cart_id="cart-001",
        beneficiary="merchant_0031@bank",
        amount=rupees("3940.00"),
        expires_at=_later(),
        nonce=new_nonce(),
    )
    kw.update(over)
    return PaymentMandate(**kw)


def test_intent_holds_decimal_paise():
    intent = make_intent()
    assert intent.max_amount == Decimal(400000)
    assert isinstance(intent.max_amount, Decimal)


def test_negative_amount_rejected():
    with pytest.raises(ValidationError):
        make_intent(max_amount=Decimal(-1))


def test_line_item_visible_by_default():
    """M-09 hides a line item; the default must be honest."""
    item = LineItem(sku="S", name="n", price=rupees(10), qty=1)
    assert item.visible is True


def test_cart_subtotal_matches_items():
    cart = make_cart()
    assert cart.total == rupees("3940.00")


def test_chain_composes():
    chain = MandateChain(intent=make_intent(), cart=make_cart(), payment=make_payment())
    assert chain.payment.amount <= chain.intent.max_amount


def test_visible_total_excludes_hidden_items():
    """The gap between visible_total and total is exactly what M-09 exploits."""
    items = [
        LineItem(sku="A", name="Shoes", price=rupees("3940.00"), qty=1),
        LineItem(sku="GC", name="Gift card", price=rupees("2000.00"), qty=1, visible=False),
    ]
    cart = make_cart(items=items, total=rupees("5940.00"))
    assert cart.visible_total() == rupees("3940.00")
    assert cart.total == rupees("5940.00")
    assert cart.has_hidden_items() is True


def test_nonces_are_unique():
    assert len({new_nonce() for _ in range(500)}) == 500


def test_expiry_is_timezone_aware():
    intent = make_intent()
    assert intent.expires_at.tzinfo is not None


def test_is_expired():
    past = datetime.now(UTC) - timedelta(seconds=1)
    assert make_intent(expires_at=past).is_expired() is True
    assert make_intent().is_expired() is False


def test_json_roundtrip_preserves_decimal():
    """Episodes are written to JSONL; a Decimal that returns as float is a bug."""
    chain = MandateChain(intent=make_intent(), cart=make_cart(), payment=make_payment())
    restored = MandateChain.model_validate_json(chain.model_dump_json())
    assert restored.payment.amount == chain.payment.amount
    assert isinstance(restored.payment.amount, Decimal)
