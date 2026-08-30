"""Fixtures every test module gets.

The attack corpus is a module-level registry that `@register` writes into at
import time, and a scenario's `attack_modules` add to it by executing a file.
That is the right design for the product — a teammate drops a .py beside their
YAML and their attack is in the corpus — but it means *loading a scenario
mutates global state that outlives the test that did it*.

This lived in `test_scenario.py`, which is the module that thought of it. It
was not enough: `test_cli.py` runs `praman run scenarios/convenience-fee.yaml`
through the real entry point, which registered `X-20` for the rest of the
session and made `test_corpus.py` fail — but only when the CLI tests ran first,
so the suite passed or failed on alphabetical order. A guard that protects one
module protects nothing.
"""

from __future__ import annotations

import sys

import pytest

from praman.red.attacks import ATTACKS


@pytest.fixture(autouse=True)
def isolated_registry():
    """Put the corpus back the way it was found.

    `sys.modules` matters as much as the registry: `_import_attack_modules`
    skips a module it has already executed, so restoring `ATTACKS` without
    forgetting the module leaves the attack unregistered *and* unloadable.
    """
    before = dict(ATTACKS)
    modules = set(sys.modules)
    yield
    ATTACKS.clear()
    ATTACKS.update(before)
    for name in set(sys.modules) - modules:
        if name.startswith("praman_scenario_attacks_"):
            del sys.modules[name]
