import { useEffect, useState } from "react"
import { listArtifacts, getTrajectory } from "../api"
import { LIBRARY_ID } from "../constants"
import { deriveClaimStatus } from "../utils"
import type { Artifact, ClaimStatus } from "../types"
import SidebarItem from "./SidebarItem"

interface SidebarEntry {
  artifact: Artifact
  status: ClaimStatus
}

interface Props {
  selectedId: string | null
  onSelect: (id: string | null) => void
  refreshKey: number
  showGraph: boolean
  onShowGraph: () => void
}

const STATUS_ORDER: ClaimStatus[] = ["grilling", "parked", "survived", "killed"]
const STATUS_LABELS: Record<ClaimStatus, string> = {
  parked: "Parked",
  grilling: "Grilling",
  survived: "Survived",
  killed: "Killed",
}

export default function Sidebar({ selectedId, onSelect, refreshKey, showGraph, onShowGraph }: Props) {
  const [entries, setEntries] = useState<SidebarEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    listArtifacts(LIBRARY_ID)
      .then(async ({ artifacts }) => {
        const results: SidebarEntry[] = []
        for (const artifact of artifacts) {
          try {
            const { events } = await getTrajectory(artifact.id)
            results.push({ artifact, status: deriveClaimStatus(events) })
          } catch {
            results.push({ artifact, status: "parked" })
          }
        }
        if (!cancelled) {
          setEntries(results)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [refreshKey])

  const grouped = STATUS_ORDER.map(status => ({
    status,
    items: entries.filter(e => e.status === status),
  })).filter(g => g.items.length > 0)

  return (
    <aside className="w-70 shrink-0 bg-zinc-900 border-r border-zinc-800 flex flex-col">
      {/* Header + new button */}
      <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-300 tracking-wide">淬 Anneal</span>
        <button
          className="w-7 h-7 flex items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 text-lg"
          onClick={() => onSelect(null)}
          title="Park new idea"
        >
          +
        </button>
      </div>

      {/* Entries list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {loading && (
          <p className="text-xs text-zinc-500 px-3 py-2">Loading...</p>
        )}

        {!loading && entries.length === 0 && (
          <p className="text-xs text-zinc-500 px-3 py-2">No ideas yet</p>
        )}

        {grouped.map(({ status, items }) => (
          <div key={status}>
            <p className="text-[10px] uppercase tracking-widest text-zinc-600 px-3 mb-1">
              {STATUS_LABELS[status]}
            </p>
            {items.map(({ artifact, status: s }) => (
              <SidebarItem
                key={artifact.id}
                goal={artifact.goal}
                kind={artifact.kind}
                status={s}
                selected={!showGraph && artifact.id === selectedId}
                onClick={() => onSelect(artifact.id)}
              />
            ))}
          </div>
        ))}
      </div>

      {/* Footer: library-level corpus graph */}
      <div className="shrink-0 border-t border-zinc-800 p-2">
        <button
          className={`w-full px-3 py-2 rounded-md text-left text-sm transition-colors ${
            showGraph
              ? "bg-zinc-800 text-purple-300"
              : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
          }`}
          onClick={onShowGraph}
          title="View the library's corpus graph"
        >
          🕸 语料图
        </button>
      </div>
    </aside>
  )
}
