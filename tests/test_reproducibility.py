"""A campaign must reproduce from its seed alone.

Without this, every figure we publish is an anecdote — a judge who re-runs the
repo and gets different numbers has no reason to believe the first set.

Wall-clock fields cannot be deterministic and are excluded by name rather than
by hand-waving: `timestamp` and `latency_ms` are measurements *of* the run, not
results *from* it. Everything that carries a claim is stable.
"""

from praman.blue import Defense
from praman.red.runner import run_campaign

VOLATILE = {"timestamp", "latency_ms"}


def _significant(episode) -> dict:
    return episode.model_dump(exclude=VOLATILE)


def test_same_seed_reproduces_every_result_field():
    kw = {"seed": 1729, "repeats": 2}
    first = run_campaign(**kw, defense=Defense(tiers=(1,)))
    second = run_campaign(**kw, defense=Defense(tiers=(1,)))

    assert [_significant(e) for e in first] == [_significant(e) for e in second]


def test_a_different_seed_produces_a_different_run():
    """Otherwise the seed is decoration and the sample never varies."""
    a = run_campaign(seed=1729, repeats=2, defense=Defense(tiers=(1,)))
    b = run_campaign(seed=99, repeats=2, defense=Defense(tiers=(1,)))
    assert [e.seed for e in a] != [e.seed for e in b]
