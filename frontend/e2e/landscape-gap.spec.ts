import { expect, test } from "@playwright/test"

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

test("gap candidate can be confirmed from the workspace landscape", async ({ page }) => {
  const requests: { url: string; body?: Record<string, unknown> }[] = []
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
    if (url === "/api/v2/workspaces/w-1/claims") return json({ commit_position: 3, event_ids: ["e3"], result: { claim_id: "c-1" } })
    if (url === "/api/v2/claims/c-1/review-rounds") return json({ commit_position: 4, event_ids: ["e4"], result: { review_round_id: "r-1" } })
    return route.fulfill({ status: 404, body: JSON.stringify({ detail: url }) })
  })
  await page.goto("/workspaces/w-1")
  await expect(page.getByText("现状图景与 gap")).toBeVisible()
  await expect(page.getByText(/覆盖范围:现有文献覆盖了练习的即时效应/)).toBeVisible()
  await page.getByRole("button", { name: "确认这个 gap" }).click()
  const confirmCall = requests.find(r => r.url.endsWith("/gap-candidates/gap-1/confirm"))
  expect(confirmCall?.body).toMatchObject({ user_reason: "人审确认", expected_sequence: 1 })
  await expect(page.getByText("已确认 gap")).toBeVisible()

  // 反证桥接:已确认 gap → 预填草稿 → 署名才固化 vacancy claim 并开审查轮
  await page.getByRole("button", { name: "对这个 gap 发起反证" }).click()
  expect(requests.some(r => r.url.endsWith("/claims"))).toBe(false)
  await expect(page.getByLabel("反证用 claim(空缺断言)")).toHaveValue(/没有覆盖间隔练习在真实课堂的长期保持/)
  await page.getByRole("button", { name: "署名固化为 claim 并开审查轮" }).click()
  await expect(page).toHaveURL(/\/review-rounds\/r-1$/)
  expect(requests.find(r => r.url.endsWith("/workspaces/w-1/claims"))?.body).toMatchObject({ kind: "vacancy" })
})
