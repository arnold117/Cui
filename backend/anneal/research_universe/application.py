"""Slice 1 semantic commands, narrow challenge port, and pure event projections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4, uuid5, NAMESPACE_URL

from anneal.research_universe.domain.events import (
    ChallengeAnsweredPayload, ChallengeCreatedPayload, ChallengeDeferredPayload,
    ChallengeWithdrawnPayload, ClaimCreatedPayload, ClaimForgedFromCapturePayload,
    ExplorationAnchorCreatedPayload, ExplorationNoteSavedPayload,
    ParkReleasedPayload, PendingNativeEvent, ReviewRoundStartedPayload,
    VerdictConfirmedPayload, WorkspaceCreatedPayload,
)
from anneal.research_universe.store.event_store import CommitResult, NativeEventStore, command_fingerprint
from anneal.research_universe.command_guard import CommandExecutionGuard


@dataclass(frozen=True)
class ChallengeDraft:
    attack_surface: str
    why_it_matters: str
    self_check_method: str
    prompt_version: str
    model_identifier: str | None
    basis_refs: list[str]
    uncertainty: str


class ChallengeGenerator(Protocol):
    def generate(self, *, question: str, claim: str) -> ChallengeDraft: ...


class ChallengeGenerationFailed(Exception): pass
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


def workspace_projection(store: NativeEventStore, universe_id: str, workspace_id: str) -> dict:
    workspace = None; note_revisions = []; anchors = []; claims = []; rounds = []; park_release_refs = []; forged = []
    workspace_sequence = 0
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
    if workspace is None: raise NotFound(workspace_id)
    latest_note = note_revisions[-1] if note_revisions else None
    challenge_states = _challenge_states(events)
    workspace_round_ids = {r["id"] for r in rounds}
    workspace_challenges = [challenge_states[cid] for cid in challenge_states if challenge_states[cid]["review_round_id"] in workspace_round_ids]
    workspace.update(
        sequence=workspace_sequence,
        note=latest_note,
        note_revisions=note_revisions,
        anchors=anchors,
        claims=claims,
        park_release_refs=park_release_refs,
        claim_forge_provenance=forged,
        review_rounds=rounds,
        pending_challenges=[x for x in workspace_challenges if x["status"] in ("pending", "answered")],
    )
    return workspace


def review_round_projection(store: NativeEventStore, universe_id: str, round_id: str) -> dict:
    events = _events(store, universe_id)
    for event in events:
        if event.event_type == "review_round_started" and event.validated_payload().round_id == round_id:
            p = event.validated_payload()
            challenge_states = _challenge_states(events)
            challenges = [challenge_states[cid] for cid in challenge_states if challenge_states[cid]["review_round_id"] == round_id]
            rounds = [{"id": rp.round_id, "claim_id": rp.claim_id, "question_snapshot": {"version_id": rp.question_version_id, "text": rp.question_text}, "claim_snapshot": {"id": rp.claim_id, "version_id": rp.claim_version_id, "text": rp.claim_text}, "verdict": _round_verdicts(events).get(rp.round_id)} for e in events if e.event_type == "review_round_started" and (rp := e.validated_payload()).claim_id == p.claim_id]
            return {"id": p.round_id, "workspace_id": p.workspace_id, "question_snapshot": {"version_id": p.question_version_id, "text": p.question_text}, "claim_snapshot": {"id": p.claim_id, "version_id": p.claim_version_id, "text": p.claim_text}, "verdict": _round_verdicts(events).get(round_id), "sequence": _round_next_sequence(events, round_id), "challenges": challenges, "ledger": _ledger(challenges), "rounds": rounds}
    raise NotFound(round_id)


def universe_home_projection(store: NativeEventStore, universe_id: str) -> dict:
    workspaces = []
    for event in _events(store, universe_id):
        if event.event_type == "workspace_created":
            workspaces.append(workspace_projection(store, universe_id, event.validated_payload().workspace_id))
    pending = [{**c, "workspace_id": w["id"], "question": w["question"]["text"]} for w in workspaces for c in w["pending_challenges"]]
    return {"universe_id": universe_id, "workspaces": workspaces, "pending_facts": pending}



def park_release_refs(store: NativeEventStore, universe_id: str, capture_id: str) -> list[dict]:
    return [{"universe_id": universe_id, "id": p.release_id, "capture_id": p.capture_id, "workspace_id": p.workspace_id, "provisional_role": p.provisional_role} for e in _events(store, universe_id) if e.event_type == "park_released" and (p := e.validated_payload()).capture_id == capture_id]


class Slice1Service:
    def __init__(self, store: NativeEventStore, actor_id: str | None, generator: ChallengeGenerator, guard: CommandExecutionGuard | None = None) -> None:
        self.store, self.actor_id, self.generator, self.guard = store, actor_id, generator, guard

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
