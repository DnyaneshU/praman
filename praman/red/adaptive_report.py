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
from praman.console import Table, banner, summary
from praman.console import setup as console_setup
from praman.money import fmt
from praman.red.campaign import CampaignResult, run_adaptive_campaign
from praman.red.episode import write_jsonl
from praman.red.mutator.base import STRATEGIES

BAR_WIDTH = 34


def _curve(result: CampaignResult) -> None:
    print()
    table = Table(
        ("round", 7),
        ("ASR", 6, ">"),
        ("", BAR_WIDTH),
        ("episodes", 9, ">"),
        ("moved", 13, ">"),
    )
    table.head()
    for round_ in sorted({e.round for e in result.episodes}):
        rows = [e for e in result.episodes if e.round == round_]
        rate = metrics.asr(rows)
        table.row(
            round_,
            f"{rate:.0%}",
            "█" * round(rate * BAR_WIDTH),
            len(rows),
            fmt(metrics.rupees_moved(rows)),
        )


def _breakthroughs(result: CampaignResult) -> None:
    if not result.breakthroughs:
        print("\n  no attack got through — the control held for every round")
        return

    print()
    table = Table(("broke through", 40), ("via", 34))
    table.head()
    for variant in result.breakthroughs:
        rationale = (
            STRATEGIES[variant.strategies[-1]].rationale
            if variant.strategies
            else "succeeded without adapting"
        )
        table.row(variant, rationale)


def _held(result: CampaignResult) -> None:
    """Rules the search could not get around. Reporting these earns the rest."""
    broke = {v.attack_id for v in result.breakthroughs}
    survived = sorted({e.attack_id for e in result.episodes} - broke)
    if survived:
        print(f"\n  held against every strategy tried:  {', '.join(survived)}")


def report(result: CampaignResult, seed: int, profile: str) -> None:
    episodes = result.episodes
    banner("ADAPTIVE CAMPAIGN", f"profile: {profile}", f"seed: {seed}")

    _curve(result)
    _breakthroughs(result)
    _held(result)

    broke_at = metrics.rounds_to_break(episodes)
    summary(
        [
            (
                "static ASR",
                f"{metrics.static_asr(episodes):.1%}   (documented attack, control knows it)",
            ),
            (
                "adaptive ASR",
                f"{metrics.adaptive_asr(episodes):.1%}   (same attacker, allowed to adapt)",
            ),
            ("adaptive delta", f"{metrics.adaptive_delta(episodes) * 100:+.1f} points"),
            ("rounds to break", broke_at if broke_at is not None else "never"),
            ("moved", fmt(metrics.rupees_moved(episodes))),
            ("episodes", len(episodes)),
        ]
    )
    print()


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
