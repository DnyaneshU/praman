"""The ledger is the only authority on harm.

Two properties carry the whole project:
  1. Money is conserved — no settlement invents or destroys rupees.
  2. Nonce redemption is atomic under genuine concurrency, not simulated.

The second is the substrate for S-03 (double redemption). If it were faked, the
attack would be theatre and the defense against it would prove nothing.
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest

from praman.money import rupees
from praman.range.ledger import Ledger
from tests.test_mandates import make_payment


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    lg = Ledger(tmp_path / "range.db")
    lg.open_account("user:asha", rupees(50000))
    lg.open_account("merchant_0031@bank", rupees(0))
    return lg


def test_open_account_and_balance(ledger):
    assert ledger.balance("user:asha") == rupees(50000)


def test_settle_moves_money(ledger):
    result = ledger.settle(make_payment(), source="user:asha")
    assert result.settled is True
    assert ledger.balance("user:asha") == rupees("46060.00")
    assert ledger.balance("merchant_0031@bank") == rupees("3940.00")


def test_settle_conserves_total(ledger):
    before = sum(ledger.snapshot().values(), Decimal(0))
    ledger.settle(make_payment(), source="user:asha")
    after = sum(ledger.snapshot().values(), Decimal(0))
    assert before == after


def test_settle_to_unknown_beneficiary_creates_it(ledger):
    """Attacker VPAs are never pre-opened. Money must still be traceable."""
    payment = make_payment(beneficiary="mule-vpa@axl")
    ledger.settle(payment, source="user:asha")
    assert ledger.balance("mule-vpa@axl") == rupees("3940.00")


def test_insufficient_funds_is_refused_with_a_reason(ledger):
    payment = make_payment(amount=rupees(999999))
    result = ledger.settle(payment, source="user:asha")
    assert result.settled is False
    assert result.reason is not None
    assert ledger.balance("user:asha") == rupees(50000)


def test_total_moved_to(ledger):
    ledger.settle(make_payment(beneficiary="mule-vpa@axl"), source="user:asha")
    ledger.settle(
        make_payment(mandate_id="pay-002", beneficiary="mule-vpa@axl"), source="user:asha"
    )
    assert ledger.total_moved_to("mule-vpa@axl") == rupees("7880.00")


def test_redeem_nonce_once(ledger):
    assert ledger.redeem_nonce("n-1") is True
    assert ledger.redeem_nonce("n-1") is False


def test_redeem_nonce_is_atomic_under_real_concurrency(ledger):
    """S-03's substrate. Twelve threads, one nonce, exactly one winner.

    A barrier forces them to arrive together, so this contends for real rather
    than serialising by accident.
    """
    workers = 12
    barrier = Barrier(workers)

    def attempt(_: int) -> bool:
        barrier.wait()
        return ledger.redeem_nonce("contested")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(attempt, range(workers)))

    assert sum(results) == 1, f"expected exactly one winner, got {sum(results)}"


def test_concurrent_settles_never_overdraw(ledger):
    """Balance checks and debits must share one transaction."""
    ledger.open_account("thin", rupees(1000))
    workers = 10
    barrier = Barrier(workers)

    def attempt(i: int):
        barrier.wait()
        return ledger.settle(
            make_payment(mandate_id=f"pay-{i}", amount=rupees(200), beneficiary="sink"),
            source="thin",
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(attempt, range(workers)))

    settled = [r for r in results if r.settled]
    assert len(settled) == 5
    assert ledger.balance("thin") == rupees(0)
    assert ledger.balance("sink") == rupees(1000)


def test_settle_does_not_consume_the_nonce(ledger):
    """Deliberate: the ledger offers atomicity, the *control* decides to use it.

    If settle consumed nonces itself, S-03 would be impossible undefended and
    Tier 1's inv-04 would be measuring nothing.
    """
    payment = make_payment()
    ledger.settle(payment, source="user:asha")
    assert ledger.redeem_nonce(payment.nonce) is True


def test_transactions_are_recorded(ledger):
    ledger.settle(make_payment(), source="user:asha")
    txns = ledger.transactions()
    assert len(txns) == 1
    assert txns[0]["beneficiary"] == "merchant_0031@bank"
    assert txns[0]["amount"] == rupees("3940.00")
