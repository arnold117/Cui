"""L3 Lens canary — 已知样本哨兵挑战测试 (known-sample sentinel challenge).

WHY THIS EXISTS
---------------
All three L3 detectors are cold-start-silent by design (no material → no
output). That means a BROKEN detector (bad prompt edit, model swap, prefilter
regression) looks EXACTLY like a healthy detector that simply has nothing to
say. A sentinel that has never fired and a sentinel that is dead are
indistinguishable from the outside. This script feeds each detector known
samples and verifies that what should scream screams and what should stay
silent stays silent.

TRIGGER DISCIPLINE — RUN THIS AFTER ANY OF:
  * any edit to anneal/llm/prompts.py (contradiction / taste / semantic-edges
    prompts);
  * an LLM model / provider swap (ANNEAL_LLM_MODEL / _PROVIDER / _BASE_URL);
  * any change to anneal/lens/prefilter.py or anneal/lens/topic_terms.py;
  * before every release.

WHAT IT COSTS / TOUCHES
-----------------------
Uses the REAL configured LLM (backend/.env → ANNEAL_LLM_*; DeepSeek in the
default setup) — roughly 7 chat calls per clean run (a couple more on retries)
plus one OpenAlex search. Storage is a per-case, throwaway
InMemoryEventStore/InMemoryRepository — NO product database or data file is
read or written. This is exactly why it is NOT part of the default pytest run
(costs money, walks the network): run it explicitly.

USAGE
-----
    conda activate anneal
    cd backend && python scripts/canary_l3.py

CASES (each detector gets a "must fire" and a "must stay silent" end)
---------------------------------------------------------------------
  C1-fire    ② contradiction: survived past claim + frontally contradicting
             new claim → ≥1 pending CHALLENGE (kind="lens_contradiction").
  C1-silent  ② contradiction: same topic, compatible claims → 0 events.
  C2-fire    ① taste anchor: grilled history + blatantly incremental new
             claim → exactly 1 CHALLENGE (kind="taste") with a valid rubric
             tier, anchored to REAL seeded past claims (no hallucinated ids).
  C2-silent  ① taste anchor: empty library (cold start) → silent, no LLM call.
  C3-fire    ③ semantic edges: obvious method-reuse pair → ≥1 LINK event with
             a legal edge type between the two seeded claims.
  C3-silent  ③ semantic edges: lexically-overlapping but semantically
             unrelated pair (passes the prefilter, so the LLM's restraint is
             actually exercised) → 0 LINK events.

FAILURE POLICY (LLM variance)
-----------------------------
A failing case is re-run ONCE with fresh state. Pass on retry → FLAKY
(reported separately, does not fail the run). Fail twice → FAIL, and the
process exits non-zero. Exit codes: 0 = all PASS/FLAKY, 1 = ≥1 FAIL,
2 = setup error (missing LLM config etc.).

The samples are deliberately blunt: this is a binary alarm, not a sensitivity
instrument. If a case here flaps, the detector (or its prompt/prefilter/model)
has moved enough to be worth a human look.
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

# --- Import bootstrap -------------------------------------------------------
# Force THIS tree's `anneal` package to the front of sys.path. The conda env
# carries an editable install that may point at another checkout; a canary
# must test the code it sits next to.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

import anneal  # noqa: E402
from anneal.domain.events import CHALLENGE, PARK, VERDICT, make_event  # noqa: E402
from anneal.domain.models import Artifact, Claim  # noqa: E402
from anneal.lens.prefilter import prefilter_candidates  # noqa: E402
from anneal.llm.client import create_client  # noqa: E402
from anneal.llm.config import load_llm_config  # noqa: E402
from anneal.services.event_service import EventService  # noqa: E402
from anneal.services.lens_service import (  # noqa: E402
    _SEMANTIC_EDGE_TYPES,
    _TASTE_TIERS,
    LensService,
)
from anneal.store.event_store import InMemoryEventStore  # noqa: E402
from anneal.store.repository import InMemoryRepository  # noqa: E402

LIB = "canary-lib"


# ---------------------------------------------------------------------------
# World construction (fresh, throwaway, in-memory — per case, per attempt)
# ---------------------------------------------------------------------------


@dataclass
class World:
    store: InMemoryEventStore
    event_svc: EventService
    repo: InMemoryRepository
    lens: LensService


def build_world(llm) -> World:
    store = InMemoryEventStore()
    event_svc = EventService(store)
    repo = InMemoryRepository()
    lens = LensService(store, event_svc, repo=repo, llm=llm)
    return World(store, event_svc, repo, lens)


def seed_grilled(
    w: World, *, claim_id: str, artifact_id: str, body: str, outcome: str,
    rationale: str = "canary seed",
    death_cause: str | None = None,
    revival_condition: str | None = None,
) -> Claim:
    """Seed a fully-grilled claim (park → challenge → confirmed verdict).

    Mirrors the realistic event recipe used by the unit tests so that
    ``claim_status`` genuinely resolves to survived/killed. Killed seeds
    should carry a ``death_cause`` so the precedent-injection path (判例
    四元组 → ②① prompts) is exercised by the sentinel rather than the
    legacy "unclassified" rendering; survived seeds carry none by design.
    """
    assert outcome in ("survived", "killed")
    w.repo.create_artifact(
        Artifact(id=artifact_id, library_id=LIB, kind="idea", goal="canary")
    )
    claim = Claim(id=claim_id, library_id=LIB, body=body, artifact_ids=[artifact_id])
    w.repo.create_claim(claim)

    w.store.append(
        artifact_id,
        make_event(
            type=PARK, actor="user", confirmed=True,
            target_ref=claim_id, payload={"kind": "idea"},
        ),
    )
    w.store.append(
        artifact_id,
        make_event(
            type=CHALLENGE, actor="system", confirmed=True,
            target_ref=claim_id, payload={"question": "canary grill"},
        ),
    )
    payload: dict = {
        "outcome": "survive" if outcome == "survived" else "kill",
        "rationale": rationale,
    }
    if death_cause is not None:
        payload["death_cause"] = death_cause
    if revival_condition is not None:
        payload["revival_condition"] = revival_condition
    verdict = make_event(
        type=VERDICT, actor="system", confirmed=False, target_ref=claim_id,
        payload=payload,
    )
    w.event_svc.append_event(artifact_id, verdict)
    w.event_svc.confirm_event(artifact_id, verdict.id)
    return claim


def register_current(w: World, *, artifact_id: str, claim_id: str, body: str) -> None:
    """Register the current (mid-grill) artifact + claim."""
    w.repo.create_artifact(
        Artifact(id=artifact_id, library_id=LIB, kind="idea", goal="canary")
    )
    w.repo.create_claim(
        Claim(id=claim_id, library_id=LIB, body=body, artifact_ids=[artifact_id])
    )


def check_prefilter_reaches_llm(w: World, current_body: str, past: Claim) -> str | None:
    """Precondition: the control sample must survive the lexical prefilter.

    A silent-end case only exercises the LLM's restraint if the candidate
    actually reaches the LLM. If the prefilter drops it, the case would pass
    vacuously — report that as a failure (prefilter regression OR stale
    canary sample; either way a human must look).
    """
    shortlist = prefilter_candidates(current_body, [past])
    if not shortlist:
        return (
            "PRECONDITION BROKEN: lexical prefilter no longer shortlists the "
            "canary candidate — the LLM was never consulted. Either the "
            "prefilter regressed or the canary sample needs re-tuning."
        )
    return None


# ---------------------------------------------------------------------------
# Cases — each returns (ok, expected, actual, detail)
# ---------------------------------------------------------------------------


@dataclass
class CaseOutcome:
    ok: bool
    expected: str
    actual: str
    detail: str = ""


def case_contradiction_fire(llm) -> CaseOutcome:
    """② Survived past claim + frontal contradiction → must scream."""
    w = build_world(llm)
    past = seed_grilled(
        w, claim_id="c1-past", artifact_id="c1-art-past",
        body=(
            "Daily caffeine intake improves short-term memory recall "
            "in healthy adults."
        ),
        outcome="survived",
        rationale="Defended with replicated caffeine–recall RCT evidence.",
    )
    current_body = (
        "Daily caffeine intake impairs short-term memory recall "
        "in healthy adults."
    )
    register_current(w, artifact_id="c1-art-cur", claim_id="c1-cur", body=current_body)

    events = w.lens.scan_contradictions("c1-art-cur", "c1-cur", current_body)

    expected = ">=1 lens_contradiction CHALLENGE anchored to seeded past claim"
    hits = [
        e for e in events
        if e.type == CHALLENGE
        and e.payload.get("kind") == "lens_contradiction"
        and e.payload.get("past_claim_id") == past.id
    ]
    if not hits:
        return CaseOutcome(
            False, expected, f"{len(events)} events, no matching hit",
            detail=f"events={[e.payload for e in events]}",
        )
    bad = [e for e in hits if e.confirmed or e.actor != "system"]
    if bad:
        return CaseOutcome(
            False, expected, "hit exists but not a pending system challenge",
            detail=f"confirmed/actor wrong on {[e.id for e in bad]}",
        )
    return CaseOutcome(
        True, expected,
        f"{len(hits)} hit(s), tension_type={hits[0].payload.get('tension_type')!r}",
    )


def case_contradiction_silent(llm) -> CaseOutcome:
    """② Same topic, fully compatible claims → must stay silent."""
    w = build_world(llm)
    past = seed_grilled(
        w, claim_id="c1s-past", artifact_id="c1s-art-past",
        body=(
            "Daily caffeine intake improves short-term memory recall "
            "in healthy adults."
        ),
        outcome="survived",
        rationale="Defended with replicated caffeine–recall RCT evidence.",
    )
    current_body = (
        "Daily caffeine intake increases resting heart rate "
        "in healthy adults."
    )
    register_current(w, artifact_id="c1s-art-cur", claim_id="c1s-cur", body=current_body)

    expected = "0 events (compatible claims, zero false positives)"
    precondition_err = check_prefilter_reaches_llm(w, current_body, past)
    if precondition_err:
        return CaseOutcome(False, expected, "candidate never reached LLM",
                           detail=precondition_err)

    events = w.lens.scan_contradictions("c1s-art-cur", "c1s-cur", current_body)
    if events:
        return CaseOutcome(
            False, expected, f"{len(events)} event(s) — FALSE POSITIVE",
            detail=f"payloads={[e.payload for e in events]}",
        )
    return CaseOutcome(True, expected, "0 events")


def case_taste_fire(llm) -> CaseOutcome:
    """① Grilled history + blatantly incremental claim → taste verdict,
    anchored to real seeded past claims only."""
    w = build_world(llm)
    survived = seed_grilled(
        w, claim_id="c2-past-survived", artifact_id="c2-art-s",
        body=(
            "Spaced repetition scheduling improves long-term retention of "
            "foreign vocabulary in second-language learners."
        ),
        outcome="survived",
        rationale="Defended: the spacing effect replicated in my own vocab pilots.",
    )
    killed = seed_grilled(
        w, claim_id="c2-past-killed", artifact_id="c2-art-k",
        body=(
            "Cramming all vocabulary practice into one massed session improves "
            "long-term retention for second-language learners."
        ),
        outcome="killed",
        death_cause="refuted",
        rationale=(
            "Killed: massed practice lost to spacing at every delayed test — "
            "factually wrong."
        ),
    )
    current_body = (
        "Spaced repetition scheduling improves long-term retention of foreign "
        "vocabulary in third-language learners."
    )
    register_current(w, artifact_id="c2-art-cur", claim_id="c2-cur", body=current_body)

    events = asyncio.run(w.lens.assess_taste("c2-art-cur", "c2-cur", current_body))

    expected = (
        "exactly 1 taste CHALLENGE, tier in rubric, >=1 anchored claim, "
        "all anchor ids real"
    )
    if len(events) != 1:
        return CaseOutcome(
            False, expected, f"{len(events)} event(s)",
            detail=f"payloads={[e.payload for e in events]}",
        )
    p = events[0].payload
    if p.get("kind") != "taste":
        return CaseOutcome(False, expected, f"kind={p.get('kind')!r}")
    if p.get("tier") not in _TASTE_TIERS:
        return CaseOutcome(False, expected, f"off-rubric tier={p.get('tier')!r}")

    seeded_ids = {survived.id, killed.id}
    anchored = [a.get("past_claim_id") for a in (p.get("anchored_claims") or [])]
    if not anchored:
        return CaseOutcome(
            False, expected, "verdict fired but anchored_claims is empty",
            detail=f"anchored_papers={p.get('anchored_papers')}",
        )
    ghosts = [a for a in anchored if a not in seeded_ids]
    if ghosts:
        # Should be structurally impossible (service filters) — if it happens
        # the anti-hallucination layer itself is broken.
        return CaseOutcome(
            False, expected, f"HALLUCINATED anchor ids {ghosts}",
            detail="structural anchor filter is not doing its job",
        )
    return CaseOutcome(
        True, expected,
        f"1 event, tier={p['tier']!r}, anchored_claims={anchored}",
    )


def case_taste_cold_start_silent(llm) -> CaseOutcome:
    """① Empty library (no grilled history) → must stay silent (the Q-G gate).

    Deterministic: the gate returns [] before any LLM or network call.
    """
    w = build_world(llm)
    current_body = (
        "Spaced repetition scheduling improves long-term retention of foreign "
        "vocabulary in third-language learners."
    )
    register_current(w, artifact_id="c2s-art-cur", claim_id="c2s-cur", body=current_body)

    events = asyncio.run(w.lens.assess_taste("c2s-art-cur", "c2s-cur", current_body))

    expected = "0 events (cold start must be silent)"
    if events:
        return CaseOutcome(
            False, expected, f"{len(events)} event(s) — GATE BROKEN",
            detail=f"payloads={[e.payload for e in events]}",
        )
    return CaseOutcome(True, expected, "0 events")


def case_edges_fire(llm) -> CaseOutcome:
    """③ Obvious method-reuse pair → at least one semantic LINK edge."""
    w = build_world(llm)
    a = seed_grilled(
        w, claim_id="c3-claim-a", artifact_id="c3-art-a",
        body=(
            "Contrastive learning on augmented image pairs improves "
            "representation quality for downstream image classification."
        ),
        outcome="survived",
        rationale="Survived: augmentation-invariance argument held under grilling.",
    )
    b = seed_grilled(
        w, claim_id="c3-claim-b", artifact_id="c3-art-b",
        body=(
            "Contrastive learning on augmented sentence pairs improves "
            "representation quality for downstream text retrieval."
        ),
        outcome="survived",
        rationale="Survived: the same contrastive objective transferred to text pairs.",
    )

    events = asyncio.run(w.lens.compute_semantic_edges(LIB))

    expected = ">=1 LINK with legal edge type between the two seeded claims"
    seeded_ids = {a.id, b.id}
    good = [
        e for e in events
        if e.payload.get("edge_type") in _SEMANTIC_EDGE_TYPES
        and e.payload.get("source_claim_id") in seeded_ids
        and e.payload.get("target_claim_id") in seeded_ids
    ]
    if not good:
        return CaseOutcome(
            False, expected, f"{len(events)} LINK event(s), none valid",
            detail=f"payloads={[e.payload for e in events]}",
        )
    types = sorted({e.payload["edge_type"] for e in good})
    return CaseOutcome(True, expected, f"{len(good)} edge(s), types={types}")


def case_edges_silent(llm) -> CaseOutcome:
    """③ Lexical overlap, zero semantic relation → zero edges (no over-linking)."""
    w = build_world(llm)
    c = seed_grilled(
        w, claim_id="c3s-claim-c", artifact_id="c3s-art-c",
        body=(
            "Daily green tea consumption reduces self-reported anxiety levels "
            "in college students."
        ),
        outcome="survived",
        rationale="Survived: anxiety self-reports dropped in the tea group.",
    )
    d = seed_grilled(
        w, claim_id="c3s-claim-d", artifact_id="c3s-art-d",
        body=(
            "Green roof installation reduces summer cooling energy consumption "
            "in urban buildings."
        ),
        outcome="survived",
        rationale="Survived: cooling-load meters showed the reduction.",
    )

    expected = "0 LINK events (unrelated pair, no over-connection)"
    # Precondition: the pair must share lexical terms so the LLM is actually
    # consulted (both directions use the same symmetric prefilter).
    precondition_err = check_prefilter_reaches_llm(w, c.body, d)
    if precondition_err:
        return CaseOutcome(False, expected, "pair never reached LLM",
                           detail=precondition_err)

    events = asyncio.run(w.lens.compute_semantic_edges(LIB))
    if events:
        return CaseOutcome(
            False, expected, f"{len(events)} LINK event(s) — OVER-CONNECTED",
            detail=f"payloads={[e.payload for e in events]}",
        )
    return CaseOutcome(True, expected, "0 LINK events")


# ---------------------------------------------------------------------------
# Harness — retry-once policy, report table, exit code
# ---------------------------------------------------------------------------

CASES = [
    ("C1-fire", "② contradiction fires on frontal conflict", case_contradiction_fire),
    ("C1-silent", "② contradiction silent on compatible pair", case_contradiction_silent),
    ("C2-fire", "① taste fires on incremental claim w/ history", case_taste_fire),
    ("C2-silent", "① taste silent on cold start", case_taste_cold_start_silent),
    ("C3-fire", "③ semantic edge on method-reuse pair", case_edges_fire),
    ("C3-silent", "③ zero edges on unrelated pair", case_edges_silent),
]


@dataclass
class Row:
    case_id: str
    label: str
    status: str  # PASS | FLAKY | FAIL
    expected: str
    actual: str
    detail: str = ""


def run_attempt(fn, llm) -> CaseOutcome:
    try:
        return fn(llm)
    except Exception as exc:  # noqa: BLE001 — canary must report, not crash
        return CaseOutcome(
            False, "case completes without exception",
            f"EXCEPTION {type(exc).__name__}: {exc}",
            detail=traceback.format_exc(limit=5),
        )


def main() -> int:
    config = load_llm_config()
    if config is None:
        print(
            "SETUP ERROR: no LLM config. Expected ANNEAL_LLM_KEY / "
            "ANNEAL_LLM_MODEL in backend/.env (see anneal/llm/config.py).",
            file=sys.stderr,
        )
        return 2
    try:
        llm = create_client(config)
    except Exception as exc:  # missing sdk package etc.
        print(f"SETUP ERROR: cannot create LLM client: {exc}", file=sys.stderr)
        return 2

    print("=" * 78)
    print("L3 LENS CANARY — known-sample sentinel challenge")
    print(f"  anneal package : {Path(anneal.__file__).resolve()}")
    print(f"  provider/model : {config.provider} / {config.model}"
          f" (base_url={config.base_url})")
    print(f"  storage        : throwaway InMemory store+repo per case")
    print("=" * 78)

    rows: list[Row] = []
    for case_id, label, fn in CASES:
        print(f"\n[{case_id}] {label} ...", flush=True)
        first = run_attempt(fn, llm)
        if first.ok:
            rows.append(Row(case_id, label, "PASS", first.expected, first.actual))
            print(f"[{case_id}] PASS — {first.actual}")
            continue

        print(f"[{case_id}] attempt 1 failed ({first.actual}); retrying once "
              f"with fresh state ...", flush=True)
        second = run_attempt(fn, llm)
        if second.ok:
            rows.append(Row(
                case_id, label, "FLAKY", second.expected,
                f"retry: {second.actual} (first attempt: {first.actual})",
                detail=first.detail,
            ))
            print(f"[{case_id}] FLAKY — passed on retry: {second.actual}")
        else:
            rows.append(Row(
                case_id, label, "FAIL", second.expected,
                f"attempt1: {first.actual} | attempt2: {second.actual}",
                detail="\n--- attempt 1 ---\n" + first.detail
                       + "\n--- attempt 2 ---\n" + second.detail,
            ))
            print(f"[{case_id}] FAIL — both attempts failed")

    # ---- report table ----
    print("\n" + "=" * 78)
    print("CANARY REPORT")
    print("=" * 78)
    id_w = max(len(r.case_id) for r in rows)
    st_w = max(len(r.status) for r in rows)
    for r in rows:
        print(f"{r.case_id:<{id_w}}  {r.status:<{st_w}}  {r.label}")
        print(f"{'':<{id_w}}  {'':<{st_w}}  expected: {r.expected}")
        print(f"{'':<{id_w}}  {'':<{st_w}}  actual  : {r.actual}")

    flaky = [r for r in rows if r.status == "FLAKY"]
    failed = [r for r in rows if r.status == "FAIL"]

    if flaky:
        print("\nFLAKY (passed only on retry — watch these; a flapping canary "
              "is a drifting detector):")
        for r in flaky:
            print(f"  {r.case_id}: first-attempt failure detail:")
            for line in (r.detail or "(no detail)").splitlines():
                print(f"    {line}")

    if failed:
        print("\nFAILURES:")
        for r in failed:
            print(f"  {r.case_id}: {r.label}")
            for line in (r.detail or "(no detail)").splitlines():
                print(f"    {line}")

    n_pass = sum(1 for r in rows if r.status == "PASS")
    print(f"\nSUMMARY: {n_pass} PASS, {len(flaky)} FLAKY, {len(failed)} FAIL "
          f"(of {len(rows)})")
    if failed:
        print("RESULT: RED — a detector that should scream is mute, or one that "
              "should be silent is screaming. Do not ship.")
        return 1
    print("RESULT: GREEN — every sentinel screamed/stayed silent on cue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
