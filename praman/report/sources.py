"""Every external claim in the report, and where it came from.

One registry, so a figure cannot appear in the document without a source
attached to it. `MARKET` carries the numbers; each entry names the `Source` it
came from, and `tests/test_sources.py` fails if any of them points at a
citation that does not exist.

This exists because of a near-miss. Two claims in an earlier draft overreached
the paper they cited — the abstract has RC-1..RC-5 and no RC-6, and no
model-tier breakdown at all — and a judge who followed the citation would have
found it. Anything we measured ourselves is marked `OURS` and is not in here;
anything in here is somebody else's number, quoted as theirs.

Nothing in this module is a forecast of our own. Where analysts disagree —
and on agentic commerce in 2030 they disagree by a factor of three — the
spread is reported rather than the most flattering member of it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Source", "SOURCES", "MARKET", "MarketFact", "cite"]


@dataclass(frozen=True)
class Source:
    key: str
    author: str
    title: str
    published: str
    url: str

    def reference(self) -> str:
        """One line, in the order a reference list reads."""
        return f"{self.author} ({self.published}). {self.title}. {self.url}"


@dataclass(frozen=True)
class MarketFact:
    """A number somebody else published, with the key of whoever published it."""

    label: str
    value: str
    source: str


# -- the protocols this project takes as its subject -------------------------

SOURCES: tuple[Source, ...] = (
    Source(
        "ap2",
        "Google Cloud",
        "Announcing the Agent Payments Protocol (AP2) — signed Intent, Cart and "
        "Payment mandates carried as W3C Verifiable Credentials; open licence, 60+ partners",
        "16 September 2025",
        "https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol",
    ),
    Source(
        "agentpay",
        "Mastercard",
        "Mastercard unveils Agent Pay — Agentic Tokens extending the Mastercard "
        "Digital Enablement Service to verified AI agents",
        "29 April 2025",
        "https://www.mastercard.com/global/en/news-and-trends/press/2025/april/mastercard-unveils-agent-pay-pioneering-agentic-payments-technology-to-power-commerce-in-the-age-of-ai.html",
    ),
    Source(
        "uap",
        "Business Standard",
        "India may allow agentic AI-led UPI transactions under new NPCI protocol — "
        "the Unified Agent Protocol, to register, verify and authorise AI agents "
        "across UPI without changing the underlying rails",
        "July 2026",
        "https://www.business-standard.com/finance/news/india-may-allow-agentic-ai-led-upi-transactions-under-new-npci-protocol-126070801343_1.html",
    ),
    # -- how big the thing being secured is expected to get ------------------
    Source(
        "juniper",
        "Juniper Research",
        "Agentic Commerce Market 2026–2031 — agentic commerce spend to reach "
        "$1.5tn in 2030, growing from pilot deployments in 2025 and 2026; "
        '"trust will remain the number one barrier to agentic commerce deployment"',
        "April 2026",
        "https://www.juniperresearch.com/press/agentic-commerce-set-to-generate-15-trillion-globally-by-2030-as-payments-infrastructure-leaders-revealed/",
    ),
    # Secondary: we read this in an aggregator, not in McKinsey's own
    # publication, and it is cited as what it is. A firm's homepage standing in
    # for a report URL is a citation a reader cannot check.
    Source(
        "mckinsey",
        "McKinsey & Company, as reported by Stellagent",
        "Global agentic commerce projected at $3tn–$5tn in revenue by 2030 — "
        "quoted here from secondary reporting, not from the original publication",
        "2026",
        "https://stellagent.ai/insights/agentic-commerce-market-size-forecast-2030",
    ),
    Source(
        "bain",
        "Bain & Company",
        "2030 forecast: how agentic AI will reshape US retail — US agentic commerce "
        "at $300bn–$500bn by 2030, roughly 15–25% of e-commerce",
        "2026",
        "https://www.bain.com/insights/2030-forecast-how-agentic-ai-will-reshape-us-retail-snap-chart/",
    ),
    Source(
        "bas",
        "Mordor Intelligence",
        "Breach and Attack Simulation Market — USD 1.29bn in 2026",
        "2026",
        "https://www.mordorintelligence.com/industry-reports/breach-and-attack-simulation-market",
    ),
    # -- the rail Praman models ----------------------------------------------
    Source(
        "npci",
        "National Payments Corporation of India, reported by ANI",
        "UPI hits new high in May 2026 with 23.2bn transactions worth ₹29.9tn",
        "June 2026",
        "https://www.aninews.in/news/business/upi-hits-new-high-in-may-2026-with-232-billion-transactions-worth-rs-299-trillion-npci-data-shows20260602155337/",
    ),
    Source(
        "i4c",
        "Ministry of Home Affairs / Indian Cyber Crime Coordination Centre, "
        "reported by ScamWatch HQ",
        "Indians lost an estimated ₹22,495 crore to cyber fraud in 2025",
        "2026",
        "https://scamwatchhq.com/india-scams-2026-digital-arrest-upi-fraud-epidemic/",
    ),
    Source(
        "upifraud",
        "Government of India data placed before Parliament, reported by The420.in",
        "UPI fraud of ₹805 crore across 10.64 lakh incidents to November FY26; "
        "₹981 crore across 12.64 lakh cases in FY25",
        "2026",
        "https://the420.in/india-upi-fraud-data-fy26-parliament-digital-payments/",
    ),
    # -- the security literature the design rests on -------------------------
    Source(
        "arxiv",
        "arXiv:2607.21824",
        "Protocol-Level Attacks on Agentic Commerce Platforms — root-cause classes "
        "RC-1 to RC-5, which this corpus adopts and extends",
        "2026",
        "https://arxiv.org/abs/2607.21824",
    ),
    Source(
        "anderson",
        "J. P. Anderson",
        "Computer Security Technology Planning Study — the reference monitor: "
        "tamper-proof, always invoked, small enough to analyse",
        "1972",
        "https://csrc.nist.gov/csrc/media/publications/conference-paper/1998/10/08/proceedings-of-the-21st-nissc-1998/documents/early-cs-papers/ande72.pdf",
    ),
    Source(
        "saltzer",
        "J. H. Saltzer and M. D. Schroeder",
        "The Protection of Information in Computer Systems — complete mediation, "
        "which is why the ledger refuses unmediated settlement",
        "1975",
        "https://www.cs.virginia.edu/~evans/cs551/saltzer/",
    ),
    Source(
        "vc",
        "W3C",
        "Verifiable Credentials Data Model — the credential format AP2 carries its mandates in",
        "2022",
        "https://www.w3.org/TR/vc-data-model/",
    ),
    Source(
        "lightgbm",
        "G. Ke et al., NeurIPS",
        "LightGBM: A Highly Efficient Gradient Boosting Decision Tree — the learned tier",
        "2017",
        "https://papers.nips.cc/paper/6907-lightgbm-a-highly-efficient-gradient-boosting-decision-tree",
    ),
    Source(
        "fawcett",
        "T. Fawcett, Pattern Recognition Letters",
        "An introduction to ROC analysis — the AUC convention used here, ties "
        "counted as half a win",
        "2006",
        "https://doi.org/10.1016/j.patrec.2005.10.010",
    ),
)

_BY_KEY = {s.key: s for s in SOURCES}


def cite(key: str) -> Source:
    return _BY_KEY[key]


# -- the market numbers, each attached to whoever published it ---------------

MARKET: tuple[MarketFact, ...] = (
    MarketFact("Agentic commerce spend, 2030", "$1.5 trillion", "juniper"),
    MarketFact("Same, McKinsey's estimate", "$3–5 trillion", "mckinsey"),
    MarketFact("US agentic commerce, 2030", "$300–500 billion", "bain"),
    MarketFact("Deployment status, 2025–26", "pilot deployments only", "juniper"),
    MarketFact("Named barrier to adoption", "trust, ranked first", "juniper"),
    MarketFact("UPI, May 2026", "23.2bn transactions, ₹29.9tn", "npci"),
    MarketFact("UPI fraud, FY25", "₹981 crore, 12.64 lakh cases", "upifraud"),
    MarketFact("Indian cyber fraud losses, 2025", "₹22,495 crore", "i4c"),
    MarketFact("Breach-and-attack-simulation market, 2026", "$1.29 billion", "bas"),
    MarketFact("Of which simulates payment mandates", "no vendor identified", "OURS"),
)
