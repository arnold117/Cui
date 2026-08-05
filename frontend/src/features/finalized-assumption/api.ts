import { command } from "../research-universe/api"
import type { CommandEnvelope, CommandResponse } from "../research-universe/types"
import type { ParkCaptureDetail, ParkCaptureSummary, ReleaseInput } from "./types"

const BASE = "/api/v2"
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) { const body = await response.json().catch(() => ({ detail: response.statusText })); const failure = new Error(typeof body.detail === "string" ? body.detail : response.statusText) as Error & { status?: number }; failure.status = response.status; throw failure }
  return response.json() as Promise<T>
}
function send<T>(path: string, body: object) { return request<T>(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }) }

/** Exact native PARK DTO adapter; no Workspace imports raw capture text. */
export const finalizedAssumptions = {
  list: async () => (await request<{ library_id: string; captures: ParkCaptureSummary[] }>("/park-captures")).captures,
  get: (id: string) => request<ParkCaptureDetail>(`/park-captures/${id}`),
  capture: async (original_text: string, envelope: CommandEnvelope) => {
    const response = await send<CommandResponse<{ capture_id: string }>>("/park-captures", { ...envelope, original_text })
    return response.fragment as ParkCaptureDetail
  },
  release: async (input: ReleaseInput, envelope: CommandEnvelope) => {
    const response = await send<CommandResponse<{ workspace_id: string }>>(`/park-captures/${input.captureId}/release`, { ...envelope, provisional_role: input.provisionalRole, workspace_id: input.workspaceId, question: input.question, workspace_expected_sequence: input.workspaceExpectedSequence ?? 0 })
    return { workspace_id: response.result.workspace_id, fragment: response.fragment }
  },
}
export { command }
