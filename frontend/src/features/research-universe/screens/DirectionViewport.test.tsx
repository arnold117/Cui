import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { DirectionViewport } from "./DirectionViewport"
import { AppRouter } from "../../../router"
import { researchUniverse } from "../api"
import type { Direction } from "../types"

vi.mock("../api", () => ({
  researchUniverse: { direction: vi.fn(), active: vi.fn(), createWorkspace: vi.fn(), rephraseDirection: vi.fn() },
  command: (payload: Record<string, unknown>, expected_sequence: number) => ({ ...payload, command_id: "cmd", expected_sequence }),
}))

const directionFixture = (overrides: Partial<Direction> = {}): Direction => ({
  id: "d1",
  proposition: { version_id: "pv1", text: "A long-term thesis." },
  status: "active",
  sequence: 1,
  rephrase_history: [],
  attached_workspaces: [],
  crystallizations: [],
  ...overrides,
})

describe("DirectionViewport", () => {
  it("renders the proposition, attached workspaces, and crystallizations", async () => {
    vi.mocked(researchUniverse.direction).mockResolvedValue(directionFixture({
      attached_workspaces: [{ link_id: "l1", workspace_id: "w1", question: "Why does X happen?", position: "exploring", pending_fact_count: 2 }],
      crystallizations: [{ crystallization_id: "x1", workspace_id: "w1", conclusion_id: "c1", conclusion_text: "The answer is X.", conclusion_type: "tentative_answer" }],
    }))
    render(<AppRouter><DirectionViewport directionId="d1" /></AppRouter>)
    expect(await screen.findByRole("heading", { name: "我正在追什么" })).toBeInTheDocument()
    expect(screen.getByText("A long-term thesis.")).toBeInTheDocument()
    expect(screen.getByText(/待回应 2/)).toBeInTheDocument()
    expect(screen.getByText("The answer is X.")).toBeInTheDocument()
  })

  it("rephrase desk preserves the prior proposition and unnamed explicitly clears it", async () => {
    let current = directionFixture()
    vi.mocked(researchUniverse.direction).mockImplementation(() => Promise.resolve(current))
    vi.mocked(researchUniverse.rephraseDirection).mockImplementation(() => {
      current = directionFixture({ proposition: { version_id: "pv2", text: null }, sequence: 2, rephrase_history: [{ prior_proposition_version_id: "pv1", prior_proposition_text: "A long-term thesis.", new_proposition_version_id: "pv2", new_proposition_text: null, change_type: "unnamed", user_reason: "old is insufficient", source_conclusion_ref: "c1" }] })
      return Promise.resolve({ commit_position: 1, event_ids: ["e"], result: { direction_id: "d1", new_proposition_version_id: "pv2" }, fragment: current })
    })
    render(<AppRouter><DirectionViewport directionId="d1" rephraseIntent sourceConclusionRef="c1" /></AppRouter>)
    await screen.findByRole("heading", { name: "现在我想追什么" })
    expect(screen.getByText(/此前我在追：A long-term thesis/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("radio", { name: /暂不命名/ }))
    // unnamed leaves the new proposition empty and disabled, never an empty-string masquerade
    const textarea = screen.getByLabelText("现在我想追") as HTMLTextAreaElement
    expect(textarea).toBeDisabled()
    expect(textarea).toHaveValue("")
    fireEvent.change(screen.getByLabelText("为什么现在要这样改"), { target: { value: "old is insufficient" } })
    fireEvent.click(screen.getByRole("button", { name: "确认新命题" }))
    await waitFor(() => expect(researchUniverse.rephraseDirection).toHaveBeenCalledWith("d1", expect.objectContaining({ change_type: "unnamed", new_proposition: null, source_conclusion_ref: "c1" })))
    await screen.findByText("暂不命名")
  })
})
