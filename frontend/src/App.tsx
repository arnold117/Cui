import { useState, useCallback, useEffect } from "react"
import Sidebar from "./components/Sidebar"
import ParkView from "./components/ParkView"
import GrillView from "./components/GrillView"
import DocView from "./components/DocView"
import TrajectoryView from "./components/TrajectoryView"
import VersionsView from "./components/VersionsView"
import CorpusGraphView from "./components/CorpusGraphView"
import EmptyState from "./components/EmptyState"
import { LIBRARY_ID } from "./constants"
import { getArtifact, getTrajectory, getClaim } from "./api"
import { deriveClaimStatus } from "./utils"
import type { Artifact, Claim, ClaimStatus } from "./types"

type DocTab = "doc" | "trajectory" | "versions"

function App() {
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null)
  const [showGraph, setShowGraph] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  // Loaded data for selected artifact
  const [artifact, setArtifact] = useState<Artifact | null>(null)
  const [claim, setClaim] = useState<Claim | null>(null)
  const [status, setStatus] = useState<ClaimStatus>("parked")
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadingArtifact, setLoadingArtifact] = useState(false)
  const [docTab, setDocTab] = useState<DocTab>("doc")

  const handleRefresh = useCallback(() => {
    setRefreshKey(k => k + 1)
  }, [])

  const handleSelect = useCallback((id: string | null) => {
    setShowGraph(false)
    setSelectedArtifactId(id)
    setDocTab("doc")
  }, [])

  const handleShowGraph = useCallback(() => {
    setShowGraph(true)
  }, [])

  // Fetch artifact + claim + status when selection changes
  useEffect(() => {
    if (!selectedArtifactId) {
      setArtifact(null)
      setClaim(null)
      setStatus("parked")
      setLoadError(null)
      return
    }

    let cancelled = false
    setLoadingArtifact(true)
    setLoadError(null)

    async function load() {
      try {
        const [{ artifact: art }, { events }] = await Promise.all([
          getArtifact(selectedArtifactId!),
          getTrajectory(selectedArtifactId!),
        ])
        if (cancelled) return

        setArtifact(art)
        setStatus(deriveClaimStatus(events))

        // Find the claim from artifact's park event or from the artifact itself
        // The park event should have a claim, or we fetch from the first claim reference
        const parkEvent = events.find(e => e.type === "park")
        const claimId = parkEvent?.target_ref || (parkEvent?.payload?.claim_id as string | undefined)
        if (claimId) {
          const { claim: c } = await getClaim(claimId)
          if (!cancelled) setClaim(c)
        } else {
          // Fallback: the claim body might be in the artifact goal
          if (!cancelled) {
            setClaim({
              id: "",
              library_id: art.library_id,
              body: art.goal,
              artifact_ids: [art.id],
              created_at: art.created_at,
              updated_at: art.updated_at,
            })
          }
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : "Failed to load artifact")
        }
      } finally {
        if (!cancelled) setLoadingArtifact(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [selectedArtifactId, refreshKey])

  const renderContent = () => {
    // Library-level corpus graph view takes precedence over artifact views.
    if (showGraph) {
      return <CorpusGraphView libraryId={LIBRARY_ID} />
    }

    // No selection: show park view
    if (selectedArtifactId === null) {
      return <ParkView onRefresh={handleRefresh} onSelect={(id) => setSelectedArtifactId(id)} />
    }

    // Loading
    if (loadingArtifact) {
      return (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-zinc-500">Loading...</p>
        </div>
      )
    }

    // Error
    if (loadError) {
      return (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-red-400">{loadError}</p>
        </div>
      )
    }

    // No artifact loaded
    if (!artifact || !claim) {
      return <EmptyState />
    }

    // Parked or grilling: show GrillView
    if (status === "parked" || status === "grilling") {
      return (
        <GrillView
          artifactId={artifact.id}
          claim={claim}
          artifact={artifact}
          onRefresh={handleRefresh}
        />
      )
    }

    // Survived or killed: show tab toggle between doc and trajectory
    return (
      <div className="flex-1 flex flex-col overflow-hidden bg-zinc-950">
        {/* Tab bar */}
        <div className="shrink-0 border-b border-zinc-800 px-5 flex gap-0">
          <button
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              docTab === "doc"
                ? "border-purple-500 text-purple-300"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
            onClick={() => setDocTab("doc")}
          >
            DOC
          </button>
          <button
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              docTab === "trajectory"
                ? "border-purple-500 text-purple-300"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
            onClick={() => setDocTab("trajectory")}
          >
            轨迹
          </button>
          <button
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              docTab === "versions"
                ? "border-purple-500 text-purple-300"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
            onClick={() => setDocTab("versions")}
          >
            版本
          </button>
          <div className="flex-1" />
          <div className="flex items-center pr-1">
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                status === "survived"
                  ? "bg-emerald-700/50 text-emerald-200"
                  : "bg-red-700/50 text-red-200"
              }`}
            >
              {status === "survived" ? "SURVIVED" : "KILLED"}
            </span>
          </div>
        </div>

        {/* Tab content */}
        {docTab === "doc" ? (
          <DocView artifactId={artifact.id} libraryId={artifact.library_id} />
        ) : docTab === "trajectory" ? (
          <TrajectoryView artifactId={artifact.id} />
        ) : (
          <VersionsView artifactId={artifact.id} />
        )}
      </div>
    )
  }

  return (
    <div className="h-screen flex bg-zinc-950 text-zinc-100">
      <Sidebar
        selectedId={selectedArtifactId}
        onSelect={handleSelect}
        refreshKey={refreshKey}
        showGraph={showGraph}
        onShowGraph={handleShowGraph}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        {renderContent()}
      </main>
    </div>
  )
}

export default App
