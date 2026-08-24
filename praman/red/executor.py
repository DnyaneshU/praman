"""Running one episode: attack, settle, read the ledger.

Every episode gets a fresh range — its own ledger, keys and RNG — so episodes
never contaminate each other and a campaign is reproducible from its seed.

Harm is measured as the *delta* in attacker-controlled balances across the
episode, read off the ledger. Nothing here judges whether an attack "worked";
it reports how many rupees moved.

Session 3 adds a `defense` argument. Until then every chain reaches the ledger
unopposed, which is the baseline the whole project is measured against.
"""

from __future__ import annotations

import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
    round_: int = 0,
) -> Episode:
    """Run one attack (or one honest purchase) end to end.

    `attack=None` is benign traffic: the same agent, the same range, no tamper.
    """
    agent = agent or ScriptedAgent()

    with tempfile.TemporaryDirectory() as tmp:
        ctx = RangeContext.build(Path(tmp) / "range.db", profile=profile, seed=seed)
        try:
            task = ctx.catalog.task(task_id)
            honest = agent.shop(task, ctx)
            chains = attack.plan(honest, ctx) if attack else [honest]

            before = ctx.harm()
            started = time.perf_counter()
            _settle_all(chains, ctx, concurrent=bool(attack and attack.concurrent))
            elapsed_ms = (time.perf_counter() - started) * 1000
            moved = ctx.harm() - before

            return Episode(
                episode_id=episode_id,
                round=round_,
                attack_id=attack.id if attack else BENIGN,
                rail_profile=ctx.profile.name,
                victim_model=agent.model_name,
                seed=seed,
                verdict="allow",
                rupees_moved=moved,
                beneficiary=chains[-1].payment.beneficiary if moved else None,
                latency_ms={"settle": round(elapsed_ms, 3)},
                detail=_detail(attack, chains),
            )
        finally:
            ctx.ledger.close()


def _settle_all(chains: list[MandateChain], ctx: RangeContext, *, concurrent: bool) -> None:
    """Settle every chain in the plan.

    S-03's race must genuinely contend, so its settlements go through a thread
    pool against the real ledger rather than being replayed in sequence.
    """
    if not concurrent or len(chains) == 1:
        for chain in chains:
            settle_chain(chain, ctx)
        return

    with ThreadPoolExecutor(max_workers=len(chains)) as pool:
        list(pool.map(lambda chain: settle_chain(chain, ctx), chains))


def _detail(attack: Attack | None, chains: list[MandateChain]) -> str | None:
    if attack is None:
        return None
    if len(chains) == 1:
        return None
    verb = "concurrent redemptions" if attack.concurrent else "settlements"
    return f"{len(chains)} {verb} on one authorisation"
