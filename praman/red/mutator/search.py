"""Deterministic, defense-aware search over an attack grammar.

The control returns the rule it enforced. The search reads that and proposes
strategies aimed at *that rule*, so each round is an informed attempt rather
than random mutation. This is the "defense-aware attacker" the adaptive-
evaluation literature asks for, and it needs no model — which is why our
headline result reproduces on a judge's laptop with no credential.

Strategies are deliberately atomic. None of them is a complete bypass on its
own; the interesting variants are *combinations* discovered over rounds, which
is what makes this a search rather than a lookup table.

Some strategies do not work, and they stay in. A search that only contains
winning moves is a demo, not a search — and the dead ends are informative:
freshness turns out to be genuinely hard to evade, and that is worth reporting
alongside the checks that fall.
"""

from __future__ import annotations

from praman.blue.verdict import Verdict
from praman.range.context import ATTACKER_MERCHANT, COMPROMISED_MERCHANT, RangeContext
from praman.range.mandates import MandateChain, new_nonce
from praman.range.purchase import summarise
from praman.red.mutator.base import Mutator, Strategy, Variant, register, strategies_for

__all__ = ["SearchMutator"]

NEUTRAL_MERCHANT = "merchant_0102"
"""A real merchant the attacker does not control. Used by a strategy that
satisfies the rule and profits nothing — a genuine dead end."""


@register
class ReissueFromControlledMerchant(Strategy):
    """Stop fighting inv-02 and satisfy it: become the merchant.

    The rule says the money must go to whoever issued the cart. So issue the
    cart. The attacker operates a registered merchant and holds its key, so the
    re-signed chain is structurally impeccable — and the only thing wrong with
    it is a reputation score, which is not arithmetic.

    This is the finding that argues for Tier 2 existing at all.
    """

    id = "mut-reissue"
    targets = ("inv-02",)
    rationale = "issue the cart from a merchant we control"

    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        chain.cart.merchant_id = ATTACKER_MERCHANT
        ctx.sign_cart(chain.cart)
        chain.payment.cart_id = chain.cart.mandate_id
        chain.payment.beneficiary = ctx.merchant_vpa(ATTACKER_MERCHANT)
        ctx.sign_payment(chain.payment)
        return chain


@register
class AliasBeneficiaryVpa(Strategy):
    """A lookalike destination. Fails: the comparison is exact, not fuzzy."""

    id = "mut-alias"
    targets = ("inv-02",)
    rationale = "a lookalike VPA may pass a lax comparison"

    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        honest = ctx.merchant_vpa(chain.cart.merchant_id)
        chain.payment.beneficiary = honest.replace("@", ".@")
        ctx.sign_payment(chain.payment)
        return chain


@register
class RouteViaNeutralMerchant(Strategy):
    """Satisfies inv-02 and takes nothing — evasion without profit.

    Kept because the selector must be able to tell "got past the rule" from
    "got the money". A variant that passes every check and moves ₹0 is not a
    success, and the fitness function has to say so.
    """

    id = "mut-neutral"
    targets = ("inv-02",)
    rationale = "issue from any merchant at all"

    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        chain.cart.merchant_id = NEUTRAL_MERCHANT
        ctx.sign_cart(chain.cart)
        chain.payment.cart_id = chain.cart.mandate_id
        chain.payment.beneficiary = ctx.merchant_vpa(NEUTRAL_MERCHANT)
        ctx.sign_payment(chain.payment)
        return chain


@register
class RelabelCategory(Strategy):
    """inv-01 reads a category the attacker writes.

    The check compares the cart's declared categories against the intent's
    allowed list. On a cart the attacker signs, that declaration is attacker
    input — so relabel a gift voucher as footwear and the arithmetic agrees.

    The lesson is not that inv-01 is wrong; it is that a deterministic check
    over self-declared metadata inherits the trustworthiness of the declarer.
    """

    id = "mut-relabel"
    targets = ("inv-01",)
    rationale = "the category is metadata we write ourselves"

    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        allowed = chain.intent.allowed_categories
        if allowed:
            for item in chain.cart.items:
                item.category = allowed[0]
        ctx.sign_cart(chain.cart)
        ctx.sign_payment(chain.payment)
        return chain


@register
class UnhideButOmitFromSummary(Strategy):
    """inv-06 checks a flag; the user reads the text.

    Mark every line visible so `has_hidden_items()` is satisfied, then write a
    summary that mentions only the first one. The concealment survives intact
    because the invariant tests a proxy for the property rather than the
    property itself.
    """

    id = "mut-unhide"
    targets = ("inv-06",)
    rationale = "set the flag, keep the summary misleading"

    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        cart = chain.cart
        for item in cart.items:
            item.visible = True
        cart.display_summary = summarise(cart.items[:1])
        ctx.sign_cart(cart)
        ctx.sign_payment(chain.payment)
        return chain


@register
class RefreshNonces(Strategy):
    """Freshness has no cheap bypass, and we say so.

    Re-nonce the chain and inv-04 is satisfied — but the intent is signed by
    the *user*, whose key the attacker does not hold, so a re-nonced intent
    fails inv-05 instead. The attack simply moves which rule refuses it.

    A dead end, kept and reported. Deterministic freshness backed by an atomic
    store is the one Tier 1 check the search cannot get around.
    """

    id = "mut-renonce"
    targets = ("inv-04",)
    rationale = "a replay might pass with a fresh nonce"

    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        chain.intent.nonce = new_nonce()
        chain.payment.nonce = new_nonce()
        ctx.sign_payment(chain.payment)
        return chain


class SearchMutator(Mutator):
    """Propose variants aimed at the rule that just refused us.

    Deterministic: same blocked variant, same proposals, every time. That is
    what keeps a multi-round campaign reproducible from its seed.
    """

    name = "search"

    def __init__(self, branching: int | None = None) -> None:
        """`branching=None` tries every strategy aimed at the rule.

        A cap silently truncates the strategy list in registration order, which
        once hid `mut-compromised` — the one strategy that defeats Tier 2 —
        behind three that only defeat Tier 1. Explore everything by default and
        let the selector do the pruning.
        """
        self.branching = branching

    def mutate(self, variant: Variant, verdict: Verdict) -> list[Variant]:
        if verdict.allowed or verdict.invariant is None:
            return []
        fresh = [s for s in strategies_for(verdict.invariant) if s.id not in variant.strategies]
        if self.branching is not None:
            fresh = fresh[: self.branching]
        return [variant.extend(s) for s in fresh]


@register
class ReissueFromCompromisedMerchant(Strategy):
    """Reissue from an established merchant whose key we hold.

    The same idea as `mut-reissue`, moved upmarket. Where the mule merchant is
    eleven days old and unrated, this one has traded for two years with signed
    listings and a 0.86 reputation — so a control that learned "new and poorly
    rated means fraud" sees nothing at all.

    Kept precisely because it defeats Tier 2 rather than Tier 1. A range where
    every attacker looks disreputable would teach the model one merchant's
    score and let us report it as machine learning.
    """

    id = "mut-compromised"
    targets = ("inv-02",)
    rationale = "reissue from an established merchant we have compromised"

    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        chain.cart.merchant_id = COMPROMISED_MERCHANT
        ctx.sign_cart(chain.cart)
        chain.payment.cart_id = chain.cart.mandate_id
        chain.payment.beneficiary = ctx.merchant_vpa(COMPROMISED_MERCHANT)
        ctx.sign_payment(chain.payment)
        return chain
