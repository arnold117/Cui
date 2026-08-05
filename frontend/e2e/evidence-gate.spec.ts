import { expect, test } from "@playwright/test"

const challenge = { id: "ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending", sequence: 1, attack_surface: "The comparison group may practise differently.", why_it_matters: "Practice alone may not explain the difference.", self_check_method: "Compare retrieval effort across groups.", answers: [], provenance: { generator_kind: "system", prompt_version: "v1", model_identifier: "test-model", basis_refs: ["question", "claim"], uncertainty: "moderate" } }
const snapshot = { id: "c-1", version_id: "cv-1", text: "Repeated recall improves later access." }
let desk = { id: "w-1", question: { version_id: "q-1", text: "Why does practice change recall?" }, sequence: 4, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [], materials: [] }
let round: Record<string, unknown> = { id: "r-1", workspace_id: "w-1", question_snapshot: { version_id: "q-1", text: "Why does practice change recall?" }, claim_snapshot: snapshot, sequence: 1, verdict: null, challenges: [challenge], ledger: { answered: [], deferred: [], pending: [challenge], brought_unconfirmed: [] }, rounds: [], evidence_candidates: [], confirmed_facts: [] }

test("bring a material, propose a contradiction, confirm it, and see the deterministic challenge with a receipt", async ({ page }) => {
  const requests: { url: string; body?: Record<string, unknown> }[] = []
  await page.route("**/api/v2/**", async route => {
    const req = route.request(), url = new URL(req.url()).pathname, method = req.method(), body = req.postDataJSON?.() as Record<string, unknown>
    requests.push({ url, body })
    const json = (value: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value) })
    if (method === "GET" && url === "/api/v2/universes/active") return json({ id: "u-1" })
    if (method === "GET" && url === "/api/v2/workspaces/w-1") return json(desk)
    if (method === "GET" && url === "/api/v2/review-rounds/r-1") return json(round)
    if (method === "POST" && url === "/api/v2/workspaces/w-1/materials") {
      const material = { id: "m-1", workspace_id: "w-1", excerpt: body.excerpt as string, source_locator: body.source_locator ?? null, parse_status: body.parse_status as string, purpose: body.purpose as string }
      desk = { ...desk, materials: [...desk.materials, material] }
      return json({ commit_position: 1, event_ids: ["e1"], result: { material_id: material.id, workspace_id: "w-1" }, fragment: desk })
    }
    if (method === "POST" && url === "/api/v2/review-rounds/r-1/evidence-candidates") {
      const material = (desk as { materials: Array<{ id: string; excerpt: string; source_locator: string | null }> }).materials.find(m => m.id === body.material_id)!
      const candidate = { id: "ec-1", round_id: "r-1", workspace_id: "w-1", claim_snapshot: snapshot, material_anchor: { id: material.id, excerpt: material.excerpt, source_locator: material.source_locator }, relation: body.relation, status: "pending", sequence: 1, uncertainty: body.uncertainty ?? null, provenance: { generator_kind: "user" } }
      round = { ...round, evidence_candidates: [...(round.evidence_candidates as unknown[]), candidate] }
      return json({ commit_position: 2, event_ids: ["e2"], result: { candidate_id: candidate.id, round_id: "r-1" }, fragment: round })
    }
    if (method === "POST" && url === "/api/v2/evidence-candidates/ec-1/confirm") {
      const candidate = (round.evidence_candidates as Array<{ id: string; relation: string; material_anchor: { id: string; excerpt: string; source_locator: string | null } }>)[0]
      const deterministic = { id: "det-ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending", sequence: 1, attack_surface: `已确认反证：${candidate.material_anchor.excerpt}`, why_it_matters: `这段材料已被确认与 claim「${snapshot.text}」构成反证；审查必须正面处理它，不能绕过。`, self_check_method: "面对这段已确认反证，写下你的回应：它是否成立、是否被解释，或 claim 是否需要划界。", answers: [], provenance: { generator_kind: "system", prompt_version: "deterministic-evidence-contradiction-v1", model_identifier: null, basis_refs: [candidate.material_anchor.id, candidate.id], uncertainty: "已确认取证事实" } }
      round = { ...round, evidence_candidates: (round.evidence_candidates as unknown[]).map(c => ({ ...(c as Record<string, unknown>), status: "confirmed" })), confirmed_facts: [{ id: candidate.id, relation: candidate.relation, material_anchor: candidate.material_anchor, claim_snapshot: snapshot }], challenges: [...(round.challenges as unknown[]), deterministic] }
      return json({ commit_position: 3, event_ids: ["e3"], result: { candidate_id: candidate.id, round_id: "r-1", relation: candidate.relation, challenge_id: deterministic.id }, fragment: round })
    }
    return route.fulfill({ status: 404, body: JSON.stringify({ detail: url }) })
  })

  await page.goto("/workspaces/w-1")
  await page.getByLabel("摘录或观察").fill("The intervention group shows the opposite effect.")
  await page.getByRole("button", { name: "带入材料" }).click()
  await expect(page.getByText("The intervention group shows the opposite effect.")).toBeVisible()
  expect(requests.find(x => x.url.endsWith("/materials"))?.body).toMatchObject({ excerpt: "The intervention group shows the opposite effect.", parse_status: "parsed", purpose: "evidence", expected_sequence: 0 })

  await page.goto("/review-rounds/r-1")
  await expect(page.getByText("并列证据台 · 取证候选未确认")).toBeVisible()
  await page.getByLabel("选择待取证材料").selectOption("m-1")
  await page.getByRole("radio", { name: "反证" }).check()
  await page.getByRole("button", { name: "提出候选" }).click()
  await expect(page.getByRole("button", { name: "确认是反证" })).toBeVisible()
  expect(requests.find(x => x.url.endsWith("evidence-candidates"))?.body).toMatchObject({ material_id: "m-1", relation: "contradicts", expected_sequence: 0 })

  await page.getByRole("button", { name: "确认是反证" }).click()
  await expect(page.getByText(/已确认的取证事实：The intervention group shows the opposite effect\. 与 claim 构成 反证/)).toBeVisible()
  await expect(page.getByText("已确认反证：The intervention group shows the opposite effect.")).toBeVisible()
  await expect(page.getByText(/生成依据：m-1 · ec-1 · 不确定性：已确认取证事实/)).toBeVisible()
  expect(requests.find(x => x.url.endsWith("/confirm"))?.body).toMatchObject({ expected_sequence: 1 })
})
