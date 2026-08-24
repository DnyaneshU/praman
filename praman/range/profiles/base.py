"""Rail profiles — the same engine, three payment worlds.

A profile decides two things: the shape of the mandates for that rail, and
which invariants apply to it. Everything downstream — the agent, the attacks,
the mutator, the metrics — is profile-agnostic. That is what lets the demo flip
from "fraud happening in India today" to "the rail NPCI is about to approve"
with one flag rather than a second codebase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

from praman.range.catalog import Task
from praman.range.mandates import IntentMandate, new_id, new_nonce

__all__ = ["RailProfile", "PROFILES", "get_profile"]


class RailProfile(ABC):
    name: str
    description: str

    #: Invariant ids Tier 1 enforces on this rail. Session 3 implements them.
    invariants: tuple[str, ...] = (
        "inv-01",  # cart stays inside the intent's constraints
        "inv-02",  # payment beneficiary is the merchant that issued the cart
        "inv-03",  # total under the ceiling
        "inv-04",  # nonce fresh and unconsumed
        "inv-05",  # every signature in the chain verifies
        "inv-06",  # nothing hidden from the user-facing summary
        "inv-07",  # nothing expired
    )

    #: Seconds a mandate stays valid on this rail.
    ttl_seconds: int = 1800

    @abstractmethod
    def build_intent(self, task: Task) -> IntentMandate:
        """Turn a shopping task into the rail's intent mandate."""

    def expiry(self, now: datetime | None = None) -> datetime:
        return (now or datetime.now(UTC)) + timedelta(seconds=self.ttl_seconds)


PROFILES: dict[str, type[RailProfile]] = {}


def register(cls: type[RailProfile]) -> type[RailProfile]:
    PROFILES[cls.name] = cls
    return cls


def get_profile(name: str) -> RailProfile:
    if name not in PROFILES:
        known = ", ".join(sorted(PROFILES)) or "none registered"
        raise KeyError(f"unknown rail profile {name!r}; known: {known}")
    return PROFILES[name]()


def _new_intent(task: Task, expires_at: datetime) -> IntentMandate:
    return IntentMandate(
        mandate_id=new_id("int"),
        principal=task.principal,
        description=task.description,
        max_amount=task.max_amount,
        allowed_categories=list(task.categories),
        expires_at=expires_at,
        nonce=new_nonce(),
    )
