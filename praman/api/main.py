"""The arena's HTTP surface.

Four endpoints, all of them reads over committed files. `python -m praman
export` writes exactly what they return as static JSON, so the same arena runs
against this server locally and as static files when deployed — one frontend,
one set of paths, no build-time branch.

Two operating modes, and the difference is enforced rather than documented:

  live    local development. Campaigns can be started from the page.
  replay  no LLM is called and no credential exists to be spent.

`PRAMAN_MODE=replay` is the deployed default. A public URL that can start
campaigns is a public URL anyone can bill, and a full campaign takes minutes to
watch — neither is what a judge with forty repos wants. Serving committed
results makes the numbers reproducible by anyone with no credential at all,
which is a stronger claim than a live demo, not a weaker one.

This module must import with no `ANTHROPIC_API_KEY` present. Nothing here
constructs a model client, and `test_api.py` asserts the import.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from praman import metrics
from praman.api.replay import CampaignStore

MODE = os.environ.get("PRAMAN_MODE", "live").lower()
STATIC_DIR = Path(__file__).parent / "static"
RESULTS_DIR = Path(os.environ.get("PRAMAN_RESULTS", "results"))

app = FastAPI(
    title="Praman Arena",
    description="Breach and attack simulation for agentic payment mandate controls",
    version="0.1.0",
)
store = CampaignStore(RESULTS_DIR)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": MODE}


@app.get("/api/campaigns")
def campaigns() -> list[dict]:
    """Every committed campaign, newest first."""
    return [c.describe() for c in store.list()]


@app.get("/api/campaign/{campaign_id}")
def campaign(campaign_id: str) -> dict:
    record = store.get(campaign_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no campaign {campaign_id!r}")
    return {
        "id": record.id,
        "summary": metrics.summarise(record.episodes),
        "episodes": [e.model_dump(mode="json") for e in record.episodes],
    }


@app.post("/api/campaign/start")
def start_campaign() -> dict:
    if MODE == "replay":
        raise HTTPException(
            status_code=403,
            detail="this deployment replays committed results; run campaigns locally",
        )
    raise HTTPException(status_code=501, detail="live campaigns run from the CLI")


# The arena is mounted last so API routes always win. It ships as plain files —
# no build step, no bundle to regenerate — so this is the whole frontend deploy.
#
# A missing static directory used to skip this block in silence, which deploys
# as an API that answers every request correctly and a site with no pages. It
# is a packaging failure, so it says so: the assets are declared in
# pyproject.toml under tool.setuptools.package-data.
if STATIC_DIR.is_dir():
    # Mounted at the root rather than at /static, so index.html can reference
    # its own assets relatively. Those same relative paths then resolve under a
    # static export served from a project path, which is what lets one frontend
    # serve both. Declared last, so every /api route above wins the match.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="arena")

else:  # pragma: no cover - only reachable from a broken install
    logging.getLogger(__name__).error(
        "no arena at %s — the frontend was not packaged; check "
        "tool.setuptools.package-data in pyproject.toml",
        STATIC_DIR,
    )
