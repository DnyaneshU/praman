"""The local-model victim, and the outcomes that must never be miscounted.

Most of this file runs without Ollama. The parts that need a served model skip
rather than fail, because CI has no GPU and a judge cloning the repo may not
have pulled anything — neither should see a red suite for a study that is an
extension, not the core claim.

What is asserted unconditionally is the accounting: a model that declines is a
`refusal` and a model that answers nonsense is an `error`, and neither is ever
allowed to look like a defended attack. That is the arithmetic the headline
number rests on, and it holds whether or not a model is running.
"""

import json
import urllib.error
import urllib.request

import pytest

from praman.range.catalog import Catalog
from praman.range.context import RangeContext
from praman.range.ollama_agent import (
    OLLAMA_URL,
    AgentConfused,
    AgentRefusal,
    OllamaAgent,
)
from praman.red.attacks import get_attack
from praman.red.executor import run_episode


def ollama_models() -> set[str]:
    """Models this machine can actually serve, or an empty set."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
            body = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return set()
    return {m["name"] for m in body.get("models", [])}


AVAILABLE = ollama_models()
needs_ollama = pytest.mark.skipif(not AVAILABLE, reason="ollama is not serving any model")


class _StubAgent(OllamaAgent):
    """An OllamaAgent whose model always says one fixed thing."""

    def __init__(self, reply: str) -> None:
        super().__init__(model="stub")
        self._reply = reply

    def _ask(self, prompt: str) -> str:  # noqa: ARG002 - prompt is irrelevant to a stub
        return self._reply


# -- accounting, no model required ------------------------------------------


def _shop(reply: str):
    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        return _StubAgent(reply).shop(ctx.catalog.task("task-shoes"), ctx)
    finally:
        ctx.ledger.close()


def test_a_refusal_is_a_refusal_not_a_block():
    """A model that would not answer has not been defended against."""
    with pytest.raises(AgentRefusal):
        _shop("I cannot help with that request.")


def test_an_unparseable_reply_is_an_error():
    with pytest.raises(AgentConfused):
        _shop("Sure! I'd recommend the blue ones.")


def test_a_sku_that_was_never_offered_is_an_error():
    """Hallucinating a plausible SKU must not silently become a purchase."""
    with pytest.raises(AgentConfused):
        _shop("SKU-9999")


def test_a_valid_choice_becomes_a_signed_chain():
    chain = _shop("SKU-1001")
    assert chain.cart.items[0].sku == "SKU-1001"
    assert chain.payment.signature


def test_refusals_are_recorded_on_the_episode_and_excluded_from_rates():
    """The outcome exists so this number cannot quietly flatter the defense."""
    from praman import metrics

    episode = run_episode(
        episode_id="r",
        attack=get_attack("S-02"),
        task_id="task-shoes",
        seed=1729,
        agent=_StubAgent("I cannot assist with that."),
    )
    assert episode.outcome == "refusal"
    assert episode.rupees_moved == 0
    assert metrics.asr([episode]) == 0.0
    assert metrics.refusal_rate([episode]) == 1.0


def test_the_model_name_is_recorded_so_results_can_be_split_by_tier():
    assert OllamaAgent(model="llama3.2:3b").model_name == "ollama:llama3.2:3b"


def _ask_against(monkeypatch, error: Exception) -> str:
    """Drive `_ask` against a transport that fails a particular way.

    Against a real server this needed Ollama running to produce a 404 — so it
    passed on the one machine that had it and failed on every other, which is
    the opposite of what a test in the no-model-required half of this file is
    for. What is actually under test is how a failure is *explained*, and that
    is ours, not the server's.
    """
    agent = OllamaAgent(model="definitely-not-pulled:1b")

    def refuse(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(AgentConfused) as raised:
        agent._ask("hello")
    return str(raised.value)


def test_a_missing_model_says_how_to_fix_it(monkeypatch):
    """A 404 means the model is not pulled, which has an obvious fix."""
    not_found = urllib.error.HTTPError(OLLAMA_URL, 404, "Not Found", None, None)
    assert "ollama pull definitely-not-pulled:1b" in _ask_against(monkeypatch, not_found)


def test_a_dead_server_is_not_reported_as_a_missing_model(monkeypatch):
    """The sibling case, and the one that used to be reported for both."""
    message = _ask_against(monkeypatch, urllib.error.URLError("connection refused"))
    assert "ollama serve" in message
    assert "ollama pull" not in message


def test_any_other_http_error_keeps_its_status(monkeypatch):
    """A 500 is neither a missing model nor a dead server. Say which it is."""
    boom = urllib.error.HTTPError(OLLAMA_URL, 500, "Internal Server Error", None, None)
    assert "500" in _ask_against(monkeypatch, boom)


def test_the_poisoned_listing_is_offered_even_outside_the_intents_categories():
    """M-08's whole job is to pull the agent outside its brief.

    If the whispered listing were filtered out before the model saw it, the
    attack could not be tested at all and a 0% result would mean nothing.
    """
    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        get_attack("M-08").prepare(ctx)
        intent = ctx.profile.build_intent(Catalog.load().task("task-shoes"))
        offered = OllamaAgent()._offered(intent, ctx)
        assert any(p.injected_note for p in offered)
        assert any(p.category not in intent.allowed_categories for p in offered)
    finally:
        ctx.ledger.close()


# -- with a real model ------------------------------------------------------


@needs_ollama
def test_a_served_model_shops_within_its_budget():
    model = sorted(AVAILABLE)[0]
    ctx = RangeContext.build(":memory:", seed=1729)
    try:
        task = ctx.catalog.task("task-shoes")
        chain = OllamaAgent(model=model).shop(task, ctx)
        assert chain.cart.total <= chain.intent.max_amount
        assert chain.payment.signature
    finally:
        ctx.ledger.close()


@needs_ollama
def test_structural_attacks_do_not_care_which_model_is_shopping():
    """The study's central claim, as an assertion.

    S-02 changes one field in the payment mandate. Nothing about that involves
    the agent's judgement, so a served model must be exactly as vulnerable as
    the scripted one — which is the argument for a control-layer fix.
    """
    model = sorted(AVAILABLE)[0]
    episode = run_episode(
        episode_id="s",
        attack=get_attack("S-02"),
        task_id="task-shoes",
        seed=1729,
        agent=OllamaAgent(model=model),
    )
    assert episode.succeeded
    assert episode.victim_model == f"ollama:{model}"
