"""API tests using FastAPI TestClient (synchronous).

Tests each endpoint for correct status codes, response shapes,
and domain-error-to-HTTP mappings.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from anneal.api.app import create_app
from anneal.api.deps import _state
from tests.fakes import FakeLLMClient


@pytest.fixture()
def client(monkeypatch):
    """Fresh TestClient per test — each test gets a clean in-memory state.

    Using the context manager form ensures the lifespan (startup/shutdown)
    runs, which initialises in-memory stores and services.

    Sets LLM env vars to empty strings so load_dotenv (override=False)
    won't fill them from .env — no real LLM client is created.  Tests
    that need an LLM use separate fixtures that inject a FakeLLMClient.
    """
    monkeypatch.setenv("ANNEAL_LLM_KEY", "")
    monkeypatch.setenv("ANNEAL_LLM_MODEL", "")
    monkeypatch.delenv("ANNEAL_DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _park(client: TestClient, library_id: str = "lib-1", body: str = "test idea", kind: str = "idea") -> dict:
    """Park an idea and return the response JSON."""
    resp = client.post("/api/v1/park", json={"library_id": library_id, "body": body, "kind": kind})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _start_grill(client: TestClient, artifact_id: str, kind: str = "idea") -> dict:
    resp = client.post(f"/api/v1/grill/{artifact_id}/start", json={"kind": kind})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _challenge(client: TestClient, artifact_id: str, claim_id: str, question: str = "Why?") -> dict:
    resp = client.post(
        f"/api/v1/grill/{artifact_id}/challenge",
        json={"claim_id": claim_id, "question": question},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _answer(client: TestClient, artifact_id: str, claim_id: str, response: str = "Because.") -> dict:
    resp = client.post(
        f"/api/v1/grill/{artifact_id}/answer",
        json={"claim_id": claim_id, "response": response},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _verdict(client: TestClient, artifact_id: str, claim_id: str, outcome: str = "survive", rationale: str = "solid") -> dict:
    resp = client.post(
        f"/api/v1/grill/{artifact_id}/verdict",
        json={"claim_id": claim_id, "outcome": outcome, "rationale": rationale},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _confirm(client: TestClient, artifact_id: str, event_id: str) -> dict:
    resp = client.post(
        f"/api/v1/events/{artifact_id}/confirm",
        json={"event_id": event_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Park tests
# ---------------------------------------------------------------------------


class TestPark:
    def test_park_returns_artifact_and_claim(self, client: TestClient):
        data = _park(client)
        assert "artifact" in data
        assert "claim" in data
        assert data["artifact"]["kind"] == "idea"
        assert data["claim"]["body"] == "test idea"

    def test_park_unsupported_kind_returns_400(self, client: TestClient):
        resp = client.post("/api/v1/park", json={"library_id": "lib-1", "body": "x", "kind": "paper"})
        assert resp.status_code == 400

    def test_list_parked(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        resp = client.get("/api/v1/park", params={"library_id": "lib-1"})
        assert resp.status_code == 200
        assert artifact_id in resp.json()["artifact_ids"]


# ---------------------------------------------------------------------------
# GET endpoint tests
# ---------------------------------------------------------------------------


class TestGetEndpoints:
    def test_get_artifact(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        resp = client.get(f"/api/v1/artifact/{artifact_id}")
        assert resp.status_code == 200
        assert resp.json()["artifact"]["id"] == artifact_id

    def test_get_artifact_not_found(self, client: TestClient):
        resp = client.get("/api/v1/artifact/nonexistent")
        assert resp.status_code == 404

    def test_get_claim(self, client: TestClient):
        data = _park(client)
        claim_id = data["claim"]["id"]
        resp = client.get(f"/api/v1/claim/{claim_id}")
        assert resp.status_code == 200
        assert resp.json()["claim"]["id"] == claim_id

    def test_get_claim_not_found(self, client: TestClient):
        resp = client.get("/api/v1/claim/nonexistent")
        assert resp.status_code == 404

    def test_list_artifacts(self, client: TestClient):
        _park(client, library_id="lib-list")
        _park(client, library_id="lib-list", body="second idea")
        resp = client.get("/api/v1/artifacts", params={"library_id": "lib-list"})
        assert resp.status_code == 200
        assert len(resp.json()["artifacts"]) == 2

    def test_list_artifacts_empty(self, client: TestClient):
        resp = client.get("/api/v1/artifacts", params={"library_id": "empty"})
        assert resp.status_code == 200
        assert resp.json()["artifacts"] == []


# ---------------------------------------------------------------------------
# Grill tests
# ---------------------------------------------------------------------------


class TestGrill:
    def test_start_grill(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        resp = client.post(f"/api/v1/grill/{artifact_id}/start", json={"kind": "idea"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "grill_started"

    def test_challenge_returns_event(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        result = _challenge(client, artifact_id, claim_id)
        assert "event" in result
        assert result["event"]["type"] == "challenge"

    def test_answer_returns_event(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        _challenge(client, artifact_id, claim_id)
        result = _answer(client, artifact_id, claim_id)
        assert "event" in result
        assert result["event"]["type"] == "answer"

    def test_verdict_returns_event(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        _challenge(client, artifact_id, claim_id)
        _answer(client, artifact_id, claim_id)
        result = _verdict(client, artifact_id, claim_id)
        assert "event" in result
        assert result["event"]["type"] == "verdict"
        assert result["event"]["payload"]["outcome"] == "survive"

    def test_bypass_returns_event(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        _challenge(client, artifact_id, claim_id)
        resp = client.post(
            f"/api/v1/grill/{artifact_id}/bypass",
            json={"claim_id": claim_id},
        )
        assert resp.status_code == 200
        event = resp.json()["event"]
        assert event["debt"] is True


# ---------------------------------------------------------------------------
# Promote tests
# ---------------------------------------------------------------------------


class TestPromote:
    def test_promote_with_debt_returns_409(self, client: TestClient):
        """Bypass creates debt; promote should be blocked."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        _challenge(client, artifact_id, claim_id)
        # Bypass creates a survive verdict with debt=True
        client.post(
            f"/api/v1/grill/{artifact_id}/bypass",
            json={"claim_id": claim_id},
        )
        resp = client.post(f"/api/v1/promote/{artifact_id}/{claim_id}")
        assert resp.status_code == 409

    def test_promote_after_clearing_debt(self, client: TestClient):
        """Clear debt via confirm, then promote succeeds."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        _challenge(client, artifact_id, claim_id)

        # Bypass creates debt
        bypass_resp = client.post(
            f"/api/v1/grill/{artifact_id}/bypass",
            json={"claim_id": claim_id},
        )
        bypass_event_id = bypass_resp.json()["event"]["id"]

        # Confirm the bypass event to clear debt
        _confirm(client, artifact_id, bypass_event_id)

        # Now promote should succeed
        resp = client.post(f"/api/v1/promote/{artifact_id}/{claim_id}")
        assert resp.status_code == 200
        assert resp.json()["event"]["type"] == "promote"

    def test_promote_ungrilled_returns_409(self, client: TestClient):
        """Cannot promote a claim that hasn't survived grill."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        resp = client.post(f"/api/v1/promote/{artifact_id}/{claim_id}")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Event (confirmation gate) tests
# ---------------------------------------------------------------------------


class TestEvents:
    def test_confirm_event(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        challenge_result = _challenge(client, artifact_id, claim_id)
        event_id = challenge_result["event"]["id"]

        result = _confirm(client, artifact_id, event_id)
        assert result["event"]["type"] == "confirm"
        assert result["event"]["target_ref"] == event_id

    def test_retract_event(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        challenge_result = _challenge(client, artifact_id, claim_id)
        event_id = challenge_result["event"]["id"]

        resp = client.post(
            f"/api/v1/events/{artifact_id}/retract",
            json={"event_id": event_id},
        )
        assert resp.status_code == 200
        assert resp.json()["event"]["type"] == "retract"

    def test_batch_confirm(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)

        c1 = _challenge(client, artifact_id, claim_id)
        c2 = _challenge(client, artifact_id, claim_id, question="Another?")
        ids = [c1["event"]["id"], c2["event"]["id"]]

        resp = client.post(
            f"/api/v1/events/{artifact_id}/batch-confirm",
            json={"event_ids": ids},
        )
        assert resp.status_code == 200
        assert len(resp.json()["events"]) == 2

    def test_pending_events(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        _challenge(client, artifact_id, claim_id)

        resp = client.get(f"/api/v1/events/{artifact_id}/pending")
        assert resp.status_code == 200
        # The challenge event is unconfirmed, so it should be pending
        assert len(resp.json()["events"]) >= 1


# ---------------------------------------------------------------------------
# Projection tests
# ---------------------------------------------------------------------------


class TestProjections:
    def test_trajectory_returns_all_events(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        _challenge(client, artifact_id, claim_id)

        resp = client.get(f"/api/v1/artifact/{artifact_id}/trajectory")
        assert resp.status_code == 200
        events = resp.json()["events"]
        # At least park + challenge
        assert len(events) >= 2
        types = [e["type"] for e in events]
        assert "park" in types
        assert "challenge" in types

    def test_doc_projection(self, client: TestClient):
        """DOC contains only survived, confirmed, no-debt content."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        _challenge(client, artifact_id, claim_id)
        _answer(client, artifact_id, claim_id)
        verdict_result = _verdict(client, artifact_id, claim_id)
        verdict_event_id = verdict_result["event"]["id"]

        # Confirm the verdict
        _confirm(client, artifact_id, verdict_event_id)

        # Promote
        client.post(f"/api/v1/promote/{artifact_id}/{claim_id}")

        resp = client.get(f"/api/v1/artifact/{artifact_id}/doc")
        assert resp.status_code == 200
        doc_events = resp.json()["events"]
        # DOC should have content (at least the answer and verdict)
        assert len(doc_events) >= 1
        # No debt, no killed, no park in DOC
        for e in doc_events:
            assert e["debt"] is False
            assert e["type"] != "park"
            if e["type"] == "verdict":
                assert e["payload"]["outcome"] != "kill"

    def test_versions_empty_for_no_doc_content(self, client: TestClient):
        """A parked-only artifact produces no DOC versions."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]

        resp = client.get(f"/api/v1/artifact/{artifact_id}/versions")
        assert resp.status_code == 200
        assert resp.json() == {"versions": []}

    def test_versions_projection(self, client: TestClient):
        """An artifact whose events produce DOC content emits versions."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        challenge_result = _challenge(client, artifact_id, claim_id)
        _answer(client, artifact_id, claim_id)
        verdict_result = _verdict(client, artifact_id, claim_id)

        # Confirm the challenge + verdict so DOC content materialises.
        _confirm(client, artifact_id, challenge_result["event"]["id"])
        _confirm(client, artifact_id, verdict_result["event"]["id"])

        # Promote so the claim's content lands in the DOC.
        client.post(f"/api/v1/promote/{artifact_id}/{claim_id}")

        resp = client.get(f"/api/v1/artifact/{artifact_id}/versions")
        assert resp.status_code == 200
        versions = resp.json()["versions"]
        assert len(versions) >= 1
        for v in versions:
            assert set(v.keys()) >= {
                "version",
                "ts",
                "triggering_event_id",
                "triggering_event_type",
                "doc",
                "added_event_ids",
                "removed_event_ids",
            }


# ---------------------------------------------------------------------------
# Lens feed tests
# ---------------------------------------------------------------------------


class TestLensFeed:
    def test_lens_feed_parked_artifact_returns_409(self, client: TestClient):
        """Cannot feed a parked artifact to Lens."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        resp = client.post(
            f"/api/v1/lens-feed/{artifact_id}",
            json={"library_id": "lib-1"},
        )
        assert resp.status_code == 409

    def test_lens_feed_after_grill(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        challenge_result = _challenge(client, artifact_id, claim_id)
        _confirm(client, artifact_id, challenge_result["event"]["id"])
        _answer(client, artifact_id, claim_id)
        verdict_result = _verdict(client, artifact_id, claim_id)
        _confirm(client, artifact_id, verdict_result["event"]["id"])

        resp = client.post(
            f"/api/v1/lens-feed/{artifact_id}",
            json={"library_id": "lib-1"},
        )
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) >= 1

    def test_query_lens_feed(self, client: TestClient):
        resp = client.get("/api/v1/lens-feed", params={"library_id": "lib-1"})
        assert resp.status_code == 200
        assert resp.json()["entries"] == []


# ---------------------------------------------------------------------------
# Full end-to-end flow through API
# ---------------------------------------------------------------------------


class TestFullFlow:
    def test_park_grill_verdict_confirm_promote_doc(self, client: TestClient):
        """Full flow: park -> grill -> verdict -> confirm -> promote -> get doc."""
        # 1. Park
        park_data = _park(client, body="quantum entanglement improves ML")
        artifact_id = park_data["artifact"]["id"]
        claim_id = park_data["claim"]["id"]

        # 2. Start grill
        _start_grill(client, artifact_id)

        # 3. Challenge -> answer -> verdict(survive)
        challenge_result = _challenge(client, artifact_id, claim_id, "Evidence?")
        challenge_event_id = challenge_result["event"]["id"]

        answer_result = _answer(client, artifact_id, claim_id, "Paper XYZ shows...")

        verdict_result = _verdict(client, artifact_id, claim_id, "survive", "evidence checks out")
        verdict_event_id = verdict_result["event"]["id"]

        # 4. Confirm the verdict (and challenge for lens feed completeness)
        _confirm(client, artifact_id, challenge_event_id)
        _confirm(client, artifact_id, verdict_event_id)

        # 5. Promote
        resp = client.post(f"/api/v1/promote/{artifact_id}/{claim_id}")
        assert resp.status_code == 200

        # 6. Get doc
        resp = client.get(f"/api/v1/artifact/{artifact_id}/doc")
        assert resp.status_code == 200
        doc_events = resp.json()["events"]
        assert len(doc_events) >= 1

        # No park, no killed, no debt in DOC
        for e in doc_events:
            assert e["type"] != "park"
            assert e["debt"] is False

        # 7. Trajectory should contain everything
        resp = client.get(f"/api/v1/artifact/{artifact_id}/trajectory")
        assert resp.status_code == 200
        all_events = resp.json()["events"]
        types = [e["type"] for e in all_events]
        assert "park" in types
        assert "challenge" in types
        assert "answer" in types
        assert "verdict" in types
        assert "confirm" in types
        assert "promote" in types


# ---------------------------------------------------------------------------
# Edit endpoint tests
# ---------------------------------------------------------------------------


class TestEdit:
    def test_create_edit_surface(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        resp = client.post(
            f"/api/v1/artifact/{artifact_id}/edit",
            json={"content": "revised text", "scope": "surface"},
        )
        assert resp.status_code == 200
        event = resp.json()["event"]
        assert event["type"] == "edit"
        assert event["confirmed"] is False
        assert event["payload"]["content"] == "revised text"
        assert event["payload"]["scope"] == "surface"

    def test_create_edit_substance(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        resp = client.post(
            f"/api/v1/artifact/{artifact_id}/edit",
            json={"content": "new claim text", "scope": "substance"},
        )
        assert resp.status_code == 200
        event = resp.json()["event"]
        assert event["type"] == "edit"
        assert event["payload"]["scope"] == "substance"

    def test_create_edit_invalid_scope_returns_400(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        resp = client.post(
            f"/api/v1/artifact/{artifact_id}/edit",
            json={"content": "text", "scope": "invalid"},
        )
        assert resp.status_code == 400

    def test_edit_appears_in_trajectory(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        client.post(
            f"/api/v1/artifact/{artifact_id}/edit",
            json={"content": "revised text", "scope": "surface"},
        )
        resp = client.get(f"/api/v1/artifact/{artifact_id}/trajectory")
        assert resp.status_code == 200
        types = [e["type"] for e in resp.json()["events"]]
        assert "edit" in types


# ---------------------------------------------------------------------------
# Fix 1: Grill state validation via API
# ---------------------------------------------------------------------------


class TestGrillStateValidation:
    def test_challenge_on_nonexistent_artifact_returns_400(self, client: TestClient):
        """challenge on an artifact with no events -> 400."""
        resp = client.post(
            "/api/v1/grill/nonexistent-id/challenge",
            json={"claim_id": "c1", "question": "Why?"},
        )
        assert resp.status_code == 400

    def test_verdict_without_prior_challenge_returns_400(self, client: TestClient):
        """verdict on parked-only artifact (no challenge) -> 400."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        resp = client.post(
            f"/api/v1/grill/{artifact_id}/verdict",
            json={"claim_id": claim_id, "outcome": "survive", "rationale": "ok"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Fix 2: Acceptance criterion 3 — killed idea
# ---------------------------------------------------------------------------


class TestKilledIdea:
    def test_killed_verdict_in_trajectory_not_in_doc(self, client: TestClient):
        """Park -> grill -> challenge -> answer -> verdict(kill) -> confirm.

        Trajectory contains the killed verdict; DOC does NOT.
        """
        # Park
        data = _park(client, body="bad hypothesis")
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]

        # Grill cycle -> kill
        _start_grill(client, artifact_id)
        challenge_result = _challenge(client, artifact_id, claim_id, "Evidence?")
        _answer(client, artifact_id, claim_id, "I have none")
        verdict_result = _verdict(client, artifact_id, claim_id, "kill", "unsupported")
        verdict_event_id = verdict_result["event"]["id"]

        # Confirm the verdict
        _confirm(client, artifact_id, challenge_result["event"]["id"])
        _confirm(client, artifact_id, verdict_event_id)

        # Trajectory should contain the killed verdict
        resp = client.get(f"/api/v1/artifact/{artifact_id}/trajectory")
        assert resp.status_code == 200
        traj_events = resp.json()["events"]
        kill_verdicts = [
            e for e in traj_events
            if e["type"] == "verdict" and e["payload"].get("outcome") == "kill"
        ]
        assert len(kill_verdicts) >= 1

        # DOC should NOT contain killed claim's events
        resp = client.get(f"/api/v1/artifact/{artifact_id}/doc")
        assert resp.status_code == 200
        doc_events = resp.json()["events"]
        # No events referencing the killed claim should appear in DOC
        for e in doc_events:
            if e.get("target_ref") == claim_id:
                assert e["type"] != "verdict" or e["payload"].get("outcome") != "kill"


# ---------------------------------------------------------------------------
# Fix 2: Acceptance criterion 5 — lens feed via API
# ---------------------------------------------------------------------------


class TestLensFeedViaAPI:
    def test_full_grill_then_lens_feed_ingest_and_query(self, client: TestClient):
        """Park -> full grill -> confirm -> ingest lens feed -> query returns entries."""
        data = _park(client, library_id="lib-lens")
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]

        # Full grill cycle
        _start_grill(client, artifact_id)
        challenge_result = _challenge(client, artifact_id, claim_id, "Prove it")
        _answer(client, artifact_id, claim_id, "Study X shows Y")
        verdict_result = _verdict(client, artifact_id, claim_id, "survive", "solid")
        _confirm(client, artifact_id, challenge_result["event"]["id"])
        _confirm(client, artifact_id, verdict_result["event"]["id"])

        # Ingest into lens feed
        resp = client.post(
            f"/api/v1/lens-feed/{artifact_id}",
            json={"library_id": "lib-lens"},
        )
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) >= 1

        # Query lens feed by library_id
        resp = client.get("/api/v1/lens-feed", params={"library_id": "lib-lens"})
        assert resp.status_code == 200
        queried = resp.json()["entries"]
        assert len(queried) >= 1
        # All entries should belong to the correct library
        for entry in queried:
            assert entry["library_id"] == "lib-lens"


# ---------------------------------------------------------------------------
# Fix 2: Acceptance criterion 6 — review kind uses same flow
# ---------------------------------------------------------------------------


class TestReviewKind:
    def test_review_kind_same_grill_flow_as_idea(self, client: TestClient):
        """Park with kind='review' -> full grill cycle -> same event types as idea."""
        data = _park(client, kind="review", body="review of paper Z")
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        assert data["artifact"]["kind"] == "review"

        # Full grill cycle
        _start_grill(client, artifact_id, kind="review")
        challenge_result = _challenge(client, artifact_id, claim_id, "Justify this critique")
        _answer(client, artifact_id, claim_id, "Evidence from paper X")
        verdict_result = _verdict(client, artifact_id, claim_id, "survive", "solid critique")

        # Confirm
        _confirm(client, artifact_id, challenge_result["event"]["id"])
        _confirm(client, artifact_id, verdict_result["event"]["id"])

        # Trajectory should have the same event types as an idea flow
        resp = client.get(f"/api/v1/artifact/{artifact_id}/trajectory")
        assert resp.status_code == 200
        event_types = {e["type"] for e in resp.json()["events"]}
        assert {"park", "challenge", "answer", "verdict", "confirm"}.issubset(event_types)


# ---------------------------------------------------------------------------
# Auto-grill (LLM-powered) API tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def client_with_challenge_llm(monkeypatch):
    """TestClient with a FakeLLMClient that returns a challenge response."""
    monkeypatch.setenv("ANNEAL_LLM_KEY", "")
    monkeypatch.setenv("ANNEAL_LLM_MODEL", "")
    monkeypatch.delenv("ANNEAL_DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as c:
        fake_llm = FakeLLMClient([
            json.dumps({"question": "What evidence supports this?", "target_aspect": "evidence"}),
        ])
        _state["grill_service"]._llm = fake_llm
        yield c


@pytest.fixture()
def client_with_verdict_llm(monkeypatch):
    """TestClient with a FakeLLMClient that returns a verdict response."""
    monkeypatch.setenv("ANNEAL_LLM_KEY", "")
    monkeypatch.setenv("ANNEAL_LLM_MODEL", "")
    monkeypatch.delenv("ANNEAL_DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as c:
        fake_llm = FakeLLMClient([
            json.dumps({"outcome": "survive", "rationale": "well supported", "confidence": 0.9}),
        ])
        _state["grill_service"]._llm = fake_llm
        yield c


@pytest.fixture()
def client_with_bad_llm(monkeypatch):
    """TestClient with a FakeLLMClient that returns garbage (unparseable JSON)."""
    monkeypatch.setenv("ANNEAL_LLM_KEY", "")
    monkeypatch.setenv("ANNEAL_LLM_MODEL", "")
    monkeypatch.delenv("ANNEAL_DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as c:
        fake_llm = FakeLLMClient(["this is not json at all"])
        _state["grill_service"]._llm = fake_llm
        yield c


class TestAutoGrillAPI:
    def test_auto_challenge_returns_event(self, client_with_challenge_llm: TestClient):
        """POST /grill/{id}/auto-challenge -> 200 with CHALLENGE event."""
        data = _park(client_with_challenge_llm)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client_with_challenge_llm, artifact_id)

        resp = client_with_challenge_llm.post(
            f"/api/v1/grill/{artifact_id}/auto-challenge",
            json={"claim_id": claim_id, "claim_body": "test idea", "context": ""},
        )
        assert resp.status_code == 200
        event = resp.json()["event"]
        assert event["type"] == "challenge"
        assert event["confirmed"] is False
        assert event["payload"]["auto_generated"] is True
        assert event["payload"]["question"] == "What evidence supports this?"

    def test_auto_challenge_without_llm_returns_501(self, client: TestClient):
        """POST /grill/{id}/auto-challenge without LLM configured -> 501."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)

        resp = client.post(
            f"/api/v1/grill/{artifact_id}/auto-challenge",
            json={"claim_id": claim_id, "claim_body": "test idea"},
        )
        assert resp.status_code == 501

    def test_auto_verdict_returns_event(self, client_with_verdict_llm: TestClient):
        """POST /grill/{id}/auto-verdict -> 200 with VERDICT event."""
        data = _park(client_with_verdict_llm)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client_with_verdict_llm, artifact_id)
        _challenge(client_with_verdict_llm, artifact_id, claim_id)

        resp = client_with_verdict_llm.post(
            f"/api/v1/grill/{artifact_id}/auto-verdict",
            json={
                "claim_id": claim_id,
                "claim_body": "test idea",
                "question": "Why?",
                "answer": "Because evidence.",
            },
        )
        assert resp.status_code == 200
        event = resp.json()["event"]
        assert event["type"] == "verdict"
        assert event["confirmed"] is False
        assert event["payload"]["auto_generated"] is True
        assert event["payload"]["outcome"] in ("survive", "kill")

    def test_auto_verdict_without_llm_returns_501(self, client: TestClient):
        """POST /grill/{id}/auto-verdict without LLM configured -> 501."""
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client, artifact_id)
        _challenge(client, artifact_id, claim_id)

        resp = client.post(
            f"/api/v1/grill/{artifact_id}/auto-verdict",
            json={
                "claim_id": claim_id,
                "claim_body": "test idea",
                "question": "Why?",
                "answer": "Because.",
            },
        )
        assert resp.status_code == 501

    def test_auto_challenge_bad_json_returns_502(self, client_with_bad_llm: TestClient):
        """POST /grill/{id}/auto-challenge with LLM returning garbage -> 502."""
        data = _park(client_with_bad_llm)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        _start_grill(client_with_bad_llm, artifact_id)

        resp = client_with_bad_llm.post(
            f"/api/v1/grill/{artifact_id}/auto-challenge",
            json={"claim_id": claim_id, "claim_body": "test idea"},
        )
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Collect (literature search) API tests
# ---------------------------------------------------------------------------


def _fake_paper(source_id: str = "W1", title: str = "A paper") -> dict:
    """A neutral OpenAlex-shaped result dict (as search_openalex yields)."""
    return {
        "source": "openalex",
        "source_id": source_id,
        "doi": f"10.1234/{source_id}",
        "url": f"https://openalex.org/{source_id}",
        "title": title,
        "authors": ["Alice", "Bob"],
        "abstract": "An abstract about the topic.",
        "year": 2023,
        "venue": "Journal of Things",
        "citations": 7,
        "pdf_urls": [],
    }


def _patch_search(monkeypatch, papers: list[dict]) -> None:
    """Patch the search adapter used by CollectService so no network hits."""
    async def _fake_search(query, max_results=10, mailto=None):
        return papers[:max_results]

    monkeypatch.setattr(
        "anneal.services.collect_service.search_openalex", _fake_search
    )


class TestCollectAPI:
    def test_collect_returns_materials_and_logs_events(self, client: TestClient, monkeypatch):
        _patch_search(monkeypatch, [_fake_paper("W1", "First"), _fake_paper("W2", "Second")])
        data = _park(client)
        artifact_id = data["artifact"]["id"]

        resp = client.post(
            f"/api/v1/artifact/{artifact_id}/collect",
            json={"library_id": "lib-1", "query": "topic", "max_results": 10},
        )
        assert resp.status_code == 200, resp.text
        materials = resp.json()["materials"]
        assert len(materials) == 2
        assert materials[0]["payload"]["title"] == "First"
        assert materials[0]["kind"] == "paper"

        # collect_material events landed on the artifact's stream
        resp = client.get(f"/api/v1/artifact/{artifact_id}/trajectory")
        assert resp.status_code == 200
        collect_events = [
            e for e in resp.json()["events"] if e["type"] == "collect_material"
        ]
        assert len(collect_events) == 2
        assert {e["payload"]["title"] for e in collect_events} == {"First", "Second"}

    def test_collect_nonexistent_artifact_returns_404(self, client: TestClient, monkeypatch):
        _patch_search(monkeypatch, [_fake_paper()])
        resp = client.post(
            "/api/v1/artifact/nope/collect",
            json={"library_id": "lib-1", "query": "topic"},
        )
        assert resp.status_code == 404

    def test_list_materials_after_collect(self, client: TestClient, monkeypatch):
        _patch_search(monkeypatch, [_fake_paper("W1", "First"), _fake_paper("W2", "Second")])
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        client.post(
            f"/api/v1/artifact/{artifact_id}/collect",
            json={"library_id": "lib-1", "query": "topic"},
        )

        resp = client.get(f"/api/v1/artifact/{artifact_id}/materials")
        assert resp.status_code == 200, resp.text
        materials = resp.json()["materials"]
        assert len(materials) == 2
        assert {m["payload"]["title"] for m in materials} == {"First", "Second"}

    def test_list_materials_nonexistent_artifact_returns_404(self, client: TestClient):
        resp = client.get("/api/v1/artifact/nope/materials")
        assert resp.status_code == 404

    def test_list_materials_empty_when_none_collected(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        resp = client.get(f"/api/v1/artifact/{artifact_id}/materials")
        assert resp.status_code == 200
        assert resp.json()["materials"] == []


# ---------------------------------------------------------------------------
# Grounding API tests
# ---------------------------------------------------------------------------


def _collect_one(client: TestClient, artifact_id: str) -> str:
    """Collect a single patched paper and return its material id."""
    resp = client.post(
        f"/api/v1/artifact/{artifact_id}/collect",
        json={"library_id": "lib-1", "query": "topic"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["materials"][0]["id"]


class TestGroundingAPI:
    def test_manual_ground_returns_pending_event_then_confirm(self, client: TestClient, monkeypatch):
        _patch_search(monkeypatch, [_fake_paper("W1", "Grounding paper")])
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        material_id = _collect_one(client, artifact_id)

        resp = client.post(
            f"/api/v1/grounding/{artifact_id}/ground",
            json={
                "claim_id": claim_id,
                "material_id": material_id,
                "supported": True,
                "evidence": "Section 3 shows X.",
                "assessment": "Directly supports.",
            },
        )
        assert resp.status_code == 200, resp.text
        event = resp.json()["event"]
        assert event["type"] == "ground"
        assert event["confirmed"] is False
        assert event["target_ref"] == claim_id
        assert event["payload"]["material_id"] == material_id
        assert event["payload"]["supported"] is True
        assert event["payload"]["evidence"] == "Section 3 shows X."
        assert event["payload"]["title"] == "Grounding paper"

        # The pending GROUND event can be confirmed via the existing gate.
        confirm = _confirm(client, artifact_id, event["id"])
        assert confirm["event"]["type"] == "confirm"
        assert confirm["event"]["target_ref"] == event["id"]

    def test_ground_unknown_material_returns_400(self, client: TestClient):
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        resp = client.post(
            f"/api/v1/grounding/{artifact_id}/ground",
            json={"claim_id": claim_id, "material_id": "missing", "supported": True},
        )
        assert resp.status_code == 400

    def test_auto_ground_without_llm_returns_501(self, client: TestClient, monkeypatch):
        _patch_search(monkeypatch, [_fake_paper("W1", "Paper")])
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        material_id = _collect_one(client, artifact_id)

        resp = client.post(
            f"/api/v1/grounding/{artifact_id}/auto-ground",
            json={
                "claim_id": claim_id,
                "claim_body": "test idea",
                "material_id": material_id,
            },
        )
        assert resp.status_code == 501

    def test_auto_ground_with_llm_returns_pending_event(self, client: TestClient, monkeypatch):
        """With a FakeLLM wired onto the grounding service, auto-ground yields a
        pending GROUND event."""
        _patch_search(monkeypatch, [_fake_paper("W1", "Paper")])
        data = _park(client)
        artifact_id = data["artifact"]["id"]
        claim_id = data["claim"]["id"]
        material_id = _collect_one(client, artifact_id)

        fake_llm = FakeLLMClient([
            json.dumps({
                "supported": True,
                "evidence": "Abstract states the result.",
                "assessment": "Supports the claim.",
            }),
        ])
        _state["grounding_service"]._llm = fake_llm

        resp = client.post(
            f"/api/v1/grounding/{artifact_id}/auto-ground",
            json={
                "claim_id": claim_id,
                "claim_body": "test idea",
                "material_id": material_id,
            },
        )
        assert resp.status_code == 200, resp.text
        event = resp.json()["event"]
        assert event["type"] == "ground"
        assert event["confirmed"] is False
        assert event["target_ref"] == claim_id
        assert event["payload"]["supported"] is True
        assert event["payload"]["auto_generated"] is True
