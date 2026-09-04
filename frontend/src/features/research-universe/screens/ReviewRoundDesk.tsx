import { useEffect, useRef, useState, type FormEvent } from "react"
import { command, researchUniverse } from "../api"
import type { Challenge, ReviewRound, VerdictType } from "../types"
import { EvidenceSurface } from "./EvidenceSurface"
import { useNavigation } from "../../../router"

const VERDICT_OPTIONS: { type: VerdictType; label: string; note?: string }[] = [
  { type: "survived", label: "暂时站住了", note: "扛过本轮检验，不是真理证书 · 仅本轮站住" },
  { type: "refuted", label: "这条表述不成立" },
  { type: "not_worth", label: "不值得继续" },
  { type: "boundary", label: "需要收窄／改写" },
  { type: "circumstantial", label: "现在先不投入" },
]

export function ReviewRoundDesk({ roundId }: { roundId: string }) {
  const [round, setRound] = useState<ReviewRound | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [judging, setJudging] = useState(false)
  const [generatingChallenge, setGeneratingChallenge] = useState(false)
  const generation = useRef(0)
  async function load() {
    const current = ++generation.current
    try { const value = await researchUniverse.reviewRound(roundId); if (current === generation.current) { setError(null); setRound(value) } } catch (reason) { if (current === generation.current) setError(reason instanceof Error ? reason.message : "未能读取审查轮次。") }
  }
  useEffect(() => { void load(); return () => { generation.current++ } }, [roundId])
  async function generateMoreChallenge() {
    if (generatingChallenge || round?.verdict) return
    setGeneratingChallenge(true); setError(null)
    try { await researchUniverse.generateAdditionalChallenge(roundId, command({}, 0)); await load() } catch (reason) { setError(reason instanceof Error ? reason.message : "生成更多挑战失败。") } finally { setGeneratingChallenge(false) }
  }
  if (error) return <section className="ru-state" role="alert"><p>未能打开审查轮次：{error}</p><button className="ru-ink-button" onClick={() => void load()}>重试</button></section>
  if (!round) return <section className="ru-state" aria-live="polite">正在读取审查快照…</section>
  const closed = Boolean(round.verdict)
  return <section className="ru-review" aria-labelledby="review-title"><p className="ru-kicker">审查轮次 · 不可变快照</p><h1 id="review-title">审查这一条 claim</h1><div className="ru-snapshot-grid"><article><h2>当时的问题</h2><p className="ru-reading-copy">{round.question_snapshot.text}</p><small>问题快照 {round.question_snapshot.version_id ?? round.question_snapshot.id ?? "已记录"}</small></article><article><h2>当时的 claim</h2><p className="ru-reading-copy">{round.claim_snapshot.text}</p><small>Claim 快照 {round.claim_snapshot.version_id ?? round.claim_snapshot.id ?? "已记录"}</small></article></div>
    <div className="ru-challenge-list">{round.challenges.map((challenge) => <ChallengePanel key={`${challenge.id}-${challenge.status}-${challenge.answers?.length ?? 0}`} round={round} challenge={challenge} onChanged={() => void load()} />)}</div>
    {!closed && <div className="ru-generate-more"><button className="ru-ink-button ru-active" disabled={generatingChallenge} onClick={() => void generateMoreChallenge()}>{generatingChallenge ? "正在生成更多挑战…" : "生成更多挑战"}</button><p className="ru-challenge-note">让 Cui 攻击一个尚未覆盖的角度；新的挑战会进入同一轮审查。</p></div>}
    <EvidenceSurface round={round} onChanged={() => void load()} />
    {!closed && <div className="ru-verdict-actions"><p className="ru-reading-copy">挑战可以暂缓、撤回或带回未确认上下文；本轮结束时，由你作出裁决。</p><button className="ru-ink-button ru-active" onClick={() => setJudging(true)}>作出本轮裁决</button></div>}
    {judging && !closed && <VerdictForge round={round} onChanged={() => void load()} onClose={() => setJudging(false)} />}
    {closed && <ReReview round={round} onError={(message) => setError(message)} />}
    {round.verdict?.verdict_type === "boundary" && <BoundaryLineage round={round} onError={(message) => setError(message)} />}
    <nav className="ru-review-exits" aria-label="离开审查轮次"><a className="ru-ink-button" href={`/workspaces/${round.workspace_id}`}>回工作区继续探索</a><a className="ru-quiet-button" href="/">回研究宇宙查看上下文</a><a className="ru-quiet-button" href={`/workspaces/${round.workspace_id}/dialogue`}>回文献探讨继续收尾</a></nav></section>
}

function ChallengePanel({ round, challenge, onChanged }: { round: ReviewRound; challenge: Challenge; onChanged: () => void }) {
  const [answer, setAnswer] = useState("")
  const [busy, setBusy] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [deferOpen, setDeferOpen] = useState(false)
  const [condition, setCondition] = useState("")
  const [explainOpen, setExplainOpen] = useState(false)
  const [withdrawOpen, setWithdrawOpen] = useState(false)
  const [withdrawReason, setWithdrawReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const open = challenge.status === "pending" || challenge.status === "answered"
  const answered = (challenge.answers?.length ?? 0) > 0
  async function saveAnswer() {
    if (!answer.trim() || busy) return
    setBusy(true); setError(null)
    try { await researchUniverse.answerChallenge(challenge.id, command({ answer_text: answer.trim(), provisional_anchor_refs: [] }, challenge.sequence ?? 1)); setAnswer(""); onChanged() } catch (reason) { setError(reason instanceof Error ? reason.message : "保存答辩失败。") } finally { setBusy(false) }
  }
  async function defer() {
    if (!condition.trim() || busy) return
    setBusy(true); setError(null)
    try { await researchUniverse.deferChallenge(challenge.id, command({ reason: "暂缓这条挑战", condition: condition.trim() }, challenge.sequence ?? 1)); onChanged() } catch (reason) { setError(reason instanceof Error ? reason.message : "暂缓失败。") } finally { setBusy(false) }
  }
  async function withdraw() {
    if (!withdrawReason.trim() || busy) return
    setBusy(true); setError(null)
    try { await researchUniverse.withdrawChallenge(challenge.id, command({ reason: withdrawReason.trim() }, challenge.sequence ?? 1)); onChanged() } catch (reason) { setError(reason instanceof Error ? reason.message : "撤回失败。") } finally { setBusy(false) }
  }
  if (!open) {
    return <aside className="ru-challenge ru-challenge-closed" aria-labelledby={`challenge-title-${challenge.id}`}><p className="ru-kicker">{challenge.status === "deferred" ? "暂缓" : challenge.status === "withdrawn" ? "已撤回" : "已裁决"}</p><h2 id={`challenge-title-${challenge.id}`}>{challenge.attack_surface}</h2>{challenge.status === "deferred" && challenge.defer && <p className="ru-reading-copy">何时重看：{challenge.defer.condition}</p>}{challenge.status === "withdrawn" && challenge.withdraw && <p className="ru-reading-copy">理由：{challenge.withdraw.reason}</p>}</aside>
  }
  return <aside className="ru-challenge" aria-labelledby={`challenge-title-${challenge.id}`}><p className="ru-kicker">Cui 的挑战 · {answered ? "已回应 · 待裁决" : "待回应"}</p><h2 id={`challenge-title-${challenge.id}`}>{challenge.attack_surface}</h2><dl><div><dt>为什么重要</dt><dd>{challenge.why_it_matters}</dd></div><div><dt>可以怎样自检</dt><dd>{challenge.self_check_method}</dd></div></dl>{challenge.provenance && <p className="ru-provenance">生成依据：{challenge.provenance.basis_refs?.join(" · ") ?? "已记录"} · 不确定性：{challenge.provenance.uncertainty ?? "未说明"}</p>}
    {answered && <div className="ru-answer-log"><p className="ru-kicker">已保存答辩</p>{(challenge.answers ?? []).map((item) => <p className="ru-answer-entry" key={item.version_id}>{item.text}{item.provisional_anchor_refs.length ? <> · 带入未确认上下文 {item.provisional_anchor_refs.join("、")}</> : null}</p>)}<p className="ru-challenge-note">答辩已保存，挑战仍待裁决。</p></div>}
    <form className="ru-answer-form" onSubmit={(e) => { e.preventDefault(); void saveAnswer() }}><label htmlFor={`answer-${challenge.id}`}>我目前的回应</label><textarea id={`answer-${challenge.id}`} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="写下对这一条挑战的回应（作为暂定上下文，不是已确认事实）。" disabled={busy} /><button className="ru-ink-button ru-active" disabled={busy || !answer.trim()}>{busy ? "正在保存…" : "保存答辩"}</button></form>
    <div className="ru-cant-answer"><button className="ru-quiet-button" onClick={() => setMenuOpen((v) => !v)} aria-expanded={menuOpen}>我还不能回应 ▾</button>{menuOpen && <ul className="ru-cant-answer-menu">{!deferOpen && <li><button className="ru-quiet-button" onClick={() => { setDeferOpen(true); setExplainOpen(false) }}>暂缓这条挑战（写下何时重看）</button></li>}{deferOpen && <li className="ru-inline-action"><label htmlFor={`defer-condition-${challenge.id}`}>何时重看</label><input id={`defer-condition-${challenge.id}`} value={condition} onChange={(e) => setCondition(e.target.value)} placeholder="例如：读到 Paper A 之后" /><button className="ru-quiet-button" disabled={busy || !condition.trim()} onClick={() => void defer()}>确认暂缓</button></li>}{!explainOpen && <li><button className="ru-quiet-button" onClick={() => { setExplainOpen(true); setDeferOpen(false) }}>先理解这一关</button></li>}{explainOpen && <li className="ru-inline-action"><p className="ru-reading-copy">通用自检方法：{challenge.self_check_method}</p></li>}<li><a className="ru-quiet-button" href={`/workspaces/${round.workspace_id}`}>回到探索，不作判断</a></li></ul>}
    {!withdrawOpen && <button className="ru-quiet-button ru-danger" onClick={() => setWithdrawOpen(true)}>撤回这条挑战</button>}{withdrawOpen && <div className="ru-inline-action"><label htmlFor={`withdraw-reason-${challenge.id}`}>撤回理由</label><input id={`withdraw-reason-${challenge.id}`} value={withdrawReason} onChange={(e) => setWithdrawReason(e.target.value)} placeholder="为什么撤回这条挑战" /><button className="ru-quiet-button" disabled={busy || !withdrawReason.trim()} onClick={() => void withdraw()}>确认撤回</button><button className="ru-quiet-button" onClick={() => { setWithdrawOpen(false); setWithdrawReason("") }}>取消</button></div>}</div>
    {error && <p className="ru-error" role="alert">{error}</p>}
    {!answer && !answered && <p className="ru-challenge-note">这条挑战仍待回应。保存答辩不会解决挑战；你可以暂缓、撤回，或先回工作区继续探索。</p>}
  </aside>
}

function VerdictForge({ round, onChanged, onClose }: { round: ReviewRound; onChanged: () => void; onClose: () => void }) {
  const ledger = round.ledger
  const [verdictType, setVerdictType] = useState<VerdictType | null>(null)
  const [reason, setReason] = useState("")
  const [revival, setRevival] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const valid = Boolean(verdictType) && reason.trim().length > 0 && (verdictType !== "circumstantial" || revival.trim().length > 0)
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!verdictType || !valid || busy) return
    setBusy(true); setError(null)
    try { await researchUniverse.confirmVerdict(round.id, command({ verdict_type: verdictType, user_reason: reason.trim(), revival_condition: verdictType === "circumstantial" ? revival.trim() : null }, round.sequence ?? 1)); onChanged(); onClose() } catch (reasonError) { setError(reasonError instanceof Error ? reasonError.message : "裁决失败。") } finally { setBusy(false) }
  }
  const buckets: { key: "answered" | "deferred" | "pending" | "brought_unconfirmed"; label: string }[] = [
    { key: "answered", label: "已回应" },
    { key: "deferred", label: "暂缓" },
    { key: "pending", label: "仍待回应" },
    { key: "brought_unconfirmed", label: "带入但未确认" },
  ]
  return <section className="ru-verdict" aria-labelledby="verdict-ledger-title"><p className="ru-kicker">本轮审查账本</p><h2 id="verdict-ledger-title">作出本轮裁决</h2><p className="ru-reading-copy">Claim（本轮文本）：{round.claim_snapshot.text}</p><div className="ru-ledger-grid">{buckets.map((bucket) => { const items = ledger?.[bucket.key] ?? []; return <section key={bucket.key}><h3>{bucket.label}</h3>{items.length ? items.map((item) => <p key={item.id} className="ru-ledger-item">{item.attack_surface}</p>) : <p className="ru-ledger-empty">—</p>}</section> })}</div><p className="ru-challenge-note">这是一项你的判断。Cui 不会替你决定结果。</p><form className="ru-verdict-form" onSubmit={submit}><fieldset><legend>本轮裁决</legend>{VERDICT_OPTIONS.map((option) => <label key={option.type}><input type="radio" name="verdict" checked={verdictType === option.type} onChange={() => setVerdictType(option.type)} /> <span>{option.label}</span>{option.note && <small>{option.note}</small>}</label>)}</fieldset><label htmlFor="verdict-reason">你的理由</label><textarea id="verdict-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="写下这项判断的依据。" required />{verdictType === "circumstantial" && <label htmlFor="verdict-revival">现在先不投入 —— 何时、什么条件下再回来（必填）</label>}{verdictType === "circumstantial" && <input id="verdict-revival" value={revival} onChange={(e) => setRevival(e.target.value)} placeholder="例如：等数据可验证后再重看" required />}{error && <p className="ru-error" role="alert">{error}</p>}<div className="ru-verdict-actions"><button className="ru-ink-button ru-active" disabled={busy || !valid}>{busy ? "正在记录裁决…" : "确认裁决"}</button><button className="ru-quiet-button" type="button" onClick={onClose}>取消</button></div></form></section>
}

function ReReview({ round, onError }: { round: ReviewRound; onError: (message: string) => void }) {
  const { navigate } = useNavigation()
  const [busy, setBusy] = useState(false)
  const claimId = round.claim_snapshot.id
  async function startAgain() {
    if (!claimId || busy) return
    setBusy(true)
    try { const result = await researchUniverse.startReview(claimId, command({}, 0)); navigate(`/review-rounds/${result.result.review_round_id}`) } catch (reason) { onError(reason instanceof Error ? reason.message : "再次审查失败。") } finally { setBusy(false) }
  }
  return <section className="ru-rereview" aria-labelledby="rereview-title"><p className="ru-kicker">已裁决 · 可再次审查</p><h2 id="rereview-title">再次审查这一条 claim</h2>{(round.rounds?.length ?? 0) > 0 && <ul className="ru-round-history">{(round.rounds ?? []).map((item) => <li key={item.id}><span>审查轮次 {item.id.slice(0, 8)}</span><strong>{item.verdict ? `裁决：${item.verdict.verdict_type}` : "未裁决"}</strong></li>)}</ul>}<button className="ru-ink-button ru-active" disabled={busy} onClick={() => void startAgain()}>{busy ? "正在形成新的挑战…" : "再次审查这一条 claim"}</button></section>
}

function BoundaryLineage({ round, onError }: { round: ReviewRound; onError: (message: string) => void }) {
  const { navigate } = useNavigation()
  const [busy, setBusy] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null
  const verdict = round.verdict
  async function openNewQuestion() {
    if (busy) return
    setBusy(true)
    try {
      const active = await researchUniverse.active()
      const question = `把这条边界做成一个开放问题：${round.claim_snapshot.text}`
      const created = await researchUniverse.createWorkspace(active.id, command({ question }, 0))
      navigate(`/workspaces/${created.result.workspace_id}`)
    } catch (reason) { onError(reason instanceof Error ? reason.message : "开新问题失败。") } finally { setBusy(false) }
  }
  return <section className="ru-boundary" aria-labelledby="boundary-title"><p className="ru-kicker">边界 · 已记录</p><h2 id="boundary-title">这条 claim 已保留为本轮结论；不会被改写，也不会自动生成替代主张。</h2><p className="ru-reading-copy">理由：{verdict?.user_reason ?? "未说明"}</p><nav className="ru-review-exits" aria-label="边界出口"><a className="ru-ink-button" href={`/workspaces/${round.workspace_id}`}>回到探索稿</a><button className="ru-ink-button ru-active" disabled={busy} onClick={() => void openNewQuestion()}>{busy ? "正在创建新问题…" : "围绕这条边界开一个新问题"}</button><button className="ru-quiet-button" onClick={() => setDismissed(true)}>暂时停在这里</button></nav></section>
}
