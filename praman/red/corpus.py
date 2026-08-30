"""Reading the seed corpus.

The corpus file is the public record of what we claim to have built. Keeping it
truthful matters more than keeping it complete — `test_corpus_matches_registry`
fails the build if a technique is marked implemented without an attack behind
it, or an attack ships without a corpus entry.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Seed", "load_corpus", "CORPUS_PATH", "SURFACES"]

SURFACES = (
    "mandate-chain",
    "upi-rail",
    "card-rail",
    "agent-protocol",
    "agent-judgement",
    "social",
    "laundering",
)
"""Declared here so a typo becomes a test failure rather than a
silently-new category of one."""

CORPUS_PATH = Path(__file__).with_name("corpus.yaml")


class Seed(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    name: str
    attack_class: str = Field(alias="class")
    surface: str
    """Where in the payment stack this lives — see corpus.yaml's header.

    The point of the field is breadth. An attack map that covers one layer is
    a map of one layer, however deep it goes, and `surface` is what makes that
    visible instead of leaving it to be inferred from the ids.
    """
    root_cause: str
    implemented: bool
    mechanism: str
    caught_by: str
    note: str | None = None


def load_corpus(path: Path | str = CORPUS_PATH) -> list[Seed]:
    with Path(path).open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or []
    return [Seed(**entry) for entry in raw]
