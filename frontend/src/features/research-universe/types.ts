export type ExpectedSequence = number

export interface CommandEnvelope { command_id: string; expected_sequence: ExpectedSequence }
export interface CommandResponse<T = Record<string, unknown>> { commit_position: number; event_ids: string[]; result: T; fragment?: unknown }

export interface NoteRevision { id: string; note_id: string; text: string; sequence?: number; revision_id?: string }
export interface ExplorationNote { id: string; note_id?: string; revision_id: string; text: string; sequence: number }
export interface ExplorationAnchor { id: string; note_id: string; note_revision_id: string; start: number; end: number; selected_text: string }
export interface Claim { id: string; text: string; author?: "user"; sequence?: number }
export interface ParkReleaseRef { id: string; capture_id: string; provisional_role: "question" | "exploration" | "material_lead" | "unnamed" }
export interface Snapshot { id?: string; version_id?: string; text: string }
export interface PendingChallenge { id: string; review_round_id: string; claim_id?: string; attack_surface: string; why_it_matters: string; self_check_method: string; status: "pending"; provenance?: { generator_kind?: string; prompt_version?: string; model_identifier?: string | null; basis_refs?: string[]; uncertainty?: string } }
export interface ReviewRound { id: string; workspace_id: string; question_snapshot: Snapshot; claim_snapshot: Snapshot; challenges: PendingChallenge[] }
export interface WorkspaceDesk { id: string; question: Snapshot; sequence: number; note?: ExplorationNote | null; note_revisions: NoteRevision[]; anchors: ExplorationAnchor[]; claims: Claim[]; review_rounds: ReviewRound[]; pending_challenges: PendingChallenge[]; park_release_refs?: ParkReleaseRef[] }
export interface HomePendingFact extends PendingChallenge { workspace_id: string; question: string }
export interface HomeProjection { universe_id: string; workspaces: WorkspaceDesk[]; pending_facts: HomePendingFact[] }
