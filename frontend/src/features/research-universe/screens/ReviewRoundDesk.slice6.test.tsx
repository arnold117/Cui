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
    generateAdditionalChallenge: vi.fn(),
    generateEvidenceCandidate: vi.fn(),
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

const challenge = { id: "ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending" as const, sequence: 1, attack_surface: "边界尚未说明", why_it_matters: "无法判断适用范围", self_check_method: "写下一种失效条件", answers: [], provenance: { basis_refs: ["question", "claim"], uncertainty: "待检验" } }
const snapshot = { id: "c-1", version_id: "cv-1", text: "X causes Y." }
const desk: WorkspaceDesk = { id: "w-1", question: { version_id: "q-1", text: "Q" }, sequence: 5, note: null, note_revisions: [], anchors: [], claims: [], review_rounds: [], pending_challenges: [], materials: [{ id: "m-1", excerpt: "Paper A observes Z.", source_locator: "Paper A", parse_status: "parsed", purpose: "evidence" }] }
function makeRound(overrides: Record<string, unknown> = {}) {
  return { id: "r-1", workspace_id: "w-1", question_snapshot: { version_id: "q-1", text: "Q" }, claim_snapshot: snapshot, sequence: 1, verdict: null, challenges: [challenge], ledger: { answered: [], deferred: [], pending: [challenge], brought_unconfirmed: [] }, rounds: [], evidence_candidates: [], confirmed_facts: [], ...overrides }
}
const responded = <T extends Record<string, unknown>>(payload: T) => ({ commit_position: 2, event_ids: [] as string[], result: payload })

afterEach(() => cleanup())

describe("ReviewRoundDesk Slice 6 expanded LLM generation", () => {
  it("generates an additional challenge and renders it through the existing ChallengePanel", async () => {
    const extra = { id: "ch-2", review_round_id: "r-1", claim_id: "c-1", status: "pending" as const, sequence: 1, attack_surface: "缺少对照组", why_it_matters: "为何重要", self_check_method: "自检方法", answers: [], provenance: { generator_kind: "system", prompt_version: "slice6-expanded-challenge-v1", model_identifier: "fake", basis_refs: ["question", "claim", "ch-1"], uncertainty: "中等" } }
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.generateAdditionalChallenge).mockResolvedValue(responded({ challenge_id: "ch-2", round_id: "r-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ challenges: [challenge, extra] }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("button", { name: "生成更多挑战" }))
    await waitFor(() => expect(researchUniverse.generateAdditionalChallenge).toHaveBeenCalledWith("r-1", expect.objectContaining({ expected_sequence: 0 })))
    expect(await screen.findByText("缺少对照组")).toBeInTheDocument()
    expect(screen.getByText(/生成依据：question · claim · ch-1/)).toBeInTheDocument()
  })

  it("lets Cui propose an evidence candidate per eligible material and renders rationale/highlight/provenance", async () => {
    const generated = { id: "ec-gen-1", round_id: "r-1", workspace_id: "w-1", claim_snapshot: snapshot, material_anchor: { id: "m-1", excerpt: "Paper A observes Z.", source_locator: "Paper A" }, relation: "contradicts" as const, status: "pending" as const, sequence: 1, uncertainty: "中", rationale: "这段摘录与 claim 构成反证。", evidence_highlight: "observes Z", provenance: { generator_kind: "system", prompt_version: "slice6-evidence-candidate-v1", model_identifier: "fake", basis_refs: ["m-1"] } }
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.desk).mockResolvedValue(desk)
    vi.mocked(researchUniverse.generateEvidenceCandidate).mockResolvedValue(responded({ candidate_id: "ec-gen-1", round_id: "r-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ evidence_candidates: [generated] }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    const generate = await screen.findByRole("button", { name: "让 Cui 提出取证候选" })
    fireEvent.click(generate)
    await waitFor(() => expect(researchUniverse.generateEvidenceCandidate).toHaveBeenCalledWith("r-1", expect.objectContaining({ material_id: "m-1", expected_sequence: 0 })))
    expect(await screen.findByText(/为何/)).toBeInTheDocument()
    expect(screen.getByText("这段摘录与 claim 构成反证。")).toBeInTheDocument()
    expect(screen.getByText("observes Z")).toBeInTheDocument()
    expect(screen.getByText(/生成依据：m-1 · slice6-evidence-candidate-v1/)).toBeInTheDocument()
  })
})
