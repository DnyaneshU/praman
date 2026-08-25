"""Replaying a committed campaign at a speed a human can follow.

A campaign runs in seconds; watching one is the point. Episodes stream with a
pause between them and a longer one at each round boundary, because the story
the arena tells is *round by round* — blocked, blocked, then through.

Nothing here re-runs anything. The episodes are read from the JSONL committed
in `results/`, which is why the deployed arena needs no credential and why a
judge re-running the campaign locally gets the same numbers back.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from fastapi import WebSocket

from praman import metrics
from praman.red.episode import Episode, read_jsonl

__all__ = ["CampaignStore", "CampaignRecord", "stream_episodes"]

EPISODE_DELAY = 0.45
ROUND_DELAY = 1.2


@dataclass(frozen=True)
class CampaignRecord:
    id: str
    path: Path
    episodes: list[Episode]

    def describe(self) -> dict:
        rounds = sorted({e.round for e in self.episodes})
        return {
            "id": self.id,
            "episodes": len(self.episodes),
            "rounds": len(rounds),
            "adaptive": len(rounds) > 1,
            "asr": metrics.asr(self.episodes),
            "moved": str(metrics.rupees_moved(self.episodes)),
        }


class CampaignStore:
    """Committed campaign files, read on demand.

    Deliberately not cached: `make campaign` rewrites these during development
    and a cached store would serve yesterday's numbers from a page that looks
    live.
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def list(self) -> list[CampaignRecord]:
        if not self.directory.is_dir():
            return []
        records = [self._load(p) for p in sorted(self.directory.glob("*.jsonl"))]
        return [r for r in records if r is not None]

    def get(self, campaign_id: str) -> CampaignRecord | None:
        # Resolve through the directory listing rather than joining the id onto
        # a path: an id is user input, and this endpoint is public.
        return next((r for r in self.list() if r.id == campaign_id), None)

    @staticmethod
    def _load(path: Path) -> CampaignRecord | None:
        try:
            episodes = read_jsonl(path)
        except (ValueError, OSError):
            return None
        return CampaignRecord(id=path.stem, path=path, episodes=episodes) if episodes else None


async def stream_episodes(websocket: WebSocket, record: CampaignRecord) -> None:
    """Send the summary, then each episode, pausing at round boundaries."""
    await websocket.send_json(
        {
            "type": "summary",
            "campaign": record.describe(),
            "summary": metrics.summarise(record.episodes),
        }
    )

    previous_round: int | None = None
    for episode in record.episodes:
        if previous_round is not None and episode.round != previous_round:
            await websocket.send_json({"type": "round", "round": episode.round})
            await asyncio.sleep(ROUND_DELAY)
        previous_round = episode.round

        await websocket.send_json({"type": "episode", "episode": episode.model_dump(mode="json")})
        await asyncio.sleep(EPISODE_DELAY)

    await websocket.send_json({"type": "done"})
