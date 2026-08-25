"""`python -m praman adapt` — the adaptive campaign and its report.

Prints the one figure the field asks for and nobody publishes on payment harm:
the gap between attack success against a fixed script and attack success
against the same attacker allowed to read the rejection and try again.

The breakthrough list is deliberately verbatim. "Adaptive ASR rose" is a claim;
`S-02 -> mut-reissue` naming the exact strategy that broke a named rule is
evidence, and it is what a fraud team would ask to see.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from praman import metrics
from praman.blue.defense import Defense
from praman.console import setup as console_setup
from praman.money import fmt
from praman.red.campaign import CampaignResult, run_adaptive_campaign
from praman.red.episode import write_jsonl
from praman.red.mutator.base import STRATEGIES

RULE = "─" * 76
BAR_WIDTH = 34


def _curve(result: CampaignResult) -> None:
    print(f"\n  {'round':<7} {'ASR':>6}  {'':<{BAR_WIDTH}} {'episodes':>9} {'moved':>13}")
    print(f"  {'-' * 7} {'-' * 6}  {'-' * BAR_WIDTH} {'-' * 9} {'-' * 13}")
    rounds = sorted({e.round for e in result.episodes})
    for round_ in rounds:
        rows = [e for e in result.episodes if e.round == round_]
        rate = metrics.asr(rows)
        bar = "█" * round(rate * BAR_WIDTH)
        moved = fmt(metrics.rupees_moved(rows))
        print(f"  {round_:<7} {rate:>5.0%}  {bar:<{BAR_WIDTH}} {len(rows):>9} {moved:>13}")


def _breakthroughs(result: CampaignResult) -> None:
    if not result.breakthroughs:
        print("\n  no attack got through — the control held for every round")
        return

    print(f"\n  {'broke through':<40} {'via'}")
    print(f"  {'-' * 40} {'-' * 34}")
    for variant in result.breakthroughs:
        if variant.strategies:
            reason = STRATEGIES[variant.strategies[-1]].rationale
        else:
            reason = "succeeded without adapting"
        print(f"  {str(variant):<40} {reason}")


def _held(result: CampaignResult) -> None:
    """Rules the search could not get around. Reporting these earns the rest."""
    broke = {v.attack_id for v in result.breakthroughs}
    survived = sorted({e.attack_id for e in result.episodes} - broke)
    if survived:
        print(f"\n  held against every strategy tried:  {', '.join(survived)}")


def report(result: CampaignResult, seed: int, profile: str) -> None:
    episodes = result.episodes
    print(RULE)
    print(f"PRAMAN  ·  ADAPTIVE CAMPAIGN  ·  profile: {profile}  ·  seed: {seed}")
    print(RULE)

    _curve(result)
    _breakthroughs(result)
    _held(result)

    static = metrics.static_asr(episodes)
    adaptive = metrics.adaptive_asr(episodes)
    broke_at = metrics.rounds_to_break(episodes)

    print(f"\n  {'-' * 74}")
    print(f"  static ASR           {static:.1%}   (documented attack, control knows it)")
    print(f"  adaptive ASR         {adaptive:.1%}   (same attacker, allowed to adapt)")
    print(f"  adaptive delta       {metrics.adaptive_delta(episodes) * 100:+.1f} points")
    print(f"  rounds to break      {broke_at if broke_at is not None else 'never'}")
    print(f"  moved                {fmt(metrics.rupees_moved(episodes))}")
    print(f"  episodes             {len(episodes)}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Praman — adaptive campaign")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--profile", default="autopay")
    parser.add_argument("--tiers", default="1")
    parser.add_argument("--out", type=Path, default=Path("results/adaptive.jsonl"))
    args = parser.parse_args(argv)
    console_setup()

    tiers = tuple(int(t) for t in args.tiers.split(","))
    result = run_adaptive_campaign(
        rounds=args.rounds,
        seed=args.seed,
        profile=args.profile,
        defense=Defense(tiers=tiers),
    )

    report(result, args.seed, args.profile)
    write_jsonl(result.episodes, args.out)
    print(f"  wrote {len(result.episodes)} episodes to {args.out}\n")

    # The thesis, as an exit code: an attacker that cannot improve on the
    # documented attack means Praman is a regression suite.
    return 0 if metrics.adaptive_delta(result.episodes) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
