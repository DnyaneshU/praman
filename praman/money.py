"""Money handling for the range.

The internal unit is **paise**, held as a `Decimal` with a zero exponent. Rupees
exist only at the edges — parsing input and formatting output.

Floats are rejected rather than converted. Praman's central claim is a rupee
figure read off a ledger, so an amount that drifts by a paise is not a rounding
annoyance, it is a wrong headline number.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

__all__ = ["rupees", "paise", "fmt", "PAISE_PER_RUPEE"]

PAISE_PER_RUPEE = Decimal(100)


def rupees(amount: str | int | Decimal) -> Decimal:
    """Convert a rupee amount to paise.

    >>> rupees("3940.50")
    Decimal('394050')

    Accepts str, int or Decimal. Rejects float outright — see module docstring.
    """
    if isinstance(amount, float):
        raise TypeError(
            f"float is not accepted for money (got {amount!r}); "
            'pass a string like "3940.50", an int, or a Decimal'
        )
    if isinstance(amount, bool):  # bool is an int subclass; catch it early
        raise TypeError("bool is not a money amount")

    try:
        value = Decimal(amount)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not a valid money amount: {amount!r}") from exc

    if not value.is_finite():
        raise ValueError(f"money must be finite, got {amount!r}")
    if value < 0:
        raise ValueError(f"money must not be negative, got {amount!r}")
    if value.as_tuple().exponent < -2:
        raise ValueError(f"money is precise to paise only, got {amount!r}")

    return (value * PAISE_PER_RUPEE).quantize(Decimal(1))


def paise(value: int | Decimal) -> Decimal:
    """Wrap an amount already expressed in paise."""
    if isinstance(value, float):
        raise TypeError("float is not accepted for money")
    result = Decimal(value)
    if result != result.to_integral_value():
        raise ValueError(f"paise must be a whole number, got {value!r}")
    if result < 0:
        raise ValueError(f"money must not be negative, got {value!r}")
    return result.quantize(Decimal(1))


def _group_indian(digits: str) -> str:
    """Group digits the Indian way: last three, then pairs. 1234567 -> 12,34,567."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join([*parts, tail])


def fmt(amount_paise: Decimal) -> str:
    """Format paise as rupees with Indian digit grouping.

    >>> fmt(Decimal(394050))
    '₹3,940.50'
    """
    whole, fraction = divmod(int(amount_paise), 100)
    return f"₹{_group_indian(str(whole))}.{fraction:02d}"
