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

export type ClaimStatus = "parked" | "grilling" | "survived" | "killed"

export interface SidebarEntry {
  artifact: Artifact
  claim: Claim | null
  status: ClaimStatus
  events: Event[]
}
