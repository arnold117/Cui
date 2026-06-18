"""Tests for anneal.services.collect_service — native dict->Material mapping.

No real network: we monkeypatch ``collect_service.search_all`` (the multi-source
orchestrator) with a fake async function that returns canned neutral dicts. The
store/repo/event-service are the real in-memory implementations (mirroring
test_park_service.py).
"""

from __future__ import annotations

import pytest

from anneal.domain.events import COLLECT_MATERIAL
from anneal.services import collect_service as collect_mod
from anneal.services.collect_service import CollectService
from anneal.services.event_service import EventService
from anneal.store.event_store import InMemoryEventStore
from anneal.store.repository import InMemoryRepository

LIBRARY = "lib-1"
ARTIFACT = "artifact-1"


# ---------------------------------------------------------------------------
# Fixtures (mirror test_park_service.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    return InMemoryEventStore()


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def event_service(store):
    return EventService(store)


@pytest.fixture
def svc(store, event_service, repo):
    return CollectService(store, event_service, repo=repo)


def _neutral(source_id: str, title: str) -> dict:
    """A neutral paper-like dict as the adapter would return."""
    return {
        "source": "openalex",
        "source_id": source_id,
        "title": title,
        "authors": ["Ada Lovelace"],
        "abstract": "a grilled abstract",
        "year": 2021,
        "venue": "Journal of Forged Drafts",
        "citations": 7,
        "doi": "10.1/" + source_id,
        "pdf_urls": ["https://example.org/" + source_id + ".pdf"],
        "url": "https://openalex.org/" + source_id,
    }


def _patch_adapter(monkeypatch, results: list[dict]):
    async def fake_search(query, sources=None, max_per_source=10, mailto=None):
        fake_search.calls.append((query, max_per_source, mailto, sources))
        return results[:max_per_source]

    fake_search.calls = []
    monkeypatch.setattr(collect_mod, "search_all", fake_search)
    return fake_search


# ---------------------------------------------------------------------------
# collect — happy path
# ---------------------------------------------------------------------------


class TestCollect:
    async def test_creates_one_material_per_result(self, svc, monkeypatch):
        _patch_adapter(monkeypatch, [_neutral("W1", "first"), _neutral("W2", "second")])

        materials = await svc.collect(ARTIFACT, LIBRARY, "annealing")

        assert len(materials) == 2
        assert all(m.kind == "paper" for m in materials)
        assert all(m.library_id == LIBRARY for m in materials)

    async def test_material_provenance_and_payload(self, svc, monkeypatch):
        _patch_adapter(monkeypatch, [_neutral("W1", "first")])

        (material,) = await svc.collect(ARTIFACT, LIBRARY, "annealing")

        assert material.provenance == {
            "source": "openalex",
            "source_id": "W1",
            "doi": "10.1/W1",
            "url": "https://openalex.org/W1",
            "query": "annealing",
            "sources": ["openalex"],
        }
        assert material.payload == {
            "title": "first",
            "authors": ["Ada Lovelace"],
            "abstract": "a grilled abstract",
            "year": 2021,
            "venue": "Journal of Forged Drafts",
            "citations": 7,
            "pdf_urls": ["https://example.org/W1.pdf"],
        }

    async def test_persists_materials_to_repo(self, svc, repo, monkeypatch):
        _patch_adapter(monkeypatch, [_neutral("W1", "first"), _neutral("W2", "second")])

        materials = await svc.collect(ARTIFACT, LIBRARY, "q")

        for m in materials:
            assert repo.get_material(m.id) is not None
            assert repo.get_material(m.id).provenance["source_id"] == m.provenance[
                "source_id"
            ]

    async def test_appends_one_event_per_material(self, svc, store, monkeypatch):
        _patch_adapter(monkeypatch, [_neutral("W1", "first"), _neutral("W2", "second")])

        materials = await svc.collect(ARTIFACT, LIBRARY, "q")

        events = store.get_events(ARTIFACT)
        assert len(events) == 2
        assert all(e.type == COLLECT_MATERIAL for e in events)
        assert all(e.actor == "system" for e in events)
        assert all(e.confirmed is True for e in events)

        # target_ref + payload line up with the created materials, in order.
        for material, event in zip(materials, events):
            assert event.target_ref == material.id
            assert event.payload == {
                "material_id": material.id,
                "source": "openalex",
                "title": material.payload["title"],
                "query": "q",
            }

    async def test_passes_query_and_max_results_to_adapter(self, svc, monkeypatch):
        fake = _patch_adapter(monkeypatch, [_neutral("W1", "first")])

        await svc.collect(ARTIFACT, LIBRARY, "needle", max_results=3)

        assert fake.calls[0][0] == "needle"
        assert fake.calls[0][1] == 3

    async def test_persists_merged_sources_into_provenance(self, svc, monkeypatch):
        # A deduped paper carries a multi-source ``sources`` list.
        paper = dict(_neutral("W1", "first"), sources=["openalex", "crossref"])
        _patch_adapter(monkeypatch, [paper])

        (material,) = await svc.collect(ARTIFACT, LIBRARY, "q")

        assert material.provenance["sources"] == ["openalex", "crossref"]

    async def test_passes_sources_filter_to_orchestrator(self, svc, monkeypatch):
        fake = _patch_adapter(monkeypatch, [_neutral("W1", "first")])

        await svc.collect(ARTIFACT, LIBRARY, "q", sources=["openalex", "arxiv"])

        assert fake.calls[0][3] == ["openalex", "arxiv"]

    async def test_reads_contact_email_from_env(self, svc, monkeypatch):
        fake = _patch_adapter(monkeypatch, [_neutral("W1", "first")])
        monkeypatch.setattr(collect_mod, "load_dotenv", lambda *a, **k: None)
        monkeypatch.setenv("OPENALEX_CONTACT", "me@example.com")

        await svc.collect(ARTIFACT, LIBRARY, "q")

        assert fake.calls[0][2] == "me@example.com"

    async def test_no_contact_email_passes_none(self, svc, monkeypatch):
        fake = _patch_adapter(monkeypatch, [_neutral("W1", "first")])
        monkeypatch.setattr(collect_mod, "load_dotenv", lambda *a, **k: None)
        monkeypatch.delenv("OPENALEX_CONTACT", raising=False)

        await svc.collect(ARTIFACT, LIBRARY, "q")

        assert fake.calls[0][2] is None


# ---------------------------------------------------------------------------
# collect — graceful degradation
# ---------------------------------------------------------------------------


class TestCollectEmpty:
    async def test_no_results_creates_nothing(self, svc, store, repo, monkeypatch):
        _patch_adapter(monkeypatch, [])

        materials = await svc.collect(ARTIFACT, LIBRARY, "q")

        assert materials == []
        assert store.get_events(ARTIFACT) == []
