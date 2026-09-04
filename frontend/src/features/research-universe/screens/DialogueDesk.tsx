import { useEffect, useMemo, useRef, useState } from "react"
import { command, researchUniverse } from "../api"
import { useNavigation } from "../../../router"
import type { DialogueCandidate } from "../types"
import { CLAIM_KINDS, clearDialogueDraft, contentStage, emptyDraft, loadDialogueDraft, saveDialogueDraft, STAGE_DESCRIPTIONS, STAGE_LABELS, type ClaimKind, type DialogueDraft, dialogueProgress } from "../dialogueDraft"

const RELATION_LABELS: Record<string, string> = { supports: "支持", partial: "部分支持", opposes: "对立", background: "背景" }

/**
 * 文献探讨 · 一次会话 = 一页,六步推进。
 * - 当前停在哪一步由内容推导(hypotheses→选料→覆盖→claim→gap→草稿),不做完不往下走;
 * - 已完成步骤折叠成一行,可随时展开回看/修改;改上游会自动作废下游瞬态内容;
 * - 进度存 localStorage,可退出、可再进;claim/gap 入轨迹的仍以轨迹为准。
 */
export function DialogueDesk({ workspaceId }: { workspaceId: string }) {
  const { navigate } = useNavigation()
  const [question, setQuestion] = useState("")
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [searchedEmpty, setSearchedEmpty] = useState(false)
  const [copied, setCopied] = useState(false)
  const [revisit, setRevisit] = useState<number | null>(null)
  const [hasProgress, setHasProgress] = useState(false)
  const bootstrapped = useRef(false)

  const [state, setState] = useState<DialogueDraft>(() => loadDialogueDraft(workspaceId))

  useEffect(() => {
    if (dialogueProgress(workspaceId).exists) setHasProgress(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const stage = contentStage(state)
  const uniqueKeywords = useMemo(() => [...new Set(state.keywordsText.split(/[;；]/).map((k) => k.trim()).filter(Boolean))], [state.keywordsText])
  const chosen: DialogueCandidate[] = state.candidates.filter((c) => state.selected.includes(c.locator))
  const corpusIds = chosen.filter((c) => c.material_id).map((c) => c.material_id as string)
  const externalRefs = chosen.filter((c) => !c.material_id).map((c) => ({ locator: c.locator, excerpt: c.excerpt ?? c.title, url: c.url ?? null }))
  const gapConfirmed = state.confirmedGapIds.length > 0

  useEffect(() => {
    let live = true
    researchUniverse.desk(workspaceId)
      .then((desk) => {
        if (!live) return
        setQuestion(desk.question.text)
        // 没有本机草稿但轨迹里已有固化内容(经工作区/审查轮固化过 claim、gap)→ 接上,而不是从零开始。
        setState((prev) => {
          if (bootstrapped.current || prev.savedAt) return prev
          bootstrapped.current = true
          const claims = desk.claims ?? []
          const rounds = desk.review_rounds ?? []
          const gaps = (desk.landscape?.gaps ?? []).filter((g) => g.status === "confirmed").map((g) => g.id)
          if (claims.length === 0 && rounds.length === 0 && gaps.length === 0) return prev
          return {
            ...prev,
            claimText: prev.claimText || (claims.length > 0 ? claims[claims.length - 1].text : ""),
            roundId: prev.roundId || (rounds.length > 0 ? rounds[rounds.length - 1].id : undefined),
            confirmedGapIds: [...new Set([...prev.confirmedGapIds, ...gaps])],
          }
        })
      })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "读取工作区失败") })
    return () => { live = false }
  }, [workspaceId])

  useEffect(() => {
    saveDialogueDraft(workspaceId, state)
  }, [workspaceId, state])

  function patch(partial: Partial<DialogueDraft>) { setState((prev) => ({ ...prev, ...partial })) }

  function invalidateDownstream(partial: Partial<DialogueDraft> = {}) {
    patch({ summary: undefined, gapDraft: undefined, relatedWork: undefined, ...partial })
    setRevisit(null)
  }

  async function runOrientation() {
    if (busy) return
    setBusy(true); setError(undefined)
    try {
      const result = await researchUniverse.orientation(workspaceId, question)
      patch({ hypothesesText: result.hypotheses.join("\n"), keywordsText: result.keywords.join("; "), selectedKeywords: [], skipHypotheses: false })
    } catch (e) { setError(e instanceof Error ? e.message : "出发点准备失败") } finally { setBusy(false) }
  }

  function skipHypotheses() {
    patch({ skipHypotheses: true })
    setRevisit(null)
  }

  function editKeywords(value: string) {
    const kept = state.selectedKeywords.filter((k) => value.includes(k))
    const selectionChanged = kept.join("|") !== state.selectedKeywords.join("|")
    patch({ keywordsText: value, ...(selectionChanged ? { selectedKeywords: kept } : {}) })
    setRevisit(null)
  }

  function toggleKeyword(keyword: string) {
    const has = state.selectedKeywords.includes(keyword)
    patch(has
      ? { selectedKeywords: state.selectedKeywords.filter((k) => k !== keyword) }
      : { selectedKeywords: [...state.selectedKeywords, keyword] })
  }

  // 勾选/取消关键词 → 只触发一次合并检索(单 query,500ms 防抖)。
  useEffect(() => {
    const selection = state.selectedKeywords.join(" ")
    if (!selection || !question) return
    const timer = window.setTimeout(() => { void runSearch(selection) }, 500)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.selectedKeywords.join(" "), question])

  async function runSearch(queryOverride?: string | null) {
    if (busy) return
    const q = queryOverride !== undefined && queryOverride !== null ? queryOverride : (state.selectedKeywords.length > 0 ? state.selectedKeywords.join(" ") : undefined)
    setBusy(true); setError(undefined); setSearchedEmpty(false)
    try {
      const result = await researchUniverse.literatureSearch(workspaceId, { question, query: q || undefined })
      setSearchedEmpty(result.candidates.length === 0)
      invalidateDownstream({ candidates: result.candidates, selected: [], searchQuery: result.query })
    } catch (e) { setError(e instanceof Error ? e.message : "检索失败") } finally { setBusy(false) }
  }

  function toggle(locator: string) {
    const has = state.selected.includes(locator)
    const selected = has ? state.selected.filter((l) => l !== locator) : [...state.selected, locator].slice(-6)
    invalidateDownstream({ selected })
  }

  async function summarize() {
    if (busy || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      const result = await researchUniverse.landscapeSummary(workspaceId, corpusIds, externalRefs)
      patch({ summary: result.text })
    } catch (e) { setError(e instanceof Error ? e.message : "梳理失败") } finally { setBusy(false) }
  }

  function setClaimKind(kind: ClaimKind) {
    const meta = CLAIM_KINDS.find((c) => c.kind === kind)
    patch(meta && !state.claimText.trim()
      ? { claimKind: kind, claimText: meta.skeleton }
      : { claimKind: kind })
  }

  async function openReview() {
    if (busy || !state.claimText.trim()) return
    setBusy(true); setError(undefined)
    try {
      const made = await researchUniverse.createClaim(workspaceId, command({ text: state.claimText.trim() }, 0))
      const review = await researchUniverse.startReview(made.result.claim_id!, command({}, 0))
      patch({ roundId: review.result.review_round_id, claimAck: false })
    } catch (e) { setError(e instanceof Error ? e.message : "开审查轮失败") } finally { setBusy(false) }
  }

  async function literatureAttack() {
    if (busy || !state.roundId || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      await researchUniverse.literatureChallenge(state.roundId, command({ material_ids: corpusIds, external_refs: externalRefs }, 0))
      setError("已追加一条文献挑战,去审查轮查看与回应。")
    } catch (e) { setError(e instanceof Error ? e.message : "文献发难失败") } finally { setBusy(false) }
  }

  async function draftGap() {
    if (busy || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      const draft = await researchUniverse.gapDraft(workspaceId, corpusIds, externalRefs)
      patch({ gapDraft: draft })
    } catch (e) { setError(e instanceof Error ? e.message : "起草失败") } finally { setBusy(false) }
  }

  async function proposeGap() {
    if (busy || !state.gapDraft) return
    const coverage = state.gapDraft.coverage_statement.trim()
    const invitation = state.gapDraft.counterexample_invitation.trim()
    if (coverage.length < 10 || !invitation) return
    setBusy(true); setError(undefined)
    try {
      const proposed = await researchUniverse.proposeGapCandidate(workspaceId, command({
        coverage_statement: coverage,
        search_query: state.gapDraft.search_query.trim() || state.searchQuery || "(未检索,手工登记)",
        search_scope: "active",
        matched_locators: state.selected,
        searched_at: new Date().toISOString().slice(0, 10),
        counterexample_invitation: invitation,
      }, 0))
      const gapId = proposed.result.gap_candidate_id
      await researchUniverse.confirmGapCandidate(gapId, command({ user_reason: "人审确认" }, 1))
      patch({ gapDraft: undefined, confirmedGapIds: [...state.confirmedGapIds, gapId] })
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

  function clearAll() {
    clearDialogueDraft(workspaceId)
    setState(emptyDraft(workspaceId))
    setSearchedEmpty(false); setError(undefined); setRevisit(null); setHasProgress(false)
  }

  const oneLine: Record<number, string> = {
    1: state.skipHypotheses ? "不设假设,直接检索" : `候选假设 ${state.hypothesesText.split("\n").filter((l) => l.trim()).length} 条 · ${uniqueKeywords.length} 个检索词`,
    2: `检索并选入 ${state.selected.length} 篇`,
    3: "覆盖梳理已生成",
    4: `claim 已固化,审查轮已开`,
    5: `✓ gap 已确认 ×${state.confirmedGapIds.length}`,
    6: "综述草稿已生成",
  }

  return <section className="ru-dialogue-new" aria-labelledby="dialogue-title">
    <header className="ru-dialogue-head">
      <div>
        <p className="ru-kicker">文献探讨 · 与 Cui 一起读文献</p>
        <h1 id="dialogue-title">{question || "正在展开问题…"}</h1>
      </div>
      <div className="ru-dialogue-head-actions">
        <span className="ru-save-note">进度自动保存在本机浏览器</span>
        <button type="button" className="ru-exit-button" onClick={() => navigate(`/workspaces/${workspaceId}`)}>退出会话</button>
      </div>
    </header>
    {hasProgress && <p className="ru-resume-note" role="status">已恢复上次会话:当前在第 {stage} 步({STAGE_LABELS[stage - 1]})。<button type="button" className="ru-link-button" onClick={clearAll}>清空并重新开始</button></p>}
    {error && <p className={error.startsWith("已追加") ? "ru-ok-note" : "ru-error"} role={error.startsWith("已追加") ? "status" : "alert"}>{error}</p>}

    <ol className="ru-stage-rail" aria-label="会话阶段">
      {STAGE_LABELS.map((label, i) => {
        const n = i + 1
        const done = stage > n
        const current = stage === n
        return <li key={label} className={current ? "ru-stage-li ru-stage-li-current" : done ? "ru-stage-li ru-stage-li-done" : "ru-stage-li"}>
          <button type="button" disabled={stage < n} title={STAGE_DESCRIPTIONS[i]} onClick={() => setRevisit(done && revisit === n ? null : done ? n : null)}>
            <span className="ru-stage-dot">{done ? "✓" : n}</span>{label}
          </button>
        </li>
      })}
    </ol>

    {Array.from({ length: stage }, (_, i) => {
      const n = i + 1
      const open = (n === stage && revisit === null) || revisit === n
      if (!open) {
        return <section key={n} className="ru-done-step" aria-label={`已完成:第 ${n} 步 ${STAGE_LABELS[n - 1]}`}>
          <button type="button" className="ru-done-step-toggle" onClick={() => setRevisit(n)}>
            <span className="ru-done-step-title"><span className="ru-stage-dot">✓</span>{n}. {STAGE_LABELS[n - 1]}</span>
            <span className="ru-done-step-line">{oneLine[n]}</span>
            <span className="ru-done-step-action">展开修改 ▾</span>
          </button>
        </section>
      }
      const inRevisit = revisit === n && n !== stage
      return <section key={n} className={inRevisit ? "ru-stage-card ru-stage-card-revisit" : "ru-stage-card"} aria-current={!inRevisit ? "step" : undefined}>
        <div className="ru-stage-card-title">
          <h2>{n}. {STAGE_LABELS[n - 1]}</h2>
          <span className="ru-kicker">{inRevisit ? "回看/修改中 · 内容会接续到后续步骤" : `第 ${n} 步 · ${STAGE_DESCRIPTIONS[n - 1]}`}</span>
        </div>
        {n === 1 && bodyOne()}
        {n === 2 && bodyTwo()}
        {n === 3 && bodyThree()}
        {n === 4 && bodyFour()}
        {n === 5 && bodyFive()}
        {n === 6 && bodySix()}
        {inRevisit && <button type="button" className="ru-link-button ru-link-close-revisit" onClick={() => setRevisit(null)}>收起,回到第 {stage} 步</button>}
      </section>
    })}
  </section>

  function bodyOne() {
    const drafted = Boolean(state.hypothesesText.trim())
    const agreed = Boolean(state.hypothesesDone || state.skipHypotheses)
    if (!drafted && !state.skipHypotheses) {
      return <div className="ru-stage-body">
        <p className="ru-copy">这是一个全新问题:先让 Cui 起草一版候选假设与检索词,再由你改写、增删。假设始终是你的判断——它是下面检索和对抗的地基。</p>
        <div className="ru-stage-actions">
          <button type="button" className="ru-ink-button ru-active" disabled={busy} onClick={() => void runOrientation()}>{busy ? "思考中…" : "让 Cui 起草候选假设与关键词"}</button>
          <button type="button" className="ru-link-button" onClick={skipHypotheses}>先不设假设,直接去选料</button>
        </div>
      </div>
    }
    if (state.skipHypotheses && !drafted) {
      return <div className="ru-stage-body">
        <p className="ru-copy">你选择先不设假设,直接看文献。想补写随时回来改。</p>
        <div className="ru-stage-actions">
          <button type="button" className="ru-link-button" onClick={() => patch({ skipHypotheses: false })}>回到第 1 步,还是要一份候选假设</button>
        </div>
      </div>
    }
    return <div className="ru-stage-body">
      {agreed && !state.skipHypotheses && <p className="ru-resume-note">你已用过这版假设;继续改写会作为第 1 步的新版本,后续步骤不受影响。</p>}
      <div className="ru-material-form">
        <label htmlFor="hypotheses-edit">候选假设(每行一条;由 Cui 起草,你可改写/增删/加自己的)</label>
        <textarea id="hypotheses-edit" className="ru-conclusion-text" rows={Math.min(8, state.hypothesesText.split("\n").length + 1)} value={state.hypothesesText} onChange={(e) => patch({ hypothesesText: e.target.value })} />
      </div>
      <div className="ru-secondary-row">
        <button type="button" className="ru-quiet-button" disabled={busy} onClick={() => void runOrientation()}>{busy ? "思考中…" : "让 Cui 重写一版(覆盖上面草稿)"}</button>
      </div>
      <div className="ru-stage-actions">
        <button type="button" className="ru-ink-button ru-active" disabled={!drafted} onClick={() => patch({ hypothesesDone: true })}>就用这版假设,去选料 →</button>
      </div>
    </div>
  }

  function bodyTwo() {
    return <div className="ru-stage-body">
      <div className="ru-material-form">
        <label htmlFor="keywords-edit">检索词(用分号 ; 分隔,可直接编辑)</label>
        <input id="keywords-edit" className="ru-revival-input" value={state.keywordsText} onChange={(e) => editKeywords(e.target.value)} placeholder="例:US hegemony; 美国霸权; power transition" />
        {uniqueKeywords.length > 0 && <div className="ru-keyword-chips" aria-label="检索词开关(勾选即自动合并检索)">
          {uniqueKeywords.map((kw) => <button key={kw} type="button" className={state.selectedKeywords.includes(kw) ? "ru-chip ru-chip-on" : "ru-chip"} onClick={() => toggleKeyword(kw)}>{state.selectedKeywords.includes(kw) ? "✓ " : ""}{kw}</button>)}
        </div>}
        <p className="ru-quiet-hint">勾选/取消任一词条会自动合并检索一次;每个候选都先给出观点与对你的支撑关系,再决定是否选入。</p>
        <div className="ru-secondary-row">
          <button type="button" className="ru-quiet-button" disabled={busy || uniqueKeywords.length === 0} onClick={() => void runSearch(state.selectedKeywords.length > 0 ? state.selectedKeywords.join(" ") : uniqueKeywords.join(" "))}>{busy ? "检索中…" : "按当前词条搜一次"}</button>
          {searchedEmpty && state.candidates.length === 0 && <span className="ru-muted-note">没有候选文献</span>}
        </div>
      </div>
      {busy && <p className="ru-muted-note">正在检索语料库 + arXiv/OpenAlex…</p>}
      {state.candidates.length > 0 && <ul className="ru-paper-list">
        {state.candidates.map((c) => {
          const picked = state.selected.includes(c.locator)
          return <li key={c.locator} className={picked ? "ru-paper-card ru-paper-picked" : "ru-paper-card"}>
            <div className="ru-paper-main">
              <strong className="ru-paper-title">{c.title}</strong>
              <p className="ru-paper-meta">{c.source && c.source !== "corpus" ? `${c.source} · ` : "语料 · "}{c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.locator} ↗</a> : c.locator}</p>
              {c.stance && <p className="ru-paper-stance">观点:{c.stance}</p>}
              {c.relation && <p className="ru-paper-relation"><span className={`ru-rel-chip ru-rel-${c.relation.kind}`}>{RELATION_LABELS[c.relation.kind] ?? c.relation.kind}</span>{c.relation.note}</p>}
              {c.reason && <p className="ru-paper-meta">为何相关:{c.reason}</p>}
            </div>
            <button type="button" className={picked ? "ru-pick ru-pick-on" : "ru-pick"} onClick={() => toggle(c.locator)}>{picked ? "✓ 已选入" : "选入"}</button>
          </li>
        })}
      </ul>}
      {state.candidates.length === 0 && searchedEmpty && <p className="ru-edge-empty">这次没有候选文献:语料库(active)与 arXiv/OpenAlex 实时检索都没给出可用结果(或 LLM 判定都不够相关)。试试换更聚焦的关键词、改改假设,或稍等片刻重试(外部源偶发限流)。</p>}
      {state.selected.length > 0 && <p className="ru-selected-count">已选 {state.selected.length} 篇(通常 1–5 篇),可进入覆盖梳理</p>}
      <div className="ru-stage-actions">
        <button type="button" className="ru-ink-button ru-active" disabled={state.selected.length === 0 || busy} onClick={() => void summarize()}>梳理这几篇覆盖了什么 →</button>
      </div>
    </div>
  }

  function bodyThree() {
    const fixed = Boolean(state.roundId)
    return <div className="ru-stage-body">
      {state.summary && <div className="ru-ai-block">
        <p className="ru-kicker">覆盖梳理(Cui 起草,临时;基于已选 {state.selected.length} 篇)</p>
        <p className="ru-ai-content">{state.summary}</p>
        <div className="ru-secondary-row">
          <button type="button" className="ru-quiet-button" disabled={busy} onClick={() => void summarize()}>重新梳理</button>
        </div>
      </div>}
      {fixed
        ? <p className="ru-ok-note">claim 已固化,对抗在第 4 步等你去看审查轮;这里只读回看。</p>
        : <div>
          <p className="ru-copy">读上面的覆盖梳理,写你对文献格局的一句判断。探索性综述不需要论文式论点——共识、分歧、空缺都算,审查轮会替它找反例;打不烂的才写进综述正文。claim 由你签名,Cui 只攻击。</p>
          <div className="ru-kind-row" role="group" aria-label="claim 类型">
            {CLAIM_KINDS.map((c) => <button key={c.kind} type="button" className={state.claimKind === c.kind ? "ru-chip ru-chip-on" : "ru-chip"} onClick={() => setClaimKind(c.kind)}>{c.label}</button>)}
          </div>
          <p className="ru-quiet-hint">点类型会把骨架句填进下方文本框(____ 处填空),再由你写实;选"自写立场"或直接改即可。</p>
          <div className="ru-material-form">
            <label htmlFor="claim">由你写下的 claim</label>
            <textarea id="claim" className="ru-conclusion-text" rows={5} value={state.claimText} onChange={(e) => patch({ claimText: e.target.value })} placeholder="读了这些之后,你究竟要断言什么?" />
          </div>
          <div className="ru-stage-actions">
            <button type="button" className="ru-ink-button ru-active" disabled={busy || !state.claimText.trim()} onClick={() => void openReview()}>{busy ? "正在固化…" : "固化 claim 并开审查轮"}</button>
          </div>
        </div>}
    </div>
  }

  function bodyFour() {
    return <div className="ru-stage-body">
      <div className="ru-review-handoff">
        <p className="ru-ok-note">✓ claim 已固化,审查轮已开。claim 由你署名、不可改写——要换立场就回到工作区另起一条 claim。</p>
        <blockquote className="ru-claim-quote">{state.claimText}</blockquote>
        <div className="ru-secondary-row">
          <button type="button" className="ru-link-button" onClick={() => navigate(`/review-rounds/${state.roundId}`)}>去审查轮完整应答与裁决 →</button>
          <button type="button" className="ru-quiet-button" disabled={busy || state.selected.length === 0} onClick={() => void literatureAttack()}>用所选文献发难(追加一条文献挑战)</button>
        </div>
        <p className="ru-quiet-hint">对抗在审查轮里进行;发难、应答、裁决都可在审查轮页来回,那里也有"回到文献探讨"。看完情况再继续 gap 与草稿。</p>
        <div className="ru-stage-actions">
          <button type="button" className="ru-ink-button ru-active" disabled={busy} onClick={() => patch({ claimAck: true })}>我看过审查轮了,继续起草 gap →</button>
        </div>
      </div>
    </div>
  }

  function bodyFive() {
    return <div className="ru-stage-body">
      {!gapConfirmed && !state.gapDraft && <div>
        <p className="ru-copy">让 Cui 根据已选文献与覆盖梳理起草一个 gap 候选:覆盖范围声明 + 可复现检索记录 + 反例邀请。提出的是缺口,不是"所以你应该做 Y";由你署名提交确认后才入轨迹。</p>
        <div className="ru-stage-actions">
          <button type="button" className="ru-ink-button ru-active" disabled={busy || state.selected.length === 0} onClick={() => void draftGap()}>{busy ? "起草中…" : "让 Cui 起草 gap 候选"}</button>
        </div>
      </div>}
      {state.gapDraft && !gapConfirmed && <div className="ru-material-form">
        <p className="ru-kicker">gap 形状:覆盖声明 + 检索记录 + 反例邀请(Cui 起草,你改,你署名)</p>
        <label htmlFor="d-coverage">覆盖范围声明(哪些已被覆盖、缺口在哪)</label>
        <textarea id="d-coverage" className="ru-conclusion-text" value={state.gapDraft.coverage_statement} onChange={(e) => patch({ gapDraft: { ...state.gapDraft!, coverage_statement: e.target.value } })} />
        <label htmlFor="d-invitation">邀请反例</label>
        <input id="d-invitation" className="ru-revival-input" value={state.gapDraft.counterexample_invitation} onChange={(e) => patch({ gapDraft: { ...state.gapDraft!, counterexample_invitation: e.target.value } })} />
        <div className="ru-stage-actions">
          <button type="button" className="ru-quiet-button" disabled={busy} onClick={() => void draftGap()}>重新起草</button>
          <button type="button" className="ru-ink-button ru-active" disabled={busy || state.gapDraft.coverage_statement.trim().length < 10 || !state.gapDraft.counterexample_invitation.trim()} onClick={() => void proposeGap()}>{busy ? "提交中…" : "提交并确认这个 gap"}</button>
        </div>
      </div>}
      {gapConfirmed && <p className="ru-ok-note">✓ gap 已确认 ×{state.confirmedGapIds.length},已入轨迹(工作区"现状图景与 gap"里可见)。</p>}
    </div>
  }

  function bodySix() {
    return <div className="ru-stage-body">
      {!state.relatedWork && <div>
        <p className="ru-copy">基于已选文献与已确认的 gap,生成 related-work 综述草稿(导出用,不入轨迹)。</p>
        <div className="ru-stage-actions">
          <button type="button" className="ru-ink-button ru-active" disabled={busy || state.selected.length === 0} onClick={() => void draftRelatedWork()}>{busy ? "生成中…" : "生成 related-work 综述草稿"}</button>
        </div>
      </div>}
      {state.relatedWork && <div>
        <div className="ru-ai-block">
          <p className="ru-kicker">综述草稿(导出形式,不入轨迹)</p>
          <pre className="ru-dialogue-pre">{state.relatedWork}</pre>
        </div>
        <div className="ru-crystal-actions">
          <button type="button" className="ru-quiet-button" onClick={() => void copyDraft()}>{copied ? "已复制" : "复制"}</button>
          <button type="button" className="ru-quiet-button" onClick={downloadDraft}>下载 .md</button>
          <button type="button" className="ru-quiet-button" disabled={busy} onClick={() => void draftRelatedWork()}>重新生成</button>
        </div>
        <p className="ru-quiet-hint">会话走完。草稿与选料存本机;claim 与 gap 已入轨迹。随时可从工作区"继续文献探讨"回到这里继续改。</p>
      </div>}
    </div>
  }
}
