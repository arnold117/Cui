export type CaptureRole = "trigger_question" | "exploration_context" | "material_lead" | "unnamed"

export interface ParkRelease { universe_id: string; id: string; capture_id: string; workspace_id: string; provisional_role: CaptureRole }
export interface ParkCaptureSummary { id: string; status: "sealed"; released: boolean; releases: ParkRelease[]; forged_into: unknown[] }
export interface ParkCaptureDetail extends ParkCaptureSummary { original_text: string }
export interface ReleasedAssumption { workspace_id: string; fragment?: unknown }
export interface ReleaseInput { captureId: string; provisionalRole: CaptureRole; workspaceId?: string; question?: string; workspaceExpectedSequence?: number }
