"""Scenarios — new test cases without touching the package.

Everything the arena shows today comes from `python -m praman matrix`: two
rails, three control configurations, one catalogue, six attacks. That is a
fixed grid, and a fixed grid is a checklist — the thing this project exists to
argue against. A checklist tells you what someone thought of; it cannot tell
you what an attacker will find.

A scenario is one YAML file that says what to test:

    python -m praman run scenarios/gift-card-ceiling.yaml

It can widen the range (new merchants, products and shopping tasks), point at
Python files that define new attacks, choose the rail, the control, the attack
subset and the number of adaptation rounds. The run writes a campaign into
`results/`, which is the directory the arena serves — so a new test case shows
up in the picker with no code change, no rebuild, and no redeploy.

Three rules the format enforces, each because the alternative produces numbers
that quietly stop meaning anything:

**The range is overlaid, never replaced.** A scenario adds to the shipped
catalogue. Every invariant threshold, every Tier 2 feature and every published
figure is calibrated against that population, so a scenario that started from
an empty range would report percentages against a different world while looking
like the same experiment.

**Redefining a shipped id is an error.** Silently overriding
`merchant_0250`'s reputation would move Tier 2's decision boundary with nothing
in the result to say so. Pick a new id.

**Everything is validated before anything runs.** A campaign takes minutes; a
typo should cost milliseconds. Unknown attack ids, unknown task ids, products
sold by merchants that do not exist and duplicate ids are all reported together,
up front, by name.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from praman import metrics
from praman.blue.anomaly import AnomalyTier
from praman.blue.defense import Defense
from praman.blue.training import MODEL_PATH
from praman.console import setup as console_setup
from praman.money import fmt
from praman.range.catalog import FIXTURES_DIR, Catalog
from praman.range.profiles import PROFILES
from praman.red.attacks import ATTACKS
from praman.red.campaign import run_adaptive_campaign
from praman.red.episode import Episode, write_jsonl
from praman.red.runner import run_campaign

__all__ = ["Scenario", "RangeOverlay", "ScenarioError", "load", "run", "prepared_range"]

RULE = "─" * 76
FIXTURE_FILES = ("merchants.yaml", "products.yaml", "tasks.yaml")


class ScenarioError(ValueError):
    """A scenario that cannot run, with every reason listed at once."""

    def __init__(self, source: Path | str, problems: list[str]) -> None:
        self.problems = problems
        listed = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"{source} cannot run:\n{listed}")


class RangeOverlay(BaseModel):
    """Merchants, products and tasks this scenario adds to the range.

    Held as raw mappings rather than parsed models, deliberately: they are
    written into a fixtures directory and read back through `Catalog.load`,
    the same call the shipped range uses. One code path means a scenario's
    catalogue cannot differ from the real one in some detail nobody checked.
    """

    model_config = ConfigDict(extra="forbid")

    merchants: list[dict] = Field(default_factory=list)
    products: list[dict] = Field(default_factory=list)
    tasks: list[dict] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.merchants or self.products or self.tasks)


class Scenario(BaseModel):
    """One test case, as written in YAML.

    `extra="forbid"` is the point of using a model here: a scenario that says
    `attack:` instead of `attacks:` would otherwise run the full corpus and
    look like it worked.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    """Becomes `results/<id>.jsonl`, and the campaign's id in the arena."""
    name: str
    description: str | None = None

    rail: str = "autopay"
    control: list[int] = Field(default_factory=lambda: [1])
    """Defense tiers. `[]` is the undefended baseline, and is a real answer."""

    seed: int = 1729
    repeats: int = 4
    """How many times each attack runs, each with its own seed and task.
    Single-round campaigns only — an adaptive run's budget is `rounds`."""
    rounds: int = 1
    """More than one turns this into an adaptive campaign: the attacker is told
    which rule refused it and searches for a way around that rule."""

    tasks: list[str] = Field(default_factory=lambda: ["task-shoes", "task-trainer"])
    attacks: list[str] | None = None
    """Which corpus ids to run. `null` means every attack registered, including
    any the scenario's own modules add."""

    attack_modules: list[str] = Field(default_factory=list)
    """Python files defining new attacks, resolved relative to the scenario."""

    range: RangeOverlay = Field(default_factory=RangeOverlay)

    source: Path | None = Field(default=None, exclude=True)
    """Where this was loaded from. Attack module paths resolve against it."""

    @property
    def adaptive(self) -> bool:
        return self.rounds > 1

    def meta(self) -> dict:
        """The sidecar the arena reads to title this campaign."""
        return {"name": self.name, "description": self.description}


# -- loading ----------------------------------------------------------------


def load(path: Path | str) -> Scenario:
    """Parse and fully validate a scenario, importing any attacks it defines.

    Attack modules are imported here rather than at run time because
    `attacks:` is checked against the registry, and a scenario's own attacks
    have to be in it before that check can be fair.
    """
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScenarioError(path, [str(exc)]) from exc
    if not isinstance(raw, dict):
        raise ScenarioError(path, ["expected a mapping at the top level"])

    scenario = Scenario(**raw, source=path)
    problems = _import_attack_modules(scenario)
    problems += _validate(scenario)
    if problems:
        raise ScenarioError(path, problems)
    return scenario


def _import_attack_modules(scenario: Scenario) -> list[str]:
    """Execute each attack module so its `@register` decorators run.

    Loaded by path rather than by import name so a scenario can live anywhere —
    a teammate's `scenarios/` directory is not on `sys.path` and should not have
    to be. Re-registering an id already in the corpus raises inside `register`,
    which is the error worth surfacing: two different attacks answering to
    `S-02` would make every result ambiguous.
    """
    base = scenario.source.parent if scenario.source else Path.cwd()
    problems: list[str] = []

    for entry in scenario.attack_modules:
        module_path = (base / entry).resolve()
        if not module_path.is_file():
            problems.append(f"attack module not found: {entry}")
            continue

        name = f"praman_scenario_attacks_{module_path.stem}"
        if name in sys.modules:
            continue  # already loaded this run; its attacks are registered

        spec = importlib.util.spec_from_file_location(name, module_path)
        if spec is None or spec.loader is None:
            problems.append(f"could not load attack module: {entry}")
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 - any failure is the user's to see
            del sys.modules[name]
            problems.append(f"{entry} failed to import: {exc}")

    return problems


def _validate(scenario: Scenario) -> list[str]:
    """Everything wrong with this scenario, all at once.

    Reported together rather than one exception at a time: a scenario is
    usually wrong in two or three ways on the first attempt, and fixing them
    one run at a time is how a five-minute task becomes an afternoon.
    """
    problems: list[str] = []
    shipped = Catalog.load()

    if scenario.rail not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        problems.append(f"unknown rail {scenario.rail!r}; known rails: {known}")

    for tier in scenario.control:
        if tier not in (1, 2, 3):
            problems.append(f"unknown control tier {tier}; tiers are 1, 2 and 3")

    for count, name in ((scenario.repeats, "repeats"), (scenario.rounds, "rounds")):
        if count < 1:
            problems.append(f"{name} must be at least 1")

    if scenario.adaptive and not scenario.control:
        # The attacker adapts to refusals. With nothing refusing, round 0
        # succeeds outright, the frontier empties, and the run reports a
        # one-round campaign that looks like an adaptive result.
        problems.append(
            "rounds > 1 needs a control to adapt against; set control, or leave rounds at 1"
        )

    problems += _overlay_problems(scenario.range, shipped)

    known_tasks = set(shipped.tasks) | {t.get("id") for t in scenario.range.tasks}
    for task_id in scenario.tasks:
        if task_id not in known_tasks:
            shipped_tasks = ", ".join(sorted(shipped.tasks))
            problems.append(
                f"unknown task {task_id!r}; define it under range.tasks, "
                f"or use one of: {shipped_tasks}"
            )
    if not scenario.tasks:
        problems.append("tasks is empty; a campaign with nothing to buy runs no episodes")

    for attack_id in scenario.attacks or []:
        if attack_id not in ATTACKS:
            known = ", ".join(sorted(ATTACKS))
            problems.append(f"unknown attack {attack_id!r}; registered: {known}")
    if scenario.attacks is not None and not scenario.attacks:
        problems.append("attacks is an empty list; omit the key to run every attack")

    return problems


def _overlay_problems(overlay: RangeOverlay, shipped: Catalog) -> list[str]:
    """Cross-reference checks the YAML schema cannot make on its own."""
    problems: list[str] = []

    groups = (
        ("merchant", "id", overlay.merchants, shipped.merchants),
        ("product", "sku", overlay.products, shipped.products),
        ("task", "id", overlay.tasks, shipped.tasks),
    )
    for kind, key, entries, existing in groups:
        for entry in entries:
            identifier = entry.get(key)
            if identifier is None:
                problems.append(f"a {kind} under range.{kind}s has no {key}")
            elif identifier in existing:
                problems.append(
                    f"{kind} {identifier!r} already exists in the shipped range; "
                    "scenarios add to the range, they do not redefine it"
                )

    merchant_ids = set(shipped.merchants) | {m.get("id") for m in overlay.merchants}
    for product in overlay.products:
        merchant_id = product.get("merchant_id")
        if merchant_id is not None and merchant_id not in merchant_ids:
            problems.append(
                f"product {product.get('sku', '?')!r} is sold by unknown merchant "
                f"{merchant_id!r} — add it under range.merchants"
            )

    return problems


# -- running ----------------------------------------------------------------


@contextmanager
def prepared_range(scenario: Scenario) -> Iterator[Path]:
    """Yield a fixtures directory holding the shipped range plus the overlay.

    A directory rather than an in-memory catalogue because attacks poison the
    catalogue — M-08 writes its payload into product metadata — so every
    episode loads its own copy. Sharing one would leak an episode's tampering
    into the next, and the run would stop being reproducible.
    """
    if scenario.range.is_empty():
        yield FIXTURES_DIR
        return

    with tempfile.TemporaryDirectory(prefix="praman-range-") as tmp:
        directory = Path(tmp)
        for filename in FIXTURE_FILES:
            shutil.copyfile(FIXTURES_DIR / filename, directory / filename)

        additions = (
            ("merchants.yaml", scenario.range.merchants),
            ("products.yaml", scenario.range.products),
            ("tasks.yaml", scenario.range.tasks),
        )
        for filename, entries in additions:
            if not entries:
                continue
            path = directory / filename
            existing = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            path.write_text(
                yaml.safe_dump(existing + entries, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

        # Load once here so a malformed entry fails before the campaign starts
        # rather than inside the first episode, where the traceback would point
        # at the executor instead of at the scenario.
        Catalog.load(directory)
        yield directory


def _defense(tiers: list[int]) -> Defense | None:
    if not tiers:
        return None
    anomaly = AnomalyTier()
    if 2 in tiers and MODEL_PATH.exists():
        anomaly.load(MODEL_PATH)
    return Defense(tiers=tuple(tiers), anomaly=anomaly)


def run(scenario: Scenario, *, out_dir: Path | str = Path("results")) -> list[Episode]:
    """Run the scenario and write its campaign where the arena will find it."""
    out_dir = Path(out_dir)
    defense = _defense(scenario.control)

    with prepared_range(scenario) as fixtures:
        if scenario.adaptive:
            # `defense` is never None here: validation rejects rounds > 1 with
            # no control, because there would be nothing to adapt against.
            result = run_adaptive_campaign(
                rounds=scenario.rounds,
                seed=scenario.seed,
                profile=scenario.rail,
                defense=defense,
                task_id=scenario.tasks[0],
                attacks=scenario.attacks,
                fixtures=fixtures,
            )
            episodes = result.episodes
        else:
            episodes = run_campaign(
                seed=scenario.seed,
                repeats=scenario.repeats,
                profile=scenario.rail,
                defense=defense,
                tasks=scenario.tasks,
                attacks=scenario.attacks,
                fixtures=fixtures,
            )

    path = write_jsonl(episodes, out_dir / f"{scenario.id}.jsonl")
    path.with_suffix(".meta.json").write_text(
        json.dumps(scenario.meta(), indent=2) + "\n", encoding="utf-8"
    )
    return episodes


def report(scenario: Scenario, episodes: list[Episode], out: Path) -> None:
    attacked = [e for e in episodes if e.attack_id != "benign"]

    print(RULE)
    print(f"PRAMAN  ·  SCENARIO  ·  {scenario.id}")
    print(RULE)
    print(f"\n  {scenario.name}")
    if scenario.description:
        print(f"  {scenario.description}")

    control = (
        "undefended"
        if not scenario.control
        else "Tier " + "+".join(str(t) for t in scenario.control)
    )
    print(f"\n  rail                 {scenario.rail}")
    print(f"  control              {control}")
    print(f"  rounds               {scenario.rounds}")
    print(f"  seed                 {scenario.seed}")

    print(f"\n  {'attack':<10} {'ASR':>7} {'moved':>14}")
    print(f"  {'-' * 10} {'-' * 7} {'-' * 14}")
    for attack_id, rate in sorted(metrics.asr_by_attack(attacked).items()):
        rows = [e for e in attacked if e.attack_id == attack_id]
        print(f"  {attack_id:<10} {rate:>6.0%} {fmt(metrics.rupees_moved(rows)):>14}")

    print(f"\n  {'-' * 74}")
    print(f"  ASR                  {metrics.asr(episodes):.1%}")
    print(f"  moved                {fmt(metrics.rupees_moved(episodes))}")
    print(f"  benign pass rate     {metrics.benign_pass_rate(episodes):.1%}")
    print(f"  episodes             {len(episodes)}")
    print(f"\n  wrote {out}")
    print("  it is in the arena now — reload the page and pick it from the sidebar\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m praman run",
        description="Praman — run a scenario written in YAML",
    )
    parser.add_argument("scenario", type=Path, help="path to a scenario .yaml")
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args(argv)
    console_setup()

    try:
        scenario = load(args.scenario)
    except ScenarioError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2

    episodes = run(scenario, out_dir=args.out)
    report(scenario, episodes, args.out / f"{scenario.id}.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
