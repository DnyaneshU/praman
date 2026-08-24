"""`python -m praman campaign` — the undefended baseline.

Runs every implemented attack, plus honest control traffic, against a range
with no control in front of it, and writes the episodes to JSONL.

The number this produces is the one everything else is measured against. If a
defense later reports 96%, it means 96% *of this*. Without a baseline, a
defense that blocks everything and a defense that blocks nothing produce the
same reassuring report.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from praman import metrics
from praman.console import setup as console_setup
from praman.money import fmt
from praman.range.agent import ScriptedAgent
from praman.red.attacks import ATTACKS
from praman.red.episode import Episode, write_jsonl
from praman.red.executor import run_episode

DEFAULT_OUT = Path("results/baseline.jsonl")
RULE = "─" * 68


def run_baseline(
    *,
    seed: int = 1729,
    repeats: int = 5,
    profile: str = "autopay",
    tasks: list[str] | None = None,
) -> list[Episode]:
    """One episode per attack per repeat, plus the same number of benign runs.

    Each repeat gets its own seed and task so the sample varies, while the whole
    campaign stays reproducible from the base seed alone.
    """
    agent = ScriptedAgent()
    tasks = tasks or ["task-shoes", "task-trainer"]
    episodes: list[Episode] = []

    for index in range(repeats):
        seed_i = seed + index
        task_id = tasks[index % len(tasks)]
        for attack_id in sorted(ATTACKS):
            episodes.append(
                run_episode(
                    episode_id=f"ep-{len(episodes):04d}",
                    attack=ATTACKS[attack_id](),
                    task_id=task_id,
                    seed=seed_i,
                    profile=profile,
                    agent=agent,
                )
            )
        episodes.append(
            run_episode(
                episode_id=f"ep-{len(episodes):04d}",
                attack=None,
                task_id=task_id,
                seed=seed_i,
                profile=profile,
                agent=agent,
            )
        )

    return episodes


def report(episodes: list[Episode], profile: str, seed: int) -> None:
    by_attack = metrics.asr_by_attack(episodes)

    print(RULE)
    print(f"PRAMAN BASELINE  ·  no control in place  ·  profile: {profile}  ·  seed: {seed}")
    print(RULE)
    print(f"\n  {'attack':<8} {'name':<34} {'ASR':>7}   {'₹ moved':>14}")
    print(f"  {'-' * 8} {'-' * 34} {'-' * 7}   {'-' * 14}")

    for attack_id, rate in by_attack.items():
        subset = [e for e in episodes if e.attack_id == attack_id]
        name = ATTACKS[attack_id].name
        print(f"  {attack_id:<8} {name:<34} {rate:>6.1%}   {fmt(metrics.rupees_moved(subset)):>14}")

    print(f"\n  {'-' * 68}")
    print(f"  undefended ASR      {metrics.asr(episodes):.1%}")
    print(f"  total ₹ moved       {fmt(metrics.rupees_moved(episodes))}")
    print(f"  benign pass rate    {metrics.benign_pass_rate(episodes):.1%}")
    print(f"  episodes            {len(episodes)}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Praman — undefended baseline campaign")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--profile", default="autopay")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    console_setup()

    episodes = run_baseline(seed=args.seed, repeats=args.repeats, profile=args.profile)
    report(episodes, args.profile, args.seed)
    write_jsonl(episodes, args.out)
    print(f"  wrote {len(episodes)} episodes to {args.out}\n")

    # Every attack must take money when nothing is stopping it, or the defense
    # measured against this baseline proves nothing.
    return 0 if metrics.asr(episodes) == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
