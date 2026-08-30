"""Every external claim traces to a citation, and every citation is reachable.

This exists because of a near-miss. An earlier draft attributed two claims to
arXiv 2607.21824 that the paper does not make — its abstract has RC-1..RC-5
with no RC-6, and no model-tier breakdown at all. The paper was real, the
citation was real, and the claims were still wrong. A judge who followed the
reference would have found it before we did.

So: one registry, and a number cannot appear in the report without naming who
published it. `OURS` is the only value that means "nobody else — we measured
this", and it is spelled out rather than left blank, because a blank source
reads as an oversight and is indistinguishable from one.
"""

from __future__ import annotations

from praman.report.sources import MARKET, SOURCES, cite


def test_every_market_figure_names_a_real_source():
    keys = {s.key for s in SOURCES}
    for fact in MARKET:
        assert fact.source == "OURS" or fact.source in keys, (
            f"{fact.label!r} cites {fact.source!r}, which is not in SOURCES"
        )


def test_no_source_is_declared_twice():
    keys = [s.key for s in SOURCES]
    assert len(keys) == len(set(keys)), "duplicate citation key"


def test_every_source_is_complete_enough_to_follow():
    """A reference a reader cannot chase is decoration."""
    for source in SOURCES:
        assert source.author.strip(), f"{source.key} has no author"
        assert source.title.strip(), f"{source.key} has no title"
        assert source.published.strip(), f"{source.key} has no date"
        assert source.url.startswith("https://"), f"{source.key} has no resolvable URL"
        assert source.key in source.reference() or source.author in source.reference()


def test_the_protocols_the_project_is_about_are_all_cited():
    """AP2, Agent Pay and UAP are the reason the project exists."""
    for key in ("ap2", "agentpay", "uap"):
        assert cite(key).url.startswith("https://")


def test_the_security_literature_is_cited_not_just_alluded_to():
    """The design claims complete mediation and a reference monitor by name."""
    for key in ("anderson", "saltzer"):
        assert cite(key).published.isdigit(), f"{key} should carry a year"


def test_a_disputed_forecast_is_not_reported_as_settled():
    """Analysts differ on agentic commerce by a factor of three.

    Quoting only the largest would be picking the flattering end. Both the
    Juniper and the McKinsey figures have to be present for the spread to be
    visible to a reader.
    """
    labels = {fact.source for fact in MARKET}
    assert {"juniper", "mckinsey"} <= labels, "only one side of a disputed forecast is quoted"
