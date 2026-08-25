"""Running one episode: prepare, shop, mediate, read the ledger.

Every episode gets a fresh range — its own ledger, keys and RNG — so episodes
never contaminate each other and a campaign is reproducible from its seed.

With a defense attached, nothing reaches the ledger except through the monitor;
the ledger itself refuses unmediated settlement. Without one, chains settle
directly, which is the undefended baseline every later number is measured
against. The same code path produces both, so the comparison is honest.

Harm is the delta in attacker-controlled balances across the episode, read off
the ledger. Nothing here judges whether an attack "worked" — it reports how
many rupees moved.
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from praman.blue.defense import Defense
from praman.blue.monitor import Mediation, Monitor
from praman.blue.verdict import Verdict
from praman.range.agent import ScriptedAgent, VictimAgent
from praman.range.context import RangeContext
from praman.range.mandates import MandateChain
from praman.range.purchase import settle_chain
from praman.red.attacks.base import Attack
from praman.red.episode import Episode

__all__ = ["run_episode", "BENIGN"]

BENIGN = "benign"
"""Attack id for honest control traffic. Its pass rate is the false-positive rate."""


def run_episode(
    *,
    episode_id: str,
    attack: Attack | None,
    task_id: str,
    seed: int,
    profile: str = "autopay",
    agent: VictimAgent | None = None,
    defense: Defense | None = None,
    round_: int = 0,
) -> Episode:
    """Run one attack (or one honest purchase) end to end.

    `attack=None` is benign traffic: same agent, same range, no tamper. It is
    the false-positive signal, so it must travel the identical path.
    """
    agent = agent or ScriptedAgent()

    with tempfile.TemporaryDirectory() as tmp:
        ctx = RangeContext.build(Path(tmp) / "range.db", profile=profile, seed=seed)
        try:
            monitor = Monitor(defense, ctx) if defense else None

            if attack:
                attack.prepare(ctx)

            honest = agent.shop(ctx.catalog.task(task_id), ctx)
            chains = attack.plan(honest, ctx) if attack else [honest]

            before = ctx.harm()
            started = time.perf_counter()
            mediations = _settle_all(
                chains, ctx, monitor, concurrent=bool(attack and attack.concurrent)
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            moved = ctx.harm() - before
            blocked = [m for m in mediations if not m.allowed]
            evidence = blocked[0].verdict if blocked else None

            # "block" means the control actually prevented harm, not merely
            # that it objected somewhere. S-04's plan settles an honest chain
            # and then a replay: one allow and one block is a clean stop.
            # S-03's is three redemptions where one survives — that is not.
            prevented = bool(blocked) and moved == 0

            return Episode(
                episode_id=episode_id,
                round=round_,
                attack_id=attack.id if attack else BENIGN,
                rail_profile=ctx.profile.name,
                victim_model=agent.model_name,
                seed=seed,
                outcome="block" if prevented else "allow",
                blocked_by_tier=evidence.tier if evidence else None,
                violated_invariant=evidence.invariant if evidence else None,
                rupees_moved=moved,
                beneficiary=chains[-1].payment.beneficiary if moved else None,
                latency_ms={
                    "settle": round(elapsed_ms, 3),
                    # Per *decision*, not per episode: "added milliseconds per
                    # authorisation" is the number a payments architect asks
                    # for, and summing across a three-way race overstates it.
                    "control": round(
                        sum(m.verdict.latency_ms for m in mediations) / len(mediations), 4
                    ),
                },
                detail=_detail(attack, mediations, evidence),
            )
        finally:
            ctx.ledger.close()


def _settle_all(
    chains: list[MandateChain],
    ctx: RangeContext,
    monitor: Monitor | None,
    *,
    concurrent: bool,
) -> list[Mediation]:
    """Settle every chain in the plan, through the monitor when one is attached.

    S-03's race must genuinely contend, so its settlements go through a thread
    pool against the real ledger. Serialising them would turn the finding into
    theatre — and would also let the freshness check pass three times over.
    """
    settle: Callable[[MandateChain], Mediation]
    if monitor is not None:
        settle = monitor.mediate
    else:

        def settle(chain: MandateChain) -> Mediation:
            return Mediation(Verdict.allow(), settle_chain(chain, ctx))

    if not concurrent or len(chains) == 1:
        return [settle(chain) for chain in chains]

    with ThreadPoolExecutor(max_workers=len(chains)) as pool:
        return list(pool.map(settle, chains))


def _detail(
    attack: Attack | None, mediations: list[Mediation], evidence: Verdict | None
) -> str | None:
    """One line of human-readable evidence, as the arena's feed shows it."""
    if attack is None:
        return None

    parts: list[str] = []
    if len(mediations) > 1:
        verb = "concurrent redemptions" if attack.concurrent else "settlements"
        parts.append(f"{len(mediations)} {verb} on one authorisation")
        blocked = sum(not m.allowed for m in mediations)
        if blocked:
            parts.append(f"{blocked} blocked")
    if evidence is not None:
        parts.append(f"{evidence.observed} (expected {evidence.expected})")
    return " · ".join(parts) or None
