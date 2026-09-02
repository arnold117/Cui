import type { AbsorbWorkspaceEnvelope, GapDraftFields, LiteratureChallengeEnvelope, LiteratureSearchResponse, CorpusSearchResponse, GapDecisionEnvelope, GapProposeEnvelope, AddMaterialEnvelope, AnswerChallengeEnvelope, AttachCrystallizationEnvelope, AttachDirectionEnvelope, BranchWorkspaceEnvelope, Claim, CommandEnvelope, CommandResponse, ConcludeWorkspaceEnvelope, ConfirmVerdictEnvelope, CorrectEvidenceEnvelope, CreateDirectionEnvelope, DecideEvidenceEnvelope, DeclareDirectionStatusEnvelope, DeferChallengeEnvelope, DetachDirectionLinkEnvelope, Direction, ExplorationAnchor, ExplorationNote, GenerateEvidenceCandidateEnvelope, HomeProjection, PauseWorkspaceEnvelope, ProposeEvidenceCandidateEnvelope, ReopenWorkspaceEnvelope, RephraseDirectionEnvelope, ReviewRound, WithdrawChallengeEnvelope, WorkspaceDesk } from "./types"

const BASE = "/api/v2"
function commandId() { return globalThis.crypto?.randomUUID?.() ?? `cmd-${Date.now()}-${Math.random().toString(16).slice(2)}` }
export function command<T extends object>(payload: T, expected_sequence: CommandEnvelope["expected_sequence"], existing?: CommandEnvelope): T & CommandEnvelope { return existing ? { ...payload, ...existing } : { ...payload, command_id: commandId(), expected_sequence } }
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = init ? await fetch(`${BASE}${path}`, init) : await fetch(`${BASE}${path}`)
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    const detail = body.detail
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item) => item.msg ?? JSON.stringify(item)).join("; ") : JSON.stringify(detail ?? body)
    const failure = new Error(message || `${response.status} ${response.statusText}`) as Error & { status?: number }
    failure.status = response.status
    throw failure
  }
  return response.json() as Promise<T>
}
function read<T>(path: string) { return request<T>(path) }
function send<T>(path: string, body: object) { return request<T>(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }) }
export interface ActiveUniverse { id: string; library_id?: string }
export const researchUniverse = {
  active: () => read<ActiveUniverse>("/universes/active"),
  home: (universeId: string) => read<HomeProjection>(`/universes/${universeId}/home`),
  createWorkspace: (universeId: string, envelope: CommandEnvelope & { question: string }) => send<CommandResponse<{ workspace_id: string; aggregate_sequences?: Record<string, number> }>>(`/universes/${universeId}/workspaces`, envelope),
  desk: (workspaceId: string) => read<WorkspaceDesk>(`/workspaces/${workspaceId}`),
  saveNote: (workspaceId: string, envelope: CommandEnvelope & { text: string }) => send<CommandResponse<{ note_id: string; note_revision_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/notes`, envelope),
  createAnchor: (workspaceId: string, envelope: CommandEnvelope & { note_id: string; note_revision_id: string; start: number; end: number; selected_text: string }) => send<CommandResponse<{ anchor_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/anchors`, envelope),
  createClaim: (workspaceId: string, envelope: CommandEnvelope & { text: string }) => send<CommandResponse<{ claim_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/claims`, envelope),
  forgeProvenance: (workspaceId: string, envelope: CommandEnvelope & { claim_id: string; capture_id: string; release_id: string }) => send<CommandResponse<{ aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/claims/forge-provenance`, envelope),
  startReview: (claimId: string, envelope: CommandEnvelope) => send<CommandResponse<{ review_round_id: string; aggregate_sequences?: Record<string, number> }>>(`/claims/${claimId}/review-rounds`, envelope),
  reviewRound: (roundId: string) => read<ReviewRound>(`/review-rounds/${roundId}`),
  answerChallenge: (challengeId: string, envelope: AnswerChallengeEnvelope) => send<CommandResponse<{ challenge_id: string; review_round_id: string; answer_version_id: string; aggregate_sequences?: Record<string, number> }>>(`/challenges/${challengeId}/answers`, envelope),
  deferChallenge: (challengeId: string, envelope: DeferChallengeEnvelope) => send<CommandResponse<{ challenge_id: string; review_round_id: string; aggregate_sequences?: Record<string, number> }>>(`/challenges/${challengeId}/defer`, envelope),
  withdrawChallenge: (challengeId: string, envelope: WithdrawChallengeEnvelope) => send<CommandResponse<{ challenge_id: string; review_round_id: string; aggregate_sequences?: Record<string, number> }>>(`/challenges/${challengeId}/withdraw`, envelope),
  confirmVerdict: (roundId: string, envelope: ConfirmVerdictEnvelope) => send<CommandResponse<{ review_round_id: string; verdict_type: string; aggregate_sequences?: Record<string, number> }>>(`/review-rounds/${roundId}/verdicts`, envelope),
  addMaterial: (workspaceId: string, envelope: AddMaterialEnvelope) => send<CommandResponse<{ material_id: string; workspace_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/materials`, envelope),
  proposeEvidenceCandidate: (roundId: string, envelope: ProposeEvidenceCandidateEnvelope) => send<CommandResponse<{ candidate_id: string; round_id: string; aggregate_sequences?: Record<string, number> }>>(`/review-rounds/${roundId}/evidence-candidates`, envelope),
  // Slice 6 — expanded LLM generation
  generateAdditionalChallenge: (roundId: string, envelope: CommandEnvelope) => send<CommandResponse<{ challenge_id: string; round_id: string; aggregate_sequences?: Record<string, number> }>>(`/review-rounds/${roundId}/challenges`, envelope),
  generateEvidenceCandidate: (roundId: string, envelope: GenerateEvidenceCandidateEnvelope) => send<CommandResponse<{ candidate_id: string; round_id: string; aggregate_sequences?: Record<string, number> }>>(`/review-rounds/${roundId}/evidence-candidate-generation`, envelope),
  confirmEvidence: (candidateId: string, envelope: DecideEvidenceEnvelope) => send<CommandResponse<{ candidate_id: string; round_id: string; relation: string; challenge_id?: string; aggregate_sequences?: Record<string, number> }>>(`/evidence-candidates/${candidateId}/confirm`, envelope),
  correctEvidence: (candidateId: string, envelope: CorrectEvidenceEnvelope) => send<CommandResponse<{ candidate_id: string; round_id: string; relation: string; challenge_id?: string; aggregate_sequences?: Record<string, number> }>>(`/evidence-candidates/${candidateId}/correct`, envelope),
  rejectEvidence: (candidateId: string, envelope: DecideEvidenceEnvelope) => send<CommandResponse<{ candidate_id: string; round_id: string; aggregate_sequences?: Record<string, number> }>>(`/evidence-candidates/${candidateId}/reject`, envelope),
  withdrawEvidence: (candidateId: string, envelope: DecideEvidenceEnvelope) => send<CommandResponse<{ candidate_id: string; round_id: string; aggregate_sequences?: Record<string, number> }>>(`/evidence-candidates/${candidateId}/withdraw`, envelope),
  // Slice 5 — crystallization / direction impact
  pauseWorkspace: (workspaceId: string, envelope: PauseWorkspaceEnvelope) => send<CommandResponse<{ workspace_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/pause`, envelope),
  reopenWorkspace: (workspaceId: string, envelope: ReopenWorkspaceEnvelope) => send<CommandResponse<{ workspace_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/reopen`, envelope),
  concludeWorkspace: (workspaceId: string, envelope: ConcludeWorkspaceEnvelope) => send<CommandResponse<{ workspace_id: string; conclusion_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/conclusions`, envelope),
  branchWorkspace: (workspaceId: string, envelope: BranchWorkspaceEnvelope) => send<CommandResponse<{ workspace_id: string; successor_workspace_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/branch`, envelope),
  absorbWorkspace: (workspaceId: string, envelope: AbsorbWorkspaceEnvelope) => send<CommandResponse<{ workspace_id: string; target_workspace_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/absorb`, envelope),
  attachDirection: (workspaceId: string, envelope: AttachDirectionEnvelope) => send<CommandResponse<{ direction_link_id: string; workspace_id: string; direction_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/direction-links`, envelope),
  detachDirectionLink: (linkId: string, envelope: DetachDirectionLinkEnvelope) => send<CommandResponse<{ direction_link_id: string; workspace_id: string; direction_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspace-direction-links/${linkId}/detach`, envelope),
  createDirection: (universeId: string, envelope: CreateDirectionEnvelope) => send<CommandResponse<{ direction_id: string; proposition_version_id: string; aggregate_sequences?: Record<string, number> }>>(`/universes/${universeId}/directions`, envelope),
  declareDirectionStatus: (directionId: string, envelope: DeclareDirectionStatusEnvelope) => send<CommandResponse<{ direction_id: string; status: string; aggregate_sequences?: Record<string, number> }>>(`/directions/${directionId}/status-declarations`, envelope),
  rephraseDirection: (directionId: string, envelope: RephraseDirectionEnvelope) => send<CommandResponse<{ direction_id: string; new_proposition_version_id: string; aggregate_sequences?: Record<string, number> }>>(`/directions/${directionId}/rephrasings`, envelope),
  attachCrystallization: (directionId: string, envelope: AttachCrystallizationEnvelope) => send<CommandResponse<{ crystallization_id: string; direction_id: string; workspace_id: string; aggregate_sequences?: Record<string, number> }>>(`/directions/${directionId}/crystallizations`, envelope),
  direction: (directionId: string) => read<Direction>(`/directions/${directionId}`),
  // slice1 — corpus search + gap candidates / landscape
  corpusSearch: (q: string, opts?: { group?: "active" | "legacy"; limit?: number }) => read<CorpusSearchResponse>(`/corpus/search?${new URLSearchParams({ q, group: opts?.group ?? "active", limit: String(opts?.limit ?? 20) }).toString()}`),
  proposeGapCandidate: (workspaceId: string, envelope: GapProposeEnvelope) => send<CommandResponse<{ gap_candidate_id: string; aggregate_sequences?: Record<string, number> }>>(`/workspaces/${workspaceId}/gap-candidates`, envelope),
  confirmGapCandidate: (candidateId: string, envelope: GapDecisionEnvelope) => send<CommandResponse<{ gap_candidate_id: string; aggregate_sequences?: Record<string, number> }>>(`/gap-candidates/${candidateId}/confirm`, envelope),
  rejectGapCandidate: (candidateId: string, envelope: GapDecisionEnvelope) => send<CommandResponse<{ gap_candidate_id: string; aggregate_sequences?: Record<string, number> }>>(`/gap-candidates/${candidateId}/reject`, envelope),
  // slice1 second cut — literature dialogue surface
  literatureSearch: (workspaceId: string, body: { question: string; query?: string }) => send<LiteratureSearchResponse>(`/workspaces/${workspaceId}/dialogue/literature-search`, body),
  landscapeSummary: (workspaceId: string, materialIds: string[]) => send<{ text: string }>(`/workspaces/${workspaceId}/dialogue/landscape-summary`, { material_ids: materialIds }),
  gapDraft: (workspaceId: string, materialIds: string[]) => send<GapDraftFields>(`/workspaces/${workspaceId}/dialogue/gap-draft`, { material_ids: materialIds }),
  relatedWorkDraft: (workspaceId: string, materialIds: string[], gapIds: string[]) => send<{ text: string }>(`/workspaces/${workspaceId}/dialogue/related-work-draft`, { material_ids: materialIds, gap_ids: gapIds }),
  literatureChallenge: (roundId: string, envelope: LiteratureChallengeEnvelope) => send<CommandResponse<{ challenge_id: string; review_round_id: string; aggregate_sequences?: Record<string, number> }>>(`/review-rounds/${roundId}/literature-challenges`, envelope),
}
export type { Claim, ExplorationAnchor, ExplorationNote }
