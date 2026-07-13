import { useState, useRef, useEffect } from "react"
import type { Claim, Artifact, VerdictTriage } from "../types"
import { useGrillFlow } from "../hooks/useGrillFlow"
import type { ChallengeView } from "../hooks/useGrillFlow"
import { promote } from "../api"
import { DEATH_CAUSE_LABELS } from "../utils"
import GrillMessage from "./GrillMessage"
import EvidencePanel from "./EvidencePanel"

interface Props {
  artifactId: string
  claim: Claim
  artifact: Artifact
  onRefresh: () => void
}

// ---------------------------------------------------------------------------
// Per-challenge card. Each challenge owns its own lifecycle UI:
//   awaiting_answer  → inline answer box + submit (answers THIS challenge)
//   awaiting_verdict → "AI 正在思考..." (verdict in flight / not yet returned)
//   awaiting_decision→ verdict bubble + confirm/retract for its verdict
//   resolved         → challenge + answer + confirmed verdict outcome
// Multiple awaiting_answer challenges can be open at once; each gets its own
// box, so there is no single global bottom answer bar anymore.
// ---------------------------------------------------------------------------
function ChallengeCard({
  cv,
  loading,
  onSubmitAnswer,
  onConfirm,
  onRetract,
  libraryId,
  claimId,
}: {
  cv: ChallengeView
  loading: boolean
  onSubmitAnswer: (challengeId: string, text: string) => void
  onConfirm: (verdictId: string, triage?: VerdictTriage) => void
  onRetract: (verdictId: string) => void
  libraryId: string
  claimId: string
}) {
  const [answerText, setAnswerText] = useState("")

  const handleSubmit = () => {
    const text = answerText.trim()
    if (!text) return
    setAnswerText("")
    onSubmitAnswer(cv.event.id, text)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="space-y-3">
      {/* The challenge bubble (carries the lens badge when applicable). */}
      <GrillMessage event={cv.event} isPending={false} isLoading={loading} />

      {/* The user's answer, if any. */}
      {cv.answerEvent && (
        <GrillMessage event={cv.answerEvent} isPending={false} isLoading={loading} />
      )}

      {/* The verdict, if any. confirm/retract show only while awaiting_decision.
          A pending KILL hosts the 死因分诊 panel (needs library for the
          boundary successor picker). */}
      {cv.verdictEvent && (
        <GrillMessage
          event={cv.verdictEvent}
          isPending={cv.state === "awaiting_decision"}
          isLoading={loading}
          onConfirm={onConfirm}
          onRetract={onRetract}
          libraryId={libraryId}
          currentClaimId={claimId}
        />
      )}

      {/* Inline answer box, scoped to THIS challenge. */}
      {cv.state === "awaiting_answer" && (
        <div className="pl-1 space-y-2">
          <textarea
            className="w-full h-20 bg-zinc-800 border border-zinc-700 rounded-lg p-3 text-zinc-100 placeholder-zinc-500 resize-none focus:outline-none focus:border-zinc-500"
            placeholder="回答这条挑战..."
            value={answerText}
            onChange={e => setAnswerText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-600">⌘+Enter 提交</span>
            <button
              className="px-5 py-2 bg-zinc-100 text-zinc-900 rounded-lg font-medium hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              onClick={handleSubmit}
              disabled={loading || !answerText.trim()}
            >
              回答
            </button>
          </div>
        </div>
      )}

      {/* Verdict in flight (answered, no verdict yet). */}
      {cv.state === "awaiting_verdict" && (
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
  )
}

export default function GrillView({ artifactId, claim, artifact, onRefresh }: Props) {
  const flow = useGrillFlow(artifactId, claim, artifact.kind)
  const [promoting, setPromoting] = useState(false)
  const [promoteError, setPromoteError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when events change.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [flow.events, flow.claimState])

  // Refresh sidebar when a verdict gets confirmed (resolved count rises) or the
  // claim rolls up to all_resolved — keeps the sidebar status in sync.
  const resolvedCount = flow.challenges.filter(c => c.state === "resolved").length
  useEffect(() => {
    if (resolvedCount > 0) {
      onRefresh()
    }
  }, [resolvedCount, onRefresh])

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

  // The last confirmed verdict outcome decides survive-vs-kill messaging when
  // the claim rolls up to all_resolved (mirrors the old done/confirmed_kill).
  const { lastVerdictOutcome, lastVerdictRationale, lastVerdictDeathCause, lastVerdictRevival } = (() => {
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
    let deathCause: string | null = null
    let revival: string | null = null
    for (const e of flow.events) {
      if (
        e.type === "verdict" &&
        !retracted.has(e.id) &&
        (e.confirmed || confirmed.has(e.id))
      ) {
        outcome = e.payload.outcome as string
        rationale = (e.payload.rationale as string) ?? null
        deathCause = (e.payload.death_cause as string) ?? null
        revival = (e.payload.revival_condition as string) ?? null
      }
    }
    return {
      lastVerdictOutcome: outcome,
      lastVerdictRationale: rationale,
      lastVerdictDeathCause: deathCause,
      lastVerdictRevival: revival,
    }
  })()

  const isKilled = lastVerdictOutcome === "kill"
  const showBoard = flow.claimState !== "idle"

  // Spinner for grill-start / continue / lens scan (no challenge yet to host
  // an inline awaiting_verdict spinner).
  const showTopSpinner =
    flow.loading &&
    !flow.challenges.some(c => c.state === "awaiting_verdict")

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-zinc-950">
      {/* Top bar: claim + kind badge */}
      <div className="shrink-0 border-b border-zinc-800 px-5 py-3">
        <div className="flex items-start gap-3">
          <span className="text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-amber-700/50 text-amber-200 shrink-0 mt-0.5">
            {artifact.kind}
          </span>
          <p className="text-sm text-zinc-200 leading-relaxed flex-1">{claim.body}</p>
          {/* 评品味: explicit, on-demand taste-anchor. Surfaces a taste challenge
              into the board (or nothing, when there's no grilled history/anchor). */}
          <button
            className="shrink-0 mt-0.5 px-3 py-1 rounded-full text-xs font-medium bg-violet-700/40 text-violet-200 border border-violet-600/40 hover:bg-violet-700/60 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
            onClick={flow.assessTaste}
            disabled={flow.loading}
            title="把这个 claim 锚在文献与你的历史上，给出品味定位"
          >
            {flow.loading && (
              <span className="inline-block w-1.5 h-1.5 bg-violet-300 rounded-full animate-pulse" />
            )}
            ◆ 评品味
          </button>
        </div>
        {/* onGrounded refreshes the board: confirming a contradicts ground
            surfaces a pending evidence_contradiction challenge (负证据反哺)
            that must appear immediately. */}
        <EvidencePanel
          artifactId={artifactId}
          libraryId={artifact.library_id}
          claimId={claim.id}
          claimBody={claim.body}
          onGrounded={flow.refreshEvents}
        />
      </div>

      {/* Scrollable multi-challenge board */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        {/* Idle: centered welcome state */}
        {!showBoard && (
          <div className="flex-1 flex items-center justify-center min-h-[60vh]">
            <div className="text-center space-y-5 max-w-sm">
              <p className="text-lg font-medium text-zinc-200">准备好了吗？</p>
              <p className="text-sm text-zinc-400">AI 将对你的 claim 发起挑战。</p>
              <button
                className="px-8 py-3 bg-amber-600 hover:bg-amber-500 text-white font-medium rounded-lg transition-colors text-base"
                onClick={flow.startGrill}
                disabled={flow.loading}
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
                  <p className="pt-1">Lens 还会翻出你轨迹里与此冲突的旧结论。</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* One card per challenge — the parallel board. */}
        {showBoard &&
          flow.challenges.map(cv => (
            <ChallengeCard
              key={cv.event.id}
              cv={cv}
              loading={flow.loading}
              onSubmitAnswer={flow.submitAnswer}
              onConfirm={flow.confirmVerdict}
              onRetract={flow.retractVerdict}
              libraryId={artifact.library_id}
              claimId={claim.id}
            />
          ))}

        {/* Top-level spinner (grill start / continue / lens scan). */}
        {showBoard && showTopSpinner && (
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

      {/* Bottom area: claim rollup controls (only when all challenges resolved). */}
      {showBoard && (
        <div className="shrink-0 border-t border-zinc-800 px-5 py-4">
          {flow.error && <p className="text-red-400 text-sm mb-3">{flow.error}</p>}

          {/* A confirmed KILL means done/kill regardless of other open
              challenges (mirrors the old global done/confirmed_kill). */}
          {!isKilled && flow.claimState === "grilling" && flow.unresolved.length > 0 && (
            <p className="text-xs text-zinc-500">
              还有 {flow.unresolved.length} 条挑战待解决。
            </p>
          )}

          {/* Survived + stopped: distinct terminal "拷问完成" screen. */}
          {!isKilled && flow.claimState === "all_resolved" && flow.stopped && (
            <div className="space-y-3">
              <div className="bg-emerald-950/30 border border-emerald-700/40 rounded-lg px-4 py-4">
                <p className="text-sm font-medium text-emerald-400 mb-2">
                  ✅ 拷问完成
                </p>
                <p className="text-sm text-zinc-300">
                  Claim 存活了 {flow.rounds} 轮挑战。
                </p>
                <p className="text-xs text-zinc-500 leading-relaxed mt-2">
                  这条 claim 经受住了拷问。你可以将它 Promote 成正式结论。
                </p>
              </div>
              <button
                className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white font-medium rounded-lg transition-colors disabled:opacity-50"
                onClick={handlePromote}
                disabled={promoting}
              >
                {promoting ? "Promoting..." : "Promote to DOC"}
              </button>
              {promoteError && <p className="text-red-400 text-sm">{promoteError}</p>}
            </div>
          )}

          {!isKilled && flow.claimState === "all_resolved" && !flow.stopped && (
            <div className="space-y-3">
              <div className="bg-zinc-800/40 border border-zinc-700/40 rounded-lg px-4 py-3">
                <p className="text-sm font-medium text-emerald-400 mb-2">
                  ✅ 所有挑战已通过（{flow.rounds} 轮拷问）
                </p>
                <p className="text-sm text-zinc-300">继续深挖还是到此为止?</p>
                <p className="text-xs text-zinc-500 mt-2">
                  已经历 {flow.rounds} 轮拷问。
                  {flow.rounds < 3 && " 继续可能发现更多弱点。"}
                </p>
              </div>
              <div className="flex gap-3">
                <button
                  className="flex-1 py-2 bg-amber-600 hover:bg-amber-500 text-white font-medium rounded-lg transition-colors disabled:opacity-50"
                  onClick={flow.continueGrill}
                  disabled={flow.loading}
                >
                  继续拷问
                </button>
                <button
                  className="flex-1 py-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 font-medium rounded-lg transition-colors disabled:opacity-50"
                  onClick={flow.stopGrill}
                  disabled={flow.loading}
                >
                  到此为止
                </button>
              </div>
              <button
                className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white font-medium rounded-lg transition-colors disabled:opacity-50"
                onClick={handlePromote}
                disabled={promoting}
              >
                {promoting ? "Promoting..." : "Promote to DOC"}
              </button>
              {promoteError && <p className="text-red-400 text-sm">{promoteError}</p>}
            </div>
          )}

          {isKilled && (
            <div className="space-y-3">
              <div className="bg-red-950/40 border border-red-700/50 rounded-lg px-4 py-4">
                <p className="text-sm font-medium text-red-400 mb-2">
                  ❌ Claim 未通过拷问
                  {lastVerdictDeathCause && (
                    <span className="ml-2 text-xs font-normal text-red-300/80">
                      {DEATH_CAUSE_LABELS[lastVerdictDeathCause] ?? lastVerdictDeathCause}
                    </span>
                  )}
                </p>
                {lastVerdictRationale && (
                  <p className="text-sm text-zinc-400 leading-relaxed mb-3">
                    AI 判定: {lastVerdictRationale}
                  </p>
                )}
                {lastVerdictRevival && (
                  <p className="text-xs text-zinc-400 leading-relaxed mb-3">
                    复活条件: {lastVerdictRevival}
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
        </div>
      )}

      {/* Error display for idle state */}
      {!showBoard && flow.error && (
        <div className="shrink-0 border-t border-zinc-800 px-5 py-3">
          <p className="text-red-400 text-sm">{flow.error}</p>
        </div>
      )}
    </div>
  )
}
