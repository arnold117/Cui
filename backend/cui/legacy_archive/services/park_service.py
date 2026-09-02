"""Park service — captures inspiration into the sealed isolation zone.

PARK = sealed isolation; the only path to the moat (Lens) is through GRILL.
No ungrilled content leaks past this boundary.

Spec acceptance (section 5 line 1):
    "Park a灵感, it's in isolation, marked ungrilled,
     not visible in Lens feed queries."
"""

from __future__ import annotations

from cui.domain.constants import SUPPORTED_ARTIFACT_KINDS
from cui.domain.events import PARK, make_event
from cui.domain.models import Artifact, Claim
from cui.domain.projections import is_parked
from cui.legacy_archive.services.event_service import EventService
from cui.store.event_store import EventStore
from cui.store.repository import Repository


class ParkService:
    """Service for parking inspirations into the sealed isolation zone.

    Creates Artifact and Claim objects, persists them to the repository,
    and appends a PARK event to the EventStore.
    """

    def __init__(self, store: EventStore, event_service: EventService, repo: Repository) -> None:
        self._store = store
        self._event_service = event_service
        self._repo = repo

    def park(
        self, library_id: str, body: str, kind: str = "idea"
    ) -> tuple[Artifact, Claim]:
        """Park a new inspiration into the sealed isolation zone.

        - Validates kind is in SUPPORTED_ARTIFACT_KINDS (service-layer
          validation, not model).
        - Creates a new Artifact.
        - Creates a new Claim with the given body.
        - Appends a 'park' event (confirmed=True, debt=False) with
          target_ref=claim.id.
        - Returns (artifact, claim).

        Raises ValueError if kind is not in SUPPORTED_ARTIFACT_KINDS.
        """
        if kind not in SUPPORTED_ARTIFACT_KINDS:
            raise ValueError(
                f"Unsupported artifact kind {kind!r}; "
                f"supported: {sorted(SUPPORTED_ARTIFACT_KINDS)}"
            )

        artifact = Artifact(library_id=library_id, kind=kind, goal=body)
        claim = Claim(library_id=library_id, body=body, artifact_ids=[artifact.id])

        self._repo.create_artifact(artifact)
        self._repo.create_claim(claim)

        event = make_event(
            type=PARK,
            actor="user",
            confirmed=True,
            debt=False,
            target_ref=claim.id,
            payload={"kind": kind, "claim_id": claim.id},
        )
        self._event_service.append_event(artifact.id, event)

        return artifact, claim

    def list_parked(self, library_id: str) -> list[str]:
        """Return artifact_ids that are still parked.

        Uses the repository to list all artifacts for the library, then
        filters by is_parked() projection on each artifact's event stream.
        """
        artifacts = self._repo.list_artifacts(library_id)
        return [
            artifact.id
            for artifact in artifacts
            if is_parked(self._store.get_events(artifact.id))
        ]

    def get_events(self, artifact_id: str) -> list:
        """Get all events for an artifact."""
        return self._store.get_events(artifact_id)
