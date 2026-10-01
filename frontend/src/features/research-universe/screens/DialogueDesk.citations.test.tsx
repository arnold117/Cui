import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest"
import { AppRouter } from "../../../router"
import { DialogueDesk } from "./DialogueDesk"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const desk = { id: "w-1", question: { version_id: "q-1", text: "Why does RLHF improve reasoning?" }, sequence: 0, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [] }
const candidates = [{ material_id: "m1", locator: "arxiv:2401.00009", title: "RLHF reasoning paper", reason: "r", source: "corpus", stance: "s", relation: { kind: "supports", note: "n" } }]

const gapWithCheck = { coverage_statement: "文献覆盖了评测方法,但没有覆盖推理链真实应用 [arxiv:2401.00009]。", search_query: "q", counterexample_invitation: "请指正。", citation_check_status: "ok", citation_checks: [{ sentence: "文献覆盖了评测方法 [arxiv:2401.00009]。", locator: "arxiv:2401.00009", verdict: "unsupported", scope: "abstract" }] }

function mockApi() {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url)
    if (path.endsWith("/api/v2/workspaces/w-1") && (init?.method ?? "GET") === "GET") return response(desk)
    if (path.endsWith("/dialogue/gap-draft")) return response(gapWithCheck)
    return response({ detail: path }, 404)
  })
}

const base = { v: 2, hypothesesText: "h", hypothesesDone: true, keywordsText: "", selectedKeywords: [], candidates, selected: ["arxiv:2401.00009"], searchQuery: "q", summary: "## 这几篇覆盖了什么\n评测。", claimText: "c", roundId: "r1", claimAck: true, confirmedGapIds: [] as string[] }
const seed = (extra: Record<string, unknown>) => window.sessionStorage.setItem("cui:dialogue-draft:v2:w-1", JSON.stringify({ ...base, workspaceId: "w-1", ...extra, savedAt: new Date().toISOString() }))
const renderDesk = () => render(<AppRouter><DialogueDesk workspaceId="w-1" /></AppRouter>)

afterEach(() => { cleanup(); window.sessionStorage.clear() })
beforeEach(() => { fetchMock.mockReset(); window.sessionStorage.clear(); mockApi() })

describe("引用核对 (mark-only list under each draft)", () => {
  it("lists unsupported/unselected citations with the scope-specific message under the related-work draft", async () => {
    seed({ confirmedGapIds: ["g1"], relatedWork: "段落。", relatedWorkCheck: { citation_check_status: "ok", citation_checks: [
      { sentence: "RLHF 提升了推理 [arxiv:2401.00009]。", locator: "arxiv:2401.00009", verdict: "unsupported", scope: "abstract" },
      { sentence: "另一句 [arxiv:2402.00001]。", locator: "arxiv:2402.00001", verdict: "unsupported", scope: "excerpt" },
      { sentence: "第三句 [arxiv:2402.00002]。", locator: "arxiv:2402.00002", verdict: "unsupported", scope: "full" },
      { sentence: "没选的 [arxiv:9999.99999]。", locator: "arxiv:9999.99999", verdict: "not_selected", scope: null },
      { sentence: "没问题 [arxiv:2401.00009]。", locator: "arxiv:2401.00009", verdict: "supported", scope: "full" },
    ] } })
    renderDesk()
    await screen.findByText(/RLHF 提升了推理/, {}, { timeout: 3000 })
    expect(screen.getByText(/摘要中未找到依据\(可能在全文\)/)).toBeInTheDocument()
    expect(screen.getByText(/摘录中未找到依据/)).toBeInTheDocument()
    expect(screen.getByText(/全文中未找到依据/)).toBeInTheDocument()
    expect(screen.getByText(/引用了未选入的文献/)).toBeInTheDocument()
    expect(screen.queryByText(/没问题/)).not.toBeInTheDocument()
  })

  it("shows one all-pass line, and says so when the check is unavailable", async () => {
    seed({ confirmedGapIds: ["g1"], relatedWork: "段落。", relatedWorkCheck: { citation_check_status: "ok", citation_checks: [{ sentence: "s [arxiv:2401.00009]", locator: "arxiv:2401.00009", verdict: "supported", scope: "full" }] } })
    renderDesk()
    await screen.findByText("引用核对:全部可在所选文献中找到依据", {}, { timeout: 3000 })
    cleanup()
    seed({ confirmedGapIds: ["g1"], relatedWork: "段落。", relatedWorkCheck: { citation_check_status: "unavailable", citation_checks: [] } })
    renderDesk()
    await screen.findByText(/引用核对暂不可用/, {}, { timeout: 3000 })
  })

  it("renders the gap-draft check from the endpoint response", async () => {
    seed({})
    renderDesk()
    fireEvent.click(await screen.findByRole("button", { name: "让 Cui 起草 gap 候选" }, { timeout: 3000 }))
    await screen.findByText(/摘要中未找到依据\(可能在全文\)/, {}, { timeout: 3000 })
  })

  it("shows the summary check under the coverage summary", async () => {
    seed({ roundId: undefined, claimAck: false, summaryCheck: { citation_check_status: "ok", citation_checks: [{ sentence: "覆盖了 [arxiv:2401.00009]", locator: "arxiv:2401.00009", verdict: "unsupported", scope: "full" }] } })
    renderDesk()
    await screen.findByText(/全文中未找到依据/, {}, { timeout: 3000 })
  })
})
