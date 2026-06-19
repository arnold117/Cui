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

const EDGE_COLOR: Record<GraphEdge["type"], string> = {
  contradicts: "#f87171", // red-400
  grounds: "#52525b", // zinc-600
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
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    api
      .getCorpusGraph(libraryId)
      .then(g => {
        if (!cancelled) {
          setGraph(g)
          setLoading(false)
        }
      })
      .catch(e => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load corpus graph")
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [libraryId])

  const positioned = useMemo(() => (graph ? layout(graph) : []), [graph])
  const posById = useMemo(() => {
    const m = new Map<string, Positioned>()
    for (const n of positioned) m.set(n.id, n)
    return m
  }, [positioned])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-zinc-950">
        <p className="text-sm text-zinc-500">Loading corpus graph...</p>
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
          <span className="flex items-center gap-1.5">
            <svg width="22" height="8">
              <line x1="0" y1="4" x2="22" y2="4" stroke={EDGE_COLOR.contradicts} strokeWidth="2" />
            </svg>
            contradicts
          </span>
          <span className="flex items-center gap-1.5">
            <svg width="22" height="8">
              <line x1="0" y1="4" x2="22" y2="4" stroke={EDGE_COLOR.grounds} strokeWidth="2" />
            </svg>
            grounds
          </span>
        </div>
      </div>

      {/* Graph */}
      <div className="flex-1 overflow-auto p-4">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full h-full"
          style={{ minHeight: HEIGHT }}
        >
          {/* edges first (under nodes) */}
          {graph!.edges.map((e, i) => {
            const s = posById.get(e.source)
            const t = posById.get(e.target)
            if (!s || !t) return null
            return (
              <line
                key={`e-${i}`}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={EDGE_COLOR[e.type]}
                strokeWidth={e.type === "contradicts" ? 2 : 1.5}
                strokeDasharray={e.type === "contradicts" ? "5 4" : undefined}
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
