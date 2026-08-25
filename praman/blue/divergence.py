"""Tier 3 — does the cart resemble what it claims to be?

The residual after Tier 1 and Tier 2: every rule satisfied, the statistics
unremarkable, and the action still not the one the principal wanted.

Session 4's search produced exactly one attack of that shape that survives a
strengthened Tier 1. `mut-relabel` files a gift voucher under "footwear" so
inv-01's arithmetic agrees — the category is a field the attacker writes, and
the product name is not. The two disagreeing is the tell.

**Tier 3 escalates; it does not decide.** The research consensus is that
verification alone does not close the intent-alignment gap without a human, so
a divergent chain is held for review rather than refused. That is the FREE-AI
human-in-the-loop requirement satisfied by design, and episodes record it
separately from a rule-based block so the two never blur in a report.

**What this deliberately does not attempt.** Comparing the intent's natural
language to a product name — "buy running shoes under 4000" against "Road
Runner 7" — needs embeddings. Those two share no tokens at all, so a lexical
attempt rated every honest purchase as divergent and dropped benign pass rate
to 0%. That is measured, not assumed. Until an embedding backend is wired in,
the comparison is left undone rather than done badly, and the ceiling is stated
in the report instead of hidden in a good-looking number.
"""

from __future__ import annotations

import re

from praman.blue.verdict import Verdict
from praman.range.mandates import MandateChain

__all__ = ["DivergenceTier", "CATEGORY_WORDS"]

_TOKEN = re.compile(r"[a-z0-9]+")

CATEGORY_WORDS: dict[str, frozenset[str]] = {
    "footwear": frozenset(
        {
            "shoe",
            "shoes",
            "runner",
            "running",
            "trainer",
            "kick",
            "kicks",
            "court",
            "marathon",
            "sneaker",
            "boot",
            "grip",
        }
    ),
    "giftcard": frozenset({"gift", "voucher", "prepaid", "card"}),
}
"""A small lexicon, not a model.

Tier 3 needs to notice that "Instant Gift Voucher 3500" is not footwear, and a
dozen keywords answer that exactly and deterministically."""


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) > 2}


class DivergenceTier:
    """Escalates a cart whose contents do not resemble how they are filed."""

    tier = 3

    def check(self, chain: MandateChain) -> Verdict:
        mislabelled = self._mislabelled(chain)
        if mislabelled is None:
            return Verdict.allow(tier=self.tier, score=0.0)

        name, declared, looks_like = mislabelled
        return Verdict.escalate(
            rule="item does not resemble the category it is filed under",
            observed=f'"{name}" declared {declared}',
            expected=f"reads as {looks_like}",
            tier=self.tier,
            score=1.0,
        )

    @staticmethod
    def _mislabelled(chain: MandateChain) -> tuple[str, str, str] | None:
        for item in chain.cart.items:
            words = _tokens(item.name)
            for category, keywords in CATEGORY_WORDS.items():
                if words & keywords and category != item.category:
                    return item.name, item.category, category
        return None
