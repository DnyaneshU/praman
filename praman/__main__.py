"""`python -m praman <command>` — the cross-platform entry point.

The Makefile is a convenience for Unix and CI. It is not the documented path,
because `make` is not present on a stock Windows machine and judges clone this
on whatever they happen to be using. Python is already a prerequisite, so the
package itself is the one runner guaranteed to work everywhere.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from praman.console import setup as console_setup

COMMANDS = {
    "demo": "An honest purchase, settled end to end",
    "campaign": "Run a single-round campaign, baseline beside defended",
    "adapt": "Run the adaptive campaign — the static vs adaptive gap",
    "train": "Fit Tier 2 on Red's survivors and report what it learned",
    "test": "Run the test suite",
    "lint": "Ruff check and format check",
}


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
        help="; ".join(f"{k}: {v}" for k, v in COMMANDS.items()),
    )
    args, rest = parser.parse_known_args(argv)

    if args.command is None:
        parser.print_help()
        print("\ncommands:")
        for name, blurb in COMMANDS.items():
            print(f"  {name:<10} {blurb}")
        return 0

    if args.command == "demo":
        from praman.range.demo import main as demo_main

        return demo_main(rest)

    if args.command == "campaign":
        from praman.red.runner import main as campaign_main

        return campaign_main(rest)

    if args.command == "adapt":
        from praman.red.adaptive_report import main as adapt_main

        return adapt_main(rest)

    if args.command == "train":
        from praman.blue.train_cli import main as train_main

        return train_main(rest)

    if args.command == "test":
        return subprocess.call([sys.executable, "-m", "pytest", *rest])

    if args.command == "lint":
        checks = [
            [sys.executable, "-m", "ruff", "check", "praman", "tests"],
            [sys.executable, "-m", "ruff", "format", "--check", "praman", "tests"],
        ]
        return max(subprocess.call(cmd) for cmd in checks)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
