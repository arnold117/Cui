import { expect, test, type Page } from "@playwright/test"

const question = { version_id: "q-1", text: "Why does practice change recall?" }
const gapText = "Studies cover immediate recall in the lab, not retention a semester later."
const desk = (overrides: Record<string, unknown> = {}) => ({
  id: "w-1",
  question,
  sequence: 9,
  note: { id: "n-1", note_id: "n-1", revision_id: "nr-1", text: "Repeated recall may alter later access.", sequence: 9 },
  note_revisions: [], anchors: [], materials: [],
  claims: [{ id: "c-1", text: "Retrieval practice strengthens later access." }],
  review_rounds: [{ id: "r-1", claim_id: "c-1", claim_snapshot: { text: "Retrieval practice strengthens later access." }, question_snapshot: question, verdict: { round_id: "r-1", verdict_type: "survived", user_reason: "ok" } }],
  pending_challenges: [],
  landscape: { workspace_id: "w-1", question, alive_claims: [], claim_verdicts: {}, confirmed_facts: [], gaps: [{ id: "g-1", workspace_id: "w-1", coverage_statement: gapText, search_record: { query: "retrieval practice", scope: "active", matched_locators: [] }, counterexample_invitation: "i", status: "confirmed" }] },
  user_position: "exploring", conclusion: null, direction_links: [], confirmed_facts: [],
  ...overrides,
})
const conclusionText = "Repeated recall strengthens later access."
const existing = { id: "d-1", proposition: "A long-term thesis about memory.", status: "active", crystallizations: [], crystallizations_count: 0, attached_workspaces_count: 0 }

/** 有状态的 mock:结论写入后工作区投影读得回;结晶命令写入后首页投影读得回新方向与结晶。 */
async function mockServer(page: Page) {
  const requests: { url: string; method: string; body?: Record<string, unknown> }[] = []
  let currentDesk = desk()
  let home = { universe_id: "u-1", workspaces: [], pending_facts: [], directions: [existing] as Record<string, unknown>[] }
  await page.route("**/api/v2/**", async route => {
    const req = route.request(), url = new URL(req.url()).pathname, method = req.method(), body = req.postDataJSON?.() as Record<string, unknown> | undefined
    requests.push({ url, method, body })
    const json = (value: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value) })
    if (url === "/api/v2/universes/active") return json({ id: "u-1" })
    if (url === "/api/v2/universes/u-1/home") return json(home)
    if (url === "/api/v2/workspaces/w-1" && method === "GET") return json(currentDesk)
    if (url === "/api/v2/workspaces/w-1/conclusions" && method === "POST") {
      currentDesk = { ...currentDesk, user_position: "concluded", conclusion: { id: "conc-1", type: body?.conclusion_type, text: body?.conclusion_text, reason: body?.user_reason, basis_refs: [], revival_condition: null }, sequence: 10 }
      return json({ commit_position: 1, event_ids: ["e1"], result: { workspace_id: "w-1", conclusion_id: "conc-1" } })
    }
    if (url === "/api/v2/workspaces/w-1/crystallize-into-direction" && method === "POST") {
      const id = (body?.direction_id as string | null) ?? "d-new"
      const crystal = { crystallization_id: "x-1", direction_id: id, workspace_id: "w-1", conclusion_id: "conc-1", conclusion_text: conclusionText, conclusion_type: "tentative_answer" }
      const direction = { id, proposition: (body?.new_proposition as string | null) ?? existing.proposition, status: "active", crystallizations: [crystal], crystallizations_count: 1, attached_workspaces_count: 1 }
      home = { ...home, directions: [...home.directions.filter(d => d.id !== id), direction] }
      return json({ commit_position: 2, event_ids: ["e2", "e3", "e4"], result: { direction_id: id, direction_link_id: "l-1", crystallization_id: "x-1", workspace_id: "w-1" } })
    }
    return route.fulfill({ status: 404, body: JSON.stringify({ detail: url }) })
  })
  return requests
}

/** 结晶卡:6 类结论 + 理由 → 确认这次探索的位置;同一张卡接着问去向。账本在右侧。 */
async function confirmPosition(page: Page) {
  await page.goto("/workspaces/w-1")
  await expect(page.getByRole("heading", { name: "6. 结晶" })).toBeVisible()
  const panel = page.getByRole("complementary", { name: "聚焦面" })
  await expect(panel.getByRole("heading", { name: "这次结论的依据" })).toBeVisible()
  await expect(panel.getByText(gapText)).toBeVisible()
  await page.getByRole("radio", { name: /暂时回答/ }).check()
  await page.getByLabel("结论", { exact: true }).fill(conclusionText)
  await page.getByLabel("理由", { exact: true }).fill("The claim survived its review round.")
  await page.getByRole("button", { name: "确认这次探索的位置" }).click()
  await expect(page.getByRole("group", { name: "这次结论去哪" })).toBeVisible()
}

test("a new direction from a gap: the conclusion becomes its crystallization and home reads both back", async ({ page }) => {
  const requests = await mockServer(page)
  await confirmPosition(page)
  await page.getByRole("radio", { name: "从 gap 新建方向" }).check()
  await expect(page.getByLabel("方向命题")).toHaveValue(gapText)
  const create = page.getByRole("button", { name: "新建方向并结晶" })
  await expect(create).toBeDisabled()
  await page.getByRole("button", { name: "签名：这是我的方向命题" }).click()
  await create.click()
  await expect(page.getByText(`已结晶到方向「${gapText}」`)).toBeVisible()
  const conclude = requests.find(x => x.url.endsWith("/conclusions") && x.method === "POST")
  expect(conclude?.body).toMatchObject({ conclusion_type: "tentative_answer", user_reason: "The claim survived its review round.", expected_sequence: 9 })
  const crystallize = requests.filter(x => x.url.endsWith("/crystallize-into-direction") && x.method === "POST")
  expect(crystallize).toHaveLength(1)
  expect(crystallize[0].body).toMatchObject({ conclusion_id: "conc-1", direction_id: null, new_proposition: gapText, expected_sequence: 0 })
  // 首页方向地形读回新方向与这条结晶
  await page.goto("/")
  await expect(page.getByRole("link", { name: new RegExp(gapText.slice(0, 20)) })).toHaveAttribute("href", "/directions/d-new")
  await expect(page.getByText(`最近结晶：${conclusionText}`)).toBeVisible()
})

test("attach to an existing direction from the dropdown", async ({ page }) => {
  const requests = await mockServer(page)
  await confirmPosition(page)
  await page.getByRole("radio", { name: "挂到已有方向" }).check()
  await page.getByRole("combobox", { name: "已有方向" }).selectOption("d-1")
  await page.getByRole("button", { name: "挂到这个方向" }).click()
  await expect(page.getByText("已结晶到方向「A long-term thesis about memory.」")).toBeVisible()
  expect(requests.find(x => x.url.endsWith("/crystallize-into-direction"))?.body).toMatchObject({ conclusion_id: "conc-1", direction_id: "d-1", new_proposition: null })
  await page.goto("/")
  await expect(page.getByRole("link", { name: /A long-term thesis about memory/ })).toHaveAttribute("href", "/directions/d-1")
  await expect(page.getByText(`最近结晶：${conclusionText}`)).toBeVisible()
})
