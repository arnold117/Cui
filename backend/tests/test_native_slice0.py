from fastapi.testclient import TestClient
import pytest

from cui.api.app import create_native_app, create_native_test_app
from cui.research_universe.api.routes import LibraryContext
from cui.research_universe.domain.events import NativeEvent, PendingNativeEvent
from pydantic import ValidationError
from cui.legacy_archive.api.routes import create_router as create_archive_router
from cui.store.repository import InMemoryRepository
from cui.store.event_store import InMemoryEventStore
from cui.domain.models import Artifact, Claim, Material, Project, Conversation
from cui.domain.events import make_event
from fastapi import FastAPI
from cui.research_universe.store.event_store import (
    CommandFingerprintConflict,
    ExpectedSequenceConflict,
    InMemoryNativeEventStore,
)


def test_native_test_app_provisions_server_scoped_active_universe():
    app = create_native_test_app(InMemoryNativeEventStore(), LibraryContext("library-a"))
    with TestClient(app) as client:
        assert client.get("/api/v1/park").status_code == 404
        created = client.post("/api/v2/universes").json()
        assert created["library_id"] == "library-a"
        assert client.get("/api/v2/universes/active").json() == created
        assert client.get("/api/v2/legacy-archive").status_code == 503


def test_native_production_fails_closed_without_database(monkeypatch):
    monkeypatch.delenv("CUI_DATABASE_URL", raising=False)
    # Host bootstrap may load backend/.env — neutralize it so the test proves
    # fails-closed when no configuration source provides a database URL.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="CUI_DATABASE_URL"):
        create_native_app()


def test_native_event_store_idempotency_sequence_and_global_order():
    store = InMemoryNativeEventStore()
    universe = store.create_active_universe("library-a")
    event = PendingNativeEvent(event_type="workspace_created", aggregate_type="workspace", aggregate_id="w1", payload={"workspace_id": "w1", "initial_question_version_id": "q1", "initial_question_text": "What?"})
    first = store.append(universe_id=universe, command_id="c1", command_type="create_workspace", command_payload={"workspace_id": "w1"}, actor_kind="user", actor_id="local", expected_sequences={("workspace", "w1"): 0}, events=[event], result_payload={"workspace_id": "w1"})
    replay = store.append(universe_id=universe, command_id="c1", command_type="create_workspace", command_payload={"workspace_id": "w1"}, actor_kind="user", actor_id="local", expected_sequences={("workspace", "w1"): 0}, events=[event], result_payload={"workspace_id": "w1"})
    assert replay.replayed and replay.event_ids == first.event_ids
    with pytest.raises(CommandFingerprintConflict):
        store.append(universe_id=universe, command_id="c1", command_type="create_workspace", command_payload={"workspace_id": "other"}, actor_kind="user", actor_id="local", expected_sequences={("workspace", "w1"): 0}, events=[event], result_payload={})
    with pytest.raises(ExpectedSequenceConflict):
        store.append(universe_id=universe, command_id="c2", command_type="create_workspace", command_payload={}, actor_kind="user", actor_id="local", expected_sequences={("workspace", "w1"): 0}, events=[event], result_payload={})
    assert [e.commit_position for e in store.read_events(universe)] == [first.commit_position]


def test_catalogue_is_versioned_strict_and_round_trips():
    payload = {"workspace_id": "w", "initial_question_version_id": "q", "initial_question_text": "Question?"}
    pending = PendingNativeEvent(event_type="workspace_created", aggregate_type="workspace", aggregate_id="w", payload=payload)
    assert pending.validated_payload().model_dump(mode="json") == {**payload, "user_position": "exploring"}
    with pytest.raises(ValueError, match="workspace_created@v2"):
        PendingNativeEvent(event_type="workspace_created", aggregate_type="workspace", aggregate_id="w", schema_version=2, payload=payload).validated_payload()
    with pytest.raises(ValueError, match="unknown@v1"):
        PendingNativeEvent(event_type="unknown", aggregate_type="workspace", aggregate_id="w", payload=payload).validated_payload()
    with pytest.raises(ValidationError):
        PendingNativeEvent(event_type="workspace_created", aggregate_type="workspace", aggregate_id="w", payload={**payload, "surplus": True}).validated_payload()
    with pytest.raises(ValidationError):
        PendingNativeEvent(event_type="workspace_created", aggregate_type="workspace", aggregate_id="w", payload={"workspace_id": "w"}).validated_payload()
    envelope = NativeEvent(universe_id="u", aggregate_type="workspace", aggregate_id="w", stream_id="s", sequence=0, commit_position=1, commit_index=0, event_type="workspace_created", actor_kind="user", actor_id="local", payload=payload)
    assert envelope.validated_payload().model_dump(mode="json") == pending.validated_payload().model_dump(mode="json")


def test_archive_detail_aggregates_library_scoped_legacy_context():
    repo, events = InMemoryRepository(), InMemoryEventStore()
    repo.create_artifact(Artifact(id="a", library_id="one", kind="paper", goal="g", project_ids=["p"], material_ids=["m"]))
    repo.create_claim(Claim(id="c", library_id="one", body="claim", artifact_ids=["a"]))
    repo.create_material(Material(id="m", library_id="one", kind="pdf", payload={"title": "source"}))
    repo.create_project(Project(id="p", library_id="one", goal="project"))
    repo.create_conversation(Conversation(id="cv", library_id="one", project_ids=["p"]))
    # Corrupt historical cross-library joins are excluded by the archive facade.
    repo.create_claim(Claim(id="foreign", library_id="two", body="no", artifact_ids=["a"]))
    repo.create_material(Material(id="foreign-m", library_id="two", kind="pdf"))
    events.append("a", make_event(type="park", actor="user", payload={"capture": "sealed"}))
    app = FastAPI(); app.include_router(create_archive_router(repo, events, "one"), prefix="/api/v2")
    with TestClient(app) as client:
        detail = client.get("/api/v2/legacy-archive/artifacts/a")
        assert detail.status_code == 200
        body = detail.json()
        assert [x["id"] for x in body["claims"]] == ["c"]
        assert [x["id"] for x in body["materials"]] == ["m"]
        assert [x["id"] for x in body["projects"]] == ["p"]
        assert [x["id"] for x in body["conversations"]] == ["cv"]
        assert body["trajectory"][0]["type"] == "park"
        assert client.get("/api/v2/legacy-archive/artifacts/foreign").status_code == 404
