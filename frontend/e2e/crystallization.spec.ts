import { expect, test } from "@playwright/test"

const desk = (overrides: Record<string, unknown> = {}) => ({
  id: "w-1",
  question: { version_id: "q-1", text: "Why does practice change recall?" },
  sequence: 9,
  note: { id: "n-1", note_id: "n-1", revision_id: "nr-1", text: "Repeated recall may alter later access.", sequence: 9 },
  note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [], materials: [],
  user_position: "exploring", conclusion: null,
  direction_links: [{ link_id: "l-1", direction_id: "d-1", direction_proposition: "A long-term thesis about memory.", status: "active" }],
  confirmed_facts: [],
  ...overrides,
})

test("conclusion becomes a direction crystallization and home reads it back", async ({ page }) => {
  const requests: { url: string; method: string; body?: Record<string, unknown> }[] = []
  let currentDesk = desk()
  let home = { universe_id: "u-1", workspaces: [], pending_facts: [], directions: [] }
  await page.route("**/api/v2/**", async route => {
    const req = route.request(), url = new URL(req.url()).pathname, method = req.method(), body = req.postDataJSON?.() as Record<string, unknown> | undefined
    requests.push({ url, method, body })
    const json = (value: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value) })
    if (url === "/api/v2/universes/active") return json({ id: "u-1" })
    if (url === "/api/v2/universes/u-1/home") return json(home)
    if (url === "/api/v2/workspaces/w-1" && method === "GET") return json(currentDesk)
    if (url === "/api/v2/workspaces/w-1/conclusions" && method === "POST") {
      currentDesk = { ...currentDesk, user_position: "concluded", conclusion: { id: "conc-1", type: "tentative_answer", text: "Repeated recall strengthens later access.", basis_refs: [], revival_condition: null }, sequence: 10 }
      return json({ commit_position: 1, event_ids: ["e1"], result: { workspace_id: "w-1", conclusion_id: "conc-1" }, fragment: currentDesk })
    }
    if (url === "/api/v2/directions/d-1/crystallizations" && method === "POST") {
      home = { universe_id: "u-1", workspaces: [], pending_facts: [], directions: [{ id: "d-1", proposition: "A long-term thesis about memory.", status: "active", crystallizations: [{ crystallization_id: "x-1", workspace_id: "w-1", conclusion_id: "conc-1", conclusion_text: "Repeated recall strengthens later access.", conclusion_type: "tentative_answer" }], crystallizations_count: 1, attached_workspaces_count: 1 }] }
      return json({ commit_position: 2, event_ids: ["e2"], result: { crystallization_id: "x-1", direction_id: "d-1", workspace_id: "w-1" } })
    }
    return route.fulfill({ status: 404, body: JSON.stringify({ detail: url }) })
  })
  await page.goto("/workspaces/w-1")
  await page.getByRole("button", { name: "确认这次探索的位置" }).click()
  await expect(page.getByRole("heading", { name: "结晶台" })).toBeVisible()
  await page.getByLabel("我的探索结论").fill("Repeated recall strengthens later access.")
  await page.getByRole("radio", { name: /暂时回答/ }).check()
  await page.getByRole("button", { name: "确认结晶" }).click()
  await expect(page.getByRole("heading", { name: "已确认本次探索结论" })).toBeVisible()
  await page.getByRole("radio", { name: /成为方向的一项结晶/ }).check()
  await page.getByRole("button", { name: "确认", exact: true }).click()
  const crystallizeRequest = requests.find(x => x.url.endsWith("/crystallizations") && x.method === "POST")
  expect(crystallizeRequest?.body).toMatchObject({ workspace_id: "w-1", conclusion_id: "conc-1" })
  // home readback now shows the crystallization
  await page.goto("/")
  await expect(page.getByText("最近结晶：Repeated recall strengthens later access.")).toBeVisible()
  await expect(page.getByRole("link", { name: /A long-term thesis about memory/ })).toHaveAttribute("href", "/directions/d-1")
  const concludeRequest = requests.find(x => x.url.endsWith("/conclusions") && x.method === "POST")
  expect(concludeRequest?.body).toMatchObject({ conclusion_type: "tentative_answer", expected_sequence: 9 })
})
