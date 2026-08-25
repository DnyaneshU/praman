"""`python -m praman serve` — start the arena.

One command, no build step, no npm. Opens on http://127.0.0.1:8000 by default.
"""

from __future__ import annotations

import argparse

from praman.console import setup as console_setup

BANNER = """
────────────────────────────────────────────────────────────────
  PRAMAN ARENA
  attack feed · mandate chain · verdict · attack-success curve

  open  http://{host}:{port}
  mode  {mode}
────────────────────────────────────────────────────────────────
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Praman — serve the arena")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--mode",
        choices=("live", "replay"),
        default=None,
        help="replay serves committed results only; it is the deployed default",
    )
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)
    console_setup()

    import os

    if args.mode:
        os.environ["PRAMAN_MODE"] = args.mode

    print(BANNER.format(host=args.host, port=args.port, mode=os.environ.get("PRAMAN_MODE", "live")))

    import uvicorn

    uvicorn.run(
        "praman.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
