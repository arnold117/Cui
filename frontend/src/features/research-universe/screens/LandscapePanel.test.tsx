import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { WorkspaceLandscape } from "../types"
import { AppRouter } from "../../../router"
import { LandscapePanel } from "./LandscapePanel"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const onChanged = vi.fn()

const emptyLandscape: WorkspaceLandscape = {
  workspace_id: "w-1",
  question: { version_id: "q-1", text: "Why does X matter?" },
  alive_claims: [],
  claim_verdicts: {},
  confirmed_facts: [],
  gaps: [],
}
const landscapeWithPendingGap: WorkspaceLandscape = {
  ...emptyLandscape,
  gaps: [{
    id: "gap-1", workspace_id: "w-1",
    coverage_statement: "现有文献覆盖了机制测量,但没有覆盖真实任务表现。",
    search_record: { query: "X real-task", scope: "active", matched_locators: ["arxiv:2401.00001"], searched_at: "2026-09-02" },
    counterexample_invitation: "欢迎任何真实任务上的反例。",
    status: "pending", sequence: 1,
  }],
}

afterEach(() => cleanup())
beforeEach(() => { fetchMock.mockReset(); onChanged.mockClear() })

describe("landscape panel", () => {
  it("renders empty landscape and registers a gap candidate with a search record", async () => {
    fetchMock
      .mockResolvedValueOnce(response({ query: "X", group: "active", total: 1, results: [{ material_id: "m-1", source_locator: "arxiv:2401.00001", title: "X eval paper", matched_terms: 1, snippet: "…" }] }))  // corpus search
      .mockResolvedValueOnce(response({ commit_position: 1, event_ids: ["e1"], result: { gap_candidate_id: "gap-1" } }))  // propose
    const landscape: WorkspaceLandscape = emptyLandscape
    render(<LandscapePanel landscape={landscape} onChanged={onChanged} />)
    await screen.findByText("这一问,现状是什么、缺口在哪")
    fireEvent.click(screen.getByRole("button", { name: "登记一个 gap 候选" }))
    fireEvent.change(screen.getByLabelText("覆盖范围声明(哪些已被覆盖、缺口在哪)"), { target: { value: "现有文献覆盖了机制测量,但没有覆盖真实任务表现。" } })
    fireEvent.change(screen.getByLabelText("邀请反例"), { target: { value: "欢迎任何真实任务上的反例。" } })
    fireEvent.change(screen.getByLabelText("语料检索(active,供检索记录)"), { target: { value: "X real-task" } })
    fireEvent.click(screen.getByRole("button", { name: "检索语料" }))
    await screen.findByText("X eval paper")
    fireEvent.click(screen.getByRole("button", { name: "选取" }))
    fireEvent.click(screen.getByRole("button", { name: "提出 gap 候选" }))
    await waitFor(() => {
      const proposeCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/gap-candidates"))
      expect(proposeCall).toBeTruthy()
      const body = JSON.parse(proposeCall![1].body)
      expect(body.coverage_statement).toContain("真实任务表现")
      expect(body.matched_locators).toEqual(["arxiv:2401.00001"])
      expect(body.search_query).toBe("X real-task")
      expect(body.expected_sequence).toBe(0)
    })
    expect(onChanged).toHaveBeenCalled()
  })

  it("renders a pending gap and lets the human confirm it", async () => {
    fetchMock.mockResolvedValueOnce(response({ commit_position: 2, event_ids: ["e2"], result: { gap_candidate_id: "gap-1" } }))  // confirm
    render(<LandscapePanel landscape={landscapeWithPendingGap} onChanged={onChanged} />)
    await screen.findByText((content, el) => Boolean(el && el.tagName === "P" && content.includes("现有文献覆盖了机制测量,但没有覆盖真实任务表现")))
    fireEvent.click(screen.getByRole("button", { name: "确认这个 gap" }))
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/gap-1/confirm"))).toHaveLength(1))
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/gap-1/confirm"))!
    expect(JSON.parse(init.body)).toMatchObject({ user_reason: "人审确认", expected_sequence: 1 })
    expect(onChanged).toHaveBeenCalled()
  })

  it("shows alive claims and confirmed facts readback", async () => {
    render(<LandscapePanel landscape={{ ...emptyLandscape,
      alive_claims: [{ id: "c-1", text: "Repeated recall improves later access.", sequence: 2 }],
      claim_verdicts: { "c-1": "survived" },
      confirmed_facts: [{ candidate_id: "f-1", claim_id: "c-1", claim_text: "Repeated recall improves later access.", relation: "supports", material_locator: "arxiv:2401.00001" }],
    }} onChanged={onChanged} />)
    await waitFor(() => expect(screen.getAllByText(/Repeated recall improves later access/).length).toBeGreaterThanOrEqual(2))
    expect(screen.getByText(/已确认取证 · supports/)).toBeInTheDocument()
    expect(screen.getByText(/裁决:存活/)).toBeInTheDocument()
  })
  describe("challenge a confirmed gap", () => {
    const withStatus = (status: "pending" | "confirmed" | "corrected" | "rejected"): WorkspaceLandscape => ({ ...landscapeWithPendingGap, gaps: [{ ...landscapeWithPendingGap.gaps[0], status }] })
    const renderPanel = (l: WorkspaceLandscape) => render(<AppRouter><LandscapePanel landscape={l} onChanged={onChanged} /></AppRouter>)

    it("offers the challenge button only on confirmed / corrected gaps", () => {
      for (const status of ["pending", "rejected"] as const) {
        renderPanel(withStatus(status))
        expect(screen.queryByRole("button", { name: "对这个 gap 发起反证" })).not.toBeInTheDocument()
        cleanup()
      }
      for (const status of ["confirmed", "corrected"] as const) {
        renderPanel(withStatus(status))
        expect(screen.getByRole("button", { name: "对这个 gap 发起反证" })).toBeInTheDocument()
        cleanup()
      }
    })

    it("pre-fills a draft, creates nothing until signed, then creates a vacancy claim, opens a round and navigates", async () => {
      fetchMock.mockImplementation(async (url: string) => {
        if (String(url).endsWith("/claims")) return response({ result: { claim_id: "c-9" } })
        if (String(url).endsWith("/review-rounds")) return response({ result: { review_round_id: "r-9" } })
        return response({ detail: String(url) }, 404)
      })
      renderPanel(withStatus("confirmed"))
      fireEvent.click(screen.getByRole("button", { name: "对这个 gap 发起反证" }))
      const box = screen.getByLabelText("反证用 claim(空缺断言)") as HTMLTextAreaElement
      expect(box.value).toContain("没有覆盖真实任务表现")
      expect(fetchMock).not.toHaveBeenCalled()
      const sign = screen.getByRole("button", { name: "署名固化为 claim 并开审查轮" })
      fireEvent.change(box, { target: { value: "" } })
      expect(sign).toBeDisabled()
      fireEvent.change(box, { target: { value: "我改写的空缺断言。" } })
      fireEvent.click(sign)
      await waitFor(() => expect(window.location.pathname).toBe("/review-rounds/r-9"))
      const claimCall = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/claims"))!
      expect(JSON.parse(claimCall[1].body)).toMatchObject({ text: "我改写的空缺断言。", kind: "vacancy", origin_gap_id: "gap-1" })
      expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/claims/c-9/review-rounds") || String(u).endsWith("/review-rounds"))).toBe(true)
    })
  })

  describe("challenge progress on the gap card (display only)", () => {
    const withChallenge = (outcome: string, round_id: string | null = "r-1"): WorkspaceLandscape => ({ ...landscapeWithPendingGap, gaps: [{ ...landscapeWithPendingGap.gaps[0], status: "confirmed", challenges: [{ claim_id: "c-1", claim_text: "目前没有文献覆盖真实任务表现", round_id, outcome }] }] })
    const renderPanel = (l: WorkspaceLandscape) => render(<AppRouter><LandscapePanel landscape={l} onChanged={onChanged} /></AppRouter>)

    it("shows reviewing / survived lines with a link to the round", () => {
      renderPanel(withChallenge("open"))
      expect(screen.getByText(/反证中/)).toBeInTheDocument()
      fireEvent.click(screen.getByRole("button", { name: "查看审查轮" }))
      expect(window.location.pathname).toBe("/review-rounds/r-1")
      cleanup()
      renderPanel(withChallenge("survived"))
      expect(screen.getByText(/反证结果:未能推翻/)).toBeInTheDocument()
    })

    it("refuted: shows the re-judge prompt but leaves the gap status label untouched", () => {
      renderPanel(withChallenge("refuted"))
      expect(screen.getByText(/反证结果:已被推翻 — 这个 gap 可能需要你重新判断/)).toBeInTheDocument()
      expect(screen.getByText(/已确认 gap/)).toBeInTheDocument()
    })
  })
})
