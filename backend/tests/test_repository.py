"""Unit tests for InMemoryRepository."""

from __future__ import annotations

from datetime import datetime

from anneal.domain.models import Artifact, Claim, Conversation, Library, Material, Project
from anneal.store.repository import InMemoryRepository


def _make_library(lid: str = "lib-1") -> Library:
    return Library(id=lid, name="Test Library")


def _make_project(pid: str = "proj-1", lid: str = "lib-1") -> Project:
    return Project(id=pid, library_id=lid, goal="Test goal")


class TestLibraryRoundTrip:
    def test_create_and_get(self) -> None:
        repo = InMemoryRepository()
        lib = _make_library()
        repo.create_library(lib)
        got = repo.get_library(lib.id)
        assert got is not None
        assert got.id == lib.id
        assert got.name == lib.name

    def test_get_nonexistent_returns_none(self) -> None:
        repo = InMemoryRepository()
        assert repo.get_library("no-such-id") is None


class TestProjectRoundTrip:
    def test_create_and_get(self) -> None:
        repo = InMemoryRepository()
        proj = _make_project()
        repo.create_project(proj)
        got = repo.get_project(proj.id)
        assert got is not None
        assert got.id == proj.id
        assert got.goal == proj.goal

    def test_get_nonexistent_returns_none(self) -> None:
        repo = InMemoryRepository()
        assert repo.get_project("no-such-id") is None


class TestArtifactRoundTrip:
    def test_create_and_get(self) -> None:
        repo = InMemoryRepository()
        art = Artifact(
            id="art-1",
            library_id="lib-1",
            kind="paper",
            goal="Write a paper",
            title="My Paper",
        )
        repo.create_artifact(art)
        got = repo.get_artifact("art-1")
        assert got is not None
        assert got.id == "art-1"
        assert got.kind == "paper"
        assert got.goal == "Write a paper"

    def test_get_nonexistent_returns_none(self) -> None:
        repo = InMemoryRepository()
        assert repo.get_artifact("no-such-id") is None

    def test_with_project_and_material_ids(self) -> None:
        repo = InMemoryRepository()
        art = Artifact(
            id="art-2",
            library_id="lib-1",
            kind="paper",
            goal="Write",
            project_ids=["proj-1", "proj-2"],
            material_ids=["mat-1"],
        )
        repo.create_artifact(art)
        got = repo.get_artifact("art-2")
        assert got is not None
        assert got.project_ids == ["proj-1", "proj-2"]
        assert got.material_ids == ["mat-1"]

    def test_list_artifacts_filters_by_library(self) -> None:
        repo = InMemoryRepository()
        a1 = Artifact(id="a1", library_id="lib-1", kind="paper", goal="g1")
        a2 = Artifact(id="a2", library_id="lib-1", kind="paper", goal="g2")
        a3 = Artifact(id="a3", library_id="lib-2", kind="paper", goal="g3")
        repo.create_artifact(a1)
        repo.create_artifact(a2)
        repo.create_artifact(a3)

        lib1_arts = repo.list_artifacts("lib-1")
        assert len(lib1_arts) == 2
        assert {a.id for a in lib1_arts} == {"a1", "a2"}

        lib2_arts = repo.list_artifacts("lib-2")
        assert len(lib2_arts) == 1
        assert lib2_arts[0].id == "a3"

    def test_list_artifacts_empty(self) -> None:
        repo = InMemoryRepository()
        assert repo.list_artifacts("no-lib") == []


class TestClaimRoundTrip:
    def test_create_and_get(self) -> None:
        repo = InMemoryRepository()
        claim = Claim(
            id="cl-1",
            library_id="lib-1",
            body="Claim body",
        )
        repo.create_claim(claim)
        got = repo.get_claim("cl-1")
        assert got is not None
        assert got.body == "Claim body"

    def test_with_artifact_ids(self) -> None:
        repo = InMemoryRepository()
        claim = Claim(
            id="cl-2",
            library_id="lib-1",
            body="Another claim",
            artifact_ids=["art-1", "art-2"],
        )
        repo.create_claim(claim)
        got = repo.get_claim("cl-2")
        assert got is not None
        assert got.artifact_ids == ["art-1", "art-2"]

    def test_get_nonexistent_returns_none(self) -> None:
        repo = InMemoryRepository()
        assert repo.get_claim("no-such-id") is None

    def test_list_claims_filters_by_library(self) -> None:
        repo = InMemoryRepository()
        c1 = Claim(id="c1", library_id="lib-1", body="b1")
        c2 = Claim(id="c2", library_id="lib-1", body="b2")
        c3 = Claim(id="c3", library_id="lib-2", body="b3")
        repo.create_claim(c1)
        repo.create_claim(c2)
        repo.create_claim(c3)

        lib1_claims = repo.list_claims("lib-1")
        assert len(lib1_claims) == 2
        assert {c.id for c in lib1_claims} == {"c1", "c2"}

        lib2_claims = repo.list_claims("lib-2")
        assert len(lib2_claims) == 1
        assert lib2_claims[0].id == "c3"

    def test_list_claims_empty(self) -> None:
        repo = InMemoryRepository()
        assert repo.list_claims("no-lib") == []


class TestMaterialRoundTrip:
    def test_create_and_get(self) -> None:
        repo = InMemoryRepository()
        mat = Material(
            id="mat-1",
            library_id="lib-1",
            kind="pdf",
            provenance={"source": "pubmed"},
            payload={"text": "content"},
        )
        repo.create_material(mat)
        got = repo.get_material("mat-1")
        assert got is not None
        assert got.kind == "pdf"
        assert got.provenance == {"source": "pubmed"}
        assert got.payload == {"text": "content"}

    def test_get_nonexistent_returns_none(self) -> None:
        repo = InMemoryRepository()
        assert repo.get_material("no-such-id") is None


class TestConversationRoundTrip:
    def test_create_and_get(self) -> None:
        repo = InMemoryRepository()
        conv = Conversation(
            id="conv-1",
            library_id="lib-1",
            project_ids=["proj-1"],
        )
        repo.create_conversation(conv)
        got = repo.get_conversation("conv-1")
        assert got is not None
        assert got.project_ids == ["proj-1"]

    def test_get_nonexistent_returns_none(self) -> None:
        repo = InMemoryRepository()
        assert repo.get_conversation("no-such-id") is None
