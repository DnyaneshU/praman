"""Every structural attack must succeed against an undefended range.

This is the single most important test file in the project right now. If an
attack cannot take money when nothing is stopping it, then Session 3's defense
proves nothing about that attack, and every number we report for it is
meaningless. A regression here invalidates results rather than breaking a
feature.
"""

from decimal import Decimal

import pytest

from praman.range.context import ATTACKER_MERCHANT
from praman.red.attacks import ATTACKS, get_attack
from praman.red.executor import run_episode

STRUCTURAL = ["S-01", "S-02", "S-03", "S-04"]


def episode(attack_id: str | None, seed: int = 1729):
    return run_episode(
        episode_id=f"test-{attack_id or 'benign'}",
        attack=get_attack(attack_id) if attack_id else None,
        task_id="task-shoes",
        seed=seed,
    )


@pytest.mark.parametrize("attack_id", STRUCTURAL)
def test_attack_succeeds_undefended(attack_id):
    ep = episode(attack_id)
    assert ep.succeeded, f"{attack_id} took nothing — the defense would prove nothing"
    assert ep.rupees_moved > 0
    assert ep.beneficiary is not None


@pytest.mark.parametrize("attack_id", STRUCTURAL)
def test_attack_is_reproducible(attack_id):
    """Same seed, same harm. Without this our headline figures are anecdotes."""
    assert episode(attack_id).rupees_moved == episode(attack_id).rupees_moved


def test_benign_purchase_moves_nothing_to_the_attacker():
    ep = episode(None)
    assert ep.rupees_moved == Decimal(0)
    assert ep.attack_id == "benign"


def test_s02_changes_only_the_beneficiary():
    """The narrower the tamper, the sharper the demo. One field, ₹3,940 gone."""
    ep = episode("S-02")
    assert ep.beneficiary == "mule-vpa@axl"
    assert ep.rupees_moved == Decimal(394000)


def test_s03_redeems_one_authorisation_several_times():
    """Three concurrent settlements of a single mandate, all of which land."""
    attack = get_attack("S-03")
    ep = episode("S-03")
    unit = ep.rupees_moved / attack.redemptions
    assert ep.rupees_moved == unit * attack.redemptions
    assert attack.redemptions == 3
    assert "concurrent redemptions" in (ep.detail or "")


def test_s04_reuses_a_spent_intent():
    """The honest purchase settles first; the replay rides the same intent."""
    ep = episode("S-04")
    assert ep.succeeded
    assert ep.beneficiary is not None


@pytest.mark.parametrize("attack_id", STRUCTURAL)
def test_attacks_do_not_mutate_the_honest_chain(attack_id):
    """`apply` must copy. A mutated input would corrupt the S-04 replay plan."""
    from praman.range.agent import ScriptedAgent
    from praman.range.context import RangeContext

    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        honest = ScriptedAgent().shop(ctx.catalog.task("task-shoes"), ctx)
        snapshot = honest.model_dump_json()
        get_attack(attack_id).apply(honest, ctx)
        assert honest.model_dump_json() == snapshot
    finally:
        ctx.ledger.close()


def test_every_registered_attack_has_distinct_metadata():
    ids = [a.id for a in ATTACKS.values()]
    assert len(ids) == len(set(ids))
    assert all(a.root_cause.startswith("RC-") for a in ATTACKS.values())


def test_structural_attacks_route_harm_to_attacker_accounts():
    """Harm that lands anywhere else is invisible to every metric we report."""
    from praman.range.context import RangeContext

    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        assert ctx.merchant_vpa(ATTACKER_MERCHANT) in ctx.attacker_accounts
        assert ctx.attacker_vpa in ctx.attacker_accounts
    finally:
        ctx.ledger.close()
