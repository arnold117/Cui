import type { Claim, CommandEnvelope, CommandResponse, ExplorationAnchor, ExplorationNote, HomeProjection, ReviewRound, WorkspaceDesk } from "./types"

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
  startReview: (claimId: string, envelope: CommandEnvelope) => send<CommandResponse<{ review_round_id: string; aggregate_sequences?: Record<string, number> }>>(`/claims/${claimId}/review-rounds`, envelope),
  reviewRound: (roundId: string) => read<ReviewRound>(`/review-rounds/${roundId}`),
}
export type { Claim, ExplorationAnchor, ExplorationNote }
