import { expect, test, type Page } from "@playwright/test"

const desk = {
  id: "w-1",
  question: { version_id: "q-1", text: "Why does practice change recall?" },
  sequence: 9,
  note: null,
  note_revisions: [],
  anchors: [],
  claims: [],
  review_rounds: [],
  pending_challenges: [],
  landscape: {
    workspace_id: "w-1",
    question: { version_id: "q-1", text: "Why does practice change recall?" },
    alive_claims: [],
    claim_verdicts: {},
    confirmed_facts: [],
    gaps: [
      { id: "gap-1", workspace_id: "w-1", coverage_statement: "现有文献覆盖了练习的即时效应,但没有覆盖间隔练习在真实课堂的长期保持。", search_record: { query: "spaced practice classroom", scope: "active", matched_locators: ["arxiv:2401.00001"], searched_at: "2026-09-02" }, counterexample_invitation: "如有真实课堂的间隔练习长期数据,请指正。", status: "pending", sequence: 1 },
    ],
  },
}
const round = { id: "r-1", claim_id: "c-1", workspace_id: "w-1", claim_snapshot: { text: "我改写的空缺断言。" }, question_snapshot: desk.question, verdict: null, evidence_candidates: [], ledger: { answered: [], deferred: [], pending: [], brought_unconfirmed: [] }, rounds: [{ id: "r-1" }],
  challenges: [{ id: "ch-1", review_round_id: "r-1", claim_id: "c-1", attack_surface: "课堂数据其实存在", why_it_matters: "w", self_check_method: "s", status: "pending" }] }

type Call = { url: string; body?: Record<string, unknown> }
async function mockApi(page: Page) {
  const requests: Call[] = []
  let confirmed = false
  await page.route("**/api/v2/**", async route => {
    const req = route.request()
    const url = new URL(req.url()).pathname
    const body = req.postDataJSON?.() as Record<string, unknown>
    requests.push({ url, body })
    const json = (value: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value) })
    if (url === "/api/v2/universes/active") return json({ id: "u-1" })
    if (url === "/api/v2/workspaces/w-1" && req.method() === "GET") {
      return json(confirmed ? {
        ...desk,
        landscape: { ...desk.landscape, gaps: [{ ...desk.landscape.gaps[0], status: "confirmed", decision_reason: "人审确认" }] },
      } : desk)
    }
    if (url === "/api/v2/gap-candidates/gap-1/confirm") { confirmed = true; return json({ commit_position: 2, event_ids: ["e2"], result: { gap_candidate_id: "gap-1" } }) }
    if (url === "/api/v2/workspaces/w-1/gap-candidates") return json({ commit_position: 5, event_ids: ["e5"], result: { gap_candidate_id: "gap-2" } })
    if (url === "/api/v2/gap-candidates/gap-2/confirm") return json({ commit_position: 6, event_ids: ["e6"], result: { gap_candidate_id: "gap-2" } })
    if (url === "/api/v2/workspaces/w-1/claims") return json({ commit_position: 3, event_ids: ["e3"], result: { claim_id: "c-1" } })
    if (url === "/api/v2/claims/c-1/review-rounds") return json({ commit_position: 4, event_ids: ["e4"], result: { review_round_id: "r-1" } })
    if (url === "/api/v2/review-rounds/r-1") return json(round)
    return route.fulfill({ status: 404, body: JSON.stringify({ detail: url }) })
  })
  return requests
}

test("legacy pending gap is confirmed on the gap card; its counter-claim round opens on the right and closes back to 现状", async ({ page }) => {
  const requests = await mockApi(page)
  await page.goto("/workspaces/w-1")
  await page.getByRole("button", { name: /^gap/ }).click()
  const panel = page.getByRole("complementary", { name: "聚焦面" })
  await expect(panel.getByRole("heading", { name: "写 gap 时可以倚靠的" })).toBeVisible()
  await expect(page.getByRole("button", { name: "登记一个 gap 候选" })).toHaveCount(0)
  await expect(page.getByText("现有文献覆盖了练习的即时效应,但没有覆盖间隔练习在真实课堂的长期保持。")).toBeVisible()
  await page.getByRole("button", { name: "确认这个 gap", exact: true }).click()
  await expect.poll(() => requests.find(r => r.url.endsWith("/gap-candidates/gap-1/confirm"))?.body).toMatchObject({ user_reason: "人审确认", expected_sequence: 1 })
  await expect(page.getByText("已确认 gap", { exact: true })).toBeVisible()

  // 反证桥接:已确认 gap → 预填草稿 → 署名才固化 vacancy claim 并开审查轮
  await page.getByRole("button", { name: "对这个 gap 发起反证" }).click()
  expect(requests.some(r => r.url.endsWith("/claims"))).toBe(false)
  await expect(page.getByLabel("反证用 claim(空缺断言)")).toHaveValue(/没有覆盖间隔练习在真实课堂的长期保持/)
  await page.getByLabel("反证用 claim(空缺断言)").fill("我改写的空缺断言。")
  await page.getByRole("button", { name: "署名固化为 claim 并开审查轮" }).click()
  await expect(page).toHaveURL(/\/workspaces\/w-1\/rounds\/r-1$/)
  expect(requests.find(r => r.url.endsWith("/workspaces/w-1/claims"))?.body).toMatchObject({ kind: "vacancy" })

  // gap 阶段里打开的轮:收起 = 回到现状
  await expect(panel.locator("blockquote")).toHaveText("我改写的空缺断言。")
  await expect(page.getByRole("heading", { name: "5. gap" })).toBeVisible()
  await panel.getByRole("button", { name: "回到现状" }).click()
  await expect(page).toHaveURL(/\/workspaces\/w-1$/)
  await expect(panel.getByRole("heading", { name: "写 gap 时可以倚靠的" })).toBeVisible()
})

test("without a local draft, drafting is unavailable and a hand-written gap submits as confirmed", async ({ page }) => {
  const requests = await mockApi(page)
  await page.goto("/workspaces/w-1")
  await page.getByRole("button", { name: /^gap/ }).click()
  await expect(page.getByRole("button", { name: "让 Cui 起草 gap 候选" })).toBeDisabled()
  await expect(page.getByText("这台设备上没有选料草稿,起草不可用;可以直接手写。")).toBeVisible()
  await page.getByLabel(/覆盖范围声明/).fill("现有文献覆盖了实验室里的即时回忆,但没有覆盖课堂里一学期后的保持。")
  await page.getByLabel("邀请反例").fill("有课堂长期追踪数据的研究会推翻它。")
  await page.getByRole("button", { name: "提交并确认这个 gap" }).click()
  await expect.poll(() => requests.filter(r => r.url.includes("gap-candidates")).map(r => r.url)).toEqual(["/api/v2/workspaces/w-1/gap-candidates", "/api/v2/gap-candidates/gap-2/confirm"])
  expect(requests.find(r => r.url === "/api/v2/workspaces/w-1/gap-candidates")?.body).toMatchObject({ search_query: "(未检索,手工登记)", matched_locators: [] })
})
