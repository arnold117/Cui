import { useState } from "react"
import { DEATH_CAUSE_BADGE_CLASSES, DEATH_CAUSE_LABELS } from "../utils"
import { getClaimPrecedent } from "../api"

// ---------------------------------------------------------------------------
// 判例先验 (precedent prior, spec-precedent-prior §2 Q5) — the SHARED 溯源
// surface. The main-line auto_challenge aims its question with the
// researcher's OWN kill precedents and reports back which ones it used as
// `precedent_refs` (hallucinated ids already dropped backend-side). This trace
// is what keeps 本刀 auditable instead of a black-box 改良.
//
// Lives here, once, because BOTH the grill stream (GrillMessage) and the
// trajectory replay (EventCard) show it. The whole point of this cut is to
// kill duplicate implementations of one trust chain — a second copy of the
// badge would reintroduce the disease in the UI layer.
//
//   文案红线 (前科定罪): the copy may say where the ANGLE of the question came
//   from. It may NOT suggest the current claim resembles a past kill, nor that
//   anything is being repeated — that would be the UI passing the verdict the
//   system is forbidden to pass.
//
// Resolution is USER-ACTION-DRIVEN (click to expand → fetch once). No effect
// watches derived state; this app has already paid for that pattern once.
// ---------------------------------------------------------------------------

export interface PrecedentEntry {
  claimId: string
  /** null when the claim can no longer be resolved — the row stays, honestly. */
  body: string | null
  /** Where the claim was parked — the click-through target. */
  artifactId?: string
  /** Only when the ruling verdict is a kill AND carries a cause. Legacy kills
   *  show no badge (投影语义: 未分类, never invented — mirrors EventCard). */
  deathCause?: string
}

/**
 * ONE request per cited 判例. The ruling-verdict selection rule (retracted
 * dropped / CONFIRMED only / last ruling wins) is NOT re-derived here — it is
 * read off the backend `verdict_precedent` projection through
 * `GET /claim/{id}/precedent`, so there is exactly one implementation of the
 * confirm gate to keep honest.
 */
async function resolvePrecedent(claimId: string): Promise<PrecedentEntry> {
  try {
    const { claim, precedent } = await getClaimPrecedent(claimId)
    return {
      claimId,
      body: claim.body,
      artifactId: claim.artifact_ids[0],
      deathCause:
        precedent && precedent.outcome === "kill"
          ? precedent.death_cause ?? undefined
          : undefined,
    }
  } catch {
    // Unresolvable claim (deleted / 404) — the row stays and says so.
    return { claimId, body: null }
  }
}

/**
 * Trace state for one challenge's `precedent_refs`. Fetch fires on the user's
 * click and exactly once per event; nothing observes derived state.
 */
export function usePrecedentTrace(refs: string[]) {
  const [expanded, setExpanded] = useState(false)
  const [entries, setEntries] = useState<PrecedentEntry[] | null>(null)
  const [resolving, setResolving] = useState(false)

  const toggle = () => {
    const next = !expanded
    setExpanded(next)
    if (!next || entries !== null || resolving) return
    setResolving(true)
    Promise.all(refs.map(resolvePrecedent))
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setResolving(false))
  }

  return { expanded, entries, resolving, toggle }
}

/** The chip itself. Callers place it in their own header row. */
export function PrecedentBadge({
  count,
  expanded,
  onToggle,
}: {
  count: number
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className="text-[10px] font-semibold text-violet-200 bg-violet-700/50 border border-violet-600/40 px-1.5 py-0.5 rounded-full hover:bg-violet-700/70 transition-colors"
    >
      ⟲ 提问角度来自 {count} 条判例 {expanded ? "▾" : "▸"}
    </button>
  )
}

function PrecedentRow({
  entry,
  onOpenArtifact,
}: {
  entry: PrecedentEntry
  onOpenArtifact?: (artifactId: string) => void
}) {
  const clickable = Boolean(onOpenArtifact && entry.artifactId)
  const body = entry.body
  const preview =
    body === null
      ? "这条判例已读不到（claim 不可解析）"
      : body.length > 90
        ? body.slice(0, 89) + "…"
        : body

  return (
    <button
      type="button"
      disabled={!clickable}
      title={body ?? entry.claimId}
      onClick={() => {
        if (clickable) onOpenArtifact!(entry.artifactId!)
      }}
      className={`w-full text-left rounded-md border border-zinc-700/50 bg-zinc-900/50 px-2 py-1.5 space-y-1 ${
        clickable
          ? "hover:bg-zinc-800/70 hover:border-violet-600/50 cursor-pointer"
          : "cursor-default"
      }`}
    >
      {entry.deathCause && (
        <span
          className={`inline-block text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${
            DEATH_CAUSE_BADGE_CLASSES[entry.deathCause] ??
            "bg-zinc-600/50 text-zinc-200 border-zinc-500/40"
          }`}
        >
          {DEATH_CAUSE_LABELS[entry.deathCause] ?? entry.deathCause}
        </span>
      )}
      <span
        className={`block text-[11px] leading-relaxed ${
          body === null ? "text-zinc-500 italic" : "text-zinc-300"
        }`}
      >
        {preview}
      </span>
    </button>
  )
}

/**
 * The expanded 溯源 panel — 取证形状: what the question was aimed WITH, never
 * a judgement on the claim being grilled. The 红线 line under the heading is
 * the last guard against 前科定罪 being read into the badge, so it is kept
 * legible (zinc-400, AA on this panel) rather than decorative — still
 * subordinate to the question, but not something the eye slides past.
 */
export function PrecedentPanel({
  entries,
  resolving,
  onOpenArtifact,
}: {
  entries: PrecedentEntry[] | null
  resolving: boolean
  onOpenArtifact?: (artifactId: string) => void
}) {
  return (
    <div className="mt-2.5 rounded-lg border border-violet-800/40 bg-violet-950/30 px-2.5 py-2 space-y-1.5">
      <p className="text-[11px] text-violet-200/90 leading-relaxed">
        这一问的提问角度参考了你自己 kill 过的这几条 claim
      </p>
      <p className="text-[10px] text-zinc-400 leading-relaxed">
        判例只决定「从哪个角度问」——过去的 kill 不是当下的证据，也不是对这条 claim 的判断
      </p>
      {resolving && <p className="text-[10px] text-zinc-500">读取判例中...</p>}
      {entries?.map(entry => (
        <PrecedentRow
          key={entry.claimId}
          entry={entry}
          onOpenArtifact={onOpenArtifact}
        />
      ))}
    </div>
  )
}
