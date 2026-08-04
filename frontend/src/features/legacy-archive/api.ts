import type { Artifact, Event } from "../../types"

const BASE = "/api/v2/legacy-archive"

async function read<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`)
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `${response.status} ${response.statusText}`)
  }
  return response.json()
}

export interface ArchiveArtifact extends Pick<Artifact, "id" | "kind" | "goal" | "title" | "created_at" | "updated_at"> {}
export interface ArchiveEvent extends Pick<Event, "id" | "ts" | "type" | "actor" | "confirmed" | "payload"> {}

export const legacyArchive = {
  list: () => read<{ artifacts: ArchiveArtifact[] }>(""),
  artifact: (id: string) => read<{ artifact: ArchiveArtifact }>(`/artifacts/${encodeURIComponent(id)}`),
  trajectory: (id: string) => read<{ events: ArchiveEvent[] }>(`/artifacts/${encodeURIComponent(id)}/trajectory`),
}
