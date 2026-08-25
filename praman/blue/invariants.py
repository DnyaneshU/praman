"""Tier 1 — deterministic arithmetic over the mandate chain.

The tempting build is a classifier that reads the chain and predicts "attack".
That is precisely the architecture the adaptive-attack literature demonstrates
collapsing: twelve published defenses of that shape, each reporting near-zero
attack success, most broken above 90% once the attacker could adapt.

So Tier 1 judges no language at all. It checks relationships — cart against
intent, payment against cart, freshness, arithmetic — and every check is
independent, named, and carries its own evidence. Explainability is not a
feature bolted on; the verdict *is* the rule that failed.

Two ordering rules the monitor depends on:

**Stateless before stateful.** `inv-04` consumes nonces. Running it before the
cheap checks would burn a nonce on a chain that was going to be refused anyway.

**One invariant per attack.** S-01..S-04 and M-08/M-09 are each caught by a
different check. If two attacks tripped the same one, one of them would be
telling us nothing about the control.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from decimal import Decimal

from praman.blue.verdict import Verdict
from praman.money import fmt, rupees
from praman.range.context import RangeContext
from praman.range.mandates import MandateChain

__all__ = ["Invariant", "INVARIANTS", "STATELESS", "STATEFUL"]


class Invariant(ABC):
    id: str
    rule: str
    """The rule in one line, phrased as it appears in the arena."""

    stateful: bool = False
    """True if checking mutates the range. Only inv-04 does."""

    @abstractmethod
    def check(self, chain: MandateChain, ctx: RangeContext) -> Verdict: ...

    def _block(self, observed: str, expected: str) -> Verdict:
        return Verdict.block(
            invariant=self.id, rule=self.rule, observed=observed, expected=expected
        )


class SignaturesValid(Invariant):
    """Every mandate is signed by the party that should have signed it.

    Cheapest and first: a forged chain is not worth reasoning about. In
    practice none of our attacks trip this — they all keep signatures valid,
    which is the whole point of the project.
    """

    id = "inv-05"
    rule = "every mandate in the chain must carry a valid signature"

    def check(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        checks = (
            ("intent", chain.intent, ctx.principal),
            ("cart", chain.cart, chain.cart.merchant_id),
            ("payment", chain.payment, ctx.principal),
        )
        for label, mandate, holder in checks:
            if not ctx.keyring.verify(mandate, holder):
                return self._block(
                    observed=f"{label}.signature invalid for {holder}",
                    expected=f"{label} signed by {holder}",
                )
        return Verdict.allow()


class NotExpired(Invariant):
    id = "inv-07"
    rule = "no mandate in the chain may be past its expiry"

    def check(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        for label, mandate in (
            ("intent", chain.intent),
            ("cart", chain.cart),
            ("payment", chain.payment),
        ):
            if mandate.is_expired():
                return self._block(
                    observed=f"{label} expired at {mandate.expires_at.isoformat()}",
                    expected=f"{label} still live",
                )
        return Verdict.allow()


class CartWithinIntent(Invariant):
    """The cart must serve the intent that authorised it.

    Catches S-01 (a gift card where shoes were authorised) and M-08, where a
    hidden instruction steers the agent outside the authorised category. A
    semantic attack still has to break the arithmetic to move money, which is
    why a deterministic check catches some of them.
    """

    id = "inv-01"
    rule = "cart must reference its intent and stay within the authorised categories"

    def check(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        intent, cart = chain.intent, chain.cart

        if cart.intent_id != intent.mandate_id:
            return self._block(
                observed=f"cart.intent_id {cart.intent_id}",
                expected=f"intent.mandate_id {intent.mandate_id}",
            )

        allowed = set(intent.allowed_categories)
        offending = sorted({i.category for i in cart.items} - allowed)
        if offending:
            return self._block(
                observed=f"cart contains {', '.join(offending)}",
                expected=f"only {', '.join(sorted(allowed))}",
            )
        return Verdict.allow()


class TotalUnderCeiling(Invariant):
    """Arithmetic: the cart adds up, and it stays under what the user allowed."""

    id = "inv-03"
    rule = "cart total must equal its line items and stay within the intent ceiling"

    def check(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        intent, cart, payment = chain.intent, chain.cart, chain.payment

        line_sum = sum((i.subtotal() for i in cart.items), Decimal(0))
        if cart.total != line_sum:
            return self._block(
                observed=f"cart.total {fmt(cart.total)}",
                expected=f"line items sum to {fmt(line_sum)}",
            )
        if cart.total > intent.max_amount:
            return self._block(
                observed=f"cart.total {fmt(cart.total)}",
                expected=f"at most {fmt(intent.max_amount)}",
            )
        if payment.amount != cart.total:
            return self._block(
                observed=f"payment.amount {fmt(payment.amount)}",
                expected=f"cart.total {fmt(cart.total)}",
            )
        return Verdict.allow()


class SummaryMatchesCharge(Invariant):
    """What the user was shown must be what the user is charged.

    Catches M-09. The cart is arithmetically sound, inside the ceiling, in the
    right category, correctly signed — and it quietly bills for a second pair
    of shoes the summary never mentioned.

    **Strengthened in response to the search.** The first version tested
    `has_hidden_items()` — a *flag on each line*. `mut-unhide` beat it in one
    round by setting every flag true and leaving the summary text untouched:
    the proxy was satisfied while the concealment survived intact.

    So this now checks the property itself. The summary states a total; that
    total must equal what the chain actually charges. A flag is something the
    attacker writes, and the rupee figure shown to the user is the thing that
    matters.
    """

    id = "inv-06"
    rule = "the total shown to the user must equal the total charged"

    _AMOUNT = re.compile(r"₹\s*([\d,]+(?:\.\d{2})?)")

    def check(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        cart = chain.cart
        shown = self._stated_total(cart.display_summary)

        if shown is None:
            return self._block(
                observed="summary states no total",
                expected=f"a stated total of {fmt(cart.total)}",
            )
        if shown != cart.total:
            return self._block(
                observed=f"{fmt(shown)} shown, {fmt(cart.total)} charged",
                expected=f"concealed charge of {fmt(cart.total - shown)}",
            )
        return Verdict.allow()

    @classmethod
    def _stated_total(cls, summary: str) -> Decimal | None:
        """The largest rupee figure in the summary — by construction, the total."""
        found = cls._AMOUNT.findall(summary)
        if not found:
            return None
        return max(rupees(value.replace(",", "")) for value in found)


class BeneficiaryBindsCartIssuer(Invariant):
    """Money goes to the merchant that issued the cart, and nobody else.

    Catches S-02 — one changed field, every signature still valid. This is the
    invariant the demo names on stage.
    """

    id = "inv-02"
    rule = "payment.beneficiary must equal the VPA of the merchant that issued the cart"

    def check(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        cart, payment = chain.cart, chain.payment

        if payment.cart_id != cart.mandate_id:
            return self._block(
                observed=f"payment.cart_id {payment.cart_id}",
                expected=f"cart.mandate_id {cart.mandate_id}",
            )

        issuer_vpa = ctx.merchant_vpa(cart.merchant_id)
        if payment.beneficiary != issuer_vpa:
            return self._block(
                observed=f"beneficiary {payment.beneficiary}",
                expected=f"{issuer_vpa} ({cart.merchant_id})",
            )
        return Verdict.allow()


class Freshness(Invariant):
    """One authorisation, one settlement.

    The only stateful check: it *consumes* the intent and payment nonces
    through the ledger's atomic primitive. Catches S-03, where three concurrent
    redemptions contend for the same authorisation and exactly one may win, and
    S-04, where a spent intent tries to authorise a second purchase.

    A chain that fails here is dead regardless, so a partially consumed pair is
    not worth unwinding.
    """

    id = "inv-04"
    rule = "an intent and a payment may each be redeemed once"
    stateful = True

    def check(self, chain: MandateChain, ctx: RangeContext) -> Verdict:
        for label, nonce in (
            ("intent", chain.intent.nonce),
            ("payment", chain.payment.nonce),
        ):
            if not ctx.ledger.redeem_nonce(nonce):
                return self._block(
                    observed=f"{label} nonce already redeemed",
                    expected=f"an unredeemed {label}",
                )
        return Verdict.allow()


INVARIANTS: tuple[Invariant, ...] = (
    SignaturesValid(),
    NotExpired(),
    CartWithinIntent(),
    TotalUnderCeiling(),
    SummaryMatchesCharge(),
    BeneficiaryBindsCartIssuer(),
    Freshness(),
)
"""Evaluation order. Cheap and stateless first; the consuming check last."""

STATELESS: tuple[Invariant, ...] = tuple(i for i in INVARIANTS if not i.stateful)
STATEFUL: tuple[Invariant, ...] = tuple(i for i in INVARIANTS if i.stateful)
