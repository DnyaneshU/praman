"""The adaptive loop — the property the whole submission rests on.

If adaptive attack success does not exceed static attack success, Praman is a
regression suite and the thesis is gone. That is asserted here, not inspected
on a chart.

The rest of this file pins the things that would let the headline number lie:
a mutator that ignores the rule it was told about, a selector that mistakes
"evaded the check" for "took the money", and a wrapper that silently flattens
a three-way race into one settlement.
"""

import pytest

from praman import metrics
from praman.blue import Defense
from praman.blue.verdict import Verdict
from praman.range.agent import ScriptedAgent
from praman.range.context import RangeContext
from praman.red.attacks import get_attack
from praman.red.campaign import run_adaptive_campaign
from praman.red.episode import Episode
from praman.red.executor import run_episode
from praman.red.mutator.base import STRATEGIES, Variant
from praman.red.mutator.search import SearchMutator
from praman.red.selector import Candidate, fitness, select


def blocked_by(invariant: str) -> Verdict:
    return Verdict.block(invariant=invariant, rule="", observed="", expected="")


def episode(**over) -> Episode:
    base = {
        "episode_id": "e",
        "attack_id": "S-02",
        "rail_profile": "autopay",
        "seed": 1,
        "outcome": "block",
    }
    return Episode(**{**base, **over})


# -- the gate ---------------------------------------------------------------


def test_adaptive_attack_success_exceeds_static():
    """The thesis, as an assertion.

    Round 0 is the documented attack against a control that knows it. Later
    rounds are the same attacker having read the rejection. The gap between
    them is the number nobody publishes for payment harm.
    """
    result = run_adaptive_campaign(rounds=5, seed=1729)
    static = metrics.static_asr(result.episodes)
    adaptive = metrics.adaptive_asr(result.episodes)

    assert adaptive > static, f"no adaptation: static {static:.1%}, adaptive {adaptive:.1%}"
    assert metrics.adaptive_delta(result.episodes) > 0
    assert metrics.rounds_to_break(result.episodes) is not None


def test_breakthroughs_are_reported_with_their_lineage():
    """A win we cannot describe is not a finding. The report quotes these."""
    result = run_adaptive_campaign(rounds=5, seed=1729)
    assert result.breakthroughs
    mutated = [v for v in result.breakthroughs if v.strategies]
    assert mutated, "nothing was broken *by adapting* — only pre-existing wins"
    assert all(str(v) for v in mutated)


def test_freshness_survives_the_search_and_we_say_so():
    """S-04 is the honest dead end.

    An atomic freshness check backed by a real store is the one Tier 1 rule the
    search cannot get around: re-noncing the intent breaks the user's signature
    instead. Reporting a rule that held beats implying every rule fell.
    """
    result = run_adaptive_campaign(rounds=5, seed=1729)
    broke = {v.attack_id for v in result.breakthroughs}
    assert "S-04" not in broke


def test_campaign_is_reproducible():
    a = run_adaptive_campaign(rounds=4, seed=1729)
    b = run_adaptive_campaign(rounds=4, seed=1729)
    assert [v.lineage for v in a.breakthroughs] == [v.lineage for v in b.breakthroughs]
    assert metrics.adaptive_delta(a.episodes) == metrics.adaptive_delta(b.episodes)


# -- the mutator ------------------------------------------------------------


def test_mutator_only_proposes_strategies_aimed_at_the_named_rule():
    """Defense-aware means informed by the rejection, not mutating blindly."""
    children = SearchMutator().mutate(Variant("S-02"), blocked_by("inv-02"))
    assert children
    for child in children:
        assert "inv-02" in STRATEGIES[child.strategies[-1]].targets


def test_mutator_proposes_nothing_for_an_allow():
    assert SearchMutator().mutate(Variant("S-02"), Verdict.allow()) == []


def test_mutator_never_reapplies_a_strategy_the_lineage_already_used():
    """Re-applying a strategy wastes a round and inflates the population."""
    parent = Variant("S-02", ("mut-reissue",))
    children = SearchMutator().mutate(parent, blocked_by("inv-02"))
    assert children
    newly_added = [c.strategies[-1] for c in children]
    assert "mut-reissue" not in newly_added
    assert all(c.strategies[:-1] == parent.strategies for c in children)


def test_mutator_is_deterministic():
    a = SearchMutator().mutate(Variant("S-01"), blocked_by("inv-01"))
    b = SearchMutator().mutate(Variant("S-01"), blocked_by("inv-01"))
    assert a == b


# -- the selector -----------------------------------------------------------


def test_money_outranks_progress():
    took_money = episode(outcome="allow", rupees_moved=1)
    got_further = episode(violated_invariant="inv-04")
    assert fitness(took_money) > fitness(got_further)


def test_evading_a_rule_without_profit_is_not_a_win():
    """`mut-neutral` satisfies inv-02 and takes ₹0. It must not rank as success."""
    evaded = Candidate(Variant("S-02", ("mut-neutral",)), episode(outcome="allow"))
    assert not evaded.succeeded


def test_progress_prefers_a_chain_the_control_thought_longer_about():
    early = Candidate(Variant("a"), episode(violated_invariant="inv-05"))
    late = Candidate(Variant("b"), episode(violated_invariant="inv-04"))
    assert select([early, late], keep=1)[0].variant.attack_id == "b"


# -- the wrapper ------------------------------------------------------------


@pytest.mark.parametrize(
    ("attack_id", "expected_chains"),
    [("S-03", 3), ("S-04", 2), ("S-02", 1)],
)
def test_mutation_preserves_each_attack_plan_shape(attack_id, expected_chains):
    """MutatedAttack delegates `plan` to the base class bound to itself.

    Get this wrong and S-03's three-way race quietly becomes one settlement,
    which would make the freshness check look far stronger than it is.
    """
    variant = Variant(attack_id, ("mut-relabel",))
    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        honest = ScriptedAgent().shop(ctx.catalog.task("task-shoes"), ctx)
        assert len(variant.build().plan(honest, ctx)) == expected_chains
    finally:
        ctx.ledger.close()


def test_mutation_preserves_attack_metadata():
    mutated = Variant("S-03", ("mut-relabel",)).build()
    base = get_attack("S-03")
    assert mutated.id == base.id
    assert mutated.concurrent is True
    assert mutated.redemptions == base.redemptions


def test_a_variant_rebuilds_identically_from_its_recipe():
    """Variants are recipes, not chains — that is what makes results portable."""
    recipe = Variant("S-02", ("mut-reissue",))
    runs = [
        run_episode(
            episode_id="v",
            attack=recipe.build(),
            task_id="task-shoes",
            seed=1729,
            defense=Defense(tiers=(1,)),
        ).rupees_moved
        for _ in range(2)
    ]
    assert runs[0] == runs[1] > 0
