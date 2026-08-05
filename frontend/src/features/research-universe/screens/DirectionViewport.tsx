import { useEffect, useRef, useState, type FormEvent } from "react"
import { command, researchUniverse } from "../api"
import type { Direction, DirectionChangeType, DirectionStatus } from "../types"
import { useNavigation } from "../../../router"

const REPHRASE_OPTIONS: { type: DirectionChangeType; label: string; note?: string }[] = [
  { type: "clarify", label: "更清楚地重述", note: "把同一方向说得更准" },
  { type: "narrow_or_widen", label: "收窄 / 扩展", note: "调整这一方向的边界" },
  { type: "turning", label: "方向正在转向", note: "承认方向本身在拐弯" },
  { type: "unnamed", label: "暂不命名", note: "旧命题不够，但我不伪造新命题" },
]
const STATUS_OPTIONS: { type: DirectionStatus; label: string }[] = [
  { type: "active", label: "active" },
  { type: "on_hold", label: "on hold" },
  { type: "retired", label: "retired" },
]
const POSITION_LABELS: Record<string, string> = { exploring: "探索中", paused: "已暂停", concluded: "已结晶", branched: "已分支", absorbed: "已并入" }

export function DirectionViewport({ directionId, rephraseIntent = false, sourceConclusionRef }: { directionId: string; rephraseIntent?: boolean; sourceConclusionRef?: string }) {
  const { navigate } = useNavigation()
  const [direction, setDirection] = useState<Direction | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rephrasing, setRephrasing] = useState(rephraseIntent)
  const [newProposition, setNewProposition] = useState("")
  const [changeType, setChangeType] = useState<DirectionChangeType | null>(null)
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [statusOpen, setStatusOpen] = useState(false)
  const [newStatus, setNewStatus] = useState<DirectionStatus>("active")
  const [statusBusy, setStatusBusy] = useState(false)
  const [newExperiment, setNewExperiment] = useState(false)
  const [experimentQuestion, setExperimentQuestion] = useState("")
  const [experimentBusy, setExperimentBusy] = useState(false)
  const generation = useRef(0)

  async function load() {
    const current = ++generation.current
    try { const value = await researchUniverse.direction(directionId); if (current === generation.current) { setError(null); setDirection(value) } } catch (e) { if (current === generation.current) setError(e instanceof Error ? e.message : "未能读取方向。") }
  }
  useEffect(() => { setRephrasing(rephraseIntent); void load(); return () => { generation.current++ } }, [directionId, rephraseIntent])

  async function submitRephrase(e: FormEvent) {
    e.preventDefault()
    if (!direction || busy || !changeType || !reason.trim() || (changeType !== "unnamed" && !newProposition.trim())) return
    setBusy(true); setError(null)
    try {
      const result = await researchUniverse.rephraseDirection(direction.id, command({ new_proposition: changeType === "unnamed" ? null : newProposition.trim(), change_type: changeType, user_reason: reason.trim(), source_conclusion_ref: sourceConclusionRef ?? null }, direction.sequence ?? 1))
      const fresh = result.fragment as Direction | undefined
      if (fresh?.id) setDirection(fresh)
      setRephrasing(false); setNewProposition(""); setChangeType(null); setReason("")
      void load()
    } catch (reasonError) { setError(reasonError instanceof Error ? reasonError.message : "重述失败。") } finally { setBusy(false) }
  }

  async function declareStatus() {
    if (!direction || statusBusy) return
    setStatusBusy(true); setError(null)
    try {
      await researchUniverse.declareDirectionStatus(direction.id, command({ status: newStatus, user_reason: "用户声明" }, direction.sequence ?? 1))
      setStatusOpen(false); void load()
    } catch (reasonError) { setError(reasonError instanceof Error ? reasonError.message : "状态声明失败。") } finally { setStatusBusy(false) }
  }

  async function startExperiment() {
    if (experimentBusy || !experimentQuestion.trim()) return
    setExperimentBusy(true); setError(null)
    try {
      const active = await researchUniverse.active()
      const created = await researchUniverse.createWorkspace(active.id, command({ question: experimentQuestion.trim() }, 0))
      navigate(`/workspaces/${created.result.workspace_id}`)
    } catch (reasonError) { setError(reasonError instanceof Error ? reasonError.message : "开启新问题失败。") } finally { setExperimentBusy(false) }
  }

  if (error && !direction) return <section className="ru-state" role="alert"><p>未能打开方向：{error}</p><button className="ru-ink-button" onClick={() => void load()}>重试</button></section>
  if (!direction) return <section className="ru-state" aria-live="polite">正在读取方向…</section>

  const proposition = direction.proposition.text ?? "暂不命名"
  return <section className="ru-direction" aria-labelledby="direction-title"><p className="ru-kicker">方向沉浸式面</p><h1 id="direction-title">我正在追什么</h1><blockquote className="ru-direction-proposition">{proposition}</blockquote><p className="ru-provenance">{direction.status} · 命题版本 {direction.proposition.version_id.slice(0, 8)}</p><div className="ru-crystal-actions"><button className="ru-quiet-button" onClick={() => setRephrasing(v => !v)}>重述</button><button className="ru-quiet-button" onClick={() => { setStatusOpen(v => !v); if (!statusOpen) setNewStatus(direction.status) }}>声明状态</button>{statusOpen && <span className="ru-inline-action">{STATUS_OPTIONS.map(opt => <label key={opt.type}><input type="radio" name="direction-status" checked={newStatus === opt.type} onChange={() => setNewStatus(opt.type)} /> {opt.label}</label>)}{statusBusy ? <span>正在声明…</span> : <button className="ru-quiet-button" onClick={() => void declareStatus()}>确认</button>}</span>}</div>
    {rephrasing && <RephraseDesk direction={direction} newProposition={newProposition} setNewProposition={setNewProposition} changeType={changeType} setChangeType={setChangeType} reason={reason} setReason={setReason} busy={busy} onSubmit={submitRephrase} onCancel={() => setRephrasing(false)} sourceConclusionRef={sourceConclusionRef} />}
    {error && <p className="ru-error" role="alert">{error}</p>}
    <section className="ru-direction-workspaces" aria-labelledby="direction-workspaces-title"><p className="ru-kicker">这条方向正在被这些问题试验</p><h2 id="direction-workspaces-title">问题试验场</h2>{direction.attached_workspaces.length ? <div className="ru-home-facts">{direction.attached_workspaces.map(ws => <a key={ws.link_id} href={`/workspaces/${ws.workspace_id}`}><span>{POSITION_LABELS[ws.position] ?? ws.position}{ws.question ? ` · ${ws.question}` : ""}</span><strong>{ws.pending_fact_count > 0 ? `待回应 ${ws.pending_fact_count}` : "没有待回应事实"}</strong></a>)}</div> : <p className="ru-reading-copy">还没有工作区在试验这条方向。</p>}<div className="ru-new-experiment"><button className="ru-quiet-button" onClick={() => setNewExperiment(v => !v)}>{newExperiment ? "取消" : "新问题试验"}</button>{newExperiment && <div className="ru-inline-action"><label htmlFor="experiment-question">写下一个此刻值得试验的问题（Cui 不会替你安排要开什么）</label><textarea id="experiment-question" className="ru-conclusion-text" value={experimentQuestion} onChange={(e) => setExperimentQuestion(e.target.value)} placeholder="你此刻想探索的问题……" /><button className="ru-ink-button ru-active" disabled={experimentBusy || !experimentQuestion.trim()} onClick={() => void startExperiment()}>{experimentBusy ? "正在创建…" : "开始新问题试验"}</button></div>}</div></section>
    <section className="ru-direction-crystallizations" aria-labelledby="direction-crystallizations-title"><p className="ru-kicker">已确认的结晶</p><h2 id="direction-crystallizations-title">结晶</h2>{direction.crystallizations.length ? <div className="ru-materials-list">{direction.crystallizations.map(c => <article key={c.crystallization_id} className="ru-material-card"><p className="ru-reading-copy">{c.conclusion_text}</p><p className="ru-provenance">来自工作区 {c.workspace_id.slice(0, 8)} · {c.conclusion_type}</p></article>)}</div> : <p className="ru-reading-copy">这条方向还没有结晶。</p>}</section>
    <nav className="ru-review-exits" aria-label="方向出口"><a className="ru-ink-button" href="/">回研究宇宙</a></nav></section>
}

function RephraseDesk({ direction, newProposition, setNewProposition, changeType, setChangeType, reason, setReason, busy, onSubmit, onCancel, sourceConclusionRef }: {
  direction: Direction; newProposition: string; setNewProposition: (v: string) => void; changeType: DirectionChangeType | null; setChangeType: (v: DirectionChangeType) => void; reason: string; setReason: (v: string) => void; busy: boolean; onSubmit: (e: FormEvent) => void; onCancel: () => void; sourceConclusionRef?: string
}) {
  const valid = Boolean(changeType) && reason.trim().length > 0 && (changeType === "unnamed" || newProposition.trim().length > 0)
  return <section className="ru-rephrase" aria-labelledby="rephrase-title"><p className="ru-kicker">方向命题重述台</p><h2 id="rephrase-title">现在我想追什么</h2><p className="ru-reading-copy">此前我在追：{direction.proposition.text ?? "暂不命名"}{sourceConclusionRef ? ` · 由一次结晶引入（${sourceConclusionRef.slice(0, 8)}）` : ""}</p><form className="ru-rephrase-form" onSubmit={onSubmit}><label htmlFor="new-proposition">现在我想追</label><textarea id="new-proposition" className="ru-conclusion-text" value={newProposition} onChange={(e) => setNewProposition(e.target.value)} placeholder={changeType === "unnamed" ? "暂不命名：不伪造新命题" : "亲写新命题……"} required={changeType !== "unnamed"} disabled={changeType === "unnamed"} /><fieldset className="ru-conclusion-types"><legend>这次变化是</legend>{REPHRASE_OPTIONS.map(opt => <label key={opt.type}><input type="radio" name="change-type" checked={changeType === opt.type} onChange={() => setChangeType(opt.type)} /> <span>{opt.label}</span>{opt.note && <small>{opt.note}</small>}</label>)}</fieldset><label htmlFor="rephrase-reason">为什么现在要这样改</label><input id="rephrase-reason" className="ru-revival-input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="写下理由" required /><div className="ru-crystal-actions"><button className="ru-quiet-button" type="button" onClick={onCancel}>取消</button><button className="ru-ink-button ru-active" disabled={busy || !valid}>{busy ? "正在保存…" : "确认新命题"}</button></div></form></section>
}
