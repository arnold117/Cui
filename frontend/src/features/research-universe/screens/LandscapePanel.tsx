import { useState } from "react"
import { command, researchUniverse } from "../api"
import type { CorpusSearchHit, GapCandidate, WorkspaceLandscape } from "../types"

const STATUS_LABELS: Record<GapCandidate["status"], string> = {
  pending: "待你裁决",
  confirmed: "已确认 gap",
  corrected: "已修订",
  rejected: "已拒绝",
  withdrawn: "已撤回",
}
const VERDICT_LABELS: Record<string, string> = {
  survived: "存活", circumstantial: "有条件存活", refuted: "已证伪", not_worth: "不值一探", boundary: "划界", open: "未裁决",
}

/** slice1 S1.4 — 现状图景与 gap 候选台(工作区级,prop 驱动,读数据来自 desk 响应)。 */
export function LandscapePanel({ landscape, onChanged }: { landscape: WorkspaceLandscape; onChanged: () => void }) {
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [coverage, setCoverage] = useState("")
  const [invitation, setInvitation] = useState("")
  const [query, setQuery] = useState("")
  const [hits, setHits] = useState<CorpusSearchHit[]>([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState<string[]>([])

  async function runSearch() {
    if (!query.trim() || searching) return
    setSearching(true)
    setError(undefined)
    try {
      const result = await researchUniverse.corpusSearch(query.trim(), { group: "active", limit: 10 })
      setHits(result.results)
      setSelected([])
    } catch (e) {
      setError(e instanceof Error ? e.message : "语料检索失败")
    } finally {
      setSearching(false)
    }
  }

  async function propose() {
    if (busy || coverage.trim().length < 10 || !invitation.trim()) return
    setBusy(true)
    setError(undefined)
    try {
      await researchUniverse.proposeGapCandidate(landscape.workspace_id, command({
        coverage_statement: coverage.trim(),
        search_query: query.trim() || "(未检索,手工登记)",
        search_scope: "active",
        matched_locators: selected,
        searched_at: new Date().toISOString().slice(0, 10),
        counterexample_invitation: invitation.trim(),
      }, 0))
      setOpen(false); setCoverage(""); setInvitation(""); setQuery(""); setHits([]); setSelected([])
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交 gap 失败")
    } finally {
      setBusy(false)
    }
  }

  async function decide(gap: GapCandidate, action: "confirm" | "reject") {
    if (busy) return
    setBusy(true)
    setError(undefined)
    try {
      if (action === "confirm") {
        await researchUniverse.confirmGapCandidate(gap.id, command({ user_reason: "人审确认" }, gap.sequence ?? 1))
      } else {
        await researchUniverse.rejectGapCandidate(gap.id, command({ user_reason: "人审拒绝" }, gap.sequence ?? 1))
      }
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : "裁决失败")
    } finally {
      setBusy(false)
    }
  }

  const validProposal = coverage.trim().length >= 10 && invitation.trim().length > 0

  return <section className="ru-landscape" aria-labelledby="landscape-title">
    <p className="ru-kicker">现状图景与 gap</p>
    <h2 id="landscape-title">这一问,现状是什么、缺口在哪</h2>
    {error && <p className="ru-error" role="alert">{error}</p>}
    <div className="ru-landscape-readout">
      <p className="ru-challenge-note">存活主张 {landscape.alive_claims.length} · 已确认取证 {landscape.confirmed_facts.length} · gap 候选 {landscape.gaps.length}。图景只读;要做判断的是你。</p>
      {(landscape.alive_claims.length > 0 || landscape.confirmed_facts.length > 0) && <ul className="ru-landscape-list">
        {landscape.alive_claims.map((c) => <li key={c.id} className="ru-landscape-item"><strong>{c.text}</strong><span className="ru-provenance">裁决:{VERDICT_LABELS[landscape.claim_verdicts[c.id] ?? "open"] ?? landscape.claim_verdicts[c.id]}</span></li>)}
        {landscape.confirmed_facts.map((f) => <li key={f.candidate_id} className="ru-landscape-item"><span>已确认取证 · {f.relation}</span><strong>{f.claim_text}</strong><span className="ru-provenance">{f.material_locator ?? "无定位"}</span></li>)}
      </ul>}
      {landscape.alive_claims.length === 0 && landscape.confirmed_facts.length === 0 && <p className="ru-edge-empty">还没有可引用的现状;先走通 claim 与取证,或直接登记一个 gap。</p>}
    </div>
    <div className="ru-gap-list">
      {landscape.gaps.length === 0 && !open && <p className="ru-edge-empty">尚无 gap 候选。</p>}
      {landscape.gaps.map((gap) => <article key={gap.id} className="ru-material-card">
        <p className="ru-provenance">gap 候选 · {STATUS_LABELS[gap.status]}{gap.decision_reason ? ` · ${gap.decision_reason}` : ""}</p>
        <p className="ru-reading-copy"><strong>覆盖范围:</strong>{gap.coverage_statement}</p>
        <p className="ru-reading-copy"><strong>邀请反例:</strong>{gap.counterexample_invitation}</p>
        <p className="ru-provenance">检索:{gap.search_record.query}{gap.search_record.matched_locators.length > 0 ? ` · 命中 ${gap.search_record.matched_locators.length} 篇` : ""}{gap.search_record.searched_at ? ` · ${gap.search_record.searched_at}` : ""}</p>
        {gap.status === "pending" && <div className="ru-crystal-actions"><button className="ru-quiet-button" disabled={busy} onClick={() => void decide(gap, "reject")}>拒绝</button><button className="ru-ink-button ru-active" disabled={busy} onClick={() => void decide(gap, "confirm")}>确认这个 gap</button></div>}
      </article>)}
    </div>
    {!open && <button className="ru-quiet-button" onClick={() => setOpen(true)}>登记一个 gap 候选</button>}
    {open && <div className="ru-material-form">
      <p className="ru-challenge-note">gap 形状(S20):覆盖范围声明 + 可复现检索记录 + 反例邀请。提出的是缺口,不是"所以你应该做 Y"。</p>
      <label htmlFor="gap-coverage">覆盖范围声明(哪些已被覆盖、缺口在哪)</label>
      <textarea id="gap-coverage" className="ru-conclusion-text" value={coverage} onChange={(e) => setCoverage(e.target.value)} placeholder="现有文献覆盖了……但没有覆盖……" required />
      <label htmlFor="gap-invitation">邀请反例</label>
      <input id="gap-invitation" className="ru-revival-input" value={invitation} onChange={(e) => setInvitation(e.target.value)} placeholder="如果你知道反例,请指出——" required />
      <div className="ru-gap-search">
        <label htmlFor="gap-search-query">语料检索(active,供检索记录)</label>
        <div><input id="gap-search-query" className="ru-revival-input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="检索词…" /><button className="ru-quiet-button" disabled={searching || !query.trim()} onClick={() => void runSearch()}>{searching ? "检索中…" : "检索语料"}</button></div>
        {hits.length > 0 && <ul className="ru-landscape-list">
          {hits.map((hit) => <li key={hit.material_id} className="ru-landscape-item">
            <button className={selected.includes(hit.source_locator) ? "ru-ink-button" : "ru-quiet-button"} onClick={() => setSelected((prev) => prev.includes(hit.source_locator) ? prev.filter((x) => x !== hit.source_locator) : [...prev, hit.source_locator])}>{selected.includes(hit.source_locator) ? "已选" : "选取"}</button>
            <strong>{hit.title}</strong><span className="ru-provenance">{hit.source_locator}</span>
          </li>)}
        </ul>}
      </div>
      <div className="ru-crystal-actions"><button className="ru-quiet-button" onClick={() => setOpen(false)}>取消</button><button className="ru-ink-button ru-active" disabled={busy || !validProposal} onClick={() => void propose()}>{busy ? "正在登记…" : "提出 gap 候选"}</button></div>
    </div>}
  </section>
}
