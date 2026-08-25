"""What a control decides, and why.

This is the evidence emitter. It is a data structure rather than a module of
its own because the evidence *is* the verdict: a block that cannot name the
invariant it enforced is a bug, not a terse log line.

That matters beyond tidiness. Explainability is what India's FREE-AI framework
requires and what NPCI publicly asked for when it named consent-traceability as
the open problem. A Tier 1 verdict gets it for free — the reason a payment was
refused is the arithmetic that failed, stated in the same terms the mandate
uses.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Verdict"]


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    tier: int | None = None
    """Which tier decided. None for an allow that no tier objected to."""

    invariant: str | None = None
    """The rule that failed, e.g. "inv-02". Required whenever allowed is False."""
    rule: str | None = None
    """The rule in one line, as the arena displays it."""
    observed: str | None = None
    expected: str | None = None

    score: float | None = None
    """Tier 2/3 only. Tier 1 is arithmetic and has no score."""
    escalated: bool = False
    """Held for human review rather than refused outright. Tier 3 only.

    Kept distinct from a rule-based block because they are different claims: a
    rule says the chain is invalid, an escalation says a person should look."""
    features: dict[str, float] = Field(default_factory=dict)
    """Behavioural features extracted for this chain, recorded on the episode."""
    latency_ms: float = 0.0

    @classmethod
    def allow(cls, **kw) -> Verdict:
        return cls(allowed=True, **kw)

    @classmethod
    def block(
        cls,
        *,
        invariant: str,
        rule: str,
        observed: str,
        expected: str,
        tier: int = 1,
        **kw,
    ) -> Verdict:
        """A block must carry its evidence. The signature enforces that."""
        return cls(
            allowed=False,
            tier=tier,
            invariant=invariant,
            rule=rule,
            observed=observed,
            expected=expected,
            **kw,
        )

    @classmethod
    def escalate(cls, *, rule: str, observed: str, expected: str, tier: int = 3, **kw) -> Verdict:
        """Hold for review. Not allowed, but not a rule violation either."""
        return cls(
            allowed=False,
            escalated=True,
            tier=tier,
            invariant=f"tier-{tier}",
            rule=rule,
            observed=observed,
            expected=expected,
            **kw,
        )

    def reason(self) -> str:
        """One line, as spoken on stage: 'inv-02: payment.beneficiary must ...'."""
        if self.allowed:
            return "allowed"
        return f"{self.invariant}: {self.rule}"
