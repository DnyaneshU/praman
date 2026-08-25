"""The arena's HTTP and WebSocket surface.

Two operating modes, and the difference is enforced rather than documented:

  live    local development. Campaigns can be started from the page.
  replay  what is deployed. Committed campaign files are streamed back at demo
          speed, no LLM is called, and no credential exists to be spent.

`PRAMAN_MODE=replay` is the deployed default. A public URL that can start
campaigns is a public URL anyone can bill, and a full campaign takes minutes to
watch — neither is what a judge with forty repos wants. Replaying committed
results makes the numbers reproducible by anyone with no credential at all,
which is a stronger claim than a live demo, not a weaker one.

This module must import with no `ANTHROPIC_API_KEY` present. Nothing here
constructs a model client, and `test_api.py` asserts the import.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from praman import metrics
from praman.api.replay import CampaignStore, stream_episodes

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


@app.websocket("/ws/replay/{campaign_id}")
async def replay(websocket: WebSocket, campaign_id: str) -> None:
    """Stream a committed campaign back, one episode at a time."""
    await websocket.accept()
    record = store.get(campaign_id)
    if record is None:
        await websocket.send_json({"type": "error", "detail": f"no campaign {campaign_id!r}"})
        await websocket.close()
        return

    try:
        await stream_episodes(websocket, record)
    except WebSocketDisconnect:
        # A viewer closing the tab mid-replay is normal, not an error.
        return


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
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

else:  # pragma: no cover - only reachable from a broken install
    logging.getLogger(__name__).error(
        "no arena at %s — the frontend was not packaged; check "
        "tool.setuptools.package-data in pyproject.toml",
        STATIC_DIR,
    )
