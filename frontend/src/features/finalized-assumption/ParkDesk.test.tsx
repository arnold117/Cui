import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AppRouter } from "../../router"
import { ParkDesk } from "./ParkDesk"

const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
function view(captureId?: string) { return render(<AppRouter><ParkDesk captureId={captureId} /></AppRouter>) }

describe("sealed capture desk", () => {
  beforeEach(() => fetchMock.mockReset())
  it("keeps exact capture envelope for retry and displays the seal", async () => {
    fetchMock.mockResolvedValue(response({ library_id: "lib", captures: [] }))
    view(); const field = await screen.findByLabelText("捕获原始文本"); expect(screen.getByText("密封：Cui 不会读取")).toBeInTheDocument()
    fetchMock.mockReset().mockResolvedValueOnce(response({ detail: "offline" }, 503)).mockResolvedValueOnce(response({ commit_position: 0, event_ids: [], result: { capture_id: "p" }, fragment: { id: "p", original_text: "raw", status: "sealed", released: false, releases: [], forged_into: [] } })).mockResolvedValue(response({ library_id: "lib", captures: [{ id: "p", status: "sealed", released: false, releases: [], forged_into: [] }] }))
    fireEvent.change(field, { target: { value: "raw" } }); fireEvent.click(screen.getByRole("button", { name: "密封捕获" })); await screen.findByRole("alert"); fireEvent.click(screen.getByRole("button", { name: "密封捕获" }))
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/park-captures"))).toHaveLength(2))
    const posts = fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith("/park-captures") && init?.method === "POST"); expect(posts).toHaveLength(2); expect(posts[0][1].body).toBe(posts[1][1].body)
  })
  it("requires an open question before releasing into a new workspace", async () => {
    fetchMock.mockResolvedValueOnce(response({ id: "p", original_text: "raw", status: "sealed", released: false, releases: [], forged_into: [] })).mockResolvedValueOnce(response({ id: "u" })).mockResolvedValueOnce(response({ universe_id: "u", workspaces: [], pending_facts: [] })); view("p")
    fireEvent.click(await screen.findByRole("button", { name: "主动放行" })); expect(screen.getByRole("button", { name: "确认放行" })).toBeDisabled(); fireEvent.change(screen.getByLabelText("新的开放问题"), { target: { value: "What condition?" } }); expect(screen.getByRole("button", { name: "确认放行" })).toBeEnabled()
  })
})
