"""The arena's API, and the property the deployment depends on.

The single most important assertion here is that this module imports and
serves with **no `ANTHROPIC_API_KEY` present**. The deployed arena has no
credential, so a client constructed at import time turns into a crash on a
public URL at the worst possible moment. It is a one-line test that stops a
whole class of 3am failure.
"""

import importlib
import json

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


def test_a_campaign_carries_its_summary_and_every_episode(client):
    """One response holds everything the arena draws.

    This is what replaced the replay WebSocket. That socket read a file it had
    already finished reading and sent it back with a sleep between the lines —
    it carried no field this endpoint does not, so it was transporting delays
    rather than data. Pacing is a `setTimeout` in arena.js now, which is also
    what lets the arena deploy as static files.
    """
    campaign_id = client.get("/api/campaigns").json()[0]["id"]
    body = client.get(f"/api/campaign/{campaign_id}").json()

    assert body["episodes"]
    assert body["summary"]["episodes"] == len(body["episodes"])
    assert {"asr", "benign_pass_rate", "rupees_moved"} <= set(body["summary"])


def test_episodes_carry_the_chain_the_arena_draws(client):
    campaign_id = client.get("/api/campaigns").json()[0]["id"]
    episode = client.get(f"/api/campaign/{campaign_id}").json()["episodes"][0]

    snapshot = episode["snapshot"]
    assert snapshot is not None
    assert {"payment_beneficiary", "expected_beneficiary", "items"} <= set(snapshot)


def test_replay_mode_refuses_to_start_a_campaign(results, monkeypatch):
    """A public URL that can start campaigns is a public URL anyone can bill."""
    client = make_client(results, monkeypatch, "replay")
    assert client.get("/api/health").json()["mode"] == "replay"
    assert client.post("/api/campaign/start").status_code == 403


def test_the_arena_page_and_its_assets_are_served(client):
    """From the root, not /static.

    The page references its own assets relatively so the identical files work
    here and in the static export under a project path. Mounting at the root is
    what makes those relative paths resolve.
    """
    index = client.get("/")
    assert index.status_code == 200
    assert "Praman Arena" in index.text
    for asset in ("arena.css", "arena.js", "components.js", "format.js"):
        assert client.get(f"/{asset}").status_code == 200, asset


def test_the_api_still_wins_against_a_root_mount(client):
    """The arena is mounted greedily at /. Every API route must still match."""
    assert client.get("/api/health").json()["status"] == "ok"
    assert isinstance(client.get("/api/campaigns").json(), list)


def test_vue_is_vendored_rather_than_fetched_from_a_cdn(client):
    """A demo that needs the internet is a demo that fails in the room."""
    response = client.get("/vendor/vue.global.prod.js")
    assert response.status_code == 200
    assert len(response.content) > 100_000


# -- the static export ------------------------------------------------------


def test_the_export_answers_the_same_things_the_api_does(client, results, tmp_path):
    """Same paths, same payloads — that is the whole contract.

    The arena fetches relatively, so one frontend serves both this API at the
    root and a static export under a project path. That only holds while the
    export writes what the endpoints return, at the endpoints' own paths.
    """
    from praman.api.export import export

    export(results=results, into=tmp_path / "dist")
    dist = tmp_path / "dist"

    served = client.get("/api/campaigns").json()
    exported = json.loads((dist / "api" / "campaigns").read_text(encoding="utf-8"))
    assert exported == served

    for campaign in served:
        path = dist / "api" / "campaign" / campaign["id"]
        assert path.is_file(), f"{campaign['id']} is in the listing but not exported"
        assert (
            json.loads(path.read_text(encoding="utf-8"))
            == client.get(f"/api/campaign/{campaign['id']}").json()
        )


def test_the_export_says_it_has_no_server(results, tmp_path):
    """The masthead reads what is true. There is no mode to enforce here."""
    from praman.api.export import export

    export(results=results, into=tmp_path / "dist")
    health = json.loads((tmp_path / "dist" / "api" / "health").read_text(encoding="utf-8"))
    assert health["mode"] == "static"


def test_the_export_carries_the_whole_frontend(results, tmp_path):
    from praman.api.export import export

    export(results=results, into=tmp_path / "dist")
    dist = tmp_path / "dist"
    for asset in (
        "index.html",
        "arena.js",
        "arena.css",
        "components.js",
        "format.js",
        "vendor/vue.global.prod.js",
        "vendor/fonts.css",
    ):
        assert (dist / asset).is_file(), asset


def test_the_export_references_nothing_absolute(results, tmp_path):
    """An absolute path works at the root and 404s under /praman/.

    This is the failure that a static host produces and a local server hides,
    so it is asserted rather than discovered on the deployed URL.
    """
    import re

    from praman.api.export import export

    export(results=results, into=tmp_path / "dist")
    dist = tmp_path / "dist"

    html = (dist / "index.html").read_text(encoding="utf-8")
    absolute = [r for r in re.findall(r'(?:href|src)="([^"]+)"', html) if r.startswith("/")]
    assert not absolute, f"index.html references absolute paths: {absolute}"

    js = (dist / "arena.js").read_text(encoding="utf-8")
    assert not re.search(r'fetch\(\s*[`"\']/', js), "arena.js fetches an absolute path"


def test_a_stale_campaign_does_not_survive_a_re_export(results, tmp_path):
    """The export replaces its directory rather than merging into it.

    A campaign deleted from results/ must not linger in a deploy as a row the
    data no longer backs.
    """
    from praman.api.export import export

    dist = tmp_path / "dist"
    export(results=results, into=dist)
    ghost = dist / "api" / "campaign" / "deleted-last-week"
    ghost.write_text("{}", encoding="utf-8")

    export(results=results, into=dist)
    assert not ghost.exists()
