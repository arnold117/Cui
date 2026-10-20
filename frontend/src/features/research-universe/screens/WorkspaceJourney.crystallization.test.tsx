import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { WorkspaceJourney } from "./WorkspaceJourney"
import { AppRouter } from "../../../router"

const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
function view(id = "w") { return render(<AppRouter><WorkspaceJourney workspaceId={id} /></AppRouter>) }
// 结晶动作原样搬进「结晶」阶段卡:先点开这一阶段
const openCrystal = () => fireEvent.click(screen.getByRole("button", { name: /^6\. 结晶/ }))
const bodyOf = (suffix: string) => JSON.parse(fetchMock.mock.calls.find(([url, init]) => String(url).endsWith(suffix) && init?.method === "POST")![1].body)
const baseDesk = (overrides: Record<string, unknown> = {}) => ({
  id: "w",
  question: { version_id: "q", text: "Why does X happen?" },
  sequence: 9,
  note: { id: "n", note_id: "n", revision_id: "rev", text: "abcdef", sequence: 9 },
  note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [], materials: [],
  user_position: "exploring", conclusion: null, direction_links: [], confirmed_facts: [],
  ...overrides,
})

describe("workspace crystallization stage and position header", () => {
  beforeEach(() => { fetchMock.mockReset(); window.sessionStorage.clear() })

  it("shows the crystallization ledger and enforces deferred revival condition", async () => {
    const desk = baseDesk({
      review_rounds: [{ id: "r1", claim_snapshot: { id: "c1", text: "X causes Y." }, question_snapshot: { id: "q", text: "Why does X happen?" }, verdict: { verdict_type: "survived", user_reason: "ok" } }],
      confirmed_facts: [{ id: "f1", relation: "contradicts", material_anchor: { id: "m1", excerpt: "Paper A observes Z." }, claim_snapshot: { id: "c1", text: "X causes Y." } }],
      pending_challenges: [{ id: "ch1", review_round_id: "r1", attack_surface: "comparison group", why_it_matters: "why", self_check_method: "check", status: "pending" }],
    })
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (!init?.method && String(url).endsWith("/workspaces/w")) return Promise.resolve(response(desk))
      return Promise.resolve(response({ detail: "x" }, 404))
    })
    view()
    await screen.findByText("Why does X happen?")
    openCrystal()
    fireEvent.click(screen.getByRole("button", { name: "确认这次探索的位置" }))
    await screen.findByRole("heading", { name: "结晶台" })
    // ledger shows verdicts, confirmed evidence facts, and pending items
    expect(screen.getByText(/裁决：survived/)).toBeInTheDocument()
    expect(screen.getByText(/已确认取证：Paper A observes Z/)).toBeInTheDocument()
    expect(screen.getByText(/仍挂起：comparison group/)).toBeInTheDocument()
    const confirm = screen.getByRole("button", { name: "确认结晶" })
    // no type / text yet -> disabled
    fireEvent.change(screen.getByLabelText("我的探索结论"), { target: { value: "My conclusion" } })
    expect(confirm).toBeDisabled()
    // deferred requires a revival condition input
    fireEvent.click(screen.getByRole("radio", { name: /暂缓条件/ }))
    await screen.findByLabelText(/未来重开条件/)
    expect(confirm).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/未来重开条件/), { target: { value: "when data arrives" } })
    expect(confirm).toBeEnabled()
  })

  it("pending challenges never block concluding", async () => {
    let desk = baseDesk({ pending_challenges: [{ id: "ch1", review_round_id: "r1", attack_surface: "pending one", why_it_matters: "why", self_check_method: "check", status: "pending" }] })
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const path = String(url)
      if (!init?.method && path.endsWith("/workspaces/w")) return Promise.resolve(response(desk))
      if (path.endsWith("/conclusions") && init?.method === "POST") { desk = { ...desk, user_position: "concluded", conclusion: { id: "conc", type: "tentative_answer", text: "done", basis_refs: [], revival_condition: null }, sequence: 10 }; return Promise.resolve(response({ commit_position: 1, event_ids: ["e"], result: { workspace_id: "w", conclusion_id: "conc" }, fragment: desk })) }
      return Promise.resolve(response({ detail: "x" }, 404))
    })
    view()
    await screen.findByText("Why does X happen?")
    openCrystal()
    fireEvent.click(screen.getByRole("button", { name: "确认这次探索的位置" }))
    await screen.findByRole("heading", { name: "结晶台" })
    expect(screen.getByText(/仍挂起：pending one/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("我的探索结论"), { target: { value: "done" } })
    fireEvent.click(screen.getByRole("radio", { name: /暂时回答/ }))
    fireEvent.click(screen.getByRole("button", { name: "确认结晶" }))
    await screen.findByText("位置：已结晶")
    expect(screen.getByText("done")).toBeInTheDocument()
  })

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
    await screen.findByText("位置：已暂停")
    expect(bodyOf("/pause")).toMatchObject({ user_reason: null, expected_sequence: 9 })
    expect(header.queryByRole("button", { name: "暂停" })).not.toBeInTheDocument()
    fireEvent.click(header.getByRole("button", { name: "重开" }))
    const confirm = header.getByRole("button", { name: "确认重开" })
    expect(confirm).toBeDisabled()
    fireEvent.change(header.getByLabelText("重开理由"), { target: { value: "  " } })
    expect(confirm).toBeDisabled()
    fireEvent.change(header.getByLabelText("重开理由"), { target: { value: "新数据到了" } })
    fireEvent.click(confirm)
    await screen.findByText("位置：探索中")
    expect(bodyOf("/reopen")).toMatchObject({ user_reason: "新数据到了", expected_sequence: 10 })
  })

  it("reopen turns 结晶 back into not-done even though the conclusion stays in the projection", async () => {
    const concluded = baseDesk({ user_position: "concluded", conclusion: { id: "conc", type: "tentative_answer", text: "done", basis_refs: [], revival_condition: null } })
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (!init?.method && String(url).endsWith("/workspaces/w")) return Promise.resolve(response(concluded))
      return Promise.resolve(response({ detail: "x" }, 404))
    })
    view()
    await screen.findByText("Why does X happen?")
    expect(screen.getByRole("button", { name: /^6\. 结晶/ })).toHaveTextContent("展开修改")
    cleanup()
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (!init?.method && String(url).endsWith("/workspaces/w")) return Promise.resolve(response({ ...concluded, user_position: "exploring" }))
      return Promise.resolve(response({ detail: "x" }, 404))
    })
    view()
    await screen.findByText("Why does X happen?")
    expect(screen.getByRole("button", { name: /^6\. 结晶/ })).toHaveTextContent("打开")
  })

  it("concludes and shows the direction impact台 when a direction is attached", async () => {
    let desk = baseDesk({ direction_links: [{ link_id: "l1", direction_id: "d1", direction_proposition: "A long-term thesis.", status: "active" }] })
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const path = String(url)
      if (!init?.method && path.endsWith("/workspaces/w")) return Promise.resolve(response(desk))
      if (path.endsWith("/conclusions") && init?.method === "POST") { desk = { ...desk, user_position: "concluded", conclusion: { id: "conc", type: "tentative_answer", text: "My conclusion", basis_refs: [], revival_condition: null }, sequence: 10 }; return Promise.resolve(response({ commit_position: 1, event_ids: ["e"], result: { workspace_id: "w", conclusion_id: "conc" }, fragment: desk })) }
      if (path.endsWith("/crystallizations") && init?.method === "POST") return Promise.resolve(response({ commit_position: 2, event_ids: ["e"], result: { crystallization_id: "x1", direction_id: "d1", workspace_id: "w" }, fragment: desk }))
      return Promise.resolve(response({ detail: "x" }, 404))
    })
    view()
    await screen.findByText("Why does X happen?")
    openCrystal()
    fireEvent.click(screen.getByRole("button", { name: "确认这次探索的位置" }))
    await screen.findByRole("heading", { name: "结晶台" })
    fireEvent.change(screen.getByLabelText("我的探索结论"), { target: { value: "My conclusion" } })
    fireEvent.click(screen.getByRole("radio", { name: /暂时回答/ }))
    fireEvent.click(screen.getByRole("button", { name: "确认结晶" }))
    await screen.findByRole("heading", { name: "已确认本次探索结论" })
    // default is 暂不决定; choosing to crystallize issues the attach command
    fireEvent.click(screen.getByRole("radio", { name: /成为方向的一项结晶/ }))
    fireEvent.click(screen.getByRole("button", { name: "确认" }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/crystallizations"))).toBe(true))
  })
})
