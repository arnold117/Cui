import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import App from "../../../App"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

const question = { version_id: "q-1", text: "Why does practice change recall?" }
const round = (id: string, claim_id: string, verdict: string | null) => ({ id, claim_id, claim_snapshot: { text: claim_id }, question_snapshot: question, verdict: verdict ? { round_id: id, verdict_type: verdict, user_reason: "r" } : null })
const legacyGap = { id: "gap-old", workspace_id: "w-1", coverage_statement: "旧登记路径留下的 gap:覆盖了即时效应,没有覆盖长期保持。", search_record: { query: "spaced practice", scope: "active", matched_locators: [], searched_at: "2026-09-02" }, counterexample_invitation: "如有长期数据请指正。", status: "pending", sequence: 1 }
// 本机没有草稿(换设备):阶段全由投影推导 —— 已裁决存活的 claim、没有待回应 → 当前阶段 = gap
const desk = {
  id: "w-1", question, sequence: 3, note: null, note_revisions: [], anchors: [],
  claims: [{ id: "c1", text: "间隔练习提升长期保持。" }],
  review_rounds: [round("r1", "c1", "survived")],
  pending_challenges: [],
  landscape: { workspace_id: "w-1", question, alive_claims: [{ id: "c1", text: "间隔练习提升长期保持。" }], claim_verdicts: { c1: "survived" }, confirmed_facts: [], gaps: [legacyGap] },
}
const reviewRound = (id: string, claim_id: string, verdict: string | null, challenges: unknown[] = []) => ({ ...round(id, claim_id, verdict), workspace_id: "w-1", challenges, evidence_candidates: [], ledger: { answered: [], deferred: [], pending: [], brought_unconfirmed: [] }, rounds: [{ id }] })

function mockApi(current: Record<string, unknown> = desk, rounds: Record<string, unknown> = { r1: reviewRound("r1", "c1", "survived") }) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url), method = init?.method ?? "GET"
    if (path === "/api/v2/workspaces/w-1" && method === "GET") return response(current)
    const roundMatch = path.match(/^\/api\/v2\/review-rounds\/([^/]+)$/)
    if (roundMatch && rounds[roundMatch[1]]) return response(rounds[roundMatch[1]])
    if (path === "/api/v2/workspaces/w-1/gap-candidates" && method === "POST") return response({ commit_position: 4, event_ids: ["e4"], result: { gap_candidate_id: "g-new" } })
    if (path === "/api/v2/gap-candidates/g-new/confirm") return response({ commit_position: 5, event_ids: ["e5"], result: { gap_candidate_id: "g-new" } })
    return response({ detail: path }, 404)
  })
}
const panel = () => screen.getByRole("complementary", { name: "聚焦面" })
const posts = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").map(([u, init]) => ({ url: String(u), body: JSON.parse(init.body as string) }))
function renderAt(path: string) { window.history.replaceState({}, "", path); return render(<App />) }

afterEach(() => { cleanup(); window.sessionStorage.clear(); window.localStorage?.clear?.() })
beforeEach(() => { fetchMock.mockReset(); window.sessionStorage.clear(); window.localStorage?.clear?.() })

describe("gap stage: one path (S5)", () => {
  it("without a local draft, drafting is unavailable and says why; writing by hand still works", async () => {
    mockApi()
    renderAt("/workspaces/w-1")
    expect(await screen.findByRole("heading", { name: "5. gap" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "让 Cui 起草 gap 候选" })).toBeDisabled()
    expect(screen.getByText("这台设备上没有选料草稿,起草不可用;可以直接手写。")).toBeInTheDocument()
    expect(screen.getByLabelText(/覆盖范围声明/)).toBeEnabled()
    expect(screen.getByRole("button", { name: "提交并确认这个 gap" })).toBeDisabled()
    // 「登记一个 gap 候选」表单已删:gap 只有这一条路径
    expect(screen.queryByRole("button", { name: "登记一个 gap 候选" })).not.toBeInTheDocument()
  })

  it("hand-written gap: submitting proposes then confirms (submit = confirm)", async () => {
    mockApi()
    renderAt("/workspaces/w-1")
    fireEvent.change(await screen.findByLabelText(/覆盖范围声明/), { target: { value: "现有文献覆盖了实验室里的即时回忆,但没有覆盖课堂里一学期后的保持。" } })
    const submit = screen.getByRole("button", { name: "提交并确认这个 gap" })
    expect(submit).toBeDisabled() // 邀请反例还空着
    fireEvent.change(screen.getByLabelText("邀请反例"), { target: { value: "有课堂长期追踪数据的研究会推翻它。" } })
    fireEvent.click(submit)
    await waitFor(() => expect(posts().map((p) => p.url)).toEqual(["/api/v2/workspaces/w-1/gap-candidates", "/api/v2/gap-candidates/g-new/confirm"]))
    const [propose, confirm] = posts()
    expect(propose.body).toMatchObject({ coverage_statement: "现有文献覆盖了实验室里的即时回忆,但没有覆盖课堂里一学期后的保持。", counterexample_invitation: "有课堂长期追踪数据的研究会推翻它。", search_query: "(未检索,手工登记)", matched_locators: [], external_refs: [] })
    expect(confirm.body).toMatchObject({ user_reason: "人审确认" })
  })

  it("a legacy pending gap shows confirm / reject on the gap card", async () => {
    mockApi()
    renderAt("/workspaces/w-1")
    expect(await screen.findByText(legacyGap.coverage_statement)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "确认这个 gap" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "拒绝" })).toBeEnabled()
  })

  it("with no round open the focus panel is the 现状 panel; a round opened from it closes back with 「回到现状」", async () => {
    mockApi()
    renderAt("/workspaces/w-1")
    expect(await screen.findByRole("heading", { name: "写 gap 时可以倚靠的" })).toBeInTheDocument()
    expect(panel()).toHaveTextContent("存活的 claim · 1")
    // 左栏卡顶只留一行计数指向右侧,不再重复图景本身
    expect(screen.getByText(/现状图景在/)).toHaveTextContent("存活 claim 1 · 已确认取证 0 · 已确认 gap 0")
    fireEvent.click(screen.getByRole("button", { name: /间隔练习提升长期保持。/ }))
    expect(window.location.pathname).toBe("/workspaces/w-1/rounds/r1")
    const back = await screen.findByRole("button", { name: "回到现状" })
    expect(screen.queryByRole("heading", { name: "写 gap 时可以倚靠的" })).not.toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "5. gap" })).toBeInTheDocument()
    fireEvent.click(back)
    expect(window.location.pathname).toBe("/workspaces/w-1")
    expect(await screen.findByRole("heading", { name: "写 gap 时可以倚靠的" })).toBeInTheDocument()
  })

  it("the 现状 panel ends with this device's 覆盖梳理 and picked papers when a local draft has them, and omits it otherwise", async () => {
    const candidates = [
      { material_id: "m1", locator: "arxiv:2401.00001", title: "Spacing in classrooms", reason: "r", source: "corpus", stance: "s", relation: { kind: "supports", note: "n" } },
      { locator: "arxiv:2402.00002", title: "Lab recall study", reason: "r", source: "arxiv", stance: "s" }, // 旧草稿:没有 relation
      { locator: "arxiv:2403.00003", title: "Not picked", reason: "r", source: "arxiv", stance: "s" },
    ]
    window.sessionStorage.setItem("cui:dialogue-draft:v2:w-1", JSON.stringify({ v: 2, workspaceId: "w-1", hypothesesText: "h", hypothesesDone: true, keywordsText: "", selectedKeywords: [], candidates, selected: ["arxiv:2401.00001", "arxiv:2402.00002"], searchQueries: ["spacing"], summary: "两篇都只测了即时回忆。", claimText: "", claimAck: true, confirmedGapIds: [], savedAt: new Date().toISOString() }))
    mockApi()
    renderAt("/workspaces/w-1")
    await screen.findByRole("heading", { name: "写 gap 时可以倚靠的" })
    const section = screen.getByText("覆盖梳理 · 已选文献 2 篇").parentElement!
    expect(section).toBe(panel().querySelector("section > section:last-of-type"))
    expect(section).toHaveTextContent("两篇都只测了即时回忆。")
    expect(section).toHaveTextContent("Spacing in classrooms · arxiv:2401.00001 · 与假设:支持")
    expect(section).toHaveTextContent(/Lab recall study · arxiv:2402\.00002$/)
    expect(section).not.toHaveTextContent("Not picked")

    // 换设备(本机没有草稿):整段不出现
    cleanup(); window.sessionStorage.clear()
    renderAt("/workspaces/w-1")
    await screen.findByRole("heading", { name: "写 gap 时可以倚靠的" })
    expect(panel()).not.toHaveTextContent("已选文献")
    expect(panel()).not.toHaveTextContent("覆盖梳理")
  })

  it("on 对抗 the round still closes with 收起; 「继续到 gap」 swaps the open round for the 现状 panel", async () => {
    const pending = { id: "p1", review_round_id: "r2", claim_id: "c2", attack_surface: "替代解释未排除", why_it_matters: "w", self_check_method: "s", status: "pending" }
    mockApi({ ...desk, claims: [...desk.claims, { id: "c2", text: "第二条 claim" }], review_rounds: [...desk.review_rounds, round("r2", "c2", null)], pending_challenges: [pending] }, { r2: reviewRound("r2", "c2", null, [pending]) })
    renderAt("/workspaces/w-1/rounds/r2")
    expect(await screen.findByRole("heading", { name: "4. 对抗" })).toBeInTheDocument()
    expect(await screen.findByRole("button", { name: "收起" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "继续到 gap" }))
    expect(window.location.pathname).toBe("/workspaces/w-1")
    expect(await screen.findByRole("heading", { name: "写 gap 时可以倚靠的" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "5. gap" })).toBeInTheDocument()
  })
})
