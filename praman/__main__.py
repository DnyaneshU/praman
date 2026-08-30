"""`python -m praman <command>` — the cross-platform entry point.

The Makefile is a convenience for Unix and CI. It is not the documented path,
because `make` is not present on a stock Windows machine and judges clone this
on whatever they happen to be using. Python is already a prerequisite, so the
package itself is the one runner guaranteed to work everywhere.

One table names every command, its blurb and where it lives. It used to be two
— a dict for the help text and a chain of fourteen `if` statements to dispatch
on — which meant a command could be advertised and not wired up, falling
through to a bare `return 1` that said nothing. With a single table the help
and the dispatch cannot disagree, and `tests/test_cli.py` walks it.

Modules are imported on demand. `praman corpus` should not pay for lightgbm.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from importlib import import_module

from praman.console import setup as console_setup

#: The dev commands shell out rather than importing, so they are functions
#: here; everything else is the module that provides `main(argv)`.
Target = str | Callable[[list[str]], int]


def _pytest(argv: list[str]) -> int:
    return subprocess.call([sys.executable, "-m", "pytest", *argv])


def _lint(argv: list[str]) -> int:
    targets = argv or ["praman", "tests", "scripts"]
    return max(
        subprocess.call([sys.executable, "-m", "ruff", *check, *targets])
        for check in (["check"], ["format", "--check"])
    )


#: command -> (blurb, module or callable). Order is the order `--help` prints.
COMMANDS: dict[str, tuple[str, Target]] = {
    "demo": ("An honest purchase, settled end to end", "praman.range.demo"),
    "campaign": ("Run a single-round campaign, baseline beside defended", "praman.red.runner"),
    "adapt": (
        "Run the adaptive campaign — the static vs adaptive gap",
        "praman.red.adaptive_report",
    ),
    "train": ("Fit Tier 2 on Red's survivors and report what it learned", "praman.blue.train_cli"),
    "corpus": ("The attack surface map, and what is built of it", "praman.red.corpus_report"),
    "walkthrough": (
        "Build the solution walkthrough .docx from live results",
        "praman.report.walkthrough",
    ),
    "detect": (
        "Precision, recall, F1 and AUC over every committed campaign",
        "praman.blue.detect_report",
    ),
    "matrix": ("Generate every campaign the arena can show", "praman.red.matrix"),
    "run": ("Run a scenario: python -m praman run scenarios/<name>.yaml", "praman.scenario"),
    "export": ("Write the arena as static files, for hosting anywhere", "praman.api.export"),
    "models": ("Attack success by victim model tier (needs Ollama)", "praman.red.tiers_study"),
    "serve": ("Start the arena at http://127.0.0.1:8000", "praman.api.serve"),
    "test": ("Run the test suite", _pytest),
    "lint": ("Ruff check and format check", _lint),
}


def dispatch(command: str, argv: list[str]) -> int:
    """Run one command. Imported here so nothing is loaded until it is needed."""
    _, target = COMMANDS[command]
    if callable(target):
        return target(argv)
    return import_module(target).main(argv)


def main(argv: list[str] | None = None) -> int:
    console_setup()
    parser = argparse.ArgumentParser(
        prog="python -m praman",
        description="Praman — breach and attack simulation for payment mandate controls",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=sorted(COMMANDS),
        help="; ".join(f"{name}: {blurb}" for name, (blurb, _) in COMMANDS.items()),
    )
    args, rest = parser.parse_known_args(argv)

    if args.command is None:
        parser.print_help()
        print("\ncommands:")
        for name, (blurb, _) in COMMANDS.items():
            print(f"  {name:<12} {blurb}")
        return 0

    return dispatch(args.command, rest)


if __name__ == "__main__":
    raise SystemExit(main())
