"""Scenarios — the path by which a test case arrives without a code change.

The format's whole value is that a teammate can write one and be told, in one
pass and by name, everything wrong with it. Most of this file is therefore
about the rejections rather than the happy path: a scenario that silently ran
the wrong thing would be worse than one that refused to run at all.

The registry is global and a scenario's attacks join it, so every test that
loads one restores it afterwards. Without that, `test_corpus.py` — which
asserts the shipped corpus and the registry agree exactly — fails depending on
which order pytest happened to pick.
"""

from __future__ import annotations

import json
import sys

import pytest
import yaml

from praman.range.catalog import FIXTURES_DIR, Catalog
from praman.red.attacks import ATTACKS
from praman.scenario import Scenario, ScenarioError, load, prepared_range, run

EXAMPLE = "scenarios/convenience-fee.yaml"

MINIMAL = {
    "id": "unit-test",
    "name": "Unit test scenario",
    "control": [1],
    "repeats": 1,
    "tasks": ["task-shoes"],
    "attacks": ["S-02"],
}


@pytest.fixture(autouse=True)
def isolated_registry():
    """Scenario attacks join the global corpus. Put it back afterwards."""
    before = dict(ATTACKS)
    modules = set(sys.modules)
    yield
    ATTACKS.clear()
    ATTACKS.update(before)
    for name in set(sys.modules) - modules:
        if name.startswith("praman_scenario_attacks_"):
            del sys.modules[name]


def write(tmp_path, **overrides):
    """A scenario file built from the minimal one, with fields replaced."""
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump({**MINIMAL, **overrides}), encoding="utf-8")
    return path


def problems(path) -> list[str]:
    with pytest.raises(ScenarioError) as raised:
        load(path)
    return raised.value.problems


# -- the shipped example ----------------------------------------------------


def test_the_example_scenario_is_valid():
    """It is documentation. Documentation that does not run is a lie."""
    scenario = load(EXAMPLE)
    assert scenario.id == "convenience-fee"
    assert scenario.attacks == ["X-20", "S-02"]


def test_an_external_module_puts_its_attack_in_the_corpus():
    assert "X-20" not in ATTACKS
    load(EXAMPLE)
    assert "X-20" in ATTACKS


def test_loading_the_same_scenario_twice_does_not_trip_duplicate_registration():
    """`register` refuses a duplicate id, correctly. Loading twice is not one."""
    load(EXAMPLE)
    load(EXAMPLE)


# -- rejections -------------------------------------------------------------


def test_an_unknown_attack_is_named_and_the_registry_listed(tmp_path):
    found = problems(write(tmp_path, attacks=["S-02", "S-99"]))
    assert any("'S-99'" in p and "S-02" in p for p in found)


def test_an_unknown_task_is_named(tmp_path):
    assert any("'task-yacht'" in p for p in problems(write(tmp_path, tasks=["task-yacht"])))


def test_an_unknown_rail_is_named(tmp_path):
    assert any("'sepa'" in p for p in problems(write(tmp_path, rail="sepa")))


def test_redefining_a_shipped_merchant_is_refused(tmp_path):
    """Silently overriding one would move Tier 2's boundary with no trace."""
    overlay = {"merchants": [{"id": "merchant_0250", "name": "Not really"}]}
    found = problems(write(tmp_path, range=overlay))
    assert any("merchant_0250" in p and "do not redefine" in p for p in found)


def test_a_product_sold_by_an_unknown_merchant_is_refused(tmp_path):
    overlay = {"products": [{"sku": "SKU-9001", "merchant_id": "merchant_nope"}]}
    found = problems(write(tmp_path, range=overlay))
    assert any("'merchant_nope'" in p for p in found)


def test_a_product_may_be_sold_by_a_merchant_the_same_scenario_adds(tmp_path):
    """The overlay is one unit: order within it must not matter."""
    overlay = {
        "products": [{"sku": "SKU-9001", "merchant_id": "merchant_9000"}],
        "merchants": [{"id": "merchant_9000"}],
    }
    load(write(tmp_path, range=overlay))


def test_a_mistyped_key_is_rejected_rather_than_ignored(tmp_path):
    """`attack:` for `attacks:` would run the whole corpus and look fine."""
    path = tmp_path / "typo.yaml"
    path.write_text(yaml.safe_dump({**MINIMAL, "attack": ["S-02"]}), encoding="utf-8")
    with pytest.raises(Exception, match="attack"):
        load(path)


def test_adaptive_with_no_control_is_refused(tmp_path):
    """Nothing refuses, so nothing adapts, and round 0 is the whole campaign."""
    found = problems(write(tmp_path, rounds=4, control=[]))
    assert any("adapt" in p for p in found)


def test_every_problem_is_reported_at_once(tmp_path):
    """Three runs to find three typos is how five minutes becomes an afternoon."""
    found = problems(write(tmp_path, rail="sepa", tasks=["task-yacht"], attacks=["S-99"]))
    assert len(found) >= 3


def test_a_missing_attack_module_is_named(tmp_path):
    found = problems(write(tmp_path, attack_modules=["attacks/nope.py"]))
    assert any("nope.py" in p for p in found)


# -- the range overlay ------------------------------------------------------


def test_no_overlay_means_the_shipped_range_untouched(tmp_path):
    with prepared_range(load(write(tmp_path))) as directory:
        assert directory == FIXTURES_DIR


def test_an_overlay_adds_to_the_shipped_range_without_replacing_it(tmp_path):
    scenario = load(EXAMPLE)
    with prepared_range(scenario) as directory:
        catalog = Catalog.load(directory)

    assert "task-groceries" in catalog.tasks
    assert "merchant_0410" in catalog.merchants
    # The shipped population is what every threshold is calibrated against.
    assert "merchant_0250" in catalog.merchants
    assert "task-shoes" in catalog.tasks


def test_the_overlay_directory_does_not_outlive_the_run(tmp_path):
    scenario = load(EXAMPLE)
    with prepared_range(scenario) as directory:
        pass
    assert not directory.exists()


# -- running ----------------------------------------------------------------


def test_running_writes_a_campaign_and_a_sidecar(tmp_path):
    scenario = load(EXAMPLE)
    scenario = scenario.model_copy(update={"repeats": 1, "source": scenario.source})
    episodes = run(scenario, out_dir=tmp_path)

    assert episodes
    assert (tmp_path / "convenience-fee.jsonl").is_file()
    meta = json.loads((tmp_path / "convenience-fee.meta.json").read_text(encoding="utf-8"))
    assert meta["name"] == scenario.name


def test_the_scenarys_attack_is_stopped_by_the_invariant_it_targets(tmp_path):
    """X-20 exists to exercise inv-03, which no shipped attack reaches.

    An invariant nothing attacks is an invariant nobody has evidence for, so
    the example is only worth shipping if it actually lands there.
    """
    scenario = load(EXAMPLE)
    scenario = scenario.model_copy(update={"repeats": 1, "source": scenario.source})
    episodes = run(scenario, out_dir=tmp_path)

    skims = [e for e in episodes if e.attack_id == "X-20"]
    assert skims
    assert all(e.violated_invariant == "inv-03" for e in skims)
    assert all(e.rupees_moved == 0 for e in skims)


def test_the_scenarys_attack_takes_money_when_nothing_stops_it(tmp_path):
    """0% against a control means nothing until you see the 100% it started at."""
    scenario = load(EXAMPLE)
    undefended = scenario.model_copy(
        update={"id": "baseline", "control": [], "repeats": 1, "source": scenario.source}
    )
    episodes = run(undefended, out_dir=tmp_path)

    skims = [e for e in episodes if e.attack_id == "X-20"]
    assert all(e.rupees_moved > 0 for e in skims)


def test_only_the_requested_attacks_run(tmp_path):
    scenario = load(write(tmp_path, attacks=["S-02"]))
    episodes = run(scenario, out_dir=tmp_path)
    assert {e.attack_id for e in episodes} == {"S-02", "benign"}


def test_a_campaign_still_carries_benign_traffic(tmp_path):
    """Without it there is no false-positive rate, and no way to read the ASR."""
    scenario = load(write(tmp_path))
    episodes = run(scenario, out_dir=tmp_path)
    assert any(e.attack_id == "benign" for e in episodes)


def test_the_defaults_are_the_shipped_campaign_shape():
    """A scenario with only an id and a name still describes a real campaign."""
    scenario = Scenario(id="x", name="X")
    assert scenario.rail == "autopay"
    assert scenario.control == [1]
    assert scenario.tasks == ["task-shoes", "task-trainer"]
    assert scenario.attacks is None
    assert not scenario.adaptive
