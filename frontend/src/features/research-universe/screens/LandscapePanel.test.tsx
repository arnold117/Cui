import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { GapCandidate, WorkspaceLandscape } from "../types"
import { AppRouter } from "../../../router"
import { GapList, LandscapePanel } from "./LandscapePanel"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const onChanged = vi.fn()
const onOpen = vi.fn()

const emptyLandscape: WorkspaceLandscape = {
  workspace_id: "w-1",
  question: { version_id: "q-1", text: "Why does X matter?" },
  alive_claims: [],
  claim_verdicts: {},
  confirmed_facts: [],
  gaps: [],
}
const pendingGap: GapCandidate = {
  id: "gap-1", workspace_id: "w-1",
  coverage_statement: "现有文献覆盖了机制测量,但没有覆盖真实任务表现。",
  search_record: { query: "X real-task", scope: "active", matched_locators: ["arxiv:2401.00001"], searched_at: "2026-09-02" },
  counterexample_invitation: "欢迎任何真实任务上的反例。",
  status: "pending", sequence: 1,
}
const renderGaps = (gaps: GapCandidate[]) => render(<AppRouter><GapList workspaceId="w-1" gaps={gaps} onChanged={onChanged} onOpen={onOpen} /></AppRouter>)

afterEach(() => cleanup())
beforeEach(() => { fetchMock.mockReset(); onChanged.mockClear(); onOpen.mockClear() })

describe("gap list on the gap stage card", () => {
  it("a legacy pending gap (old registration path) still shows confirm / reject; confirm sends the human decision", async () => {
    fetchMock.mockResolvedValueOnce(response({ commit_position: 2, event_ids: ["e2"], result: { gap_candidate_id: "gap-1" } }))  // confirm
    renderGaps([pendingGap])
    expect(screen.getByText("现有文献覆盖了机制测量,但没有覆盖真实任务表现。")).toBeInTheDocument()
    expect(screen.getByText("待你裁决")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "拒绝" })).toBeEnabled()
    fireEvent.click(screen.getByRole("button", { name: "确认这个 gap" }))
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/gap-1/confirm"))).toHaveLength(1))
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/gap-1/confirm"))!
    expect(JSON.parse(init.body)).toMatchObject({ user_reason: "人审确认", expected_sequence: 1 })
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })

  it("offers the challenge button only on confirmed / corrected gaps, and decisions only on pending ones", () => {
    for (const status of ["pending", "rejected"] as const) {
      renderGaps([{ ...pendingGap, status }])
      expect(screen.queryByRole("button", { name: "对这个 gap 发起反证" })).not.toBeInTheDocument()
      cleanup()
    }
    for (const status of ["confirmed", "corrected"] as const) {
      renderGaps([{ ...pendingGap, status }])
      expect(screen.getByRole("button", { name: "对这个 gap 发起反证" })).toBeInTheDocument()
      expect(screen.queryByRole("button", { name: "确认这个 gap" })).not.toBeInTheDocument()
      cleanup()
    }
  })

  it("pre-fills a draft, creates nothing until signed, then creates a vacancy claim, opens a round and navigates", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).endsWith("/claims")) return response({ result: { claim_id: "c-9" } })
      if (String(url).endsWith("/review-rounds")) return response({ result: { review_round_id: "r-9" } })
      return response({ detail: String(url) }, 404)
    })
    renderGaps([{ ...pendingGap, status: "confirmed" }])
    fireEvent.click(screen.getByRole("button", { name: "对这个 gap 发起反证" }))
    const box = screen.getByLabelText("反证用 claim(空缺断言)") as HTMLTextAreaElement
    expect(box.value).toContain("没有覆盖真实任务表现")
    expect(fetchMock).not.toHaveBeenCalled()
    const sign = screen.getByRole("button", { name: "署名固化为 claim 并开审查轮" })
    fireEvent.change(box, { target: { value: "" } })
    expect(sign).toBeDisabled()
    fireEvent.change(box, { target: { value: "我改写的空缺断言。" } })
    fireEvent.click(sign)
    await waitFor(() => expect(window.location.pathname).toBe("/workspaces/w-1/rounds/r-9"))
    const claimCall = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/claims"))!
    expect(JSON.parse(claimCall[1].body)).toMatchObject({ text: "我改写的空缺断言。", kind: "vacancy", origin_gap_id: "gap-1" })
  })

  describe("challenge progress (display only)", () => {
    const withChallenge = (outcome: string, round_id: string | null = "r-1"): GapCandidate[] => [{ ...pendingGap, status: "confirmed", challenges: [{ claim_id: "c-1", claim_text: "目前没有文献覆盖真实任务表现", round_id, outcome }] }]

    it("shows reviewing / survived lines; the line opens its round in the focus panel", () => {
      renderGaps(withChallenge("open"))
      fireEvent.click(screen.getByRole("button", { name: /反证 claim「目前没有文献覆盖真实任务表现」· 反证中/ }))
      expect(onOpen).toHaveBeenCalledWith("r-1")
      cleanup()
      renderGaps(withChallenge("survived"))
      expect(screen.getByText(/反证结果:未能推翻/)).toBeInTheDocument()
      cleanup()
      renderGaps(withChallenge("open", null))
      expect(screen.getByText(/反证中/)).toBeInTheDocument()
      expect(screen.queryByRole("button", { name: /反证 claim/ })).not.toBeInTheDocument()
    })

    it("refuted: shows the re-judge prompt but leaves the gap status label untouched", () => {
      renderGaps(withChallenge("refuted"))
      expect(screen.getByText(/反证结果:已被推翻 — 这个 gap 可能需要你重新判断/)).toBeInTheDocument()
      expect(screen.getByText("已确认 gap")).toBeInTheDocument()
    })
  })
})

describe("现状 panel (gap stage focus panel, read-only)", () => {
  it("lists only decided-and-alive claims as surviving, counts the rest, shows confirmed facts, and opens a claim's latest round", () => {
    render(<LandscapePanel landscape={{ ...emptyLandscape,
      // 投影的 alive_claims 含未裁决的 c-2;c-3 被证伪不在 alive_claims
      alive_claims: [{ id: "c-1", text: "Repeated recall improves later access." }, { id: "c-2", text: "Still under review." }],
      claim_verdicts: { "c-1": "circumstantial", "c-2": "open", "c-3": "refuted" },
      confirmed_facts: [{ candidate_id: "f-1", claim_id: "c-1", claim_text: "Repeated recall improves later access.", relation: "supports", material_locator: "arxiv:2401.00001", decision_reason: "摘要直接报告了保持效应。" }],
      gaps: [{ ...pendingGap, status: "confirmed", challenges: [{ claim_id: "c-1", claim_text: "x", round_id: "r-1b", outcome: "circumstantial" }] }],
    }} rounds={[{ id: "r-1a", claim_id: "c-1" }, { id: "r-2", claim_id: "c-2" }, { id: "r-1b", claim_id: "c-1" }]} onOpen={onOpen} />)
    expect(screen.getByText("存活的 claim · 1")).toBeInTheDocument()
    const claim = screen.getByRole("button", { name: /Repeated recall improves later access/ })
    expect(claim).toHaveTextContent("有条件存活 · 来自 gap · 审查轮 02")
    expect(screen.queryByText("Still under review.")).not.toBeInTheDocument()
    expect(screen.getByText("另有 2 条 claim 未裁决或未存活，在「对抗」里。")).toBeInTheDocument()
    const facts = screen.getByText("已确认的取证事实 · 1").parentElement!
    expect(within(facts).getByText(/支持 · arxiv:2401.00001 → claim「Repeated recall im…」/)).toBeInTheDocument()
    expect(within(facts).getByText("摘要直接报告了保持效应。")).toBeInTheDocument()
    fireEvent.click(claim)
    expect(onOpen).toHaveBeenCalledWith("r-1b")
  })

  it("says so when there is nothing to lean on yet", () => {
    render(<LandscapePanel landscape={emptyLandscape} rounds={[]} onOpen={onOpen} />)
    expect(screen.getByText("还没有裁决为存活的 claim。")).toBeInTheDocument()
    expect(screen.getByText("还没有确认的取证事实。")).toBeInTheDocument()
  })
})
