import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { DialogueDesk } from "./DialogueDesk"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

const desk = { id: "w-1", question: { version_id: "q-1", text: "Why does RLHF improve reasoning?" }, sequence: 0, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [] }
const candidates = [
  { material_id: "m1", locator: "arxiv:2401.00009", title: "RLHF reasoning paper", reason: "直接相关" },
  { material_id: "m2", locator: "arxiv:2402.00001", title: "Reasoning evaluation", reason: "相关评测" },
  { material_id: "m3", locator: "arxiv:2402.00002", title: "Preference alignment", reason: "对齐机制" },
]

function mockJourney() {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url)
    const method = init?.method ?? "GET"
    if (path.endsWith("/api/v2/workspaces/w-1") && method === "GET") return response(desk)
    if (path.endsWith("/dialogue/literature-search")) return response({ query: "rlhf", candidates })
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

afterEach(() => cleanup())
beforeEach(() => { fetchMock.mockReset(); window.sessionStorage.clear() })

describe("literature dialogue desk", () => {
  it("walks the wedge journey end to end", async () => {
    mockJourney()
    render(<DialogueDesk workspaceId="w-1" />)
    await screen.findByText("Why does RLHF improve reasoning?")

    fireEvent.click(screen.getByRole("button", { name: "让 Cui 找文献" }))
    await screen.findByText("RLHF reasoning paper")
    for (const button of screen.getAllByRole("button", { name: "选取" })) fireEvent.click(button)
    await waitFor(() => expect(screen.getByText(/已选 3 篇/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole("button", { name: "梳理现状" }))
    await screen.findByText(/还没有被覆盖的/)

    fireEvent.change(screen.getByLabelText("claim"), { target: { value: "RLHF 提升推理是因为对齐偏好。" } })
    fireEvent.click(screen.getByRole("button", { name: "固化 claim 并开审查轮" }))
    await screen.findByText(/去审查轮回应与裁决/)

    fireEvent.click(screen.getByRole("button", { name: /用所选文献发难/ }))
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/literature-challenges"))
      expect(call).toBeTruthy()
      const body = JSON.parse(call![1].body as string)
      expect(body.material_ids).toEqual(["m1", "m2", "m3"])
    })

    fireEvent.click(screen.getByRole("button", { name: "起草 gap" }))
    await screen.findByDisplayValue(/覆盖了评测方法/)
    fireEvent.click(screen.getByRole("button", { name: "提交并确认这个 gap" }))
    await waitFor(() => expect(screen.getByText(/已确认 gap ×1/)).toBeInTheDocument())
    const propose = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/gap-candidates") )
    expect(propose).toBeTruthy()
    expect(JSON.parse(propose![1].body as string).matched_locators).toEqual(["arxiv:2401.00009", "arxiv:2402.00001", "arxiv:2402.00002"])

    fireEvent.click(screen.getByRole("button", { name: "生成草稿" }))
    await screen.findByText(/Existing work covers RLHF evaluations/)
    fireEvent.click(screen.getByRole("button", { name: "下载 .md" }))
  })
})


describe("fresh-question orientation gate", () => {
  it("offers hypotheses and keyword chips for a brand-new question", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const path = String(url)
      const method = init?.method ?? "GET"
      if (path.endsWith("/api/v2/workspaces/w-fresh") && method === "GET") return response({ ...desk, id: "w-fresh" })
      if (path.endsWith("/dialogue/orientation")) return response({ hypotheses: ["RLHF 通过偏好对齐减少漂移从而提升推理"], keywords: ["RLHF reasoning", "偏好对齐"] })
      if (path.endsWith("/dialogue/literature-search")) return response({ query: "RLHF reasoning", candidates: [] })
      return response({ detail: path }, 404)
    })
    render(<DialogueDesk workspaceId="w-fresh" />)
    await screen.findByText(/这是一个全新问题/)
    fireEvent.click(screen.getByRole("button", { name: "让 Cui 给出假设与关键词" }))
    await screen.findByText(/RLHF 通过偏好对齐减少漂移从而提升推理/)
    fireEvent.click(screen.getByRole("button", { name: "RLHF reasoning" }))
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/dialogue/literature-search"))
      expect(call).toBeTruthy()
      expect(JSON.parse(call![1].body as string).query).toBe("RLHF reasoning")
    })
  })
})
