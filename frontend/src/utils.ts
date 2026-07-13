import type { Event, ClaimStatus } from "./types"

// 死因分诊 display maps, shared by the verdict bubbles (GrillMessage), the
// trajectory event cards (EventCard) and the triage panel.
export const DEATH_CAUSE_LABELS: Record<string, string> = {
  refuted: "本质死 refuted",
  not_worth: "品味死 not_worth",
  boundary: "划界死 boundary",
  circumstantial: "偶然死 circumstantial",
}

export const DEATH_CAUSE_BADGE_CLASSES: Record<string, string> = {
  refuted: "bg-red-800/60 text-red-200 border-red-700/50",
  not_worth: "bg-amber-700/40 text-amber-200 border-amber-600/40",
  boundary: "bg-sky-700/40 text-sky-200 border-sky-600/40",
  circumstantial: "bg-zinc-600/50 text-zinc-200 border-zinc-500/40",
}

// One-line 说明 per cause, shown in the triage picker.
export const DEATH_CAUSE_HINTS: Record<string, string> = {
  refuted: "真值轴：就是错的（含重复死）",
  not_worth: "价值轴：对，但不值得做",
  boundary: "收窄换活：可关联后继 claim",
  circumstantial: "哪根轴都没死透：必附复活条件",
}

// ---------------------------------------------------------------------------
// Timestamps. Backend `ts` is naive UTC (datetime.utcnow) serialized WITHOUT a
// timezone suffix ("2026-07-13T06:19:59.123456"). `new Date(...)` would parse
// that as LOCAL time and display raw UTC — so we append "Z" when no timezone
// designator is present, then render in the browser's local timezone.
// Timestamps that already carry a designator (Z or ±hh:mm) are parsed as-is.
// ---------------------------------------------------------------------------

export function parseBackendTs(ts: string): Date {
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(ts)
  return new Date(hasTimezone ? ts : ts + "Z")
}

/** "Jul 13, 14:19" — date + time, local timezone, 24-hour clock. */
export function formatTimestamp(ts: string): string {
  return parseBackendTs(ts).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}

/** "14:19" — time only, local timezone, 24-hour clock. */
export function formatTime(ts: string): string {
  return parseBackendTs(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}

export function deriveClaimStatus(events: Event[]): ClaimStatus {
  const retracted = new Set<string>()
  for (const e of events) {
    if (e.type === "retract" && e.target_ref) retracted.add(e.target_ref)
  }

  const confirmed = new Set<string>()
  for (const e of events) {
    if (e.type === "confirm" && e.target_ref && !retracted.has(e.id)) {
      confirmed.add(e.target_ref)
    }
  }

  const hasGrill = events.some(e => ["challenge", "answer", "verdict"].includes(e.type))
  const hasPark = events.some(e => e.type === "park")
  const hasPromote = events.some(e => e.type === "promote" && !retracted.has(e.id))

  if (hasPark && !hasGrill) return "parked"

  // Find last confirmed verdict
  let lastOutcome: string | null = null
  for (const e of events) {
    if (e.type === "verdict" && !retracted.has(e.id)) {
      if (e.confirmed || confirmed.has(e.id)) {
        lastOutcome = e.payload.outcome as string
      }
    }
  }

  if (lastOutcome === "kill") return "killed"
  // "survived" requires an explicit promote event — a confirmed survive verdict
  // alone means the grill flow is still active (user hasn't promoted yet)
  if (lastOutcome === "survive" && hasPromote) return "survived"
  if (hasGrill) return "grilling"
  return "grilling"
}
