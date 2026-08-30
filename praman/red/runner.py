"""`python -m praman campaign` — run the range and report what happened.

Always runs the undefended baseline, and runs the defended campaign beside it
when tiers are requested. Neither number means anything on its own: a control
reporting 96% is only interesting against the 100% it started from, and a
control that blocks everything looks identical to a good one until you read the
benign pass rate.

Baseline and defended runs differ in exactly one argument, so the comparison
between them is honest by construction.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from praman import metrics
from praman.blue.defense import Defense
from praman.console import Table, banner, summary
from praman.console import setup as console_setup
from praman.money import fmt
from praman.range.agent import ScriptedAgent
from praman.range.catalog import FIXTURES_DIR
from praman.red.attacks import ATTACKS
from praman.red.episode import Episode, write_jsonl
from praman.red.executor import BENIGN, run_episode


def run_campaign(
    *,
    seed: int = 1729,
    repeats: int = 5,
    profile: str = "autopay",
    defense: Defense | None = None,
    tasks: list[str] | None = None,
    attacks: list[str] | None = None,
    fixtures: Path | str = FIXTURES_DIR,
) -> list[Episode]:
    """One episode per attack per repeat, plus the same number of benign runs.

    Each repeat gets its own seed and task so the sample varies, while the whole
    campaign stays reproducible from the base seed alone.

    Semantic attacks need a susceptible agent; structural ones do not care. The
    agent is chosen per attack and recorded on every episode, because
    susceptibility is a variable we report rather than a constant we assume.

    `attacks` narrows the corpus and `fixtures` points at a different range —
    both exist for scenarios, and both default to what the shipped campaigns
    use so the committed numbers are unaffected.
    """
    tasks = tasks or ["task-shoes", "task-trainer"]
    attack_ids = sorted(attacks) if attacks else sorted(ATTACKS)
    episodes: list[Episode] = []

    for index in range(repeats):
        seed_i = seed + index
        task_id = tasks[index % len(tasks)]

        for attack_id in attack_ids:
            attack = ATTACKS[attack_id]()
            episodes.append(
                run_episode(
                    episode_id=f"ep-{len(episodes):04d}",
                    attack=attack,
                    task_id=task_id,
                    seed=seed_i,
                    profile=profile,
                    agent=ScriptedAgent(susceptible=attack.attack_class == "semantic"),
                    defense=defense,
                    fixtures=fixtures,
                )
            )

        episodes.append(
            run_episode(
                episode_id=f"ep-{len(episodes):04d}",
                attack=None,
                task_id=task_id,
                seed=seed_i,
                profile=profile,
                agent=ScriptedAgent(),
                defense=defense,
                fixtures=fixtures,
            )
        )

    return episodes


def _rows(episodes: list[Episode], attack_id: str) -> list[Episode]:
    return [e for e in episodes if e.attack_id == attack_id]


def _all_blocks_named(episodes: list[Episode]) -> bool:
    """A block that cannot say which rule it enforced is a bug, not a log line."""
    blocks = [e for e in episodes if e.outcome == "block"]
    return bool(blocks) and all(e.violated_invariant for e in blocks)


def _baseline_table(baseline: list[Episode]) -> None:
    print()
    table = Table(("attack", 7), ("name", 32), ("ASR", 6, ">"), ("moved", 14, ">"))
    table.head()
    for attack_id, rate in metrics.asr_by_attack(baseline).items():
        rows = _rows(baseline, attack_id)
        table.row(
            attack_id, ATTACKS[attack_id].name, f"{rate:.0%}", fmt(metrics.rupees_moved(rows))
        )


def _defended_table(baseline: list[Episode], defended: list[Episode]) -> None:
    print()
    table = Table(
        ("attack", 7),
        ("name", 30),
        ("ASR", 12, ">"),
        ("at risk", 12, ">"),
        ("left", 11, ">"),
        ("rule", 8, ">"),
    )
    table.head()
    # From the episodes, not the registry: a campaign may have run a subset.
    for attack_id in sorted({e.attack_id for e in defended} - {BENIGN}):
        base_rows = _rows(baseline, attack_id)
        def_rows = _rows(defended, attack_id)
        table.row(
            attack_id,
            ATTACKS[attack_id].name,
            f"{metrics.asr(base_rows):.0%} -> {metrics.asr(def_rows):.0%}",
            fmt(metrics.rupees_moved(base_rows)),
            fmt(metrics.rupees_moved(def_rows)),
            next((e.violated_invariant for e in def_rows if e.violated_invariant), "-"),
        )


def report(
    baseline: list[Episode], defended: list[Episode] | None, profile: str, seed: int
) -> None:
    title = "BASELINE — no control in place" if defended is None else "TIER 1"
    banner(title, f"profile: {profile}", f"seed: {seed}")

    if defended is None:
        _baseline_table(baseline)
        summary(
            [
                ("undefended ASR", f"{metrics.asr(baseline):.1%}"),
                ("moved", fmt(metrics.rupees_moved(baseline))),
                ("benign pass rate", f"{metrics.benign_pass_rate(baseline):.1%}"),
                ("episodes", len(baseline)),
            ]
        )
        print()
        return

    _defended_table(baseline, defended)
    control_ms = [e.latency_ms.get("control", 0.0) for e in defended]
    share = metrics.prevention_rate(baseline, defended)
    mean_ms = sum(control_ms) / max(len(control_ms), 1)

    summary(
        [
            ("ASR", f"{metrics.asr(baseline):.1%} -> {metrics.asr(defended):.1%}"),
            (
                "prevented",
                f"{fmt(metrics.rupees_prevented(baseline, defended))}   "
                f"({share:.1%} of value at risk)",
            ),
            ("benign pass rate", f"{metrics.benign_pass_rate(defended):.1%}"),
            ("control latency", f"{mean_ms:.3f} ms per authorisation"),
            ("", "arithmetic ~0.02ms; the rest is signature"),
            ("", "verification and the freshness datastore write"),
            ("every block named", "yes" if _all_blocks_named(defended) else "NO"),
            ("episodes", len(defended)),
        ]
    )
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Praman — run a campaign")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--profile", default="autopay")
    parser.add_argument(
        "--tiers",
        default="1",
        help='defense tiers, e.g. "1" or "1,2,3"; "none" for the undefended baseline',
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    console_setup()

    tiers = () if args.tiers.lower() == "none" else tuple(int(t) for t in args.tiers.split(","))
    shared = {"seed": args.seed, "repeats": args.repeats, "profile": args.profile}

    baseline = run_campaign(**shared, defense=None)
    defended = run_campaign(**shared, defense=Defense(tiers=tiers)) if tiers else None

    report(baseline, defended, args.profile, args.seed)

    episodes = baseline if defended is None else defended
    label = "baseline" if defended is None else f"tier{args.tiers.replace(',', '')}"
    # Under results/scratch/, which CampaignStore does not glob. A one-off run
    # is not a committed result, and dropping it beside the matrix put an
    # unnamed tenth campaign in the arena's sidebar that duplicated one already
    # there. Same reasoning as results/studies/.
    out = args.out or Path(f"results/scratch/{label}.jsonl")
    write_jsonl(episodes, out)
    print(f"  wrote {len(episodes)} episodes to {out}\n")

    if defended is None:
        # Every attack must take money when nothing is stopping it, or the
        # defense measured against this baseline proves nothing.
        return 0 if metrics.asr(baseline) == 1.0 else 1

    # A control that blocks honest traffic, or that cannot say why it blocked,
    # has failed regardless of how good its ASR looks.
    return 0 if metrics.benign_pass_rate(defended) == 1.0 and _all_blocks_named(defended) else 1


if __name__ == "__main__":
    raise SystemExit(main())
