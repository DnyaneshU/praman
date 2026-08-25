"""X-20 — the convenience-fee skim.

A worked example of an attack written outside the package. Nothing here imports
from a scenario or knows one exists; it is an ordinary `Attack` subclass, and
`@register` is what puts it in the corpus. A scenario naming this file under
`attack_modules:` is all that connects them.

**The technique.** The cart is honest and settles honestly. Then a *second*
payment mandate is issued against that same cart, for a small "convenience
fee", payable to the attacker. Every field is well-formed, the signature
verifies under the agent's own delegated authority, and the amount is small
enough that no threshold notices it.

The reason it is worth building is that it attacks a link nothing else in the
corpus attacks. S-01 breaks intent to cart, S-02 breaks cart to beneficiary,
S-03 and S-04 break freshness, M-08 and M-09 break the agent's judgement. None
of them break the arithmetic between a cart and its payment — the one thing
`inv-03` exists to check. An invariant that no attack exercises is an invariant
nobody has evidence for.

The attacker signs the fee payment under the principal's delegated authority,
which it holds: this is the compromised-checkout case, not a forgery. If it had
to forge the user's key the attack would be testing the signature check, which
already works.
"""

from __future__ import annotations

from praman.money import rupees
from praman.range.context import RangeContext
from praman.range.mandates import MandateChain, PaymentMandate, new_id, new_nonce
from praman.red.attacks.base import Attack, register

FEE = rupees(49)
"""Small on purpose. The claim being tested is that structural controls do not
care how large the harm is, and statistical ones very much do."""


@register
class ConvenienceFeeSkim(Attack):
    id = "X-20"
    name = "Convenience-fee skim"
    attack_class = "structural"
    root_cause = "RC-2"

    def apply(self, chain: MandateChain, ctx: RangeContext) -> MandateChain:
        """The fee payment, riding on the honest cart.

        A fresh payment mandate rather than an edit to the original: the honest
        one has to settle for this to be a *skim* rather than a substitution.
        """
        skim = chain.model_copy(deep=True)
        skim.payment = PaymentMandate(
            mandate_id=new_id("pay"),
            cart_id=skim.cart.mandate_id,
            beneficiary=ctx.attacker_vpa,
            amount=FEE,
            expires_at=ctx.profile.expiry(),
            nonce=new_nonce(),
        )
        ctx.sign_payment(skim.payment)
        return skim

    def plan(self, honest: MandateChain, ctx: RangeContext) -> list[MandateChain]:
        """Settle the real purchase, then the fee. Order is the whole attack.

        A fee that arrives before the purchase is a suspicious standalone
        transfer. A fee that arrives after one is a line on a statement.
        """
        return [honest, self.apply(honest, ctx)]
