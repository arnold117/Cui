"""Journey canary — real-LLM, real-search six-step literature-dialogue sentinel.

WHY THIS EXISTS
---------------
The mocked e2e tests prove the plumbing, not the behaviour. A real-UI
walkthrough found six bugs they all missed: an all-external selection made the
literature challenge 422; external search emitted empty ``arxiv:`` locators;
drafts drifted off the research question; related-work bent the literature to
fit the claim's camp structure; ... This script drives the REAL configured LLM
(backend/.env -> CUI_LLM_*) and REAL external literature search (arXiv /
OpenAlex) through the whole journey over HTTP and asserts the structural and
behavioural contracts a mock cannot.

Journey: workspace -> orientation -> literature-search (external path: the
throwaway store has no corpus) -> pick 3 -> landscape-summary -> claim(kind) +
review round + literature challenge (external_refs only) -> gap-draft ->
propose gap (external_refs) -> confirm -> related-work-draft -> planted
citation-mismatch probe on the checker.

TRIGGER DISCIPLINE — RUN THIS AFTER ANY OF:
  * any edit to cui/research_universe/api/slice9.py (prompts, drafting context,
    citation checker, external capture) or challenge_generator.py
  * an LLM model / provider swap (CUI_LLM_MODEL / _PROVIDER / _BASE_URL)
  * a change to external search (dialogue sources / corpus)
  * before every release / demo.

WHAT IT COSTS / TOUCHES
-----------------------
~10-15 real chat calls plus arXiv/OpenAlex requests, ~1-3 minutes. Storage is a
throwaway InMemoryNativeEventStore — NO product database is read or written.
NOT part of pytest/CI (money + network + LLM variance): run it by hand.

USAGE
-----
    make canary-journey PY=/path/to/cui/bin/python
    # or: cd backend && python -m scripts.canary_journey [--question Q] [--core-terms a,b]

Exit codes: 0 = GREEN, 1 = RED (>=1 FAIL), 2 = setup error (no LLM config).
The check_* functions are pure so tests/test_canary_journey.py can exercise
them with canned data (no network, no LLM).
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))  # test THIS tree's cui, not an editable install elsewhere

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

DEFAULT_QUESTION = "RLHF 是否真的提升了 LLM 推理能力?"
DEFAULT_CORE_TERMS = ("推理", "reasoning")
CLAIM_TEXT = "关于 RLHF 对推理能力的作用存在两派:一派认为 RLHF 通过偏好对齐提升了推理,另一派认为它只是改善了指令遵循与格式,并未提升真实推理能力。"
CLAIM_KIND = "division"
CAMP_MARKERS = ("两派", "另一派", "一派", "两种观点", "两大阵营")
EMPTY_LOCATORS = {"arxiv:", "doi:", "openalex:", "pmid:", ""}
VERBATIM_RUN = 25  # longest common run (chars) with the claim that counts as copying it


# --- pure checks: each returns (ok, detail) ---------------------------------

def check_no_empty_locators(candidates: list[dict]) -> tuple[bool, str]:
    bad = [c.get("locator") for c in candidates if (c.get("locator") or "").strip().lower() in EMPTY_LOCATORS]
    return (not bad, f"{len(candidates)} candidates, empty-id locators={bad}")


def check_anchored(label: str, text: str, core_terms) -> tuple[bool, str]:
    hit = [t for t in core_terms if t.lower() in (text or "").lower()]
    return (bool(hit), f"{label}: core terms hit={hit} of {list(core_terms)}")


def check_related_work_not_claim_shaped(claim: str, related: str) -> tuple[bool, str]:
    shared = [m for m in CAMP_MARKERS if m in claim and m in related]
    m = difflib.SequenceMatcher(None, claim, related, autojunk=False).find_longest_match(0, len(claim), 0, len(related))
    reproduces_camps = "另一派" in related and "另一派" in claim
    ok = not reproduces_camps and m.size < VERBATIM_RUN
    return (ok, f"shared camp markers={shared} (count={len(shared)}), longest verbatim run with claim={m.size} chars")


def flagged_ratio(checks: list[dict]) -> str:
    bad = sum(1 for c in checks if c["verdict"] != "supported")
    return f"{bad}/{len(checks)} flagged"


def check_external_snapshots(events, locators: list[str], external_ws: str) -> tuple[bool, str]:
    """Every cited external locator has an abstract-scope material_added in the external container."""
    have = {p.source_locator for e in events if e.event_type == "material_added"
            for p in [e.validated_payload()] if p.workspace_id == external_ws and p.content_scope == "abstract"}
    missing = sorted(set(locators) - have)
    return (not missing, f"{len(set(locators))} cited, missing abstract snapshots={missing}")


def check_refs_resolve(events, refs: list[str]) -> tuple[bool, str]:
    have = {p.source_locator for e in events if e.event_type == "material_added" for p in [e.validated_payload()]}
    missing = sorted(set(refs) - have)
    return (not missing, f"{len(set(refs))} refs, unresolved={missing}")


# --- harness ----------------------------------------------------------------

class Report:
    def __init__(self) -> None:
        self.fails = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.fails += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}", flush=True)

    def info(self, name: str, detail: str) -> None:
        print(f"  [INFO] {name} — {detail}", flush=True)


class Abort(Exception):
    pass


class CountingLLM:
    def __init__(self, inner) -> None:
        self._inner, self.calls = inner, 0

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def wrapped(*a, **k):
            self.calls += 1
            return attr(*a, **k)
        return wrapped


def run(question: str, core_terms: tuple[str, ...] | None) -> int:
    from fastapi.testclient import TestClient

    from cui.api.app import create_native_test_app
    from cui.llm.client import create_client
    from cui.llm.config import load_llm_config
    from cui.research_universe.api.routes import LibraryContext, LocalPrincipal
    from cui.research_universe.api.slice9 import _check_citations, create_dialogue_router
    from cui.research_universe.application import Slice1Service
    from cui.research_universe.challenge_generator import PROMPT_VERSION_LITERATURE, RealChallengeGenerator, RealEvidenceCandidateGenerator
    from cui.research_universe.corpus import EXTERNAL_WS_COMMAND, workspace_id_for
    from cui.research_universe.store.event_store import InMemoryNativeEventStore

    config = load_llm_config()
    if config is None:
        print("SETUP ERROR: CUI_LLM_KEY / CUI_LLM_MODEL missing (backend/.env)")
        return 2
    llm = CountingLLM(create_client(config))
    store = InMemoryNativeEventStore()  # throwaway: no product DB
    uid = store.create_active_universe("canary-journey")
    principal = LocalPrincipal()
    ctx = LibraryContext("canary-journey")
    app = create_native_test_app(store, ctx, principal, RealChallengeGenerator(llm, config.model), RealEvidenceCandidateGenerator(llm, config.model))
    service = Slice1Service(store, principal.id, RealChallengeGenerator(llm, config.model), RealEvidenceCandidateGenerator(llm, config.model))
    app.include_router(create_dialogue_router(service, store, ctx, principal, llm), prefix="/api/v2")
    client = TestClient(app)
    rep, timings = Report(), {}
    print(f"question: {question}\nmodel: {config.model}\n")

    def call(step: str, path: str, body: dict) -> dict:
        t0 = time.perf_counter()
        r = client.post(f"/api/v2{path}", json=body)
        timings[step] = time.perf_counter() - t0
        rep.check(f"http {step}", 200 <= r.status_code < 300, f"{r.status_code} in {timings[step]:.1f}s" + ("" if r.is_success else f" body={r.text[:300]}"))
        if not r.is_success:
            raise Abort(step)
        return r.json()

    picked: list[str] = []
    try:
        wid = call("create-workspace", f"/universes/{uid}/workspaces", {"command_id": "w", "expected_sequence": 0, "question": question})["result"]["workspace_id"]
        ori = call("orientation", f"/workspaces/{wid}/dialogue/orientation", {"question": question})
        rep.check("orientation hypotheses>=1 and keywords>=1", bool(ori["hypotheses"] and ori["keywords"]), f"{len(ori['hypotheses'])} hypotheses, {len(ori['keywords'])} keywords")

        search = call("literature-search", f"/workspaces/{wid}/dialogue/literature-search", {"question": question, "query": ori["keywords"][0], "external": True})
        cands = search["candidates"]
        rep.check("literature-search >=3 candidates", len(cands) >= 3, f"{len(cands)} candidates, query={search['query']!r}")
        rep.check("no empty-id locators", *check_no_empty_locators(cands))
        usable = [c for c in cands if c["excerpt"].strip() and c["locator"].strip()][:3]
        refs = [{"locator": c["locator"], "excerpt": c["excerpt"], "url": c.get("url")} for c in usable]
        picked = [r["locator"] for r in refs]
        if not refs:
            raise Abort("no usable candidates")
        sel = {"material_ids": [], "external_refs": refs}

        summary = call("landscape-summary", f"/workspaces/{wid}/dialogue/landscape-summary", sel)

        cid = call("create-claim", f"/workspaces/{wid}/claims", {"command_id": "c", "expected_sequence": 0, "text": CLAIM_TEXT, "kind": CLAIM_KIND})["result"]["claim_id"]
        rid = call("start-review-round", f"/claims/{cid}/review-rounds", {"command_id": "r", "expected_sequence": 0})["result"]["review_round_id"]
        call("literature-challenge", f"/review-rounds/{rid}/literature-challenges", {"command_id": "lit", "expected_sequence": 0, **sel})

        gap = call("gap-draft", f"/workspaces/{wid}/dialogue/gap-draft", sel)
        prop = call("propose-gap", f"/workspaces/{wid}/gap-candidates", {
            "command_id": "g", "expected_sequence": 0, "coverage_statement": gap["coverage_statement"], "search_query": gap["search_query"] or search["query"],
            "matched_locators": picked, "counterexample_invitation": gap["counterexample_invitation"] or "请指出反例", "external_refs": refs})
        call("confirm-gap", f"/gap-candidates/{prop['result']['gap_candidate_id']}/confirm", {"command_id": "gc", "expected_sequence": 1})
        related = call("related-work-draft", f"/workspaces/{wid}/dialogue/related-work-draft", {**sel, "gap_ids": []})
    except Abort as exc:
        print(f"\nABORTED at {exc}; later steps skipped")
        rep.check("journey completed", False, f"aborted at {exc}")
        return _finish(rep, question, picked, timings, llm)

    events = list(store.read_events(uid))
    ext_ws = workspace_id_for(EXTERNAL_WS_COMMAND)
    print()
    rep.check("external snapshots (abstract) in external container", *check_external_snapshots(events, picked, ext_ws))
    lit = [e.validated_payload() for e in events if e.event_type == "challenge_created" and e.validated_payload().prompt_version == PROMPT_VERSION_LITERATURE]
    rep.check("literature challenge produced", bool(lit), f"{len(lit)} literature challenge(s)")
    rep.check("challenge basis_refs resolve to stored materials", *check_refs_resolve(events, [r for c in lit for r in c.basis_refs]))
    gaps = [e.validated_payload() for e in events if e.event_type == "gap_candidate_proposed"]
    rep.check("gap matched_locators resolve to stored materials", *check_refs_resolve(events, [r for g in gaps for r in g.matched_locators]))
    kinds = [e.validated_payload().kind for e in events if e.event_type == "claim_created"]
    rep.check("claim event carries kind", kinds == [CLAIM_KIND], f"kinds={kinds}")

    terms = core_terms or (DEFAULT_CORE_TERMS if question == DEFAULT_QUESTION else None)
    if terms:
        for label, text in (("landscape-summary", summary["text"]), ("gap coverage_statement", gap["coverage_statement"]), ("related-work", related["text"])):
            rep.check(f"question anchoring: {label}", *check_anchored(label, text, terms))
    else:
        rep.info("question anchoring", "SKIPPED: custom --question without --core-terms")
    rep.check("related-work not shaped by claim (no camps / no verbatim)", *check_related_work_not_claim_shaped(CLAIM_TEXT, related["text"]))

    drafts = {"landscape-summary": summary, "gap-draft": gap, "related-work": related}
    for name, d in drafts.items():
        rep.info(f"citation check {name}", f"status={d['citation_check_status']}, {flagged_ratio(d['citation_checks'])}")
    rep.check("citation check available on >=1 draft", any(d["citation_check_status"] == "ok" for d in drafts.values()), ", ".join(f"{n}={d['citation_check_status']}" for n, d in drafts.items()))

    # planted mismatch: one sentence from the material's own abstract, one fabricated claim
    m0 = usable[0]
    first_sentence = re.split(r"(?<=[.!?。])\s+", m0["excerpt"].strip())[0][:300]
    items = [{"locator": m0["locator"], "title": m0.get("title", ""), "excerpt": m0["excerpt"], "content_scope": "abstract"}]
    loc = m0["locator"]
    planted = _check_citations(llm, f"{first_sentence} [{loc}]\n该文在 GSM8K 上将准确率提升了 73.4%,并在 12 种语言的 5,000 名受试者实验中完全复现 [{loc}]。", items)
    if planted["citation_check_status"] != "ok":
        rep.check("planted mismatch: fabricated claim flagged", False, "checker unavailable")
    else:
        v = [c["verdict"] for c in planted["citation_checks"]]
        rep.check("planted mismatch: fabricated claim flagged", len(v) == 2 and v[1] == "unsupported", f"verdicts={v}")
        rep.info("planted mismatch: genuine sentence", f"verdict={v[0] if v else None} (expected supported)")
    return _finish(rep, question, picked, timings, llm)


def _finish(rep: Report, question: str, picked: list[str], timings: dict, llm: CountingLLM) -> int:
    print("\nSUMMARY")
    print(f"  question : {question}")
    print(f"  picked   : {picked}")
    print("  timings  : " + ", ".join(f"{k}={v:.1f}s" for k, v in timings.items()) + f" (total {sum(timings.values()):.1f}s)")
    print(f"  LLM calls: {llm.calls}")
    print(f"\n{'RED' if rep.fails else 'GREEN'} ({rep.fails} failed check(s))")
    return 1 if rep.fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--core-terms", default="", help="comma-separated terms the drafts must mention (default question has built-ins)")
    a = ap.parse_args()
    terms = tuple(t.strip() for t in a.core_terms.split(",") if t.strip()) or None
    return run(a.question, terms)


if __name__ == "__main__":
    sys.exit(main())
