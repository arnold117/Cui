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
  type: "contradicts" | "grounds"
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
