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

export interface Claim {
  id: string
  library_id: string
  body: string
  artifact_ids: string[]
  created_at: string
  updated_at: string
}

export type ClaimStatus = "parked" | "grilling" | "survived" | "killed"

export interface SidebarEntry {
  artifact: Artifact
  claim: Claim | null
  status: ClaimStatus
  events: Event[]
}
