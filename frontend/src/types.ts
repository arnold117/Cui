export interface Event {
  id: string
  ts: string
  type: EventType
  actor: "user" | "system"
  strictness: number | null
  debt: boolean
  confirmed: boolean
  target_ref: string | null
  payload: Record<string, unknown>
}

export type EventType =
  | "park" | "collect_material" | "analyze_material"
  | "challenge" | "answer" | "verdict"
  | "gap" | "draft" | "constrain" | "revise" | "ground"
  | "promote" | "edit" | "confirm" | "retract"

export interface DocVersion {
  version: number
  ts: string
  triggering_event_id: string
  triggering_event_type: EventType
  doc: Event[]
  added_event_ids: string[]
  removed_event_ids: string[]
}

export interface Artifact {
  id: string
  library_id: string
  kind: string
  goal: string
  constraints: Record<string, unknown>[]
  project_ids: string[]
  material_ids: string[]
  title: string
  created_at: string
  updated_at: string
}

export interface Material {
  id: string
  library_id: string
  kind: string
  provenance: Record<string, unknown>
  payload: Record<string, unknown>
}

export interface Claim {
  id: string
  library_id: string
  body: string
  artifact_ids: string[]
  created_at: string
  updated_at: string
}

// Payload shape carried by a `challenge` event surfaced by the Lens
// (cross-idea contradiction). Distinguished from an LLM grill challenge only
// by `kind === "lens_contradiction"` — same lifecycle otherwise.
export interface LensChallengePayload {
  kind: "lens_contradiction"
  question: string
  past_claim_id: string
  past_artifact_id: string
  past_outcome: "survived" | "killed"
  tension_type: "hard" | "duplicate" | "soft"
  tension: string
  auto_generated: boolean
}

export function isLensChallenge(event: Event): boolean {
  return event.type === "challenge" && event.payload.kind === "lens_contradiction"
}

// Payload shape carried by a `challenge` event surfaced by the Lens taste
// anchor (品味锚). Distinguished by `kind === "taste"` — same challenge
// lifecycle otherwise. tier is a RELATIVE rubric position (no numeric score);
// anchors cite real papers / the user's own grilled past claims.
export interface TasteChallengePayload {
  kind: "taste"
  tier: "replication" | "incremental" | "novel_but_tasteless" | "tasteful"
  reasoning: string
  anchored_papers: { title: string }[]
  anchored_claims: { past_claim_id: string }[]
  question: string
  auto_generated: boolean
}

export function isTasteChallenge(event: Event): boolean {
  return event.type === "challenge" && event.payload.kind === "taste"
}

// GROUND 判定三态 — how a paper bears on a claim. 「文献没谈」和「文献打」是
// 两个完全不同的状态; silent (查无) is a legitimate first-class output.
export type GroundVerdict = "supports" | "contradicts" | "silent"

// Read-side stance: the three states plus the legacy 未分态. Old GROUND
// events carry only `supported: bool` — True reads as supports, False reads
// as "not_supported" (silent-or-contradicts was never recorded; NEVER
// guessed — rendered as-is).
export type GroundStance = GroundVerdict | "not_supported"

export function groundStance(payload: Record<string, unknown>): GroundStance | null {
  const v = payload.verdict
  if (v === "supports" || v === "contradicts" || v === "silent") return v
  if ("supported" in payload) return payload.supported ? "supports" : "not_supported"
  return null
}

// Payload shape carried by a `challenge` event surfaced by 负证据反哺:
// confirming a `contradicts` GROUND pushes the counter-evidence onto the
// challenge board. Distinguished by `kind === "evidence_contradiction"` —
// same challenge lifecycle otherwise. Deterministic (zero LLM); carries the
// material reference + evidence excerpt straight off the ground event.
export interface EvidenceContradictionPayload {
  kind: "evidence_contradiction"
  question: string
  material_id: string
  title: string
  source: string
  evidence: string
  assessment: string
  ground_event_id: string
  auto_generated: boolean
}

export function isEvidenceContradictionChallenge(event: Event): boolean {
  return event.type === "challenge" && event.payload.kind === "evidence_contradiction"
}

// 死因分诊 (death-cause triage) — how a killed claim died. Kill is not a
// boolean: every NEW kill verdict carries exactly one cause; legacy verdicts
// carry none and render as 未分类. circumstantial is the only non-terminal
// cause and must carry a revival_condition; boundary may name the narrowed
// successor claim (successor_claim_id).
export type DeathCause = "refuted" | "not_worth" | "boundary" | "circumstantial"

export const DEATH_CAUSES: DeathCause[] = [
  "refuted",
  "not_worth",
  "boundary",
  "circumstantial",
]

// The user-amendable triage part of a kill verdict (the confirm UI lets the
// user override the auto_verdict proposal before signing it).
export interface VerdictTriage {
  death_cause: DeathCause
  revival_condition?: string
  successor_claim_id?: string
}

// Corpus graph (语料图) — library-level node-link view of confirmed relations.
export interface GraphNode {
  id: string
  type: "claim" | "material"
  label: string
  status: string | null // survived/killed/parked/open — claim nodes only
}

export interface GraphEdge {
  source: string
  target: string
  type:
    | "contradicts"
    | "grounds"
    | "undermines"
    | "builds_on"
    | "depends_on"
    | "shares_method"
    | "shares_gap"
    | "narrowed_from"
}

export interface CorpusGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export type ClaimStatus = "parked" | "grilling" | "survived" | "killed"

export interface SidebarEntry {
  artifact: Artifact
  claim: Claim | null
  status: ClaimStatus
  events: Event[]
}
