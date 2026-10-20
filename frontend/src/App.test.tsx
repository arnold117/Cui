import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import App from "./App"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)

function response(body: unknown) { return new Response(JSON.stringify(body), { status: 200 }) }

describe("production routes", () => {
  beforeEach(() => { fetchMock.mockReset(); window.history.replaceState({}, "", "/") })

  it("renders the native start station at the root without loading legacy UI", async () => {
    fetchMock.mockResolvedValueOnce(response({ id: "universe-1", library_id: "local-library" }))
    render(<App />)
    expect(screen.getByRole("heading", { name: "从哪里开始？" })).toBeInTheDocument()
    expect(screen.queryByText("PARK")).not.toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v2/universes/active"))
    expect(screen.getByText("研究宇宙已就绪")).toBeInTheDocument()
  })

  it("renders archive on direct archive location using only its read endpoint", async () => {
    window.history.replaceState({}, "", "/archive")
    fetchMock.mockResolvedValueOnce(response({ artifacts: [] }))
    render(<App />)
    expect(screen.getByRole("heading", { name: "旧轨迹，保持原样。" })).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v2/legacy-archive"))
    expect(fetchMock.mock.calls.every(([url]) => !String(url).includes("/api/v1"))).toBe(true)
  })

  it("opens an old artifact deep link as read-only archive detail", async () => {
    window.history.replaceState({}, "", "/artifact/old-42")
    fetchMock.mockResolvedValueOnce(response({ artifacts: [] })).mockResolvedValueOnce(response({ artifact: { id: "old-42", kind: "idea", goal: "old goal", title: "Old idea", created_at: "2025-01-01", updated_at: "2025-01-01" } })).mockResolvedValueOnce(response({ events: [] }))
    render(<App />)
    expect(screen.getByText(/已从退役路径/)).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v2/legacy-archive/artifacts/old-42"))
    expect(screen.queryByRole("heading", { name: "从哪里开始？" })).not.toBeInTheDocument()
  })

  it("renders the native PARK desk and keeps invalid paths explicit", () => {
    window.history.replaceState({}, "", "/park")
    const view = render(<App />)
    expect(screen.getByRole("heading", { name: "先存放，不让 Cui 介入。" })).toBeInTheDocument()
    expect(screen.getByText("密封：Cui 不会读取")).toBeInTheDocument()
    view.unmount()
    window.history.replaceState({}, "", "/archive/not-a-real-route")
    const invalidArchive = render(<App />)
    expect(screen.getByRole("heading", { name: "这个位置不存在。" })).toBeInTheDocument()
    expect(screen.getByText("/archive/not-a-real-route")).toBeInTheDocument()
    invalidArchive.unmount()
    window.history.replaceState({}, "", "/not-a-route")
    render(<App />)
    expect(screen.getByRole("heading", { name: "这个位置不存在。" })).toBeInTheDocument()
  })

  it("redirects the retired dialogue path to the workspace journey page", async () => {
    window.history.replaceState({}, "", "/workspaces/w-1/dialogue")
    fetchMock.mockResolvedValue(response({ id: "w-1", question: { version_id: "q", text: "Journey question" }, sequence: 1, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [] }))
    render(<App />)
    await waitFor(() => expect(window.location.pathname).toBe("/workspaces/w-1"))
    expect(await screen.findByRole("heading", { name: "Journey question" })).toBeInTheDocument()
    expect(screen.getByRole("list", { name: "会话阶段" })).toBeInTheDocument()
  })

  it("reacts to programmatic pathname and query-only history changes", async () => {
    fetchMock.mockResolvedValue(response({ universe: null }))
    render(<App />)
    window.history.pushState({}, "", "/not-a-route")
    expect(await screen.findByRole("heading", { name: "这个位置不存在。" })).toBeInTheDocument()
    window.history.pushState({}, "", "/__prototype/research-universe?variant=A")
    expect(await screen.findByText(/PROTOTYPE · A/)).toBeInTheDocument()
  })
})

describe("review round routes (S2)", () => {
  beforeEach(() => { fetchMock.mockReset(); window.history.replaceState({}, "", "/") })
  const desk = { id: "w-1", question: { version_id: "q", text: "Journey question" }, sequence: 1, note: null, note_revisions: [], anchors: [], claims: [{ id: "c-1", text: "被审的 claim" }], review_rounds: [{ id: "r-1", claim_id: "c-1", claim_snapshot: { text: "被审的 claim" }, question_snapshot: { text: "Journey question" }, verdict: null }], pending_challenges: [], materials: [] }
  const round = { id: "r-1", workspace_id: "w-1", question_snapshot: { version_id: "q", text: "Journey question" }, claim_snapshot: { id: "c-1", version_id: "cv-1", text: "被审的 claim" }, sequence: 1, verdict: null, challenges: [{ id: "ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending", sequence: 1, attack_surface: "边界尚未说明", why_it_matters: "w", self_check_method: "s", answers: [] }], ledger: { answered: [], deferred: [], pending: [], brought_unconfirmed: [] }, rounds: [] }
  const serve = (gate: Promise<unknown> = Promise.resolve()) => fetchMock.mockImplementation(async (url: string) => {
    if (url === "/api/v2/review-rounds/r-1") { await gate; return response(round) }
    if (url === "/api/v2/workspaces/w-1") return response(desk)
    return new Response(JSON.stringify({ detail: url }), { status: 404 })
  })

  it("/workspaces/:id/rounds/:rid opens the round in the right-side panel beside the journey; 收起 closes it", async () => {
    window.history.replaceState({}, "", "/workspaces/w-1/rounds/r-1")
    serve()
    render(<App />)
    const panel = await screen.findByRole("complementary", { name: "聚焦面" })
    expect(await within(panel).findByText("边界尚未说明")).toBeInTheDocument()
    // 左栏仍在:问题标题 + 对抗卡,打开的那条 claim 有标记
    expect(screen.getByRole("heading", { name: "Journey question" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /被审的 claim/ })).toHaveAttribute("aria-current", "true")
    fireEvent.click(within(panel).getByRole("button", { name: "收起" }))
    await waitFor(() => expect(window.location.pathname).toBe("/workspaces/w-1"))
    expect(within(screen.getByRole("complementary", { name: "聚焦面" })).getByText(/点一条 claim，它的审查轮在这里打开/)).toBeInTheDocument()
  })

  it("/review-rounds/:rid shows a placeholder while locating the workspace, then replaces itself with the journey route", async () => {
    window.history.pushState({}, "", "/review-rounds/r-1")
    const depth = window.history.length
    let open!: () => void
    serve(new Promise<void>((resolve) => { open = resolve }))
    render(<App />)
    expect(screen.getByText("正在定位这一轮所在的问题…")).toBeInTheDocument()
    open()
    await waitFor(() => expect(window.location.pathname).toBe("/workspaces/w-1/rounds/r-1"))
    expect(window.history.length).toBe(depth) // replace:旧地址不留在历史里
    expect(await within(await screen.findByRole("complementary", { name: "聚焦面" })).findByText("边界尚未说明")).toBeInTheDocument()
  })

  it("/review-rounds/:rid for a round that does not exist renders NotFound", async () => {
    window.history.replaceState({}, "", "/review-rounds/missing")
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "review round not found" }), { status: 404 }))
    render(<App />)
    expect(await screen.findByRole("heading", { name: "这个位置不存在。" })).toBeInTheDocument()
    expect(screen.getByText("/review-rounds/missing")).toBeInTheDocument()
    expect(window.location.pathname).toBe("/review-rounds/missing")
  })
})
