"""Money is paise, always Decimal, never float.

Every rupee figure Praman reports comes through here. A float anywhere in this
path would make ledger totals drift, and the whole harm claim rests on those
totals being exact.
"""

from decimal import Decimal

import pytest

from praman.money import fmt, rupees


def test_rupees_from_string_with_paise():
    assert rupees("3940.50") == Decimal(394050)


def test_rupees_from_whole_int():
    assert rupees(4000) == Decimal(400000)


def test_rupees_smallest_unit():
    assert rupees("0.01") == Decimal(1)


def test_rupees_zero():
    assert rupees(0) == Decimal(0)


def test_rupees_rejects_float():
    """Floats are banned at the door, not rounded silently."""
    with pytest.raises(TypeError):
        rupees(3940.50)


def test_rupees_rejects_negative():
    with pytest.raises(ValueError):
        rupees("-1.00")


def test_rupees_rejects_sub_paise_precision():
    with pytest.raises(ValueError):
        rupees("10.005")


def test_fmt_thousands():
    assert fmt(Decimal(394050)) == "₹3,940.50"


def test_fmt_indian_lakh_grouping():
    """2,84,000 — not 284,000. Indian grouping, because the audience is Indian."""
    assert fmt(rupees(284000)) == "₹2,84,000.00"


def test_fmt_crore_grouping():
    assert fmt(rupees(12345678)) == "₹1,23,45,678.00"


def test_fmt_small():
    assert fmt(Decimal(1)) == "₹0.01"


def test_roundtrip_is_exact_over_many_additions():
    """A thousand additions of 0.01 must be exactly 10.00, which floats fail."""
    total = Decimal(0)
    for _ in range(1000):
        total += rupees("0.01")
    assert total == rupees("10.00")
