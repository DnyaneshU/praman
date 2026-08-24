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

__all__ = ["Seed", "load_corpus", "CORPUS_PATH"]

CORPUS_PATH = Path(__file__).with_name("corpus.yaml")


class Seed(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    name: str
    attack_class: str = Field(alias="class")
    root_cause: str
    implemented: bool
    mechanism: str
    caught_by: str
    note: str | None = None


def load_corpus(path: Path | str = CORPUS_PATH) -> list[Seed]:
    with Path(path).open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or []
    return [Seed(**entry) for entry in raw]
