"""The commands a judge actually types.

Every other test exercises a function. These run the workflows the README
documents, end to end, through the same entry point a person uses — because
the one thing no unit test caught was `python -m praman demo` raising
AttributeError before it printed a single mandate. It had reimplemented the
agent's `shop()` and drifted: it passed a Task where an IntentMandate was
required. The harness was fine. The front door was not.

`demo` is the first command in the README and the simplest thing that has to
work, so it is the first thing checked here.
"""

from __future__ import annotations

from importlib import import_module

import pytest

from praman.__main__ import COMMANDS, dispatch


def test_every_advertised_command_can_be_reached():
    """A command in the help that nothing dispatches used to return a bare 1."""
    for name, (blurb, target) in COMMANDS.items():
        assert blurb, f"{name} has no description"
        if callable(target):
            continue
        module = import_module(target)
        assert callable(getattr(module, "main", None)), f"{target} has no main(argv)"


def test_the_honest_purchase_settles(capsys):
    """No model, no attack, no defense: a signed chain and a balanced ledger."""
    assert dispatch("demo", []) == 0

    out = capsys.readouterr().out
    assert "SETTLED" in out
    assert "money conserved:    yes" in out
    # The demo builds its chain through ScriptedAgent.shop, so the three
    # mandates it prints are the ones every campaign runs against.
    for link in ("INTENT", "CART", "PAYMENT"):
        assert link in out
    assert "INVALID" not in out, "a signature did not verify on the honest path"


@pytest.mark.parametrize("profile", ["autopay", "uap"])
def test_the_honest_purchase_settles_on_every_rail(profile, capsys):
    assert dispatch("demo", ["--profile", profile]) == 0
    assert "SETTLED" in capsys.readouterr().out


def test_the_attack_map_prints_every_surface(capsys):
    assert dispatch("corpus", []) == 0

    out = capsys.readouterr().out
    from praman.red.corpus import SURFACES, load_corpus

    for surface in SURFACES:
        assert surface.upper() in out
    for seed in load_corpus():
        assert seed.id in out, f"{seed.id} is mapped but the report does not print it"


def test_detection_efficacy_reads_the_committed_campaigns(capsys):
    assert dispatch("detect", []) == 0

    out = capsys.readouterr().out
    # Both columns, always. Either alone tells a flattering half of the story.
    assert "DETECTION IS NOT PREVENTION" in out
    for column in ("P", "R", "F1", "FPR", "ASR"):
        assert column in out


def test_a_campaign_runs_and_writes_where_it_is_told(tmp_path, capsys):
    out_file = tmp_path / "campaign.jsonl"
    assert dispatch("campaign", ["--repeats", "1", "--tiers", "1", "--out", str(out_file)]) == 0
    assert out_file.exists()
    assert "benign pass rate     100.0%" in capsys.readouterr().out


def test_a_scenario_runs_from_its_yaml(tmp_path, capsys):
    assert dispatch("run", ["scenarios/convenience-fee.yaml", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "convenience-fee.jsonl").exists()
    assert "SCENARIO" in capsys.readouterr().out


def test_the_arena_exports_as_static_files(tmp_path, capsys):
    assert dispatch("export", ["--out", str(tmp_path / "dist")]) == 0

    dist = tmp_path / "dist"
    assert (dist / "index.html").exists()
    assert (dist / "api" / "campaigns").exists()
    assert (dist / "api" / "health").exists()
    assert "STATIC EXPORT" in capsys.readouterr().out
