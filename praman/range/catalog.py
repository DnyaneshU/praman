"""Merchants and products, loaded from YAML fixtures.

Catalog content is *data*, not code, because attacks target it: M-08 hides
instructions in product metadata and M-12 poisons unsigned listings. A catalog
compiled into Python would make those attacks impossible to express.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from praman.money import rupees

__all__ = ["Merchant", "Product", "Task", "Catalog", "FIXTURES_DIR"]

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


class Merchant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    vpa: str
    reputation: float
    age_days: int
    signed_listings: bool


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    merchant_id: str
    name: str
    price: Decimal
    category: str
    injected_note: str | None = None
    """Free-text metadata the agent reads. M-08 writes its payload here."""


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    principal: str
    description: str
    max_amount: Decimal
    categories: list[str]


class Catalog:
    def __init__(self, merchants: list[Merchant], products: list[Product], tasks: list[Task]):
        self.merchants = {m.id: m for m in merchants}
        self.products = {p.sku: p for p in products}
        self.tasks = {t.id: t for t in tasks}

    @classmethod
    def load(cls, directory: Path | str = FIXTURES_DIR) -> Catalog:
        directory = Path(directory)
        merchants = [Merchant(**m) for m in _read(directory / "merchants.yaml")]
        products = [
            Product(**{**p, "price": rupees(p["price"])})
            for p in _read(directory / "products.yaml")
        ]
        tasks = [
            Task(**{**t, "max_amount": rupees(t["max_amount"])})
            for t in _read(directory / "tasks.yaml")
        ]
        return cls(merchants, products, tasks)

    def merchant(self, merchant_id: str) -> Merchant:
        return self.merchants[merchant_id]

    def product(self, sku: str) -> Product:
        return self.products[sku]

    def task(self, task_id: str) -> Task:
        return self.tasks[task_id]

    def search(self, category: str, max_price: Decimal) -> list[Product]:
        """What the victim agent sees when it shops.

        Ordered by merchant reputation then price — the ranking M-08 subverts.
        """
        matches = [
            p for p in self.products.values() if p.category == category and p.price <= max_price
        ]
        return sorted(
            matches,
            key=lambda p: (-self.merchants[p.merchant_id].reputation, p.price),
        )


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []
