"""`python -m praman train` — fit Tier 2 and report what it actually learned.

Prints three things, and the third is the one that matters:

  in-sample     how well the model separates the data it was fitted on
  held-out      how it does on an attacker profile it has never seen
  gains         which features carried the fit

A learned tier is easy to make look good. Reporting the held-out number beside
the in-sample one is what stops this being a demo.
"""

from __future__ import annotations

import argparse

from praman.blue.training import MODEL_PATH, evaluate_holdout, gather_training_set, train_tier2
from praman.console import banner, field
from praman.console import setup as console_setup

HOLDOUTS = (
    (0.42, "mule merchant — new, unrated, unsigned listings"),
    (0.92, "compromised merchant — established, well rated, signed"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Praman — train Tier 2 on Red's survivors")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--replicates", type=int, default=8)
    parser.add_argument("--skip-holdout", action="store_true")
    args = parser.parse_args(argv)
    console_setup()

    banner("TIER 2 TRAINING", "fitted on the attacks Tier 1 let through")

    tier, report = train_tier2(
        rounds=args.rounds, seed=args.seed, replicates=args.replicates, save_to=MODEL_PATH
    )
    episodes = gather_training_set(rounds=args.rounds, seed=args.seed, replicates=args.replicates)

    print()
    field("rows", f"{report.rows}  ({report.positives} moved money)")
    print("\n  feature gains")
    for name, gain in sorted(report.importances.items(), key=lambda kv: -kv[1]):
        marker = "" if gain else "   (unused)"
        field(name, f"{gain:>8.1f}{marker}", width=27, indent=4)

    flagged = sum(not tier.check(e.features).allowed for e in episodes if e.succeeded)
    attacks = sum(e.succeeded for e in episodes)
    false_positives = sum(not tier.check(e.features).allowed for e in episodes if not e.succeeded)
    benign = sum(not e.succeeded for e in episodes)

    print("\n  in-sample")
    field("caught", f"{flagged}/{attacks}", indent=4)
    field("false positives", f"{false_positives}/{benign}", indent=4)

    if not args.skip_holdout:
        print("\n  held out — the model never saw this merchant during training")
        for reputation, label in HOLDOUTS:
            result = evaluate_holdout(
                holdout_reputation=reputation, replicates=args.replicates, seed=args.seed
            )
            print(
                f"    {label:<52}\n"
                f"      caught {int(result['caught'])}/{int(result['held_out_attacks'])}"
                f"   recall {result['recall']:.0%}"
            )

    print()
    field("saved to", MODEL_PATH)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
