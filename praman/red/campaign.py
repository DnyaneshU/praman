"""The adaptive loop — the campaign that produces the curve.

Round 0 runs the documented seed attacks. After that, every variant the control
refused is handed the *name of the rule that refused it*, and the mutator
proposes strategies aimed at that rule. Winners are kept, dead ends retired,
and the next round faces the same control with better attacks.

The output is the number nobody publishes for payments: how much better an
attacker gets once it is allowed to adapt. Every competitor reports the round-0
figure and stops.

Determinism is not incidental. Variants are recipes, the mutator is a pure
function of (variant, rule), and the selector breaks ties on lineage — so the
whole search replays identically from a seed on someone else's laptop.
"""

from __future__ import annotations

from dataclasses import dataclass

from praman.blue.defense import Defense
from praman.blue.verdict import Verdict
from praman.range.agent import ScriptedAgent
from praman.red.attacks import ATTACKS
from praman.red.episode import Episode
from praman.red.executor import run_episode
from praman.red.mutator.base import Mutator, Variant
from praman.red.mutator.search import SearchMutator
from praman.red.selector import Candidate, select

__all__ = ["run_adaptive_campaign", "CampaignResult"]


@dataclass
class CampaignResult:
    episodes: list[Episode]
    breakthroughs: list[Variant]
    """Variants that moved money. The report quotes these verbatim."""

    rounds: int


def _run_variant(
    variant: Variant,
    *,
    task_id: str,
    seed: int,
    profile: str,
    defense: Defense,
    round_: int,
    episode_id: str,
) -> Episode:
    attack = variant.build()
    return run_episode(
        episode_id=episode_id,
        attack=attack,
        task_id=task_id,
        seed=seed,
        profile=profile,
        agent=ScriptedAgent(susceptible=attack.attack_class == "semantic"),
        defense=defense,
        round_=round_,
        lineage=variant.lineage,
        strategy=variant.strategies[-1] if variant.strategies else None,
    )


def run_adaptive_campaign(
    *,
    rounds: int = 5,
    seed: int = 1729,
    profile: str = "autopay",
    defense: Defense | None = None,
    mutator: Mutator | None = None,
    population: int = 12,
    task_id: str = "task-shoes",
) -> CampaignResult:
    """Run seed attacks, then let the attacker adapt for `rounds` rounds."""
    defense = defense or Defense(tiers=(1,))
    mutator = mutator or SearchMutator()

    frontier = [Variant(attack_id) for attack_id in sorted(ATTACKS)]
    episodes: list[Episode] = []
    breakthroughs: list[Variant] = []
    seen: set[Variant] = set(frontier)

    for round_ in range(rounds):
        if not frontier:
            break

        candidates: list[Candidate] = []
        for variant in frontier:
            episode = _run_variant(
                variant,
                task_id=task_id,
                seed=seed,
                profile=profile,
                defense=defense,
                round_=round_,
                episode_id=f"ep-{len(episodes):04d}",
            )
            episodes.append(episode)
            candidates.append(Candidate(variant, episode))
            if episode.succeeded and variant not in breakthroughs:
                breakthroughs.append(variant)

        # A variant that already takes money has nothing left to learn; the
        # search spends its budget on the ones still being refused.
        blocked = [c for c in candidates if not c.succeeded]
        proposals: list[Variant] = []
        for candidate in select(blocked, population):
            verdict = _verdict_of(candidate.episode)
            proposals.extend(
                child for child in mutator.mutate(candidate.variant, verdict) if child not in seen
            )

        seen.update(proposals)
        frontier = proposals[:population]

    return CampaignResult(episodes=episodes, breakthroughs=breakthroughs, rounds=rounds)


def _verdict_of(episode: Episode) -> Verdict:
    """Reconstruct what the control told the attacker.

    The mutator is only ever given the rule name and the fact of refusal — the
    same thing a real attacker learns from a rejection message. Handing it the
    full internal verdict would be testing a stronger attacker than the threat
    model claims.
    """
    if episode.violated_invariant is None:
        return Verdict.allow()
    return Verdict.block(
        invariant=episode.violated_invariant,
        rule="",
        observed="",
        expected="",
        tier=episode.blocked_by_tier or 1,
    )
