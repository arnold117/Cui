import { useState, useEffect, useCallback, useRef } from "react"
import type { Event, Claim } from "../types"
import * as api from "../api"

export type GrillPhase =
  | "idle"
  | "starting"
  | "challenging"
  | "awaiting_answer"
  | "answering"
  | "verdicting"
  | "awaiting_decision"
  | "confirmed_survive"
  | "confirmed_kill"
  | "done"

export interface GrillFlowState {
  events: Event[]
  phase: GrillPhase
  error: string | null
  loading: boolean
  unresolved: string[]
  rounds: number
}

export interface GrillFlowActions {
  startGrill: () => void
  submitAnswer: (text: string) => void
  confirmVerdict: (eventId: string) => void
  retractVerdict: (eventId: string) => void
  continueGrill: () => void
  stopGrill: () => void
  refreshEvents: () => void
}

// ---------------------------------------------------------------------------
// Phase reconstruction from event list
// ---------------------------------------------------------------------------

function getRetractedIds(events: Event[]): Set<string> {
  const retracted = new Set<string>()
  for (const e of events) {
    if (e.type === "retract" && e.target_ref) retracted.add(e.target_ref)
  }
  return retracted
}

function getConfirmedIds(events: Event[]): Set<string> {
  const retracted = getRetractedIds(events)
  const confirmed = new Set<string>()
  for (const e of events) {
    if (e.type === "confirm" && e.target_ref && !retracted.has(e.id)) {
      confirmed.add(e.target_ref)
    }
  }
  return confirmed
}

function countRounds(events: Event[]): number {
  return events.filter(e => e.type === "challenge").length
}

function computeUnresolved(events: Event[]): string[] {
  const retracted = getRetractedIds(events)
  const confirmed = getConfirmedIds(events)
  const unresolved: string[] = []

  for (const e of events) {
    if (e.type === "challenge" && !retracted.has(e.id)) {
      // Check if there's a corresponding survived verdict
      const question = (e.payload.question as string) ?? ""
      const hasResolution = events.some(
        v =>
          v.type === "verdict" &&
          !retracted.has(v.id) &&
          (v.confirmed || confirmed.has(v.id)) &&
          v.payload.outcome === "survive"
      )
      if (!hasResolution) {
        unresolved.push(question)
      }
    }
  }

  return unresolved
}

function reconstructPhase(events: Event[]): GrillPhase {
  const retracted = getRetractedIds(events)
  const confirmed = getConfirmedIds(events)

  const hasPark = events.some(e => e.type === "park")
  const grillEvents = events.filter(e =>
    ["challenge", "answer", "verdict"].includes(e.type) && !retracted.has(e.id)
  )

  if (hasPark && grillEvents.length === 0) return "idle"
  if (grillEvents.length === 0) return "idle"

  // Walk from the end to find the latest active state
  const active = grillEvents.filter(e => !retracted.has(e.id))
  if (active.length === 0) return "idle"

  const last = active[active.length - 1]

  if (last.type === "challenge") {
    // Unconfirmed challenge with no answer after it
    const hasAnswer = active.some(
      e => e.type === "answer" && new Date(e.ts) >= new Date(last.ts)
    )
    if (!hasAnswer) return "awaiting_answer"
  }

  if (last.type === "answer") {
    // Answer but no verdict after it
    return "verdicting"
  }

  if (last.type === "verdict") {
    const isConfirmed = last.confirmed || confirmed.has(last.id)
    if (!isConfirmed) return "awaiting_decision"

    const outcome = last.payload.outcome as string
    if (outcome === "kill") return "done"
    // Survive + confirmed → user can choose to continue or stop
    return "awaiting_decision"
  }

  return "idle"
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useGrillFlow(
  artifactId: string,
  claim: Claim,
  artifactKind: string,
): GrillFlowState & GrillFlowActions {
  const [events, setEvents] = useState<Event[]>([])
  const [phase, setPhase] = useState<GrillPhase>("idle")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const mountedRef = useRef(true)

  // Derived
  const rounds = countRounds(events)
  const unresolved = computeUnresolved(events)

  // Fetch trajectory and reconstruct phase
  const refreshEvents = useCallback(async () => {
    try {
      const { events: fetched } = await api.getTrajectory(artifactId)
      if (!mountedRef.current) return
      setEvents(fetched)
      setPhase(reconstructPhase(fetched))
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to fetch trajectory")
    }
  }, [artifactId])

  useEffect(() => {
    mountedRef.current = true
    refreshEvents()
    return () => { mountedRef.current = false }
  }, [refreshEvents])

  // --- Actions ---

  const startGrill = useCallback(async () => {
    setError(null)
    setPhase("starting")
    setLoading(true)
    try {
      await api.startGrill(artifactId, artifactKind)
      setPhase("challenging")
      const { event: challengeEvent } = await api.autoChallenge(
        artifactId,
        claim.id,
        claim.body,
      )
      if (!mountedRef.current) return
      setEvents(prev => [...prev, challengeEvent])
      setPhase("awaiting_answer")
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to start grill")
      setPhase("idle")
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [artifactId, artifactKind, claim.id, claim.body])

  const submitAnswer = useCallback(async (text: string) => {
    setError(null)
    setPhase("answering")
    setLoading(true)
    try {
      const { event: answerEvent } = await api.answer(artifactId, claim.id, text)
      if (!mountedRef.current) return
      setEvents(prev => [...prev, answerEvent])

      setPhase("verdicting")
      // Find the last challenge question for auto-verdict
      const allEvents = [...events, answerEvent]
      const lastChallenge = [...allEvents]
        .reverse()
        .find(e => e.type === "challenge")
      const question = (lastChallenge?.payload?.question as string) ?? ""

      const { event: verdictEvent } = await api.autoVerdict(
        artifactId,
        claim.id,
        claim.body,
        question,
        text,
      )
      if (!mountedRef.current) return
      setEvents(prev => [...prev, verdictEvent])
      setPhase("awaiting_decision")
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to submit answer")
      setPhase("awaiting_answer")
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [artifactId, claim.id, claim.body, events])

  const confirmVerdict = useCallback(async (eventId: string) => {
    setError(null)
    setLoading(true)
    try {
      // Confirm the verdict
      const { event: confirmEvt } = await api.confirmEvent(artifactId, eventId)
      if (!mountedRef.current) return
      setEvents(prev => [...prev, confirmEvt])

      // Also confirm the challenge that led to this verdict
      const verdictEvt = events.find(e => e.id === eventId)
      if (verdictEvt) {
        // Find the matching challenge (most recent challenge before this verdict)
        const verdictIdx = events.findIndex(e => e.id === eventId)
        for (let i = verdictIdx - 1; i >= 0; i--) {
          if (events[i].type === "challenge" && !events[i].confirmed) {
            const { event: challengeConfirm } = await api.confirmEvent(artifactId, events[i].id)
            if (!mountedRef.current) return
            setEvents(prev => [...prev, challengeConfirm])
            break
          }
        }
      }

      // Refresh events from backend to ensure clean state
      await refreshEvents()
      if (!mountedRef.current) return

      // Determine next state — show transition before final state
      const confirmed = events.find(e => e.id === eventId)
      const outcome = confirmed?.payload?.outcome as string
      if (outcome === "kill") {
        setPhase("confirmed_kill")
      } else {
        setPhase("confirmed_survive")
        // After a brief pause, transition to awaiting_decision
        setTimeout(() => {
          if (mountedRef.current) setPhase("awaiting_decision")
        }, 800)
      }
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to confirm verdict")
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [artifactId, events, refreshEvents])

  const retractVerdict = useCallback(async (eventId: string) => {
    setError(null)
    setLoading(true)
    try {
      const { event: retractEvt } = await api.retractEvent(artifactId, eventId)
      if (!mountedRef.current) return
      setEvents(prev => [...prev, retractEvt])
      setPhase("awaiting_answer")
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to retract verdict")
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [artifactId])

  const continueGrill = useCallback(async () => {
    setError(null)
    setPhase("challenging")
    setLoading(true)
    try {
      // Build context from previous rounds
      const context = events
        .filter(e => ["challenge", "answer", "verdict"].includes(e.type))
        .map(e => {
          if (e.type === "challenge") return `Q: ${e.payload.question}`
          if (e.type === "answer") return `A: ${e.payload.response}`
          if (e.type === "verdict") return `Verdict: ${e.payload.outcome} - ${e.payload.rationale}`
          return ""
        })
        .join("\n")

      const { event: challengeEvent } = await api.autoChallenge(
        artifactId,
        claim.id,
        claim.body,
        context,
      )
      if (!mountedRef.current) return
      setEvents(prev => [...prev, challengeEvent])
      setPhase("awaiting_answer")
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to continue grill")
      setPhase("awaiting_decision")
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [artifactId, claim.id, claim.body, events])

  const stopGrill = useCallback(() => {
    setPhase("done")
  }, [])

  return {
    events,
    phase,
    error,
    loading,
    unresolved,
    rounds,
    startGrill,
    submitAnswer,
    confirmVerdict,
    retractVerdict,
    continueGrill,
    stopGrill,
    refreshEvents,
  }
}
