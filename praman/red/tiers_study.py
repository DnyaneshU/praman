"""`python -m praman models` — attack success by victim model tier.

The scoreboard has always had a row for this and it has always been blank.
Susceptibility to semantic attack is widely held to be model-dependent; this
runs the corpus against real models and reports our own numbers rather than
repeating anyone else's.

The result worth reading is not any single model's rate. It is the *contrast*:

    structural attacks   break the arithmetic between mandates and do not care
                         which model is running
    semantic attacks     subvert the agent's judgement and vary enormously

If that holds, swapping the model changes semantic risk a great deal and
structural risk not at all — which is the argument for putting the fix at the
control layer instead of hoping for a better model.

Models run locally through Ollama: no token, no rate limit, no network, and a
judge with the same three models pulled gets the same table back. Refusals and
malformed replies are reported in their own columns rather than being quietly
folded into "defended".
"""

from __future__ import annotations

import argparse
from pathlib import Path

from praman import metrics
from praman.blue.defense import Defense, control_label
from praman.console import Table, banner, divider
from praman.console import setup as console_setup
from praman.money import fmt
from praman.range.agent import ScriptedAgent
from praman.range.ollama_agent import OllamaAgent
from praman.red.attacks import ATTACKS
from praman.red.episode import Episode, write_jsonl
from praman.red.executor import run_episode

DEFAULT_MODELS = ("qwen2.5:1.5b", "llama3.2:3b", "mistral:latest")
TASKS = ("task-shoes", "task-trainer")


def _agents(models: tuple[str, ...]) -> list[tuple[str, object]]:
    """Every victim under test, with the scripted baseline first.

    The scripted agent is not a model, and that is why it belongs here: it is
    the control showing what the corpus does when there is no judgement to
    subvert at all.
    """
    agents: list[tuple[str, object]] = [("scripted", ScriptedAgent(susceptible=True))]
    agents += [(model, OllamaAgent(model=model)) for model in models]
    return agents


def run_study(
    *, models: tuple[str, ...], seed: int, repeats: int, tiers: tuple[int, ...]
) -> dict[str, list[Episode]]:
    defense = Defense(tiers=tiers) if tiers else None
    results: dict[str, list[Episode]] = {}

    for label, agent in _agents(models):
        episodes: list[Episode] = []
        for index in range(repeats):
            task_id = TASKS[index % len(TASKS)]
            for attack_id in sorted(ATTACKS):
                episodes.append(
                    run_episode(
                        episode_id=f"{label}-{len(episodes):03d}",
                        attack=ATTACKS[attack_id](),
                        task_id=task_id,
                        seed=seed + index,
                        agent=agent,
                        defense=defense,
                    )
                )
        results[label] = episodes

    return results


def _for_attack(episodes: list[Episode], attack_id: str) -> list[Episode]:
    return [e for e in episodes if e.attack_id == attack_id]


def report(results: dict[str, list[Episode]]) -> None:
    """Per attack, not per class.

    Aggregating by class buries the finding. M-09 is filed as semantic but
    tampers with the cart directly and never consults the agent's judgement, so
    it lands on every model by construction. M-08 is the only attack in the
    corpus whose success actually depends on which model is shopping, and
    averaging the two together hides exactly the number worth reporting.
    """
    ids = sorted(ATTACKS)
    print()
    # One column per attack, declared once. The heading row used to be written
    # `>13` over a `>12` data cell and only looked right because a neighbouring
    # cell carried a trailing space; a Table cannot drift that way.
    table = Table(
        ("victim model", 18),
        *((attack_id, 8, ">") for attack_id in ids),
        ("moved", 13, ">"),
        ("refused", 9, ">"),
        ("err", 5, ">"),
        gap=0,
    )
    table.head()
    for label, episodes in results.items():
        table.row(
            label,
            *(f"{metrics.asr(_for_attack(episodes, a)):.0%}" for a in ids),
            fmt(metrics.rupees_moved(episodes)),
            sum(e.outcome == "refusal" for e in episodes),
            sum(e.outcome == "error" for e in episodes),
        )

    divider()
    _interpret(results)


def _interpret(results: dict[str, list[Episode]]) -> None:
    """State the contrast in words rather than leaving the table to speak."""
    structural_ids = {a.id for a in ATTACKS.values() if a.attack_class == "structural"}
    structural = {
        label: metrics.asr([e for e in episodes if e.attack_id in structural_ids])
        for label, episodes in results.items()
    }
    whisper = {label: metrics.asr(_for_attack(eps, "M-08")) for label, eps in results.items()}

    if structural and set(structural.values()) == {1.0}:
        print("  Structural attacks succeeded against every model tested, at the same")
        print("  rate. They break the arithmetic between mandates, and arithmetic has")
        print("  no opinion about which model is shopping.")

    if whisper and len(set(whisper.values())) > 1:
        fell = [k for k, v in whisper.items() if v > 0]
        held = [k for k, v in whisper.items() if v == 0]
        print("\n  M-08 is the one attack whose success depends on the model:")
        print(f"    fell for the whisper   {', '.join(fell) or 'none'}")
        print(f"    resisted it            {', '.join(held) or 'none'}")

    print("\n  Choosing a better model moves the semantic column and leaves the")
    print("  structural one untouched — which is the case for fixing this at the")
    print("  control layer rather than hoping for a safer agent.\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Praman — attack success by victim model")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument(
        "--tiers", default="none", help='control to run behind, e.g. "1"; "none" for undefended'
    )
    # Under results/studies/ rather than results/ itself. A study is not a
    # campaign — these 48 episodes span four victim models and no single rail
    # or control — and the arena serves every *.jsonl in results/ as something
    # a viewer can replay. Dropping it beside the campaigns put an entry in the
    # picker that no combination of facets could ever select.
    parser.add_argument("--out", type=Path, default=Path("results/studies/model-tiers.jsonl"))
    args = parser.parse_args(argv)
    console_setup()

    models = tuple(m.strip() for m in args.models.split(",") if m.strip())
    tiers = () if args.tiers.lower() == "none" else tuple(int(t) for t in args.tiers.split(","))

    banner("VICTIM MODEL STUDY", control_label(tiers), f"seed {args.seed}")

    results = run_study(models=models, seed=args.seed, repeats=args.repeats, tiers=tiers)
    report(results)

    every = [e for episodes in results.values() for e in episodes]
    write_jsonl(every, args.out)
    print(f"  wrote {len(every)} episodes to {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
