"""Grill service — adversarial questioning loop.

Implements PARK -> GRILL transition and the challenge-answer-verdict cycle.
从零开始拷问，无偷渡 — park content becomes context but grill starts fresh.

Uses EventService for event writes; confirmation is a cross-cutting concern
handled by EventService.confirm_event / retract_event.

Dependency: EventStore -> EventService -> GrillService.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cui.domain.constants import DEATH_CAUSES, SUPPORTED_ARTIFACT_KINDS
from cui.domain.events import (
    ANSWER,
    CHALLENGE,
    PARK,
    VERDICT,
    Event,
    make_event,
)
from cui.domain.projections import (
    confirmed_ground_evidence,
    ground_stance,
    has_grill_events,
    is_parked,
    verdict_precedent,
)
from cui.llm.client import LLMClient
from cui.llm.errors import LLMNotConfiguredError, LLMResponseError
from cui.legacy_archive.services.event_service import EventService
from cui.store.event_store import EventStore
from cui.store.repository import Repository

if TYPE_CHECKING:
    from cui.legacy_archive.prompts import ClaimPrecedent


class GrillService:
    """Adversarial grill loop for artifacts.

    Supported artifact kinds are validated at the service layer (spec §2.4:
    "泛化抽象，不泛化实现" — schema is generic, implementation is narrow).

    ``repo`` is OPTIONAL and only powers 判例先验 (the Library-wide kill
    precedents ``auto_challenge`` injects). Without it the service behaves
    exactly as before — no precedents, today's prompt verbatim.
    """

    def __init__(
        self,
        store: EventStore,
        event_service: EventService,
        llm: LLMClient | None = None,
        repo: Repository | None = None,
    ) -> None:
        self._store = store
        self._event_service = event_service
        self._llm = llm
        self._repo = repo

    # ------------------------------------------------------------------
    # Transition gate
    # ------------------------------------------------------------------

    def start_grill(self, artifact_id: str, kind: str) -> None:
        """Validate that the artifact can enter GRILL from PARK.

        This is a validation-only gate — it does NOT emit its own event.
        The first challenge() IS the start of grill.

        Raises ValueError if:
        - kind is not in SUPPORTED_KINDS
        - artifact has no events (never parked)
        - artifact has no park event
        - artifact already has grill events (already grilling)
        """
        if kind not in SUPPORTED_ARTIFACT_KINDS:
            raise ValueError(
                f"Unsupported artifact kind {kind!r}; "
                f"supported: {sorted(SUPPORTED_ARTIFACT_KINDS)}"
            )

        events = self._store.get_events(artifact_id)

        if not events:
            raise ValueError(
                f"Artifact {artifact_id!r} has no events — cannot grill an unparked artifact"
            )

        if not any(e.type == PARK for e in events):
            raise ValueError(
                f"Artifact {artifact_id!r} was never parked — must park before grilling"
            )

        if has_grill_events(events):
            raise ValueError(
                f"Artifact {artifact_id!r} already has grill events — cannot start_grill again"
            )

    # ------------------------------------------------------------------
    # Internal validation helpers
    # ------------------------------------------------------------------

    def _assert_artifact_was_parked(self, artifact_id: str) -> list[Event]:
        """Return events for artifact_id, raising if empty or never parked."""
        events = self._store.get_events(artifact_id)
        if not events:
            raise ValueError(
                f"Artifact {artifact_id!r} has no events"
            )
        if not any(e.type == PARK for e in events):
            raise ValueError(
                f"Artifact {artifact_id!r} was never parked"
            )
        return events

    def _assert_has_challenge(self, artifact_id: str) -> list[Event]:
        """Return events for artifact_id, raising if no CHALLENGE exists yet."""
        events = self._store.get_events(artifact_id)
        if not any(e.type == CHALLENGE for e in events):
            raise ValueError(
                f"No challenge exists for artifact {artifact_id!r} "
                "— cannot answer/verdict/bypass before first challenge"
            )
        return events

    # ------------------------------------------------------------------
    # Grill actions
    # ------------------------------------------------------------------

    def challenge(self, artifact_id: str, claim_id: str, question: str) -> Event:
        """System poses a challenge. Appends CHALLENGE event.

        actor="system", confirmed=False (system action needs user confirmation,
        spec §2.6 decision #2).
        target_ref=claim_id.

        Validates:
        - Artifact has events (was created).
        - Artifact has a park event (was parked).
        - Allowed on parked-only OR already-grilling artifacts.
        """
        self._assert_artifact_was_parked(artifact_id)
        event = make_event(
            type=CHALLENGE,
            actor="system",
            confirmed=False,
            target_ref=claim_id,
            payload={"question": question},
        )
        return self._event_service.append_event(artifact_id, event)

    def answer(
        self,
        artifact_id: str,
        claim_id: str,
        response: str,
        challenge_id: str | None = None,
    ) -> Event:
        """User answers a challenge. Appends ANSWER event.

        actor="user", confirmed=True (user doing it IS confirmation).
        target_ref=claim_id.

        ``challenge_id`` is optional and additive: when provided it is recorded
        in the payload so the answer can be paired to the specific challenge it
        belongs to (required once challenges run in parallel — several may be
        open at once, so ts-ordering alone is ambiguous). Omitting it keeps the
        legacy linear behavior intact.

        Validates: at least one CHALLENGE event must exist.
        """
        self._assert_has_challenge(artifact_id)
        payload: dict = {"response": response}
        if challenge_id is not None:
            payload["challenge_id"] = challenge_id
        event = make_event(
            type=ANSWER,
            actor="user",
            confirmed=True,
            target_ref=claim_id,
            payload=payload,
        )
        return self._event_service.append_event(artifact_id, event)

    @staticmethod
    def _validate_death_triage(
        outcome: str,
        death_cause: str | None,
        revival_condition: str | None,
        successor_claim_id: str | None,
    ) -> None:
        """Enforce 死因分诊 on NEW verdicts (spec docs/spec-verdict-precedent.md §2).

        kill is not a boolean: every new kill must carry exactly one death
        cause; a circumstantial kill must carry a revival condition (想不出
        复活条件 = 该选品味死 — the structure forces the distinction, not
        goodwill); revival_condition/successor_claim_id are only legal with
        their respective causes; survive carries no triage at all. Legacy
        events already in the store are untouched (validation is write-side).
        """
        if outcome == "survive":
            if death_cause is not None:
                raise ValueError("Survive verdict must not carry a death_cause")
            if revival_condition:
                raise ValueError("Survive verdict must not carry a revival_condition")
            if successor_claim_id:
                raise ValueError("Survive verdict must not carry a successor_claim_id")
            return
        # outcome == "kill"
        if death_cause is None:
            raise ValueError(
                "Kill verdict requires a death_cause; "
                f"one of {sorted(DEATH_CAUSES)}"
            )
        if death_cause not in DEATH_CAUSES:
            raise ValueError(
                f"Unknown death_cause {death_cause!r}; "
                f"must be one of {sorted(DEATH_CAUSES)}"
            )
        if death_cause == "circumstantial":
            if not (revival_condition and revival_condition.strip()):
                raise ValueError(
                    "A circumstantial kill requires a revival_condition — "
                    "if none can be stated, the death_cause is not_worth"
                )
        elif revival_condition:
            raise ValueError(
                "revival_condition is only valid with death_cause='circumstantial'"
            )
        if death_cause != "boundary" and successor_claim_id:
            raise ValueError(
                "successor_claim_id is only valid with death_cause='boundary'"
            )

    def verdict(
        self,
        artifact_id: str,
        claim_id: str,
        outcome: str,
        rationale: str,
        challenge_id: str | None = None,
        death_cause: str | None = None,
        revival_condition: str | None = None,
        successor_claim_id: str | None = None,
    ) -> Event:
        """Judge verdict on a claim. Appends VERDICT event.

        outcome must be "survive" or "kill".
        actor="system", confirmed=False (system judgment needs user confirmation).
        target_ref=claim_id.
        Killed ideas permanently remain in trajectory.

        死因分诊: a kill MUST carry ``death_cause`` (one of DEATH_CAUSES); a
        circumstantial kill MUST carry ``revival_condition``; a boundary kill
        MAY name ``successor_claim_id`` (the narrowed claim that lives on —
        the corpus graph projects it into a deterministic ``narrowed_from``
        edge). survive carries none of these. See ``_validate_death_triage``.

        ``challenge_id`` is optional and additive: when provided it is recorded
        in the payload so the verdict can be paired to the specific challenge it
        resolves (see ``answer``). Omitting it keeps legacy behavior intact.

        Validates: at least one CHALLENGE event must exist.
        """
        self._assert_has_challenge(artifact_id)
        if outcome not in ("survive", "kill"):
            raise ValueError(
                f"Verdict outcome must be 'survive' or 'kill', got {outcome!r}"
            )
        self._validate_death_triage(
            outcome, death_cause, revival_condition, successor_claim_id
        )
        payload: dict = {"outcome": outcome, "rationale": rationale}
        if challenge_id is not None:
            payload["challenge_id"] = challenge_id
        if death_cause is not None:
            payload["death_cause"] = death_cause
        if revival_condition is not None:
            payload["revival_condition"] = revival_condition
        if successor_claim_id is not None:
            payload["successor_claim_id"] = successor_claim_id
        event = make_event(
            type=VERDICT,
            actor="system",
            confirmed=False,
            target_ref=claim_id,
            payload=payload,
        )
        return self._event_service.append_event(artifact_id, event)

    def bypass(self, artifact_id: str, claim_id: str) -> Event:
        """Skip grill for a claim, mark debt=True.

        Appends VERDICT event with outcome="survive", debt=True, confirmed=False.
        Debt must be repaid (confirmed) before promote/export/reference.

        Validates: at least one CHALLENGE event must exist.
        """
        self._assert_has_challenge(artifact_id)
        event = make_event(
            type=VERDICT,
            actor="system",
            confirmed=False,
            debt=True,
            target_ref=claim_id,
            payload={"outcome": "survive", "rationale": "bypass — debt incurred"},
        )
        return self._event_service.append_event(artifact_id, event)

    # ------------------------------------------------------------------
    # Auto-grill (LLM-powered)
    # ------------------------------------------------------------------

    @staticmethod
    def _bearing_evidence(evidence_events: list[Event]) -> list[Event]:
        """Confirmed grounds that actually BEAR on the claim.

        ``silent`` grounds (查无) relate nothing and never enter the evidence
        block, so they are excluded here too — ``evidence_count`` /
        ``grounded_material_ids`` provenance must describe exactly what the
        LLM saw. supports / contradicts / legacy 未分态 (not_supported) all
        bear and stay in.
        """
        return [
            e
            for e in evidence_events
            if ground_stance(e.payload)
            in ("supports", "contradicts", "not_supported")
        ]

    def _kill_precedents(self, artifact_id: str, claim_id: str) -> list[ClaimPrecedent]:
        """Library-wide KILL 判例 to aim the next question (判例先验).

        Scope mirrors the glossary: **Library 内穿透、跨库硬墙** — every killed
        claim in the current artifact's Library qualifies (regardless of topic
        or which artifact it was parked in), nothing outside it ever does. The
        claim being grilled is excluded from its own precedent set.

        Deliberately NOT topic-prefiltered (spec §2 Q3): the precedents worth
        the most are the cross-topic ones — the same death recurring on
        unrelated subjects — and lexical prefiltering drops exactly those,
        degrading 判例先验 into a shadow of ②跨想法矛盾检测.

        Trust chain is inherited, not rebuilt: ``verdict_precedent`` only reads
        confirmed, non-retracted verdicts, so every injected rationale is one
        the user wrote or signed. Legacy kills carry ``death_cause=None`` and
        render as "unclassified" — never guessed into a cause.

        Returns ``[]`` (⇒ today's prompt verbatim) when no repository is wired,
        when the artifact cannot be resolved, or when the Library holds no
        kills at all.
        """
        from cui.legacy_archive.lens.precedent import DatedPrecedent, select_kill_precedents
        from cui.legacy_archive.prompts import ClaimPrecedent

        if self._repo is None:
            return []
        artifact = self._repo.get_artifact(artifact_id)
        if artifact is None:
            return []

        dated: list[DatedPrecedent] = []
        streams: dict[str, list[Event]] = {}  # claims sharing an artifact read it once
        for claim in self._repo.list_claims(artifact.library_id):
            if claim.id == claim_id or not claim.artifact_ids:
                continue
            parked_in = claim.artifact_ids[0]
            if parked_in not in streams:
                streams[parked_in] = self._store.get_events(parked_in)
            precedent = verdict_precedent(streams[parked_in], claim.id)
            # survive/open claims and (defensively) any precedent without a
            # verdict ts — which the budget orders on — are not 判例 here.
            if precedent is None or precedent.outcome != "kill" or precedent.ts is None:
                continue
            dated.append(
                DatedPrecedent(
                    ts=precedent.ts,
                    precedent=ClaimPrecedent(
                        body=claim.body,
                        # claim_status vocabulary — what the prompt formatter
                        # gates the death-cause line on.
                        outcome="killed",
                        claim_id=claim.id,
                        death_cause=precedent.death_cause,
                        rationale=precedent.rationale,
                        revival_condition=precedent.revival_condition,
                    ),
                )
            )
        return select_kill_precedents(dated)

    @staticmethod
    def _filter_precedent_refs(
        reported, injected: list[ClaimPrecedent]
    ) -> list[str]:
        """Drop hallucinated precedent references (同 lens_service 既有手法).

        Only ids that were actually injected into the prompt survive; order is
        preserved and duplicates collapse. A reference the user cannot click
        back to is a fabricated provenance — and ``precedent_refs`` is the only
        thing that makes 判例先验 auditable instead of a black-box 改良.
        """
        injected_ids = {p.claim_id for p in injected}
        refs: list[str] = []
        if not isinstance(reported, list):
            return refs
        for ref in reported:
            if isinstance(ref, str) and ref in injected_ids and ref not in refs:
                refs.append(ref)
        return refs

    def auto_challenge(self, artifact_id: str, claim_id: str, claim_body: str, context: str = "") -> Event:
        """LLM-generated challenge. confirmed=False per spec §2.6.

        判例先验 (spec-precedent-prior): the researcher's own Library-wide KILL
        precedents ride into the prompt to aim the question at their recurring
        weakness, and the precedents the model actually used are recorded on
        the event as ``precedent_refs`` (hallucinated ids filtered out). With
        no kill precedents the prompt is byte-identical to the legacy one.
        """
        if self._llm is None:
            raise LLMNotConfiguredError("LLM client not configured")
        from cui.legacy_archive.prompts import build_challenge_prompt, format_evidence_block
        self._assert_artifact_was_parked(artifact_id)
        evidence_events = self._bearing_evidence(
            confirmed_ground_evidence(
                self._store.get_events(artifact_id), claim_id
            )
        )
        evidence = format_evidence_block(evidence_events)
        precedents = self._kill_precedents(artifact_id, claim_id)
        system, user = build_challenge_prompt(claim_body, context, evidence, precedents)
        result = self._llm.complete_json(system, user)
        question = result.get("question", "")
        if not question:
            raise LLMResponseError("LLM returned empty challenge question")
        event = make_event(
            type=CHALLENGE, actor="system", confirmed=False,
            target_ref=claim_id,
            payload={
                "question": question,
                "target_aspect": result.get("target_aspect", ""),
                "auto_generated": True,
                "evidence_count": len(evidence_events),
                "grounded_material_ids": [e.payload.get("material_id") for e in evidence_events],
                "precedent_refs": self._filter_precedent_refs(
                    result.get("precedent_refs"), precedents
                ),
            },
        )
        return self._event_service.append_event(artifact_id, event)

    def auto_verdict(
        self,
        artifact_id: str,
        claim_id: str,
        claim_body: str,
        question: str,
        answer: str,
        challenge_id: str | None = None,
    ) -> Event:
        """LLM-generated verdict. confirmed=False per spec §2.6.

        死因分诊: on a kill the LLM must also propose a ``death_cause`` (and a
        ``revival_condition`` when circumstantial). 机器起草人签名 — the
        proposal still goes through the confirmed=False + human CONFIRM gate,
        where the user can amend it. Invalid enum values raise
        ``LLMResponseError`` (existing pattern); stray triage fields on a
        survive proposal are dropped as noise rather than failing the call.

        ``challenge_id`` is optional and additive — when provided it is recorded
        in the payload so the verdict pairs to the specific challenge it resolves
        (see ``answer``/``verdict``). Omitting it keeps legacy behavior intact.

        RED LINE — auto_verdict NEVER eats 判例 (spec-precedent-prior §2 Q2).
        auto_challenge does, because asking a sharper question is 取证 and can
        be automated; judging "more like you used to judge" is 定见 and is not
        the machine's to make. Feeding kill precedents in here would be 前科
        定罪: the model tilts toward kill because similar claims died before —
        manufacturing consistency instead of seeking truth, and degrading the
        Lens from reflected taste into anchoring inertia. This asymmetry is the
        structural defense; do NOT "wire it up here too" for symmetry.
        """
        if self._llm is None:
            raise LLMNotConfiguredError("LLM client not configured")
        from cui.legacy_archive.prompts import build_verdict_prompt, format_evidence_block
        self._assert_has_challenge(artifact_id)
        evidence_events = self._bearing_evidence(
            confirmed_ground_evidence(
                self._store.get_events(artifact_id), claim_id
            )
        )
        evidence = format_evidence_block(evidence_events)
        system, user = build_verdict_prompt(claim_body, question, answer, evidence)
        result = self._llm.complete_json(system, user)
        outcome = result.get("outcome", "")
        if outcome not in ("survive", "kill"):
            raise LLMResponseError(f"LLM returned invalid verdict outcome: {outcome!r}")
        death_cause = result.get("death_cause") or None
        revival_condition = result.get("revival_condition") or None
        if outcome == "survive":
            death_cause = None
            revival_condition = None
        else:
            if death_cause not in DEATH_CAUSES:
                raise LLMResponseError(
                    f"LLM returned invalid death_cause: {death_cause!r}"
                )
            if death_cause == "circumstantial":
                if not revival_condition:
                    raise LLMResponseError(
                        "LLM proposed a circumstantial kill without a revival_condition"
                    )
            else:
                revival_condition = None
        payload: dict = {
            "outcome": outcome,
            "rationale": result.get("rationale", ""),
            "confidence": result.get("confidence", 0.0),
            "auto_generated": True,
            "evidence_count": len(evidence_events),
            "grounded_material_ids": [e.payload.get("material_id") for e in evidence_events],
        }
        if death_cause is not None:
            payload["death_cause"] = death_cause
        if revival_condition is not None:
            payload["revival_condition"] = revival_condition
        if challenge_id is not None:
            payload["challenge_id"] = challenge_id
        event = make_event(
            type=VERDICT, actor="system", confirmed=False,
            target_ref=claim_id,
            payload=payload,
        )
        return self._event_service.append_event(artifact_id, event)
