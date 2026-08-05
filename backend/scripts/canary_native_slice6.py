"""Native Slice 6 canary — expanded LLM challenge + evidence candidate sentinel.

WHY THIS EXISTS
---------------
Slice 6 changes LLM prompts (``slice6-expanded-challenge-v1`` and
``slice6-evidence-candidate-v1``). Unit tests only prove the prompt text is
present in the code — they CANNOT prove the model behaves. This script drives
the REAL configured LLM (backend/.env → CUI_LLM_*) through the native service
commands and verifies the behavioural contracts that a prompt edit can break:
language-follows-claim, distinct additional challenges that do not repeat,
legal evidence relations with provenance, the failed-parse iron rule, and the
no-auto-verdict/no-auto-claim/no-auto-direction invariant.

TRIGGER DISCIPLINE — RUN THIS AFTER ANY OF:
  * any edit to anneal/research_universe/challenge_generator.py
  * an LLM model / provider swap (CUI_LLM_MODEL / _PROVIDER / _BASE_URL)
  * before every Phase 1 release.

WHAT IT COSTS / TOUCHES
-----------------------
Uses the REAL configured LLM — roughly 6-8 chat calls per clean run (a couple
more on retries). Storage is a throwaway InMemoryNativeEventStore per case — NO
product database is read or written, and no data files are touched. This is
exactly why it is NOT part of the default pytest run (costs money, walks the
network): run it explicitly.

USAGE
-----
    conda activate anneal
    cd backend && python scripts/canary_native_slice6.py

CASES
-----
  C-challenge-zh    a Chinese claim -> the generated challenge is in Chinese,
                    valid schema, language follows the claim.
  C-challenge-en    an English claim -> an English challenge.
  C-multi           after the first (atomic) challenge, an additional challenge
                    has a DISTINCT id, valid schema, and its attack_surface does
                    not verbatim repeat the first.
  C-evidence-zh     a Chinese material excerpt vs a Chinese claim -> a legal
                    evidence relation, non-empty rationale (or acceptable empty),
                    full provenance, language follows the claim.
  C-evidence-en     the same for an English claim/excerpt.
  C-failed-parse    a material whose parse_status == "failed" -> the generated
                    candidate relation MUST be cannot_assess (silent rejected).

Every case also asserts that the LLM calls never created a verdict, a claim,
or a direction (no auto-anything).

FAILURE POLICY (LLM variance)
-----------------------------
A failing case is re-run ONCE with fresh state. Pass on retry -> FLAKY
(reported separately, does not fail the run). Fail twice -> FAIL, and the
process exits non-zero. Exit codes: 0 = all PASS/FLAKY, 1 = >=1 FAIL,
2 = setup error (missing LLM config etc.).

The case functions take ``(challenge_generator, evidence_generator)`` so a unit
test (backend/tests/test_native_slice6.py::test_canary_harness_with_mocks) can
drive the SAME harness logic with mock generators — the live run stays explicit.
"""

from __future__ import annotations

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

from anneal.research_universe.application import (  # noqa: E402
    Slice1Service,
    review_round_projection,
)
from anneal.research_universe.challenge_generator import (  # noqa: E402
    RealChallengeGenerator,
    RealEvidenceCandidateGenerator,
)
from anneal.research_universe.store.event_store import InMemoryNativeEventStore  # noqa: E402
from anneal.llm.client import create_client  # noqa: E402
from anneal.llm.config import load_llm_config  # noqa: E402


def _has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


@dataclass
class CaseOutcome:
    ok: bool
    expected: str
    actual: str
    detail: str = ""


@dataclass
class World:
    store: InMemoryNativeEventStore
    uid: str
    service: Slice1Service


def build_world(challenge_generator, evidence_generator) -> World:
    store = InMemoryNativeEventStore()
    uid = store.create_active_universe("canary")
    service = Slice1Service(store, "canary", challenge_generator, evidence_generator)
    return World(store, uid, service)


def auto_event_violations(w: World, *, seed_claim_ids: set[str]) -> list[str]:
    """Any verdict/direction/claim event beyond the user seeds is a violation.

    The seeds include exactly the claim(s) the canary itself authored; anything
    else named claim_created — or any verdict/direction event at all — means an
    LLM call auto-created state it must never create.
    """
    violations: list[str] = []
    for event in w.store.read_events(w.uid):
        if event.event_type == "verdict_confirmed":
            violations.append("verdict_confirmed auto-created by an LLM call")
        elif event.event_type == "direction_created":
            violations.append("direction_created auto-created by an LLM call")
        elif event.event_type == "claim_created":
            cid = event.validated_payload().claim_id
            if cid not in seed_claim_ids:
                violations.append(f"claim_created auto-created by an LLM call: {cid}")
    return violations


def _seed_round(w: World, *, question: str, claim: str, prefix: str = "seed"):
    """Create a workspace + claim + atomic review round (first challenge).

    Returns (workspace_id, claim_id, round_id, first_challenge_id).
    """
    ws = w.service.create_workspace(w.uid, f"{prefix}-ws", 0, question)
    wid = ws.result_payload["workspace_id"]
    cl = w.service.create_claim(w.uid, wid, f"{prefix}-cl", 0, claim)
    cid = cl.result_payload["claim_id"]
    rr = w.service.start_review_round(w.uid, cid, f"{prefix}-rr", 0)
    return wid, cid, rr.result_payload["review_round_id"], rr.result_payload["challenge_id"]


def _add_evidence_material(w: World, wid: str, *, excerpt: str, parse_status: str = "parsed", command_id: str = "mat") -> str:
    mat = w.service.add_material(w.uid, wid, excerpt, "canary source", parse_status, "evidence", command_id, 0)
    return mat.result_payload["material_id"]


def _no_auto(w: World, seed_claim_ids: set[str]) -> str | None:
    violations = auto_event_violations(w, seed_claim_ids=seed_claim_ids)
    if violations:
        return "; ".join(violations)
    return None


def _challenge_schema_ok(challenge: dict) -> str | None:
    for key in ("attack_surface", "why_it_matters", "self_check_method"):
        value = challenge.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"challenge field {key!r} is empty"
    provenance = challenge.get("provenance") or {}
    if provenance.get("prompt_version") not in ("slice1-narrow-challenge-v1", "slice6-expanded-challenge-v1"):
        return f"unexpected prompt_version {provenance.get('prompt_version')!r}"
    if not isinstance(provenance.get("uncertainty"), str) or not provenance["uncertainty"].strip():
        return "challenge provenance uncertainty is empty"
    return None


# ---------------------------------------------------------------------------
# Cases — each returns a CaseOutcome
# ---------------------------------------------------------------------------


def case_challenge_zh(challenge_generator, evidence_generator) -> CaseOutcome:
    w = build_world(challenge_generator, evidence_generator)
    _, cid, rid, _ = _seed_round(w, question="为什么摄入咖啡因会改变记忆？", claim="日常咖啡因摄入会提升健康成年人的短期记忆。")
    frag = review_round_projection(w.store, w.uid, rid)
    challenge = frag["challenges"][0]

    expected = "challenge in Chinese with valid schema, language follows the claim"
    if not _has_cjk(challenge["attack_surface"]):
        return CaseOutcome(False, expected, "attack_surface is not Chinese", detail=str(challenge))
    schema_err = _challenge_schema_ok(challenge)
    if schema_err:
        return CaseOutcome(False, expected, schema_err, detail=str(challenge))
    no_auto = _no_auto(w, seed_claim_ids={cid})
    if no_auto:
        return CaseOutcome(False, expected, f"auto-event: {no_auto}", detail=str(challenge))
    return CaseOutcome(True, expected, f"attack_surface={challenge['attack_surface'][:48]!r}")


def case_challenge_en(challenge_generator, evidence_generator) -> CaseOutcome:
    w = build_world(challenge_generator, evidence_generator)
    _, cid, rid, _ = _seed_round(w, question="Why does caffeine change memory?", claim="Daily caffeine intake improves short-term memory recall in healthy adults.")
    frag = review_round_projection(w.store, w.uid, rid)
    challenge = frag["challenges"][0]

    expected = "challenge in English with valid schema, language follows the claim"
    if _has_cjk(challenge["attack_surface"]):
        return CaseOutcome(False, expected, "attack_surface is not English", detail=str(challenge))
    schema_err = _challenge_schema_ok(challenge)
    if schema_err:
        return CaseOutcome(False, expected, schema_err, detail=str(challenge))
    no_auto = _no_auto(w, seed_claim_ids={cid})
    if no_auto:
        return CaseOutcome(False, expected, f"auto-event: {no_auto}", detail=str(challenge))
    return CaseOutcome(True, expected, f"attack_surface={challenge['attack_surface'][:48]!r}")


def case_multi(challenge_generator, evidence_generator) -> CaseOutcome:
    w = build_world(challenge_generator, evidence_generator)
    _, cid, rid, first_id = _seed_round(w, question="为什么摄入咖啡因会改变记忆？", claim="日常咖啡因摄入会提升健康成年人的短期记忆。")
    w.service.generate_additional_challenge(w.uid, rid, "extra", 0)
    frag = review_round_projection(w.store, w.uid, rid)
    challenges = frag["challenges"]
    if len(challenges) != 2:
        return CaseOutcome(False, "a second, distinct challenge", f"{len(challenges)} challenge(s) present")
    first, second = challenges
    expected = "distinct id, valid schema, attack_surface does not verbatim repeat the first"
    if second["id"] == first_id or second["id"] == first["id"]:
        return CaseOutcome(False, expected, "additional challenge reused the first challenge id")
    if second["attack_surface"].strip() == first["attack_surface"].strip():
        return CaseOutcome(False, expected, "attack_surface verbatim repeats the first", detail=str(second))
    schema_err = _challenge_schema_ok(second)
    if schema_err:
        return CaseOutcome(False, expected, schema_err, detail=str(second))
    if second.get("provenance", {}).get("prompt_version") != "slice6-expanded-challenge-v1":
        return CaseOutcome(False, expected, "additional challenge did not carry slice6-expanded-challenge-v1", detail=str(second))
    no_auto = _no_auto(w, seed_claim_ids={cid})
    if no_auto:
        return CaseOutcome(False, expected, f"auto-event: {no_auto}", detail=str(second))
    return CaseOutcome(True, expected, f"second attack_surface={second['attack_surface'][:48]!r}")


def _evidence_language_case(challenge_generator, evidence_generator, *, language: str) -> CaseOutcome:
    w = build_world(challenge_generator, evidence_generator)
    if language == "zh":
        question, claim = "为什么摄入咖啡因会改变记忆？", "日常咖啡因摄入会提升健康成年人的短期记忆。"
        excerpt = "一项对照实验显示，连续八周每日摄入 300mg 咖啡因的被试在延迟回忆测试中得分显著更高。"
        expected = "legal relation + provenance; rationale follows the Chinese claim"
    else:
        question, claim = "Why does caffeine change memory?", "Daily caffeine intake improves short-term memory recall in healthy adults."
        excerpt = "In a controlled trial, participants given 300mg caffeine daily for eight weeks scored significantly higher on delayed recall."
        expected = "legal relation + provenance; rationale follows the English claim"
    wid, cid, rid, _ = _seed_round(w, question=question, claim=claim)
    mid = _add_evidence_material(w, wid, excerpt=excerpt, command_id="ev-mat")
    w.service.generate_evidence_candidate(w.uid, rid, mid, "ev", 0)
    frag = review_round_projection(w.store, w.uid, rid)
    candidates = frag["evidence_candidates"]
    if not candidates:
        return CaseOutcome(False, expected, "no evidence candidate was produced")
    cand = candidates[0]
    if cand["relation"] not in ("supports", "contradicts", "silent", "cannot_assess"):
        return CaseOutcome(False, expected, f"illegal relation {cand['relation']!r}", detail=str(cand))
    provenance = cand.get("provenance") or {}
    if provenance.get("prompt_version") != "slice6-evidence-candidate-v1":
        return CaseOutcome(False, expected, f"missing slice6 evidence provenance: {provenance}", detail=str(cand))
    if provenance.get("model_identifier") is None:
        return CaseOutcome(False, expected, "model_identifier is missing from provenance", detail=str(cand))
    if not provenance.get("basis_refs"):
        return CaseOutcome(False, expected, "basis_refs is empty (must carry the material id)", detail=str(cand))
    if not isinstance(cand.get("uncertainty"), str) or not cand["uncertainty"].strip():
        return CaseOutcome(False, expected, "uncertainty is missing from the candidate", detail=str(cand))
    rationale = cand.get("rationale")
    if rationale:
        if language == "zh" and not _has_cjk(rationale):
            return CaseOutcome(False, expected, "rationale does not follow the Chinese claim", detail=str(cand))
        if language == "en" and _has_cjk(rationale):
            return CaseOutcome(False, expected, "rationale does not follow the English claim", detail=str(cand))
    elif cand["relation"] != "silent":
        # Non-silent relations should carry a rationale; a missing one is a WEAK
        # pass but still acceptable per spec ("or acceptable empty").
        pass
    no_auto = _no_auto(w, seed_claim_ids={cid})
    if no_auto:
        return CaseOutcome(False, expected, f"auto-event: {no_auto}", detail=str(cand))
    return CaseOutcome(True, expected, f"relation={cand['relation']!r}, rationale={rationale[:40]!r}")


def case_evidence_zh(challenge_generator, evidence_generator) -> CaseOutcome:
    return _evidence_language_case(challenge_generator, evidence_generator, language="zh")


def case_evidence_en(challenge_generator, evidence_generator) -> CaseOutcome:
    return _evidence_language_case(challenge_generator, evidence_generator, language="en")


def case_failed_parse(challenge_generator, evidence_generator) -> CaseOutcome:
    w = build_world(challenge_generator, evidence_generator)
    wid, cid, rid, _ = _seed_round(w, question="为什么摄入咖啡因会改变记忆？", claim="日常咖啡因摄入会提升健康成年人的短期记忆。")
    mid = _add_evidence_material(w, wid, excerpt="(broken parse — bytes cannot be read)", parse_status="failed", command_id="fail-mat")
    w.service.generate_evidence_candidate(w.uid, rid, mid, "fail-ev", 0)
    frag = review_round_projection(w.store, w.uid, rid)
    candidates = frag["evidence_candidates"]
    expected = "failed-parse material -> relation forced to cannot_assess (silent rejected)"
    if not candidates:
        return CaseOutcome(False, expected, "no evidence candidate was produced")
    cand = candidates[0]
    if cand["relation"] != "cannot_assess":
        return CaseOutcome(False, expected, f"relation={cand['relation']!r} (must be cannot_assess)", detail=str(cand))
    no_auto = _no_auto(w, seed_claim_ids={cid})
    if no_auto:
        return CaseOutcome(False, expected, f"auto-event: {no_auto}", detail=str(cand))
    return CaseOutcome(True, expected, "relation=cannot_assess")


# ---------------------------------------------------------------------------
# Harness — retry-once policy, report table, exit code
# ---------------------------------------------------------------------------

CASES = [
    ("C-challenge-zh", "中文 claim → 中文挑战（schema 合法，语言跟随 claim）", case_challenge_zh),
    ("C-challenge-en", "English claim → English challenge", case_challenge_en),
    ("C-multi", "additional challenge → distinct id, no verbatim repeat", case_multi),
    ("C-evidence-zh", "中文材料 ↔ 中文 claim → 合法关系 + provenance", case_evidence_zh),
    ("C-evidence-en", "English material ↔ claim → legal relation + provenance", case_evidence_en),
    ("C-failed-parse", "parse failed → relation forced to cannot_assess", case_failed_parse),
]


@dataclass
class Row:
    case_id: str
    label: str
    status: str  # PASS | FLAKY | FAIL
    expected: str
    actual: str
    detail: str = ""


def run_attempt(fn, challenge_generator, evidence_generator) -> CaseOutcome:
    try:
        return fn(challenge_generator, evidence_generator)
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
            "SETUP ERROR: no LLM config. Expected CUI_LLM_KEY / CUI_LLM_MODEL "
            "in backend/.env (see anneal/llm/config.py).",
            file=sys.stderr,
        )
        return 2
    try:
        llm = create_client(config)
    except Exception as exc:  # missing sdk package etc.
        print(f"SETUP ERROR: cannot create LLM client: {exc}", file=sys.stderr)
        return 2
    challenge_generator = RealChallengeGenerator(llm, config.model)
    evidence_generator = RealEvidenceCandidateGenerator(llm, config.model)

    print("=" * 78)
    print("NATIVE SLICE 6 CANARY — expanded LLM challenge + evidence candidates")
    print(f"  anneal package : {BACKEND_DIR}")
    print(f"  provider/model : {config.provider} / {config.model}"
          f" (base_url={config.base_url})")
    print(f"  storage        : throwaway InMemory store per case")
    print("=" * 78)

    rows: list[Row] = []
    for case_id, label, fn in CASES:
        print(f"\n[{case_id}] {label} ...", flush=True)
        first = run_attempt(fn, challenge_generator, evidence_generator)
        if first.ok:
            rows.append(Row(case_id, label, "PASS", first.expected, first.actual))
            print(f"[{case_id}] PASS — {first.actual}")
            continue
        print(f"[{case_id}] attempt 1 failed ({first.actual}); retrying once "
              f"with fresh state ...", flush=True)
        second = run_attempt(fn, challenge_generator, evidence_generator)
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
        print("\nFLAKY (passed only on retry — watch these):")
        for r in flaky:
            for line in (r.detail or "(no detail)").splitlines():
                print(f"  {r.case_id}: {line}")

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
        print("RESULT: RED — a prompt/model regression broke a Slice 6 contract.")
        return 1
    print("RESULT: GREEN — every sentinel behaved on cue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
