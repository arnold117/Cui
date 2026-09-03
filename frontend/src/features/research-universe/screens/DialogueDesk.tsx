import { useEffect, useState } from "react"
import { command, researchUniverse } from "../api"
import type { DialogueCandidate, GapDraftFields } from "../types"

type SavedState = {
  hypothesesText: string
  keywordsText: string
  selectedKeywords: string[]
  fresh: boolean
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

const EMPTY: SavedState = { hypothesesText: "", keywordsText: "", selectedKeywords: [], fresh: true, candidates: [], selected: [], claimText: "", confirmedGapIds: [], searchQuery: "" }

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
  const [searchedEmpty, setSearchedEmpty] = useState(false)
  const parsedKeywords = state.keywordsText.split(/[;；]/).map((k) => k.trim()).filter(Boolean)
  const uniqueKeywords = [...new Set(parsedKeywords)]
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let live = true
    researchUniverse.desk(workspaceId)
      .then((desk) => {
        if (!live) return
        setQuestion(desk.question.text)
        const fresh = (desk.claims?.length ?? 0) === 0 && (desk.confirmed_facts?.length ?? 0) === 0 && (desk.materials?.length ?? 0) === 0 && ((desk.landscape?.gaps?.length ?? 0) === 0)
        setState((prev) => ({ ...prev, fresh }))
      })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "读取工作区失败") })
    return () => { live = false }
  }, [workspaceId])

  useEffect(() => {
    sessionStorage.setItem(storageKey(workspaceId), JSON.stringify(state))
  }, [workspaceId, state])

  function patch(partial: Partial<SavedState>) { setState((prev) => ({ ...prev, ...partial })) }

  async function runSearch(queryOverride?: string | null) {
    if (busy) return
    const q = queryOverride !== undefined ? queryOverride : (state.selectedKeywords.length > 0 ? state.selectedKeywords.join(" ") : undefined)
    setBusy(true); setError(undefined); setSearchedEmpty(false)
    try {
      const result = await researchUniverse.literatureSearch(workspaceId, { question, query: q || undefined })
      setSearchedEmpty(result.candidates.length === 0)
      patch({ candidates: result.candidates, selected: [], searchQuery: result.query })
    } catch (e) { setError(e instanceof Error ? e.message : "检索失败") } finally { setBusy(false) }
  }

  function toggleKeyword(keyword: string) {
    const has = state.selectedKeywords.includes(keyword)
    patch({ selectedKeywords: has ? state.selectedKeywords.filter((k) => k !== keyword) : [...state.selectedKeywords, keyword] })
  }

  // selecting keywords (or editing the keyword text) auto-triggers one combined search
  useEffect(() => {
    const selection = state.selectedKeywords.join(" ")
    if (!selection) return
    const timer = window.setTimeout(() => { void runSearch(selection) }, 500)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.selectedKeywords.join(" ")])

  async function runOrientation() {
    if (busy) return
    setBusy(true); setError(undefined)
    try {
      const result = await researchUniverse.orientation(workspaceId, question)
      patch({ hypothesesText: result.hypotheses.join("\n"), keywordsText: result.keywords.join("; "), selectedKeywords: [] })
    } catch (e) { setError(e instanceof Error ? e.message : "出发点准备失败") } finally { setBusy(false) }
  }

  function editKeywordsText(value: string) {
    const kept = state.selectedKeywords.filter((k) => value.includes(k))
    patch({ keywordsText: value, selectedKeywords: kept })
  }

  function toggle(locator: string) {
    const has = state.selected.includes(locator)
    patch({ selected: has ? state.selected.filter((l) => l !== locator) : [...state.selected, locator].slice(-6) })
  }

  const chosen: DialogueCandidate[] = state.candidates.filter((c) => state.selected.includes(c.locator))
  const corpusIds = chosen.filter((c) => c.material_id).map((c) => c.material_id as string)
  const externalRefs = chosen.filter((c) => !c.material_id).map((c) => ({ locator: c.locator, excerpt: c.excerpt ?? c.title, url: c.url ?? null }))

  async function summarize() {
    if (busy || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      const result = await researchUniverse.landscapeSummary(workspaceId, corpusIds, externalRefs)
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
      await researchUniverse.literatureChallenge(state.roundId, command({ material_ids: corpusIds, external_refs: externalRefs }, 0))
    } catch (e) { setError(e instanceof Error ? e.message : "文献发难失败") } finally { setBusy(false) }
  }

  async function draftGap() {
    if (busy || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      const draft = await researchUniverse.gapDraft(workspaceId, corpusIds, externalRefs)
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
      const result = await researchUniverse.relatedWorkDraft(workspaceId, corpusIds, state.confirmedGapIds, externalRefs)
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

    return <section className="ru-dialogue" aria-labelledby="dialogue-title">
    <p className="ru-kicker">文献探讨 · 问题工作区</p>
    <h1 id="dialogue-title">{question || "正在展开问题…"}</h1>
    <p className="ru-provenance"><a href={`/workspaces/${workspaceId}`}>← 回到问题工作区</a></p>
    {error && <p className="ru-error" role="alert">{error}</p>}
    <p className="ru-challenge-note">旅程:检索选料 → 现状梳理 → 固化 claim 进审查轮 → 文献发难 → gap → related-work 草稿。中间的对话不入轨迹;只有裁决/确认/gap 会留下。</p>

    <p className="ru-kicker">正向段 · 先把支持面建起来(会话过程,不入轨迹;假设与关键词你都可以改)</p>
    <div className="ru-dialogue-step">
      <h2>① 出发点:候选假设(可改可删可加,仍是你的判断)</h2>
      {state.fresh && !state.hypothesesText.trim() && state.candidates.length === 0 && <div>
        <p className="ru-challenge-note">这是一个全新问题:先找文献建立支持面,再谈对抗——先让 Cui 起草候选假设与关键词,然后你改。</p>
        <button className="ru-ink-button ru-active" disabled={busy} onClick={() => void runOrientation()}>{busy ? "思考中…" : "让 Cui 起草假设与关键词"}</button>
      </div>}
      {state.hypothesesText.trim() && <div className="ru-material-form">
        <label htmlFor="hypotheses-edit">候选假设(每行一个;由 Cui 起草,你可改写/增删)</label>
        <textarea id="hypotheses-edit" className="ru-conclusion-text" rows={Math.min(8, state.hypothesesText.split("\n").length + 1)} value={state.hypothesesText} onChange={(e) => patch({ hypothesesText: e.target.value })} />
      </div>}
    </div>
    <div className="ru-dialogue-step">
      <h2>② 关键词与检索(选中即自动合并搜一次)</h2>
      <div className="ru-material-form">
        <label htmlFor="keywords-edit">关键词(用 ; 或 ; 分隔;直接改,回车后按新词条勾选)</label>
        <input id="keywords-edit" className="ru-revival-input" value={state.keywordsText} onChange={(e) => editKeywordsText(e.target.value)} placeholder="例:US hegemony; 美国霸权; power transition" />
        {uniqueKeywords.length > 0 && <div className="ru-keyword-chips">
          {uniqueKeywords.map((k) => <button key={k} type="button" className={state.selectedKeywords.includes(k) ? "ru-ink-button ru-active" : "ru-quiet-button"} onClick={() => toggleKeyword(k)}>{state.selectedKeywords.includes(k) ? `✓ ${k}` : k}</button>)}
        </div>}
        <p className="ru-provenance">已勾选 {state.selectedKeywords.length} 个检索词{state.selectedKeywords.length > 0 ? "——已自动合并检索;候选会出现在下方。" : "——勾选任意词条即自动检索(也可点下方按钮手动搜一次)。"}</p>
        <button className="ru-quiet-button" disabled={busy || (uniqueKeywords.length === 0 && state.selectedKeywords.length === 0)} onClick={() => void runSearch(state.selectedKeywords.length > 0 ? state.selectedKeywords.join(" ") : uniqueKeywords.join(" "))}>按当前关键词搜一次</button>
      </div>
      {state.candidates.length > 0 && <ul className="ru-landscape-list">
        {state.candidates.map((c) => <li key={c.locator} className="ru-landscape-item">
          <button className={state.selected.includes(c.locator) ? "ru-ink-button" : "ru-quiet-button"} onClick={() => toggle(c.locator)}>{state.selected.includes(c.locator) ? "已选(待用)" : "待选"}</button>
          <div>
            <strong>{c.title}</strong>
            <p className="ru-provenance">{c.source && c.source !== "corpus" ? `${c.source} · ` : "语料 · "}{c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.locator}</a> : c.locator}</p>
            {c.stance && <p className="ru-reading-copy">观点:{c.stance}</p>}
            {c.relation && <p className="ru-provenance">{({ supports: "支持", partial: "部分支持", opposes: "对立", background: "背景" } as Record<string, string>)[c.relation.kind] ?? c.relation.kind}:{c.relation.note}</p>}
            {c.reason && <p className="ru-provenance">为何相关:{c.reason}</p>}
          </div>
        </li>)}
      </ul>}
      {!state.candidates.length && searchedEmpty && <p className="ru-edge-empty">这次没有候选文献:语料库(active)与 arXiv/OpenAlex 实时检索都没给出可用结果(或 LLM 判定都不够相关)。试试:换更聚焦的关键词、改一改上面的候选假设、或稍等片刻重试(外部源偶发限流)。</p>}
      {state.candidates.length > 0 && <p className="ru-provenance">已选 {state.selected.length} 篇(通常选 1–5 篇;至少 1 篇才能继续)</p>}
    </div>
    <div className="ru-dialogue-step">
      <h2>③ 覆盖梳理:这几篇覆盖了什么 / 还没覆盖什么</h2>
      <button className="ru-quiet-button" disabled={busy || chosen.length === 0} onClick={() => void summarize()}>梳理现状(对已选 {state.selected.length} 篇)</button>
      {state.summary && <pre className="ru-dialogue-pre">{state.summary}</pre>}
    </div>

    <div className="ru-dialogue-step">
      <p className="ru-kicker">反向段 · 对抗与裁决(入轨迹)</p>
      <h2>④ 固化你的 claim,进审查轮</h2>
      <textarea aria-label="claim" className="ru-conclusion-text" value={state.claimText} onChange={(e) => patch({ claimText: e.target.value })} placeholder="读了这些之后,你究竟要断言什么?" />
      <button className="ru-ink-button ru-active" disabled={busy || !state.claimText.trim()} onClick={() => void openReview()}>固化 claim 并开审查轮</button>
      {state.roundId && <p className="ru-provenance">审查轮已开:<a href={`/review-rounds/${state.roundId}`}>去审查轮回应与裁决</a></p>}
      {state.roundId && <button className="ru-quiet-button" disabled={busy || state.selected.length === 0} onClick={() => void literatureAttack()}>用所选文献发难(追加一条文献挑战)</button>}
    </div>

    <div className="ru-dialogue-step">
      <p className="ru-kicker">收敛段 · 定见与导出</p>
      <h2>⑤ 让 Cui 起草 gap 候选(仍由你署名提交)</h2>
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
      <h2>⑥ 生成 related-work 草稿(导出形式,不入轨迹)</h2>
      <button className="ru-quiet-button" disabled={busy || state.selected.length === 0} onClick={() => void draftRelatedWork()}>生成草稿</button>
      {state.relatedWork && <div><pre className="ru-dialogue-pre">{state.relatedWork}</pre>
        <div className="ru-crystal-actions"><button className="ru-quiet-button" onClick={() => void copyDraft()}>{copied ? "已复制" : "复制"}</button><button className="ru-quiet-button" onClick={downloadDraft}>下载 .md</button></div></div>}
    </div>
  </section>
}
