import { useState, useEffect } from "react"
import type { Event } from "../types"
import * as api from "../api"
import EventCard from "./EventCard"

interface Props {
  artifactId: string
  /** Navigate to another artifact — lets boundary verdict cards link to the
   * narrowed successor claim's artifact (收窄 → 后继). */
  onOpenArtifact?: (artifactId: string) => void
}

export default function TrajectoryView({ artifactId, onOpenArtifact }: Props) {
  const [events, setEvents] = useState<Event[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    api
      .getTrajectory(artifactId)
      .then(({ events: fetched }) => {
        if (!cancelled) {
          setEvents(fetched)
          setLoading(false)
        }
      })
      .catch(e => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load trajectory")
          setLoading(false)
        }
      })

    return () => { cancelled = true }
  }, [artifactId])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-sm text-zinc-500">Loading trajectory...</p>
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

  if (events.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-sm text-zinc-500">No events in trajectory.</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
      {events.map(event => (
        <EventCard key={event.id} event={event} onOpenArtifact={onOpenArtifact} />
      ))}
    </div>
  )
}
