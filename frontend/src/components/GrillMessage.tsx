import { useEffect, useState } from "react"
import type { Claim, DeathCause, Event, VerdictTriage } from "../types"
import { DEATH_CAUSES, precedentRefs } from "../types"
import {
  DEATH_CAUSE_BADGE_CLASSES,
  DEATH_CAUSE_HINTS,
  DEATH_CAUSE_LABELS,
  deriveClaimStatus,
  formatTime,
  rulingVerdict,
} from "../utils"
import { getClaim, getTrajectory, listArtifacts } from "../api"

interface Props {
  event: Event
  /** For a pending KILL verdict the triage panel passes the (possibly
   * amended) 死因分诊 along with the confirm. */
  onConfirm?: (eventId: string, triage?: VerdictTriage) => void
  onRetract?: (eventId: string) => void
  isPending: boolean
  isLoading?: boolean
  /** Needed only by the verdict triage panel (boundary successor picker). */
  libraryId?: string
  /** The claim being grilled — excluded from successor candidates. */
  currentClaimId?: string
  /** Navigate to another artifact (a cited 判例's parking artifact). Optional —
   * without it the 判例 rows render unlinked, body text only. */
  onOpenArtifact?: (artifactId: string) => void
}

// 📎 evidence provenance chip, shared by every bubble that carries one.
function EvidenceBadge({ count }: { count: unknown }) {
  if (typeof count !== "number" || count <= 0) return null
  return (
    <span className="text-[10px] text-zinc-400 bg-zinc-800/80 border border-zinc-700/50 px-1.5 py-0.5 rounded-full">
      📎 基于 {count} 篇证据
    </span>
  )
}

function DeathCauseBadge({ cause }: { cause: string }) {
  return (
    <span
      className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${
        DEATH_CAUSE_BADGE_CLASSES[cause] ??
        "bg-zinc-600/50 text-zinc-200 border-zinc-500/40"
      }`}
    >
      {DEATH_CAUSE_LABELS[cause] ?? cause}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Boundary successor picker — OPTIONAL link to the narrowed claim that lives
// on. Candidates = the library's other claims, fetched lazily the way the
// sidebar does (artifact list → park event → claim). 「收窄后活下来的那条」
// can be neither already killed nor the claim being grilled itself — both are
// excluded from the candidate list.
// ---------------------------------------------------------------------------
function SuccessorSelect({
  libraryId,
  currentClaimId,
  value,
  onChange,
}: {
  libraryId: string
  currentClaimId?: string
  value: string
  onChange: (claimId: string) => void
}) {
  const [candidates, setCandidates] = useState<{ id: string; body: string }[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listArtifacts(libraryId)
      .then(async ({ artifacts }) => {
        const found: { id: string; body: string }[] = []
        for (const artifact of artifacts) {
          try {
            const { events } = await getTrajectory(artifact.id)
            const parkEvent = events.find(e => e.type === "park")
            const claimId = parkEvent?.target_ref
            if (!claimId || claimId === currentClaimId) continue
            // A dead claim cannot be the narrowed survivor.
            if (deriveClaimStatus(events) === "killed") continue
            const { claim } = await getClaim(claimId)
            found.push({ id: claim.id, body: claim.body })
          } catch {
            // Skip unresolvable artifacts — the picker stays optional.
          }
        }
        if (!cancelled) {
          setCandidates(found)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [libraryId, currentClaimId])

  return (
    <div className="space-y-1">
      <p className="text-[11px] text-zinc-400">后继 claim（可选 — 收窄后活下来的那条）</p>
      <select
        className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500"
        value={value}
        onChange={e => onChange(e.target.value)}
      >
        <option value="">
          {loading ? "加载中..." : "— 不关联 —"}
        </option>
        {candidates.map(c => (
          <option key={c.id} value={c.id}>
            {c.body.length > 60 ? c.body.slice(0, 59) + "…" : c.body}
          </option>
        ))}
      </select>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Verdict bubble. A pending KILL verdict hosts the 死因分诊 panel: the four
// causes (required), a revival-condition input for circumstantial (required),
// and an optional successor picker for boundary. auto_verdict's proposal
// prefills the panel and the user can amend it before confirming.
// ---------------------------------------------------------------------------
function VerdictMessage({
  event,
  onConfirm,
  onRetract,
  isPending,
  isLoading,
  libraryId,
  currentClaimId,
}: Props) {
  const outcome = event.payload.outcome as string
  const rationale = (event.payload.rationale as string) ?? ""
  const confidence = event.payload.confidence as number | undefined
  const isKill = outcome === "kill"

  const proposedCause = event.payload.death_cause as DeathCause | undefined
  const proposedRevival = (event.payload.revival_condition as string) ?? ""
  const proposedSuccessor = (event.payload.successor_claim_id as string) ?? ""

  // Triage panel state, prefilled from the auto_verdict proposal.
  const [cause, setCause] = useState<DeathCause | "">(proposedCause ?? "")
  const [revival, setRevival] = useState(proposedRevival)
  const [successor, setSuccessor] = useState(proposedSuccessor)

  // A KILL cannot be signed without a cause; circumstantial not without a
  // revival condition (结构强制，不靠自觉 — mirrors the backend gate).
  const triageIncomplete =
    isKill && (!cause || (cause === "circumstantial" && !revival.trim()))

  const handleConfirm = () => {
    if (!onConfirm) return
    if (!isKill) {
      onConfirm(event.id)
      return
    }
    if (!cause) return
    onConfirm(event.id, {
      death_cause: cause,
      revival_condition:
        cause === "circumstantial" ? revival.trim() : undefined,
      successor_claim_id:
        cause === "boundary" && successor ? successor : undefined,
    })
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[75%] space-y-2">
        <div
          className={`rounded-xl rounded-tl-sm px-4 py-3 border ${
            isKill
              ? "bg-red-950/40 border-red-700/50"
              : "bg-emerald-950/40 border-emerald-700/50"
          }`}
        >
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                isKill
                  ? "bg-red-700/60 text-red-200"
                  : "bg-emerald-700/60 text-emerald-200"
              }`}
            >
              {isKill ? "KILL" : "SURVIVE"}
            </span>
            {isKill && !isPending && proposedCause && (
              <DeathCauseBadge cause={proposedCause} />
            )}
            {confidence != null && (
              <span className="text-[10px] text-zinc-500">
                confidence: {Math.round(confidence * 100)}%
              </span>
            )}
            <EvidenceBadge count={event.payload.evidence_count} />
          </div>
          <p className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">{rationale}</p>
          {!isPending && proposedCause === "circumstantial" && proposedRevival && (
            <p className="text-xs text-zinc-400 leading-relaxed mt-1.5">
              复活条件: {proposedRevival}
            </p>
          )}
        </div>

        {/* 死因分诊 panel — only while the KILL draft awaits the user's signature. */}
        {isPending && !isLoading && isKill && (
          <div className="pl-1 space-y-2 bg-zinc-900/60 border border-zinc-700/40 rounded-lg px-3 py-3">
            <p className="text-[11px] font-medium text-zinc-300">
              死因分诊（必选）— AI 提议可改
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {DEATH_CAUSES.map(dc => (
                <button
                  key={dc}
                  type="button"
                  className={`text-left px-2 py-1.5 rounded-md border text-[11px] transition-colors ${
                    cause === dc
                      ? DEATH_CAUSE_BADGE_CLASSES[dc]
                      : "bg-zinc-800/60 text-zinc-400 border-zinc-700/40 hover:bg-zinc-800 hover:text-zinc-200"
                  }`}
                  onClick={() => setCause(dc)}
                >
                  <span className="font-medium">{DEATH_CAUSE_LABELS[dc]}</span>
                  <span className="block text-[10px] opacity-80">
                    {DEATH_CAUSE_HINTS[dc]}
                  </span>
                </button>
              ))}
            </div>
            {cause === "circumstantial" && (
              <div className="space-y-1">
                <p className="text-[11px] text-zinc-400">
                  复活条件（必填）— 想不出复活条件，说明其实是品味死
                </p>
                <textarea
                  className="w-full h-14 bg-zinc-800 border border-zinc-700 rounded-md p-2 text-xs text-zinc-100 placeholder-zinc-500 resize-none focus:outline-none focus:border-zinc-500"
                  placeholder="写可判定的条件，如「Tier 1 证明不够 + 接受 embedding」"
                  value={revival}
                  onChange={e => setRevival(e.target.value)}
                />
              </div>
            )}
            {cause === "boundary" && libraryId && (
              <SuccessorSelect
                libraryId={libraryId}
                currentClaimId={currentClaimId}
                value={successor}
                onChange={setSuccessor}
              />
            )}
          </div>
        )}

        {isPending && !isLoading && (
          <div className="flex gap-2 pl-1">
            <button
              className="text-xs px-3 py-1 rounded-md bg-emerald-700/60 text-emerald-200 hover:bg-emerald-700/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              onClick={handleConfirm}
              disabled={triageIncomplete}
              title={triageIncomplete ? "kill 必须选死因（偶然死必填复活条件）" : undefined}
            >
              确认
            </button>
            <button
              className="text-xs px-3 py-1 rounded-md bg-red-700/60 text-red-200 hover:bg-red-700/80 transition-colors"
              onClick={() => onRetract?.(event.id)}
            >
              撤回
            </button>
          </div>
        )}
        <p className="text-[10px] text-zinc-600 pl-1">{formatTime(event.ts)}</p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 判例先验 (precedent prior, spec-precedent-prior §2 Q5). The main-line
// auto_challenge aims its question with the researcher's OWN kill precedents,
// and reports back which ones it used as `precedent_refs` (hallucinated ids
// already dropped backend-side). This trace is what keeps 本刀 auditable
// instead of a black-box 改良 — and it is 取证, not 定见:
//
//   文案红线 (前科定罪): the copy may say where the ANGLE of the question came
//   from. It may NOT suggest the current claim resembles a past kill, nor that
//   anything is being repeated — that would be the UI passing the verdict the
//   system is forbidden to pass.
//
// Resolution is USER-ACTION-DRIVEN (click to expand → fetch once). No effect
// watches derived state; this app has already paid for that pattern once.
// ---------------------------------------------------------------------------
interface PrecedentEntry {
  claimId: string
  /** null when the claim can no longer be resolved — the row stays, honestly. */
  body: string | null
  /** Where the claim was parked — the click-through target (backend reads
   *  precedents off this same artifact: claim.artifact_ids[0]). */
  artifactId?: string
  /** Only when the ruling verdict was actually read AND carries a cause.
   *  Legacy kills show no badge (投影语义: 未分类, never invented — mirrors
   *  EventCard). */
  deathCause?: string
}

async function resolvePrecedent(claimId: string): Promise<PrecedentEntry> {
  let claim: Claim
  try {
    claim = (await getClaim(claimId)).claim
  } catch {
    return { claimId, body: null }
  }
  const entry: PrecedentEntry = {
    claimId,
    body: claim.body,
    artifactId: claim.artifact_ids[0],
  }
  if (!entry.artifactId) return entry
  try {
    const { events } = await getTrajectory(entry.artifactId)
    const ruling = rulingVerdict(events, claimId)
    if (ruling && ruling.payload.outcome === "kill") {
      entry.deathCause = ruling.payload.death_cause as string | undefined
    }
  } catch {
    // 死因读不到就不显示 — the body alone still traces back.
  }
  return entry
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
      <span className={`block text-[11px] leading-relaxed ${body === null ? "text-zinc-500 italic" : "text-zinc-300"}`}>
        {preview}
      </span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Challenge bubble. Its own component because the 判例 trace holds state, and
// hooks cannot live behind GrillMessage's early returns (same reason as
// VerdictMessage).
// ---------------------------------------------------------------------------
function ChallengeMessage({
  event,
  onConfirm,
  onRetract,
  isPending,
  isLoading,
  onOpenArtifact,
}: Props) {
  const question = (event.payload.question as string) ?? ""
  const isLens = event.payload.kind === "lens_contradiction"
  const pastOutcome = event.payload.past_outcome as string | undefined
  const tension = (event.payload.tension as string) ?? ""
  const provenanceNote =
    pastOutcome === "survived"
      ? "你已确立过相反结论"
      : pastOutcome === "killed"
        ? "你已否决过这个想法"
        : ""

  // Legacy events have no `precedent_refs` key; new ones carry `[]` when the
  // Library held no kills. Both read as [] ⇒ no badge (never a「基于 0 条判例」
  // empty shell).
  const refs = precedentRefs(event)
  const [tracing, setTracing] = useState(false)
  const [entries, setEntries] = useState<PrecedentEntry[] | null>(null)
  const [resolving, setResolving] = useState(false)

  const handleTrace = () => {
    const next = !tracing
    setTracing(next)
    if (!next || entries !== null || resolving) return
    setResolving(true)
    Promise.all(refs.map(resolvePrecedent))
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setResolving(false))
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[75%] space-y-2">
        <div
          className={`rounded-xl rounded-tl-sm px-4 py-3 border ${
            isLens
              ? "bg-violet-950/50 border-violet-700/40"
              : "bg-blue-950/60 border-blue-800/40"
          }`}
        >
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            {isLens ? (
              <span className="text-[10px] font-semibold text-violet-200 bg-violet-700/50 border border-violet-600/40 px-1.5 py-0.5 rounded-full">
                ⟲ 来自你的轨迹
              </span>
            ) : (
              <p className="text-xs text-blue-400 font-medium">Challenge</p>
            )}
            <EvidenceBadge count={event.payload.evidence_count} />
            {refs.length > 0 && (
              <button
                type="button"
                onClick={handleTrace}
                aria-expanded={tracing}
                className="text-[10px] font-semibold text-violet-200 bg-violet-700/50 border border-violet-600/40 px-1.5 py-0.5 rounded-full hover:bg-violet-700/70 transition-colors"
              >
                ⟲ 提问角度来自 {refs.length} 条判例 {tracing ? "▾" : "▸"}
              </button>
            )}
          </div>
          {isLens && provenanceNote && (
            <p className="text-[11px] text-violet-300/90 mb-1">{provenanceNote}</p>
          )}
          {isLens && tension && (
            <p className="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap mb-1.5">
              {tension}
            </p>
          )}
          <p className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">{question}</p>

          {/* 判例溯源 — 取证形状: what the question was aimed WITH, never a
              judgement on the claim being grilled. */}
          {tracing && refs.length > 0 && (
            <div className="mt-2.5 rounded-lg border border-violet-800/40 bg-violet-950/30 px-2.5 py-2 space-y-1.5">
              <p className="text-[11px] text-violet-200/90 leading-relaxed">
                这一问的提问角度参考了你自己 kill 过的这几条 claim
              </p>
              <p className="text-[10px] text-zinc-500 leading-relaxed">
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
          )}
        </div>
        {isPending && !isLoading && (
          <div className="flex gap-2 pl-1">
            <button
              className="text-xs px-3 py-1 rounded-md bg-emerald-700/60 text-emerald-200 hover:bg-emerald-700/80 transition-colors"
              onClick={() => onConfirm?.(event.id)}
            >
              确认
            </button>
            <button
              className="text-xs px-3 py-1 rounded-md bg-red-700/60 text-red-200 hover:bg-red-700/80 transition-colors"
              onClick={() => onRetract?.(event.id)}
            >
              撤回
            </button>
          </div>
        )}
        <p className="text-[10px] text-zinc-600 pl-1">{formatTime(event.ts)}</p>
      </div>
    </div>
  )
}

export default function GrillMessage({ event, onConfirm, onRetract, isPending, isLoading, libraryId, currentClaimId, onOpenArtifact }: Props) {
  // confirm/retract: small muted inline note
  if (event.type === "confirm" || event.type === "retract") {
    return (
      <div className="flex justify-center py-1">
        <span className="text-xs text-zinc-500 italic">
          {event.type === "confirm" ? "已确认" : "已撤回"}
        </span>
      </div>
    )
  }

  // taste challenge (品味锚): a distinct presentation from lens_contradiction
  // and from a plain grill challenge. Same lifecycle (still a challenge) so the
  // confirm/retract + inline-answer affordances flow through unchanged.
  if (event.type === "challenge" && event.payload.kind === "taste") {
    const question = (event.payload.question as string) ?? ""
    const reasoning = (event.payload.reasoning as string) ?? ""
    const tier = event.payload.tier as string | undefined
    const papers = Array.isArray(event.payload.anchored_papers)
      ? event.payload.anchored_papers
      : []
    const pastClaims = Array.isArray(event.payload.anchored_claims)
      ? event.payload.anchored_claims
      : []

    // tier chip: replication/incremental muted, novel_but_tasteless/tasteful
    // brighter. NO numeric score (taste 红线: 相对定位 only).
    const tierLabel: Record<string, string> = {
      replication: "复制",
      incremental: "增量",
      novel_but_tasteless: "新但无味",
      tasteful: "有品味",
    }
    const tierClass: Record<string, string> = {
      replication: "bg-zinc-700/50 text-zinc-300 border-zinc-600/40",
      incremental: "bg-zinc-700/50 text-zinc-300 border-zinc-600/40",
      novel_but_tasteless: "bg-amber-700/40 text-amber-200 border-amber-600/40",
      tasteful: "bg-violet-700/50 text-violet-100 border-violet-500/50",
    }

    return (
      <div className="flex justify-start">
        <div className="max-w-[75%] space-y-2">
          <div className="rounded-xl rounded-tl-sm px-4 py-3 border bg-violet-950/40 border-violet-700/40">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-[10px] font-semibold text-violet-200 bg-violet-700/50 border border-violet-600/40 px-1.5 py-0.5 rounded-full">
                ◆ 品味锚
              </span>
              {tier && (
                <span
                  className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${
                    tierClass[tier] ?? "bg-zinc-700/50 text-zinc-300 border-zinc-600/40"
                  }`}
                >
                  {tierLabel[tier] ?? tier}
                </span>
              )}
              <EvidenceBadge count={event.payload.evidence_count} />
            </div>
            {reasoning && (
              <p className="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap mb-1.5">
                {reasoning}
              </p>
            )}
            <p className="text-[10px] text-violet-300/80 mb-1.5">
              锚: {papers.length} 篇文献 · {pastClaims.length} 条你的历史
            </p>
            <p className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">{question}</p>
          </div>
          {isPending && !isLoading && (
            <div className="flex gap-2 pl-1">
              <button
                className="text-xs px-3 py-1 rounded-md bg-emerald-700/60 text-emerald-200 hover:bg-emerald-700/80 transition-colors"
                onClick={() => onConfirm?.(event.id)}
              >
                确认
              </button>
              <button
                className="text-xs px-3 py-1 rounded-md bg-red-700/60 text-red-200 hover:bg-red-700/80 transition-colors"
                onClick={() => onRetract?.(event.id)}
              >
                撤回
              </button>
            </div>
          )}
          <p className="text-[10px] text-zinc-600 pl-1">{formatTime(event.ts)}</p>
        </div>
      </div>
    )
  }

  // evidence_contradiction (负证据反哺): counter-evidence the user CONFIRMED
  // now challenges the claim. Adversarial red presentation — this is the
  // literature striking the claim, not a neutral question. Same challenge
  // lifecycle otherwise (answer → verdict → confirm flows through unchanged).
  if (event.type === "challenge" && event.payload.kind === "evidence_contradiction") {
    const question = (event.payload.question as string) ?? ""
    const title = (event.payload.title as string) ?? ""
    const source = (event.payload.source as string) ?? ""
    const evidence = (event.payload.evidence as string) ?? ""
    const assessment = (event.payload.assessment as string) ?? ""

    return (
      <div className="flex justify-start">
        <div className="max-w-[75%] space-y-2">
          <div className="rounded-xl rounded-tl-sm px-4 py-3 border bg-red-950/40 border-red-700/50">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-[10px] font-semibold text-red-200 bg-red-800/60 border border-red-700/50 px-1.5 py-0.5 rounded-full">
                ⚡ 文献反证
              </span>
              {(title || source) && (
                <span className="text-[10px] text-red-300/80">
                  {[source, title].filter(Boolean).join(" · ")}
                </span>
              )}
            </div>
            {evidence && (
              <p className="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap mb-1.5">
                <span className="text-red-400/80">证据：</span>
                {evidence}
              </p>
            )}
            {assessment && (
              <p className="text-xs text-zinc-500 leading-relaxed whitespace-pre-wrap mb-1.5">
                {assessment}
              </p>
            )}
            <p className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">{question}</p>
          </div>
          {isPending && !isLoading && (
            <div className="flex gap-2 pl-1">
              <button
                className="text-xs px-3 py-1 rounded-md bg-emerald-700/60 text-emerald-200 hover:bg-emerald-700/80 transition-colors"
                onClick={() => onConfirm?.(event.id)}
              >
                确认
              </button>
              <button
                className="text-xs px-3 py-1 rounded-md bg-red-700/60 text-red-200 hover:bg-red-700/80 transition-colors"
                onClick={() => onRetract?.(event.id)}
              >
                撤回
              </button>
            </div>
          )}
          <p className="text-[10px] text-zinc-600 pl-1">{formatTime(event.ts)}</p>
        </div>
      </div>
    )
  }

  // challenge: left-aligned system bubble (own component — it holds the 判例
  // trace state, and hooks can't live behind this function's early returns).
  if (event.type === "challenge") {
    return (
      <ChallengeMessage
        event={event}
        onConfirm={onConfirm}
        onRetract={onRetract}
        isPending={isPending}
        isLoading={isLoading}
        onOpenArtifact={onOpenArtifact}
      />
    )
  }

  // answer: right-aligned user bubble
  if (event.type === "answer") {
    const response = (event.payload.response as string) ?? ""
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] space-y-1">
          <div className="bg-zinc-700/60 border border-zinc-600/40 rounded-xl rounded-tr-sm px-4 py-3">
            <p className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">{response}</p>
          </div>
          <p className="text-[10px] text-zinc-600 text-right pr-1">{formatTime(event.ts)}</p>
        </div>
      </div>
    )
  }

  // verdict: left-aligned system bubble with outcome + 死因分诊 (own
  // component — it holds triage-panel state, and hooks can't live behind
  // this function's early returns).
  if (event.type === "verdict") {
    return (
      <VerdictMessage
        key={event.id} // remount per verdict so the panel re-prefills from the draft
        event={event}
        onConfirm={onConfirm}
        onRetract={onRetract}
        isPending={isPending}
        isLoading={isLoading}
        libraryId={libraryId}
        currentClaimId={currentClaimId}
      />
    )
  }

  // Generic fallback for other event types
  return (
    <div className="flex justify-center py-1">
      <div className="bg-zinc-800/60 border border-zinc-700/40 rounded-lg px-3 py-2 max-w-[60%]">
        <p className="text-xs text-zinc-500">
          <span className="font-medium">{event.type}</span>
          <span className="mx-1.5 text-zinc-600">&middot;</span>
          <span>{formatTime(event.ts)}</span>
        </p>
      </div>
    </div>
  )
}
