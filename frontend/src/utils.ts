import type { Event, ClaimStatus } from "./types"

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

  if (lastOutcome === "survive") return "survived"
  if (lastOutcome === "kill") return "killed"
  return "grilling"
}
