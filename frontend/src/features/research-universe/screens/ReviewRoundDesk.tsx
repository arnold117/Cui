import { useEffect, useRef, useState, type FormEvent } from "react"
import { command, researchUniverse } from "../api"
import type { Challenge, ChallengeStatus, ExplorationAnchor, LiteratureChallengeEnvelope, Material, ReviewRound, VerdictType } from "../types"
import { EvidenceSurface } from "./EvidenceSurface"
import { VERDICT_LABELS } from "./LandscapePanel"
import { useNavigation } from "../../../router"

const VERDICT_OPTIONS: { type: VerdictType; label: string; note?: string }[] = [
  { type: "survived", label: "暂时站住了", note: "扛过本轮检验，不是真理证书 · 仅本轮站住" },
  { type: "refuted", label: "这条表述不成立" },
  { type: "not_worth", label: "不值得继续" },
  { type: "boundary", label: "需要收窄／改写" },
  { type: "circumstantial", label: "现在先不投入" },
]
const STATUS_LABELS: Record<ChallengeStatus, string> = { pending: "仍待回应", answered: "已回应", deferred: "暂缓", withdrawn: "已撤回", resolved_by_verdict: "已裁决" }
const STATUS_MARKS: Record<ChallengeStatus, string> = { pending: "●", answered: "✓", deferred: "‖", withdrawn: "–", resolved_by_verdict: "·" }

type Segment = "answer" | "evidence" | "verdict"
const SEGMENTS: [Segment, string][] = [["answer", "应答"], ["evidence", "取证"], ["verdict", "裁决"]]
// ledger 口径：只有 status=pending 算仍待回应；已回应、暂缓、撤回都不算（同后端 _ledger）
const stillPending = (round: ReviewRound) => round.challenges.filter((c) => c.status === "pending")
const defaultSegment = (round: ReviewRound): Segment => stillPending(round).length ? "answer" : round.evidence_candidates?.some((c) => c.status === "pending") ? "evidence" : "verdict"

type LiteratureRefs = Pick<LiteratureChallengeEnvelope, "material_ids" | "external_refs">
/** 文献发难的来源(由旅程页传入):本机有选料 → selection 照旧整组发;没有 → 从本工作区待取证材料里勾选,作 material_ids */
export interface LiteratureSource { selection?: LiteratureRefs; evidence: Material[] }
/** 应答可引用的(由旅程页传入,不另发请求):本工作区的待取证材料 + 探索稿锚点;写入 provisional_anchor_refs */
export interface Citable { materials: Material[]; anchors: ExplorationAnchor[] }
const clip = (text: string, n: number) => text.length > n ? `${text.slice(0, n)}…` : text
function refLabel(id: string, citable?: Citable) {
  const m = citable?.materials.find((x) => x.id === id)
  if (m) return `${m.source_locator ?? clip(m.excerpt, 16)}${m.content_scope === "abstract" ? "（摘要）" : ""}`
  const a = citable?.anchors.find((x) => x.id === id)
  return a ? `锚点「${clip(a.selected_text, 16)}」` : id
}

/**
 * 审查面:嵌在旅程页右侧(/workspaces/:id/rounds/:rid),没有页级出口。
 * onClose = 收起右侧面(closeLabel 改按钮文字);onLoaded = 每次读到这一轮(打开、刷新、改动后)通知宿主刷新左栏;fromGap = 这条 claim 是反证 gap 写成的。
 */
export function ReviewRoundDesk({ roundId, onClose, closeLabel, onLoaded, literature, fromGap, citable }: { roundId: string; onClose?: () => void; closeLabel?: string; onLoaded?: () => void; literature?: LiteratureSource; fromGap?: boolean; citable?: Citable }) {
  const [round, setRound] = useState<ReviewRound | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [segment, setSegment] = useState<Segment | null>(null)
  const [focusId, setFocusId] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [refDrafts, setRefDrafts] = useState<Record<string, string[]>>({})
  const [generatingChallenge, setGeneratingChallenge] = useState(false)
  const [litOpen, setLitOpen] = useState(false)
  const [litPicked, setLitPicked] = useState<string[]>([])
  const [litBusy, setLitBusy] = useState(false)
  const generation = useRef(0)
  async function load() {
    const current = ++generation.current
    // 默认段只在打开这一轮时定一次，之后刷新不跳段
    try { const value = await researchUniverse.reviewRound(roundId); if (current === generation.current) { setError(null); setRound(value); setSegment((s) => s ?? defaultSegment(value)); onLoaded?.() } } catch (reason) { if (current === generation.current) setError(reason instanceof Error ? reason.message : "未能读取审查轮次。") }
  }
  useEffect(() => { setSegment(null); void load(); return () => { generation.current++ } }, [roundId])
  async function generateMoreChallenge() {
    if (generatingChallenge || round?.verdict) return
    setGeneratingChallenge(true); setError(null)
    try { const generated = await researchUniverse.generateAdditionalChallenge(roundId, command({}, 0)); setFocusId(generated.result.challenge_id); await load() } catch (reason) { setError(reason instanceof Error ? reason.message : "生成更多挑战失败。") } finally { setGeneratingChallenge(false) }
  }
  async function literatureAttack(refs: LiteratureRefs) {
    if (litBusy || round?.verdict) return
    setLitBusy(true); setError(null)
    try { const made = await researchUniverse.literatureChallenge(roundId, command(refs, 0)); setLitOpen(false); setLitPicked([]); setFocusId(made.result.challenge_id); await load() } catch (reason) { setError(reason instanceof Error ? reason.message : "文献发难失败。") } finally { setLitBusy(false) }
  }
  if (error) return <section className="ru-state" role="alert"><p>未能打开审查轮次：{error}</p><button className="ru-ink-button" onClick={() => void load()}>重试</button></section>
  if (!round) return <section className="ru-state" aria-live="polite">正在读取审查快照…</section>
  const closed = Boolean(round.verdict)
  const active = segment ?? defaultSegment(round)
  const pending = stillPending(round)
  const focused = round.challenges.find((c) => c.id === focusId) ?? pending[0] ?? round.challenges[0]
  // 回应完一关（应答/暂缓/撤回）自动聚焦它之后的下一条仍待回应，到底绕回开头；没有就停在这一关
  const settle = (id: string) => {
    const i = round.challenges.findIndex((c) => c.id === id)
    setFocusId([...round.challenges.slice(i + 1), ...round.challenges.slice(0, i)].find((c) => c.status === "pending")?.id ?? id)
    void load()
  }
  const nth = (round.rounds ?? []).findIndex((r) => r.id === round.id) + 1
  const pendingCandidates = (round.evidence_candidates ?? []).filter((c) => c.status === "pending").length
  // 分段旁的小计数:[文字, 是否待处理(rust)]
  const tabCounts: Partial<Record<Segment, [string, boolean]>> = {
    evidence: pendingCandidates ? [`待确认 ${pendingCandidates}`, true] : [`${round.evidence_candidates?.length ?? 0} 条`, false],
    verdict: [round.verdict ? `已裁决 · ${VERDICT_LABELS[round.verdict.verdict_type] ?? round.verdict.verdict_type}` : "未裁决", false],
  }
  // 问题已是左栏标题:这里只留本轮 claim 快照(投影没有写入时间,「写于…」暂缺)
  return <section className="ru-review" aria-labelledby="review-title"><header className="ru-review-head"><p className="ru-kicker" id="review-title">审查轮{nth > 0 ? ` ${String(nth).padStart(2, "0")}` : ""} · claim 快照</p>{onClose && <button type="button" className="ru-quiet-button" onClick={onClose}>{closeLabel ?? "收起"}</button>}</header><blockquote className="ru-claim-quote">{round.claim_snapshot.text}</blockquote><p className="ru-provenance">{fromGap && <><span className="ru-tag">来自 gap</span> </>}本轮文本快照</p>
    <div className="ru-review-tabbar"><div role="tablist" aria-label="审查分段">{SEGMENTS.map(([key, label]) => { const count = tabCounts[key]; return <button key={key} id={`review-tab-${key}`} role="tab" aria-selected={active === key} aria-controls="review-segment" className="ru-review-tab" onClick={() => setSegment(key)}>{label}{count && <>{" "}<small className={count[1] ? "ru-pending-line" : undefined}>{count[0]}</small></>}</button> })}</div><span className={pending.length ? "ru-review-pending" : undefined}>{pending.length ? `仍待回应 ${pending.length}` : "没有仍待回应的挑战"}</span></div>
    <div id="review-segment" role="tabpanel" aria-labelledby={`review-tab-${active}`}>
      {active === "answer" && <section aria-label="攻击面"><p className="ru-kicker">攻击面 · {round.challenges.length} 关 · 一次展开一关</p><ol className="ru-attack-list">{round.challenges.map((challenge) => {
        const on = challenge.id === focused?.id
        return <li key={challenge.id}><button id={`challenge-title-${challenge.id}`} className={`ru-attack-row ru-attack-${challenge.status}`} aria-expanded={on} onClick={() => setFocusId(challenge.id)}><span className="ru-attack-mark" aria-hidden="true">{STATUS_MARKS[challenge.status]}</span><span className={challenge.title || on ? undefined : "ru-line-clamp-2"}>{challenge.title || challenge.attack_surface}</span><small>{STATUS_LABELS[challenge.status]}</small></button>
          {on && <ChallengePanel key={`${challenge.id}-${challenge.status}-${challenge.answers?.length ?? 0}`} challenge={challenge} answer={drafts[challenge.id] ?? ""} onAnswerChange={(value) => setDrafts((all) => ({ ...all, [challenge.id]: value }))} refs={refDrafts[challenge.id] ?? []} onRefsChange={(value) => setRefDrafts((all) => ({ ...all, [challenge.id]: value }))} citable={citable} onChanged={() => settle(challenge.id)} />}</li>
      })}</ol>
        {!closed && <div className="ru-generate-more"><button className="ru-quiet-button" disabled={generatingChallenge} onClick={() => void generateMoreChallenge()}>{generatingChallenge ? "正在生成更多挑战…" : "生成更多挑战"}</button>{literature && <button className="ru-quiet-button" disabled={litBusy || (!literature.selection && literature.evidence.length === 0)} aria-expanded={literature.selection ? undefined : litOpen} onClick={() => literature.selection ? void literatureAttack(literature.selection) : setLitOpen((v) => !v)}>{litBusy ? "正在用文献发难…" : "用所选文献发难"}</button>}<p className="ru-challenge-note">让 Cui 攻击一个尚未覆盖的角度；新的挑战会进入同一轮审查。</p></div>}
        {!closed && litOpen && literature && !literature.selection && <fieldset className="ru-lit-pick"><legend>这台设备上没有选料草稿：从本问题的待取证材料里勾选要用来发难的几份</legend>{literature.evidence.map((m) => <label key={m.id}><input type="checkbox" checked={litPicked.includes(m.id)} onChange={() => setLitPicked((ids) => ids.includes(m.id) ? ids.filter((id) => id !== m.id) : [...ids, m.id])} /> {m.source_locator ?? m.excerpt}</label>)}<div className="ru-crystal-actions"><button className="ru-quiet-button" onClick={() => { setLitOpen(false); setLitPicked([]) }}>取消</button><button className="ru-ink-button ru-active" disabled={litBusy || litPicked.length === 0} onClick={() => void literatureAttack({ material_ids: litPicked, external_refs: [] })}>{litBusy ? "正在发难…" : "发难"}</button></div></fieldset>}
      </section>}
      {active === "evidence" && <EvidenceSurface round={round} onChanged={() => void load()} />}
      {active === "verdict" && !closed && <VerdictForge round={round} onChanged={() => void load()} />}
      {active === "verdict" && closed && <ReReview round={round} onError={(message) => setError(message)} />}
      {active === "verdict" && round.verdict?.verdict_type === "boundary" && <BoundaryLineage round={round} onError={(message) => setError(message)} />}
    </div>
  </section>
}

// 标题在攻击面那一行（challenge-title-*）；应答草稿（文字 + 引用）由审查面按关保存，切换聚焦不丢
function ChallengePanel({ challenge, answer, onAnswerChange: setAnswer, refs, onRefsChange: setRefs, citable, onChanged }: { challenge: Challenge; answer: string; onAnswerChange: (value: string) => void; refs: string[]; onRefsChange: (value: string[]) => void; citable?: Citable; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [picker, setPicker] = useState(false)
  const [deferOpen, setDeferOpen] = useState(false)
  const [condition, setCondition] = useState("")
  const [withdrawOpen, setWithdrawOpen] = useState(false)
  const [withdrawReason, setWithdrawReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const open = challenge.status === "pending" || challenge.status === "answered"
  const answered = (challenge.answers?.length ?? 0) > 0
  async function saveAnswer() {
    if (!answer.trim() || busy) return
    setBusy(true); setError(null)
    try { await researchUniverse.answerChallenge(challenge.id, command({ answer_text: answer.trim(), provisional_anchor_refs: refs }, challenge.sequence ?? 1)); setAnswer(""); setRefs([]); onChanged() } catch (reason) { setError(reason instanceof Error ? reason.message : "保存答辩失败。") } finally { setBusy(false) }
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
  // 正文 = 攻击面问句(行里只显示短标题时才需要;无标题时行本身展开为全文);为什么问一行;自检方法退到次要
  const reasoning = <>{challenge.title && <p className="ru-reading-copy ru-challenge-question">{challenge.attack_surface}</p>}<p className="ru-challenge-why"><b>为什么问</b>{challenge.why_it_matters}</p><p className="ru-challenge-selfcheck">可以怎样自检：{challenge.self_check_method}</p></>
  if (!open) {
    return <aside className="ru-challenge ru-challenge-closed" aria-labelledby={`challenge-title-${challenge.id}`}>{challenge.status === "deferred" && challenge.defer && <p className="ru-reading-copy">何时重看：{challenge.defer.condition}</p>}{challenge.status === "withdrawn" && challenge.withdraw && <p className="ru-reading-copy">理由：{challenge.withdraw.reason}</p>}{reasoning}</aside>
  }
  const closeForms = () => { setDeferOpen(false); setCondition(""); setWithdrawOpen(false); setWithdrawReason("") }
  const toggleRef = (id: string) => setRefs(refs.includes(id) ? refs.filter((r) => r !== id) : [...refs, id])
  const option = (id: string, label: string, tag?: string) => <button key={id} type="button" role="option" aria-selected={refs.includes(id)} className="ru-cite-opt" onClick={() => toggleRef(id)}><span className="ru-cite-box" aria-hidden="true">{refs.includes(id) ? "✓" : ""}</span><span className="ru-cite-opt-label">{label}</span>{tag && <span className="ru-tag">{tag}</span>}</button>
  return <aside className="ru-challenge" aria-labelledby={`challenge-title-${challenge.id}`}>{reasoning}{challenge.provenance && <p className="ru-provenance">生成依据：{challenge.provenance.basis_refs?.join(" · ") ?? "已记录"} · 不确定性：{challenge.provenance.uncertainty ?? "未说明"}</p>}
    {answered && <div className="ru-answer-log"><p className="ru-kicker">已保存答辩</p>{(challenge.answers ?? []).map((item) => <p className="ru-answer-entry" key={item.version_id}>{item.text}{item.provisional_anchor_refs.length ? <> · 带入未确认上下文 {item.provisional_anchor_refs.map((r) => refLabel(r, citable)).join("、")}</> : null}</p>)}<p className="ru-challenge-note">答辩已保存，挑战仍待裁决。</p></div>}
    <div className="ru-answer-form"><label htmlFor={`answer-${challenge.id}`}>你的应答</label><textarea id={`answer-${challenge.id}`} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="写下你怎么回应这一关。保存应答不等于这一关已被解决。" disabled={busy} /></div>
    {citable && <><div className="ru-cite-row"><button type="button" className="ru-quiet-button" aria-expanded={picker} disabled={busy} onClick={() => setPicker((v) => !v)}>＋ 引用</button>{refs.map((r) => <span key={r} className="ru-cite-chip">{refLabel(r, citable)}<button type="button" aria-label={`移除引用 ${refLabel(r, citable)}`} onClick={() => toggleRef(r)}>×</button></span>)}</div>
      {picker && <div className="ru-cite-picker" role="listbox" aria-multiselectable="true" aria-label="引用本问题的证据材料与探索稿锚点"><p>本问题的证据材料</p>{citable.materials.length ? citable.materials.map((m) => option(m.id, [m.source_locator, clip(m.excerpt, 30)].filter(Boolean).join(" · "), m.content_scope === "abstract" ? "摘要" : undefined)) : <p className="ru-cite-empty">还没有。可从左栏已选文献「带进证据台」。</p>}<p>探索稿锚点</p>{citable.anchors.length ? citable.anchors.map((a) => option(a.id, `「${clip(a.selected_text, 60)}」`)) : <p className="ru-cite-empty">还没有。在「工具 · 探索稿」里保留片段即成锚点。</p>}</div>}
      <p className="ru-cite-note">引用的内容在裁决账本里记为「带入但未确认」，不等于取证事实。</p></>}
    {deferOpen && <div className="ru-inline-action"><label htmlFor={`defer-condition-${challenge.id}`}>何时重看</label><input id={`defer-condition-${challenge.id}`} value={condition} onChange={(e) => setCondition(e.target.value)} placeholder="例如：读到 Paper A 之后" /><div className="ru-inline-buttons"><button className="ru-quiet-button" disabled={busy || !condition.trim()} onClick={() => void defer()}>确认暂缓</button><button className="ru-quiet-button" onClick={closeForms}>取消</button></div></div>}
    {withdrawOpen && <div className="ru-inline-action"><label htmlFor={`withdraw-reason-${challenge.id}`}>撤回理由</label><input id={`withdraw-reason-${challenge.id}`} value={withdrawReason} onChange={(e) => setWithdrawReason(e.target.value)} placeholder="为什么撤回这条挑战" /><div className="ru-inline-buttons"><button className="ru-quiet-button" disabled={busy || !withdrawReason.trim()} onClick={() => void withdraw()}>确认撤回</button><button className="ru-quiet-button" onClick={closeForms}>取消</button></div></div>}
    <div className="ru-challenge-actions"><button className="ru-quiet-button" aria-pressed={deferOpen} onClick={() => { closeForms(); setDeferOpen(true) }}>暂缓</button><button className="ru-quiet-button" aria-pressed={withdrawOpen} onClick={() => { closeForms(); setWithdrawOpen(true) }}>撤回</button><button className="ru-ink-button ru-active" disabled={busy || !answer.trim()} onClick={() => void saveAnswer()}>{busy ? "正在保存…" : "保存应答"}</button></div>
    {error && <p className="ru-error" role="alert">{error}</p>}
  </aside>
}

function VerdictForge({ round, onChanged }: { round: ReviewRound; onChanged: () => void }) {
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
    try { await researchUniverse.confirmVerdict(round.id, command({ verdict_type: verdictType, user_reason: reason.trim(), revival_condition: verdictType === "circumstantial" ? revival.trim() : null }, round.sequence ?? 1)); onChanged() } catch (reasonError) { setError(reasonError instanceof Error ? reasonError.message : "裁决失败。") } finally { setBusy(false) }
  }
  const buckets: { key: "answered" | "deferred" | "pending" | "brought_unconfirmed"; label: string }[] = [
    { key: "answered", label: "已回应" },
    { key: "deferred", label: "暂缓" },
    { key: "pending", label: "仍待回应" },
    { key: "brought_unconfirmed", label: "带入但未确认" },
  ]
  return <section className="ru-verdict" aria-labelledby="verdict-ledger-title"><p className="ru-kicker">本轮审查账本</p><h2 id="verdict-ledger-title">作出本轮裁决</h2><p className="ru-reading-copy">Claim（本轮文本）：{round.claim_snapshot.text}</p><div className="ru-ledger-grid">{buckets.map((bucket) => { const items = ledger?.[bucket.key] ?? []; return <section key={bucket.key}><h3>{bucket.label}</h3>{items.length ? items.map((item) => <p key={item.id} className="ru-ledger-item">{item.title || item.attack_surface}</p>) : <p className="ru-ledger-empty">—</p>}</section> })}</div><p className="ru-challenge-note">这是一项你的判断。Cui 不会替你决定结果。</p><form className="ru-verdict-form" onSubmit={submit}><fieldset><legend>本轮裁决</legend>{VERDICT_OPTIONS.map((option) => <label key={option.type}><input type="radio" name="verdict" checked={verdictType === option.type} onChange={() => setVerdictType(option.type)} /> <span>{option.label}</span>{option.note && <small>{option.note}</small>}</label>)}</fieldset><label htmlFor="verdict-reason">你的理由</label><textarea id="verdict-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="写下这项判断的依据。" required />{verdictType === "circumstantial" && <label htmlFor="verdict-revival">现在先不投入 —— 何时、什么条件下再回来（必填）</label>}{verdictType === "circumstantial" && <input id="verdict-revival" value={revival} onChange={(e) => setRevival(e.target.value)} placeholder="例如：等数据可验证后再重看" required />}{error && <p className="ru-error" role="alert">{error}</p>}<div className="ru-verdict-actions"><button className="ru-ink-button ru-active" disabled={busy || !valid}>{busy ? "正在记录裁决…" : "确认裁决"}</button></div></form></section>
}

function ReReview({ round, onError }: { round: ReviewRound; onError: (message: string) => void }) {
  const { navigate } = useNavigation()
  const [busy, setBusy] = useState(false)
  const claimId = round.claim_snapshot.id
  async function startAgain() {
    if (!claimId || busy) return
    setBusy(true)
    try { const result = await researchUniverse.startReview(claimId, command({}, 0)); navigate(`/workspaces/${round.workspace_id}/rounds/${result.result.review_round_id}`) } catch (reason) { onError(reason instanceof Error ? reason.message : "再次审查失败。") } finally { setBusy(false) }
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
  return <section className="ru-boundary" aria-labelledby="boundary-title"><p className="ru-kicker">边界 · 已记录</p><h2 id="boundary-title">这条 claim 已保留为本轮结论；不会被改写，也不会自动生成替代主张。</h2><p className="ru-reading-copy">理由：{verdict?.user_reason ?? "未说明"}</p><nav className="ru-review-exits" aria-label="边界出口"><button className="ru-ink-button ru-active" disabled={busy} onClick={() => void openNewQuestion()}>{busy ? "正在创建新问题…" : "围绕这条边界开一个新问题"}</button><button className="ru-quiet-button" onClick={() => setDismissed(true)}>暂时停在这里</button></nav></section>
}
