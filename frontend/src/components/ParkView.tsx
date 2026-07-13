import { useState } from "react"
import { park } from "../api"
import { LIBRARY_ID } from "../constants"

interface Props {
  onRefresh: () => void
  onSelect: (artifactId: string) => void
}

export default function ParkView({ onRefresh, onSelect }: Props) {
  const [body, setBody] = useState("")
  const [kind, setKind] = useState<"idea" | "review">("idea")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!body.trim()) return
    setLoading(true)
    setError(null)
    try {
      const result = await park(LIBRARY_ID, body.trim(), kind)
      setBody("")
      onRefresh()
      onSelect(result.artifact.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to park")
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="w-full max-w-lg space-y-4">
        <div className="space-y-2">
          <h2 className="text-xl font-medium text-zinc-100">淬 · Cui — 拷问你的想法</h2>
          <p className="text-sm text-zinc-400 leading-relaxed">
            把你的 claim 写下来，系统会用对抗性拷问帮你找到弱点。
          </p>
          <p className="text-sm text-zinc-500 leading-relaxed">
            经历拷问的想法会被记录：幸存者进入 DOC，阵亡者也是有价值的轨迹。
          </p>
        </div>

        <textarea
          className="w-full h-32 bg-zinc-800 border border-zinc-700 rounded-lg p-3 text-zinc-100 placeholder-zinc-500 resize-none focus:outline-none focus:border-zinc-500"
          placeholder="What's the claim or idea?"
          value={body}
          onChange={e => setBody(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          autoFocus
        />

        <div className="flex items-center gap-3">
          <select
            className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-300 focus:outline-none focus:border-zinc-500"
            value={kind}
            onChange={e => setKind(e.target.value as "idea" | "review")}
            disabled={loading}
          >
            <option value="idea">idea</option>
            <option value="review">review</option>
          </select>

          <button
            className="px-4 py-2 bg-zinc-100 text-zinc-900 rounded-lg font-medium hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={handleSubmit}
            disabled={loading || !body.trim()}
          >
            {loading ? "Parking..." : "Park"}
          </button>

          <span className="text-xs text-zinc-600 ml-auto">⌘+Enter 提交</span>
        </div>

        {error && (
          <p className="text-red-400 text-sm">{error}</p>
        )}
      </div>
    </div>
  )
}
