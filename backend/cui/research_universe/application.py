"""Slice 1 semantic commands, narrow challenge port, and pure event projections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4, uuid5, NAMESPACE_URL

from cui.research_universe.domain.events import (
    ChallengeAnsweredPayload, ChallengeCreatedPayload, ChallengeDeferredPayload,
    ChallengeWithdrawnPayload, ClaimCreatedPayload, ClaimForgedFromCapturePayload,
    DirectionCreatedPayload, DirectionPropositionRephrasedPayload,
    DirectionStatusDeclaredPayload,
    EvidenceRelationConfirmedPayload, EvidenceRelationCorrectedPayload,
    EvidenceRelationProposedPayload, EvidenceRelationRejectedPayload,
    EvidenceRelationWithdrawnPayload, ExplorationAnchorCreatedPayload,
    ExplorationNoteSavedPayload, GapCandidateConfirmedPayload,
    GapCandidateCorrectedPayload, GapCandidateProposedPayload,
    GapCandidateRejectedPayload, GapCandidateWithdrawnPayload, MaterialAddedPayload,
    ParkReleasedPayload, PendingNativeEvent, ReviewRoundStartedPayload,
    VerdictConfirmedPayload, WorkspaceAbsorbedPayload, WorkspaceBranchedPayload,
    WorkspaceConcludedPayload, WorkspaceCreatedPayload,
    WorkspaceCrystallizationAttachedPayload, WorkspaceDirectionAttachedPayload,
    WorkspaceDirectionDetachedPayload, WorkspacePausedPayload, WorkspaceReopenedPayload,
)
from cui.research_universe.store.event_store import CommitResult, NativeEventStore, command_fingerprint
from cui.research_universe.command_guard import CommandExecutionGuard


@dataclass(frozen=True)
class ChallengeDraft:
    attack_surface: str
    why_it_matters: str
    self_check_method: str
    prompt_version: str
    model_identifier: str | None
    basis_refs: list[str]
    uncertainty: str


@dataclass(frozen=True)
class EvidenceCandidateDraft:
    relation: str
    rationale: str | None
    evidence_highlight: str | None
    uncertainty: str | None
    prompt_version: str
    model_identifier: str | None
    basis_refs: list[str]


class ChallengeGenerator(Protocol):
    def generate(self, *, question: str, claim: str) -> ChallengeDraft: ...
    def generate_additional(self, *, question: str, claim: str, prior_attack_surfaces: list[str]) -> ChallengeDraft: ...


class EvidenceCandidateGenerator(Protocol):
    def generate(self, *, claim: str, material_excerpt: str, parse_status: str) -> EvidenceCandidateDraft: ...


class ChallengeGenerationFailed(Exception): pass
class EvidenceGenerationFailed(Exception): pass
class NotFound(Exception): pass
class BoundaryViolation(Exception): pass


def _events(store: NativeEventStore, universe_id: str):
    return store.read_events(universe_id)


def _round_verdicts(events) -> dict[str, dict]:
    """round_id -> immutable verdict summary, derived solely from verdict_confirmed events."""
    result: dict[str, dict] = {}
    for event in events:
        if event.event_type == "verdict_confirmed":
            p = event.validated_payload()
            result[p.round_id] = {"round_id": p.round_id, "workspace_id": p.workspace_id, "claim_id": p.claim_id, "verdict_type": p.verdict_type, "user_reason": p.user_reason, "revival_condition": p.revival_condition}
    return result


def _challenge_states(events) -> dict[str, dict]:
    """challenge_id -> full derived challenge state (status, answers, defer/withdraw info, sequence).

    Status precedence: round verdict > deferred > withdrawn > answered > pending.
    """
    base: dict[str, dict] = {}
    answers: dict[str, list[dict]] = {}
    deferred: dict[str, dict] = {}
    withdrawn: dict[str, dict] = {}
    sequences: dict[str, int] = {}
    for event in events:
        p = event.validated_payload()
        if event.aggregate_type == "challenge":
            sequences[event.aggregate_id] = event.sequence + 1
        if event.event_type == "challenge_created":
            base[p.challenge_id] = {"id": p.challenge_id, "review_round_id": p.round_id, "claim_id": p.claim_id, "attack_surface": p.attack_surface, "why_it_matters": p.why_it_matters, "self_check_method": p.self_check_method, "provenance": {"generator_kind": p.generator_kind, "prompt_version": p.prompt_version, "model_identifier": p.model_identifier, "basis_refs": p.basis_refs, "uncertainty": p.uncertainty}}
        elif event.event_type == "challenge_answered":
            answers.setdefault(p.challenge_id, []).append({"version_id": p.answer_version_id, "text": p.answer_text, "provisional_anchor_refs": p.provisional_anchor_refs, "sequence": event.sequence})
        elif event.event_type == "challenge_deferred":
            deferred[p.challenge_id] = {"reason": p.reason, "condition": p.condition}
        elif event.event_type == "challenge_withdrawn":
            withdrawn[p.challenge_id] = {"reason": p.reason}
    round_verdicts = _round_verdicts(events)
    states: dict[str, dict] = {}
    for cid, info in base.items():
        entry = {**info, "answers": answers.get(cid, []), "sequence": sequences.get(cid, 1)}
        if cid in withdrawn: entry["withdraw"] = withdrawn[cid]
        if cid in deferred: entry["defer"] = deferred[cid]
        if info["review_round_id"] in round_verdicts:
            entry["status"] = "resolved_by_verdict"
        elif cid in withdrawn:
            entry["status"] = "withdrawn"
        elif cid in deferred:
            entry["status"] = "deferred"
        elif entry["answers"]:
            entry["status"] = "answered"
        else:
            entry["status"] = "pending"
        states[cid] = entry
    return states


def _evidence_candidate_states(events) -> dict[str, dict]:
    """candidate_id -> full derived evidence candidate state.

    A candidate is pending until exactly one immutable terminal decision
    (confirmed / corrected / rejected / withdrawn).  Old decisions are never
    rewritten; only a NEW candidate can re-open the question.
    """
    base: dict[str, dict] = {}
    decisions: dict[str, dict] = {}
    sequences: dict[str, int] = {}
    for event in events:
        p = event.validated_payload()
        if event.aggregate_type == "evidence_candidate":
            sequences[event.aggregate_id] = event.sequence + 1
        if event.event_type == "evidence_relation_proposed":
            base[p.candidate_id] = {
                "id": p.candidate_id,
                "round_id": p.round_id,
                "workspace_id": p.workspace_id,
                "claim_snapshot": {"id": p.claim_id, "version_id": p.claim_version_id, "text": p.claim_text},
                "material_anchor": {"id": p.material_id, "excerpt": p.material_excerpt, "source_locator": p.material_source_locator},
                "relation": p.relation,
                "uncertainty": p.uncertainty,
                "rationale": p.rationale,
                "evidence_highlight": p.evidence_highlight,
                "provenance": {"generator_kind": p.generator_kind, "prompt_version": p.prompt_version, "model_identifier": p.model_identifier, "basis_refs": p.basis_refs},
            }
        elif event.event_type == "evidence_relation_confirmed":
            decisions[p.candidate_id] = {"status": "confirmed", "relation": p.relation, "reason": p.user_reason}
        elif event.event_type == "evidence_relation_corrected":
            decisions[p.candidate_id] = {"status": "corrected", "relation": p.corrected_relation, "prior_relation": p.prior_relation, "reason": p.user_reason}
        elif event.event_type == "evidence_relation_rejected":
            decisions[p.candidate_id] = {"status": "rejected", "reason": p.user_reason}
        elif event.event_type == "evidence_relation_withdrawn":
            decisions[p.candidate_id] = {"status": "withdrawn", "reason": p.user_reason}
    states: dict[str, dict] = {}
    for cid, info in base.items():
        entry = {**info, "sequence": sequences.get(cid, 1)}
        decision = decisions.get(cid)
        if decision is not None:
            entry["status"] = decision["status"]
            entry["decision_reason"] = decision.get("reason")
            if "relation" in decision:
                entry["relation"] = decision["relation"]
            if decision.get("prior_relation") is not None:
                entry["prior_relation"] = decision["prior_relation"]
        else:
            entry["status"] = "pending"
        states[cid] = entry
    return states


def _gap_candidate_states(events) -> dict[str, dict]:
    """gap_candidate_id -> derived gap candidate state (workspace-scoped).

    Mirrors the evidence candidate lifecycle: proposed stays pending until
    exactly one immutable terminal decision (confirmed / corrected / rejected /
    withdrawn). Old decisions are never rewritten; a new candidate re-opens.
    """
    base: dict[str, dict] = {}
    decisions: dict[str, dict] = {}
    sequences: dict[str, int] = {}
    for event in events:
        p = event.validated_payload()
        if event.aggregate_type == "gap_candidate":
            sequences[event.aggregate_id] = event.sequence + 1
        if event.event_type == "gap_candidate_proposed":
            base[p.gap_candidate_id] = {
                "id": p.gap_candidate_id,
                "workspace_id": p.workspace_id,
                "coverage_statement": p.coverage_statement,
                "search_record": {"query": p.search_query, "scope": p.search_scope, "matched_locators": p.matched_locators, "searched_at": p.searched_at},
                "counterexample_invitation": p.counterexample_invitation,
                "generator_kind": p.generator_kind,
            }
        elif event.event_type == "gap_candidate_confirmed":
            decisions[p.gap_candidate_id] = {"status": "confirmed", "reason": p.user_reason}
        elif event.event_type == "gap_candidate_corrected":
            decisions[p.gap_candidate_id] = {"status": "corrected", "corrected_coverage_statement": p.corrected_coverage_statement, "reason": p.user_reason}
        elif event.event_type == "gap_candidate_rejected":
            decisions[p.gap_candidate_id] = {"status": "rejected", "reason": p.user_reason}
        elif event.event_type == "gap_candidate_withdrawn":
            decisions[p.gap_candidate_id] = {"status": "withdrawn", "reason": p.user_reason}
    states: dict[str, dict] = {}
    for cid, info in base.items():
        entry = {**info, "sequence": sequences.get(cid, 1)}
        decision = decisions.get(cid)
        if decision is not None:
            entry["status"] = decision["status"]
            entry["decision_reason"] = decision.get("reason")
            if decision.get("corrected_coverage_statement") is not None:
                entry["coverage_statement"] = decision["corrected_coverage_statement"]
        else:
            entry["status"] = "pending"
        states[cid] = entry
    return states


def _landscape(workspace: dict, claims: list[dict], verdicts: dict[str, str], confirmed_facts: list[dict], gaps: list[dict]) -> dict:
    """现状图景 (workspace-level readback): alive claims + confirmed facts + gaps."""
    return {
        "workspace_id": workspace["id"],
        "question": workspace["question"],
        "alive_claims": [c for c in claims if verdicts.get(c["id"], "open") != "refuted"],
        "claim_verdicts": {c["id"]: verdicts.get(c["id"], "open") for c in claims},
        "confirmed_facts": confirmed_facts,
        "gaps": gaps,
    }


def _ledger(challenges: list[dict]) -> dict:
    """Verdict-time ledger shape: answered / deferred / pending / brought-but-unconfirmed."""
    return {
        "answered": [c for c in challenges if c["status"] in ("answered", "resolved_by_verdict") and c["answers"]],
        "deferred": [c for c in challenges if c["status"] == "deferred"],
        "pending": [c for c in challenges if c["status"] == "pending"],
        "brought_unconfirmed": [c for c in challenges if any(a["provisional_anchor_refs"] for a in c["answers"])],
    }


def _round_next_sequence(events, round_id: str) -> int:
    return max((e.sequence + 1 for e in events if e.aggregate_type == "review_round" and e.aggregate_id == round_id), default=1)


# --- Slice 5 position / direction helpers -------------------------------------

_ALLOWED_POSITION_TRANSITIONS: dict[str, set[str]] = {
    "pause": {"exploring"},
    "reopen": {"paused", "concluded"},
    "conclude": {"exploring"},
    "branch": {"exploring", "concluded"},
    "absorb": {"exploring", "concluded"},
}


def _workspace_position(events, workspace_id: str) -> str:
    """Derive the current workspace user_position by replaying position events."""
    position = "exploring"
    for event in events:
        if event.aggregate_type != "workspace" or event.aggregate_id != workspace_id:
            continue
        if event.event_type == "workspace_paused":
            position = "paused"
        elif event.event_type == "workspace_reopened":
            position = "exploring"
        elif event.event_type == "workspace_concluded":
            position = "concluded"
        elif event.event_type == "workspace_branched":
            position = "branched"
        elif event.event_type == "workspace_absorbed":
            position = "absorbed"
    return position


def _direction_current(events, direction_id: str) -> dict | None:
    """Current proposition snapshot and declared status for a direction, or None."""
    proposition: dict | None = None
    status = "active"
    for event in events:
        p = event.validated_payload()
        if event.event_type == "direction_created" and p.direction_id == direction_id:
            proposition = {"version_id": p.proposition_version_id, "text": p.proposition_text}
        elif event.event_type == "direction_status_declared" and p.direction_id == direction_id:
            status = p.status
        elif event.event_type == "direction_proposition_rephrased" and p.direction_id == direction_id:
            proposition = {"version_id": p.new_proposition_version_id, "text": p.new_proposition_text}
    return {"proposition": proposition, "status": status} if proposition is not None else None


def _workspace_pending_count(events, workspace_id: str) -> int:
    """Number of open (pending/answered) challenges across this workspace's rounds."""
    round_ids = [p.round_id for e in events if e.event_type == "review_round_started" and (p := e.validated_payload()).workspace_id == workspace_id]
    challenge_states = _challenge_states(events)
    return len([c for c in challenge_states.values() if c["review_round_id"] in round_ids and c["status"] in ("pending", "answered")])


def workspace_projection(store: NativeEventStore, universe_id: str, workspace_id: str) -> dict:
    workspace = None; note_revisions = []; anchors = []; claims = []; rounds = []; park_release_refs = []; forged = []; materials = []
    workspace_sequence = 0
    position = "exploring"; conclusion: dict | None = None
    direction_links: list[dict] = []; detached_links: set[str] = set()
    successor_workspace_id: str | None = None; absorb_target_workspace_id: str | None = None
    events = _events(store, universe_id)
    round_verdicts = _round_verdicts(events)
    for event in events:
        p = event.validated_payload()
        if event.aggregate_type == "workspace" and event.aggregate_id == workspace_id:
            workspace_sequence = event.sequence + 1
        if event.event_type == "workspace_created" and p.workspace_id == workspace_id:
            workspace = {"id": p.workspace_id, "question": {"version_id": p.initial_question_version_id, "text": p.initial_question_text}}
        elif event.event_type == "exploration_note_saved" and p.workspace_id == workspace_id:
            note_revisions.append({"id": p.note_revision_id, "note_id": p.note_id, "text": p.text, "sequence": event.sequence})
        elif event.event_type == "exploration_anchor_created" and p.workspace_id == workspace_id:
            anchors.append({"id": p.anchor_id, "note_id": p.note_id, "note_revision_id": p.note_revision_id, "start": p.start, "end": p.end, "selected_text": p.selected_text})
        elif event.event_type == "claim_created" and p.origin_workspace_id == workspace_id:
            claims.append({"id": p.claim_id, "version_id": p.claim_version_id, "text": p.claim_text, "sequence": event.sequence})
        elif event.event_type == "park_released" and p.workspace_id == workspace_id:
            park_release_refs.append({"id": p.release_id, "capture_id": p.capture_id, "provisional_role": p.provisional_role})
        elif event.event_type == "claim_forged_from_capture" and p.workspace_id == workspace_id:
            forged.append({"id": p.provenance_id, "claim_id": p.claim_id, "capture_id": p.capture_id, "release_id": p.release_id})
        elif event.event_type == "review_round_started" and p.workspace_id == workspace_id:
            rounds.append({"id": p.round_id, "claim_id": p.claim_id, "question_snapshot": {"version_id": p.question_version_id, "text": p.question_text}, "claim_snapshot": {"id": p.claim_id, "version_id": p.claim_version_id, "text": p.claim_text}, "verdict": round_verdicts.get(p.round_id), "sequence": _round_next_sequence(events, p.round_id)})
        elif event.event_type == "material_added" and p.workspace_id == workspace_id:
            materials.append({"id": p.material_id, "workspace_id": p.workspace_id, "excerpt": p.excerpt, "source_locator": p.source_locator, "parse_status": p.parse_status, "purpose": p.purpose, "sequence": event.sequence})
        elif event.event_type == "workspace_paused" and p.workspace_id == workspace_id:
            position = "paused"
        elif event.event_type == "workspace_reopened" and p.workspace_id == workspace_id:
            position = "exploring"
        elif event.event_type == "workspace_concluded" and p.workspace_id == workspace_id:
            position = "concluded"
            conclusion = {"id": p.conclusion_id, "type": p.conclusion_type, "text": p.conclusion_text, "reason": p.user_reason, "basis_refs": p.basis_refs, "revival_condition": p.revival_condition, "sequence": event.sequence}
        elif event.event_type == "workspace_branched" and p.workspace_id == workspace_id:
            position = "branched"; successor_workspace_id = p.successor_workspace_id
        elif event.event_type == "workspace_absorbed" and p.workspace_id == workspace_id:
            position = "absorbed"; absorb_target_workspace_id = p.target_workspace_id
        elif event.event_type == "workspace_direction_attached" and p.workspace_id == workspace_id:
            direction_links.append({"link_id": p.direction_link_id, "direction_id": p.direction_id})
        elif event.event_type == "workspace_direction_detached" and p.workspace_id == workspace_id:
            detached_links.add(p.direction_link_id)
    if workspace is None: raise NotFound(workspace_id)
    latest_note = note_revisions[-1] if note_revisions else None
    challenge_states = _challenge_states(events)
    workspace_round_ids = {r["id"] for r in rounds}
    workspace_challenges = [challenge_states[cid] for cid in challenge_states if challenge_states[cid]["review_round_id"] in workspace_round_ids]
    candidate_states = _evidence_candidate_states(events)
    workspace_candidates = [candidate_states[cid] for cid in candidate_states if candidate_states[cid]["workspace_id"] == workspace_id]
    workspace_confirmed_facts = [c for c in workspace_candidates if c["status"] in ("confirmed", "corrected")]
    resolved_links: list[dict] = []
    for link in direction_links:
        if link["link_id"] in detached_links:
            continue
        current = _direction_current(events, link["direction_id"])
        if current is None:
            continue
        resolved_links.append({**link, "direction_proposition": current["proposition"]["text"], "status": current["status"]})
    workspace.update(
        sequence=workspace_sequence,
        note=latest_note,
        note_revisions=note_revisions,
        anchors=anchors,
        claims=claims,
        park_release_refs=park_release_refs,
        claim_forge_provenance=forged,
        review_rounds=rounds,
        materials=materials,
        pending_challenges=[x for x in workspace_challenges if x["status"] in ("pending", "answered")],
        confirmed_facts=workspace_confirmed_facts,
        user_position=position,
        conclusion=conclusion,
        direction_links=resolved_links,
        successor_workspace_id=successor_workspace_id,
        absorb_target_workspace_id=absorb_target_workspace_id,
    )
    return workspace


def review_round_projection(store: NativeEventStore, universe_id: str, round_id: str) -> dict:
    events = _events(store, universe_id)
    for event in events:
        if event.event_type == "review_round_started" and event.validated_payload().round_id == round_id:
            p = event.validated_payload()
            challenge_states = _challenge_states(events)
            challenges = [challenge_states[cid] for cid in challenge_states if challenge_states[cid]["review_round_id"] == round_id]
            candidate_states = _evidence_candidate_states(events)
            evidence_candidates = [candidate_states[cid] for cid in candidate_states if candidate_states[cid]["round_id"] == round_id]
            confirmed_facts = [c for c in evidence_candidates if c["status"] in ("confirmed", "corrected")]
            rounds = [{"id": rp.round_id, "claim_id": rp.claim_id, "question_snapshot": {"version_id": rp.question_version_id, "text": rp.question_text}, "claim_snapshot": {"id": rp.claim_id, "version_id": rp.claim_version_id, "text": rp.claim_text}, "verdict": _round_verdicts(events).get(rp.round_id)} for e in events if e.event_type == "review_round_started" and (rp := e.validated_payload()).claim_id == p.claim_id]
            return {"id": p.round_id, "workspace_id": p.workspace_id, "question_snapshot": {"version_id": p.question_version_id, "text": p.question_text}, "claim_snapshot": {"id": p.claim_id, "version_id": p.claim_version_id, "text": p.claim_text}, "verdict": _round_verdicts(events).get(round_id), "sequence": _round_next_sequence(events, round_id), "challenges": challenges, "ledger": _ledger(challenges), "rounds": rounds, "evidence_candidates": evidence_candidates, "confirmed_facts": confirmed_facts}
    raise NotFound(round_id)


def direction_projection(store: NativeEventStore, universe_id: str, direction_id: str) -> dict:
    """Direction with current proposition, declared status, rephrase history,
    attached workspaces, and crystallizations. Raises NotFound if absent."""
    events = _events(store, universe_id)
    current = _direction_current(events, direction_id)
    if current is None:
        raise NotFound(direction_id)
    direction_sequence = max((e.sequence + 1 for e in events if e.aggregate_type == "direction" and e.aggregate_id == direction_id), default=1)
    history: list[dict] = []
    link_workspaces: dict[str, str] = {}
    crystallizations: list[dict] = []
    for event in events:
        p = event.validated_payload()
        if event.event_type == "direction_proposition_rephrased" and p.direction_id == direction_id:
            history.append({"prior_proposition_version_id": p.prior_proposition_version_id, "prior_proposition_text": p.prior_proposition_text, "new_proposition_version_id": p.new_proposition_version_id, "new_proposition_text": p.new_proposition_text, "change_type": p.change_type, "user_reason": p.user_reason, "source_conclusion_ref": p.source_conclusion_ref, "sequence": event.sequence})
        elif event.event_type == "workspace_direction_attached" and p.direction_id == direction_id:
            link_workspaces[p.direction_link_id] = p.workspace_id
        elif event.event_type == "workspace_direction_detached" and p.direction_id == direction_id:
            link_workspaces.pop(p.direction_link_id, None)
        elif event.event_type == "workspace_crystallization_attached" and p.direction_id == direction_id:
            crystallizations.append({"crystallization_id": p.crystallization_id, "workspace_id": p.workspace_id, "conclusion_id": p.conclusion_id, "conclusion_text": p.conclusion_text, "conclusion_type": p.conclusion_type})
    attached: list[dict] = []
    for link_id, wid in link_workspaces.items():
        question = next((e.validated_payload().initial_question_text for e in events if e.event_type == "workspace_created" and e.validated_payload().workspace_id == wid), None)
        attached.append({"link_id": link_id, "workspace_id": wid, "question": question, "position": _workspace_position(events, wid), "pending_fact_count": _workspace_pending_count(events, wid)})
    return {"id": direction_id, "proposition": current["proposition"], "status": current["status"], "sequence": direction_sequence, "rephrase_history": history, "attached_workspaces": attached, "crystallizations": crystallizations}


def workspace_landscape_projection(store: NativeEventStore, universe_id: str, workspace_id: str) -> dict:
    """现状图景 (slice1 S1.2): workspace-level readback of alive claims, confirmed
    facts and gap candidates — the raw material a gap argument cites. Pure read;
    no new events."""
    events = _events(store, universe_id)
    workspace = workspace_projection(store, universe_id, workspace_id)
    claims = workspace["claims"]
    verdict_by_claim: dict[str, str] = {}
    for event in events:
        if event.event_type == "verdict_confirmed":
            payload = event.validated_payload()
            verdict_by_claim[payload.claim_id] = payload.verdict_type
    confirmed_facts = []
    for state in _evidence_candidate_states(events).values():
        if state["workspace_id"] != workspace_id or state["status"] not in ("confirmed", "corrected"):
            continue
        confirmed_facts.append({
            "candidate_id": state["id"],
            "claim_id": state["claim_snapshot"]["id"],
            "claim_text": state["claim_snapshot"]["text"],
            "relation": state["relation"],
            "material_locator": state["material_anchor"]["source_locator"],
            "decision_reason": state.get("decision_reason"),
        })
    gaps = [state for state in _gap_candidate_states(events).values() if state["workspace_id"] == workspace_id]
    gaps.sort(key=lambda g: g["id"])
    _DEAD = {"refuted", "not_worth"}
    alive = [c for c in claims if verdict_by_claim.get(c["id"], "open") not in _DEAD]
    return {
        "workspace_id": workspace_id,
        "question": workspace["question"],
        "alive_claims": alive,
        "claim_verdicts": {c["id"]: verdict_by_claim.get(c["id"], "open") for c in claims},
        "confirmed_facts": confirmed_facts,
        "gaps": gaps,
    }


def universe_home_projection(store: NativeEventStore, universe_id: str) -> dict:
    workspaces = []
    for event in _events(store, universe_id):
        if event.event_type == "workspace_created":
            workspaces.append(workspace_projection(store, universe_id, event.validated_payload().workspace_id))
    pending = [{**c, "workspace_id": w["id"], "question": w["question"]["text"]} for w in workspaces for c in w["pending_challenges"]]
    directions: list[dict] = []
    seen: set[str] = set()
    for event in _events(store, universe_id):
        if event.event_type != "direction_created":
            continue
        direction_id = event.validated_payload().direction_id
        if direction_id in seen:
            continue
        seen.add(direction_id)
        try:
            dp = direction_projection(store, universe_id, direction_id)
        except NotFound:
            continue
        directions.append({
            "id": dp["id"],
            "proposition": dp["proposition"]["text"] if dp["proposition"]["text"] is not None else "暂不命名",
            "status": dp["status"],
            "crystallizations": dp["crystallizations"],
            "crystallizations_count": len(dp["crystallizations"]),
            "attached_workspaces_count": len(dp["attached_workspaces"]),
        })
    return {"universe_id": universe_id, "workspaces": workspaces, "pending_facts": pending, "directions": directions}



def park_release_refs(store: NativeEventStore, universe_id: str, capture_id: str) -> list[dict]:
    return [{"universe_id": universe_id, "id": p.release_id, "capture_id": p.capture_id, "workspace_id": p.workspace_id, "provisional_role": p.provisional_role} for e in _events(store, universe_id) if e.event_type == "park_released" and (p := e.validated_payload()).capture_id == capture_id]


class Slice1Service:
    def __init__(self, store: NativeEventStore, actor_id: str | None, generator: ChallengeGenerator, evidence_generator: EvidenceCandidateGenerator | None = None, guard: CommandExecutionGuard | None = None) -> None:
        self.store, self.actor_id, self.generator, self.evidence_generator, self.guard = store, actor_id, generator, evidence_generator, guard

    def _id(self, command_id: str, kind: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"slice1:{kind}:{command_id}"))

    def _append(self, universe_id: str, command_id: str, command_type: str, payload: dict, expected: dict[tuple[str, str], int], event: PendingNativeEvent, result: dict) -> CommitResult:
        fingerprint = command_fingerprint(universe_id, command_type, payload, [(kind, ident, sequence) for (kind, ident), sequence in expected.items()])
        prior = self.store.lookup_command(universe_id, command_id, fingerprint)
        if prior: return prior
        return self.store.append(universe_id=universe_id, command_id=command_id, command_type=command_type, command_payload=payload, actor_kind="user", actor_id=self.actor_id, expected_sequences=expected, events=[event], result_payload=result)

    def _append_many(self, universe_id: str, command_id: str, command_type: str, payload: dict, expected: dict[tuple[str, str], int], events: list[PendingNativeEvent], result: dict) -> CommitResult:
        fingerprint = command_fingerprint(universe_id, command_type, payload, [(kind, ident, sequence) for (kind, ident), sequence in expected.items()])
        prior = self.store.lookup_command(universe_id, command_id, fingerprint)
        if prior: return prior
        return self.store.append(universe_id=universe_id, command_id=command_id, command_type=command_type, command_payload=payload, actor_kind="user", actor_id=self.actor_id, expected_sequences=expected, events=events, result_payload=result)

    def release_park(self, universe_id: str, capture_id: str, command_id: str, expected_sequence: int, provisional_role: str, workspace_id: str | None = None, question: str | None = None, workspace_expected_sequence: int = 0) -> CommitResult:
        if (workspace_id is None) == (question is None): raise BoundaryViolation("release requires exactly one target: existing workspace or new user-authored question")
        release_id = self._id(command_id, "park-release")
        events = []
        expected = {("park_release", release_id): expected_sequence}
        if workspace_id is None:
            workspace_id = self._id(command_id, "workspace"); qid = self._id(command_id, "question")
            wp = WorkspaceCreatedPayload(workspace_id=workspace_id, initial_question_version_id=qid, initial_question_text=question or "")
            events.append(PendingNativeEvent(event_type="workspace_created", payload=wp.model_dump(), aggregate_type="workspace", aggregate_id=workspace_id))
            expected[("workspace", workspace_id)] = workspace_expected_sequence
        else:
            workspace_projection(self.store, universe_id, workspace_id)
        rp = ParkReleasedPayload(release_id=release_id, capture_id=capture_id, workspace_id=workspace_id, provisional_role=provisional_role) # type: ignore[arg-type]
        events.append(PendingNativeEvent(event_type="park_released", payload=rp.model_dump(), aggregate_type="park_release", aggregate_id=release_id))
        payload = {"capture_id": capture_id, "workspace_id": workspace_id, "question": question, "provisional_role": provisional_role}
        result = {"capture_id": capture_id, "release_id": release_id, "workspace_id": workspace_id, "aggregate_sequences": {"park_release": expected_sequence + 1}}
        if question is not None: result["aggregate_sequences"]["workspace"] = workspace_expected_sequence + 1
        return self._append_many(universe_id, command_id, "release_park", payload, expected, events, result)

    def forge_claim_from_capture(self, universe_id: str, workspace_id: str, claim_id: str, capture_id: str, release_id: str, command_id: str, expected_sequence: int) -> CommitResult:
        workspace_projection(self.store, universe_id, workspace_id);
        if not any(e.event_type == "claim_created" and e.validated_payload().claim_id == claim_id and e.validated_payload().origin_workspace_id == workspace_id for e in _events(self.store, universe_id)): raise NotFound(claim_id)
        if not any(e.event_type == "park_released" and e.validated_payload().release_id == release_id and e.validated_payload().capture_id == capture_id and e.validated_payload().workspace_id == workspace_id for e in _events(self.store, universe_id)): raise BoundaryViolation("forge provenance requires a release into the claim workspace")
        provenance_id = self._id(command_id, "claim-forge-provenance")
        p = ClaimForgedFromCapturePayload(provenance_id=provenance_id, claim_id=claim_id, capture_id=capture_id, release_id=release_id, workspace_id=workspace_id)
        return self._append(universe_id, command_id, "forge_claim_from_capture", p.model_dump(), {("claim_forge_provenance", provenance_id): expected_sequence}, PendingNativeEvent(event_type="claim_forged_from_capture", payload=p.model_dump(), aggregate_type="claim_forge_provenance", aggregate_id=provenance_id), {"provenance_id": provenance_id, "claim_id": claim_id, "aggregate_sequences": {"claim_forge_provenance": expected_sequence + 1}})

    def create_workspace(self, universe_id: str, command_id: str, expected_sequence: int, question: str) -> CommitResult:
        wid, qid = self._id(command_id, "workspace"), self._id(command_id, "question"); p = WorkspaceCreatedPayload(workspace_id=wid, initial_question_version_id=qid, initial_question_text=question)
        return self._append(universe_id, command_id, "create_workspace", {"question": question}, {("workspace", wid): expected_sequence}, PendingNativeEvent(event_type="workspace_created", payload=p.model_dump(), aggregate_type="workspace", aggregate_id=wid), {"workspace_id": wid, "aggregate_sequences": {"workspace": expected_sequence + 1}})

    def save_note(self, universe_id: str, workspace_id: str, command_id: str, expected_sequence: int, text: str) -> CommitResult:
        # A workspace owns exactly one continuously explored note.  Its identity is
        # independent of a save command; each command contributes an immutable revision.
        workspace_projection(self.store, universe_id, workspace_id)
        note_id = str(uuid5(NAMESPACE_URL, f"slice1:{universe_id}:workspace-note:{workspace_id}"))
        p = ExplorationNoteSavedPayload(note_id=note_id, note_revision_id=self._id(command_id, "note-revision"), workspace_id=workspace_id, text=text)
        return self._append(universe_id, command_id, "save_note", {"workspace_id": workspace_id, "text": text}, {("workspace", workspace_id): expected_sequence}, PendingNativeEvent(event_type="exploration_note_saved", payload=p.model_dump(), aggregate_type="workspace", aggregate_id=workspace_id), {"note_id": p.note_id, "note_revision_id": p.note_revision_id, "aggregate_sequences": {"workspace": expected_sequence + 1}})

    def create_anchor(self, universe_id: str, workspace_id: str, command_id: str, expected_sequence: int, note_id: str, note_revision_id: str, start: int, end: int, selected_text: str) -> CommitResult:
        w = workspace_projection(self.store, universe_id, workspace_id)
        if not any(n["note_id"] == note_id and n["id"] == note_revision_id and n["text"][start:end] == selected_text for n in w["note_revisions"]): raise BoundaryViolation("anchor must bind an extant note revision and exact range")
        p = ExplorationAnchorCreatedPayload(anchor_id=self._id(command_id, "anchor"), workspace_id=workspace_id, note_id=note_id, note_revision_id=note_revision_id, start=start, end=end, selected_text=selected_text)
        return self._append(universe_id, command_id, "create_anchor", p.model_dump(), {("workspace", workspace_id): expected_sequence}, PendingNativeEvent(event_type="exploration_anchor_created", payload=p.model_dump(), aggregate_type="workspace", aggregate_id=workspace_id), {"anchor_id": p.anchor_id, "aggregate_sequences": {"workspace": expected_sequence + 1}})

    def create_claim(self, universe_id: str, workspace_id: str, command_id: str, expected_sequence: int, text: str) -> CommitResult:
        workspace_projection(self.store, universe_id, workspace_id)
        cid, vid = self._id(command_id, "claim"), self._id(command_id, "claim-version"); p = ClaimCreatedPayload(claim_id=cid, origin_workspace_id=workspace_id, claim_version_id=vid, claim_text=text)
        return self._append(universe_id, command_id, "create_claim", {"workspace_id": workspace_id, "text": text}, {("claim", cid): expected_sequence}, PendingNativeEvent(event_type="claim_created", payload=p.model_dump(), aggregate_type="claim", aggregate_id=cid), {"claim_id": cid, "claim_version_id": vid, "aggregate_sequences": {"claim": expected_sequence + 1}})

    def start_review_round(self, universe_id: str, claim_id: str, command_id: str, expected_sequence: int) -> CommitResult:
        claim = next((e.validated_payload() for e in _events(self.store, universe_id) if e.event_type == "claim_created" and e.validated_payload().claim_id == claim_id), None)
        if claim is None: raise NotFound(claim_id)
        workspace = workspace_projection(self.store, universe_id, claim.origin_workspace_id)
        rid = str(uuid5(NAMESPACE_URL, f"{universe_id}:review-round:{command_id}"))
        challenge_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:challenge:{command_id}"))
        command_payload = {"claim_id": claim_id, "workspace_id": claim.origin_workspace_id}
        targets = [("review_round", rid, expected_sequence), ("challenge", challenge_id, 0)]
        execution = self.guard.command_execution if self.guard else self.store.command_execution
        with execution(universe_id, command_id):
            prior = self.store.lookup_command(universe_id, command_id, command_fingerprint(universe_id, "start_review_round", command_payload, targets))
            if prior: return prior
            try: draft = self.generator.generate(question=workspace["question"]["text"], claim=claim.claim_text)
            except Exception as exc: raise ChallengeGenerationFailed(str(exc)) from exc
            round_payload = ReviewRoundStartedPayload(round_id=rid, workspace_id=claim.origin_workspace_id, question_version_id=workspace["question"]["version_id"], question_text=workspace["question"]["text"], claim_id=claim.claim_id, claim_version_id=claim.claim_version_id, claim_text=claim.claim_text)
            challenge_payload = ChallengeCreatedPayload(challenge_id=challenge_id, round_id=rid, claim_id=claim.claim_id, claim_version_id=claim.claim_version_id, claim_text=claim.claim_text, attack_surface=draft.attack_surface, why_it_matters=draft.why_it_matters, self_check_method=draft.self_check_method, generator_kind="system", prompt_version=draft.prompt_version, model_identifier=draft.model_identifier, basis_refs=draft.basis_refs, uncertainty=draft.uncertainty)
            return self.store.append(universe_id=universe_id, command_id=command_id, command_type="start_review_round", command_payload=command_payload, actor_kind="user", actor_id=self.actor_id, expected_sequences={("review_round", rid): expected_sequence, ("challenge", challenge_id): 0}, events=[PendingNativeEvent(event_type="review_round_started", payload=round_payload.model_dump(), aggregate_type="review_round", aggregate_id=rid), PendingNativeEvent(event_type="challenge_created", payload=challenge_payload.model_dump(), aggregate_type="challenge", aggregate_id=challenge_id)], result_payload={"review_round_id": rid, "challenge_id": challenge_id, "aggregate_sequences": {"review_round": expected_sequence + 1, "challenge": 1}})

    def generate_challenge(self, universe_id: str, round_id: str, command_id: str, expected_sequence: int) -> CommitResult:
        raise BoundaryViolation("Slice 1 creates the initial challenge atomically with its review round")

    def generate_additional_challenge(self, universe_id: str, round_id: str, command_id: str, expected_sequence: int) -> CommitResult:
        """Explicit user command: ask the LLM for one MORE challenge on this round.

        The generated challenge attacks a DIFFERENT angle (the already-used
        attack_surfaces are handed to the generator so it never repeats).  The
        new challenge is a fresh aggregate at expected_sequence 0.  No verdict,
        claim, direction or workspace is ever auto-created here.
        """
        round_data = review_round_projection(self.store, universe_id, round_id)
        question = round_data["question_snapshot"]["text"]
        claim = round_data["claim_snapshot"]
        existing_surfaces = [c["attack_surface"] for c in round_data["challenges"]]
        existing_ids = [c["id"] for c in round_data["challenges"]]
        try:
            draft = self.generator.generate_additional(question=question, claim=claim["text"], prior_attack_surfaces=existing_surfaces)
        except Exception as exc:
            raise ChallengeGenerationFailed(str(exc)) from exc
        challenge_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:challenge:{command_id}"))
        p = ChallengeCreatedPayload(challenge_id=challenge_id, round_id=round_id, claim_id=claim["id"], claim_version_id=claim["version_id"], claim_text=claim["text"], attack_surface=draft.attack_surface, why_it_matters=draft.why_it_matters, self_check_method=draft.self_check_method, generator_kind="system", prompt_version=draft.prompt_version, model_identifier=draft.model_identifier, basis_refs=[*draft.basis_refs, *existing_ids], uncertainty=draft.uncertainty)
        return self._append(universe_id, command_id, "generate_additional_challenge", {"round_id": round_id}, {("challenge", challenge_id): expected_sequence}, PendingNativeEvent(event_type="challenge_created", payload=p.model_dump(), aggregate_type="challenge", aggregate_id=challenge_id), {"challenge_id": challenge_id, "round_id": round_id, "aggregate_sequences": {"challenge": expected_sequence + 1}})

    def generate_literature_challenge(self, universe_id: str, round_id: str, material_ids: list[str], command_id: str, expected_sequence: int) -> CommitResult:
        """Explicit user command (slice1 second cut): ask the LLM for a
        literature-grounded challenge on this round's claim.

        The chosen corpus materials are handed to the generator (excerpts
        truncated at the prompt boundary) and their locators ride as the
        challenge's basis_refs — the reference IS the basis. Same challenge
        lifecycle: a fresh challenge aggregate at expected_sequence 0.
        """
        events = _events(self.store, universe_id)
        round_payload = next((e.validated_payload() for e in events if e.event_type == "review_round_started" and e.validated_payload().round_id == round_id), None)
        if round_payload is None:
            raise NotFound(round_id)
        materials = []
        for event in events:
            if event.event_type != "material_added":
                continue
            payload = event.validated_payload()
            if payload.material_id not in material_ids:
                continue
            from cui.research_universe.corpus import corpus_workspace_ids
            allowed_workspaces = {round_payload.workspace_id} | corpus_workspace_ids()
            if payload.workspace_id not in allowed_workspaces:
                raise BoundaryViolation("material does not belong to the round's workspace nor the corpus")
            if payload.purpose != "evidence" or payload.parse_status != "parsed":
                raise BoundaryViolation("literature challenge materials must be parsed evidence materials")
            materials.append({"material_id": payload.material_id, "locator": payload.source_locator or payload.material_id, "excerpt": payload.excerpt})
        missing = set(material_ids) - {m["material_id"] for m in materials}
        if missing:
            raise NotFound(sorted(missing)[0])
        gen = getattr(self.generator, "generate_literature", None)
        if gen is None:
            raise BoundaryViolation("challenge generator has no literature support")
        try:
            draft = gen(question=round_payload.question_text, claim=round_payload.claim_text, materials=materials)
        except Exception as exc:
            raise ChallengeGenerationFailed(str(exc)) from exc
        challenge_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:challenge:{command_id}"))
        p = ChallengeCreatedPayload(challenge_id=challenge_id, round_id=round_id, claim_id=round_payload.claim_id, claim_version_id=round_payload.claim_version_id, claim_text=round_payload.claim_text, attack_surface=draft.attack_surface, why_it_matters=draft.why_it_matters, self_check_method=draft.self_check_method, generator_kind="system", prompt_version=draft.prompt_version, model_identifier=draft.model_identifier, basis_refs=draft.basis_refs, uncertainty=draft.uncertainty)
        return self._append(universe_id, command_id, "generate_literature_challenge", {"round_id": round_id, "material_ids": material_ids}, {("challenge", challenge_id): expected_sequence}, PendingNativeEvent(event_type="challenge_created", payload=p.model_dump(), aggregate_type="challenge", aggregate_id=challenge_id), {"challenge_id": challenge_id, "round_id": round_id, "aggregate_sequences": {"challenge": expected_sequence + 1}})

    def generate_evidence_candidate(self, universe_id: str, round_id: str, material_id: str, command_id: str, expected_sequence: int) -> CommitResult:
        """Explicit user command: ask the LLM to propose an evidence relation.

        Iron rule from Slice 4: a material whose parse failed can NEVER
        masquerade as silent (or any other assessable relation) — the relation
        is forced to cannot_assess regardless of what the LLM returned.  The
        candidate enters the SAME pending -> confirm/correct/reject/withdraw
        lifecycle as a manual candidate.
        """
        events = _events(self.store, universe_id)
        round_payload = next((e.validated_payload() for e in events if e.event_type == "review_round_started" and e.validated_payload().round_id == round_id), None)
        if round_payload is None: raise NotFound(round_id)
        material_payload = next((e.validated_payload() for e in events if e.event_type == "material_added" and e.validated_payload().material_id == material_id), None)
        if material_payload is None: raise NotFound(material_id)
        if material_payload.workspace_id != round_payload.workspace_id: raise BoundaryViolation("material does not belong to the round's workspace")
        if material_payload.purpose != "evidence": raise BoundaryViolation("reference material never enters the evidence candidate flow")
        if self.evidence_generator is None:
            raise EvidenceGenerationFailed("no evidence candidate generator is configured")
        try:
            draft = self.evidence_generator.generate(claim=round_payload.claim_text, material_excerpt=material_payload.excerpt, parse_status=material_payload.parse_status)
        except Exception as exc:
            raise EvidenceGenerationFailed(str(exc)) from exc
        relation = draft.relation
        if material_payload.parse_status == "failed":
            relation = "cannot_assess"
        candidate_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:evidence-candidate:{command_id}"))
        p = EvidenceRelationProposedPayload(candidate_id=candidate_id, round_id=round_id, workspace_id=round_payload.workspace_id, claim_id=round_payload.claim_id, claim_version_id=round_payload.claim_version_id, claim_text=round_payload.claim_text, material_id=material_payload.material_id, material_excerpt=material_payload.excerpt, material_source_locator=material_payload.source_locator, relation=relation, uncertainty=draft.uncertainty, generator_kind="system", prompt_version=draft.prompt_version, model_identifier=draft.model_identifier, basis_refs=[material_id], rationale=draft.rationale, evidence_highlight=draft.evidence_highlight)
        return self._append(universe_id, command_id, "generate_evidence_candidate", {"round_id": round_id, "material_id": material_id}, {("evidence_candidate", candidate_id): expected_sequence}, PendingNativeEvent(event_type="evidence_relation_proposed", payload=p.model_dump(), aggregate_type="evidence_candidate", aggregate_id=candidate_id), {"candidate_id": candidate_id, "round_id": round_id, "aggregate_sequences": {"evidence_candidate": expected_sequence + 1}})

    def _challenge_state_or_raise(self, universe_id: str, challenge_id: str) -> dict:
        events = _events(self.store, universe_id)
        state = _challenge_states(events).get(challenge_id)
        if state is None: raise NotFound(challenge_id)
        if state["review_round_id"] in _round_verdicts(events):
            raise BoundaryViolation("challenge is resolved by its round verdict")
        if state["status"] in ("deferred", "withdrawn"):
            raise BoundaryViolation(f"challenge is already {state['status']}")
        return state

    def answer_challenge(self, universe_id: str, challenge_id: str, answer_text: str, provisional_anchor_refs: list[str], command_id: str, expected_sequence: int) -> CommitResult:
        state = self._challenge_state_or_raise(universe_id, challenge_id)
        answer_version_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:answer-version:{command_id}"))
        p = ChallengeAnsweredPayload(challenge_id=challenge_id, round_id=state["review_round_id"], claim_id=state["claim_id"], answer_version_id=answer_version_id, answer_text=answer_text, provisional_anchor_refs=provisional_anchor_refs)
        return self._append(universe_id, command_id, "answer_challenge", {"challenge_id": challenge_id, "answer_text": answer_text, "provisional_anchor_refs": provisional_anchor_refs}, {("challenge", challenge_id): expected_sequence}, PendingNativeEvent(event_type="challenge_answered", payload=p.model_dump(), aggregate_type="challenge", aggregate_id=challenge_id), {"challenge_id": challenge_id, "review_round_id": state["review_round_id"], "answer_version_id": answer_version_id, "aggregate_sequences": {"challenge": expected_sequence + 1}})

    def defer_challenge(self, universe_id: str, challenge_id: str, reason: str, condition: str, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._challenge_state_or_raise(universe_id, challenge_id)
        p = ChallengeDeferredPayload(challenge_id=challenge_id, round_id=state["review_round_id"], claim_id=state["claim_id"], reason=reason, condition=condition)
        return self._append(universe_id, command_id, "defer_challenge", {"challenge_id": challenge_id, "reason": reason, "condition": condition}, {("challenge", challenge_id): expected_sequence}, PendingNativeEvent(event_type="challenge_deferred", payload=p.model_dump(), aggregate_type="challenge", aggregate_id=challenge_id), {"challenge_id": challenge_id, "review_round_id": state["review_round_id"], "aggregate_sequences": {"challenge": expected_sequence + 1}})

    def withdraw_challenge(self, universe_id: str, challenge_id: str, reason: str, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._challenge_state_or_raise(universe_id, challenge_id)
        p = ChallengeWithdrawnPayload(challenge_id=challenge_id, round_id=state["review_round_id"], claim_id=state["claim_id"], reason=reason)
        return self._append(universe_id, command_id, "withdraw_challenge", {"challenge_id": challenge_id, "reason": reason}, {("challenge", challenge_id): expected_sequence}, PendingNativeEvent(event_type="challenge_withdrawn", payload=p.model_dump(), aggregate_type="challenge", aggregate_id=challenge_id), {"challenge_id": challenge_id, "review_round_id": state["review_round_id"], "aggregate_sequences": {"challenge": expected_sequence + 1}})

    def confirm_verdict(self, universe_id: str, round_id: str, verdict_type: str, user_reason: str, revival_condition: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        events = _events(self.store, universe_id)
        round_payload = next((e.validated_payload() for e in events if e.event_type == "review_round_started" and e.validated_payload().round_id == round_id), None)
        if round_payload is None: raise NotFound(round_id)
        if round_id in _round_verdicts(events): raise BoundaryViolation("review round already has an immutable verdict")
        p = VerdictConfirmedPayload(round_id=round_id, workspace_id=round_payload.workspace_id, claim_id=round_payload.claim_id, verdict_type=verdict_type, user_reason=user_reason, revival_condition=revival_condition)
        return self._append(universe_id, command_id, "confirm_verdict", {"round_id": round_id, "verdict_type": verdict_type, "user_reason": user_reason, "revival_condition": revival_condition}, {("review_round", round_id): expected_sequence}, PendingNativeEvent(event_type="verdict_confirmed", payload=p.model_dump(), aggregate_type="review_round", aggregate_id=round_id), {"review_round_id": round_id, "verdict_type": verdict_type, "aggregate_sequences": {"review_round": expected_sequence + 1}})

    # --- Slice 4: manual material / evidence gate --------------------------------

    def _contradiction_challenge(self, state: dict, challenge_id: str) -> ChallengeCreatedPayload:
        """Deterministic pending challenge for a confirmed contradiction.  NO LLM."""
        excerpt = state["material_anchor"]["excerpt"]
        claim_text = state["claim_snapshot"]["text"]
        return ChallengeCreatedPayload(
            challenge_id=challenge_id,
            round_id=state["round_id"],
            claim_id=state["claim_snapshot"]["id"],
            claim_version_id=state["claim_snapshot"]["version_id"],
            claim_text=claim_text,
            attack_surface=f"已确认反证：{excerpt}",
            why_it_matters=f"这段材料已被确认与 claim「{claim_text}」构成反证；审查必须正面处理它，不能绕过。",
            self_check_method="面对这段已确认反证，写下你的回应：它是否成立、是否被解释，或 claim 是否需要划界。",
            generator_kind="system",
            prompt_version="deterministic-evidence-contradiction-v1",
            model_identifier=None,
            basis_refs=[state["material_anchor"]["id"], state["id"]],
            uncertainty="已确认取证事实",
        )

    def _evidence_candidate_state(self, universe_id: str, candidate_id: str) -> dict:
        state = _evidence_candidate_states(_events(self.store, universe_id)).get(candidate_id)
        if state is None: raise NotFound(candidate_id)
        return state

    def _evidence_decision_targets(self, universe_id: str, command_id: str, state: dict, expected_sequence: int, *, with_challenge: bool) -> dict[tuple[str, str], int]:
        """Decision-command target streams.  A confirmed/corrected contradiction also
        creates a deterministic challenge in the SAME commit; reject/withdraw never do."""
        expected = {("evidence_candidate", state["id"]): expected_sequence}
        if with_challenge:
            challenge_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:challenge:{command_id}"))
            expected[("challenge", challenge_id)] = 0
        return expected

    def _require_pending(self, state: dict) -> None:
        if state["status"] != "pending":
            raise BoundaryViolation(f"evidence candidate is already {state['status']}; old decisions are never reopened")

    def add_material(self, universe_id: str, workspace_id: str, excerpt: str, source_locator: str | None, parse_status: str, purpose: str, command_id: str, expected_sequence: int) -> CommitResult:
        workspace_projection(self.store, universe_id, workspace_id)
        material_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:material:{command_id}"))
        p = MaterialAddedPayload(material_id=material_id, workspace_id=workspace_id, excerpt=excerpt, source_locator=source_locator, parse_status=parse_status, purpose=purpose)
        return self._append(universe_id, command_id, "add_material", {"workspace_id": workspace_id, "excerpt": excerpt, "source_locator": source_locator, "parse_status": parse_status, "purpose": purpose}, {("material", material_id): expected_sequence}, PendingNativeEvent(event_type="material_added", payload=p.model_dump(), aggregate_type="material", aggregate_id=material_id), {"material_id": material_id, "workspace_id": workspace_id, "aggregate_sequences": {"material": expected_sequence + 1}})

    def propose_evidence_candidate(self, universe_id: str, round_id: str, material_id: str, relation: str, uncertainty: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        events = _events(self.store, universe_id)
        round_payload = next((e.validated_payload() for e in events if e.event_type == "review_round_started" and e.validated_payload().round_id == round_id), None)
        if round_payload is None: raise NotFound(round_id)
        material_payload = next((e.validated_payload() for e in events if e.event_type == "material_added" and e.validated_payload().material_id == material_id), None)
        if material_payload is None: raise NotFound(material_id)
        if material_payload.workspace_id != round_payload.workspace_id: raise BoundaryViolation("material does not belong to the round's workspace")
        if material_payload.purpose != "evidence": raise BoundaryViolation("reference material never enters the evidence candidate flow")
        if relation == "silent" and material_payload.parse_status != "parsed": raise BoundaryViolation("parse failure can never masquerade as silent; use cannot_assess")
        candidate_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:evidence-candidate:{command_id}"))
        p = EvidenceRelationProposedPayload(candidate_id=candidate_id, round_id=round_id, workspace_id=round_payload.workspace_id, claim_id=round_payload.claim_id, claim_version_id=round_payload.claim_version_id, claim_text=round_payload.claim_text, material_id=material_payload.material_id, material_excerpt=material_payload.excerpt, material_source_locator=material_payload.source_locator, relation=relation, uncertainty=uncertainty)
        return self._append(universe_id, command_id, "propose_evidence_candidate", {"round_id": round_id, "material_id": material_id, "relation": relation, "uncertainty": uncertainty}, {("evidence_candidate", candidate_id): expected_sequence}, PendingNativeEvent(event_type="evidence_relation_proposed", payload=p.model_dump(), aggregate_type="evidence_candidate", aggregate_id=candidate_id), {"candidate_id": candidate_id, "round_id": round_id, "aggregate_sequences": {"evidence_candidate": expected_sequence + 1}})

    def confirm_evidence_candidate(self, universe_id: str, candidate_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._evidence_candidate_state(universe_id, candidate_id)
        command_payload = {"candidate_id": candidate_id, "user_reason": user_reason}
        expected = self._evidence_decision_targets(universe_id, command_id, state, expected_sequence, with_challenge=state["relation"] == "contradicts")
        prior = self.store.lookup_command(universe_id, command_id, command_fingerprint(universe_id, "confirm_evidence_candidate", command_payload, [(kind, ident, seq) for (kind, ident), seq in expected.items()]))
        if prior: return prior
        self._require_pending(state)
        p = EvidenceRelationConfirmedPayload(candidate_id=candidate_id, round_id=state["round_id"], claim_id=state["claim_snapshot"]["id"], relation=state["relation"], user_reason=user_reason)
        events = [PendingNativeEvent(event_type="evidence_relation_confirmed", payload=p.model_dump(), aggregate_type="evidence_candidate", aggregate_id=candidate_id)]
        result = {"candidate_id": candidate_id, "round_id": state["round_id"], "relation": state["relation"], "aggregate_sequences": {"evidence_candidate": expected_sequence + 1}}
        if state["relation"] == "contradicts":
            challenge_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:challenge:{command_id}"))
            challenge_payload = self._contradiction_challenge(state, challenge_id)
            events.append(PendingNativeEvent(event_type="challenge_created", payload=challenge_payload.model_dump(), aggregate_type="challenge", aggregate_id=challenge_id))
            result["challenge_id"] = challenge_id
            result["aggregate_sequences"]["challenge"] = 1
        return self._append_many(universe_id, command_id, "confirm_evidence_candidate", command_payload, expected, events, result)

    def correct_evidence_candidate(self, universe_id: str, candidate_id: str, corrected_relation: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._evidence_candidate_state(universe_id, candidate_id)
        command_payload = {"candidate_id": candidate_id, "corrected_relation": corrected_relation, "user_reason": user_reason}
        expected = self._evidence_decision_targets(universe_id, command_id, {**state, "relation": corrected_relation}, expected_sequence, with_challenge=corrected_relation == "contradicts")
        prior = self.store.lookup_command(universe_id, command_id, command_fingerprint(universe_id, "correct_evidence_candidate", command_payload, [(kind, ident, seq) for (kind, ident), seq in expected.items()]))
        if prior: return prior
        self._require_pending(state)
        if corrected_relation == state["relation"]: raise BoundaryViolation("correct must change the relation")
        p = EvidenceRelationCorrectedPayload(candidate_id=candidate_id, round_id=state["round_id"], claim_id=state["claim_snapshot"]["id"], prior_relation=state["relation"], corrected_relation=corrected_relation, user_reason=user_reason)
        events = [PendingNativeEvent(event_type="evidence_relation_corrected", payload=p.model_dump(), aggregate_type="evidence_candidate", aggregate_id=candidate_id)]
        result = {"candidate_id": candidate_id, "round_id": state["round_id"], "relation": corrected_relation, "aggregate_sequences": {"evidence_candidate": expected_sequence + 1}}
        if corrected_relation == "contradicts":
            challenge_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:challenge:{command_id}"))
            challenge_payload = self._contradiction_challenge({**state, "relation": corrected_relation}, challenge_id)
            events.append(PendingNativeEvent(event_type="challenge_created", payload=challenge_payload.model_dump(), aggregate_type="challenge", aggregate_id=challenge_id))
            result["challenge_id"] = challenge_id
            result["aggregate_sequences"]["challenge"] = 1
        return self._append_many(universe_id, command_id, "correct_evidence_candidate", command_payload, expected, events, result)

    def reject_evidence_candidate(self, universe_id: str, candidate_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._evidence_candidate_state(universe_id, candidate_id)
        command_payload = {"candidate_id": candidate_id, "user_reason": user_reason}
        expected = self._evidence_decision_targets(universe_id, command_id, state, expected_sequence, with_challenge=False)
        prior = self.store.lookup_command(universe_id, command_id, command_fingerprint(universe_id, "reject_evidence_candidate", command_payload, [(kind, ident, seq) for (kind, ident), seq in expected.items()]))
        if prior: return prior
        self._require_pending(state)
        p = EvidenceRelationRejectedPayload(candidate_id=candidate_id, round_id=state["round_id"], claim_id=state["claim_snapshot"]["id"], user_reason=user_reason)
        return self._append_many(universe_id, command_id, "reject_evidence_candidate", command_payload, expected, [PendingNativeEvent(event_type="evidence_relation_rejected", payload=p.model_dump(), aggregate_type="evidence_candidate", aggregate_id=candidate_id)], {"candidate_id": candidate_id, "round_id": state["round_id"], "aggregate_sequences": {"evidence_candidate": expected_sequence + 1}})

    def withdraw_evidence_candidate(self, universe_id: str, candidate_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._evidence_candidate_state(universe_id, candidate_id)
        command_payload = {"candidate_id": candidate_id, "user_reason": user_reason}
        expected = self._evidence_decision_targets(universe_id, command_id, state, expected_sequence, with_challenge=False)
        prior = self.store.lookup_command(universe_id, command_id, command_fingerprint(universe_id, "withdraw_evidence_candidate", command_payload, [(kind, ident, seq) for (kind, ident), seq in expected.items()]))
        if prior: return prior
        self._require_pending(state)
        p = EvidenceRelationWithdrawnPayload(candidate_id=candidate_id, round_id=state["round_id"], claim_id=state["claim_snapshot"]["id"], user_reason=user_reason)
        return self._append_many(universe_id, command_id, "withdraw_evidence_candidate", command_payload, expected, [PendingNativeEvent(event_type="evidence_relation_withdrawn", payload=p.model_dump(), aggregate_type="evidence_candidate", aggregate_id=candidate_id)], {"candidate_id": candidate_id, "round_id": state["round_id"], "aggregate_sequences": {"evidence_candidate": expected_sequence + 1}})

    # --- Slice 5: workspace crystallization / direction impact ----------------

    def _assert_position_transition(self, universe_id: str, workspace_id: str, action: str) -> None:
        workspace_projection(self.store, universe_id, workspace_id)
        position = _workspace_position(_events(self.store, universe_id), workspace_id)
        if position not in _ALLOWED_POSITION_TRANSITIONS[action]:
            raise BoundaryViolation(f"cannot {action} a workspace in position {position}")

    # --- slice1 S1.2: gap candidates (workspace-scoped, S20) -----------------

    def _gap_candidate_state(self, universe_id: str, candidate_id: str) -> dict:
        state = _gap_candidate_states(_events(self.store, universe_id)).get(candidate_id)
        if state is None:
            raise NotFound(candidate_id)
        return state

    def propose_gap_candidate(self, universe_id: str, workspace_id: str, coverage_statement: str, search_query: str, search_scope: str, matched_locators: list[str], counterexample_invitation: str, searched_at: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        workspace_projection(self.store, universe_id, workspace_id)
        candidate_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:gap-candidate:{command_id}"))
        p = GapCandidateProposedPayload(gap_candidate_id=candidate_id, workspace_id=workspace_id, coverage_statement=coverage_statement, search_query=search_query, search_scope=search_scope, matched_locators=matched_locators, searched_at=searched_at, counterexample_invitation=counterexample_invitation)
        command_payload = {"workspace_id": workspace_id, "coverage_statement": coverage_statement, "search_query": search_query, "search_scope": search_scope, "matched_locators": matched_locators, "counterexample_invitation": counterexample_invitation}
        return self._append(universe_id, command_id, "propose_gap_candidate", command_payload, {("gap_candidate", candidate_id): expected_sequence}, PendingNativeEvent(event_type="gap_candidate_proposed", payload=p.model_dump(), aggregate_type="gap_candidate", aggregate_id=candidate_id), {"gap_candidate_id": candidate_id, "aggregate_sequences": {"gap_candidate": expected_sequence + 1}})

    def confirm_gap_candidate(self, universe_id: str, candidate_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._gap_candidate_state(universe_id, candidate_id)
        command_payload = {"candidate_id": candidate_id, "user_reason": user_reason}
        expected = {("gap_candidate", state["id"]): expected_sequence}
        prior = self.store.lookup_command(universe_id, command_id, command_fingerprint(universe_id, "confirm_gap_candidate", command_payload, [(kind, ident, seq) for (kind, ident), seq in expected.items()]))
        if prior:
            return prior
        if state["status"] != "pending":
            raise BoundaryViolation(f"gap candidate is already {state['status']}; old decisions are never reopened")
        p = GapCandidateConfirmedPayload(gap_candidate_id=candidate_id, workspace_id=state["workspace_id"], user_reason=user_reason)
        return self._append(universe_id, command_id, "confirm_gap_candidate", command_payload, expected, PendingNativeEvent(event_type="gap_candidate_confirmed", payload=p.model_dump(), aggregate_type="gap_candidate", aggregate_id=candidate_id), {"gap_candidate_id": candidate_id, "aggregate_sequences": {"gap_candidate": expected_sequence + 1}})

    def correct_gap_candidate(self, universe_id: str, candidate_id: str, corrected_coverage_statement: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._gap_candidate_state(universe_id, candidate_id)
        command_payload = {"candidate_id": candidate_id, "corrected_coverage_statement": corrected_coverage_statement, "user_reason": user_reason}
        expected = {("gap_candidate", state["id"]): expected_sequence}
        prior = self.store.lookup_command(universe_id, command_id, command_fingerprint(universe_id, "correct_gap_candidate", command_payload, [(kind, ident, seq) for (kind, ident), seq in expected.items()]))
        if prior:
            return prior
        if state["status"] != "pending":
            raise BoundaryViolation(f"gap candidate is already {state['status']}; old decisions are never reopened")
        p = GapCandidateCorrectedPayload(gap_candidate_id=candidate_id, workspace_id=state["workspace_id"], corrected_coverage_statement=corrected_coverage_statement, user_reason=user_reason)
        return self._append(universe_id, command_id, "correct_gap_candidate", command_payload, expected, PendingNativeEvent(event_type="gap_candidate_corrected", payload=p.model_dump(), aggregate_type="gap_candidate", aggregate_id=candidate_id), {"gap_candidate_id": candidate_id, "aggregate_sequences": {"gap_candidate": expected_sequence + 1}})

    def reject_gap_candidate(self, universe_id: str, candidate_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._gap_candidate_state(universe_id, candidate_id)
        command_payload = {"candidate_id": candidate_id, "user_reason": user_reason}
        expected = {("gap_candidate", state["id"]): expected_sequence}
        prior = self.store.lookup_command(universe_id, command_id, command_fingerprint(universe_id, "reject_gap_candidate", command_payload, [(kind, ident, seq) for (kind, ident), seq in expected.items()]))
        if prior:
            return prior
        if state["status"] != "pending":
            raise BoundaryViolation(f"gap candidate is already {state['status']}; old decisions are never reopened")
        p = GapCandidateRejectedPayload(gap_candidate_id=candidate_id, workspace_id=state["workspace_id"], user_reason=user_reason)
        return self._append(universe_id, command_id, "reject_gap_candidate", command_payload, expected, PendingNativeEvent(event_type="gap_candidate_rejected", payload=p.model_dump(), aggregate_type="gap_candidate", aggregate_id=candidate_id), {"gap_candidate_id": candidate_id, "aggregate_sequences": {"gap_candidate": expected_sequence + 1}})

    def withdraw_gap_candidate(self, universe_id: str, candidate_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        state = self._gap_candidate_state(universe_id, candidate_id)
        command_payload = {"candidate_id": candidate_id, "user_reason": user_reason}
        expected = {("gap_candidate", state["id"]): expected_sequence}
        prior = self.store.lookup_command(universe_id, command_id, command_fingerprint(universe_id, "withdraw_gap_candidate", command_payload, [(kind, ident, seq) for (kind, ident), seq in expected.items()]))
        if prior:
            return prior
        if state["status"] != "pending":
            raise BoundaryViolation(f"gap candidate is already {state['status']}; old decisions are never reopened")
        p = GapCandidateWithdrawnPayload(gap_candidate_id=candidate_id, workspace_id=state["workspace_id"], user_reason=user_reason)
        return self._append(universe_id, command_id, "withdraw_gap_candidate", command_payload, expected, PendingNativeEvent(event_type="gap_candidate_withdrawn", payload=p.model_dump(), aggregate_type="gap_candidate", aggregate_id=candidate_id), {"gap_candidate_id": candidate_id, "aggregate_sequences": {"gap_candidate": expected_sequence + 1}})

    def pause_workspace(self, universe_id: str, workspace_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        self._assert_position_transition(universe_id, workspace_id, "pause")
        p = WorkspacePausedPayload(workspace_id=workspace_id, user_reason=user_reason)
        return self._append(universe_id, command_id, "pause_workspace", {"workspace_id": workspace_id, "user_reason": user_reason}, {("workspace", workspace_id): expected_sequence}, PendingNativeEvent(event_type="workspace_paused", payload=p.model_dump(), aggregate_type="workspace", aggregate_id=workspace_id), {"workspace_id": workspace_id, "aggregate_sequences": {"workspace": expected_sequence + 1}})

    def reopen_workspace(self, universe_id: str, workspace_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        self._assert_position_transition(universe_id, workspace_id, "reopen")
        p = WorkspaceReopenedPayload(workspace_id=workspace_id, user_reason=user_reason)
        return self._append(universe_id, command_id, "reopen_workspace", {"workspace_id": workspace_id, "user_reason": user_reason}, {("workspace", workspace_id): expected_sequence}, PendingNativeEvent(event_type="workspace_reopened", payload=p.model_dump(), aggregate_type="workspace", aggregate_id=workspace_id), {"workspace_id": workspace_id, "aggregate_sequences": {"workspace": expected_sequence + 1}})

    def conclude_workspace(self, universe_id: str, workspace_id: str, conclusion_type: str, conclusion_text: str, user_reason: str | None, basis_refs: list[str], revival_condition: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        self._assert_position_transition(universe_id, workspace_id, "conclude")
        conclusion_id = str(uuid5(NAMESPACE_URL, f"{universe_id}:conclusion:{command_id}"))
        p = WorkspaceConcludedPayload(workspace_id=workspace_id, conclusion_id=conclusion_id, conclusion_type=conclusion_type, conclusion_text=conclusion_text, user_reason=user_reason, basis_refs=basis_refs, revival_condition=revival_condition)  # type: ignore[arg-type]
        return self._append(universe_id, command_id, "conclude_workspace", {"workspace_id": workspace_id, "conclusion_type": conclusion_type, "conclusion_text": conclusion_text, "user_reason": user_reason, "basis_refs": basis_refs, "revival_condition": revival_condition}, {("workspace", workspace_id): expected_sequence}, PendingNativeEvent(event_type="workspace_concluded", payload=p.model_dump(), aggregate_type="workspace", aggregate_id=workspace_id), {"workspace_id": workspace_id, "conclusion_id": conclusion_id, "aggregate_sequences": {"workspace": expected_sequence + 1}})

    def branch_workspace(self, universe_id: str, workspace_id: str, new_question: str, user_reason: str, command_id: str, expected_sequence: int) -> CommitResult:
        """Atomically create the successor workspace AND record the branch in one commit."""
        self._assert_position_transition(universe_id, workspace_id, "branch")
        successor_id, qid = self._id(command_id, "workspace"), self._id(command_id, "question")
        wp = WorkspaceCreatedPayload(workspace_id=successor_id, initial_question_version_id=qid, initial_question_text=new_question)
        bp = WorkspaceBranchedPayload(workspace_id=workspace_id, successor_workspace_id=successor_id, user_reason=user_reason)
        expected = {("workspace", workspace_id): expected_sequence, ("workspace", successor_id): 0}
        events = [PendingNativeEvent(event_type="workspace_created", payload=wp.model_dump(), aggregate_type="workspace", aggregate_id=successor_id), PendingNativeEvent(event_type="workspace_branched", payload=bp.model_dump(), aggregate_type="workspace", aggregate_id=workspace_id)]
        return self._append_many(universe_id, command_id, "branch_workspace", {"workspace_id": workspace_id, "new_question": new_question, "user_reason": user_reason}, expected, events, {"workspace_id": workspace_id, "successor_workspace_id": successor_id, "aggregate_sequences": {"workspace": expected_sequence + 1, "successor": 1}})

    def absorb_workspace(self, universe_id: str, workspace_id: str, target_workspace_id: str, user_reason: str, command_id: str, expected_sequence: int) -> CommitResult:
        self._assert_position_transition(universe_id, workspace_id, "absorb")
        if target_workspace_id == workspace_id:
            raise BoundaryViolation("absorb target must be a different workspace")
        workspace_projection(self.store, universe_id, target_workspace_id)
        p = WorkspaceAbsorbedPayload(workspace_id=workspace_id, target_workspace_id=target_workspace_id, user_reason=user_reason)
        return self._append(universe_id, command_id, "absorb_workspace", {"workspace_id": workspace_id, "target_workspace_id": target_workspace_id, "user_reason": user_reason}, {("workspace", workspace_id): expected_sequence}, PendingNativeEvent(event_type="workspace_absorbed", payload=p.model_dump(), aggregate_type="workspace", aggregate_id=workspace_id), {"workspace_id": workspace_id, "target_workspace_id": target_workspace_id, "aggregate_sequences": {"workspace": expected_sequence + 1}})

    def create_direction(self, universe_id: str, proposition: str, command_id: str, expected_sequence: int) -> CommitResult:
        direction_id, vid = self._id(command_id, "direction"), self._id(command_id, "direction-proposition")
        p = DirectionCreatedPayload(direction_id=direction_id, proposition_version_id=vid, proposition_text=proposition)
        return self._append(universe_id, command_id, "create_direction", {"proposition": proposition}, {("direction", direction_id): expected_sequence}, PendingNativeEvent(event_type="direction_created", payload=p.model_dump(), aggregate_type="direction", aggregate_id=direction_id), {"direction_id": direction_id, "proposition_version_id": vid, "aggregate_sequences": {"direction": expected_sequence + 1}})

    def declare_direction_status(self, universe_id: str, direction_id: str, status: str, user_reason: str, command_id: str, expected_sequence: int) -> CommitResult:
        direction_projection(self.store, universe_id, direction_id)
        p = DirectionStatusDeclaredPayload(direction_id=direction_id, status=status, user_reason=user_reason)  # type: ignore[arg-type]
        return self._append(universe_id, command_id, "declare_direction_status", {"direction_id": direction_id, "status": status, "user_reason": user_reason}, {("direction", direction_id): expected_sequence}, PendingNativeEvent(event_type="direction_status_declared", payload=p.model_dump(), aggregate_type="direction", aggregate_id=direction_id), {"direction_id": direction_id, "status": status, "aggregate_sequences": {"direction": expected_sequence + 1}})

    def rephrase_direction(self, universe_id: str, direction_id: str, new_proposition: str | None, change_type: str, user_reason: str, source_conclusion_ref: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        current = direction_projection(self.store, universe_id, direction_id)
        new_vid = self._id(command_id, "direction-proposition")
        p = DirectionPropositionRephrasedPayload(direction_id=direction_id, prior_proposition_version_id=current["proposition"]["version_id"], prior_proposition_text=current["proposition"]["text"] or "", new_proposition_version_id=new_vid, new_proposition_text=new_proposition, change_type=change_type, user_reason=user_reason, source_conclusion_ref=source_conclusion_ref)  # type: ignore[arg-type]
        return self._append(universe_id, command_id, "rephrase_direction", {"direction_id": direction_id, "new_proposition": new_proposition, "change_type": change_type, "user_reason": user_reason, "source_conclusion_ref": source_conclusion_ref}, {("direction", direction_id): expected_sequence}, PendingNativeEvent(event_type="direction_proposition_rephrased", payload=p.model_dump(), aggregate_type="direction", aggregate_id=direction_id), {"direction_id": direction_id, "new_proposition_version_id": new_vid, "aggregate_sequences": {"direction": expected_sequence + 1}})

    def attach_direction(self, universe_id: str, workspace_id: str, direction_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        workspace_projection(self.store, universe_id, workspace_id)
        direction_projection(self.store, universe_id, direction_id)
        link_id = self._id(command_id, "direction-link")
        p = WorkspaceDirectionAttachedPayload(direction_link_id=link_id, workspace_id=workspace_id, direction_id=direction_id, user_reason=user_reason)
        return self._append(universe_id, command_id, "attach_direction", {"workspace_id": workspace_id, "direction_id": direction_id, "user_reason": user_reason}, {("workspace_direction_link", link_id): expected_sequence}, PendingNativeEvent(event_type="workspace_direction_attached", payload=p.model_dump(), aggregate_type="workspace_direction_link", aggregate_id=link_id), {"direction_link_id": link_id, "workspace_id": workspace_id, "direction_id": direction_id, "aggregate_sequences": {"workspace_direction_link": expected_sequence + 1}})

    def detach_direction_link(self, universe_id: str, link_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        events = _events(self.store, universe_id)
        attached = next((e.validated_payload() for e in events if e.event_type == "workspace_direction_attached" and e.validated_payload().direction_link_id == link_id), None)
        if attached is None:
            raise NotFound(link_id)
        if any(e.event_type == "workspace_direction_detached" and e.validated_payload().direction_link_id == link_id for e in events):
            raise BoundaryViolation("direction link is already detached")
        p = WorkspaceDirectionDetachedPayload(direction_link_id=link_id, workspace_id=attached.workspace_id, direction_id=attached.direction_id, user_reason=user_reason)
        return self._append(universe_id, command_id, "detach_direction_link", {"direction_link_id": link_id, "user_reason": user_reason}, {("workspace_direction_link", link_id): expected_sequence}, PendingNativeEvent(event_type="workspace_direction_detached", payload=p.model_dump(), aggregate_type="workspace_direction_link", aggregate_id=link_id), {"direction_link_id": link_id, "workspace_id": attached.workspace_id, "direction_id": attached.direction_id, "aggregate_sequences": {"workspace_direction_link": expected_sequence + 1}})

    def attach_crystallization(self, universe_id: str, direction_id: str, workspace_id: str, conclusion_id: str, user_reason: str | None, command_id: str, expected_sequence: int) -> CommitResult:
        ws = workspace_projection(self.store, universe_id, workspace_id)
        direction_projection(self.store, universe_id, direction_id)
        if ws.get("conclusion") is None or ws["conclusion"]["id"] != conclusion_id:
            raise BoundaryViolation("workspace has no such conclusion")
        conclusion = ws["conclusion"]
        crystallization_id = self._id(command_id, "crystallization")
        p = WorkspaceCrystallizationAttachedPayload(crystallization_id=crystallization_id, direction_id=direction_id, workspace_id=workspace_id, conclusion_id=conclusion_id, conclusion_text=conclusion["text"], conclusion_type=conclusion["type"], user_reason=user_reason)  # type: ignore[arg-type]
        return self._append(universe_id, command_id, "attach_crystallization", {"direction_id": direction_id, "workspace_id": workspace_id, "conclusion_id": conclusion_id, "user_reason": user_reason}, {("workspace_crystallization", crystallization_id): expected_sequence}, PendingNativeEvent(event_type="workspace_crystallization_attached", payload=p.model_dump(), aggregate_type="workspace_crystallization", aggregate_id=crystallization_id), {"crystallization_id": crystallization_id, "direction_id": direction_id, "workspace_id": workspace_id, "aggregate_sequences": {"workspace_crystallization": expected_sequence + 1}})
