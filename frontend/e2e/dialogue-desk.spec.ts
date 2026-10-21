import { expect, test, type Page, type Route } from "@playwright/test"
import type { components } from "../src/features/research-universe/api.gen"

// mock 响应体用后端 OpenAPI 生成类型标注:字段漂移 → tsc 红
type S = components["schemas"]

/**
 * 问题工作区旅程页(六阶段竖排,原文献探讨会话)的真实浏览器冒烟。
 * 全部 /api/v2/** 走 mock,不碰真后端;断言一律用 toBeVisible(),确保元素真的在布局里可见,
 * 而不是只存在于 DOM(jsdom 的 getByText 只证明后者)。
 */

const baseDesk = {
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

const candidates: S["DialogueCandidate"][] = [
  { material_id: "m1", locator: "arxiv:2401.00009", title: "RLHF reasoning paper", reason: "直接相关", source: "corpus", excerpt: "", stance: "认为 RLHF 通过偏好对齐提升指令遵循。", relation: { kind: "supports", note: "支撑对齐→推理改善的路径。" } },
  { material_id: "m2", locator: "arxiv:2402.00001", title: "Reasoning evaluation", reason: "相关评测", source: "corpus", excerpt: "", stance: "评测了推理链的稳定性。", relation: { kind: "partial", note: "部分支撑:仅限评测面。" } },
  { material_id: "m3", locator: "arxiv:2402.00002", title: "Preference alignment", reason: "对齐机制", source: "corpus", excerpt: "", stance: "讨论对齐偏好分布。", relation: { kind: "background", note: "背景相关。" } },
]

interface Call { url: string; method: string; body: Record<string, unknown> | undefined }

const pendingChallenge = { id: "ch-1", review_round_id: "r1", claim_id: "c1", attack_surface: "替代解释未排除", why_it_matters: "w", self_check_method: "s", status: "pending" }
const reviewRound = (claimText: string) => ({ id: "r1", workspace_id: "w-1", question_snapshot: baseDesk.question, claim_snapshot: { id: "c1", text: claimText }, sequence: 1, verdict: null, challenges: [{ ...pendingChallenge, sequence: 1, answers: [] }], ledger: { answered: [], deferred: [], pending: [pendingChallenge], brought_unconfirmed: [] }, rounds: [], evidence_candidates: [], confirmed_facts: [] })

/** 装配全套 mock 路由,并把每个请求记进 calls 供回归断言。投影有状态:claim、审查轮、gap 写入后读得回(阶段由投影推导)。 */
async function mockJourney(page: Page, calls: Call[]) {
  let desk: Record<string, unknown> = { ...baseDesk }
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
    if (url.endsWith("/dialogue/orientation")) return json({ hypotheses: ["RLHF 通过偏好对齐减少分布外漂移从而提升推理", "推理提升来自训练数据的分布而非对齐"], keywords: ["RLHF reasoning", "偏好对齐"] } satisfies S["OrientationResponse"])
    if (url.endsWith("/dialogue/literature-search")) return json({ suggested_query: "LLM free-text suggestion", executed_queries: ["RLHF reasoning"], candidates } satisfies S["LiteratureSearchResponse"])
    if (url.endsWith("/dialogue/landscape-summary")) return json({ text: "## 这几篇覆盖了什么\nRLHF 评测覆盖了指令遵循与对齐。\n## 还没有被覆盖的\n推理链上的真实应用表现未被覆盖。" } satisfies S["DraftTextResponse"])
    if (url.endsWith("/claims") && method === "POST") { desk = { ...desk, claims: [{ id: "c1", text: body?.text }] }; return json({ result: { claim_id: "c1" } }) }
    if (url.endsWith("/review-rounds") && method === "POST") { desk = { ...desk, review_rounds: [{ id: "r1", claim_id: "c1", claim_snapshot: { text: (desk.claims as { text: string }[])[0].text }, question_snapshot: baseDesk.question, verdict: null }], pending_challenges: [pendingChallenge] }; return json({ result: { review_round_id: "r1" } }) }
    if (url === "/api/v2/review-rounds/r1" && method === "GET") return json(reviewRound((desk.claims as { text: string }[])[0].text))
    if (url.endsWith("/literature-challenges")) return json({ result: { challenge_id: "ch-lit" } })
    if (url.endsWith("/dialogue/gap-draft")) return json({ coverage_statement: "文献覆盖了评测方法,但没有覆盖推理链真实应用的长期表现。", counterexample_invitation: "如有推理任务上的 RLHF 长期数据请指正。" } satisfies S["GapDraftResponse"])
    if (url.endsWith("/gap-candidates") && method === "POST") return json({ result: { gap_candidate_id: "g1" } })
    if (url.endsWith("/gap-candidates/g1/confirm")) {
      desk = { ...desk, landscape: { workspace_id: "w-1", question: baseDesk.question, alive_claims: [], claim_verdicts: {}, confirmed_facts: [], gaps: [{ id: "g1", workspace_id: "w-1", coverage_statement: "文献覆盖了评测方法,但没有覆盖推理链真实应用的长期表现。", search_record: { query: "RLHF reasoning", scope: "active", matched_locators: [] }, counterexample_invitation: "如有推理任务上的 RLHF 长期数据请指正。", status: "confirmed" }] } }
      return json({ result: { gap_candidate_id: "g1" } })
    }
    if (url.endsWith("/dialogue/related-work-draft")) return json({ text: "Existing work covers RLHF evaluations [arxiv:2401.00009] while the real-task gap stays open." } satisfies S["DraftTextResponse"])
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
  await expect(page.getByLabel("会话阶段").getByText("Reasoning evaluation")).toBeVisible() // 左栏「已选文献」也列着它
  await expect(page.getByRole("button", { name: /梳理这几篇覆盖了什么 →/ })).toBeVisible()
  await page.getByRole("button", { name: /梳理这几篇覆盖了什么 →/ }).click()
}

test("walks the six-stage workspace journey with real layout assertions", async ({ page }) => {
  const calls: Call[] = []
  await mockJourney(page, calls)

  await page.goto("/workspaces/w-1")
  await expect(page.getByRole("heading", { name: "Why does RLHF improve reasoning?" })).toBeVisible()
  await expect(page.getByRole("list", { name: "会话阶段" })).toBeVisible()
  // 页头只留位置按钮;工具区默认折叠
  await expect(page.getByRole("button", { name: "暂停", exact: true })).toBeVisible()
  await expect(page.getByLabel("探索稿")).toBeHidden()
  // 六个阶段都在左栏,当前阶段卡展开
  await expect(page.getByRole("heading", { name: "1. 出发点" })).toBeVisible()
  await expect(page.getByRole("button", { name: /^结晶/ })).toBeVisible()

  // ── 第 1 步 ──
  await stage1(page)
  await expect(page.getByRole("button", { name: /^出发点 候选假设 2 条 · 2 个检索词/ })).toBeVisible()

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

  // ── 第 4 步:对抗(claim 固化 + 开审查轮 → 同页右侧面打开这一轮 → 在右侧面用所选文献发难)──
  await expect(page.getByRole("heading", { name: "4. 对抗" })).toBeVisible({ timeout: 8000 })
  await expect(page).toHaveURL(/\/workspaces\/w-1\/rounds\/r1$/)
  await expect(page.getByRole("button", { name: /对齐偏好分布才是推理提升的主因。.*审查轮 01.*待回应 1 条/ })).toBeVisible()
  await expect(page.getByText("尚无裁决")).toBeVisible()
  const panel = page.getByRole("complementary", { name: "聚焦面" })
  await expect(panel.locator("blockquote")).toHaveText("对齐偏好分布才是推理提升的主因。")
  await expect(panel.getByText("替代解释未排除")).toBeVisible()
  // 两栏:审查面在左栏右边,左栏不被挤掉
  const [left, right] = [await page.getByRole("list", { name: "会话阶段" }).boundingBox(), await panel.boundingBox()]
  expect(right!.x).toBeGreaterThanOrEqual(left!.x + left!.width)
  await panel.getByRole("button", { name: "用所选文献发难" }).click()
  await expect.poll(() => of(calls, "/literature-challenges").length).toBe(1)
  const challenge = of(calls, "/literature-challenges")[0]
  expect(challenge.url).toBe("/api/v2/review-rounds/r1/literature-challenges")
  expect(challenge.body?.material_ids).toEqual(["m1", "m2", "m3"])

  await page.getByRole("button", { name: "继续到 gap" }).click()

  // ── 第 5 步:gap 起草 → 署名提交确认(仍有待回应挑战:当前阶段仍是对抗,gap 卡照样能做,不锁)──
  await expect(page.getByRole("heading", { name: "5. gap" })).toBeVisible()
  await expect(page.getByRole("button", { name: /^对抗 待回应 1 条/ })).toBeVisible()
  await page.getByRole("button", { name: "让 Cui 起草 gap 候选" }).click()
  const coverage = page.getByLabel(/覆盖范围声明/)
  await expect(coverage).toBeVisible({ timeout: 8000 })
  await expect(coverage).toHaveValue(/没有覆盖推理链真实应用的长期表现/)
  await page.getByRole("button", { name: /提交并确认这个 gap/ }).click()
  // 确认后落到第 6 步(原会话页同样在 gap 确认后进入末步)
  await expect(page.getByRole("heading", { name: "6. 结晶" })).toBeVisible({ timeout: 8000 })
  const propose = of(calls, "/gap-candidates")[0]
  expect(propose.body?.matched_locators).toEqual(["arxiv:2401.00009", "arxiv:2402.00001", "arxiv:2402.00002"])
  expect(propose.body?.search_query).toBe("RLHF reasoning")
  expect(of(calls, "/gap-candidates/g1/confirm")[0].body?.user_reason).toBe("人审确认")

  // ── 第 6 步:结晶(原页头的位置动作 + related-work 草稿)──
  await expect(page.getByRole("button", { name: /^gap ✓ gap 已确认 ×1/ })).toBeVisible()
  await expect(page.getByRole("button", { name: "确认这次探索的位置" })).toBeVisible()
  await page.getByRole("button", { name: /生成 related-work 综述草稿/ }).click()
  await expect(page.getByText(/Existing work covers RLHF evaluations/)).toBeVisible({ timeout: 8000 })
  const related = of(calls, "/dialogue/related-work-draft")[0]
  expect(related.body?.gap_ids).toEqual(["g1"])
  expect(related.body?.material_ids).toEqual(["m1", "m2", "m3"])
  await expect(page.getByRole("button", { name: "下载 .md" })).toBeVisible()
  await expect(page.getByText(/会话走完/)).toBeVisible()

  // 已完成阶段折叠成行,点开能回看、再收起回到当前阶段(仍有待回应 → 对抗)
  await page.getByRole("button", { name: /^出发点 候选假设 2 条/ }).click()
  await expect(page.getByText("回看/修改中 · 内容会接续到后续步骤")).toBeVisible()
  await expect(page.getByLabel(/候选假设/)).toHaveValue(/我自己的假设:对齐提升推理/)
  await page.getByRole("button", { name: "收起,回到第 4 步" }).click()
  await expect(page.getByRole("heading", { name: "4. 对抗" })).toBeVisible()
})

test("narrow screens collapse the stage rows into a top strip", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockJourney(page, [])
  await page.goto("/workspaces/w-1")
  const strip = page.getByRole("navigation", { name: "阶段条" })
  await expect(strip).toBeVisible()
  await expect(page.getByRole("button", { name: /^结晶/ })).toBeHidden()
  await strip.getByRole("button", { name: /结晶/ }).click()
  await expect(page.getByRole("heading", { name: "6. 结晶" })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test("narrow screens stack the review panel below the journey, and the copy says 下方", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const desk = { ...baseDesk, claims: [{ id: "c1", text: "窄屏上的 claim" }], review_rounds: [{ id: "r1", claim_id: "c1", claim_snapshot: { text: "窄屏上的 claim" }, question_snapshot: baseDesk.question, verdict: null }], pending_challenges: [pendingChallenge] }
  await page.route("**/api/v2/**", async (route: Route) => {
    const url = new URL(route.request().url()).pathname
    const json = (value: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value) })
    if (url === "/api/v2/workspaces/w-1") return json(desk)
    if (url === "/api/v2/review-rounds/r1") return json(reviewRound("窄屏上的 claim"))
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: url }) })
  })
  await page.goto("/workspaces/w-1/rounds/r1")
  await expect(page.getByText("下方", { exact: true })).toBeVisible()
  await expect(page.getByText("右侧", { exact: true })).toBeHidden()
  const panel = page.getByRole("complementary", { name: "聚焦面" })
  await expect(panel.getByText("替代解释未排除")).toBeVisible()
  const [card, box] = [await page.getByRole("button", { name: /窄屏上的 claim/ }).boundingBox(), await panel.boundingBox()]
  expect(box!.y).toBeGreaterThan(card!.y + card!.height)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test("leave and re-enter restores the session at the same stage with keywords kept", async ({ page }) => {
  const calls: Call[] = []
  await mockJourney(page, calls)

  await page.goto("/workspaces/w-1")
  await expect(page.getByRole("heading", { name: "Why does RLHF improve reasoning?" })).toBeVisible()
  // 全新会话:没有恢复横幅
  await expect(page.getByRole("status")).toHaveCount(0)

  await stage1(page)
  await stage2(page, calls)

  // ── 离开 → 旧的文献探讨入口地址重新进入(重定向回旅程页)──
  await expect(page.getByRole("heading", { name: "3. 覆盖与 claim" })).toBeVisible({ timeout: 8000 })
  await page.goto("/")

  // ── 重新进入 → 恢复横幅 + 停在第 3 步 + 上游内容保留 ──
  const searchesBeforeReentry = of(calls, "/dialogue/literature-search").length
  await page.goto("/workspaces/w-1/dialogue")
  await expect(page).toHaveURL(/\/workspaces\/w-1$/)
  const resume = page.getByRole("status")
  await expect(resume).toBeVisible()
  await expect(resume).toHaveText(/已恢复上次会话:当前在第 3 步/)
  await expect(page.getByRole("heading", { name: "3. 覆盖与 claim" })).toBeVisible()
  await expect(page.getByText(/还没有被覆盖的/)).toBeVisible()
  // 展开第 2 步回看:检索词与候选都还在
  await page.getByRole("button", { name: /^选料/ }).click()
  await expect(page.getByLabel(/检索词\(用分号/)).toHaveValue("RLHF reasoning; 偏好对齐")
  await expect(page.getByRole("button", { name: /✓ RLHF reasoning/ })).toBeVisible()
  await expect(page.getByLabel("会话阶段").getByText("Reasoning evaluation")).toBeVisible() // 左栏「已选文献」也列着它
  // 重进不重跑检索,恢复出来的选中文献保留(#2)
  await expect(page.getByText(/已选 3 篇/)).toBeVisible()
  await page.waitForTimeout(800) // 越过 500ms 防抖窗口,确认没有迟到的检索
  expect(of(calls, "/dialogue/literature-search").length).toBe(searchesBeforeReentry)
})
