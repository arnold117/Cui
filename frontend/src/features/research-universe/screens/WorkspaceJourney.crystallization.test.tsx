import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import App from "../../../App"
import { WorkspaceJourney } from "./WorkspaceJourney"
import { AppRouter } from "../../../router"

const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
function view(id = "w") { return render(<AppRouter><WorkspaceJourney workspaceId={id} /></AppRouter>) }
function renderAt(path: string) { window.history.replaceState({}, "", path); return render(<App />) }
const bodyOf = (suffix: string) => JSON.parse(fetchMock.mock.calls.find(([url, init]) => String(url).endsWith(suffix) && init?.method === "POST")![1].body)
const called = (suffix: string) => fetchMock.mock.calls.some(([url]) => String(url).endsWith(suffix))
const panel = () => screen.getByRole("complementary", { name: "聚焦面" })
const row = (name: RegExp) => screen.getByRole("button", { name })

const question = { version_id: "q", text: "Why does X happen?" }
const round = (id: string, claim_id: string, verdict: string | null = null) => ({ id, claim_id, claim_snapshot: { id: claim_id, text: claim_id }, question_snapshot: question, verdict: verdict ? { round_id: id, verdict_type: verdict, user_reason: "r" } : null })
const challenge = (id: string, status: string) => ({ id, review_round_id: "r2", attack_surface: `challenge ${id}`, why_it_matters: "w", self_check_method: "s", status })
const gap = (id: string, text: string) => ({ id, workspace_id: "w", coverage_statement: text, search_record: { query: "q", scope: "active", matched_locators: [] }, counterexample_invitation: "i", status: "confirmed" })
const baseDesk = (overrides: Record<string, unknown> = {}) => ({
  id: "w", question, sequence: 9,
  note: { id: "n", note_id: "n", revision_id: "rev", text: "abcdef", sequence: 9 },
  note_revisions: [], anchors: [], materials: [],
  claims: [{ id: "c1", text: "X causes Y." }, { id: "c2", text: "Z is irrelevant." }],
  review_rounds: [round("r1", "c1", "survived"), round("r2", "c2")],
  // 待回应只数 status=pending:一条 pending + 一条已回应未裁决 ⇒ 1
  pending_challenges: [challenge("p1", "pending"), challenge("a1", "answered")],
  landscape: { workspace_id: "w", question, alive_claims: [], claim_verdicts: {}, gaps: [gap("g1", "Gap one: nobody measured Z."), gap("g2", "Gap two: no long-term data.")], confirmed_facts: [{ candidate_id: "f1", claim_id: "c1", claim_text: "X causes Y.", relation: "contradicts", material_locator: "Paper A", decision_reason: "Paper A observes Z." }] },
  user_position: "exploring", conclusion: null, direction_links: [], confirmed_facts: [],
  ...overrides,
})
const existing = { id: "d1", proposition: "A long-term thesis.", status: "active", crystallizations: [], crystallizations_count: 0, attached_workspaces_count: 0 }

/** 有状态的后端:结论、结晶写入后,工作区投影与首页投影都读得回。 */
function mockServer(desk = baseDesk(), directions: unknown[] = [existing]) {
  const server = { desk, home: { universe_id: "u", workspaces: [], pending_facts: [], directions } }
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url), method = init?.method ?? "GET", body = init?.body ? JSON.parse(init.body as string) : undefined
    if (path === "/api/v2/workspaces/w" && method === "GET") return response(server.desk)
    if (path === "/api/v2/universes/active") return response({ id: "u" })
    if (path === "/api/v2/universes/u/home") return response(server.home)
    if (path === "/api/v2/review-rounds/r2") return response({ ...round("r2", "c2"), workspace_id: "w", challenges: [challenge("p1", "pending")], evidence_candidates: [], ledger: { answered: [], deferred: [], pending: [], brought_unconfirmed: [] }, rounds: [{ id: "r2" }] })
    if (path === "/api/v2/workspaces/w/conclusions" && method === "POST") {
      server.desk = { ...server.desk, user_position: "concluded", conclusion: { id: "conc", type: body.conclusion_type, text: body.conclusion_text, reason: body.user_reason, basis_refs: [], revival_condition: body.revival_condition }, sequence: 10 }
      return response({ commit_position: 1, event_ids: ["e"], result: { workspace_id: "w", conclusion_id: "conc" } })
    }
    if (path === "/api/v2/workspaces/w/crystallize-into-direction" && method === "POST") {
      const id = body.direction_id ?? "d-new", crystal = { crystallization_id: "x1", direction_id: id, workspace_id: "w", conclusion_id: body.conclusion_id, conclusion_text: "c", conclusion_type: "tentative_answer" }
      server.home = { ...server.home, directions: [{ id, proposition: body.new_proposition ?? existing.proposition, status: "active", crystallizations: [crystal], crystallizations_count: 1, attached_workspaces_count: 1 }] }
      return response({ commit_position: 2, event_ids: ["e1", "e2"], result: { direction_id: id, direction_link_id: "l1", crystallization_id: "x1", workspace_id: "w" } })
    }
    return response({ detail: path }, 404)
  })
  return server
}

const openCrystal = async () => fireEvent.click(await screen.findByRole("button", { name: /^结晶/ }))
/** 选类型 + 写结论与理由 → 确认这次探索的位置 → 同一张卡进入「这次结论去哪」 */
async function locate(type = /暂时回答/) {
  renderAt("/workspaces/w")
  await openCrystal()
  fireEvent.click(screen.getByRole("radio", { name: type }))
  fireEvent.change(screen.getByLabelText("结论"), { target: { value: "My conclusion" } })
  fireEvent.change(screen.getByLabelText("理由"), { target: { value: "c1 survived" } })
  fireEvent.click(screen.getByRole("button", { name: "确认这次探索的位置" }))
  await screen.findByRole("group", { name: "这次结论去哪" })
}
/** 把结晶卡收成一行(点开别的阶段),读结晶那一行 */
const crystalRow = () => { fireEvent.click(row(/^出发点/)); return row(/^结晶/) }

afterEach(() => { cleanup(); window.sessionStorage.clear(); window.localStorage?.clear?.() })
beforeEach(() => { fetchMock.mockReset(); window.sessionStorage.clear(); window.localStorage?.clear?.() })

describe("结晶 stage: 账本 on the right", () => {
  it("shows the 账本 when no round is open, and the card points to it with the 仍待回应 count", async () => {
    mockServer()
    renderAt("/workspaces/w")
    await openCrystal()
    expect(within(panel()).getByRole("heading", { name: "这次结论的依据" })).toBeInTheDocument()
    const ledger = within(panel())
    expect(ledger.getByRole("button", { name: /X causes Y\./ })).toHaveTextContent("存活")
    expect(ledger.getByRole("button", { name: /Z is irrelevant\./ })).toHaveTextContent("未裁决 · 仍待回应 1")
    expect(ledger.getByText("Gap one: nobody measured Z.")).toBeInTheDocument()
    expect(ledger.getByText("Paper A observes Z.")).toBeInTheDocument()
    expect(screen.getByText(/仍待回应 1 条——结晶不会关掉它们/)).toBeInTheDocument()
  })

  it("opening a round from the 账本 keeps 结晶 open and closes back with 「回到账本」", async () => {
    mockServer()
    renderAt("/workspaces/w")
    await openCrystal()
    fireEvent.click(within(panel()).getByRole("button", { name: /Z is irrelevant\./ }))
    await waitFor(() => expect(window.location.pathname).toBe("/workspaces/w/rounds/r2"))
    fireEvent.click(await within(panel()).findByRole("button", { name: "回到账本" }))
    await waitFor(() => expect(window.location.pathname).toBe("/workspaces/w"))
    expect(await within(panel()).findByRole("heading", { name: "这次结论的依据" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "6. 结晶" })).toBeInTheDocument()
  })
})

describe("结晶 stage: confirm the position, then where the conclusion goes", () => {
  it("needs a type, a conclusion and a reason; deferred also needs a revival condition", async () => {
    mockServer()
    renderAt("/workspaces/w")
    await openCrystal()
    const confirm = screen.getByRole("button", { name: "确认这次探索的位置" })
    expect(confirm).toBeDisabled()
    fireEvent.click(screen.getByRole("radio", { name: /暂缓条件/ }))
    fireEvent.change(screen.getByLabelText("结论"), { target: { value: "Park it" } })
    expect(confirm).toBeDisabled() // 理由还空着
    fireEvent.change(screen.getByLabelText("理由"), { target: { value: "no data yet" } })
    expect(confirm).toBeDisabled()
    expect(screen.getByText("暂缓必须写复活条件")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/复活条件/), { target: { value: "when data arrives" } })
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)
    await screen.findByRole("group", { name: "这次结论去哪" })
    expect(bodyOf("/conclusions")).toMatchObject({ conclusion_type: "deferred", conclusion_text: "Park it", user_reason: "no data yet", revival_condition: "when data arrives", expected_sequence: 9 })
    expect(screen.getByText("复活条件:when data arrives")).toBeInTheDocument()
    // 位置已确认但还没选去向:阶段 6 未完成,主按钮要先选去向
    expect(screen.getByRole("button", { name: "选择去向" })).toBeDisabled()
    expect(crystalRow()).toHaveTextContent("确认这次探索的位置,再定结论去哪")
  })

  it("attach to an existing direction: one crystallize-into-direction call with direction_id", async () => {
    mockServer()
    await locate()
    fireEvent.click(screen.getByRole("radio", { name: "挂到已有方向" }))
    const select = await screen.findByRole("combobox", { name: "已有方向" })
    expect(screen.getByRole("button", { name: "挂到这个方向" })).toBeDisabled()
    fireEvent.change(select, { target: { value: "d1" } })
    fireEvent.click(screen.getByRole("button", { name: "挂到这个方向" }))
    expect(await screen.findByText("已结晶到方向「A long-term thesis.」")).toBeInTheDocument()
    expect(bodyOf("/crystallize-into-direction")).toMatchObject({ conclusion_id: "conc", direction_id: "d1", new_proposition: null, expected_sequence: 0 })
    expect(called("/direction-links") || called("/crystallizations") || called("/directions")).toBe(false) // 不再分步调三条旧命令
    expect(crystalRow()).toHaveTextContent("结晶到方向「A long-term thesis.」")
  })

  it("new direction from a gap: the chosen gap prefills it, signing as-is is enough, editing after signing invalidates", async () => {
    mockServer()
    await locate()
    fireEvent.click(screen.getByRole("radio", { name: "从 gap 新建方向" }))
    const proposition = screen.getByLabelText("方向命题") as HTMLTextAreaElement
    expect(proposition.value).toBe("Gap one: nobody measured Z.")
    fireEvent.change(screen.getByRole("combobox", { name: "用哪个 gap 预填" }), { target: { value: "g2" } })
    expect(proposition.value).toBe("Gap two: no long-term data.")
    const create = screen.getByRole("button", { name: "新建方向并结晶" })
    expect(create).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: "签名：这是我的方向命题" }))
    expect(create).toBeEnabled() // 不强制改写:原样签名即可
    fireEvent.change(proposition, { target: { value: "Gap two, reworded." } })
    expect(create).toBeDisabled() // 签名后再改 ⇒ 签名失效
    expect(screen.getByRole("button", { name: "签名：这是我的方向命题" })).toBeInTheDocument()
    fireEvent.change(proposition, { target: { value: "Gap two: no long-term data." } })
    fireEvent.click(screen.getByRole("button", { name: "签名：这是我的方向命题" }))
    fireEvent.click(create)
    expect(await screen.findByText("已结晶到方向「Gap two: no long-term data.」")).toBeInTheDocument()
    expect(bodyOf("/crystallize-into-direction")).toMatchObject({ conclusion_id: "conc", direction_id: null, new_proposition: "Gap two: no long-term data.", expected_sequence: 0 })
  })

  it("只留在本次: an explicit click, no direction call, and it completes the stage", async () => {
    mockServer()
    await locate()
    fireEvent.click(screen.getByRole("radio", { name: "只留在本次探索" }))
    fireEvent.click(screen.getByRole("button", { name: "只留在本次" }))
    expect(screen.getByText("这次结论只留在本次探索")).toBeInTheDocument()
    expect(called("/crystallize-into-direction")).toBe(false)
    expect(JSON.parse(window.sessionStorage.getItem("cui:dialogue-draft:v2:w") ?? "{}").keptLocal).toBe("conc")
    expect(crystalRow()).toHaveTextContent("结论只留在本次探索")
  })

  it("拆分／转向 brings 分支 and 吸收 as secondary actions", async () => {
    mockServer()
    renderAt("/workspaces/w")
    await openCrystal()
    fireEvent.click(screen.getByRole("radio", { name: /暂时回答/ }))
    expect(screen.queryByRole("button", { name: "分支出新问题" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("radio", { name: /拆分／转向/ }))
    fireEvent.click(screen.getByRole("button", { name: "吸收进另一个问题" }))
    expect(screen.getByLabelText("并入哪一条工作区")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "分支出新问题" }))
    expect(screen.getByLabelText("后继问题")).toBeInTheDocument()
    expect(screen.queryByLabelText("并入哪一条工作区")).not.toBeInTheDocument()
  })
})

describe("workspace position header and reopen", () => {
  it("header keeps only pause/reopen: pause reason optional, reopen reason required", async () => {
    let desk = baseDesk()
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const path = String(url)
      if (!init?.method && path.endsWith("/workspaces/w")) return Promise.resolve(response(desk))
      if (path.endsWith("/pause") && init?.method === "POST") { desk = { ...desk, user_position: "paused", sequence: 10 }; return Promise.resolve(response({ commit_position: 1, event_ids: ["e"], result: { workspace_id: "w" }, fragment: desk })) }
      if (path.endsWith("/reopen") && init?.method === "POST") { desk = { ...desk, user_position: "exploring", sequence: 11 }; return Promise.resolve(response({ commit_position: 2, event_ids: ["e"], result: { workspace_id: "w" }, fragment: desk })) }
      return Promise.resolve(response({ detail: "x" }, 404))
    })
    view()
    await screen.findByText("Why does X happen?")
    const header = within(screen.getByRole("heading", { level: 1 }).closest("header")!)
    expect(header.getAllByRole("button").map(b => b.textContent)).toEqual(["暂停"])
    fireEvent.click(header.getByRole("button", { name: "暂停" }))
    fireEvent.click(header.getByRole("button", { name: "确认暂停" }))
    await screen.findByText("问题 · 已暂停")
    expect(bodyOf("/pause")).toMatchObject({ user_reason: null, expected_sequence: 9 })
    expect(header.queryByRole("button", { name: "暂停" })).not.toBeInTheDocument()
    fireEvent.click(header.getByRole("button", { name: "重开" }))
    const confirm = header.getByRole("button", { name: "确认重开" })
    expect(confirm).toBeDisabled()
    fireEvent.change(header.getByLabelText("重开理由"), { target: { value: "  " } })
    expect(confirm).toBeDisabled()
    fireEvent.change(header.getByLabelText("重开理由"), { target: { value: "新数据到了" } })
    fireEvent.click(confirm)
    await screen.findByText("问题 · 探索中")
    expect(bodyOf("/reopen")).toMatchObject({ user_reason: "新数据到了", expected_sequence: 10 })
  })

  it("a crystallization read back from home completes 结晶 on another device; reopen makes it not-done again", async () => {
    const concluded = baseDesk({ claims: [], review_rounds: [], pending_challenges: [], user_position: "concluded", conclusion: { id: "conc", type: "tentative_answer", text: "done", basis_refs: [], revival_condition: null } })
    const crystallized = { ...existing, crystallizations: [{ crystallization_id: "x1", direction_id: "d1", workspace_id: "w", conclusion_id: "conc", conclusion_text: "done", conclusion_type: "tentative_answer" }] }
    mockServer(concluded, [crystallized])
    view()
    await waitFor(() => expect(row(/^结晶/)).toHaveTextContent("展开修改"))
    expect(row(/^结晶/)).toHaveTextContent("结晶到方向「A long-term thesis.」")
    cleanup()
    mockServer({ ...concluded, user_position: "exploring" }, [crystallized])
    view()
    await screen.findByText("Why does X happen?")
    expect(row(/^结晶/)).toHaveTextContent("打开")
  })
})
