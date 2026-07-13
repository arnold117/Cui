import { useState, useEffect, useCallback, useRef } from "react"
import type { Event, Claim, VerdictTriage } from "../types"
import {
  isEvidenceContradictionChallenge,
  isLensChallenge,
  isTasteChallenge,
} from "../types"
import * as api from "../api"

// ---------------------------------------------------------------------------
// Challenge-centric model (spec docs/spec-lens-contradiction.md §2 前端集成)
//
// The old hook collapsed "the claim's overall grill state" and "the active
// challenge's state" into ONE global `phase`, so only a single linear
// challenge → answer → verdict thread worked. We now derive PER-CHALLENGE
// state from the event stream, so multiple challenges (the LLM grill challenge
// AND Lens-surfaced contradiction challenges) coexist, each independently
// answered / verdicted. A lens challenge is just a `challenge` event with
// payload.kind === "lens_contradiction"; it shares the SAME lifecycle and is
// distinguished only by a badge in the UI.
// ---------------------------------------------------------------------------

export type ChallengeState =
  | "awaiting_answer" // no answer for this challenge yet
  | "awaiting_verdict" // answered, but no verdict yet
  | "awaiting_decision" // verdict exists but is not yet confirmed
  | "resolved" // verdict is confirmed

export interface ChallengeView {
  event: Event // the `challenge` event
  state: ChallengeState
  answerEvent?: Event
  verdictEvent?: Event
  // "lens" = Lens-surfaced (contradiction/taste); "evidence" = 负证据反哺
  // (confirmed contradicts ground). Neither counts as a grill round.
  source: "grill" | "lens" | "evidence"
}

export type ClaimState = "idle" | "grilling" | "all_resolved"

export interface GrillFlowState {
  events: Event[]
  challenges: ChallengeView[]
  claimState: ClaimState
  error: string | null
  loading: boolean
  unresolved: string[]
  /** Count of LLM-sourced challenges only. Lens challenges are surfaced
   * tensions, not grill "rounds", so they are excluded from this counter. */
  rounds: number
  /** True once the user clicked "到此为止" on a survived claim. Drives the
   * distinct terminal "拷问完成" screen. Reset whenever a new challenge is
   * created or the user continues, so re-grilling clears the terminal screen. */
  stopped: boolean
}

export interface GrillFlowActions {
  startGrill: () => void
  /** Answer a SPECIFIC challenge by id, then auto-verdict against THAT
   * challenge's question. */
  submitAnswer: (challengeId: string, text: string) => void
  /** Confirm a pending verdict. For a KILL verdict the triage panel passes
   * the (possibly user-amended) 死因分诊; when it differs from the drafted
   * payload the draft is retracted and re-issued with the user's triage
   * before signing (events are immutable — 机器起草人改判 = retract + 新
   * verdict + confirm). */
  confirmVerdict: (verdictId: string, triage?: VerdictTriage) => Promise<void>
  retractVerdict: (verdictId: string) => void
  continueGrill: () => void
  stopGrill: () => void
  scanLens: () => void
  /** User-initiated, on-demand taste-anchor assessment (评品味). NOT auto, NOT
   * fired on grill start. Surfaces a taste `challenge` into the board. */
  assessTaste: () => void
  refreshEvents: () => void
}

// ---------------------------------------------------------------------------
// Pure derivation helpers (the testable core).
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

function isConfirmed(
  event: Event,
  confirmedIds: Set<string>,
): boolean {
  return event.confirmed || confirmedIds.has(event.id)
}

/**
 * Derive the per-challenge lifecycle view for a claim from the event stream.
 *
 * Pairing rule — ID FIRST, ts-window fallback:
 *
 *   1. An `answer`/`verdict` belongs to challenge C iff
 *      `event.payload.challenge_id === C.event.id`. This is the only correct
 *      rule once challenges run in parallel: at grill start the LLM challenge
 *      is created, then the Lens auto-scan opens contradiction challenges, so
 *      several challenges exist BEFORE any answer. A ts-window cannot tell
 *      which open challenge a later answer belongs to — the explicit
 *      `challenge_id` (written by the backend when the frontend threads it
 *      through) does.
 *
 *   2. Only when an answer/verdict carries NO `challenge_id` (legacy /
 *      single-thread data recorded before this link existed) do we fall back
 *      to the original ts-window heuristic: the event belongs to the last
 *      challenge whose ts <= the event's ts (i.e. its open window
 *      [C.ts, nextChallenge.ts)). This keeps old linear trajectories deriving
 *      correctly.
 *
 * If two answers/verdicts somehow resolve to the same challenge, the first by
 * ts wins (the challenge is answered once; later duplicates are ignored).
 */
export function deriveChallenges(events: Event[], claimId: string): ChallengeView[] {
  const retracted = getRetractedIds(events)
  const confirmed = getConfirmedIds(events)

  // Events relevant to THIS claim thread, in ts order. We key off target_ref
  // for challenge/answer/verdict (all carry the claim id as target_ref in the
  // backend); challenges without target_ref still count via type fallback.
  const targetsClaim = (e: Event) =>
    e.target_ref === claimId || e.target_ref == null

  const sorted = [...events].sort(
    (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime(),
  )

  // Ordered, non-retracted challenges for this claim.
  const challengeEvents = sorted.filter(
    e => e.type === "challenge" && !retracted.has(e.id) && targetsClaim(e),
  )

  const challengeIds = new Set(challengeEvents.map(c => c.id))

  // For an event lacking challenge_id, find the challenge whose ts-window it
  // falls into: the last challenge with ts <= event ts (legacy heuristic).
  const challengeIdByTsWindow = (e: Event): string | undefined => {
    const t = new Date(e.ts).getTime()
    let match: string | undefined
    for (const c of challengeEvents) {
      if (new Date(c.ts).getTime() <= t) match = c.id
      else break // challengeEvents is ts-sorted
    }
    return match
  }

  // Resolve which challenge an answer/verdict belongs to: id first, ts-window
  // fallback only when no (recognized) challenge_id is present.
  const ownerOf = (e: Event): string | undefined => {
    const linked = e.payload?.challenge_id as string | undefined
    if (linked && challengeIds.has(linked)) return linked
    if (linked) return undefined // links to a retracted/foreign challenge → drop
    return challengeIdByTsWindow(e)
  }

  const views: ChallengeView[] = challengeEvents.map((challenge) => {
    const isOwned = (e: Event) =>
      targetsClaim(e) && !retracted.has(e.id) && ownerOf(e) === challenge.id

    const answerEvent = sorted.find(e => e.type === "answer" && isOwned(e))
    const verdictEvent = sorted.find(e => e.type === "verdict" && isOwned(e))

    let state: ChallengeState
    if (!answerEvent) {
      state = "awaiting_answer"
    } else if (!verdictEvent) {
      state = "awaiting_verdict"
    } else if (isConfirmed(verdictEvent, confirmed)) {
      state = "resolved"
    } else {
      state = "awaiting_decision"
    }

    return {
      event: challenge,
      state,
      answerEvent,
      verdictEvent,
      // Lens-surfaced challenges — cross-idea contradictions AND taste-anchor
      // verdicts — are surfaced tensions, not grill rounds; both map to "lens"
      // so countRounds excludes them. Evidence-contradiction challenges
      // (负证据反哺) are surfaced counter-evidence — likewise not rounds.
      source: isEvidenceContradictionChallenge(challenge)
        ? "evidence"
        : isLensChallenge(challenge) || isTasteChallenge(challenge)
          ? "lens"
          : "grill",
    }
  })

  return views
}

/**
 * Roll the per-challenge states up into the claim's overall state.
 *   - "idle"          — no challenges at all.
 *   - "grilling"      — at least one challenge is not yet resolved.
 *   - "all_resolved"  — at least one challenge AND every challenge resolved.
 *
 * A confirmed KILL counts as resolved (its challenge's verdict is confirmed),
 * so a killed claim with no other open challenges rolls up to "all_resolved".
 * The UI then reads the last confirmed verdict's outcome to decide whether to
 * show promote (survive) vs kill messaging — mirroring the old `done` /
 * `confirmed_kill` split, now driven by the rollup instead of a global phase.
 */
export function deriveClaimState(challenges: ChallengeView[]): ClaimState {
  if (challenges.length === 0) return "idle"
  const allResolved = challenges.every(c => c.state === "resolved")
  return allResolved ? "all_resolved" : "grilling"
}

function countRounds(challenges: ChallengeView[]): number {
  // Only LLM-sourced challenges count as grill rounds (lens ones are surfaced
  // tensions, not rounds). See `rounds` doc above.
  return challenges.filter(c => c.source === "grill").length
}

function computeUnresolved(challenges: ChallengeView[]): string[] {
  return challenges
    .filter(c => c.state !== "resolved")
    .map(c => (c.event.payload.question as string) ?? "")
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
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [stopped, setStopped] = useState(false)
  const mountedRef = useRef(true)
  // Guards the auto-scan-once-per-grill-start behavior: set true the moment a
  // grill is started so we never re-scan on continue or on re-render.
  const lensScannedRef = useRef(false)

  // Derived, event-sourced state.
  const challenges = deriveChallenges(events, claim.id)
  const claimState = deriveClaimState(challenges)
  const rounds = countRounds(challenges)
  const unresolved = computeUnresolved(challenges)

  // Fetch trajectory; state derives from `events` purely.
  const refreshEvents = useCallback(async () => {
    try {
      const { events: fetched } = await api.getTrajectory(artifactId)
      if (!mountedRef.current) return
      setEvents(fetched)
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to fetch trajectory")
    }
  }, [artifactId])

  useEffect(() => {
    mountedRef.current = true
    refreshEvents()
    return () => {
      mountedRef.current = false
    }
  }, [refreshEvents])

  // --- Lens scan (fire-and-forget; failures must NOT break grill) ---

  const scanLens = useCallback(async () => {
    try {
      await api.scanContradictions(artifactId, claim.id, claim.body)
      if (!mountedRef.current) return
      await refreshEvents()
    } catch {
      // Swallow: a lens failure (e.g. 501 when no LLM) must never break grill.
    }
  }, [artifactId, claim.id, claim.body, refreshEvents])

  // --- Taste anchor (评品味): user-initiated, on-demand. Unlike scanLens it is
  // NOT fired on grill start. It shows a loading state (it's a deliberate
  // action the user waits on), but surfaces/swallows errors like scanLens so a
  // taste failure (e.g. 501 no LLM, or simply zero anchors) never breaks grill.
  const assessTaste = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      await api.assessTaste(artifactId, claim.id, claim.body)
      if (!mountedRef.current) return
      await refreshEvents()
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to assess taste")
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [artifactId, claim.id, claim.body, refreshEvents])

  // --- Actions ---

  const startGrill = useCallback(async () => {
    setError(null)
    setLoading(true)
    setStopped(false)
    try {
      await api.startGrill(artifactId, artifactKind)
      const { event: challengeEvent } = await api.autoChallenge(
        artifactId,
        claim.id,
        claim.body,
      )
      if (!mountedRef.current) return
      setEvents(prev => [...prev, challengeEvent])
      // Auto-scan the Lens once, AFTER the first challenge exists, guarded so
      // it only runs once per grill start (not on continue, not per render).
      if (!lensScannedRef.current) {
        lensScannedRef.current = true
        void scanLens()
      }
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to start grill")
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [artifactId, artifactKind, claim.id, claim.body, scanLens])

  const submitAnswer = useCallback(
    async (challengeId: string, text: string) => {
      setError(null)
      setLoading(true)
      try {
        const { event: answerEvent } = await api.answer(
          artifactId,
          claim.id,
          challengeId,
          text,
        )
        if (!mountedRef.current) return
        setEvents(prev => [...prev, answerEvent])

        // Verdict against the SPECIFIC challenge being answered (not "the last
        // challenge"). Pull its question straight off the targeted event, and
        // thread challengeId so the verdict event is paired back to it by id.
        const challengeEvt = events.find(e => e.id === challengeId)
        const question = (challengeEvt?.payload?.question as string) ?? ""

        const { event: verdictEvent } = await api.autoVerdict(
          artifactId,
          claim.id,
          claim.body,
          question,
          text,
          challengeId,
        )
        if (!mountedRef.current) return
        setEvents(prev => [...prev, verdictEvent])
      } catch (e) {
        if (!mountedRef.current) return
        setError(e instanceof Error ? e.message : "Failed to submit answer")
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    },
    [artifactId, claim.id, claim.body, events],
  )

  const confirmVerdict = useCallback(
    async (verdictId: string, triage?: VerdictTriage) => {
      setError(null)
      setLoading(true)
      try {
        let verdictEvt = events.find(e => e.id === verdictId)
        let confirmTargetId = verdictId

        // 死因分诊: when the user's triage differs from the drafted payload,
        // re-issue. Events are immutable, so "editing" the AI draft = retract
        // it, post a manual verdict carrying the same outcome/rationale plus
        // the user's triage, then confirm THAT (机器起草人签名，人改判重录).
        if (verdictEvt && triage) {
          const p = verdictEvt.payload
          const changed =
            (p.death_cause ?? undefined) !== triage.death_cause ||
            ((p.revival_condition as string | undefined) || undefined) !==
              (triage.revival_condition || undefined) ||
            ((p.successor_claim_id as string | undefined) || undefined) !==
              (triage.successor_claim_id || undefined)
          if (changed) {
            const { event: retractEvt } = await api.retractEvent(
              artifactId,
              verdictId,
            )
            if (!mountedRef.current) return
            setEvents(prev => [...prev, retractEvt])

            const { event: reissued } = await api.postVerdict(
              artifactId,
              claim.id,
              (p.outcome as string) ?? "kill",
              (p.rationale as string) ?? "",
              p.challenge_id as string | undefined,
              triage,
            )
            if (!mountedRef.current) return
            setEvents(prev => [...prev, reissued])
            verdictEvt = reissued
            confirmTargetId = reissued.id
          }
        }

        const { event: confirmEvt } = await api.confirmEvent(
          artifactId,
          confirmTargetId,
        )
        if (!mountedRef.current) return
        setEvents(prev => [...prev, confirmEvt])

        // Also confirm the challenge that owns this verdict so the challenge
        // bubble leaves the pending gate too. Prefer the explicit link
        // (verdict.payload.challenge_id) — correct under parallel challenges —
        // and fall back to the legacy "most recent unconfirmed challenge before
        // this verdict in ts order" scan only when no link is present.
        const linkedChallengeId = verdictEvt?.payload?.challenge_id as
          | string
          | undefined

        let challengeToConfirm: Event | undefined
        if (linkedChallengeId) {
          challengeToConfirm = events.find(
            e =>
              e.id === linkedChallengeId &&
              e.type === "challenge" &&
              !e.confirmed,
          )
        } else {
          const verdictIdx = events.findIndex(e => e.id === verdictId)
          if (verdictIdx >= 0) {
            for (let i = verdictIdx - 1; i >= 0; i--) {
              if (events[i].type === "challenge" && !events[i].confirmed) {
                challengeToConfirm = events[i]
                break
              }
            }
          }
        }

        if (challengeToConfirm) {
          const { event: challengeConfirm } = await api.confirmEvent(
            artifactId,
            challengeToConfirm.id,
          )
          if (!mountedRef.current) return
          setEvents(prev => [...prev, challengeConfirm])
        }

        await refreshEvents()
      } catch (e) {
        if (!mountedRef.current) return
        setError(e instanceof Error ? e.message : "Failed to confirm verdict")
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    },
    [artifactId, claim.id, events, refreshEvents],
  )

  const retractVerdict = useCallback(
    async (verdictId: string) => {
      setError(null)
      setLoading(true)
      try {
        const { event: retractEvt } = await api.retractEvent(artifactId, verdictId)
        if (!mountedRef.current) return
        setEvents(prev => [...prev, retractEvt])
        await refreshEvents()
      } catch (e) {
        if (!mountedRef.current) return
        setError(e instanceof Error ? e.message : "Failed to retract verdict")
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    },
    [artifactId, refreshEvents],
  )

  const continueGrill = useCallback(async () => {
    setError(null)
    setLoading(true)
    setStopped(false)
    try {
      // Build context from previous rounds.
      const context = events
        .filter(e => ["challenge", "answer", "verdict"].includes(e.type))
        .map(e => {
          if (e.type === "challenge") return `Q: ${e.payload.question}`
          if (e.type === "answer") return `A: ${e.payload.response}`
          if (e.type === "verdict")
            return `Verdict: ${e.payload.outcome} - ${e.payload.rationale}`
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
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : "Failed to continue grill")
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [artifactId, claim.id, claim.body, events])

  // stopGrill does not mutate the event stream: when claimState is already
  // "all_resolved", the user choosing "到此为止" flips into the terminal
  // "拷问完成" screen. We refresh to settle the final state / sidebar.
  const stopGrill = useCallback(() => {
    setStopped(true)
    void refreshEvents()
  }, [refreshEvents])

  return {
    events,
    challenges,
    claimState,
    error,
    loading,
    unresolved,
    rounds,
    stopped,
    startGrill,
    submitAnswer,
    confirmVerdict,
    retractVerdict,
    continueGrill,
    stopGrill,
    scanLens,
    assessTaste,
    refreshEvents,
  }
}
