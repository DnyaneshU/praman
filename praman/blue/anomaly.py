"""Tier 2 — a model trained on whatever got past Tier 1.

This is the loop closing. Session 4's search found that the way past the
invariant gate is to *satisfy* it: reissue the cart from a merchant the
attacker operates, and the chain becomes structurally impeccable. No arithmetic
can object, because the only thing wrong with it is a reputation score.

That is exactly the shape of problem a gradient-boosted model on tabular
features is good at, and exactly the shape a rule is bad at. Tier 2 trains on
Red's survivors — the attacks that reached the ledger — so the control learns
from the attacker rather than from a rulebook someone wrote in advance.

GBM rather than a neural net, deliberately: it trains in seconds on a few
hundred rows, it explains itself through split gains, and it wins on tabular
data. A neural net here would be a slower, less legible way to do worse.
"""

from __future__ import annotations

from pathlib import Path

from praman.blue.features import FEATURE_NAMES, vector
from praman.blue.verdict import Verdict
from praman.red.episode import Episode

__all__ = ["AnomalyTier", "TrainingReport"]

DEFAULT_THRESHOLD = 0.5


class TrainingReport:
    """What the training run learned, for the report and the arena."""

    __slots__ = ("rows", "positives", "importances")

    def __init__(self, rows: int, positives: int, importances: dict[str, float]) -> None:
        self.rows = rows
        self.positives = positives
        self.importances = importances

    def top(self, n: int = 3) -> list[tuple[str, float]]:
        return sorted(self.importances.items(), key=lambda kv: -kv[1])[:n]

    def __repr__(self) -> str:
        return f"<TrainingReport rows={self.rows} positives={self.positives}>"


class AnomalyTier:
    """Scores a chain on how much it resembles the attacks that got through.

    Untrained, it abstains rather than guessing — an untrained tier that
    blocked would make Tier 1 look worse than it is and would poison every
    comparison in the report.
    """

    tier = 2

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold
        self._booster = None
        self.report: TrainingReport | None = None

    @property
    def trained(self) -> bool:
        return self._booster is not None

    def train(self, episodes: list[Episode]) -> TrainingReport:
        """Fit on episodes that reached the ledger, labelled by whether they took money.

        Only episodes Tier 1 allowed through are useful: a chain the gate
        refused never reveals whether it would have moved money, and including
        it would teach Tier 2 to re-derive Tier 1's rules instead of learning
        the residual.
        """
        import lightgbm as lgb
        import numpy as np

        rows = [e for e in episodes if e.features and e.outcome == "allow"]
        if not rows:
            raise ValueError("no allowed episodes with features to train on")

        x = np.asarray([vector(e.features) for e in rows], dtype=float)
        y = np.asarray([int(e.succeeded) for e in rows], dtype=int)
        positives = int(y.sum())
        if positives in (0, len(rows)):
            raise ValueError(
                f"training set is single-class ({positives}/{len(y)} positive); "
                "run a campaign where some attacks get through and some do not"
            )

        dataset = lgb.Dataset(x, label=y, feature_name=list(FEATURE_NAMES))
        self._booster = lgb.train(
            {
                "objective": "binary",
                "verbosity": -1,
                "num_leaves": 7,
                "min_data_in_leaf": 2,
                "learning_rate": 0.15,
                "seed": 1729,
                "deterministic": True,
                "force_row_wise": True,
            },
            dataset,
            num_boost_round=60,
        )

        gains = self._booster.feature_importance(importance_type="gain")
        self.report = TrainingReport(
            rows=len(rows),
            positives=positives,
            importances=dict(zip(FEATURE_NAMES, (float(g) for g in gains), strict=True)),
        )
        return self.report

    def score(self, features: dict[str, float]) -> float:
        if not self.trained:
            return 0.0
        import numpy as np

        return float(self._booster.predict(np.asarray([vector(features)], dtype=float))[0])

    def check(self, features: dict[str, float]) -> Verdict:
        if not self.trained:
            return Verdict.allow(tier=self.tier)

        score = self.score(features)
        if score < self.threshold:
            return Verdict.allow(tier=self.tier, score=score)

        top = ", ".join(f"{name}" for name, _ in (self.report.top(2) if self.report else []))
        return Verdict.block(
            invariant="tier-2",
            rule="chain resembles attacks that previously reached the ledger",
            observed=f"anomaly score {score:.2f}",
            expected=f"below {self.threshold:.2f} (drivers: {top})",
            tier=self.tier,
            score=score,
        )

    def save(self, path: Path | str) -> None:
        if not self.trained:
            raise ValueError("nothing to save: model is untrained")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._booster.save_model(str(path))

    def load(self, path: Path | str) -> None:
        import lightgbm as lgb

        self._booster = lgb.Booster(model_file=str(path))
