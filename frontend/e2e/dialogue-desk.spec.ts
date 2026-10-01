import { expect, test, type Page, type Route } from "@playwright/test"

/**
 * 文献探讨(六步分阶段会话页)的真实浏览器冒烟。
 * 全部 /api/v2/** 走 mock,不碰真后端;断言一律用 toBeVisible(),确保元素真的在布局里可见,
 * 而不是只存在于 DOM(jsdom 的 getByText 只证明后者)。
 */

const desk = {
  id: "w-1",
  question: { version_id: "q-1", text: "Why does RLHF improve reasoning?" },
  sequence: 0,
  note: null,
  note_revisions: [],
  anchors: [],
  claims: [],
  review_rounds: [],
  pending_challenges: [],
}

const candidates = [
  { material_id: "m1", locator: "arxiv:2401.00009", title: "RLHF reasoning paper", reason: "直接相关", source: "corpus", stance: "认为 RLHF 通过偏好对齐提升指令遵循。", relation: { kind: "supports", note: "支撑对齐→推理改善的路径。" } },
  { material_id: "m2", locator: "arxiv:2402.00001", title: "Reasoning evaluation", reason: "相关评测", source: "corpus", stance: "评测了推理链的稳定性。", relation: { kind: "partial", note: "部分支撑:仅限评测面。" } },
  { material_id: "m3", locator: "arxiv:2402.00002", title: "Preference alignment", reason: "对齐机制", source: "corpus", stance: "讨论对齐偏好分布。", relation: { kind: "background", note: "背景相关。" } },
]

interface Call { url: string; method: string; body: Record<string, unknown> | undefined }

/** 装配全套 mock 路由,并把每个请求记进 calls 供回归断言。 */
async function mockJourney(page: Page, calls: Call[]) {
  await page.route("**/api/v2/**", async (route: Route) => {
    const req = route.request()
    const url = new URL(req.url()).pathname
    const method = req.method()
    let body: Record<string, unknown> | undefined
    try { body = req.postDataJSON() as Record<string, unknown> } catch { body = undefined }
    calls.push({ url, method, body })
    const json = (value: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value) })

    if (url === "/api/v2/universes/active" && method === "GET") return json({ id: "u-1" })
    if (url === "/api/v2/workspaces/w-1" && method === "GET") return json(desk)
    if (url.endsWith("/dialogue/orientation")) return json({ hypotheses: ["RLHF 通过偏好对齐减少分布外漂移从而提升推理", "推理提升来自训练数据的分布而非对齐"], keywords: ["RLHF reasoning", "偏好对齐"] })
    if (url.endsWith("/dialogue/literature-search")) return json({ query: "RLHF reasoning", candidates })
    if (url.endsWith("/dialogue/landscape-summary")) return json({ text: "## 这几篇覆盖了什么\nRLHF 评测覆盖了指令遵循与对齐。\n## 还没有被覆盖的\n推理链上的真实应用表现未被覆盖。" })
    if (url.endsWith("/claims") && method === "POST") return json({ result: { claim_id: "c1" } })
    if (url.endsWith("/review-rounds") && method === "POST") return json({ result: { review_round_id: "r1" } })
    if (url.endsWith("/literature-challenges")) return json({ result: { challenge_id: "ch-lit" } })
    if (url.endsWith("/dialogue/gap-draft")) return json({ coverage_statement: "文献覆盖了评测方法,但没有覆盖推理链真实应用的长期表现。", search_query: "rlhf reasoning", counterexample_invitation: "如有推理任务上的 RLHF 长期数据请指正。" })
    if (url.endsWith("/gap-candidates") && method === "POST") return json({ result: { gap_candidate_id: "g1" } })
    if (url.endsWith("/gap-candidates/g1/confirm")) return json({ result: { gap_candidate_id: "g1" } })
    if (url.endsWith("/dialogue/related-work-draft")) return json({ text: "Existing work covers RLHF evaluations [arxiv:2401.00009] while the real-task gap stays open." })
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: url }) })
  })
}

const of = (calls: Call[], suffix: string) => calls.filter(c => c.url.endsWith(suffix))

/** 第 1 步:起草假设 → 改写 → 确认(不自动前进,点确认才进第 2 步)。 */
async function stage1(page: Page) {
  await page.getByRole("button", { name: "让 Cui 起草候选假设与关键词" }).click()
  const hypotheses = page.getByLabel(/候选假设/)
  await expect(hypotheses).toBeVisible()
  await expect(hypotheses).toHaveValue(/RLHF 通过偏好对齐减少分布外漂移/, { timeout: 5000 })
  await hypotheses.fill("我自己的假设:对齐提升推理。\n质疑:也可能只是数据重复。")
  await page.getByRole("button", { name: "就用这版假设,去选料 →" }).click()
  // 第 2 步单卡真的顶上来(而不是只有 DOM 里多了个节点)
  await expect(page.getByRole("heading", { name: "2. 选料" })).toBeVisible()
}

/** 第 2 步:勾一个检索词(合并检索哨兵)→ 选 3 篇 → 覆盖梳理。 */
async function stage2(page: Page, calls: Call[]) {
  await expect(page.getByLabel(/检索词\(用分号/)).toHaveValue("RLHF reasoning; 偏好对齐")
  await page.getByRole("button", { name: "RLHF reasoning", exact: true }).click()
  // 勾选一次 = 恰好一次合并检索(500ms 防抖后)
  await expect.poll(() => of(calls, "/dialogue/literature-search").length, { timeout: 8000 }).toBe(1)
  const search = of(calls, "/dialogue/literature-search")[0]
  expect(search.body?.query).toBe("RLHF reasoning")
  expect(search.body?.question).toBe("Why does RLHF improve reasoning?")

  await expect(page.getByText(/观点:认为 RLHF 通过偏好对齐提升指令遵循/)).toBeVisible({ timeout: 8000 })
  await expect(page.getByText(/支撑对齐→推理改善的路径/)).toBeVisible()
  for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "选入", exact: true }).first().click()
  await expect(page.getByText(/已选 3 篇/)).toBeVisible()
  // 真实布局下的卡片与按钮真的可见(jsdom 只保证在树里)
  await expect(page.getByText("Reasoning evaluation")).toBeVisible()
  await expect(page.getByRole("button", { name: /梳理这几篇覆盖了什么 →/ })).toBeVisible()
  await page.getByRole("button", { name: /梳理这几篇覆盖了什么 →/ }).click()
}

test("walks the six-stage dialogue journey with real layout assertions", async ({ page }) => {
  const calls: Call[] = []
  await mockJourney(page, calls)

  await page.goto("/workspaces/w-1/dialogue")
  await expect(page.getByRole("heading", { name: "Why does RLHF improve reasoning?" })).toBeVisible()
  await expect(page.getByRole("list", { name: "会话阶段" })).toBeVisible()
  await expect(page.getByText("文献探讨 · 与 Cui 一起读文献")).toBeVisible()

  // ── 第 1 步 ──
  await stage1(page)
  await expect(page.getByRole("button", { name: /1\. 出发点 候选假设 2 条 · 2 个检索词/ })).toBeVisible()

  // ── 第 2 步 ──
  await stage2(page, calls)

  // ── 第 3 步:覆盖梳理 → 骨架 → 写实 → 固化 claim ──
  await expect(page.getByRole("heading", { name: "3. 覆盖与 claim" })).toBeVisible({ timeout: 8000 })
  await expect(page.getByText(/还没有被覆盖的/)).toBeVisible()
  await page.getByRole("button", { name: "分歧断言" }).click()
  const claim = page.getByLabel("由你写下的 claim")
  await expect(claim).toHaveValue(/分成两派/)
  await claim.fill("对齐偏好分布才是推理提升的主因。")
  await page.getByRole("button", { name: /固化 claim 并开审查轮/ }).click()

  // ── 第 4 步:对抗(claim 固化 + 开审查轮 → 文献发难)──
  await expect(page.getByRole("heading", { name: "4. 对抗" })).toBeVisible({ timeout: 8000 })
  await expect(page.getByText(/✓ claim 已固化,审查轮已开/)).toBeVisible()
  await expect(page.getByRole("button", { name: /去审查轮完整应答与裁决 →/ })).toBeVisible()
  await page.getByRole("button", { name: /用所选文献发难/ }).click()
  await expect(page.getByRole("status")).toHaveText(/已追加一条文献挑战/)
  const challenge = of(calls, "/literature-challenges")[0]
  expect(challenge.url).toBe("/api/v2/review-rounds/r1/literature-challenges")
  expect(challenge.body?.material_ids).toEqual(["m1", "m2", "m3"])

  await page.getByRole("button", { name: /我看过审查轮了,继续起草 gap →/ }).click()

  // ── 第 5 步:gap 起草 → 署名提交确认 ──
  await expect(page.getByRole("heading", { name: "5. gap" })).toBeVisible()
  await page.getByRole("button", { name: "让 Cui 起草 gap 候选" }).click()
  const coverage = page.getByLabel(/覆盖范围声明/)
  await expect(coverage).toBeVisible({ timeout: 8000 })
  await expect(coverage).toHaveValue(/没有覆盖推理链真实应用的长期表现/)
  await page.getByRole("button", { name: /提交并确认这个 gap/ }).click()
  await expect(page.getByText(/✓ gap 已确认 ×1/)).toBeVisible({ timeout: 8000 })
  const propose = of(calls, "/gap-candidates")[0]
  expect(propose.body?.matched_locators).toEqual(["arxiv:2401.00009", "arxiv:2402.00001", "arxiv:2402.00002"])
  expect(propose.body?.search_query).toBe("rlhf reasoning")
  expect(of(calls, "/gap-candidates/g1/confirm")[0].body?.user_reason).toBe("人审确认")

  // ── 第 6 步:related-work 草稿 ──
  await expect(page.getByRole("heading", { name: "6. 收尾" })).toBeVisible({ timeout: 8000 })
  await page.getByRole("button", { name: /生成 related-work 综述草稿/ }).click()
  await expect(page.getByText(/Existing work covers RLHF evaluations/)).toBeVisible({ timeout: 8000 })
  const related = of(calls, "/dialogue/related-work-draft")[0]
  expect(related.body?.gap_ids).toEqual(["g1"])
  expect(related.body?.material_ids).toEqual(["m1", "m2", "m3"])
  await expect(page.getByRole("button", { name: "下载 .md" })).toBeVisible()
  await expect(page.getByText(/会话走完/)).toBeVisible()

  // 已完成步骤折叠成行,点阶段条能展开回看、再收起
  await expect(page.getByRole("button", { name: /1\. 出发点 候选假设 2 条/ })).toBeVisible()
  await page.getByRole("button", { name: "✓ 出发点" }).click()
  await expect(page.getByText("回看/修改中 · 内容会接续到后续步骤")).toBeVisible()
  await expect(page.getByLabel(/候选假设/)).toHaveValue(/我自己的假设:对齐提升推理/)
  await page.getByRole("button", { name: "收起,回到第 6 步" }).click()
  await expect(page.getByRole("heading", { name: "6. 收尾" })).toBeVisible()
})

test("exit and re-enter restores the session at the same stage with keywords kept", async ({ page }) => {
  const calls: Call[] = []
  await mockJourney(page, calls)

  await page.goto("/workspaces/w-1/dialogue")
  await expect(page.getByRole("heading", { name: "Why does RLHF improve reasoning?" })).toBeVisible()
  // 全新会话:没有恢复横幅
  await expect(page.getByRole("status")).toHaveCount(0)

  await stage1(page)
  await stage2(page, calls)

  // ── 退出会话 → 回工作区 ──
  await expect(page.getByRole("heading", { name: "3. 覆盖与 claim" })).toBeVisible({ timeout: 8000 })
  await page.getByRole("button", { name: "退出会话" }).click()
  await expect(page).toHaveURL(/\/workspaces\/w-1$/)
  await expect(page.getByText("Why does RLHF improve reasoning?").first()).toBeVisible()

  // ── 重新进入 → 恢复横幅 + 停在第 3 步 + 上游内容保留 ──
  const searchesBeforeReentry = of(calls, "/dialogue/literature-search").length
  await page.goto("/workspaces/w-1/dialogue")
  const resume = page.getByRole("status")
  await expect(resume).toBeVisible()
  await expect(resume).toHaveText(/已恢复上次会话:当前在第 3 步/)
  await expect(page.getByRole("heading", { name: "3. 覆盖与 claim" })).toBeVisible()
  await expect(page.getByText(/还没有被覆盖的/)).toBeVisible()
  // 展开第 2 步回看:检索词与候选都还在
  await page.getByRole("button", { name: "✓ 选料" }).click()
  await expect(page.getByLabel(/检索词\(用分号/)).toHaveValue("RLHF reasoning; 偏好对齐")
  await expect(page.getByRole("button", { name: /✓ RLHF reasoning/ })).toBeVisible()
  await expect(page.getByText("Reasoning evaluation")).toBeVisible()
  // 重进不重跑检索,恢复出来的选中文献保留(#2)
  await expect(page.getByText(/已选 3 篇/)).toBeVisible()
  await page.waitForTimeout(800) // 越过 500ms 防抖窗口,确认没有迟到的检索
  expect(of(calls, "/dialogue/literature-search").length).toBe(searchesBeforeReentry)
})
