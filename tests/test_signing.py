"""ECDSA P-256 over a canonical serialisation.

The attacks in this project all keep signatures valid while breaking the
*relationships* between documents. That only means something if tampering with
a signed document genuinely fails verification — which is what this file pins.
"""

from decimal import Decimal

import pytest

from praman.range.signing import Keyring, canonical_bytes
from tests.test_mandates import make_cart, make_intent, make_payment


@pytest.fixture
def ring() -> Keyring:
    r = Keyring()
    r.generate("user:asha")
    r.generate("merchant_0031")
    r.generate("attacker")
    return r


def test_sign_then_verify(ring):
    intent = make_intent()
    intent.signature = ring.sign(intent, "user:asha")
    assert ring.verify(intent, "user:asha") is True


def test_tampering_with_amount_breaks_verification(ring):
    intent = make_intent()
    intent.signature = ring.sign(intent, "user:asha")
    intent.max_amount = Decimal(999999)
    assert ring.verify(intent, "user:asha") is False


def test_tampering_with_any_field_breaks_verification(ring):
    cart = make_cart()
    cart.signature = ring.sign(cart, "merchant_0031")
    cart.merchant_id = "merchant_9999"
    assert ring.verify(cart, "merchant_0031") is False


def test_tampering_with_a_nested_line_item_breaks_verification(ring):
    """S-01 rewrites items; the signature must notice."""
    cart = make_cart()
    cart.signature = ring.sign(cart, "merchant_0031")
    cart.items[0].price = Decimal(1)
    assert ring.verify(cart, "merchant_0031") is False


def test_wrong_signer_fails(ring):
    payment = make_payment()
    payment.signature = ring.sign(payment, "attacker")
    assert ring.verify(payment, "merchant_0031") is False


def test_unsigned_mandate_does_not_verify(ring):
    assert ring.verify(make_intent(), "user:asha") is False


def test_canonical_bytes_exclude_the_signature(ring):
    """Otherwise signing would have to sign its own output."""
    intent = make_intent()
    before = canonical_bytes(intent)
    intent.signature = ring.sign(intent, "user:asha")
    assert canonical_bytes(intent) == before


def test_canonical_bytes_are_order_independent():
    a = make_intent(mandate_id="x", principal="user:asha")
    b = make_intent(principal="user:asha", mandate_id="x")
    b.nonce = a.nonce
    b.expires_at = a.expires_at
    assert canonical_bytes(a) == canonical_bytes(b)


def test_canonical_bytes_are_stable_across_calls():
    intent = make_intent()
    assert canonical_bytes(intent) == canonical_bytes(intent)


def test_decimal_serialises_without_float_drift():
    """A Decimal that canonicalises via float would break signatures at random."""
    cart = make_cart()
    raw = canonical_bytes(cart).decode()
    assert '"total":"394000"' in raw


def test_unknown_holder_raises(ring):
    with pytest.raises(KeyError):
        ring.sign(make_intent(), "nobody")
