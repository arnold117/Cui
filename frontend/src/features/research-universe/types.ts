export type ExpectedSequence = number

export interface CommandEnvelope { command_id: string; expected_sequence: ExpectedSequence }
export interface CommandResponse<T = Record<string, unknown>> { commit_position: number; event_ids: string[]; result: T; fragment?: unknown }

export interface NoteRevision { id: string; note_id: string; text: string; sequence?: number; revision_id?: string }
export interface ExplorationNote { id: string; note_id?: string; revision_id: string; text: string; sequence: number }
export interface ExplorationAnchor { id: string; note_id: string; note_revision_id: string; start: number; end: number; selected_text: string }
export interface Claim { id: string; text: string; author?: "user"; sequence?: number }
export interface ParkReleaseRef { id: string; capture_id: string; provisional_role: "question" | "exploration" | "material_lead" | "unnamed" }
export interface Snapshot { id?: string; version_id?: string; text: string }

export type ChallengeStatus = "pending" | "answered" | "deferred" | "withdrawn" | "resolved_by_verdict"
export type VerdictType = "survived" | "refuted" | "not_worth" | "boundary" | "circumstantial"
export interface ChallengeAnswer { version_id: string; text: string; provisional_anchor_refs: string[]; sequence?: number }
export interface ChallengeProvenance { generator_kind?: string; prompt_version?: string; model_identifier?: string | null; basis_refs?: string[]; uncertainty?: string }
export interface Challenge {
  id: string
  review_round_id: string
  claim_id?: string
  attack_surface: string
  why_it_matters: string
  self_check_method: string
  status: ChallengeStatus
  sequence?: number
  answers?: ChallengeAnswer[]
  defer?: { reason: string; condition: string }
  withdraw?: { reason: string }
  provenance?: ChallengeProvenance
}
export interface Verdict { round_id: string; workspace_id?: string; claim_id?: string; verdict_type: VerdictType; user_reason: string; revival_condition?: string | null }
export interface ReviewLedger { answered: Challenge[]; deferred: Challenge[]; pending: Challenge[]; brought_unconfirmed: Challenge[] }
export interface ReviewRoundSummary { id: string; claim_id?: string; question_snapshot: Snapshot; claim_snapshot: Snapshot; verdict?: Verdict | null; sequence?: number }
export interface ReviewRound {
  id: string
  workspace_id: string
  question_snapshot: Snapshot
  claim_snapshot: Snapshot
  verdict?: Verdict | null
  sequence?: number
  challenges: Challenge[]
  ledger?: ReviewLedger
  rounds?: ReviewRoundSummary[]
  evidence_candidates?: EvidenceCandidate[]
  confirmed_facts?: ConfirmedFact[]
}
export interface WorkspaceDesk { id: string; question: Snapshot; sequence: number; note?: ExplorationNote | null; note_revisions: NoteRevision[]; anchors: ExplorationAnchor[]; claims: Claim[]; review_rounds: ReviewRoundSummary[]; pending_challenges: Challenge[]; park_release_refs?: ParkReleaseRef[]; materials?: Material[] }
export interface HomePendingFact extends Challenge { workspace_id: string; question: string }
export interface HomeProjection { universe_id: string; workspaces: WorkspaceDesk[]; pending_facts: HomePendingFact[] }

export type MaterialPurpose = "evidence" | "reference"
export type MaterialParseStatus = "parsed" | "failed"
export interface Material { id: string; workspace_id?: string; excerpt: string; source_locator?: string | null; parse_status: MaterialParseStatus; purpose: MaterialPurpose }
export type EvidenceRelation = "supports" | "contradicts" | "silent" | "cannot_assess"
export type EvidenceStatus = "pending" | "confirmed" | "corrected" | "rejected" | "withdrawn"
export interface MaterialAnchor { id: string; excerpt: string; source_locator?: string | null }
export interface EvidenceCandidate {
  id: string
  round_id?: string
  workspace_id?: string
  claim_snapshot: Snapshot
  material_anchor: MaterialAnchor
  relation: EvidenceRelation
  status: EvidenceStatus
  uncertainty?: string | null
  provenance?: ChallengeProvenance
  decision_reason?: string | null
  prior_relation?: EvidenceRelation
  sequence?: number
}
export interface ConfirmedFact { id: string; relation: EvidenceRelation; material_anchor: MaterialAnchor; claim_snapshot: Snapshot }

export interface AnswerChallengeEnvelope extends CommandEnvelope { answer_text: string; provisional_anchor_refs: string[] }
export interface DeferChallengeEnvelope extends CommandEnvelope { reason: string; condition: string }
export interface WithdrawChallengeEnvelope extends CommandEnvelope { reason: string }
export interface ConfirmVerdictEnvelope extends CommandEnvelope { verdict_type: VerdictType; user_reason: string; revival_condition?: string | null }
export interface AddMaterialEnvelope extends CommandEnvelope { excerpt: string; source_locator?: string | null; parse_status: MaterialParseStatus; purpose: MaterialPurpose }
export interface ProposeEvidenceCandidateEnvelope extends CommandEnvelope { material_id: string; relation: EvidenceRelation; uncertainty?: string | null }
export interface DecideEvidenceEnvelope extends CommandEnvelope { user_reason?: string | null }
export interface CorrectEvidenceEnvelope extends DecideEvidenceEnvelope { corrected_relation: EvidenceRelation }
