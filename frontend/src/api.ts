import type { Artifact, Claim, CorpusGraph, DocVersion, Event, Material } from "./types"

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

// Corpus graph (语料图) — library-level node-link view.
export const getCorpusGraph = (libraryId = "default") =>
  request<CorpusGraph>("GET", `/library/${libraryId}/graph`)

// Lazily compute LLM-typed semantic edges (builds_on / depends_on /
// shares_method / shares_gap) for the corpus graph. Idempotent / compute-once.
// May return 501 when no LLM is configured — callers MUST swallow that so the
// structural (Tier 0) graph still renders.
export const buildEdges = (libraryId = "default") =>
  request<{ created: number; events: unknown[] }>(
    "POST",
    `/library/${libraryId}/build-edges`,
  )

// Grill
export const startGrill = (artifactId: string, kind: string) =>
  request<{ status: string }>("POST", `/grill/${artifactId}/start`, { kind })

export const autoChallenge = (artifactId: string, claimId: string, claimBody: string, context = "") =>
  request<{ event: Event }>("POST", `/grill/${artifactId}/auto-challenge`, { claim_id: claimId, claim_body: claimBody, context })

export const answer = (artifactId: string, claimId: string, challengeId: string, response: string) =>
  request<{ event: Event }>("POST", `/grill/${artifactId}/answer`, { claim_id: claimId, response, challenge_id: challengeId })

export const autoVerdict = (artifactId: string, claimId: string, claimBody: string, question: string, answerText: string, challengeId: string) =>
  request<{ event: Event }>("POST", `/grill/${artifactId}/auto-verdict`, { claim_id: claimId, claim_body: claimBody, question, answer: answerText, challenge_id: challengeId })

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

export const getVersions = (artifactId: string) =>
  request<{ versions: DocVersion[] }>("GET", `/artifact/${artifactId}/versions`)

// Edit
export const createEdit = (artifactId: string, content: string, scope: "surface" | "substance") =>
  request<{ event: Event }>("POST", `/artifact/${artifactId}/edit`, { content, scope })

// Batch confirm
export const batchConfirm = (artifactId: string, eventIds: string[]) =>
  request<{ events: Event[] }>("POST", `/events/${artifactId}/batch-confirm`, { event_ids: eventIds })

// Promote
export const promote = (artifactId: string, claimId: string) =>
  request<{ event: Event }>("POST", `/promote/${artifactId}/${claimId}`)

// Collect (literature search)
export const collectMaterials = (artifactId: string, libraryId: string, query: string, maxResults = 10) =>
  request<{ materials: Material[] }>("POST", `/artifact/${artifactId}/collect`, { library_id: libraryId, query, max_results: maxResults })

export const listMaterials = (artifactId: string) =>
  request<{ materials: Material[] }>("GET", `/artifact/${artifactId}/materials`)

// Grounding
export const autoGround = (artifactId: string, claimId: string, claimBody: string, materialId: string) =>
  request<{ event: Event }>("POST", `/grounding/${artifactId}/auto-ground`, { claim_id: claimId, claim_body: claimBody, material_id: materialId })

export const groundManual = (artifactId: string, claimId: string, materialId: string, supported: boolean, evidence = "", assessment = "") =>
  request<{ event: Event }>("POST", `/grounding/${artifactId}/ground`, { claim_id: claimId, material_id: materialId, supported, evidence, assessment })

export const getEvidence = (artifactId: string, claimId: string) =>
  request<{ events: Event[] }>("GET", `/artifact/${artifactId}/evidence?claim_id=${claimId}`)

// Lens feed
export const ingestLensFeed = (artifactId: string, libraryId: string) =>
  request<{ entries: unknown[] }>("POST", `/lens-feed/${artifactId}`, { library_id: libraryId })

export const queryLensFeed = (libraryId: string) =>
  request<{ entries: unknown[] }>("GET", `/lens-feed?library_id=${libraryId}`)

// Lens cross-idea contradiction scan. Surfaces pending `challenge` events with
// payload.kind === "lens_contradiction". May fail (e.g. 501) when no LLM is
// configured — callers must swallow that so a lens failure never breaks grill.
export const scanContradictions = (
  artifactId: string,
  claimId: string,
  claimBody: string,
  includeSoft = false,
) =>
  request<{ events: Event[] }>("POST", `/lens/${artifactId}/scan-contradictions`, {
    claim_id: claimId,
    claim_body: claimBody,
    include_soft: includeSoft,
  })

// Lens taste anchor (品味锚). User-initiated, on-demand. Surfaces pending
// `challenge` events with payload.kind === "taste". May return zero events
// (no grilled history / no real anchor) or fail (e.g. 501 when no LLM) — a
// taste failure must never break grill.
export const assessTaste = (
  artifactId: string,
  claimId: string,
  claimBody: string,
) =>
  request<{ events: Event[] }>("POST", `/lens/${artifactId}/assess-taste`, {
    claim_id: claimId,
    claim_body: claimBody,
  })
