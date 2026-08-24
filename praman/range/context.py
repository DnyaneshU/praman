"""RangeContext — everything an episode needs, assembled in one place.

Built fresh per episode with a seeded RNG, so a campaign is reproducible from
its seed alone. Judges who can re-run our numbers score us differently from
judges who have to take them on trust.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from praman.money import rupees
from praman.range.catalog import FIXTURES_DIR, Catalog
from praman.range.ledger import Ledger
from praman.range.mandates import CartMandate, IntentMandate, MandateChain, PaymentMandate
from praman.range.profiles import RailProfile, get_profile
from praman.range.signing import Keyring

__all__ = [
    "RangeContext",
    "ATTACKER_VPA",
    "ATTACKER_MERCHANT",
    "DEFAULT_OPENING_BALANCE",
]

ATTACKER_VPA = "mule-vpa@axl"
"""A mule account. Where a rebound beneficiary sends money."""

ATTACKER_MERCHANT = "merchant_0777"
"""A registered merchant the attacker operates — eleven days old, reputation
0.42. Mule merchants are a real onboarding problem, and modelling one is what
lets an attack sign a cart with a key it legitimately holds."""

DEFAULT_OPENING_BALANCE = rupees(50000)


@dataclass
class RangeContext:
    keyring: Keyring
    ledger: Ledger
    catalog: Catalog
    profile: RailProfile
    rng: random.Random
    seed: int
    principal: str = "user:asha"
    attacker_vpa: str = ATTACKER_VPA

    @classmethod
    def build(
        cls,
        db_path: str | Path,
        profile: str = "autopay",
        seed: int = 1729,
        opening_balance: Decimal = DEFAULT_OPENING_BALANCE,
        fixtures: Path | str = FIXTURES_DIR,
    ) -> RangeContext:
        catalog = Catalog.load(fixtures)
        ledger = Ledger(db_path)
        keyring = Keyring()

        principal = "user:asha"
        keyring.generate(principal)
        ledger.open_account(principal, opening_balance)
        for merchant in catalog.merchants.values():
            keyring.generate(merchant.id)
            ledger.open_account(merchant.vpa, Decimal(0))
        keyring.generate("attacker")

        return cls(
            keyring=keyring,
            ledger=ledger,
            catalog=catalog,
            profile=get_profile(profile),
            rng=random.Random(seed),
            seed=seed,
            principal=principal,
        )

    # -- signing ------------------------------------------------------------

    def sign_intent(self, intent: IntentMandate) -> IntentMandate:
        intent.signature = self.keyring.sign(intent, self.principal)
        return intent

    def sign_cart(self, cart: CartMandate) -> CartMandate:
        cart.signature = self.keyring.sign(cart, cart.merchant_id)
        return cart

    def sign_payment(self, payment: PaymentMandate) -> PaymentMandate:
        payment.signature = self.keyring.sign(payment, self.principal)
        return payment

    def sign_chain(self, chain: MandateChain) -> MandateChain:
        self.sign_intent(chain.intent)
        self.sign_cart(chain.cart)
        self.sign_payment(chain.payment)
        return chain

    # -- convenience ---------------------------------------------------------

    def merchant_vpa(self, merchant_id: str) -> str:
        return self.catalog.merchant(merchant_id).vpa

    @property
    def attacker_accounts(self) -> tuple[str, ...]:
        """Every account the attacker controls. Harm is money reaching any of them."""
        return (self.attacker_vpa, self.merchant_vpa(ATTACKER_MERCHANT))

    def harm(self) -> Decimal:
        """Rupees that reached the attacker. The only harm figure we report."""
        return sum(
            (self.ledger.total_moved_to(account) for account in self.attacker_accounts),
            Decimal(0),
        )
