import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppRouter } from "../../../router"
import { WorkspaceDesk } from "./WorkspaceDesk"

const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const base = { id: "w", question: { version_id: "q", text: "Q" }, sequence: 9, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [], park_release_refs: [], materials: [] }
afterEach(() => cleanup())
beforeEach(() => fetchMock.mockReset())
function view() { return render(<AppRouter><WorkspaceDesk workspaceId="w" /></AppRouter>) }

describe("workspace material entry", () => {
  it("adds a neutral material and lists it with purpose and parse status", async () => {
    fetchMock.mockResolvedValueOnce(response(base))
      .mockResolvedValueOnce(response({ commit_position: 1, event_ids: ["e1"], result: { material_id: "m-1" }, fragment: { ...base, materials: [{ id: "m-1", excerpt: "Paper A observes Z.", source_locator: "Paper A", parse_status: "parsed", purpose: "evidence" }] } }))
      .mockResolvedValueOnce(response({ ...base, materials: [{ id: "m-1", excerpt: "Paper A observes Z.", source_locator: "Paper A", parse_status: "parsed", purpose: "evidence" }] }))
    view()
    await screen.findByText("Q")
    fireEvent.change(screen.getByLabelText("来源（可选）"), { target: { value: "Paper A" } })
    fireEvent.change(screen.getByLabelText("摘录或观察"), { target: { value: "Paper A observes Z." } })
    fireEvent.click(screen.getByRole("button", { name: "带入材料" }))
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/materials"))).toHaveLength(1))
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/materials"))
    expect(JSON.parse(init.body)).toMatchObject({ excerpt: "Paper A observes Z.", source_locator: "Paper A", parse_status: "parsed", purpose: "evidence", expected_sequence: 0 })
    expect(await screen.findByText("Paper A observes Z.")).toBeInTheDocument()
    expect(screen.getByText(/Paper A · 待取证材料 · 已解析/)).toBeInTheDocument()
  })

  it("marks an unparsable material failed while landing neutrally", async () => {
    fetchMock.mockResolvedValueOnce(response(base))
      .mockResolvedValueOnce(response({ commit_position: 1, event_ids: ["e1"], result: { material_id: "m-1" } }))
      .mockResolvedValueOnce(response({ ...base, materials: [{ id: "m-1", excerpt: "garbled", source_locator: null, parse_status: "failed", purpose: "evidence" }] }))
    view()
    await screen.findByText("Q")
    fireEvent.change(screen.getByLabelText("摘录或观察"), { target: { value: "garbled" } })
    fireEvent.click(screen.getByLabelText("这段摘录我无法判断"))
    fireEvent.click(screen.getByRole("button", { name: "带入材料" }))
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/materials"))).toHaveLength(1))
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/materials"))
    expect(JSON.parse(init.body)).toMatchObject({ parse_status: "failed", purpose: "evidence", expected_sequence: 0 })
    expect(await screen.findByText("garbled")).toBeInTheDocument()
    expect(screen.getByText(/无来源定位 · 待取证材料 · 无法判断/)).toBeInTheDocument()
  })

  it("enters a reference material without asserting support or refusal", async () => {
    fetchMock.mockResolvedValueOnce(response(base))
      .mockResolvedValueOnce(response({ commit_position: 1, event_ids: ["e1"], result: { material_id: "m-1" } }))
      .mockResolvedValueOnce(response({ ...base, materials: [{ id: "m-1", excerpt: "context note", source_locator: null, parse_status: "parsed", purpose: "reference" }] }))
    view()
    await screen.findByText("Q")
    fireEvent.change(screen.getByLabelText("摘录或观察"), { target: { value: "context note" } })
    fireEvent.click(screen.getByLabelText("只作探索参考"))
    fireEvent.click(screen.getByRole("button", { name: "带入材料" }))
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/materials"))).toHaveLength(1))
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/materials"))
    expect(JSON.parse(init.body)).toMatchObject({ purpose: "reference", expected_sequence: 0 })
    expect(await screen.findByText("context note")).toBeInTheDocument()
    expect(screen.getByText(/无来源定位 · 只作探索参考 · 已解析/)).toBeInTheDocument()
  })
})
