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

  // challenge: left-aligned system bubble
  if (event.type === "challenge") {
    const question = (event.payload.question as string) ?? ""
    return (
      <div className="flex justify-start">
        <div className="max-w-[75%] space-y-2">
          <div className="bg-blue-950/60 border border-blue-800/40 rounded-xl rounded-tl-sm px-4 py-3">
            <p className="text-xs text-blue-400 font-medium mb-1">Challenge</p>
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
