import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ReviewRoundDesk } from "./ReviewRoundDesk"
import { researchUniverse } from "../api"
import type { WorkspaceDesk } from "../types"
import { AppRouter } from "../../../router"

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api")
  return { ...actual, researchUniverse: {
    reviewRound: vi.fn(),
    desk: vi.fn(),
    proposeEvidenceCandidate: vi.fn(),
    confirmEvidence: vi.fn(),
    correctEvidence: vi.fn(),
    rejectEvidence: vi.fn(),
    withdrawEvidence: vi.fn(),
    answerChallenge: vi.fn(),
    deferChallenge: vi.fn(),
    withdrawChallenge: vi.fn(),
    confirmVerdict: vi.fn(),
    startReview: vi.fn(),
    active: vi.fn(),
    createWorkspace: vi.fn(),
  } }
})

const challenge = { id: "ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending" as const, sequence: 1, attack_surface: "边界尚未说明", why_it_matters: "无法判断适用范围", self_check_method: "写下一种失效条件", answers: [] }
const snapshot = { id: "c-1", version_id: "cv-1", text: "X causes Y." }
const candidate = { id: "ec-1", round_id: "r-1", workspace_id: "w-1", claim_snapshot: snapshot, material_anchor: { id: "m-1", excerpt: "Paper A contradicts X", source_locator: "Paper A" }, relation: "contradicts" as const, status: "pending" as const, sequence: 1, uncertainty: "待检验", provenance: { generator_kind: "user" } }
const desk: WorkspaceDesk = { id: "w-1", question: { version_id: "q-1", text: "Q" }, sequence: 5, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [], materials: [{ id: "m-1", excerpt: "Paper A contradicts X", source_locator: "Paper A", parse_status: "parsed", purpose: "evidence" }, { id: "m-2", excerpt: "Reference note", source_locator: null, parse_status: "parsed", purpose: "reference" }, { id: "m-3", excerpt: "garbled", source_locator: null, parse_status: "failed", purpose: "evidence" }] }
function makeRound(overrides: Record<string, unknown> = {}) {
  return { id: "r-1", workspace_id: "w-1", question_snapshot: { version_id: "q-1", text: "Q" }, claim_snapshot: snapshot, sequence: 1, verdict: null, challenges: [challenge], ledger: { answered: [], deferred: [], pending: [challenge], brought_unconfirmed: [] }, rounds: [], evidence_candidates: [candidate], confirmed_facts: [], ...overrides }
}
const responded = <T extends Record<string, unknown>>(payload: T) => ({ commit_position: 2, event_ids: [] as string[], result: payload })

afterEach(() => cleanup())

describe("ReviewRoundDesk evidence surface", () => {
  it("shows materials and a pending candidate with a confirm label reflecting the relation", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound())
    vi.mocked(researchUniverse.desk).mockResolvedValue(desk)
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    expect(await screen.findByText("Paper A contradicts X")).toBeInTheDocument()
    expect(screen.getByText("Reference note")).toBeInTheDocument()
    expect(screen.getByText(/只作探索参考，不进入候选/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "确认是反证" })).toBeInTheDocument()
  })

  it("confirms a contradiction and shows the fact receipt", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.desk).mockResolvedValue(desk)
    vi.mocked(researchUniverse.confirmEvidence).mockResolvedValue(responded({ candidate_id: "ec-1", round_id: "r-1", relation: "contradicts" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ evidence_candidates: [{ ...candidate, status: "confirmed" }], confirmed_facts: [{ id: "ec-1", relation: "contradicts", material_anchor: candidate.material_anchor, claim_snapshot: snapshot }] }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("Paper A contradicts X")
    fireEvent.click(screen.getByRole("button", { name: "确认是反证" }))
    await waitFor(() => expect(researchUniverse.confirmEvidence).toHaveBeenCalledWith("ec-1", expect.objectContaining({ expected_sequence: 1, user_reason: null })))
    expect(await screen.findByText(/已确认的取证事实：Paper A contradicts X 与 claim 构成 反证/)).toBeInTheDocument()
    expect(screen.getByText(/已确认 · 构成 反证/)).toBeInTheDocument()
  })

  it("rejects a candidate and leaves it out of confirmed facts", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.desk).mockResolvedValue(desk)
    vi.mocked(researchUniverse.rejectEvidence).mockResolvedValue(responded({ candidate_id: "ec-1", round_id: "r-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ evidence_candidates: [{ ...candidate, status: "rejected", decision_reason: "misread" }], confirmed_facts: [] }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("Paper A contradicts X")
    fireEvent.click(screen.getByRole("button", { name: "拒绝（不涉及／误读…）" }))
    fireEvent.change(screen.getByLabelText(/理由（可选）/), { target: { value: "misread" } })
    fireEvent.click(screen.getByRole("button", { name: "确认拒绝" }))
    await waitFor(() => expect(researchUniverse.rejectEvidence).toHaveBeenCalledWith("ec-1", expect.objectContaining({ expected_sequence: 1, user_reason: "misread" })))
    expect(await screen.findByText(/已拒绝：这条候选未进入已确认的取证事实/)).toBeInTheDocument()
    expect(screen.queryByText(/已确认 · 构成/)).not.toBeInTheDocument()
  })

  it("withdraws a candidate", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.desk).mockResolvedValue(desk)
    vi.mocked(researchUniverse.withdrawEvidence).mockResolvedValue(responded({ candidate_id: "ec-1", round_id: "r-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ evidence_candidates: [{ ...candidate, status: "withdrawn" }], confirmed_facts: [] }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("Paper A contradicts X")
    fireEvent.click(screen.getByRole("button", { name: "撤回" }))
    fireEvent.click(screen.getByRole("button", { name: "确认撤回" }))
    await waitFor(() => expect(researchUniverse.withdrawEvidence).toHaveBeenCalledWith("ec-1", expect.objectContaining({ expected_sequence: 1 })))
    expect(await screen.findByText(/已撤回这条取证候选/)).toBeInTheDocument()
  })

  it("corrects a pending candidate to a different relation", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.desk).mockResolvedValue(desk)
    vi.mocked(researchUniverse.correctEvidence).mockResolvedValue(responded({ candidate_id: "ec-1", round_id: "r-1", relation: "silent" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ evidence_candidates: [{ ...candidate, status: "corrected", relation: "silent", prior_relation: "contradicts" }], confirmed_facts: [{ id: "ec-1", relation: "silent", material_anchor: candidate.material_anchor, claim_snapshot: snapshot }] }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("Paper A contradicts X")
    fireEvent.click(screen.getByRole("button", { name: "改为…" }))
    fireEvent.change(screen.getByLabelText(/改为什么/), { target: { value: "silent" } })
    fireEvent.click(screen.getByRole("button", { name: "确认修正" }))
    await waitFor(() => expect(researchUniverse.correctEvidence).toHaveBeenCalledWith("ec-1", expect.objectContaining({ corrected_relation: "silent", expected_sequence: 1 })))
    expect(await screen.findByText(/已确认的取证事实：Paper A contradicts X 与 claim 构成 查无/)).toBeInTheDocument()
  })

  it("disables silent for a parse-failed material and offers cannot_assess", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound())
    vi.mocked(researchUniverse.desk).mockResolvedValue(desk)
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("garbled")
    fireEvent.change(screen.getByLabelText("选择待取证材料"), { target: { value: "m-3" } })
    const silent = screen.getByRole("radio", { name: /查无/ })
    expect(silent).toBeDisabled()
    expect(screen.getByRole("radio", { name: "无法判断" })).toBeEnabled()
    fireEvent.click(screen.getByRole("button", { name: "提出候选" }))
    await waitFor(() => expect(researchUniverse.proposeEvidenceCandidate).toHaveBeenCalledWith("r-1", expect.objectContaining({ material_id: "m-3", relation: "cannot_assess", expected_sequence: 0 })))
  })
})
