"""`python -m praman detect` — the control scored as a detection model.

Precision, recall, F1 and AUC, over every committed campaign. These are the
numbers a detection model is normally judged in, and Praman reports them beside
the ones it actually optimises for, because the two disagree in a way that
matters.

**Detection is not prevention.** Tier 1 flags every attack in the static
corpus — precision 1.00, recall 1.00, F1 1.00, no false positives — and money
still reaches the attacker on 16.7% of them. S-03 fires three concurrent
redemptions at one authorisation; the control refuses two and the third
settles. Every one of those episodes is a true positive by decision and a
success by ledger.

A submission that reported only F1 would show a perfect classifier over a
system losing money. One that reported only ASR would hide that the control saw
every attack coming. Both are printed here, always, side by side — and the gap
between them is the number worth arguing about, because in live payments a
flag that arrives after settlement is a chargeback, not a defense.

The second thing this shows is what adaptation does to recall. Against the
documented corpus Tier 1 flags everything. Against an attacker that has read
its refusals, recall falls by half: the variants it finds are not caught late,
they are not caught at all.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from praman import metrics
from praman.api.replay import CampaignStore
from praman.blue.anomaly import AnomalyTier
from praman.blue.defense import MODEL_PATH, control_label
from praman.console import setup as console_setup
from praman.money import fmt
from praman.red.episode import Episode

RULE = "─" * 78


def tier2_auc(episodes: list[Episode]) -> float | None:
    """AUC for the learned tier, from the features every episode already carries.

    Only Tier 2 emits a score, so only Tier 2 has an AUC. The deterministic
    tiers return a verdict, not a ranking, and quoting an AUC for them would be
    dressing a rule up as a model.
    """
    if not MODEL_PATH.exists():
        return None
    tier = AnomalyTier()
    tier.load(MODEL_PATH)
    scored = [(tier.score(e.features), e.attack_id != "benign") for e in episodes if e.features]
    return metrics.roc_auc(scored) if scored else None


def report(store: CampaignStore) -> int:
    records = store.list()
    if not records:
        return 1

    print(f"\n  {'campaign':<22} {'control':<12} {'P':>6} {'R':>6} {'F1':>6} {'FPR':>6} {'ASR':>7}")
    print(f"  {'-' * 22} {'-' * 12} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 7}")

    for record in records:
        d = metrics.detection(record.episodes)
        tiers = record.episodes[0].defense_tiers
        print(
            f"  {record.id:<22} {control_label(tiers):<12} "
            f"{d['precision']:>6.3f} {d['recall']:>6.3f} {d['f1']:>6.3f} "
            f"{d['false_positive_rate']:>6.3f} {metrics.asr(record.episodes):>6.1%}"
        )

    _gap(records)
    _auc(records)
    return 0


def _gap(records: list) -> None:
    """The point of printing both columns."""
    every = [e for r in records for e in r.episodes]
    perfect = [
        r for r in records if metrics.recall(r.episodes) == 1.0 and metrics.asr(r.episodes) > 0
    ]

    print(f"\n  {'-' * 76}")
    print("  DETECTION IS NOT PREVENTION")
    for record in perfect:
        moved = fmt(metrics.rupees_moved(record.episodes))
        print(f"    {record.id}: recall 1.000 and {moved} still reached the attacker.")
    if perfect:
        print("    Every attack was flagged. S-03 settles one of three concurrent")
        print("    redemptions anyway — a true positive by decision, a success by")
        print("    ledger. In live payments that flag is a chargeback, not a block.")

    adaptive = [r for r in records if len({e.round for e in r.episodes}) > 1]
    if adaptive:
        print("\n  WHAT ADAPTATION DOES TO RECALL")
        for record in adaptive:
            rounds = sorted({e.round for e in record.episodes})
            first = metrics.recall([e for e in record.episodes if e.round == rounds[0]])
            last = metrics.recall([e for e in record.episodes if e.round == rounds[-1]])
            print(
                f"    {record.id}: round {rounds[0]} recall {first:.3f} "
                f"-> round {rounds[-1]} recall {last:.3f}"
            )
        print("    The variants it finds are not caught late. They are not caught.")

    print(f"\n  scored episodes        {len([e for e in every if e.counts_toward_rates])}")


def _auc(records: list) -> None:
    """Tier 2's ranking quality, where a ranking exists at all."""
    trained = [r for r in records if 2 in r.episodes[0].defense_tiers]
    if not trained:
        return

    print("\n  TIER 2, AS A RANKER")
    for record in trained:
        auc = tier2_auc(record.episodes)
        shown = f"{auc:.3f}" if auc is not None else "undefined (one class only)"
        print(f"    {record.id}: AUC {shown}")
    print("    Only the learned tier emits a score, so only it has an AUC. The")
    print("    deterministic tiers return a verdict rather than a ranking, and")
    print("    quoting one for them would dress a rule up as a model.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m praman detect",
        description="Praman — the control scored as a detection model",
    )
    parser.add_argument("--results", type=Path, default=Path("results"))
    args = parser.parse_args(argv)
    console_setup()

    print(RULE)
    print("PRAMAN  ·  DETECTION EFFICACY")
    print(RULE)
    print("\n  Attacks are the positive class. A flag is the control naming a rule")
    print("  or escalating for review. Refusals and harness errors are excluded.")

    code = report(CampaignStore(args.results))
    if code:
        print(f"\n  no campaigns in {args.results} — run `python -m praman matrix` first\n")
    else:
        print()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
