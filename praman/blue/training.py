"""Closing the loop: train Tier 2 on the attacks that got past Tier 1.

The order matters and is the whole point. Run the adaptive search against Tier
1 alone; whatever reaches the ledger is labelled by the ledger itself — money
moved or it did not — and that labelled set is Tier 2's training data.

Nobody wrote those labels. The attacker produced them by adapting, and the
defense learns from its own failures rather than from a rulebook someone
guessed at in advance. That coupling is the product, not the model.
"""

from __future__ import annotations

from pathlib import Path

from praman.blue.anomaly import AnomalyTier, TrainingReport
from praman.blue.defense import MODEL_PATH, Defense
from praman.red.campaign import run_adaptive_campaign
from praman.red.episode import Episode
from praman.red.executor import run_episode

__all__ = ["gather_training_set", "train_tier2", "MODEL_PATH"]


TRAINING_TASKS = ("task-shoes", "task-trainer", "task-budget", "task-premium")


def gather_training_set(
    *,
    rounds: int = 5,
    seed: int = 1729,
    profile: str = "autopay",
    replicates: int = 6,
) -> list[Episode]:
    """Run the adaptive search against Tier 1 and return what reached the ledger.

    Swept across seeds and tasks. One campaign yields only a handful of
    survivors, and a model fitted on eight rows is a coin flip with a
    confidence interval — the sweep is what makes the fit mean anything.

    Benign episodes come through this filter too, labelled by the ledger as
    having moved nothing. They are the negatives, and they are why Tier 2 does
    not simply learn "block everything".
    """
    episodes: list[Episode] = []
    for index in range(replicates):
        task_id = TRAINING_TASKS[index % len(TRAINING_TASKS)]
        result = run_adaptive_campaign(
            rounds=rounds,
            seed=seed + index,
            profile=profile,
            defense=Defense(tiers=(1,)),
            task_id=task_id,
        )
        episodes.extend(e for e in result.episodes if e.outcome == "allow" and e.features)

        # Honest traffic, one run per task. Without it the model has no
        # legitimate examples and learns "everything the attacker did not do
        # is fine" — which is how a fraud model ends up with a catastrophic
        # false-positive rate the moment it meets production.
        for task in TRAINING_TASKS:
            benign = run_episode(
                episode_id=f"train-benign-{index}-{task}",
                attack=None,
                task_id=task,
                seed=seed + index,
                profile=profile,
                defense=Defense(tiers=(1,)),
            )
            if benign.outcome == "allow" and benign.features:
                episodes.append(benign)

    return episodes


def train_tier2(
    *,
    rounds: int = 5,
    seed: int = 1729,
    profile: str = "autopay",
    replicates: int = 6,
    save_to: Path | None = MODEL_PATH,
) -> tuple[AnomalyTier, TrainingReport]:
    """Gather survivors, fit the model, and optionally persist it."""
    episodes = gather_training_set(rounds=rounds, seed=seed, profile=profile, replicates=replicates)
    tier = AnomalyTier()
    report = tier.train(episodes)
    if save_to is not None:
        tier.save(save_to)
    return tier, report


def evaluate_holdout(
    *, holdout_reputation: float, replicates: int = 8, seed: int = 1729
) -> dict[str, float]:
    """Train without ever seeing one merchant, then test on it.

    The question a judge should ask about any learned tier is whether it
    generalised or memorised. Feature importances cannot answer that — a model
    that carves out one merchant's reputation with two tight splits reports the
    same importance as one that learned a real pattern.

    Holding a merchant out answers it directly: if the model still flags the
    unseen attacker, it learned something transferable. If it does not, that is
    the honest ceiling of behavioural features, and it is what Tier 3 and human
    review exist for.
    """
    episodes = gather_training_set(replicates=replicates, seed=seed)

    def reputation(episode: Episode) -> float:
        return round(episode.features.get("merchant_reputation", 0.0), 2)

    held = [e for e in episodes if reputation(e) == holdout_reputation]
    trained_on = [e for e in episodes if reputation(e) != holdout_reputation]
    if not held:
        raise ValueError(f"no episodes at reputation {holdout_reputation}")

    tier = AnomalyTier()
    tier.train(trained_on)

    attacks = [e for e in held if e.succeeded]
    caught = sum(not tier.check(e.features).allowed for e in attacks)
    return {
        "trained_on": float(len(trained_on)),
        "held_out": float(len(held)),
        "held_out_attacks": float(len(attacks)),
        "caught": float(caught),
        "recall": caught / len(attacks) if attacks else 0.0,
    }
