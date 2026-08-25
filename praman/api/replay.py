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
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import WebSocket

from praman import metrics
from praman.blue.defense import control_label
from praman.red.episode import Episode, read_jsonl

__all__ = ["CampaignStore", "CampaignRecord", "stream_episodes"]

logger = logging.getLogger(__name__)

EPISODE_DELAY = 0.45
ROUND_DELAY = 1.2


def _read_meta(path: Path) -> dict:
    """A scenario's `<id>.meta.json`, if it wrote one.

    Only scenarios author these; the generated matrix names itself from the
    rail and tiers its episodes already carry. A malformed sidecar costs the
    campaign its title, never its place in the picker.
    """
    sidecar = path.with_suffix(".meta.json")
    if not sidecar.is_file():
        return {}
    try:
        with sidecar.open(encoding="utf-8") as fh:
            meta = json.load(fh)
    except (ValueError, OSError) as exc:
        logger.warning("ignoring unreadable %s: %s", sidecar.name, exc)
        return {}
    return meta if isinstance(meta, dict) else {}


RAILS = {"autopay": "UPI Autopay", "uap": "NPCI UAP"}


@dataclass(frozen=True)
class CampaignRecord:
    id: str
    path: Path
    episodes: list[Episode]
    meta: dict = field(default_factory=dict)
    """Whatever `<id>.meta.json` said, if a scenario wrote one."""

    def describe(self) -> dict:
        """Everything the picker needs to name and rank this campaign.

        The picker lists campaigns rather than synthesising one from a rail and
        a tier selection. It used to do the latter, and two committed campaigns
        — `autopay-tier1` and `uap-tier1` — were unreachable because the
        adaptive run shares their rail and tiers and won the tie. A list cannot
        hide a campaign the way a lookup can.
        """
        rounds = sorted({e.round for e in self.episodes})
        first = self.episodes[0]
        adaptive = len(rounds) > 1
        tiers = first.defense_tiers
        return {
            "id": self.id,
            "name": self.meta.get("name") or self._name(first.rail_profile, tiers, adaptive),
            "description": self.meta.get("description"),
            "authored": bool(self.meta),
            "episodes": len(self.episodes),
            "rounds": len(rounds),
            "adaptive": adaptive,
            "rail": first.rail_profile,
            "rail_name": RAILS.get(first.rail_profile, first.rail_profile),
            "tiers": tiers,
            "label": control_label(tiers),
            # The headline numbers, so selecting a campaign fills the scoreboard
            # before anything streams. A page of em-dashes waiting on a replay
            # reads as broken rather than as ready.
            "asr": metrics.asr(self.episodes),
            "benign": metrics.benign_pass_rate(self.episodes),
            "moved": str(metrics.rupees_moved(self.episodes)),
            "static_asr": metrics.static_asr(self.episodes),
            "adaptive_asr": metrics.adaptive_asr(self.episodes),
            "adaptive_delta": metrics.adaptive_delta(self.episodes),
            "rounds_to_break": metrics.rounds_to_break(self.episodes),
        }

    @staticmethod
    def _name(rail: str, tiers: list[int], adaptive: bool) -> str:
        control = control_label(tiers)
        return f"{RAILS.get(rail, rail)} · {control}" + (" · adaptive" if adaptive else "")


class CampaignStore:
    """Committed campaign files, read on demand.

    Deliberately not cached: `make campaign` rewrites these during development
    and a cached store would serve yesterday's numbers from a page that looks
    live.
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def list(self) -> list[CampaignRecord]:
        """Campaigns only, and only from the top level.

        `glob` rather than `rglob` is load-bearing: `results/studies/` holds
        runs that are not campaigns — the victim-model study spans four models
        and belongs to no single rail — and serving one as a campaign puts a
        row in the picker that nothing on the page can select.
        """
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
        """Read one campaign file, complaining loudly if it will not parse.

        Swallowing the error silently makes an unreadable campaign vanish from
        the picker with no signal at all — which is exactly what happened when
        a new Episode field met results written by an older build. A campaign
        that cannot be read is a broken deployment, not an empty list.
        """
        try:
            episodes = read_jsonl(path)
        except (ValueError, OSError) as exc:
            logger.warning("skipping unreadable campaign %s: %s", path.name, exc)
            return None
        if not episodes:
            return None
        return CampaignRecord(id=path.stem, path=path, episodes=episodes, meta=_read_meta(path))


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
