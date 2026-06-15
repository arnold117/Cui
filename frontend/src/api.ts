import type { Artifact, Claim, Event } from "./types"

const BASE = "/api/v1"

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const opts: RequestInit = { method, headers: { "Content-Type": "application/json" } }
  if (body) opts.body = JSON.stringify(body)
  const resp = await fetch(`${BASE}${path}`, opts)
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `${resp.status} ${resp.statusText}`)
  }
  return resp.json()
}

// Park
export const park = (libraryId: string, body: string, kind = "idea") =>
  request<{ artifact: Artifact; claim: Claim }>("POST", "/park", { library_id: libraryId, body, kind })

export const listParked = (libraryId: string) =>
  request<{ artifact_ids: string[] }>("GET", `/park?library_id=${libraryId}`)

// Artifacts
export const getArtifact = (id: string) =>
  request<{ artifact: Artifact }>("GET", `/artifact/${id}`)

export const getClaim = (id: string) =>
  request<{ claim: Claim }>("GET", `/claim/${id}`)

export const listArtifacts = (libraryId: string) =>
  request<{ artifacts: Artifact[] }>("GET", `/artifacts?library_id=${libraryId}`)

// Grill
export const startGrill = (artifactId: string, kind: string) =>
  request<{ status: string }>("POST", `/grill/${artifactId}/start`, { kind })

export const autoChallenge = (artifactId: string, claimId: string, claimBody: string, context = "") =>
  request<{ event: Event }>("POST", `/grill/${artifactId}/auto-challenge`, { claim_id: claimId, claim_body: claimBody, context })

export const answer = (artifactId: string, claimId: string, response: string) =>
  request<{ event: Event }>("POST", `/grill/${artifactId}/answer`, { claim_id: claimId, response })

export const autoVerdict = (artifactId: string, claimId: string, claimBody: string, question: string, answerText: string) =>
  request<{ event: Event }>("POST", `/grill/${artifactId}/auto-verdict`, { claim_id: claimId, claim_body: claimBody, question, answer: answerText })

// Events
export const confirmEvent = (artifactId: string, eventId: string) =>
  request<{ event: Event }>("POST", `/events/${artifactId}/confirm`, { event_id: eventId })

export const retractEvent = (artifactId: string, eventId: string) =>
  request<{ event: Event }>("POST", `/events/${artifactId}/retract`, { event_id: eventId })

export const pendingEvents = (artifactId: string) =>
  request<{ events: Event[] }>("GET", `/events/${artifactId}/pending`)

// Projections
export const getTrajectory = (artifactId: string) =>
  request<{ events: Event[] }>("GET", `/artifact/${artifactId}/trajectory`)

export const getDoc = (artifactId: string) =>
  request<{ events: Event[] }>("GET", `/artifact/${artifactId}/doc`)

// Promote
export const promote = (artifactId: string, claimId: string) =>
  request<{ event: Event }>("POST", `/promote/${artifactId}/${claimId}`)

// Lens feed
export const ingestLensFeed = (artifactId: string, libraryId: string) =>
  request<{ entries: unknown[] }>("POST", `/lens-feed/${artifactId}`, { library_id: libraryId })

export const queryLensFeed = (libraryId: string) =>
  request<{ entries: unknown[] }>("GET", `/lens-feed?library_id=${libraryId}`)
