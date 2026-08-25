"""The ledger — the only authority on whether harm occurred.

Every claim Praman makes about a defense is ultimately "this many rupees did or
did not reach an attacker-controlled account." No model, scorer or heuristic
gets a say in that; it is read off these tables.

Two deliberate design choices, both load-bearing:

**stdlib sqlite3 with explicit `BEGIN IMMEDIATE`, no ORM.** S-03 is a
token-redemption race. An ORM that hides the transaction boundary would turn a
genuine concurrency finding into a simulated one, so the boundary stays visible
in the source.

**`settle()` does not consume the payment nonce.** The ledger *offers*
`redeem_nonce()` as an atomic primitive; whether a control calls it is exactly
what is under test. Auto-consuming here would make S-03 impossible undefended
and leave Tier 1's `inv-04` measuring nothing. Do not "fix" this.

Balances are integer paise, so SQL arithmetic is exact and a debit can be a
single atomic `UPDATE`.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praman.range.mandates import PaymentMandate

__all__ = ["Ledger", "SettlementResult", "UnmediatedSettlement"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id      TEXT PRIMARY KEY,
    balance INTEGER NOT NULL CHECK (balance >= 0)
);
CREATE TABLE IF NOT EXISTS redemptions (
    nonce       TEXT PRIMARY KEY,
    redeemed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mandate_id  TEXT NOT NULL,
    source      TEXT NOT NULL,
    beneficiary TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    settled_at  TEXT NOT NULL
);
"""


class UnmediatedSettlement(RuntimeError):
    """Raised when something tries to settle without going through the monitor.

    This is what makes "out-of-band" an enforced property rather than a claim
    on a slide: once a monitor is attached, the ledger refuses any settlement
    it did not approve, no matter who is calling.
    """


class SettlementResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settled: bool
    amount: Decimal
    beneficiary: str
    reason: str | None = None


class Ledger:
    """A tiny double-entry ledger over SQLite.

    Connections are thread-local: the concurrency tests are real, so the
    connections behind them have to be too.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._local = threading.local()
        self._registry: list[sqlite3.Connection] = []
        self._registry_lock = threading.Lock()
        self._mediator: object | None = None
        self._connect().executescript(_SCHEMA)

    # -- connection handling -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            # check_same_thread=False so close() can reclaim a worker thread's
            # connection from the main thread. Each connection is still *used*
            # by exactly one thread — only teardown crosses the boundary.
            conn = sqlite3.connect(
                self.path, timeout=30.0, isolation_level=None, check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
            with self._registry_lock:
                self._registry.append(conn)
        return conn

    def close(self) -> None:
        """Close every connection this ledger opened, on any thread.

        Windows will not delete a file that still has an open handle, so a
        ledger left open makes temp-directory cleanup fail. Closing only the
        calling thread's connection is not enough after a concurrency test.

        Failures are not swallowed: a connection that will not close is a
        resource leak, and hiding it here cost an afternoon once already.
        """
        with self._registry_lock:
            connections, self._registry = self._registry, []
        self._local = threading.local()
        for conn in connections:
            conn.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- accounts ------------------------------------------------------------

    def open_account(self, account_id: str, balance: Decimal = Decimal(0)) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT OR IGNORE INTO accounts (id, balance) VALUES (?, ?)",
            (account_id, int(balance)),
        )

    def balance(self, account_id: str) -> Decimal:
        row = (
            self._connect()
            .execute("SELECT balance FROM accounts WHERE id = ?", (account_id,))
            .fetchone()
        )
        return Decimal(row["balance"]) if row else Decimal(0)

    def snapshot(self) -> dict[str, Decimal]:
        rows = self._connect().execute("SELECT id, balance FROM accounts").fetchall()
        return {r["id"]: Decimal(r["balance"]) for r in rows}

    # -- freshness -----------------------------------------------------------

    def redeem_nonce(self, nonce: str) -> bool:
        """Consume a nonce. Returns True exactly once across all callers and threads.

        The PRIMARY KEY does the work: a second INSERT raises IntegrityError
        rather than racing on a read-then-write.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO redemptions (nonce, redeemed_at) VALUES (?, ?)",
                (nonce, datetime.now(UTC).isoformat()),
            )
            conn.execute("COMMIT")
            return True
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return False
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # -- mediation -----------------------------------------------------------

    def require_mediation(self, monitor) -> None:
        """Refuse any settlement this monitor has not approved.

        Attached by the monitor itself at construction. Detaching is not
        offered: a control you can turn off from inside the range is not a
        control.
        """
        self._mediator = monitor

    # -- settlement ----------------------------------------------------------

    def settle(self, payment: PaymentMandate, source: str) -> SettlementResult:
        """Move `payment.amount` from `source` to `payment.beneficiary`, atomically.

        The balance check and both updates share one `BEGIN IMMEDIATE`
        transaction, so concurrent settlements cannot overdraw.
        """
        if self._mediator is not None and not self._mediator.approves(payment.mandate_id):
            raise UnmediatedSettlement(
                f"payment {payment.mandate_id} reached the ledger without a verdict"
            )
        amount = int(payment.amount)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute("SELECT balance FROM accounts WHERE id = ?", (source,)).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return SettlementResult(
                    settled=False,
                    amount=payment.amount,
                    beneficiary=payment.beneficiary,
                    reason=f"no such account: {source}",
                )
            if row["balance"] < amount:
                conn.execute("ROLLBACK")
                return SettlementResult(
                    settled=False,
                    amount=payment.amount,
                    beneficiary=payment.beneficiary,
                    reason="insufficient funds",
                )

            # Money leaving to an account we have never seen is normal here —
            # attacker-controlled VPAs are never pre-opened.
            conn.execute(
                "INSERT OR IGNORE INTO accounts (id, balance) VALUES (?, 0)",
                (payment.beneficiary,),
            )
            conn.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (amount, source))
            conn.execute(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                (amount, payment.beneficiary),
            )
            conn.execute(
                "INSERT INTO transactions (mandate_id, source, beneficiary, amount, settled_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    payment.mandate_id,
                    source,
                    payment.beneficiary,
                    amount,
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        return SettlementResult(
            settled=True, amount=payment.amount, beneficiary=payment.beneficiary
        )

    # -- reporting -----------------------------------------------------------

    def total_moved_to(self, beneficiary: str) -> Decimal:
        row = (
            self._connect()
            .execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM transactions WHERE beneficiary = ?",
                (beneficiary,),
            )
            .fetchone()
        )
        return Decimal(row["total"])

    def transactions(self) -> list[dict]:
        rows = (
            self._connect()
            .execute(
                "SELECT mandate_id, source, beneficiary, amount, settled_at"
                " FROM transactions ORDER BY id"
            )
            .fetchall()
        )
        return [
            {
                "mandate_id": r["mandate_id"],
                "source": r["source"],
                "beneficiary": r["beneficiary"],
                "amount": Decimal(r["amount"]),
                "settled_at": r["settled_at"],
            }
            for r in rows
        ]
