"""`python -m praman matrix` — every campaign the arena can show.

The arena replays committed results, so a rail switch and a tier toggle on the
page are only honest if a campaign was actually run for each combination. This
generates that matrix once and writes it to `results/`, which is what the
deployed arena serves.

Two rails times three control configurations, plus an adaptive campaign per
rail. The undefended run is included deliberately: a 16.7% attack success rate
means nothing until you can put it beside the 100% it started from, and the
picker should let a judge do exactly that in two clicks.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from praman import metrics
from praman.blue.anomaly import AnomalyTier
from praman.blue.defense import Defense
from praman.blue.training import MODEL_PATH
from praman.console import setup as console_setup
from praman.money import fmt
from praman.red.campaign import run_adaptive_campaign
from praman.red.episode import Episode, write_jsonl
from praman.red.runner import run_campaign

RULE = "─" * 76
RAILS = ("autopay", "uap")
CONTROLS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("undefended", ()),
    ("tier1", (1,)),
    ("tier123", (1, 2, 3)),
)


def _defense(tiers: tuple[int, ...]) -> Defense | None:
    """Build the control, loading the trained Tier 2 when the config asks for it."""
    if not tiers:
        return None
    anomaly = AnomalyTier()
    if 2 in tiers and MODEL_PATH.exists():
        anomaly.load(MODEL_PATH)
    return Defense(tiers=tiers, anomaly=anomaly)


def build(*, seed: int, repeats: int, rounds: int, out: Path) -> list[tuple[str, list[Episode]]]:
    written: list[tuple[str, list[Episode]]] = []

    for rail in RAILS:
        for label, tiers in CONTROLS:
            episodes = run_campaign(
                seed=seed, repeats=repeats, profile=rail, defense=_defense(tiers)
            )
            name = f"{rail}-{label}"
            write_jsonl(episodes, out / f"{name}.jsonl")
            written.append((name, episodes))

        adaptive = run_adaptive_campaign(
            rounds=rounds, seed=seed, profile=rail, defense=_defense((1,))
        )
        name = f"{rail}-adaptive"
        write_jsonl(adaptive.episodes, out / f"{name}.jsonl")
        written.append((name, adaptive.episodes))

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Praman — generate the campaign matrix")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args(argv)
    console_setup()

    print(RULE)
    print(f"PRAMAN  ·  CAMPAIGN MATRIX  ·  seed {args.seed}")
    print(RULE)
    print(f"\n  {'campaign':<22} {'episodes':>9} {'ASR':>7} {'moved':>14} {'benign':>8}")
    print(f"  {'-' * 22} {'-' * 9} {'-' * 7} {'-' * 14} {'-' * 8}")

    for name, episodes in build(
        seed=args.seed, repeats=args.repeats, rounds=args.rounds, out=args.out
    ):
        print(
            f"  {name:<22} {len(episodes):>9} {metrics.asr(episodes):>6.0%} "
            f"{fmt(metrics.rupees_moved(episodes)):>14} "
            f"{metrics.benign_pass_rate(episodes):>7.0%}"
        )

    print(f"\n  wrote to {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
