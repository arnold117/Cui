"""T5 real-DB e2e: an ACTIVE corpus material reaches evidence-candidate confirm.

Runs against the real anneal database through the HTTP slice4 endpoints
(plan T5 acceptance: "任一 active 材料可走到 evidence candidate 三态,复用 slice4
端点,一条真流"). One real LLM call happens when the review round starts
(native design: the initial challenge is generated atomically).

Usage (backend/, cui env, backend/.env with a live CUI_DATABASE_URL):
    python scripts/t5_e2e_corpus_evidence.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from cui.api.app import create_native_app  # noqa: E402
from cui.research_universe.api.routes import LibraryContext  # noqa: E402
from cui.tools.v4_importer import ACTIVE_WS_COMMAND, workspace_id_for  # noqa: E402

app = create_native_app()
with TestClient(app) as client:
    ws_id = workspace_id_for(ACTIVE_WS_COMMAND)
    desk = client.get(f"/api/v2/workspaces/{ws_id}").json()
    materials = desk.get("materials") or []
    active_materials = [m for m in materials if (m.get("source_locator") or "").startswith("arxiv:")]
    assert len(active_materials) > 0, f"no active corpus materials in workspace {ws_id}"
    material = active_materials[0]
    run = uuid4().hex[:8]
    claim = client.post(
        f"/api/v2/workspaces/{ws_id}/claims",
        json={"command_id": f"t5-e2e-claim-{run}", "expected_sequence": 0,
              "text": f"语料 e2e({run}):文献 {material['source_locator']} 对模型能力的论断值得取证。"},
    )
    assert claim.status_code == 201, claim.text
    claim_id = claim.json()["result"]["claim_id"]
    round_ = client.post(
        f"/api/v2/claims/{claim_id}/review-rounds",
        json={"command_id": f"t5-e2e-round-{run}", "expected_sequence": 0},
    )
    assert round_.status_code == 201, round_.text
    round_id = round_.json()["result"]["review_round_id"]
    candidate = client.post(
        f"/api/v2/review-rounds/{round_id}/evidence-candidates",
        json={"command_id": f"t5-e2e-cand-{run}", "expected_sequence": 0,
              "material_id": material["id"], "relation": "supports", "uncertainty": "e2e-low"},
    )
    assert candidate.status_code == 201, candidate.text
    candidate_id = candidate.json()["result"]["candidate_id"]
    confirmed = client.post(
        f"/api/v2/evidence-candidates/{candidate_id}/confirm",
        json={"command_id": f"t5-e2e-confirm-{run}", "expected_sequence": 1, "user_reason": "t5 e2e"},
    )
    assert confirmed.status_code in (200, 201), confirmed.text
    fragment = confirmed.json()["fragment"]
    states = {c["id"]: c.get("status") for c in fragment.get("evidence_candidates", [])}
    assert states.get(candidate_id) == "confirmed", states
    print(f"E2E OK  material={material['id']} (locator={material['source_locator']}) "
          f"claim={claim_id} round={round_id} candidate={candidate_id} -> confirmed")
