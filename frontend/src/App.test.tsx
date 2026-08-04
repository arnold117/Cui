import { render, screen, waitFor } from "@testing-library/react"
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

  it("explains retired, invalid archive, and unknown paths instead of falling through to root", () => {
    window.history.replaceState({}, "", "/park")
    const view = render(<App />)
    expect(screen.getByRole("heading", { name: "这里不再是研究宇宙的入口。" })).toBeInTheDocument()
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

  it("reacts to programmatic pathname and query-only history changes", async () => {
    fetchMock.mockResolvedValue(response({ universe: null }))
    render(<App />)
    window.history.pushState({}, "", "/not-a-route")
    expect(await screen.findByRole("heading", { name: "这个位置不存在。" })).toBeInTheDocument()
    window.history.pushState({}, "", "/__prototype/research-universe?variant=A")
    expect(await screen.findByText(/PROTOTYPE · A/)).toBeInTheDocument()
  })
})
