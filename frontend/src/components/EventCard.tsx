import type { Event } from "../types"

interface Props {
  event: Event
}

const TYPE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  challenge: { bg: "bg-blue-700/50", text: "text-blue-200", label: "Challenge" },
  answer: { bg: "bg-zinc-600/50", text: "text-zinc-200", label: "Answer" },
  verdict: { bg: "bg-zinc-600/50", text: "text-zinc-200", label: "Verdict" },
  promote: { bg: "bg-purple-700/50", text: "text-purple-200", label: "Promote" },
  park: { bg: "bg-zinc-600/50", text: "text-zinc-300", label: "Park" },
  confirm: { bg: "bg-emerald-700/50", text: "text-emerald-200", label: "Confirm" },
  retract: { bg: "bg-red-700/50", text: "text-red-200", label: "Retract" },
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function extractContent(event: Event): string {
  const p = event.payload
  if (event.type === "challenge") return (p.question as string) ?? ""
  if (event.type === "answer") return (p.response as string) ?? ""
  if (event.type === "verdict") return (p.rationale as string) ?? ""
  if (event.type === "promote") return "Promoted to DOC"
  if (event.type === "park") return (p.body as string) ?? ""
  if (event.type === "confirm") return "Confirmed"
  if (event.type === "retract") return "Retracted"
  return JSON.stringify(p)
}

export default function EventCard({ event }: Props) {
  const style = TYPE_STYLES[event.type] ?? {
    bg: "bg-zinc-600/50",
    text: "text-zinc-300",
    label: event.type,
  }

  // Verdict-specific badge coloring
  const isVerdict = event.type === "verdict"
  const outcome = event.payload.outcome as string | undefined
  const verdictBadge = isVerdict
    ? outcome === "kill"
      ? { bg: "bg-red-700/50", text: "text-red-200" }
      : { bg: "bg-emerald-700/50", text: "text-emerald-200" }
    : null

  const confidence = isVerdict ? (event.payload.confidence as number | undefined) : undefined

  return (
    <div className="bg-zinc-800/40 border border-zinc-700/50 rounded-lg px-4 py-3 space-y-2">
      <div className="flex items-center gap-2">
        <span
          className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full ${
            verdictBadge ? verdictBadge.bg : style.bg
          } ${verdictBadge ? verdictBadge.text : style.text}`}
        >
          {style.label}
        </span>
        {isVerdict && outcome && (
          <span
            className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
              outcome === "kill"
                ? "bg-red-700/60 text-red-200"
                : "bg-emerald-700/60 text-emerald-200"
            }`}
          >
            {outcome.toUpperCase()}
          </span>
        )}
        {confidence != null && (
          <span className="text-[10px] text-zinc-500">
            {Math.round(confidence * 100)}%
          </span>
        )}
        <span className="text-[10px] text-zinc-600 ml-auto">{formatTimestamp(event.ts)}</span>
      </div>
      <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">
        {extractContent(event)}
      </p>
    </div>
  )
}
