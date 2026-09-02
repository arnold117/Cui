import { useEffect, useState } from "react"
import { command, researchUniverse } from "../api"
import type { DialogueCandidate, GapDraftFields } from "../types"

type SavedState = {
  candidates: DialogueCandidate[]
  selected: string[]  // locators of chosen literature
  summary?: string
  claimText: string
  roundId?: string
  draft?: GapDraftFields
  confirmedGapIds: string[]
  relatedWork?: string
  searchQuery: string
}

const EMPTY: SavedState = { candidates: [], selected: [], claimText: "", confirmedGapIds: [], searchQuery: "" }

function storageKey(workspaceId: string) { return `cui-dialogue-${workspaceId}` }

function loadState(workspaceId: string): SavedState {
  try {
    const raw = sessionStorage.getItem(storageKey(workspaceId))
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : { ...EMPTY }
  } catch {
    return { ...EMPTY }
  }
}

/** slice1 第二刀 L2 — 文献探讨模式页(wedge demo 旅程)。 */
export function DialogueDesk({ workspaceId }: { workspaceId: string }) {
  const [question, setQuestion] = useState("")
  const [state, setState] = useState<SavedState>(() => loadState(workspaceId))
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let live = true
    researchUniverse.desk(workspaceId)
      .then((desk) => { if (live) setQuestion(desk.question.text) })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "读取工作区失败") })
    return () => { live = false }
  }, [workspaceId])

  useEffect(() => {
    sessionStorage.setItem(storageKey(workspaceId), JSON.stringify(state))
  }, [workspaceId, state])

  function patch(partial: Partial<SavedState>) { setState((prev) => ({ ...prev, ...partial })) }

  async function runSearch() {
    if (busy) return
    setBusy(true); setError(undefined)
    try {
      const result = await researchUniverse.literatureSearch(workspaceId, { question, query: searchQuery || undefined })
      patch({ candidates: result.candidates, selected: [], searchQuery: result.query })
    } catch (e) { setError(e instanceof Error ? e.message : "检索失败") } finally { setBusy(false) }
  }

  function toggle(locator: string) {
    const has = state.selected.includes(locator)
    patch({ selected: has ? state.selected.filter((l) => l !== locator) : [...state.selected, locator].slice(-6) })
  }

  const chosen: DialogueCandidate[] = state.candidates.filter((c) => state.selected.includes(c.locator))

  async function summarize() {
    if (busy || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      const result = await researchUniverse.landscapeSummary(workspaceId, chosen.map((c) => c.material_id))
      patch({ summary: result.text })
    } catch (e) { setError(e instanceof Error ? e.message : "梳理失败") } finally { setBusy(false) }
  }

  async function openReview() {
    if (busy || !state.claimText.trim()) return
    setBusy(true); setError(undefined)
    try {
      const made = await researchUniverse.createClaim(workspaceId, command({ text: state.claimText.trim() }, 0))
      const review = await researchUniverse.startReview(made.result.claim_id!, command({}, 0))
      patch({ roundId: review.result.review_round_id })
    } catch (e) { setError(e instanceof Error ? e.message : "开审查轮失败") } finally { setBusy(false) }
  }

  async function literatureAttack() {
    if (busy || !state.roundId || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      await researchUniverse.literatureChallenge(state.roundId, command({ material_ids: chosen.map((c) => c.material_id) }, 0))
    } catch (e) { setError(e instanceof Error ? e.message : "文献发难失败") } finally { setBusy(false) }
  }

  async function draftGap() {
    if (busy || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      const draft = await researchUniverse.gapDraft(workspaceId, chosen.map((c) => c.material_id))
      patch({ draft })
    } catch (e) { setError(e instanceof Error ? e.message : "起草失败") } finally { setBusy(false) }
  }

  async function proposeGap() {
    if (busy || !state.draft) return
    const coverage = state.draft.coverage_statement.trim()
    const invitation = state.draft.counterexample_invitation.trim()
    if (coverage.length < 10 || !invitation) return
    setBusy(true); setError(undefined)
    try {
      const proposed = await researchUniverse.proposeGapCandidate(workspaceId, command({
        coverage_statement: coverage,
        search_query: state.draft.search_query.trim() || state.searchQuery || "(未检索,手工登记)",
        search_scope: "active",
        matched_locators: state.selected,
        searched_at: new Date().toISOString().slice(0, 10),
        counterexample_invitation: invitation,
      }, 0))
      const gapId = proposed.result.gap_candidate_id
      await researchUniverse.confirmGapCandidate(gapId, command({ user_reason: "人审确认" }, 1))
      patch({ draft: undefined, confirmedGapIds: [...state.confirmedGapIds, gapId] })
    } catch (e) { setError(e instanceof Error ? e.message : "登记 gap 失败") } finally { setBusy(false) }
  }

  async function draftRelatedWork() {
    if (busy || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      const result = await researchUniverse.relatedWorkDraft(workspaceId, chosen.map((c) => c.material_id), state.confirmedGapIds)
      patch({ relatedWork: result.text })
    } catch (e) { setError(e instanceof Error ? e.message : "草稿失败") } finally { setBusy(false) }
  }

  async function copyDraft() {
    if (!state.relatedWork) return
    try { await navigator.clipboard.writeText(state.relatedWork); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { setError("复制失败") }
  }

  function downloadDraft() {
    if (!state.relatedWork) return
    const blob = new Blob([state.relatedWork], { type: "text/markdown" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `related-work-${workspaceId}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const selectedLocators = state.selected

  return <section className="ru-dialogue" aria-labelledby="dialogue-title">
    <p className="ru-kicker">文献探讨 · 问题工作区</p>
    <h1 id="dialogue-title">{question || "正在展开问题…"}</h1>
    {error && <p className="ru-error" role="alert">{error}</p>}
    <p className="ru-challenge-note">旅程:检索选料 → 现状梳理 → 固化 claim 进审查轮 → 文献发难 → gap → related-work 草稿。中间的对话不入轨迹;只有裁决/确认/gap 会留下。</p>

    <div className="ru-dialogue-step">
      <h2>① 让 Cui 从语料里找候选文献</h2>
      <div><input aria-label="检索词(可选)" className="ru-revival-input" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="检索词;留空则由 Cui 按问题检索" /><button className="ru-ink-button ru-active" disabled={busy} onClick={() => void runSearch()}>{busy ? "工作中…" : "让 Cui 找文献"}</button></div>
      {state.candidates.length > 0 && <ul className="ru-landscape-list">
        {state.candidates.map((c) => <li key={c.locator} className="ru-landscape-item">
          <button className={selectedLocators.includes(c.locator) ? "ru-ink-button" : "ru-quiet-button"} onClick={() => toggle(c.locator)}>{selectedLocators.includes(c.locator) ? "已选" : "选取"}</button>
          <strong>{c.title}</strong><span className="ru-provenance">{c.locator}</span><span>{c.reason}</span>
        </li>)}
      </ul>}
      <p className="ru-provenance">已选 {state.selected.length} 篇(建议 3–5 篇)</p>
    </div>

    <div className="ru-dialogue-step">
      <h2>② 让 Cui 梳理现状(这几篇覆盖了什么 / 没覆盖什么)</h2>
      <button className="ru-quiet-button" disabled={busy || state.selected.length === 0} onClick={() => void summarize()}>梳理现状</button>
      {state.summary && <pre className="ru-dialogue-pre">{state.summary}</pre>}
    </div>

    <div className="ru-dialogue-step">
      <h2>③ 固化你的 claim,进审查轮</h2>
      <textarea aria-label="claim" className="ru-conclusion-text" value={state.claimText} onChange={(e) => patch({ claimText: e.target.value })} placeholder="读了这些之后,你究竟要断言什么?" />
      <button className="ru-ink-button ru-active" disabled={busy || !state.claimText.trim()} onClick={() => void openReview()}>固化 claim 并开审查轮</button>
      {state.roundId && <p className="ru-provenance">审查轮已开:<a href={`/review-rounds/${state.roundId}`}>去审查轮回应与裁决</a></p>}
      {state.roundId && <button className="ru-quiet-button" disabled={busy || state.selected.length === 0} onClick={() => void literatureAttack()}>用所选文献发难(追加一条文献挑战)</button>}
    </div>

    <div className="ru-dialogue-step">
      <h2>④ 让 Cui 起草 gap 候选(仍由你署名提交)</h2>
      <button className="ru-quiet-button" disabled={busy || state.selected.length === 0} onClick={() => void draftGap()}>起草 gap</button>
      {state.draft && <div className="ru-material-form">
        <label htmlFor="d-coverage">覆盖范围声明</label>
        <textarea id="d-coverage" className="ru-conclusion-text" value={state.draft.coverage_statement} onChange={(e) => patch({ draft: { ...state.draft!, coverage_statement: e.target.value } })} />
        <label htmlFor="d-invitation">邀请反例</label>
        <input id="d-invitation" className="ru-revival-input" value={state.draft.counterexample_invitation} onChange={(e) => patch({ draft: { ...state.draft!, counterexample_invitation: e.target.value } })} />
        <button className="ru-ink-button ru-active" disabled={busy} onClick={() => void proposeGap()}>提交并确认这个 gap</button>
      </div>}
      {state.confirmedGapIds.length > 0 && <p className="ru-provenance">已确认 gap ×{state.confirmedGapIds.length}</p>}
    </div>

    <div className="ru-dialogue-step">
      <h2>⑤ 生成 related-work 草稿(导出形式,不入轨迹)</h2>
      <button className="ru-quiet-button" disabled={busy || state.selected.length === 0} onClick={() => void draftRelatedWork()}>生成草稿</button>
      {state.relatedWork && <div><pre className="ru-dialogue-pre">{state.relatedWork}</pre>
        <div className="ru-crystal-actions"><button className="ru-quiet-button" onClick={() => void copyDraft()}>{copied ? "已复制" : "复制"}</button><button className="ru-quiet-button" onClick={downloadDraft}>下载 .md</button></div></div>}
    </div>
  </section>
}
