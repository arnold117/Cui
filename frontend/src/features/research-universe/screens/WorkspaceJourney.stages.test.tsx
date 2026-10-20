import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppRouter } from "../../../router"
import { WorkspaceJourney } from "./WorkspaceJourney"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

const baseDesk = { id: "w-1", question: { version_id: "q-1", text: "Why does RLHF improve reasoning?" }, sequence: 0, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [] }
const pendingChallenge = { id: "ch1", review_round_id: "r1", claim_id: "c1", attack_surface: "替代解释未排除", why_it_matters: "w", self_check_method: "s", status: "pending" }
const confirmedGap = (id: string, coverage: string) => ({ id, workspace_id: "w-1", coverage_statement: coverage, search_record: { query: "x", scope: "active", matched_locators: [], searched_at: "2026-09-02" }, counterexample_invitation: "i", status: "confirmed", sequence: 2 })
const landscape = (gaps: unknown[]) => ({ workspace_id: "w-1", question: baseDesk.question, alive_claims: [], claim_verdicts: {}, confirmed_facts: [], gaps })

const candidates = [
  { material_id: "m1", locator: "arxiv:2401.00009", title: "RLHF reasoning paper", reason: "直接相关", source: "corpus", stance: "认为 RLHF 通过偏好对齐提升指令遵循。", relation: { kind: "supports", note: "支撑对齐→推理改善的路径。" } },
  { material_id: "m2", locator: "arxiv:2402.00001", title: "Reasoning evaluation", reason: "相关评测", source: "corpus", stance: "评测了推理链的稳定性。", relation: { kind: "partial", note: "部分支撑:仅限评测面。" } },
  { material_id: "m3", locator: "arxiv:2402.00002", title: "Preference alignment", reason: "对齐机制", source: "corpus", stance: "讨论对齐偏好分布。", relation: { kind: "background", note: "背景相关。" } },
]

/** 后端是有状态的:claim、审查轮、gap 写入后,下一次 GET 工作区投影能读回(阶段由投影推导)。 */
function mockFullJourney(initial: Record<string, unknown> = {}) {
  let desk: Record<string, unknown> = { ...baseDesk, ...initial }
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url)
    const method = init?.method ?? "GET"
    const body = init?.body ? JSON.parse(init.body as string) : {}
    if (/\/api\/v2\/workspaces\/w-\d$/.test(path) && method === "GET") return response(desk)
    if (path.endsWith("/dialogue/orientation")) return response({ hypotheses: ["RLHF 通过偏好对齐减少分布外漂移从而提升推理", "推理提升来自训练数据的分布而非对齐"], keywords: ["RLHF reasoning", "偏好对齐"] })
    if (path.endsWith("/dialogue/literature-search")) return response({ suggested_query: "LLM free-text suggestion", executed_queries: ["RLHF reasoning"], candidates })
    if (path.endsWith("/dialogue/landscape-summary")) return response({ text: "## 这几篇覆盖了什么\nRLHF 评测覆盖了指令遵循与对齐。\n## 还没有被覆盖的\n推理链上的真实应用表现未被覆盖。" })
    if (path.endsWith("/claims")) { desk = { ...desk, claims: [...(desk.claims as unknown[]), { id: "c1", text: body.text }] }; return response({ result: { claim_id: "c1" } }) }
    if (path.endsWith("/review-rounds") && method === "POST") { desk = { ...desk, review_rounds: [{ id: "r1", claim_id: "c1", claim_snapshot: { text: (desk.claims as { text: string }[]).at(-1)!.text }, question_snapshot: baseDesk.question, verdict: null }], pending_challenges: [pendingChallenge] }; return response({ result: { review_round_id: "r1" } }) }
    if (path.endsWith("/literature-challenges")) return response({ result: { challenge_id: "ch-lit" } })
    if (path.endsWith("/dialogue/gap-draft")) return response({ coverage_statement: "文献覆盖了评测方法,但没有覆盖推理链真实应用的长期表现。", counterexample_invitation: "如有推理任务上的 RLHF 长期数据请指正。" })
    if (path.endsWith("/gap-candidates") && method === "POST") return response({ result: { gap_candidate_id: "g1" } })
    if (path.includes("/gap-candidates/g1/confirm")) { desk = { ...desk, landscape: landscape([confirmedGap("g1", "文献覆盖了评测方法,但没有覆盖推理链真实应用的长期表现。")]) }; return response({ result: { gap_candidate_id: "g1" } }) }
    if (path.endsWith("/dialogue/related-work-draft")) return response({ text: "Existing work covers RLHF evaluations [arxiv:2401.00009] while the real-task gap stays open." })
    return response({ detail: path }, 404)
  })
}

function renderJourney(workspaceId: string) {
  return render(<AppRouter><WorkspaceJourney workspaceId={workspaceId} /></AppRouter>)
}
const openCard = () => screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent).find((t) => /^\d\. /.test(t ?? ""))
const row = (name: RegExp) => screen.getByRole("button", { name })

function litSearchCalls() {
  return fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/dialogue/literature-search"))
}

afterEach(() => { cleanup(); window.sessionStorage.clear() })
beforeEach(() => { fetchMock.mockReset(); window.sessionStorage.clear() })

describe("workspace journey stages", () => {
  it("walks the journey: orientation → hypotheses confirm → keyword chip auto-search → picks → coverage → claim → 对抗 → gap → 结晶", async () => {
    mockFullJourney()
    renderJourney("w-1")
    await screen.findByText("Why does RLHF improve reasoning?")
    expect(openCard()).toBe("1. 出发点")

    // 第 1 步:起草假设(不自动离开;确认后才进第 2 步)
    fireEvent.click(screen.getByRole("button", { name: "让 Cui 起草候选假设与关键词" }))
    const textarea = await screen.findByLabelText(/候选假设/)
    await waitFor(() => expect((textarea as HTMLTextAreaElement).value).toContain("RLHF 通过偏好对齐减少分布外漂移"), { timeout: 3000 })
    fireEvent.change(textarea, { target: { value: "我自己的假设:对齐提升推理。\n质疑:也可能只是数据重复。" } })
    fireEvent.click(screen.getByRole("button", { name: "就用这版假设,去选料 →" }))

    // 第 2 步:选料。勾选一个词 → 只发一次合并检索
    await waitFor(() => expect(screen.getByLabelText(/检索词\(用分号/)).toHaveValue("RLHF reasoning; 偏好对齐"), { timeout: 3000 })
    expect(openCard()).toBe("2. 选料")
    fireEvent.click(screen.getByRole("button", { name: "RLHF reasoning" }))
    await waitFor(() => {
      const calls = litSearchCalls()
      expect(calls.length).toBe(1)
      expect(JSON.parse(calls[0][1].body as string).query).toBe("RLHF reasoning")
    }, { timeout: 4000 })

    // 候选卡带观点与关系,选 3 篇
    await waitFor(() => expect(screen.getByText(/观点:认为 RLHF 通过偏好对齐提升指令遵循/)).toBeInTheDocument(), { timeout: 3000 })
    expect(screen.getByText(/支撑对齐→推理改善的路径/)).toBeInTheDocument()
    for (let i = 0; i < 3; i++) fireEvent.click(screen.getAllByRole("button", { name: "选入" })[0])
    await waitFor(() => expect(screen.getByText(/已选 3 篇/)).toBeInTheDocument(), { timeout: 3000 })
    fireEvent.click(screen.getByRole("button", { name: /梳理这几篇覆盖了什么 →/ }))

    // 第 3 步:覆盖与 claim 同卡 —— 读梳理,三选一骨架,用户写实后固化
    await screen.findByText(/还没有被覆盖的/, {}, { timeout: 3000 })
    expect(openCard()).toBe("3. 覆盖与 claim")
    fireEvent.click(screen.getByRole("button", { name: "分歧断言" }))
    const claimInput = screen.getByLabelText("由你写下的 claim")
    await waitFor(() => expect((claimInput as HTMLTextAreaElement).value).toContain("分成两派"), { timeout: 2000 })
    fireEvent.change(claimInput, { target: { value: "对齐偏好分布才是推理提升的主因。" } })
    fireEvent.click(screen.getByRole("button", { name: /固化 claim 并开审查轮/ }))
    await screen.findByText(/✓ claim 已固化,审查轮已开/, {}, { timeout: 3000 })
    expect(openCard()).toBe("4. 对抗")
    await screen.findByText("待回应 1 条") // 研究边缘删了:待回应计数挂在对抗这一格
    expect(JSON.parse(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/claims"))![1].body as string).kind).toBe("division")

    // 文献发难把所选材料带进审查轮
    fireEvent.click(screen.getByRole("button", { name: /用所选文献发难/ }))
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/literature-challenges"))
      expect(call).toBeTruthy()
      expect(JSON.parse(call![1].body as string).material_ids).toEqual(["m1", "m2", "m3"])
    }, { timeout: 3000 })
    // 仍有待回应挑战 → 当前阶段停在对抗,但「继续起草 gap」照样打开 gap 卡(不锁)
    fireEvent.click(screen.getByRole("button", { name: /我看过审查轮了,继续起草 gap →/ }))
    expect(openCard()).toBe("5. gap")
    expect(screen.getByRole("button", { name: "收起,回到第 4 步" })).toBeInTheDocument()

    // 第 5 步:gap 起草 → 署名提交确认
    fireEvent.click(screen.getByRole("button", { name: "让 Cui 起草 gap 候选" }))
    const coverage = await screen.findByLabelText(/覆盖范围声明/)
    expect((coverage as HTMLTextAreaElement).value).toContain("没有覆盖推理链真实应用的长期表现")
    fireEvent.click(screen.getByRole("button", { name: /提交并确认这个 gap/ }))
    await waitFor(() => expect(openCard()).toBe("6. 结晶"), { timeout: 3000 })
    const propose = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/gap-candidates"))
    expect(propose).toBeTruthy()
    expect(JSON.parse(propose![1].body as string).matched_locators).toEqual(["arxiv:2401.00009", "arxiv:2402.00001", "arxiv:2402.00002"])
    expect(JSON.parse(propose![1].body as string).external_refs).toEqual([])  // 全是语料库内文献,无外部快照
    expect(JSON.parse(propose![1].body as string).search_query).toBe("RLHF reasoning")  // 实际执行的检索,不是 LLM 建议词

    // 第 6 步:结晶卡里有原页头的位置动作,也有 related-work 草稿
    expect(screen.getByRole("button", { name: "确认这次探索的位置" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /生成 related-work 综述草稿/ }))
    await screen.findByText(/Existing work covers RLHF evaluations/, {}, { timeout: 3000 })
    fireEvent.click(screen.getByRole("button", { name: "下载 .md" }))
    // 已完成的阶段折叠成一行;对抗那行显示待回应计数
    await waitFor(() => expect(row(/^5\. gap/)).toHaveTextContent("gap 已确认 ×1"))
    expect(row(/^4\. 对抗/)).toHaveTextContent("待回应 1 条")
    expect(row(/^1\. 出发点/)).toHaveTextContent("展开修改")
  })

  it("resumes a saved session at its stage; chip toggles fire one merged search and text edits do not; clear restarts", async () => {
    const seed = (extra: Record<string, unknown>) => JSON.stringify({
      v: 2, workspaceId: "w-2", hypothesesText: "恢复出来的假设", hypothesesDone: true,
      keywordsText: "偏好对齐; RLHF reasoning", selectedKeywords: [], candidates: [], selected: [],
      searchQueries: [], claimText: "", claimAck: false, confirmedGapIds: [], ...extra,
    })
    window.sessionStorage.setItem("cui:dialogue-draft:v2:w-2", seed({ savedAt: new Date().toISOString() }))
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const path = String(url)
      if (path.endsWith("/api/v2/workspaces/w-2") && (init?.method ?? "GET") === "GET") return response(baseDesk)
      if (path.endsWith("/dialogue/literature-search")) return response({ suggested_query: "偏好对齐", executed_queries: ["preference alignment"], candidates: [] })
      return response({ detail: path }, 404)
    })
    renderJourney("w-2")
    await screen.findByText("Why does RLHF improve reasoning?")

    // 恢复横幅 + 停在第 2 步
    expect(screen.getByRole("status")).toHaveTextContent(/已恢复上次会话:当前在第 2 步/)
    expect(screen.getByLabelText(/检索词\(用分号/)).toHaveValue("偏好对齐; RLHF reasoning")

    // 勾选词条 → 恰好一次合并检索,query 为勾选词
    fireEvent.click(screen.getByRole("button", { name: "偏好对齐" }))
    await waitFor(() => {
      const calls = litSearchCalls()
      expect(calls.length).toBe(1)
      expect(JSON.parse(calls[0][1].body as string).query).toBe("偏好对齐")
    }, { timeout: 4000 })
    await waitFor(() => expect(screen.getByText(/这次没有候选文献/)).toBeInTheDocument(), { timeout: 3000 })

    // 只编辑词条文字(未改变勾选)→ 不再触发检索
    fireEvent.change(screen.getByLabelText(/检索词\(用分号/), { target: { value: "偏好对齐; 新的检索词" } })
    await new Promise((r) => setTimeout(r, 800))
    expect(litSearchCalls().length).toBe(1)

    // 重新进入(新草稿仍在)→ 恢复;清空重来 → 回到第 1 步
    cleanup()
    window.sessionStorage.setItem("cui:dialogue-draft:v2:w-2", seed({ savedAt: new Date().toISOString() }))
    renderJourney("w-2")
    await screen.findByText("Why does RLHF improve reasoning?", {}, { timeout: 3000 })
    await screen.findByRole("button", { name: /清空并重新开始/ }, { timeout: 3000 })
    fireEvent.click(screen.getByRole("button", { name: /清空并重新开始/ }))
    await screen.findByRole("button", { name: "让 Cui 起草候选假设与关键词" }, { timeout: 3000 })
    const after = JSON.parse(window.sessionStorage.getItem("cui:dialogue-draft:v2:w-2") ?? "{}")
    expect(after.hypothesesDone).toBe(false)
    expect(after.keywordsText).toBe("")
  })

  it("another device (no local draft) with a claim lands on 对抗, with the claim from the trajectory", async () => {
    mockFullJourney({ claims: [{ id: "c1", text: "别处写的 claim" }], review_rounds: [{ id: "r1", claim_id: "c1", claim_snapshot: { text: "别处写的 claim" }, question_snapshot: baseDesk.question, verdict: null }] })
    renderJourney("w-1")
    await screen.findByText(/✓ claim 已固化,审查轮已开/)
    expect(openCard()).toBe("4. 对抗")
    expect(screen.getByText("别处写的 claim", { selector: "blockquote" })).toBeInTheDocument()
    expect(screen.queryByRole("status")).not.toBeInTheDocument() // 本机没有会话,不显示恢复横幅
    expect(row(/^1\. 出发点/)).toHaveTextContent("展开修改")
    expect(row(/^3\. 覆盖与 claim/)).toHaveTextContent("已写 1 条 claim")
  })

  it("any stage opens without locking; a not-yet-current card says so and returns to the current stage", async () => {
    mockFullJourney()
    renderJourney("w-1")
    await screen.findByText("Why does RLHF improve reasoning?")
    fireEvent.click(row(/^6\. 结晶/))
    expect(openCard()).toBe("6. 结晶")
    expect(screen.getByText("不是当前阶段 · 不锁,可以先做")).toBeInTheDocument()
    fireEvent.click(row(/^4\. 对抗/))
    expect(screen.getByText(/还没有固化的 claim/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "收起,回到第 1 步" }))
    expect(openCard()).toBe("1. 出发点")
  })

  it("rewriting in 覆盖与 claim writes a new claim instead of editing the signed one", async () => {
    mockFullJourney({ claims: [{ id: "c0", text: "第一条" }], review_rounds: [{ id: "r0", claim_id: "c0", claim_snapshot: { text: "第一条" }, question_snapshot: baseDesk.question, verdict: null }] })
    renderJourney("w-1")
    await screen.findByText(/✓ claim 已固化,审查轮已开/)
    fireEvent.click(row(/^3\. 覆盖与 claim/))
    fireEvent.click(screen.getByRole("button", { name: "再写一条 claim" }))
    fireEvent.change(screen.getByLabelText("由你写下的 claim"), { target: { value: "第二条" } })
    fireEvent.click(screen.getByRole("button", { name: /固化 claim 并开审查轮/ }))
    await waitFor(() => expect(openCard()).toBe("4. 对抗"))
    expect(JSON.parse(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/claims"))![1].body as string).text).toBe("第二条")
    await screen.findByText("第二条", { selector: "blockquote" })
  })

  it("blocks solidifying a claim while skeleton blanks remain, with a hint", async () => {
    window.sessionStorage.setItem("cui:dialogue-draft:v2:w-1", JSON.stringify({
      v: 2, workspaceId: "w-1", hypothesesText: "h", hypothesesDone: true, keywordsText: "RLHF reasoning", selectedKeywords: ["RLHF reasoning"],
      candidates, selected: ["arxiv:2401.00009"], searchQueries: ["RLHF reasoning"], summary: "## 这几篇覆盖了什么\n评测。", claimText: "", claimAck: false, confirmedGapIds: [], savedAt: new Date().toISOString(),
    }))
    mockFullJourney()
    renderJourney("w-1")
    fireEvent.click(await screen.findByRole("button", { name: "分歧断言" }, { timeout: 3000 }))
    const solidify = screen.getByRole("button", { name: /固化 claim 并开审查轮/ })
    expect(solidify).toBeDisabled()
    expect(screen.getByText("还有 ____ 没填")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("由你写下的 claim"), { target: { value: "文献在对齐机制上分成两派:一派认为偏好分布,另一派认为数据重复。" } })
    expect(solidify).toBeEnabled()
    expect(screen.queryByText("还有 ____ 没填")).not.toBeInTheDocument()
  })

  it("step 6: a confirmed gap can be challenged (entry visible without expanding step 5) by signing a pre-filled vacancy claim into a review round", async () => {
    const coverage = "文献覆盖了评测方法,但没有覆盖推理链真实应用的长期表现。"
    window.sessionStorage.setItem("cui:dialogue-draft:v2:w-1", JSON.stringify({
      v: 2, workspaceId: "w-1", hypothesesText: "h", hypothesesDone: true, keywordsText: "x", selectedKeywords: [],
      candidates, selected: ["arxiv:2401.00009"], searchQueries: ["x"], summary: "## 覆盖\n评测。", claimText: "c", roundId: "r0", claimAck: true,
      confirmedGapIds: ["g1"], savedAt: new Date().toISOString(),
    }))
    mockFullJourney({ claims: [{ id: "c0", text: "c" }], review_rounds: [{ id: "r0", claim_id: "c0", claim_snapshot: { text: "c" }, question_snapshot: baseDesk.question, verdict: null }], landscape: landscape([confirmedGap("g1", coverage)]) })
    renderJourney("w-1")
    // gap 已确认、无待回应 → 当前在第 6 步:入口直接可见,无需展开已折叠的第 5 步
    fireEvent.click(await screen.findByRole("button", { name: "对这个 gap 发起反证" }, { timeout: 3000 }))
    expect(openCard()).toBe("6. 结晶")
    const box = screen.getByLabelText("反证用 claim(空缺断言)") as HTMLTextAreaElement
    expect(box.value).toContain("没有覆盖推理链真实应用的长期表现")
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/claims"))).toBe(false)
    fireEvent.change(box, { target: { value: "" } })
    expect(screen.getByRole("button", { name: "署名固化为 claim 并开审查轮" })).toBeDisabled()
    fireEvent.change(box, { target: { value: "没有文献覆盖长期表现。" } })
    fireEvent.click(screen.getByRole("button", { name: "署名固化为 claim 并开审查轮" }))
    await waitFor(() => expect(window.location.pathname).toBe("/review-rounds/r1"), { timeout: 3000 })
    expect(JSON.parse(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/claims"))![1].body as string)).toMatchObject({ text: "没有文献覆盖长期表现。", kind: "vacancy" })
  })
})
