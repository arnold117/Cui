import type { ClaimStatus } from "../types"

interface Props {
  goal: string
  kind: string
  status: ClaimStatus
  selected: boolean
  onClick: () => void
}

const STATUS_COLORS: Record<ClaimStatus, string> = {
  parked: "bg-zinc-500",
  grilling: "bg-amber-500",
  survived: "bg-emerald-500",
  killed: "bg-red-500",
}

export default function SidebarItem({ goal, kind, status, selected, onClick }: Props) {
  const truncated = goal.length > 60 ? goal.slice(0, 60) + "..." : goal

  return (
    <button
      className={`w-full text-left px-3 py-2 rounded-md flex items-start gap-2 transition-colors ${
        selected
          ? "bg-zinc-700 text-zinc-100"
          : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
      }`}
      onClick={onClick}
    >
      <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${STATUS_COLORS[status]}`} />
      <span className="flex-1 min-w-0">
        <span className="block text-sm leading-snug">{truncated}</span>
        <span className="text-xs text-zinc-500 uppercase tracking-wide">{kind}</span>
      </span>
    </button>
  )
}
