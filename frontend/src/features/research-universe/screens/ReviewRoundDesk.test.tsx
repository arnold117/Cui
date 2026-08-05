import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ReviewRoundDesk } from "./ReviewRoundDesk"
import { researchUniverse } from "../api"
import { AppRouter } from "../../../router"

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api")
  return { ...actual, researchUniverse: {
    reviewRound: vi.fn(),
    answerChallenge: vi.fn(),
    deferChallenge: vi.fn(),
    withdrawChallenge: vi.fn(),
    confirmVerdict: vi.fn(),
    startReview: vi.fn(),
    active: vi.fn(),
    createWorkspace: vi.fn(),
    desk: vi.fn(),
    addMaterial: vi.fn(),
    proposeEvidenceCandidate: vi.fn(),
    confirmEvidence: vi.fn(),
    correctEvidence: vi.fn(),
    rejectEvidence: vi.fn(),
    withdrawEvidence: vi.fn(),
  } }
})

const challenge = { id: "ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending" as const, sequence: 1, attack_surface: "边界尚未说明", why_it_matters: "无法判断适用范围", self_check_method: "写下一种失效条件", answers: [], provenance: { basis_refs: ["question", "claim"], uncertainty: "待检验" } }
const snapshot = { id: "c-1", version_id: "cv-1", text: "主张" }
function makeRound(overrides: Record<string, unknown> = {}) {
  return { id: "r-1", workspace_id: "w-1", question_snapshot: { version_id: "q-1", text: "问题" }, claim_snapshot: snapshot, sequence: 1, verdict: null, challenges: [challenge], ledger: { answered: [], deferred: [], pending: [challenge], brought_unconfirmed: [] }, rounds: [], ...overrides }
}
const responded = <T extends Record<string, unknown>>(payload: T) => ({ commit_position: 2, event_ids: [] as string[], result: payload })

afterEach(() => cleanup())

describe("ReviewRoundDesk review lifecycle", () => {
  it("keeps the challenge pending, links back, and exposes Slice 3 answer/verdict surfaces", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound())
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    expect(await screen.findByText("边界尚未说明")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "回工作区继续探索" })).toHaveAttribute("href", "/workspaces/w-1")
    expect(screen.getByRole("link", { name: "回研究宇宙查看上下文" })).toHaveAttribute("href", "/")
    expect(screen.getByLabelText("我目前的回应")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "保存答辩" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "作出本轮裁决" })).toBeInTheDocument()
  })

  it("saves an answer, keeps the challenge open, and shows the saved reply", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.answerChallenge).mockResolvedValue(responded({ challenge_id: "ch-1", review_round_id: "r-1", answer_version_id: "av-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ challenges: [{ ...challenge, status: "answered", sequence: 2, answers: [{ version_id: "av-1", text: "my reply", provisional_anchor_refs: [] }] }], ledger: { answered: [{ ...challenge, status: "answered", answers: [{ version_id: "av-1", text: "my reply", provisional_anchor_refs: [] }] }], deferred: [], pending: [], brought_unconfirmed: [] } }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.change(screen.getByLabelText("我目前的回应"), { target: { value: "my reply" } })
    fireEvent.click(screen.getByRole("button", { name: "保存答辩" }))
    await waitFor(() => expect(researchUniverse.answerChallenge).toHaveBeenCalledWith("ch-1", expect.objectContaining({ answer_text: "my reply", expected_sequence: 1, provisional_anchor_refs: [] })))
    expect(await screen.findByText("my reply")).toBeInTheDocument()
    expect(screen.getByText(/答辩已保存，挑战仍待裁决/)).toBeInTheDocument()
  })

  it("defers a challenge with a revisit condition and closes it", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.deferChallenge).mockResolvedValue(responded({ challenge_id: "ch-1", review_round_id: "r-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ challenges: [{ ...challenge, status: "deferred", sequence: 2, defer: { reason: "暂缓这条挑战", condition: "读到 Paper A 之后" } }], ledger: { answered: [], deferred: [{ ...challenge, status: "deferred" }], pending: [], brought_unconfirmed: [] } }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("button", { name: "我还不能回应 ▾" }))
    fireEvent.click(screen.getByRole("button", { name: /暂缓这条挑战/ }))
    fireEvent.change(screen.getByLabelText("何时重看"), { target: { value: "读到 Paper A 之后" } })
    fireEvent.click(screen.getByRole("button", { name: "确认暂缓" }))
    await waitFor(() => expect(researchUniverse.deferChallenge).toHaveBeenCalledWith("ch-1", expect.objectContaining({ reason: "暂缓这条挑战", condition: "读到 Paper A 之后", expected_sequence: 1 })))
    expect(await screen.findByText(/何时重看：读到 Paper A 之后/)).toBeInTheDocument()
    expect(screen.queryByLabelText("我目前的回应")).not.toBeInTheDocument()
  })

  it("withdraws a challenge with a reason and closes it", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.withdrawChallenge).mockResolvedValue(responded({ challenge_id: "ch-1", review_round_id: "r-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ challenges: [{ ...challenge, status: "withdrawn", sequence: 2, withdraw: { reason: "no longer relevant" } }], ledger: { answered: [], deferred: [], pending: [], brought_unconfirmed: [] } }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("button", { name: "撤回这条挑战" }))
    fireEvent.change(screen.getByLabelText("撤回理由"), { target: { value: "no longer relevant" } })
    fireEvent.click(screen.getByRole("button", { name: "确认撤回" }))
    await waitFor(() => expect(researchUniverse.withdrawChallenge).toHaveBeenCalledWith("ch-1", expect.objectContaining({ reason: "no longer relevant", expected_sequence: 1 })))
    expect(await screen.findByText(/理由：no longer relevant/)).toBeInTheDocument()
  })

  it("records a verdict through the ledger with an explicit user reason", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.confirmVerdict).mockResolvedValue(responded({ review_round_id: "r-1", verdict_type: "survived" }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("button", { name: "作出本轮裁决" }))
    expect(screen.getByText(/这是一项你的判断。Cui 不会替你决定结果。/)).toBeInTheDocument()
    expect(screen.getByText("已回应")).toBeInTheDocument()
    expect(screen.getByText("仍待回应")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("radio", { name: /暂时站住了/ }))
    fireEvent.change(screen.getByLabelText("你的理由"), { target: { value: "stood this round" } })
    fireEvent.click(screen.getByRole("button", { name: "确认裁决" }))
    await waitFor(() => expect(researchUniverse.confirmVerdict).toHaveBeenCalledWith("r-1", expect.objectContaining({ verdict_type: "survived", user_reason: "stood this round", revival_condition: null, expected_sequence: 1 })))
  })

  it("requires a revival condition for a circumstantial verdict", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound())
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("button", { name: "作出本轮裁决" }))
    fireEvent.click(screen.getByRole("radio", { name: /现在先不投入/ }))
    const confirm = screen.getByRole("button", { name: "确认裁决" })
    expect(confirm).toBeDisabled()
    fireEvent.change(screen.getByLabelText("你的理由"), { target: { value: "not now" } })
    expect(confirm).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/何时、什么条件下再回来/), { target: { value: "when measured" } })
    expect(confirm).toBeEnabled()
  })

  it("offers re-review and shows round history after a verdict", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound({ verdict: { round_id: "r-1", verdict_type: "survived", user_reason: "x" }, challenges: [{ ...challenge, status: "resolved_by_verdict" }], rounds: [{ id: "r-1", claim_id: "c-1", question_snapshot: { version_id: "q-1", text: "问题" }, claim_snapshot: snapshot, verdict: { round_id: "r-1", verdict_type: "survived", user_reason: "x" } }] }))
    vi.mocked(researchUniverse.startReview).mockResolvedValue(responded({ review_round_id: "r-2" }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    const again = await screen.findByRole("button", { name: "再次审查这一条 claim" })
    expect(screen.getByText(/裁决：survived/)).toBeInTheDocument()
    fireEvent.click(again)
    await waitFor(() => expect(researchUniverse.startReview).toHaveBeenCalledWith("c-1", expect.objectContaining({ expected_sequence: 0 })))
    expect(window.location.pathname).toBe("/review-rounds/r-2")
  })

  it("shows the boundary lineage after a boundary verdict", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound({ verdict: { round_id: "r-1", verdict_type: "boundary", user_reason: "needs narrowing" }, challenges: [{ ...challenge, status: "resolved_by_verdict" }], rounds: [{ id: "r-1", claim_id: "c-1", question_snapshot: { version_id: "q-1", text: "问题" }, claim_snapshot: snapshot, verdict: { round_id: "r-1", verdict_type: "boundary", user_reason: "needs narrowing" } }] }))
    vi.mocked(researchUniverse.active).mockResolvedValue({ id: "u-1" })
    vi.mocked(researchUniverse.createWorkspace).mockResolvedValue(responded({ workspace_id: "w-2" }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    expect(await screen.findByText(/这条 claim 已保留为本轮结论/)).toBeInTheDocument()
    expect(screen.getByText(/理由：needs narrowing/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "围绕这条边界开一个新问题" }))
    await waitFor(() => expect(researchUniverse.createWorkspace).toHaveBeenCalledWith("u-1", expect.objectContaining({ question: "把这条边界做成一个开放问题：主张" })))
    expect(window.location.pathname).toBe("/workspaces/w-2")
  })
})
