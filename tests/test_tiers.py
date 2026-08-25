"""Tiers 2 and 3 — and the two ways they could quietly be worthless.

A learned tier can look perfect by blocking everything, and a semantic tier can
look perfect by escalating everything. Both failures produce a headline ASR of
zero, and both are caught here by checking honest traffic in the same breath as
attack traffic. That is not belt-and-braces: the first version of Tier 3 shipped
a 100% prevention rate and a **0% benign pass rate**, and only the benign check
found it.
"""

import pytest

from praman import metrics
from praman.blue.anomaly import AnomalyTier
from praman.blue.defense import Defense
from praman.blue.divergence import DivergenceTier
from praman.blue.features import FEATURE_NAMES, extract
from praman.blue.invariants import INVARIANTS
from praman.blue.training import gather_training_set
from praman.range.agent import ScriptedAgent
from praman.range.catalog import Catalog
from praman.range.context import RangeContext
from praman.range.profiles import PROFILES, get_profile
from praman.red.campaign import run_adaptive_campaign
from praman.red.executor import run_episode
from praman.red.mutator.base import Variant
from praman.red.runner import run_campaign

TASKS = ("task-shoes", "task-trainer", "task-budget", "task-premium")


@pytest.fixture(scope="module")
def training_set():
    return gather_training_set(replicates=3)


@pytest.fixture(scope="module")
def trained(training_set) -> AnomalyTier:
    tier = AnomalyTier()
    tier.train(training_set)
    return tier


# -- the gate ---------------------------------------------------------------


def test_a_tier_that_learned_from_red_beats_one_that_did_not(trained):
    """The loop, as an assertion: Tier 2 trains on what Tier 1 let through."""
    tier1 = run_adaptive_campaign(rounds=4, seed=1729, defense=Defense(tiers=(1,)))
    learned = run_adaptive_campaign(
        rounds=4, seed=1729, defense=Defense(tiers=(1, 2), anomaly=trained)
    )
    assert metrics.adaptive_asr(learned.episodes) < metrics.adaptive_asr(tier1.episodes)
    assert metrics.rupees_moved(learned.episodes) < metrics.rupees_moved(tier1.episodes)


@pytest.mark.parametrize("task_id", TASKS)
def test_honest_traffic_still_passes_every_tier(trained, task_id):
    """The check that caught Tier 3 escalating 100% of honest purchases."""
    episode = run_episode(
        episode_id="b",
        attack=None,
        task_id=task_id,
        seed=1729,
        defense=Defense(tiers=(1, 2, 3), anomaly=trained),
    )
    assert episode.outcome == "allow", f"{task_id} blocked by {episode.violated_invariant}"


# -- Tier 2 -----------------------------------------------------------------


def test_untrained_tier2_abstains_rather_than_guessing():
    """An untrained tier that blocked would poison every comparison in the report."""
    tier = AnomalyTier()
    assert tier.trained is False
    assert tier.check({name: 0.0 for name in FEATURE_NAMES}).allowed


def test_tier2_refuses_to_train_on_a_single_class(training_set):
    """All-positive data yields a model that blocks everything and scores 100%."""
    winners = [e for e in training_set if e.succeeded]
    with pytest.raises(ValueError, match="single-class"):
        AnomalyTier().train(winners)


def test_tier2_refuses_to_train_on_nothing():
    with pytest.raises(ValueError, match="no allowed episodes"):
        AnomalyTier().train([])


def test_tier2_survives_a_save_and_load_roundtrip(trained, tmp_path, training_set):
    path = tmp_path / "t2.lgb"
    trained.save(path)
    reloaded = AnomalyTier()
    reloaded.load(path)
    sample = training_set[0].features
    assert reloaded.score(sample) == pytest.approx(trained.score(sample))


def test_features_include_relational_signals():
    """Absolute features alone memorise merchant identity — see features.py."""
    assert {"reputation_vs_best", "chosen_is_top_ranked", "price_vs_best_available"} <= set(
        FEATURE_NAMES
    )


def test_an_honest_purchase_scores_as_the_top_ranked_choice():
    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        chain = ScriptedAgent().shop(ctx.catalog.task("task-shoes"), ctx)
        features = extract(chain, ctx)
        assert features["chosen_is_top_ranked"] == 1.0
        assert features["reputation_vs_best"] == pytest.approx(0.0)
    finally:
        ctx.ledger.close()


# -- Tier 3 -----------------------------------------------------------------


def test_tier3_escalates_a_mislabelled_item():
    """mut-relabel files a gift voucher under footwear so inv-01 agrees."""
    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        honest = ScriptedAgent().shop(ctx.catalog.task("task-shoes"), ctx)
        chain = Variant("S-01", ("mut-relabel",)).build().apply(honest, ctx)
        verdict = DivergenceTier().check(chain)
        assert verdict.allowed is False
        assert verdict.escalated is True
        assert verdict.tier == 3
    finally:
        ctx.ledger.close()


def test_tier3_leaves_an_honest_cart_alone():
    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        chain = ScriptedAgent().shop(ctx.catalog.task("task-shoes"), ctx)
        assert DivergenceTier().check(chain).allowed
    finally:
        ctx.ledger.close()


def test_escalation_is_recorded_separately_from_a_rule_block():
    """A rule says the chain is invalid; an escalation says a person should look."""
    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        honest = ScriptedAgent().shop(ctx.catalog.task("task-shoes"), ctx)
        chain = Variant("S-01", ("mut-relabel",)).build().apply(honest, ctx)
        assert DivergenceTier().check(chain).escalated
        assert not INVARIANTS[0].check(chain, ctx).escalated
    finally:
        ctx.ledger.close()


# -- inv-06, strengthened ---------------------------------------------------


def test_inv06_now_checks_the_stated_total_not_a_flag():
    """mut-unhide beat the flag version by setting every flag true.

    The invariant now compares the total the summary states against the total
    actually charged, which is the property rather than a proxy for it.
    """
    episode = run_episode(
        episode_id="u",
        attack=Variant("M-09", ("mut-unhide",)).build(),
        task_id="task-shoes",
        seed=1729,
        agent=ScriptedAgent(susceptible=True),
        defense=Defense(tiers=(1,)),
    )
    assert episode.rupees_moved == 0
    assert episode.violated_invariant == "inv-06"


# -- rail profiles ----------------------------------------------------------


def test_uap_delegates_less_than_the_principal_holds():
    """The delegate cap is what makes UAP a different rail, not a relabel.

    A lower ceiling changes what the agent can afford, which changes which
    merchant it buys from, which changes the campaign. Without it the two
    profiles produce identical numbers under different headings.
    """
    assert "uap" in PROFILES
    uap, autopay = get_profile("uap"), get_profile("autopay")
    assert uap.ttl_seconds < autopay.ttl_seconds

    task = Catalog.load().task("task-shoes")
    assert uap.build_intent(task).max_amount == uap.delegate_cap
    assert autopay.build_intent(task).max_amount == task.max_amount
    assert uap.delegate_cap < task.max_amount


def test_every_declared_invariant_is_actually_implemented():
    """Listing a check nothing runs is the failure test_corpus.py guards against."""
    implemented = {i.id for i in INVARIANTS}
    for name in PROFILES:
        assert set(get_profile(name).invariants) <= implemented, name


def test_the_two_rails_produce_different_campaigns():
    """If the rail switch changes nothing observable, it is a slide, not a feature."""
    runs = {
        rail: run_campaign(repeats=1, profile=rail, defense=None) for rail in ("autopay", "uap")
    }
    assert metrics.rupees_moved(runs["autopay"]) != metrics.rupees_moved(runs["uap"])


@pytest.mark.parametrize("profile", ["autopay", "uap"])
def test_the_same_engine_runs_on_either_rail(profile):
    """One config flag, two payment worlds — no second codebase."""
    episode = run_episode(
        episode_id="p",
        attack=None,
        task_id="task-shoes",
        seed=1729,
        profile=profile,
        defense=Defense(tiers=(1,)),
    )
    assert episode.rail_profile == profile
    assert episode.outcome == "allow"
