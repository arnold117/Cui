import { useState, useRef, useEffect } from "react"
import type { Claim, Artifact, Event } from "../types"
import { useGrillFlow } from "../hooks/useGrillFlow"
import { promote } from "../api"
import GrillMessage from "./GrillMessage"

interface Props {
  artifactId: string
  claim: Claim
  artifact: Artifact
  onRefresh: () => void
}

function getPendingIds(events: Event[]): Set<string> {
  const retracted = new Set<string>()
  for (const e of events) {
    if (e.type === "retract" && e.target_ref) retracted.add(e.target_ref)
  }
  const confirmed = new Set<string>()
  for (const e of events) {
    if (e.type === "confirm" && e.target_ref && !retracted.has(e.id)) {
      confirmed.add(e.target_ref)
    }
  }

  const pending = new Set<string>()
  for (const e of events) {
    if (
      (e.type === "challenge" || e.type === "verdict") &&
      !e.confirmed &&
      !confirmed.has(e.id) &&
      !retracted.has(e.id)
    ) {
      pending.add(e.id)
    }
  }
  return pending
}

export default function GrillView({ artifactId, claim, artifact, onRefresh }: Props) {
  const flow = useGrillFlow(artifactId, claim, artifact.kind)
  const [answerText, setAnswerText] = useState("")
  const [promoting, setPromoting] = useState(false)
  const [promoteError, setPromoteError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const pendingIds = getPendingIds(flow.events)

  // Auto-scroll to bottom when events change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [flow.events, flow.phase])

  const handleSubmitAnswer = () => {
    if (!answerText.trim()) return
    const text = answerText.trim()
    setAnswerText("")
    flow.submitAnswer(text)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleSubmitAnswer()
    }
  }

  const handlePromote = async () => {
    setPromoting(true)
    setPromoteError(null)
    try {
      await promote(artifactId, claim.id)
      onRefresh()
    } catch (e) {
      setPromoteError(e instanceof Error ? e.message : "Failed to promote")
    } finally {
      setPromoting(false)
    }
  }

  // Determine last confirmed verdict outcome and rationale
  const { lastVerdictOutcome, lastVerdictRationale } = (() => {
    const retracted = new Set<string>()
    for (const e of flow.events) {
      if (e.type === "retract" && e.target_ref) retracted.add(e.target_ref)
    }
    const confirmed = new Set<string>()
    for (const e of flow.events) {
      if (e.type === "confirm" && e.target_ref && !retracted.has(e.id)) {
        confirmed.add(e.target_ref)
      }
    }
    let outcome: string | null = null
    let rationale: string | null = null
    for (const e of flow.events) {
      if (
        e.type === "verdict" &&
        !retracted.has(e.id) &&
        (e.confirmed || confirmed.has(e.id))
      ) {
        outcome = e.payload.outcome as string
        rationale = (e.payload.rationale as string) ?? null
      }
    }
    return { lastVerdictOutcome: outcome, lastVerdictRationale: rationale }
  })()

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-zinc-950">
      {/* Top bar: claim + kind badge */}
      <div className="shrink-0 border-b border-zinc-800 px-5 py-3">
        <div className="flex items-start gap-3">
          <span className="text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-amber-700/50 text-amber-200 shrink-0 mt-0.5">
            {artifact.kind}
          </span>
          <p className="text-sm text-zinc-200 leading-relaxed">{claim.body}</p>
        </div>
      </div>

      {/* Scrollable conversation area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        {/* Idle: centered welcome state */}
        {flow.phase === "idle" && flow.events.filter(e => e.type === "challenge").length === 0 && (
          <div className="flex-1 flex items-center justify-center min-h-[60vh]">
            <div className="text-center space-y-5 max-w-sm">
              <p className="text-lg font-medium text-zinc-200">准备好了吗？</p>
              <p className="text-sm text-zinc-400">AI 将对你的 claim 发起挑战。</p>
              <button
                className="px-8 py-3 bg-amber-600 hover:bg-amber-500 text-white font-medium rounded-lg transition-colors text-base"
                onClick={flow.startGrill}
              >
                开始拷问
              </button>
              <div className="pt-2 space-y-1">
                <p className="text-xs text-zinc-600 leading-relaxed">
                  流程：AI 提问 → 你回答 → AI 判定 → 你确认/撤回 → 可选继续
                </p>
                <div className="text-xs text-zinc-600 leading-relaxed pt-2 text-left mx-auto max-w-xs space-y-1">
                  <p>点击开始后，AI 会针对你的 claim 提出挑战性问题。</p>
                  <p>你需要回答每个挑战。AI 会判定你的回答是否足够。</p>
                  <p className="pl-3">· 通过 → claim 存活，可以继续深挖或结束</p>
                  <p className="pl-3">· 未通过 → claim 阵亡，但轨迹永久保留</p>
                  <p>每个 AI 判定都需要你确认或撤回。</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Show events when there are some */}
        {(flow.phase !== "idle" || flow.events.filter(e => e.type === "challenge").length > 0) && (
          <>
            {flow.events.map(event => (
              <GrillMessage
                key={event.id}
                event={event}
                isPending={pendingIds.has(event.id)}
                isLoading={flow.loading}
                onConfirm={flow.confirmVerdict}
                onRetract={flow.retractVerdict}
              />
            ))}
          </>
        )}

        {/* Loading indicator in conversation */}
        {(flow.phase === "challenging" || flow.phase === "verdicting" || flow.phase === "starting" || flow.phase === "answering") && (
          <div className="flex justify-start">
            <div className="bg-zinc-800/40 border border-zinc-700/40 rounded-xl rounded-tl-sm px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
                <span className="text-sm text-zinc-400">AI 正在思考...</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Bottom area: changes by phase */}
      {/* Only show bottom bar when there's actual input or actions needed */}
      {flow.phase !== "idle" && (
        <div className="shrink-0 border-t border-zinc-800 px-5 py-4">
          {flow.error && (
            <p className="text-red-400 text-sm mb-3">{flow.error}</p>
          )}

          {flow.phase === "awaiting_answer" && (
            <div className="space-y-2">
              <textarea
                className="w-full h-24 bg-zinc-800 border border-zinc-700 rounded-lg p-3 text-zinc-100 placeholder-zinc-500 resize-none focus:outline-none focus:border-zinc-500"
                placeholder="输入你的回答..."
                value={answerText}
                onChange={e => setAnswerText(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={flow.loading}
                autoFocus
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-600">⌘+Enter 提交</span>
                <button
                  className="px-5 py-2 bg-zinc-100 text-zinc-900 rounded-lg font-medium hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  onClick={handleSubmitAnswer}
                  disabled={flow.loading || !answerText.trim()}
                >
                  回答
                </button>
              </div>
            </div>
          )}

          {flow.phase === "confirmed_survive" && (
            <div className="bg-emerald-950/40 border border-emerald-700/50 rounded-lg px-4 py-3 text-center">
              <p className="text-sm text-emerald-400 font-medium">已确认 — 通过</p>
            </div>
          )}

          {flow.phase === "awaiting_decision" && (
            <div className="space-y-3">
              <div className="bg-zinc-800/40 border border-zinc-700/40 rounded-lg px-4 py-3">
                <p className="text-sm font-medium text-emerald-400 mb-2">
                  ✅ 第 {flow.rounds} 轮拷问通过
                </p>
                {flow.unresolved.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-sm text-zinc-300">你还有以下挑战未解决:</p>
                    <ul className="space-y-1 pl-1">
                      {flow.unresolved.map((desc, i) => (
                        <li key={i} className="text-sm text-zinc-400 flex items-start gap-2">
                          <span className="text-zinc-600 shrink-0">·</span>
                          <span>{desc}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="text-xs text-amber-500/80 mt-2 leading-relaxed">
                      不继续的影响: 未解决的挑战会留在轨迹中，Lens 会记录你选择跳过了这些问题。
                    </p>
                  </div>
                ) : (
                  <p className="text-sm text-zinc-300">
                    所有挑战已通过。继续深挖还是到此为止?
                  </p>
                )}
                <p className="text-xs text-zinc-500 mt-2">
                  已经历 {flow.rounds} 轮拷问。
                  {flow.rounds < 3 && " 继续可能发现更多弱点。"}
                </p>
              </div>
              <div className="flex gap-3">
                <button
                  className="flex-1 py-2 bg-amber-600 hover:bg-amber-500 text-white font-medium rounded-lg transition-colors"
                  onClick={flow.continueGrill}
                  disabled={flow.loading}
                >
                  继续拷问
                </button>
                <button
                  className="flex-1 py-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 font-medium rounded-lg transition-colors"
                  onClick={flow.stopGrill}
                  disabled={flow.loading}
                >
                  到此为止
                </button>
              </div>
            </div>
          )}

          {flow.phase === "confirmed_kill" && (
            <div className="space-y-3">
              <div className="bg-red-950/40 border border-red-700/50 rounded-lg px-4 py-4">
                <p className="text-sm font-medium text-red-400 mb-2">❌ Claim 未通过本轮拷问</p>
                {lastVerdictRationale && (
                  <p className="text-sm text-zinc-400 leading-relaxed mb-3">
                    AI 判定: {lastVerdictRationale}
                  </p>
                )}
                <p className="text-xs text-zinc-500 leading-relaxed">
                  这个想法已被记录为阵亡。阵亡轨迹同样有价值 — 它会成为你的 Lens 学习素材。
                </p>
              </div>
              <button
                className="w-full py-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 font-medium rounded-lg transition-colors"
                onClick={() => onRefresh()}
              >
                查看完整轨迹
              </button>
            </div>
          )}

          {flow.phase === "done" && (
            <div className="space-y-3">
              <div className="bg-zinc-800/40 border border-zinc-700/40 rounded-lg px-4 py-3 text-center">
                {lastVerdictOutcome === "kill" ? (
                  <>
                    <p className="text-sm font-medium text-red-400 mb-1">❌ Claim 未通过拷问</p>
                    <p className="text-xs text-zinc-500">阵亡轨迹同样有价值 — 它会成为你的 Lens 学习素材。</p>
                  </>
                ) : (
                  <p className="text-sm text-emerald-400">
                    拷问完成。Claim 存活了 {flow.rounds} 轮挑战。
                  </p>
                )}
              </div>
              {lastVerdictOutcome !== "kill" && (
                <button
                  className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white font-medium rounded-lg transition-colors disabled:opacity-50"
                  onClick={handlePromote}
                  disabled={promoting}
                >
                  {promoting ? "Promoting..." : "Promote to DOC"}
                </button>
              )}
              {promoteError && (
                <p className="text-red-400 text-sm">{promoteError}</p>
              )}
            </div>
          )}

          {/* Loading phases show nothing in the bottom (spinner is in conversation area) */}
        </div>
      )}

      {/* Error display for idle phase */}
      {flow.phase === "idle" && flow.error && (
        <div className="shrink-0 border-t border-zinc-800 px-5 py-3">
          <p className="text-red-400 text-sm">{flow.error}</p>
        </div>
      )}
    </div>
  )
}
