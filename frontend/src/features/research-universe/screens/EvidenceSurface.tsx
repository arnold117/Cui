import { useEffect, useRef, useState, type FormEvent } from "react"
import { command, researchUniverse } from "../api"
import type { EvidenceCandidate, EvidenceRelation, Material, ReviewRound, WorkspaceDesk } from "../types"

const RELATIONS: EvidenceRelation[] = ["supports", "contradicts", "silent", "cannot_assess"]
const RELATION_LABELS: Record<EvidenceRelation, string> = { supports: "支持", contradicts: "反证", silent: "查无", cannot_assess: "无法判断" }
const STATUS_LABELS: Record<EvidenceCandidate["status"], string> = { pending: "待确认", confirmed: "已确认", corrected: "已修正", rejected: "已拒绝", withdrawn: "已撤回" }

export function EvidenceSurface({ round, onChanged }: { round: ReviewRound; onChanged: () => void }) {
  const [desk, setDesk] = useState<WorkspaceDesk | null>(null)
  const [proposeMaterial, setProposeMaterial] = useState("")
  const [proposeRelation, setProposeRelation] = useState<EvidenceRelation>("supports")
  const [proposeUncertainty, setProposeUncertainty] = useState("")
  const [busy, setBusy] = useState(false)
  const [decisionBusy, setDecisionBusy] = useState<string | null>(null)
  const [generatingMaterial, setGeneratingMaterial] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [receipt, setReceipt] = useState<string | null>(null)
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [inline, setInline] = useState<Record<string, "reject" | "withdraw" | "correct" | null>>({})
  const [correctValue, setCorrectValue] = useState<Record<string, EvidenceRelation | "">>({})
  const generation = useRef(0)

  async function loadDesk() {
    const current = ++generation.current
    try { const value = await researchUniverse.desk(round.workspace_id); if (current === generation.current) { setDesk(value); setError(null) } } catch (reason) { if (current === generation.current) setError(reason instanceof Error ? reason.message : "未能读取材料。") }
  }
  useEffect(() => { void loadDesk(); return () => { generation.current++ } }, [round.workspace_id])

  const materials = desk?.materials ?? []
  const candidates = round.evidence_candidates ?? []
  const eligible = materials.filter(m => m.purpose === "evidence")
  const selectedMaterial = eligible.find(m => m.id === proposeMaterial)
  const selectedFailed = selectedMaterial?.parse_status === "failed"

  async function propose(e: FormEvent) {
    e.preventDefault()
    if (busy || !proposeMaterial) return
    if (selectedFailed && proposeRelation === "silent") { setProposeRelation("cannot_assess"); return }
    setBusy(true); setError(null)
    try {
      await researchUniverse.proposeEvidenceCandidate(round.id, command({ material_id: proposeMaterial, relation: proposeRelation, uncertainty: proposeUncertainty.trim() || null }, 0))
      setProposeMaterial(""); setProposeRelation("supports"); setProposeUncertainty("")
      onChanged()
    } catch (reason) { setError(reason instanceof Error ? reason.message : "提出取证候选失败。") } finally { setBusy(false) }
  }

  async function generateEvidence(material: Material) {
    if (generatingMaterial) return
    setGeneratingMaterial(material.id); setError(null)
    try {
      await researchUniverse.generateEvidenceCandidate(round.id, command({ material_id: material.id }, 0))
      onChanged()
    } catch (reason) { setError(reason instanceof Error ? reason.message : "让 Cui 提出取证候选失败。") } finally { setGeneratingMaterial(null) }
  }

  async function decide(candidate: EvidenceCandidate, action: "confirm" | "reject" | "withdraw") {
    if (decisionBusy) return
    setDecisionBusy(candidate.id); setError(null)
    try {
      const reason = reasons[candidate.id]?.trim() || null
      if (action === "confirm") {
        await researchUniverse.confirmEvidence(candidate.id, command({ user_reason: reason }, candidate.sequence ?? 1))
        setReceipt(`已确认的取证事实：${candidate.material_anchor.excerpt} 与 claim 构成 ${RELATION_LABELS[candidate.relation]}`)
      } else if (action === "reject") {
        await researchUniverse.rejectEvidence(candidate.id, command({ user_reason: reason }, candidate.sequence ?? 1))
        setReceipt("已拒绝：这条候选未进入已确认的取证事实。")
      } else {
        await researchUniverse.withdrawEvidence(candidate.id, command({ user_reason: reason }, candidate.sequence ?? 1))
        setReceipt("已撤回这条取证候选。")
      }
      setInline((v) => ({ ...v, [candidate.id]: null }))
      onChanged()
    } catch (reason) { setError(reason instanceof Error ? reason.message : "取证裁决失败。") } finally { setDecisionBusy(null) }
  }

  async function correct(candidate: EvidenceCandidate) {
    if (decisionBusy) return
    const corrected = correctValue[candidate.id]
    if (!corrected || corrected === candidate.relation) return
    setDecisionBusy(candidate.id); setError(null)
    try {
      await researchUniverse.correctEvidence(candidate.id, command({ corrected_relation: corrected, user_reason: reasons[candidate.id]?.trim() || null }, candidate.sequence ?? 1))
      setReceipt(`已确认的取证事实：${candidate.material_anchor.excerpt} 与 claim 构成 ${RELATION_LABELS[corrected]}`)
      setInline((v) => ({ ...v, [candidate.id]: null }))
      onChanged()
    } catch (reason) { setError(reason instanceof Error ? reason.message : "修正关系失败。") } finally { setDecisionBusy(null) }
  }

  function toggleInline(id: string, kind: "reject" | "withdraw" | "correct") { setInline((v) => ({ ...v, [id]: v[id] === kind ? null : kind })) }

  return <section className="ru-evidence" aria-labelledby="evidence-title">
    <p className="ru-kicker">并列证据台 · 取证候选未确认</p>
    <h2 id="evidence-title">这段摘录与当前 claim 的对照</h2>
    {receipt && <p className="ru-receipt" role="status">{receipt}</p>}
    {error && <p className="ru-error" role="alert">{error}</p>}
    <div className="ru-evidence-grid">
      <div className="ru-evidence-materials">
        <p className="ru-kicker">材料</p>
        {materials.length === 0 ? <p className="ru-edge-empty">还没有带入材料。</p> : materials.map((m) => {
          const ineligible = m.purpose === "reference"
          return <article key={m.id} className={`ru-material-card${ineligible ? " ru-material-ineligible" : ""}`}>
            <p className="ru-reading-copy">{m.excerpt}</p>
            <p className="ru-provenance">{m.source_locator ?? "无来源定位"} · {ineligible ? "只作探索参考，不进入候选" : "待取证材料"}{m.parse_status === "failed" ? " · 无法判断" : ""}</p>
            {!ineligible && <div className="ru-material-generate"><button className="ru-quiet-button" disabled={generatingMaterial !== null} onClick={() => void generateEvidence(m)}>{generatingMaterial === m.id ? "Cui 正在取证…" : "让 Cui 提出取证候选"}</button></div>}
          </article>
        })}
      </div>
      <div className="ru-evidence-candidates">
        <p className="ru-kicker">与 Claim 的对照 · 候选</p>
        {candidates.length === 0 ? <p className="ru-edge-empty">尚未提出取证候选。</p> : candidates.map((candidate) => (
          <article key={candidate.id} className={`ru-candidate-card ru-candidate-${candidate.status}`}>
            <p className="ru-kicker">{candidate.status === "pending" ? "Cui 的取证候选（未确认）" : `已${STATUS_LABELS[candidate.status]}`}</p>
            <p className="ru-reading-copy">{candidate.material_anchor.excerpt}</p>
            <p className="ru-provenance">来源：{candidate.material_anchor.source_locator ?? "无"} · 可能：{RELATION_LABELS[candidate.relation]}{candidate.uncertainty ? ` · 不确定性：${candidate.uncertainty}` : ""}</p>
            {candidate.provenance?.generator_kind === "system" && (candidate.rationale || candidate.evidence_highlight) && <div className="ru-generated-analysis">
              {candidate.rationale ? <p><span className="ru-analysis-label">为何</span>{candidate.rationale}</p> : null}
              {candidate.evidence_highlight ? <p><span className="ru-analysis-label">证据高亮</span><mark className="ru-highlight">{candidate.evidence_highlight}</mark></p> : null}
              {candidate.provenance.prompt_version ? <p className="ru-provenance">生成依据：{candidate.provenance.basis_refs?.join(" · ") ?? "已记录"} · {candidate.provenance.prompt_version}</p> : null}
            </div>}
            {candidate.status === "pending" && <div className="ru-candidate-actions">
              <button className="ru-ink-button ru-active" disabled={decisionBusy !== null} onClick={() => void decide(candidate, "confirm")}>{candidate.relation === "contradicts" ? "确认是反证" : candidate.relation === "supports" ? "确认支持" : candidate.relation === "silent" ? "确认查无" : "确认无法判断"}</button>
              <button className="ru-quiet-button" onClick={() => toggleInline(candidate.id, "correct")}>改为…</button>
              {inline[candidate.id] === "correct" && <div className="ru-inline-action">
                <select aria-label={`改为什么（候选 ${candidate.id.slice(0, 8)}）`} value={correctValue[candidate.id] ?? ""} onChange={(e) => setCorrectValue((v) => ({ ...v, [candidate.id]: e.target.value as EvidenceRelation }))}>
                  <option value="">选择改为什么</option>
                  {RELATIONS.filter((r) => r !== candidate.relation).map((r) => <option key={r} value={r}>{RELATION_LABELS[r]}</option>)}
                </select>
                <button className="ru-quiet-button" disabled={decisionBusy !== null || !correctValue[candidate.id]} onClick={() => void correct(candidate)}>确认修正</button>
                <button className="ru-quiet-button" onClick={() => toggleInline(candidate.id, "correct")}>取消</button>
              </div>}
              <button className="ru-quiet-button ru-danger" onClick={() => toggleInline(candidate.id, "reject")}>拒绝（不涉及／误读…）</button>
              {inline[candidate.id] === "reject" && <div className="ru-inline-action">
                <label htmlFor={`reject-reason-${candidate.id}`}>理由（可选）</label>
                <input id={`reject-reason-${candidate.id}`} value={reasons[candidate.id] ?? ""} onChange={(e) => setReasons((v) => ({ ...v, [candidate.id]: e.target.value }))} placeholder="为什么不构成证据" />
                <button className="ru-quiet-button" disabled={decisionBusy !== null} onClick={() => void decide(candidate, "reject")}>确认拒绝</button>
              </div>}
              <button className="ru-quiet-button" onClick={() => toggleInline(candidate.id, "withdraw")}>撤回</button>
              {inline[candidate.id] === "withdraw" && <div className="ru-inline-action">
                <label htmlFor={`withdraw-reason-${candidate.id}`}>理由（可选）</label>
                <input id={`withdraw-reason-${candidate.id}`} value={reasons[candidate.id] ?? ""} onChange={(e) => setReasons((v) => ({ ...v, [candidate.id]: e.target.value }))} placeholder="为什么撤回这条候选" />
                <button className="ru-quiet-button" disabled={decisionBusy !== null} onClick={() => void decide(candidate, "withdraw")}>确认撤回</button>
              </div>}
            </div>}
            {candidate.status !== "pending" && candidate.decision_reason && <p className="ru-provenance">理由：{candidate.decision_reason}</p>}
            {(candidate.status === "confirmed" || candidate.status === "corrected") && <p className="ru-confirmed-flag">已确认 · 构成 {RELATION_LABELS[candidate.relation]}</p>}
          </article>
        ))}
      </div>
    </div>
    <form className="ru-propose-form" onSubmit={propose}>
      <p className="ru-kicker">提出取证候选</p>
      <label htmlFor="propose-material">选择待取证材料</label>
      <select id="propose-material" value={proposeMaterial} onChange={(e) => { const next = e.target.value; setProposeMaterial(next); const nextMaterial = eligible.find((m) => m.id === next); setProposeRelation(nextMaterial?.parse_status === "failed" ? "cannot_assess" : "supports") }}>
        <option value="">选择一份材料…</option>
        {eligible.map((m) => <option key={m.id} value={m.id}>{m.parse_status === "failed" ? "（无法判断）" : ""}{m.excerpt.slice(0, 40)}{m.excerpt.length > 40 ? "…" : ""}</option>)}
      </select>
      <fieldset>
        <legend>可能的关系</legend>
        {RELATIONS.map((rel) => {
          const disabled = rel === "silent" && selectedFailed
          return <label key={rel} className={disabled ? "ru-disabled" : undefined}><input type="radio" name="propose-relation" value={rel} checked={proposeRelation === rel} disabled={disabled} onChange={() => setProposeRelation(rel)} /> {RELATION_LABELS[rel]}{disabled && <small>（解析失败，只能“无法判断”）</small>}</label>
        })}
      </fieldset>
      <label htmlFor="propose-uncertainty">不确定性（可选）</label>
      <input id="propose-uncertainty" value={proposeUncertainty} onChange={(e) => setProposeUncertainty(e.target.value)} placeholder="这段对照有多确定？" />
      <button className="ru-ink-button ru-active" disabled={busy || !proposeMaterial}>{busy ? "正在提出…" : "提出候选"}</button>
    </form>
    {(round.confirmed_facts?.length ?? 0) > 0 && <div className="ru-confirmed-facts"><p className="ru-kicker">已确认的取证事实</p>{(round.confirmed_facts ?? []).map((fact) => <p key={fact.id} className="ru-confirmed-fact">{fact.material_anchor.excerpt} 与 claim 构成 {RELATION_LABELS[fact.relation]}。</p>)}</div>}
  </section>
}
