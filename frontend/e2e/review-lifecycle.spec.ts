import { expect, test } from "@playwright/test"

const challenge = { id: "ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending", sequence: 1, attack_surface: "替代解释是否被排除", why_it_matters: "可能是混淆变量在起作用", self_check_method: "试着写下一个反例", answers: [], provenance: { generator_kind: "system", prompt_version: "v1", model_identifier: "test-model", basis_refs: ["question", "claim"], uncertainty: "待检验" } }
const snapshot = { id: "c-1", version_id: "cv-1", text: "Repeated recall improves later access." }
function round(v: { verdict: unknown; challengeStatus: string; answers: unknown[] }) {
  const ch = { ...challenge, status: v.challengeStatus, sequence: v.answers.length ? 2 : 1, answers: v.answers }
  return { id: "r-1", workspace_id: "w-1", question_snapshot: { version_id: "q-1", text: "Why does practice change recall?" }, claim_snapshot: snapshot, sequence: 1, verdict: v.verdict, challenges: [ch], ledger: { answered: v.answers.length ? [ch] : [], deferred: [], pending: v.challengeStatus === "pending" ? [ch] : [], brought_unconfirmed: v.answers.length ? [ch] : [] }, rounds: [] }
}

test("answer, record a survived verdict, and re-review the claim", async ({ page }) => {
  let state = round({ verdict: null, challengeStatus: "pending", answers: [] })
  await page.route("**/api/v2/**", async route => {
    const req = route.request(), url = new URL(req.url()).pathname, method = req.method()
    const json = (value: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value) })
    if (method === "GET" && url === "/api/v2/review-rounds/r-1") return json(state)
    if (method === "POST" && url === "/api/v2/challenges/ch-1/answers") {
      state = round({ verdict: null, challengeStatus: "answered", answers: [{ version_id: "av-1", text: "my reply", provisional_anchor_refs: [] }] })
      return json({ commit_position: 2, event_ids: ["e2"], result: { challenge_id: "ch-1", review_round_id: "r-1", answer_version_id: "av-1" }, fragment: state })
    }
    if (method === "POST" && url === "/api/v2/review-rounds/r-1/verdicts") {
      const verdict = { round_id: "r-1", verdict_type: "survived", user_reason: "stood this round" }
      state = { ...round({ verdict, challengeStatus: "resolved_by_verdict", answers: [{ version_id: "av-1", text: "my reply", provisional_anchor_refs: [] }] }), sequence: 2, rounds: [{ id: "r-1", claim_id: "c-1", question_snapshot: { version_id: "q-1", text: "Why does practice change recall?" }, claim_snapshot: snapshot, verdict }] }
      return json({ commit_position: 3, event_ids: ["e3"], result: { review_round_id: "r-1", verdict_type: "survived" }, fragment: state })
    }
    return route.fulfill({ status: 404, body: JSON.stringify({ detail: url }) })
  })
  await page.goto("/review-rounds/r-1")
  await expect(page.getByText("替代解释是否被排除")).toBeVisible()
  await page.getByLabel("我目前的回应").fill("my reply")
  await page.getByRole("button", { name: "保存答辩" }).click()
  await expect(page.getByText("答辩已保存，挑战仍待裁决。")).toBeVisible()
  await expect(page.getByText("已回应 · 待裁决")).toBeVisible()
  await page.getByRole("button", { name: "作出本轮裁决" }).click()
  await expect(page.getByText("这是一项你的判断。Cui 不会替你决定结果。")).toBeVisible()
  await page.getByRole("radio", { name: /暂时站住了/ }).check()
  await page.getByLabel("你的理由").fill("stood this round")
  await page.getByRole("button", { name: "确认裁决" }).click()
  await expect(page.getByRole("button", { name: "再次审查这一条 claim" })).toBeVisible()
  await expect(page.getByText(/裁决：survived/)).toBeVisible()
  await expect(page.getByText("这条挑战仍待回应")).not.toBeVisible()
})

test("a boundary verdict keeps the claim and opens a new question workspace", async ({ page }) => {
  let state = round({ verdict: null, challengeStatus: "pending", answers: [] })
  await page.route("**/api/v2/**", async route => {
    const req = route.request(), url = new URL(req.url()).pathname, method = req.method()
    const json = (value: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value) })
    if (method === "GET" && url === "/api/v2/universes/active") return json({ id: "u-1" })
    if (method === "GET" && url === "/api/v2/review-rounds/r-1") return json(state)
    if (method === "POST" && url === "/api/v2/review-rounds/r-1/verdicts") {
      const verdict = { round_id: "r-1", verdict_type: "boundary", user_reason: "needs narrowing" }
      state = { ...round({ verdict, challengeStatus: "resolved_by_verdict", answers: [] }), sequence: 2, rounds: [{ id: "r-1", claim_id: "c-1", question_snapshot: { version_id: "q-1", text: "Why does practice change recall?" }, claim_snapshot: snapshot, verdict }] }
      return json({ commit_position: 2, event_ids: ["e2"], result: { review_round_id: "r-1", verdict_type: "boundary" }, fragment: state })
    }
    if (method === "POST" && url === "/api/v2/universes/u-1/workspaces") return json({ commit_position: 3, event_ids: ["e3"], result: { workspace_id: "w-2" } })
    return route.fulfill({ status: 404, body: JSON.stringify({ detail: url }) })
  })
  await page.goto("/review-rounds/r-1")
  await expect(page.getByText("替代解释是否被排除")).toBeVisible()
  await page.getByRole("button", { name: "作出本轮裁决" }).click()
  await page.getByRole("radio", { name: /需要收窄／改写/ }).check()
  await page.getByLabel("你的理由").fill("needs narrowing")
  await page.getByRole("button", { name: "确认裁决" }).click()
  await expect(page.getByText(/这条 claim 已保留为本轮结论/)).toBeVisible()
  await page.getByRole("button", { name: "围绕这条边界开一个新问题" }).click()
  await expect(page).toHaveURL("/workspaces/w-2")
})
