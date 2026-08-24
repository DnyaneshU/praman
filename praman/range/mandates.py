"""The mandate chain: Intent -> Cart -> Payment.

Three signed documents, each authorising the next. Nearly every attack in the
corpus is an attempt to break a link in this chain while keeping every
signature valid, so the models here carry the fields the invariant gate needs
to check the *relationships* between documents — not just the contents of one.

Shape follows AP2's documented mandate structure closely enough that the
"AP2-compatible" claim is defensible, without pretending to be an
implementation of it.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "LineItem",
    "IntentMandate",
    "CartMandate",
    "PaymentMandate",
    "MandateChain",
    "new_nonce",
    "new_id",
]


def new_nonce() -> str:
    """A single-use freshness token. Consumed atomically by the ledger."""
    return secrets.token_hex(16)


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


class _Money(BaseModel):
    """Base with the money guard every mandate needs."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _no_floats(cls, v):
        if isinstance(v, float):
            raise ValueError("float is not accepted for money; use Decimal paise")
        return v


class LineItem(_Money):
    sku: str
    name: str
    price: Decimal = Field(ge=0, description="paise")
    qty: int = Field(ge=1)
    category: str = "general"
    visible: bool = True
    """Whether this line appears in the summary shown to the user. M-09 sets it False."""

    def subtotal(self) -> Decimal:
        return self.price * self.qty


class _Mandate(_Money):
    mandate_id: str
    expires_at: datetime
    nonce: str
    signature: str | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at


class IntentMandate(_Mandate):
    """What the human actually authorised. Sets the ceiling for everything downstream."""

    principal: str
    description: str
    max_amount: Decimal = Field(ge=0, description="paise ceiling")
    allowed_categories: list[str] = Field(default_factory=list)


class CartMandate(_Mandate):
    """What the agent chose, signed by the merchant that issued it."""

    intent_id: str
    merchant_id: str
    items: list[LineItem]
    total: Decimal = Field(ge=0, description="paise, including hidden items")
    display_summary: str
    """What the user is shown. M-09 lives in the gap between this and `total`."""

    def visible_total(self) -> Decimal:
        return sum((i.subtotal() for i in self.items if i.visible), Decimal(0))

    def actual_total(self) -> Decimal:
        return sum((i.subtotal() for i in self.items), Decimal(0))

    def has_hidden_items(self) -> bool:
        return any(not i.visible for i in self.items)

    def categories(self) -> set[str]:
        return {i.category for i in self.items}


class PaymentMandate(_Mandate):
    """The instruction that actually moves funds."""

    cart_id: str
    beneficiary: str
    amount: Decimal = Field(ge=0, description="paise")


class MandateChain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentMandate
    cart: CartMandate
    payment: PaymentMandate

    def describe(self) -> str:
        return f"{self.intent.mandate_id} -> {self.cart.mandate_id} -> {self.payment.mandate_id}"
