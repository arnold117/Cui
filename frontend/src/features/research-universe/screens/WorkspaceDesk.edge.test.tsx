import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppRouter } from "../../../router"
import { WorkspaceDesk } from "./WorkspaceDesk"

const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock)
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const base = { id: "w", question: { version_id: "q", text: "Q" }, sequence: 9, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], park_release_refs: [] }
afterEach(() => cleanup())
beforeEach(() => fetchMock.mockReset())
function view(desk: Record<string, unknown>) {
  fetchMock.mockResolvedValue(response({ ...base, ...desk }))
  return render(<AppRouter><WorkspaceDesk workspaceId="w" /></AppRouter>)
}

describe("workspace research edge status", () => {
  it("labels an answered challenge as answered and awaiting a verdict", async () => {
    view({ pending_challenges: [{ id: "ch-1", review_round_id: "r-1", claim_id: "c-1", attack_surface: "替代解释未排除", status: "answered", answers: [{ version_id: "av-1", text: "reply", provisional_anchor_refs: [] }] }] })
    expect(await screen.findByText("已回应 · 待裁决")).toBeInTheDocument()
    expect(screen.getByText("替代解释未排除")).toBeInTheDocument()
    expect(screen.getByRole("link")).toHaveAttribute("href", "/review-rounds/r-1")
  })
  it("shows no pending fact when the projection drops terminal challenges", async () => {
    view({ pending_challenges: [] })
    expect(await screen.findByText("尚无待回应事实。")).toBeInTheDocument()
  })
})
