import { useState, useEffect } from "react"
import type { DocVersion } from "../types"
import * as api from "../api"
import EventCard from "./EventCard"

interface Props {
  artifactId: string
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export default function VersionsView({ artifactId }: Props) {
  const [versions, setVersions] = useState<DocVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    api
      .getVersions(artifactId)
      .then(({ versions: fetched }) => {
        if (!cancelled) {
          setVersions(fetched)
          setLoading(false)
        }
      })
      .catch(e => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load versions")
          setLoading(false)
        }
      })

    return () => { cancelled = true }
  }, [artifactId])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-sm text-zinc-500">Loading versions...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-sm text-red-400">{error}</p>
      </div>
    )
  }

  if (versions.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-sm text-zinc-500">No versions yet.</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
      {versions.map(version => (
        <div
          key={version.version}
          className="bg-zinc-800/20 border border-zinc-700/50 rounded-lg px-4 py-3 space-y-3"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-purple-300">
              v{version.version}
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-zinc-600/50 text-zinc-300">
              {version.triggering_event_type}
            </span>
            <span className="text-[10px] text-zinc-500">
              +{version.added_event_ids.length} / -{version.removed_event_ids.length}
            </span>
            <span className="text-[10px] text-zinc-600 ml-auto">
              {formatTimestamp(version.ts)}
            </span>
          </div>
          {version.doc.length === 0 ? (
            <p className="text-sm text-zinc-500">Empty document.</p>
          ) : (
            <div className="space-y-3">
              {version.doc.map(event => (
                <EventCard key={event.id} event={event} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
