import { useEffect, useMemo, useState } from "react"
import * as api from "../api"
import type { CorpusGraph, GraphEdge, GraphNode } from "../types"

interface Props {
  libraryId?: string
}

interface Positioned extends GraphNode {
  x: number
  y: number
}

// --- styling helpers -------------------------------------------------------

const CLAIM_FILL: Record<string, string> = {
  survived: "#10b981", // emerald-500
  killed: "#ef4444", // red-500
  parked: "#f59e0b", // amber-500
  open: "#71717a", // zinc-500
}

function claimFill(status: string | null): string {
  return (status && CLAIM_FILL[status]) || CLAIM_FILL.open
}

const MATERIAL_FILL = "#1e3a5f" // muted blue
const MATERIAL_STROKE = "#60a5fa" // blue-400

// Per-edge-type visual style. Five semantic groups, each visually distinct but
// kept within the zinc-950 dark idiom:
//   contradicts            — red dashed (tension)
//   grounds                — zinc solid (evidence)
//   builds_on/depends_on   — emerald/teal solid, DIRECTIONAL (arrowhead)
//   shares_method/shares_gap — violet/indigo dotted (similarity, undirected)
//   narrowed_from          — amber dash-dot, DIRECTIONAL (划界死 lineage:
//                            successor → killed claim; deterministic, non-LLM)
interface EdgeStyle {
  color: string
  width: number
  dash?: string
  directed?: boolean
}

const EDGE_STYLE: Record<GraphEdge["type"], EdgeStyle> = {
  contradicts: { color: "#f87171", width: 2, dash: "5 4" }, // red-400
  grounds: { color: "#52525b", width: 1.5 }, // zinc-600
  builds_on: { color: "#34d399", width: 1.8, directed: true }, // emerald-400
  depends_on: { color: "#2dd4bf", width: 1.8, directed: true }, // teal-400
  shares_method: { color: "#a78bfa", width: 1.6, dash: "2 4" }, // violet-400
  shares_gap: { color: "#818cf8", width: 1.6, dash: "2 4" }, // indigo-400
  narrowed_from: { color: "#fbbf24", width: 1.8, dash: "8 3 2 3", directed: true }, // amber-400
}

// Unique color used per directed type for its own arrowhead marker.
const DIRECTED_MARKER: Partial<Record<GraphEdge["type"], string>> = {
  builds_on: EDGE_STYLE.builds_on.color,
  depends_on: EDGE_STYLE.depends_on.color,
  narrowed_from: EDGE_STYLE.narrowed_from.color,
}

function truncate(s: string, n = 28): string {
  if (s.length <= n) return s
  return s.slice(0, n - 1) + "…"
}

// --- deterministic layout --------------------------------------------------
//
// Dependency-light: claims are placed evenly on a circle; each material is
// offset just outside the first claim it grounds (so groundings read as
// satellites). Ungrounded materials fall onto an outer ring. Fully
// deterministic — same graph always renders the same way.

const WIDTH = 900
const HEIGHT = 640
const CX = WIDTH / 2
const CY = HEIGHT / 2

function layout(graph: CorpusGraph): Positioned[] {
  const claims = graph.nodes.filter(n => n.type === "claim")
  const materials = graph.nodes.filter(n => n.type === "material")

  const positions = new Map<string, { x: number; y: number }>()

  // Claims evenly on a circle (single claim sits at center).
  const claimRadius = Math.min(WIDTH, HEIGHT) * 0.32
  const claimAngle = new Map<string, number>()
  claims.forEach((c, i) => {
    if (claims.length === 1) {
      positions.set(c.id, { x: CX, y: CY })
      claimAngle.set(c.id, 0)
      return
    }
    const angle = (i / claims.length) * Math.PI * 2 - Math.PI / 2
    claimAngle.set(c.id, angle)
    positions.set(c.id, {
      x: CX + claimRadius * Math.cos(angle),
      y: CY + claimRadius * Math.sin(angle),
    })
  })

  // Map material -> a claim it grounds (first match), to anchor it nearby.
  const groundedBy = new Map<string, string>()
  for (const e of graph.edges) {
    if (e.type !== "grounds") continue
    // grounds edge: material grounds claim (orientation-agnostic — pick the
    // endpoint that is a material vs claim).
    const sourceIsMaterial = materials.some(m => m.id === e.source)
    const matId = sourceIsMaterial ? e.source : e.target
    const claimId = sourceIsMaterial ? e.target : e.source
    if (!groundedBy.has(matId)) groundedBy.set(matId, claimId)
  }

  // Count materials per anchor claim so we can fan them out.
  const perClaimCount = new Map<string, number>()
  const perClaimIndex = new Map<string, number>()
  for (const m of materials) {
    const anchor = groundedBy.get(m.id)
    if (anchor) perClaimCount.set(anchor, (perClaimCount.get(anchor) || 0) + 1)
  }

  const outerRadius = claimRadius + 150
  materials.forEach((m, i) => {
    const anchor = groundedBy.get(m.id)
    if (anchor && positions.has(anchor)) {
      const base = claimAngle.get(anchor) ?? 0
      const count = perClaimCount.get(anchor) || 1
      const idx = perClaimIndex.get(anchor) || 0
      perClaimIndex.set(anchor, idx + 1)
      // fan materials in a small arc pointing outward from center
      const spread = 0.5
      const offset = count > 1 ? (idx - (count - 1) / 2) * spread : 0
      const angle = base + offset
      const r = claimRadius + 110
      positions.set(m.id, {
        x: CX + r * Math.cos(angle),
        y: CY + r * Math.sin(angle),
      })
    } else {
      // ungrounded material — outer ring
      const angle = (i / Math.max(materials.length, 1)) * Math.PI * 2
      positions.set(m.id, {
        x: CX + outerRadius * Math.cos(angle),
        y: CY + outerRadius * Math.sin(angle),
      })
    }
  })

  return graph.nodes.map(n => {
    const p = positions.get(n.id) || { x: CX, y: CY }
    return { ...n, x: p.x, y: p.y }
  })
}

// --- component -------------------------------------------------------------

export default function CorpusGraphView({ libraryId = "default" }: Props) {
  const [graph, setGraph] = useState<CorpusGraph | null>(null)
  const [loading, setLoading] = useState(true)
  // `building` shows the "算关系中…" hint while semantic edges are computed.
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Lazy-compute semantic edges, THEN fetch the graph. buildEdges failures
  // (e.g. 501 when no LLM is configured, or any network error) are swallowed —
  // the structural Tier 0 graph must still render. Only a getCorpusGraph
  // failure is a real error worth surfacing.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setBuilding(true)
    setError(null)

    api
      .buildEdges(libraryId)
      .catch(() => {
        /* swallow — graph renders with whatever edges already exist */
      })
      .then(() => {
        if (cancelled) return
        setBuilding(false)
        return api.getCorpusGraph(libraryId)
      })
      .then(g => {
        if (cancelled || !g) return
        setGraph(g)
        setLoading(false)
      })
      .catch(e => {
        if (cancelled) return
        setBuilding(false)
        setError(e instanceof Error ? e.message : "Failed to load corpus graph")
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [libraryId])

  // Manual "重算关系" — recompute semantic edges then refetch. Keeps the
  // current graph on-screen (no full-screen loader); shows the building hint
  // in the header. buildEdges errors are swallowed here too.
  async function recompute() {
    if (building) return
    setBuilding(true)
    setError(null)
    try {
      await api.buildEdges(libraryId).catch(() => {})
      const g = await api.getCorpusGraph(libraryId)
      setGraph(g)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load corpus graph")
    } finally {
      setBuilding(false)
    }
  }

  const positioned = useMemo(() => (graph ? layout(graph) : []), [graph])
  const posById = useMemo(() => {
    const m = new Map<string, Positioned>()
    for (const n of positioned) m.set(n.id, n)
    return m
  }, [positioned])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-zinc-950">
        <p className="text-sm text-zinc-500">
          {building ? "算关系中…" : "Loading corpus graph..."}
        </p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center bg-zinc-950">
        <p className="text-sm text-red-400">{error}</p>
      </div>
    )
  }

  // Empty only when there are no nodes at all. Isolated claim nodes (no
  // confirmed edges yet) still render — you want to SEE your corpus, not a
  // blank screen just because relationships haven't formed.
  const isEmpty = !graph || graph.nodes.length === 0

  if (isEmpty) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-zinc-950 px-8 text-center">
        <p className="text-2xl mb-3">🌱</p>
        <p className="text-sm text-zinc-300 font-medium">语料图还是空的</p>
        <p className="text-sm text-zinc-500 mt-2 max-w-md leading-relaxed">
          去 grill 几个想法、确认一些矛盾 / 取证，关系就会长出来。
        </p>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-zinc-950">
      {/* Header + legend */}
      <div className="shrink-0 border-b border-zinc-800 px-5 py-3 flex items-center gap-6">
        <span className="text-sm font-medium text-zinc-200">语料图 · Corpus Graph</span>
        <div className="flex items-center gap-4 text-[11px] text-zinc-400 flex-wrap">
          <LegendDot color={CLAIM_FILL.survived} label="survived" />
          <LegendDot color={CLAIM_FILL.killed} label="killed" />
          <LegendDot color={CLAIM_FILL.parked} label="parked" />
          <LegendDot color={CLAIM_FILL.open} label="open" />
          <span className="flex items-center gap-1.5">
            <svg width="20" height="10">
              <rect x="2" y="1" width="14" height="8" rx="2" fill={MATERIAL_FILL} stroke={MATERIAL_STROKE} />
            </svg>
            material
          </span>
          <LegendEdge style={EDGE_STYLE.contradicts} label="矛盾 contradicts" />
          <LegendEdge style={EDGE_STYLE.grounds} label="取证 grounds" />
          <LegendEdge style={EDGE_STYLE.builds_on} label="承接 builds_on·depends_on" />
          <LegendEdge style={EDGE_STYLE.shares_method} label="相似 shares_method·shares_gap" />
          <LegendEdge style={EDGE_STYLE.narrowed_from} label="收窄 narrowed_from" />
        </div>
        <button
          type="button"
          onClick={recompute}
          disabled={building}
          className="ml-auto shrink-0 rounded border border-zinc-700 px-2.5 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {building ? "算关系中…" : "重算关系"}
        </button>
      </div>

      {/* Graph */}
      <div className="flex-1 overflow-auto p-4">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full h-full"
          style={{ minHeight: HEIGHT }}
        >
          {/* arrowhead markers for directional (ancestry/dependency) edges */}
          <defs>
            {Object.entries(DIRECTED_MARKER).map(([type, color]) => (
              <marker
                key={type}
                id={`arrow-${type}`}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
              </marker>
            ))}
          </defs>

          {/* edges first (under nodes) */}
          {graph!.edges.map((e, i) => {
            const s = posById.get(e.source)
            const t = posById.get(e.target)
            if (!s || !t) return null
            const st = EDGE_STYLE[e.type]
            return (
              <line
                key={`e-${i}`}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={st.color}
                strokeWidth={st.width}
                strokeDasharray={st.dash}
                markerEnd={st.directed ? `url(#arrow-${e.type})` : undefined}
                opacity={0.8}
              />
            )
          })}

          {/* nodes */}
          {positioned.map(n => (
            <NodeShape key={n.id} node={n} />
          ))}
        </svg>
      </div>
    </div>
  )
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

function LegendEdge({ style, label }: { style: EdgeStyle; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <svg width="22" height="8">
        <line
          x1="0"
          y1="4"
          x2={style.directed ? 16 : 22}
          y2="4"
          stroke={style.color}
          strokeWidth={style.width}
          strokeDasharray={style.dash}
        />
        {style.directed && (
          <path d="M 16 1 L 22 4 L 16 7 z" fill={style.color} />
        )}
      </svg>
      {label}
    </span>
  )
}

function NodeShape({ node }: { node: Positioned }) {
  const label = truncate(node.label)
  if (node.type === "material") {
    const w = 120
    const h = 30
    return (
      <g>
        <title>{node.label}</title>
        <rect
          x={node.x - w / 2}
          y={node.y - h / 2}
          width={w}
          height={h}
          rx={4}
          fill={MATERIAL_FILL}
          stroke={MATERIAL_STROKE}
          strokeWidth={1.5}
        />
        <text
          x={node.x}
          y={node.y}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={11}
          fill="#dbeafe"
        >
          {truncate(node.label, 18)}
        </text>
      </g>
    )
  }

  // claim node — circle with label below
  const r = 26
  return (
    <g>
      <title>{node.label}</title>
      <circle
        cx={node.x}
        cy={node.y}
        r={r}
        fill={claimFill(node.status)}
        stroke="#18181b"
        strokeWidth={2}
      />
      <text
        x={node.x}
        y={node.y + r + 13}
        textAnchor="middle"
        fontSize={11}
        fill="#d4d4d8"
      >
        {label}
      </text>
    </g>
  )
}
