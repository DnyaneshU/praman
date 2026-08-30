"""`python -m praman corpus` — the attack map, and what is built of it.

The Identify pillar, printed. Every vector we have mapped across the payment
stack, grouped by the surface it attacks, with the ones that are actually built
and measured marked as such.

The split is the point. Identification is research: what could go wrong with
agentic payments, mapped as widely as we can see. Implementation is evidence:
what we have built, run, and measured against a control. Reporting them as one
number would inflate the second with the first, which is the usual way an
attack catalogue becomes a marketing document.

So the map is deliberately wider than the harness, and the gap is annotated.
Several entries name the *same* missing control — S-05, I-22 and D-33 all fail
for want of cumulative accounting across mandates — and three independent
attack paths converging on one gap is the strongest signal here for what to
build next. That is what a map is for.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from praman.console import setup as console_setup
from praman.red.corpus import CORPUS_PATH, SURFACES, Seed, load_corpus

RULE = "─" * 78

HEADINGS = {
    "mandate-chain": "The signed Intent -> Cart -> Payment protocol itself",
    "agent-judgement": "Subverting what the model decides to do",
    "agent-protocol": "Agent-to-agent trust, delegation, tool supply chain",
    "upi-rail": "India's rails: UPI, Autopay, AePS, BBPS, e-RUPI",
    "card-rail": "Tokenisation, 3DS, merchant-initiated transactions",
    "social": "GenAI social engineering against the human",
    "laundering": "Moving the proceeds once the payment succeeds",
}


def by_surface(seeds: list[Seed]) -> dict[str, list[Seed]]:
    grouped: dict[str, list[Seed]] = defaultdict(list)
    for seed in seeds:
        grouped[seed.surface].append(seed)
    return grouped


def report(seeds: list[Seed]) -> None:
    grouped = by_surface(seeds)

    for surface in SURFACES:
        entries = grouped.get(surface, [])
        if not entries:
            continue
        built = sum(s.implemented for s in entries)
        print(f"\n  {surface.upper()}  ·  {len(entries)} mapped, {built} built")
        print(f"  {HEADINGS.get(surface, '')}")
        print(f"  {'-' * 74}")
        for seed in entries:
            mark = "built" if seed.implemented else "  -  "
            print(f"    {mark}  {seed.id:<6} {seed.name:<38} {seed.caught_by}")

    _summary(seeds)


def _summary(seeds: list[Seed]) -> None:
    built = [s for s in seeds if s.implemented]
    surfaces = Counter(s.surface for s in seeds)
    causes = Counter(s.root_cause for s in seeds)

    print(f"\n  {'-' * 76}")
    print(f"  mapped                 {len(seeds)} vectors across {len(surfaces)} surfaces")
    print(f"  built and measured     {len(built)}")
    print(f"  root causes covered    {', '.join(sorted(causes))}")

    # The map is wider than the harness on purpose, and saying which is which
    # is what keeps the first number from inflating the second.
    unbuilt = [s for s in seeds if not s.implemented]
    no_rule = [s for s in unbuilt if s.caught_by == "none"]
    print(f"\n  {len(unbuilt)} mapped but not built. Of those, {len(no_rule)} name no rule at all")
    print("  — each says why in its note, and those notes are where the range's")
    print("  own boundaries are recorded rather than hidden.")

    cumulative = [s for s in seeds if "cumulative" in (s.note or "").lower()]
    if len(cumulative) > 1:
        ids = ", ".join(s.id for s in cumulative)
        print(f"\n  {len(cumulative)} independent paths converge on one missing control ({ids}):")
        print("  cumulative accounting across mandates against a delegated cap.")
        print("  Three attack surfaces pointing at one gap is what to build next.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m praman corpus",
        description="Praman — the attack map, and what is built of it",
    )
    parser.add_argument("--path", type=Path, default=CORPUS_PATH)
    args = parser.parse_args(argv)
    console_setup()

    print(RULE)
    print("PRAMAN  ·  ATTACK SURFACE MAP")
    print(RULE)

    report(load_corpus(args.path))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
