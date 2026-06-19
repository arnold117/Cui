import type { Event } from "../types"

interface Props {
  event: Event
  onConfirm?: (eventId: string) => void
  onRetract?: (eventId: string) => void
  isPending: boolean
  isLoading?: boolean
}

function formatTime(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

export default function GrillMessage({ event, onConfirm, onRetract, isPending, isLoading }: Props) {
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

  const evidenceCount =
    typeof event.payload.evidence_count === "number" ? event.payload.evidence_count : 0
  const evidenceBadge = evidenceCount > 0 && (
    <span className="text-[10px] text-zinc-400 bg-zinc-800/80 border border-zinc-700/50 px-1.5 py-0.5 rounded-full">
      📎 基于 {evidenceCount} 篇证据
    </span>
  )

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
              {evidenceBadge}
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

  // challenge: left-aligned system bubble
  if (event.type === "challenge") {
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
              {evidenceBadge}
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

  // verdict: left-aligned system bubble with outcome
  if (event.type === "verdict") {
    const outcome = event.payload.outcome as string
    const rationale = (event.payload.rationale as string) ?? ""
    const confidence = event.payload.confidence as number | undefined
    const isKill = outcome === "kill"

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
            <div className="flex items-center gap-2 mb-1">
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                  isKill
                    ? "bg-red-700/60 text-red-200"
                    : "bg-emerald-700/60 text-emerald-200"
                }`}
              >
                {isKill ? "KILL" : "SURVIVE"}
              </span>
              {confidence != null && (
                <span className="text-[10px] text-zinc-500">
                  confidence: {Math.round(confidence * 100)}%
                </span>
              )}
              {evidenceBadge}
            </div>
            <p className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">{rationale}</p>
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
