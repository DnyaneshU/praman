"""Tier 1 — every attack blocked, by the *right* rule, with its evidence.

Two properties carry the defense's whole claim:

  1. Each attack is caught by the invariant the corpus says catches it. If two
     attacks tripped the same check, one of them would tell us nothing about
     the control.
  2. Every block names the rule it enforced, with observed and expected values.
     Without that, the explainability claim we make to a regulator-facing
     audience is simply false.

Both are asserted here rather than inspected by eye.
"""

import pytest

from praman.blue import Defense, Monitor
from praman.blue.invariants import INVARIANTS, STATEFUL, STATELESS
from praman.range.agent import ScriptedAgent
from praman.range.context import RangeContext
from praman.range.ledger import UnmediatedSettlement
from praman.red.attacks import ATTACKS, get_attack
from praman.red.corpus import load_corpus
from praman.red.executor import run_episode

CAUGHT_BY = {seed.id: seed.caught_by for seed in load_corpus() if seed.implemented}


def defended(attack_id: str | None, seed: int = 1729):
    attack = get_attack(attack_id) if attack_id else None
    return run_episode(
        episode_id=f"t-{attack_id or 'benign'}",
        attack=attack,
        task_id="task-shoes",
        seed=seed,
        agent=ScriptedAgent(susceptible=bool(attack) and attack.attack_class == "semantic"),
        defense=Defense(tiers=(1,)),
    )


@pytest.mark.parametrize("attack_id", sorted(ATTACKS))
def test_every_attack_is_caught_by_its_documented_invariant(attack_id):
    """The corpus claims a rule catches each attack. Verify, don't trust."""
    episode = defended(attack_id)
    assert episode.violated_invariant == CAUGHT_BY[attack_id]


@pytest.mark.parametrize("attack_id", sorted(ATTACKS))
def test_every_block_names_its_rule_with_evidence(attack_id):
    episode = defended(attack_id)
    assert episode.violated_invariant
    assert episode.blocked_by_tier == 1
    assert "expected" in (episode.detail or "")


@pytest.mark.parametrize("attack_id", sorted(set(ATTACKS) - {"S-03"}))
def test_structural_and_semantic_attacks_take_nothing(attack_id):
    assert defended(attack_id).rupees_moved == 0


def test_s03_leaves_a_residual_and_we_say_so():
    """The honest limit: Tier 1 stops the race, not the first redemption.

    Two of three concurrent redemptions are refused. The one that survives is
    structurally impeccable — correct beneficiary, valid signatures, inside the
    ceiling — so no arithmetic can object to it. Reporting that beats claiming
    a clean sweep nobody would believe.
    """
    attack = get_attack("S-03")
    undefended = run_episode(episode_id="u", attack=attack, task_id="task-shoes", seed=1729)
    episode = defended("S-03")
    assert episode.rupees_moved == undefended.rupees_moved / attack.redemptions
    assert "2 blocked" in (episode.detail or "")


@pytest.mark.parametrize("susceptible", [False, True])
def test_honest_purchases_are_never_blocked(susceptible):
    """A control that blocks honest traffic is not a control."""
    episode = run_episode(
        episode_id="b",
        attack=None,
        task_id="task-shoes",
        seed=1729,
        agent=ScriptedAgent(susceptible=susceptible),
        defense=Defense(tiers=(1,)),
    )
    assert episode.outcome == "allow"
    assert episode.violated_invariant is None


def test_the_ledger_refuses_settlement_that_skipped_the_monitor():
    """Out-of-band is enforced, not documented.

    This is the architectural claim the whole defense rests on. Once a monitor
    is attached, the ledger will not settle for anyone who did not go through
    it — including code inside the range.
    """
    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        Monitor(Defense(tiers=(1,)), ctx)
        chain = ScriptedAgent().shop(ctx.catalog.task("task-shoes"), ctx)
        with pytest.raises(UnmediatedSettlement):
            ctx.ledger.settle(chain.payment, source=ctx.principal)
    finally:
        ctx.ledger.close()


def test_stateful_checks_run_after_stateless_ones():
    """inv-04 consumes nonces; running it early would burn one on a dead chain."""
    assert STATELESS + STATEFUL == INVARIANTS
    assert [i.id for i in STATEFUL] == ["inv-04"]
    assert not any(i.stateful for i in STATELESS)


def test_invariant_ids_are_unique():
    ids = [i.id for i in INVARIANTS]
    assert len(ids) == len(set(ids))


def test_an_undefended_run_still_settles():
    """Defense(tiers=()) is the baseline, and must travel the identical path."""
    episode = run_episode(
        episode_id="n", attack=get_attack("S-02"), task_id="task-shoes", seed=1729
    )
    assert episode.rupees_moved > 0
