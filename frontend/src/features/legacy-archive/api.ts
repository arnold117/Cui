// Archive-only view over the frozen legacy tables. The old v1 UI is gone (T3);
// these minimal shapes mirror the fields the read-only archive endpoints return.
export interface ArchiveArtifact {
  id: string
  kind: string
  goal: string
  title: string
  created_at: string
  updated_at: string
}
export interface ArchiveEvent {
  id: string
  ts: string
  type: string
  actor: "user" | "system"
  confirmed: boolean
  payload: Record<string, unknown>
}

const BASE = "/api/v2/legacy-archive"

async function read<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`)
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `${response.status} ${response.statusText}`)
  }
  return response.json()
}

export const legacyArchive = {
  list: () => read<{ artifacts: ArchiveArtifact[] }>(""),
  artifact: (id: string) => read<{ artifact: ArchiveArtifact }>(`/artifacts/${encodeURIComponent(id)}`),
  trajectory: (id: string) => read<{ events: ArchiveEvent[] }>(`/artifacts/${encodeURIComponent(id)}/trajectory`),
}
