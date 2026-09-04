import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppRouter } from "../../../router"
import { DialogueDesk } from "./DialogueDesk"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

const desk = { id: "w-1", question: { version_id: "q-1", text: "Why does RLHF improve reasoning?" }, sequence: 0, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [] }

const candidates = [
  { material_id: "m1", locator: "arxiv:2401.00009", title: "RLHF reasoning paper", reason: "直接相关", source: "corpus", stance: "认为 RLHF 通过偏好对齐提升指令遵循。", relation: { kind: "supports", note: "支撑对齐→推理改善的路径。" } },
  { material_id: "m2", locator: "arxiv:2402.00001", title: "Reasoning evaluation", reason: "相关评测", source: "corpus", stance: "评测了推理链的稳定性。", relation: { kind: "partial", note: "部分支撑:仅限评测面。" } },
  { material_id: "m3", locator: "arxiv:2402.00002", title: "Preference alignment", reason: "对齐机制", source: "corpus", stance: "讨论对齐偏好分布。", relation: { kind: "background", note: "背景相关。" } },
]

function mockFullJourney() {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url)
    const method = init?.method ?? "GET"
    if (path.endsWith("/api/v2/workspaces/w-1") && method === "GET") return response(desk)
    if (path.endsWith("/dialogue/orientation")) return response({ hypotheses: ["RLHF 通过偏好对齐减少分布外漂移从而提升推理", "推理提升来自训练数据的分布而非对齐"], keywords: ["RLHF reasoning", "偏好对齐"] })
    if (path.endsWith("/dialogue/literature-search")) return response({ query: "RLHF reasoning", candidates })
    if (path.endsWith("/dialogue/landscape-summary")) return response({ text: "## 这几篇覆盖了什么\nRLHF 评测覆盖了指令遵循与对齐。\n## 还没有被覆盖的\n推理链上的真实应用表现未被覆盖。" })
    if (path.endsWith("/claims")) return response({ result: { claim_id: "c1" } })
    if (path.endsWith("/review-rounds") && method === "POST") return response({ result: { review_round_id: "r1" } })
    if (path.endsWith("/literature-challenges")) return response({ result: { challenge_id: "ch-lit" } })
    if (path.endsWith("/dialogue/gap-draft")) return response({ coverage_statement: "文献覆盖了评测方法,但没有覆盖推理链真实应用的长期表现。", search_query: "rlhf reasoning", counterexample_invitation: "如有推理任务上的 RLHF 长期数据请指正。" })
    if (path.endsWith("/gap-candidates") && method === "POST") return response({ result: { gap_candidate_id: "g1" } })
    if (path.includes("/gap-candidates/g1/confirm")) return response({ result: { gap_candidate_id: "g1" } })
    if (path.endsWith("/dialogue/related-work-draft")) return response({ text: "Existing work covers RLHF evaluations [arxiv:2401.00009] while the real-task gap stays open." })
    return response({ detail: path }, 404)
  })
}

function renderDesk(workspaceId: string) {
  return render(<AppRouter><DialogueDesk workspaceId={workspaceId} /></AppRouter>)
}

function litSearchCalls() {
  return fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/dialogue/literature-search"))
}

afterEach(() => { cleanup(); window.sessionStorage.clear() })
beforeEach(() => { fetchMock.mockReset(); window.sessionStorage.clear() })

describe("literature dialogue desk (staged)", () => {
  it("walks the staged journey: orientation → hypotheses confirm → keyword chip auto-search → picks → coverage → claim → review handoff → gap → related-work draft", async () => {
    mockFullJourney()
    renderDesk("w-1")
    await screen.findByText("Why does RLHF improve reasoning?")

    // 第 1 步:起草假设(不自动离开;确认后才进第 2 步)
    fireEvent.click(screen.getByRole("button", { name: "让 Cui 起草候选假设与关键词" }))
    const textarea = await screen.findByLabelText(/候选假设/)
    await waitFor(() => expect((textarea as HTMLTextAreaElement).value).toContain("RLHF 通过偏好对齐减少分布外漂移"), { timeout: 3000 })
    fireEvent.change(textarea, { target: { value: "我自己的假设:对齐提升推理。\n质疑:也可能只是数据重复。" } })
    expect((textarea as HTMLTextAreaElement).value).toContain("我自己的假设")
    fireEvent.click(screen.getByRole("button", { name: "就用这版假设,去选料 →" }))

    // 第 2 步:选料。勾选一个词 → 只发一次合并检索
    await waitFor(() => expect(screen.getByLabelText(/检索词\(用分号/)).toHaveValue("RLHF reasoning; 偏好对齐"), { timeout: 3000 })
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
    fireEvent.click(screen.getByRole("button", { name: "分歧断言" }))
    const claimInput = screen.getByLabelText("由你写下的 claim")
    await waitFor(() => expect((claimInput as HTMLTextAreaElement).value).toContain("分成两派"), { timeout: 2000 })
    fireEvent.change(claimInput, { target: { value: "对齐偏好分布才是推理提升的主因。" } })
    fireEvent.click(screen.getByRole("button", { name: /固化 claim 并开审查轮/ }))
    await screen.findByText(/✓ claim 已固化,审查轮已开/, {}, { timeout: 3000 })

    // 文献发难把所选材料带进审查轮
    fireEvent.click(screen.getByRole("button", { name: /用所选文献发难/ }))
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/literature-challenges"))
      expect(call).toBeTruthy()
      expect(JSON.parse(call![1].body as string).material_ids).toEqual(["m1", "m2", "m3"])
    }, { timeout: 3000 })
    fireEvent.click(screen.getByRole("button", { name: /我看过审查轮了,继续起草 gap →/ }))

    // 第 5 步:gap 起草 → 署名提交确认
    fireEvent.click(screen.getByRole("button", { name: "让 Cui 起草 gap 候选" }))
    const coverage = await screen.findByLabelText(/覆盖范围声明/)
    expect((coverage as HTMLTextAreaElement).value).toContain("没有覆盖推理链真实应用的长期表现")
    fireEvent.click(screen.getByRole("button", { name: /提交并确认这个 gap/ }))
    await waitFor(() => expect(screen.getByText(/✓ gap 已确认 ×1/)).toBeInTheDocument(), { timeout: 3000 })
    const propose = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/gap-candidates"))
    expect(propose).toBeTruthy()
    expect(JSON.parse(propose![1].body as string).matched_locators).toEqual(["arxiv:2401.00009", "arxiv:2402.00001", "arxiv:2402.00002"])

    // 第 6 步:related-work 草稿
    fireEvent.click(screen.getByRole("button", { name: /生成 related-work 综述草稿/ }))
    await screen.findByText(/Existing work covers RLHF evaluations/, {}, { timeout: 3000 })
    fireEvent.click(screen.getByRole("button", { name: "下载 .md" }))
  })

  it("resumes a saved session at its stage; chip toggles fire one merged search and text edits do not; exit navigates back; clear restarts", async () => {
    const seed = (extra: Record<string, unknown>) => JSON.stringify({
      v: 2, workspaceId: "w-2", hypothesesText: "恢复出来的假设", hypothesesDone: true,
      keywordsText: "偏好对齐; RLHF reasoning", selectedKeywords: [], candidates: [], selected: [],
      searchQuery: "", claimText: "", claimAck: false, confirmedGapIds: [], ...extra,
    })
    window.sessionStorage.setItem("cui:dialogue-draft:v2:w-2", seed({ savedAt: new Date().toISOString() }))
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const path = String(url)
      if (path.endsWith("/api/v2/workspaces/w-2") && (init?.method ?? "GET") === "GET") return response(desk)
      if (path.endsWith("/dialogue/literature-search")) return response({ query: "偏好对齐", candidates: [] })
      return response({ detail: path }, 404)
    })
    renderDesk("w-2")
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

    // 退出会话 → 回到工作区
    fireEvent.click(screen.getByRole("button", { name: "退出会话" }))
    expect(window.location.pathname).toBe("/workspaces/w-2")

    // 重新进入(新草稿仍在)→ 恢复;清空重来 → 回到第 1 步
    cleanup()
    window.sessionStorage.setItem("cui:dialogue-draft:v2:w-2", seed({ savedAt: new Date().toISOString() }))
    renderDesk("w-2")
    await screen.findByText("Why does RLHF improve reasoning?", {}, { timeout: 3000 })
    await screen.findByRole("button", { name: /清空并重新开始/ }, { timeout: 3000 })
    fireEvent.click(screen.getByRole("button", { name: /清空并重新开始/ }))
    await screen.findByRole("button", { name: "让 Cui 起草候选假设与关键词" }, { timeout: 3000 })
    const after = JSON.parse(window.sessionStorage.getItem("cui:dialogue-draft:v2:w-2") ?? "{}")
    expect(after.hypothesesDone).toBe(false)
    expect(after.keywordsText).toBe("")
  })
})
