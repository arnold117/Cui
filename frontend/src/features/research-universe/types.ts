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
export interface WorkspaceDesk { id: string; question: Snapshot; sequence: number; landscape?: WorkspaceLandscape; note?: ExplorationNote | null; note_revisions: NoteRevision[]; anchors: ExplorationAnchor[]; claims: Claim[]; review_rounds: ReviewRoundSummary[]; pending_challenges: Challenge[]; park_release_refs?: ParkReleaseRef[]; materials?: Material[]; confirmed_facts?: ConfirmedFact[]; user_position?: WorkspacePosition; conclusion?: Conclusion | null; direction_links?: DirectionLink[]; successor_workspace_id?: string | null; absorb_target_workspace_id?: string | null }
export interface HomePendingFact extends Challenge { workspace_id: string; question: string }
export interface HomeProjection { universe_id: string; workspaces: WorkspaceDesk[]; pending_facts: HomePendingFact[]; directions?: HomeDirection[] }

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
  // Slice 6 — LLM-generated candidates carry the model's 为何 / 证据高亮
  rationale?: string | null
  evidence_highlight?: string | null
}
export interface ConfirmedFact { id: string; relation: EvidenceRelation; material_anchor: MaterialAnchor; claim_snapshot: Snapshot }

export interface AnswerChallengeEnvelope extends CommandEnvelope { answer_text: string; provisional_anchor_refs: string[] }
export interface DeferChallengeEnvelope extends CommandEnvelope { reason: string; condition: string }
export interface WithdrawChallengeEnvelope extends CommandEnvelope { reason: string }
export interface ConfirmVerdictEnvelope extends CommandEnvelope { verdict_type: VerdictType; user_reason: string; revival_condition?: string | null }
export interface AddMaterialEnvelope extends CommandEnvelope { excerpt: string; source_locator?: string | null; parse_status: MaterialParseStatus; purpose: MaterialPurpose }
export interface ProposeEvidenceCandidateEnvelope extends CommandEnvelope { material_id: string; relation: EvidenceRelation; uncertainty?: string | null }
export interface GenerateEvidenceCandidateEnvelope extends CommandEnvelope { material_id: string }
export interface DecideEvidenceEnvelope extends CommandEnvelope { user_reason?: string | null }
export interface CorrectEvidenceEnvelope extends DecideEvidenceEnvelope { corrected_relation: EvidenceRelation }

// Slice 5 — crystallization / direction impact
export type WorkspacePosition = "exploring" | "paused" | "concluded" | "branched" | "absorbed"
export type ConclusionType = "tentative_answer" | "negated_path" | "boundary" | "key_unknown" | "deferred" | "split_or_turn"
export interface Conclusion { id: string; type: ConclusionType; text: string; reason?: string | null; basis_refs?: string[]; revival_condition?: string | null; sequence?: number }
export interface DirectionLink { link_id: string; direction_id: string; direction_proposition?: string | null; status?: string }
export type DirectionStatus = "active" | "on_hold" | "retired"
export type DirectionChangeType = "clarify" | "narrow_or_widen" | "turning" | "unnamed"
export interface DirectionRephraseEntry { prior_proposition_version_id: string; prior_proposition_text: string; new_proposition_version_id: string; new_proposition_text?: string | null; change_type: DirectionChangeType; user_reason: string; source_conclusion_ref?: string | null; sequence?: number }
export interface DirectionAttachedWorkspace { link_id: string; workspace_id: string; question?: string | null; position: WorkspacePosition; pending_fact_count: number }
export interface Crystallization { crystallization_id: string; direction_id?: string; workspace_id: string; conclusion_id: string; conclusion_text: string; conclusion_type: ConclusionType }
export interface Direction { id: string; proposition: { version_id: string; text: string | null }; status: DirectionStatus; sequence?: number; rephrase_history: DirectionRephraseEntry[]; attached_workspaces: DirectionAttachedWorkspace[]; crystallizations: Crystallization[] }
export interface HomeDirection { id: string; proposition: string; status: DirectionStatus; crystallizations: Crystallization[]; crystallizations_count: number; attached_workspaces_count: number }

export interface PauseWorkspaceEnvelope extends CommandEnvelope { user_reason?: string | null }
export interface ReopenWorkspaceEnvelope extends CommandEnvelope { user_reason?: string | null }
export interface ConcludeWorkspaceEnvelope extends CommandEnvelope { conclusion_type: ConclusionType; conclusion_text: string; user_reason?: string | null; basis_refs?: string[]; revival_condition?: string | null }
export interface BranchWorkspaceEnvelope extends CommandEnvelope { new_question: string; user_reason: string }
export interface AbsorbWorkspaceEnvelope extends CommandEnvelope { target_workspace_id: string; user_reason: string }
export interface AttachDirectionEnvelope extends CommandEnvelope { direction_id: string; user_reason?: string | null }
export interface DetachDirectionLinkEnvelope extends CommandEnvelope { user_reason?: string | null }
export interface CreateDirectionEnvelope extends CommandEnvelope { proposition: string }
export interface DeclareDirectionStatusEnvelope extends CommandEnvelope { status: DirectionStatus; user_reason: string }
export interface RephraseDirectionEnvelope extends CommandEnvelope { new_proposition?: string | null; change_type: DirectionChangeType; user_reason: string; source_conclusion_ref?: string | null }
export interface AttachCrystallizationEnvelope extends CommandEnvelope { workspace_id: string; conclusion_id: string; user_reason?: string | null }

// slice1 — gap candidates / workspace landscape
export type GapStatus = "pending" | "confirmed" | "corrected" | "rejected" | "withdrawn"
export interface GapSearchRecord { query: string; scope: "active" | "legacy"; matched_locators: string[]; searched_at?: string | null }
export interface GapCandidate {
  id: string
  workspace_id: string
  coverage_statement: string
  search_record: GapSearchRecord
  counterexample_invitation: string
  generator_kind?: "user" | "system"
  status: GapStatus
  sequence?: number
  decision_reason?: string | null
}
export interface LandscapeClaim { id: string; text: string; sequence?: number }
export interface LandscapeFact { candidate_id: string; claim_id: string; claim_text: string; relation: EvidenceRelation; material_locator?: string | null; decision_reason?: string | null }
export interface WorkspaceLandscape {
  workspace_id: string
  question: Snapshot
  alive_claims: LandscapeClaim[]
  claim_verdicts: Record<string, string>
  confirmed_facts: LandscapeFact[]
  gaps: GapCandidate[]
}
export interface CorpusSearchHit { material_id: string; source_locator: string; title: string; matched_terms: number; snippet: string }
export interface CorpusSearchResponse { query: string; group: string; total: number; results: CorpusSearchHit[] }
export interface GapProposeEnvelope extends CommandEnvelope { coverage_statement: string; search_query: string; search_scope: "active" | "legacy"; matched_locators: string[]; searched_at?: string | null; counterexample_invitation: string }
export interface GapDecisionEnvelope extends CommandEnvelope { user_reason?: string | null }

// slice1 second cut — literature dialogue surface
export interface LiteratureChallengeEnvelope extends CommandEnvelope { material_ids: string[]; external_refs?: DialogueExternalRef[] }
export interface DialogueExternalRef { locator: string; excerpt: string; url?: string | null }
export interface DialogueCandidate {
  material_id?: string | null
  locator: string
  title: string
  reason: string
  source?: string
  url?: string | null
  excerpt?: string
  stance?: string
  relation?: { kind: string; note: string }
}
export interface LiteratureSearchResponse { query: string; candidates: DialogueCandidate[] }
export interface GapDraftFields { coverage_statement: string; search_query: string; counterexample_invitation: string }
