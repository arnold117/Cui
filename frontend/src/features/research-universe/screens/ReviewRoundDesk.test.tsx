import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ReviewRoundDesk } from "./ReviewRoundDesk"
import { researchUniverse } from "../api"

vi.mock("../api", () => ({ researchUniverse: { reviewRound: vi.fn() } }))

const challenge = { id: "ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending" as const, attack_surface: "边界尚未说明", why_it_matters: "无法判断适用范围", self_check_method: "写下一种失效条件", provenance: { basis_refs: ["question", "claim"], uncertainty: "待检验" } }

describe("ReviewRoundDesk exits", () => {
  it("keeps the challenge pending and links back to its workspace and universe", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue({ id: "r-1", workspace_id: "w-1", question_snapshot: { version_id: "q-1", text: "问题" }, claim_snapshot: { id: "c-1", version_id: "cv-1", text: "主张" }, challenges: [challenge] })
    render(<ReviewRoundDesk roundId="r-1" />)
    expect(await screen.findByText("边界尚未说明")).toBeInTheDocument()
    expect(screen.getByText(/挑战仍待回应/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "回工作区继续探索" })).toHaveAttribute("href", "/workspaces/w-1")
    expect(screen.getByRole("link", { name: "回研究宇宙查看上下文" })).toHaveAttribute("href", "/")
    expect(screen.queryByRole("button", { name: /裁决|答辩/ })).not.toBeInTheDocument()
  })
})
