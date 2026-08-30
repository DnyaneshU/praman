"""`python -m praman export` — the arena as a directory of files.

Everything the arena reads is a committed campaign file. Nothing is computed
per request, nothing is written, and there is no state between one viewer and
the next — so the server is a convenience, not a requirement. This writes what
its four endpoints return, at the same paths, and copies the frontend beside
them:

    dist/
      index.html  arena.css  arena.js  components.js  format.js
      vendor/…
      api/health
      api/campaigns
      api/campaign/<id>

The paths are the API's, exactly. `arena.js` fetches them *relatively*
(`fetch("api/campaigns")`), which resolves to `/api/campaigns` under the server
at the root and to `/praman/api/campaigns` under a project path on a static
host. One frontend, one set of paths, no build-time branch and no second code
path to keep in step.

Extensionless on purpose, matching the routes rather than adding `.json`.
Static hosts serve them with whatever content type they guess, and `Response.
json()` parses on content rather than on a header.

Why this exists: free hosting that runs a container has become scarce and the
free tiers that remain sleep, so a judge's first visit waits on a cold start.
Static hosting does not sleep, does not expire, and does not need a card. The
claim gets stronger rather than weaker — the deployed arena has no server at
all, and every number on screen is a file you can diff against a local re-run.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from praman import metrics
from praman.api.main import STATIC_DIR
from praman.api.replay import CampaignStore
from praman.console import banner, field
from praman.console import setup as console_setup

__all__ = ["export"]


def export(*, results: Path, into: Path) -> list[str]:
    """Write the arena and its data into `into`. Returns the campaign ids."""
    into = Path(into)
    if into.exists():
        # Rewritten wholesale rather than merged: a campaign deleted from
        # results/ must not survive in a deploy as a row the data no longer
        # backs.
        shutil.rmtree(into)
    shutil.copytree(STATIC_DIR, into)

    api = into / "api"
    (api / "campaign").mkdir(parents=True)

    store = CampaignStore(results)
    records = store.list()

    # `static` rather than `replay`: the masthead should say what is true. There
    # is no server here to enforce a mode.
    _write(api / "health", {"status": "ok", "mode": "static"})
    _write(api / "campaigns", [r.describe() for r in records])

    for record in records:
        _write(
            api / "campaign" / record.id,
            {
                "id": record.id,
                "summary": metrics.summarise(record.episodes),
                "episodes": [e.model_dump(mode="json") for e in record.episodes],
            },
        )

    return [r.id for r in records]


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m praman export",
        description="Praman — write the arena as static files",
    )
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    console_setup()

    banner("STATIC EXPORT")

    ids = export(results=args.results, into=args.out)
    if not ids:
        print(f"\n  no campaigns in {args.results} — run `python -m praman matrix` first\n")
        return 1

    files = [f for f in args.out.rglob("*") if f.is_file()]
    print()
    field("campaigns", len(ids), width=12)
    for campaign_id in ids:
        field("", campaign_id, width=12)
    print()
    field("files", len(files), width=12)
    field("size", f"{sum(f.stat().st_size for f in files) / 1024:.0f} KB", width=12)
    print(f"\n  wrote {args.out}")
    print("  serve it from anywhere: no server, no credential, no cold start\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
