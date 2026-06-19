import { useEffect, useState } from "react"
import type { Material, Event } from "../types"
import { collectMaterials, listMaterials, autoGround, confirmEvent, getEvidence } from "../api"

interface Props {
  artifactId: string
  libraryId: string
  claimId: string
  claimBody: string
  onGrounded?: () => void
}

function paperMeta(material: Material): { title: string; authors: string; year: string; venue: string } {
  const p = material.payload
  const title = (p.title as string) || "未命名文献"
  const authorsRaw = p.authors
  const authors = Array.isArray(authorsRaw) ? (authorsRaw as unknown[]).join(", ") : ""
  const year = p.year != null ? String(p.year) : ""
  const venue = (p.venue as string) || ""
  return { title, authors, year, venue }
}

export default function EvidencePanel({ artifactId, libraryId, claimId, claimBody, onGrounded }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [materials, setMaterials] = useState<Material[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)

  // Already-confirmed grounding evidence (persisted across sessions).
  const [confirmedEvidence, setConfirmedEvidence] = useState<Event[]>([])

  const loadConfirmedEvidence = async () => {
    try {
      const { events } = await getEvidence(artifactId, claimId)
      setConfirmedEvidence(events)
    } catch {
      // Read-only enrichment — a fetch failure shouldn't break the panel.
    }
  }

  // Fetch confirmed evidence whenever the panel opens (or the claim changes).
  useEffect(() => {
    if (open) loadConfirmedEvidence()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, artifactId, claimId])

  // Per-material grounding state, keyed by material id.
  const [grounding, setGrounding] = useState<Record<string, boolean>>({})
  const [groundEvents, setGroundEvents] = useState<Record<string, Event>>({})
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({})
  const [groundErrors, setGroundErrors] = useState<Record<string, string>>({})

  const handleSearch = async () => {
    const q = query.trim()
    if (!q) return
    setSearching(true)
    setError(null)
    try {
      await collectMaterials(artifactId, libraryId, q)
      const { materials: all } = await listMaterials(artifactId)
      setMaterials(all)
      setSearched(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : "搜索失败")
    } finally {
      setSearching(false)
    }
  }

  const handleGround = async (material: Material) => {
    setGrounding(g => ({ ...g, [material.id]: true }))
    setGroundErrors(e => {
      const next = { ...e }
      delete next[material.id]
      return next
    })
    try {
      const { event } = await autoGround(artifactId, claimId, claimBody, material.id)
      setGroundEvents(ge => ({ ...ge, [material.id]: event }))
    } catch (e) {
      setGroundErrors(errs => ({ ...errs, [material.id]: e instanceof Error ? e.message : "取证失败" }))
    } finally {
      setGrounding(g => ({ ...g, [material.id]: false }))
    }
  }

  const handleConfirm = async (materialId: string, eventId: string) => {
    try {
      await confirmEvent(artifactId, eventId)
      setConfirmed(c => ({ ...c, [materialId]: true }))
      // Surface the freshly-confirmed evidence in the persisted list too.
      await loadConfirmedEvidence()
      onGrounded?.()
    } catch (e) {
      setGroundErrors(errs => ({ ...errs, [materialId]: e instanceof Error ? e.message : "确认失败" }))
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSearch()
    }
  }

  return (
    <div className="mt-3 border border-zinc-800 rounded-lg bg-zinc-900/40">
      <button
        className="w-full flex items-center justify-between px-4 py-2 text-left"
        onClick={() => setOpen(o => !o)}
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-purple-300">
          证据 / 文献
        </span>
        <span className="text-xs text-zinc-500">{open ? "收起 ▲" : "展开 ▼"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          {/* Already-confirmed evidence (persisted) */}
          {confirmedEvidence.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-300/80">
                已确认证据
              </p>
              <ul className="space-y-2">
                {confirmedEvidence.map(ev => {
                  const supported = ev.payload.supported as boolean
                  const title = (ev.payload.title as string) || "未命名文献"
                  const evidence = ev.payload.evidence as string | undefined
                  const assessment = ev.payload.assessment as string | undefined
                  return (
                    <li
                      key={ev.id}
                      className="border border-emerald-900/50 rounded-lg px-3 py-2.5 bg-emerald-950/20"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm text-zinc-200 leading-snug min-w-0">{title}</p>
                        <span className="shrink-0 text-[10px] font-medium text-emerald-400 bg-emerald-900/40 px-2 py-0.5 rounded-full">
                          已确认
                        </span>
                      </div>
                      <div className="mt-1.5 space-y-1">
                        <span
                          className={
                            "text-xs font-semibold " +
                            (supported ? "text-emerald-400" : "text-red-400")
                          }
                        >
                          {supported ? "✓ 支持" : "✗ 不支持"}
                        </span>
                        {Boolean(evidence) && (
                          <p className="text-xs text-zinc-400 leading-relaxed">
                            <span className="text-zinc-600">证据：</span>
                            {evidence}
                          </p>
                        )}
                        {Boolean(assessment) && (
                          <p className="text-xs text-zinc-400 leading-relaxed">
                            <span className="text-zinc-600">评估：</span>
                            {assessment}
                          </p>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {/* Search bar */}
          <div className="flex gap-2">
            <input
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
              placeholder="搜索相关文献（关键词）..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={searching}
            />
            <button
              className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={handleSearch}
              disabled={searching || !query.trim()}
            >
              {searching ? "搜索中..." : "搜文献"}
            </button>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          {/* Results */}
          {searched && materials.length === 0 && !searching && (
            <p className="text-sm text-zinc-500">没有找到相关文献。换个关键词试试？</p>
          )}

          {!searched && materials.length === 0 && (
            <p className="text-xs text-zinc-600 leading-relaxed">
              搜索文献后，可以让 AI 判定每篇文献是否支持当前 claim，再由你确认。
            </p>
          )}

          {materials.length > 0 && (
            <ul className="space-y-2">
              {materials.map(material => {
                const meta = paperMeta(material)
                const event = groundEvents[material.id]
                const isGrounding = grounding[material.id]
                const isConfirmed = confirmed[material.id]
                const gErr = groundErrors[material.id]
                const supported = event ? (event.payload.supported as boolean) : null
                return (
                  <li
                    key={material.id}
                    className="border border-zinc-800 rounded-lg px-3 py-2.5 bg-zinc-900/60"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm text-zinc-200 leading-snug">{meta.title}</p>
                        <p className="text-xs text-zinc-500 mt-0.5">
                          {[meta.authors, meta.year, meta.venue].filter(Boolean).join(" · ")}
                        </p>
                      </div>
                      {!event && (
                        <button
                          className="shrink-0 px-3 py-1 bg-amber-700/70 hover:bg-amber-600 text-amber-100 text-xs font-medium rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                          onClick={() => handleGround(material)}
                          disabled={isGrounding}
                        >
                          {isGrounding ? "取证中..." : "取证"}
                        </button>
                      )}
                    </div>

                    {gErr && <p className="text-red-400 text-xs mt-2">{gErr}</p>}

                    {/* Pending GROUND event inline */}
                    {event && (
                      <div className="mt-2 border-t border-zinc-800 pt-2 space-y-1.5">
                        <div className="flex items-center gap-2">
                          <span
                            className={
                              "text-xs font-semibold " +
                              (supported ? "text-emerald-400" : "text-red-400")
                            }
                          >
                            {supported ? "✓ 支持" : "✗ 不支持"}
                          </span>
                          {!isConfirmed && (
                            <span className="text-xs text-amber-500/80">待确认</span>
                          )}
                          {isConfirmed && (
                            <span className="text-xs text-emerald-500/80">已确认</span>
                          )}
                        </div>
                        {Boolean(event.payload.evidence) && (
                          <p className="text-xs text-zinc-400 leading-relaxed">
                            <span className="text-zinc-600">证据：</span>
                            {event.payload.evidence as string}
                          </p>
                        )}
                        {Boolean(event.payload.assessment) && (
                          <p className="text-xs text-zinc-400 leading-relaxed">
                            <span className="text-zinc-600">评估：</span>
                            {event.payload.assessment as string}
                          </p>
                        )}
                        {!isConfirmed && (
                          <button
                            className="mt-1 px-3 py-1 bg-zinc-100 text-zinc-900 text-xs font-medium rounded-md hover:bg-white transition-colors"
                            onClick={() => handleConfirm(material.id, event.id)}
                          >
                            确认
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
