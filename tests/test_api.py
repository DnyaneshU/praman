"""The arena's API, and the property the deployment depends on.

The single most important assertion here is that this module imports and
serves with **no `ANTHROPIC_API_KEY` present**. The deployed arena has no
credential, so a client constructed at import time turns into a crash on a
public URL at the worst possible moment. It is a one-line test that stops a
whole class of 3am failure.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from praman.red.runner import run_campaign


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """A small committed-campaign directory, standing in for `results/`."""
    directory = tmp_path_factory.mktemp("results")
    from praman.blue.defense import Defense
    from praman.red.episode import write_jsonl

    write_jsonl(run_campaign(repeats=1, defense=Defense(tiers=(1,))), directory / "tier1.jsonl")
    return directory


@pytest.fixture
def client(results, monkeypatch):
    monkeypatch.setenv("PRAMAN_RESULTS", str(results))
    monkeypatch.delenv("PRAMAN_MODE", raising=False)
    import praman.api.main as main

    importlib.reload(main)
    return TestClient(main.app)


def make_client(results, monkeypatch, mode: str) -> TestClient:
    monkeypatch.setenv("PRAMAN_RESULTS", str(results))
    monkeypatch.setenv("PRAMAN_MODE", mode)
    import praman.api.main as main

    importlib.reload(main)
    return TestClient(main.app)


def test_the_app_imports_without_a_credential(monkeypatch):
    """The deployment has no key. Importing must not need one."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import praman.api.main as main

    importlib.reload(main)
    assert main.app is not None
    assert TestClient(main.app).get("/api/health").status_code == 200


def test_health_reports_the_mode(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["mode"] in {"live", "replay"}


def test_campaigns_are_listed_with_their_headline_numbers(client):
    campaigns = client.get("/api/campaigns").json()
    assert campaigns
    first = campaigns[0]
    assert {"id", "episodes", "rounds", "asr", "moved"} <= set(first)


def test_a_campaign_carries_its_summary_and_episodes(client):
    campaign_id = client.get("/api/campaigns").json()[0]["id"]
    body = client.get(f"/api/campaign/{campaign_id}").json()
    assert body["episodes"]
    assert "adaptive_delta" in body["summary"]


def test_an_unknown_campaign_is_a_404_not_a_crash(client):
    assert client.get("/api/campaign/nope").status_code == 404


def test_replay_streams_a_summary_then_episodes_then_done(client):
    campaign_id = client.get("/api/campaigns").json()[0]["id"]
    kinds = []
    with client.websocket_connect(f"/ws/replay/{campaign_id}") as ws:
        while True:
            message = ws.receive_json()
            kinds.append(message["type"])
            if message["type"] == "done" or len(kinds) > 200:
                break

    assert kinds[0] == "summary"
    assert kinds[-1] == "done"
    assert "episode" in kinds


def test_replayed_episodes_carry_the_chain_the_arena_draws(client):
    campaign_id = client.get("/api/campaigns").json()[0]["id"]
    with client.websocket_connect(f"/ws/replay/{campaign_id}") as ws:
        ws.receive_json()  # summary
        episode = ws.receive_json()["episode"]

    snapshot = episode["snapshot"]
    assert snapshot is not None
    assert {"payment_beneficiary", "expected_beneficiary", "items"} <= set(snapshot)


def test_replaying_an_unknown_campaign_reports_an_error_frame(client):
    with client.websocket_connect("/ws/replay/nope") as ws:
        assert ws.receive_json()["type"] == "error"


def test_replay_mode_refuses_to_start_a_campaign(results, monkeypatch):
    """A public URL that can start campaigns is a public URL anyone can bill."""
    client = make_client(results, monkeypatch, "replay")
    assert client.get("/api/health").json()["mode"] == "replay"
    assert client.post("/api/campaign/start").status_code == 403


def test_the_arena_page_and_its_assets_are_served(client):
    assert client.get("/").status_code == 200
    for asset in ("arena.css", "arena.js", "components.js", "format.js"):
        assert client.get(f"/static/{asset}").status_code == 200, asset


def test_vue_is_vendored_rather_than_fetched_from_a_cdn(client):
    """A demo that needs the internet is a demo that fails in the room."""
    response = client.get("/static/vendor/vue.global.prod.js")
    assert response.status_code == 200
    assert len(response.content) > 100_000
