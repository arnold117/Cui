import { expect, test } from "@playwright/test"

const challenge = { id: "ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending", sequence: 1, attack_surface: "The comparison group may practise differently.", why_it_matters: "Practice alone may not explain the difference.", self_check_method: "Compare retrieval effort across groups.", answers: [], provenance: { generator_kind: "system", prompt_version: "slice1-narrow-challenge-v1", model_identifier: "test-model", basis_refs: ["question", "claim"], uncertainty: "moderate" } }
const snapshot = { id: "c-1", version_id: "cv-1", text: "Repeated recall improves later access." }
let desk = { id: "w-1", question: { version_id: "q-1", text: "Why does practice change recall?" }, sequence: 4, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [], materials: [{ id: "m-1", workspace_id: "w-1", excerpt: "The intervention group shows the opposite effect.", source_locator: "Paper A", parse_status: "parsed", purpose: "evidence" }] }
let round: Record<string, unknown> = { id: "r-1", workspace_id: "w-1", question_snapshot: { version_id: "q-1", text: "Why does practice change recall?" }, claim_snapshot: snapshot, sequence: 1, verdict: null, challenges: [challenge], ledger: { answered: [], deferred: [], pending: [challenge], brought_unconfirmed: [] }, rounds: [], evidence_candidates: [], confirmed_facts: [] }

test("generate an additional challenge and a generated evidence candidate (mock)", async ({ page }) => {
  const requests: { url: string; body?: Record<string, unknown> }[] = []
  await page.route("**/api/v2/**", async route => {
    const req = route.request(), url = new URL(req.url()).pathname, method = req.method(), body = req.postDataJSON?.() as Record<string, unknown>
    requests.push({ url, body })
    const json = (value: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value) })
    if (method === "GET" && url === "/api/v2/universes/active") return json({ id: "u-1" })
    if (method === "GET" && url === "/api/v2/workspaces/w-1") return json(desk)
    if (method === "GET" && url === "/api/v2/review-rounds/r-1") return json(round)
    if (method === "POST" && url === "/api/v2/review-rounds/r-1/challenges") {
      const extra = { id: "ch-2", review_round_id: "r-1", claim_id: "c-1", status: "pending", sequence: 1, attack_surface: "A missing control group for the transfer effect.", why_it_matters: "Transfer may come from exposure, not retrieval practice.", self_check_method: "Add a group that only re-reads the material.", answers: [], provenance: { generator_kind: "system", prompt_version: "slice6-expanded-challenge-v1", model_identifier: "test-model", basis_refs: ["question", "claim", "ch-1"], uncertainty: "moderate" } }
      round = { ...round, challenges: [...(round.challenges as unknown[]), extra] }
      return json({ commit_position: 2, event_ids: ["e2"], result: { challenge_id: extra.id, round_id: "r-1" }, fragment: round })
    }
    if (method === "POST" && url === "/api/v2/review-rounds/r-1/evidence-candidate-generation") {
      const material = (desk as { materials: Array<{ id: string; excerpt: string; source_locator: string | null }> }).materials.find(m => m.id === body.material_id)!
      const candidate = { id: "ec-gen-1", round_id: "r-1", workspace_id: "w-1", claim_snapshot: snapshot, material_anchor: { id: material.id, excerpt: material.excerpt, source_locator: material.source_locator }, relation: "contradicts", status: "pending", sequence: 1, uncertainty: "moderate", rationale: "该对照结果直接与该 claim 的因果方向相反。", evidence_highlight: "shows the opposite effect", provenance: { generator_kind: "system", prompt_version: "slice6-evidence-candidate-v1", model_identifier: "test-model", basis_refs: [material.id] } }
      round = { ...round, evidence_candidates: [...(round.evidence_candidates as unknown[]), candidate] }
      return json({ commit_position: 3, event_ids: ["e3"], result: { candidate_id: candidate.id, round_id: "r-1" }, fragment: round })
    }
    return route.fulfill({ status: 404, body: JSON.stringify({ detail: url }) })
  })

  await page.goto("/review-rounds/r-1")
  await expect(page.getByText("The comparison group may practise differently.")).toBeVisible()

  // generate an additional challenge
  await page.getByRole("button", { name: "生成更多挑战" }).click()
  await expect(page.getByText("A missing control group for the transfer effect.")).toBeVisible()
  expect(requests.find(x => x.url.endsWith("/challenges"))?.body).toMatchObject({ expected_sequence: 0 })

  // generate an evidence candidate
  await page.getByRole("button", { name: "让 Cui 提出取证候选" }).click()
  await expect(page.getByText(/为何/)).toBeVisible()
  await expect(page.getByText("该对照结果直接与该 claim 的因果方向相反。")).toBeVisible()
  await expect(page.getByText("shows the opposite effect", { exact: true })).toBeVisible()
  await expect(page.getByText(/生成依据：m-1 · slice6-evidence-candidate-v1/)).toBeVisible()
  expect(requests.find(x => x.url.endsWith("/evidence-candidate-generation"))?.body).toMatchObject({ material_id: "m-1", expected_sequence: 0 })
})
