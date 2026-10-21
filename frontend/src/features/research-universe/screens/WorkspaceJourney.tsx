import { useEffect, useMemo, useRef, useState } from "react"
import { command, researchUniverse } from "../api"
import { useNavigation } from "../../../router"
import { GapList, LandscapePanel, LedgerPanel, short, survivingClaims, VERDICT_LABELS } from "./LandscapePanel"
import { ReleaseForge } from "./ReleaseForge"
import { ReviewRoundDesk } from "./ReviewRoundDesk"
import type { CitationReport, CommandEnvelope, ConclusionType, DialogueCandidate, HomeProjection, MaterialPurpose, ParkReleaseRef, WorkspaceDesk as Desk, WorkspacePosition } from "../types"
import { CLAIM_KINDS, clearDialogueDraft, dialogueProgress, emptyDraft, hasClaimBlanks, journeyStage, loadDialogueDraft, saveDialogueDraft, STAGE_DESCRIPTIONS, STAGE_LABELS, type ClaimKind, type DialogueDraft } from "../dialogueDraft"

const POSITION_LABELS: Record<WorkspacePosition, string> = { exploring: "探索中", paused: "已暂停", concluded: "已确认位置", branched: "已分支", absorbed: "已并入" }
const CONCLUSION_OPTIONS: { type: ConclusionType; label: string; note?: string }[] = [
  { type: "tentative_answer", label: "暂时回答", note: "这是一段可检验的回答" },
  { type: "negated_path", label: "否定路径", note: "这条路被证伪或放弃了" },
  { type: "boundary", label: "划出边界", note: "问题需要收窄或改写" },
  { type: "key_unknown", label: "关键未知", note: "卡在某个关键未知上" },
  { type: "deferred", label: "暂缓条件", note: "现在先不投入，写下何时回来" },
  { type: "split_or_turn", label: "拆分／转向", note: "这一支需要拆开或拐弯" },
]
const RELATION_LABELS: Record<string, string> = { supports: "支持", partial: "部分支持", opposes: "对立", background: "背景" }
const SCOPE_MESSAGES = { abstract: "摘要中未找到依据(可能在全文)", excerpt: "摘录中未找到依据", full: "全文中未找到依据" } as const

/** 只标记不改写:列出核对不过的引用;全过只一行;无引用不显示。 */
function CitationCheckList({ report }: { report?: CitationReport }) {
  const checks = report?.citation_checks ?? []
  const flagged = checks.filter((c) => c.verdict !== "supported")
  if (!report || (report.citation_check_status !== "unavailable" && checks.length === 0)) return null
  return <div className="ru-muted-note">
    {report.citation_check_status === "unavailable" && <p>引用核对暂不可用,以上引用未经核对。</p>}
    {report.citation_check_status === "ok" && flagged.length === 0 && <p>引用核对:全部可在所选文献中找到依据</p>}
    {flagged.length > 0 && <>
      <p className="ru-kicker">引用核对:以下引用未通过(仅标记,草稿未改动)</p>
      <ul className="ru-error">{flagged.map((c, i) => <li key={`${c.locator}-${i}`}>
        “{c.sentence}” [{c.locator}] —— {c.verdict === "not_selected" || !c.scope ? "引用了未选入的文献" : SCOPE_MESSAGES[c.scope]}
      </li>)}</ul>
    </>}
  </div>
}

type Selection = { start: number; end: number; selected_text: string }
type ClaimIntent = { claim: CommandEnvelope & { text: string; kind?: Exclude<ClaimKind, "custom"> }; claimId?: string; provenance?: CommandEnvelope & { claim_id: string; capture_id: string; release_id: string }; review?: CommandEnvelope }

/**
 * 问题工作区 = 旅程页(spec-workspace-journey S1):一个问题一页,六阶段竖排。
 * - 当前阶段由 journeyStage(desk, 草稿) 推导(服务端事实优先);任何阶段都可点开,不锁;
 * - 已完成阶段折叠成一行,可展开修改;展开修改只改本机草稿,已入轨迹的对象不改写;
 * - 页头只留暂停/重开;探索稿、手动材料、PARK 放行引用收进「工具」;
 * - 右侧聚焦面:roundId(/workspaces/:id/rounds/:rid)打开审查轮,forgeReleaseRefId 打开锻,gap 阶段没开轮时是现状图景;<800px 堆到左栏下方。
 * 会话草稿存 localStorage,可退出、可再进;claim/审查轮/gap/结论以轨迹为准。
 */
export function WorkspaceJourney({ workspaceId, forgeReleaseRefId, sourceReleaseId, roundId }: { workspaceId: string; forgeReleaseRefId?: string; sourceReleaseId?: string; roundId?: string }) {
  const { navigate } = useNavigation(); const [desk, setDesk] = useState<Desk | null>(null); const [sourceRef, setSourceRef] = useState<ParkReleaseRef | undefined>(); const [note, setNote] = useState(""); const [selected, setSelected] = useState<Selection>(); const [error, setError] = useState<string>(); const [conflict, setConflict] = useState(false); const [savePending, setSavePending] = useState(false); const draftGeneration = useRef(0); const noteCommand = useRef<(CommandEnvelope & { text: string }) | undefined>(undefined); const anchorCommand = useRef<(CommandEnvelope & { note_id: string; note_revision_id: string; start: number; end: number; selected_text: string }) | undefined>(undefined); const claimIntent = useRef<ClaimIntent | undefined>(undefined); const routeGeneration = useRef(0); const routeId = useRef(workspaceId); const [materialExcerpt, setMaterialExcerpt] = useState(""); const [materialSource, setMaterialSource] = useState(""); const [materialPurpose, setMaterialPurpose] = useState<MaterialPurpose>("evidence"); const [materialUnparsable, setMaterialUnparsable] = useState(false); const [materialPending, setMaterialPending] = useState(false); const materialCommand = useRef<(CommandEnvelope & { excerpt: string; source_locator?: string | null; parse_status: "parsed" | "failed"; purpose: MaterialPurpose }) | undefined>(undefined); const [lifecycleForm, setLifecycleForm] = useState<"pause" | "reopen" | null>(null); const [lifecycleReason, setLifecycleReason] = useState(""); const [conclusionText, setConclusionText] = useState(""); const [conclusionType, setConclusionType] = useState<ConclusionType | null>(null); const [revivalCondition, setRevivalCondition] = useState(""); const [concluding, setConcluding] = useState(false); const [branchOpen, setBranchOpen] = useState(false); const [branchQuestion, setBranchQuestion] = useState(""); const [branchReason, setBranchReason] = useState(""); const [branchPending, setBranchPending] = useState(false); const [absorbOpen, setAbsorbOpen] = useState(false); const [absorbTarget, setAbsorbTarget] = useState(""); const [absorbReason, setAbsorbReason] = useState(""); const [absorbPending, setAbsorbPending] = useState(false);
  // 结晶阶段(S6):位置的理由;去向 = 挂已有方向 / 从 gap 新建(签名才生效,签后再改即失效)/ 只留本次;home 只供方向下拉与「已结晶到哪个方向」
  const [conclusionReason, setConclusionReason] = useState(""); const [dest, setDest] = useState<"attach" | "new" | "local" | null>(null); const [destDirection, setDestDirection] = useState(""); const [destGap, setDestGap] = useState(""); const [proposition, setProposition] = useState(""); const [signed, setSigned] = useState(false); const [destBusy, setDestBusy] = useState(false); const [home, setHome] = useState<HomeProjection | null>(null); const [homeError, setHomeError] = useState(false)
  // 会话草稿(本机)。页面按 workspaceId 加 key 挂载(App.tsx),换工作区即重建,草稿不会串到别的工作区。
  const [state, setState] = useState<DialogueDraft>(() => loadDialogueDraft(workspaceId))
  const [busy, setBusy] = useState(false)
  const [searchedEmpty, setSearchedEmpty] = useState(false)
  const [copied, setCopied] = useState(false)
  const [open, setOpen] = useState<number | null>(null) // 展开哪一张阶段卡;null = 跟随推导出的当前阶段
  const [rewriting, setRewriting] = useState(false)
  const [bringing, setBringing] = useState<string>() // 正在带进证据台的那篇(locator)
  const [hasProgress, setHasProgress] = useState(() => dialogueProgress(workspaceId).exists)
  const bootstrapped = useRef(false)
  const panelRef = useRef<HTMLElement>(null)

  async function load(accept = () => true) { try { const value = await researchUniverse.desk(workspaceId); if (accept()) { setDesk(value); if (!noteCommand.current && draftGeneration.current === 0) setNote(value.note?.text ?? ""); setError(undefined); bootstrap(value) } } catch (e) { if (accept()) setError(e instanceof Error ? e.message : "读取失败") } }
  useEffect(() => { let live = true; routeGeneration.current++; routeId.current = workspaceId; noteCommand.current = undefined; anchorCommand.current = undefined; claimIntent.current = undefined; materialCommand.current = undefined; setSavePending(false); setMaterialPending(false); setMaterialExcerpt(""); setMaterialSource(""); setMaterialPurpose("evidence"); setMaterialUnparsable(false); setSourceRef(undefined); setConflict(false); setDesk(null); setError(undefined); setSelected(undefined); setLifecycleForm(null); setLifecycleReason(""); setConclusionText(""); setConclusionType(null); setRevivalCondition(""); setConcluding(false); setBranchOpen(false); setBranchQuestion(""); setBranchReason(""); setBranchPending(false); setAbsorbOpen(false); setAbsorbTarget(""); setAbsorbReason(""); setAbsorbPending(false); draftGeneration.current = 0; void load(() => live); return () => { live = false } }, [workspaceId])
  function editNote(text: string) { draftGeneration.current++; setNote(text); setSelected(undefined); noteCommand.current = undefined }
  const isCurrent = (generation: number, id: string) => generation === routeGeneration.current && id === routeId.current
  async function saveNote() { if (!desk || savePending) return; const currentGeneration = routeGeneration.current, currentId = workspaceId; const generation = draftGeneration.current; noteCommand.current ??= command({ text: note }, desk.sequence); setSavePending(true); try { const result = await researchUniverse.saveNote(currentId, noteCommand.current); if (!isCurrent(currentGeneration, currentId)) return; noteCommand.current = undefined; const fragment = result.fragment as Desk | undefined; if (fragment?.id) { setDesk(fragment); if (draftGeneration.current === generation) { setNote(fragment.note?.text ?? note); draftGeneration.current = 0 } void load(() => isCurrent(currentGeneration, currentId)) } else void load(() => isCurrent(currentGeneration, currentId)) } catch (e) { if (!isCurrent(currentGeneration, currentId)) return; setError(e instanceof Error ? e.message : "保存失败"); if ((e as { status?: number }).status === 409) { noteCommand.current = undefined; setConflict(true); void load(() => isCurrent(currentGeneration, currentId)) } } finally { if (isCurrent(currentGeneration, currentId)) setSavePending(false) } }
  async function anchor() { if (!desk?.note || !selected || note !== desk.note.text || savePending) return; const currentGeneration = routeGeneration.current, currentId = workspaceId; anchorCommand.current ??= command({ note_id: desk.note.note_id ?? desk.note.id, note_revision_id: desk.note.revision_id, ...selected }, desk.sequence); try { await researchUniverse.createAnchor(currentId, anchorCommand.current); if (!isCurrent(currentGeneration, currentId)) return; anchorCommand.current = undefined; void load(() => isCurrent(currentGeneration, currentId)) } catch (e) { if (!isCurrent(currentGeneration, currentId)) return; setError(e instanceof Error ? e.message : "锚点失败"); if ((e as { status?: number }).status === 409) { anchorCommand.current = undefined; setConflict(true); void load(() => isCurrent(currentGeneration, currentId)) } } }
  function reapply() { if (!desk) return; setConflict(false); noteCommand.current = undefined; anchorCommand.current = undefined; claimIntent.current = undefined; materialCommand.current = undefined; setError(undefined) }
  async function addMaterial() {
    if (!desk || materialPending || !materialExcerpt.trim()) return
    const currentGeneration = routeGeneration.current, currentId = workspaceId
    materialCommand.current ??= command({ excerpt: materialExcerpt.trim(), source_locator: materialSource.trim() || null, parse_status: materialUnparsable ? "failed" : "parsed", purpose: materialPurpose }, 0)
    setMaterialPending(true)
    try {
      await researchUniverse.addMaterial(currentId, materialCommand.current)
      if (!isCurrent(currentGeneration, currentId)) return
      materialCommand.current = undefined
      setMaterialExcerpt(""); setMaterialSource(""); setMaterialPurpose("evidence"); setMaterialUnparsable(false)
      void load(() => isCurrent(currentGeneration, currentId))
    } catch (e) {
      if (!isCurrent(currentGeneration, currentId)) return
      setError(e instanceof Error ? e.message : "带入材料失败")
      if ((e as { status?: number }).status === 409) { materialCommand.current = undefined; setConflict(true); void load(() => isCurrent(currentGeneration, currentId)) }
    } finally { if (isCurrent(currentGeneration, currentId)) setMaterialPending(false) }
  }
  // S4:已选文献带进证据台(只有摘要)。「已在证据台」只从投影推导,重进/换设备都对;同一篇后端去重,返回已有 material_id
  async function bringToDesk(c: DialogueCandidate) {
    if (bringing) return
    const currentGeneration = routeGeneration.current, currentId = workspaceId
    setBringing(c.locator); setError(undefined)
    try {
      await researchUniverse.addMaterial(currentId, command({ excerpt: c.excerpt || c.title, source_locator: c.locator, parse_status: "parsed" as const, purpose: "evidence" as const, content_scope: "abstract" as const }, 0))
      if (isCurrent(currentGeneration, currentId)) await load(() => isCurrent(currentGeneration, currentId))
    } catch (e) { if (isCurrent(currentGeneration, currentId)) setError(e instanceof Error ? e.message : "带进证据台失败") } finally { if (isCurrent(currentGeneration, currentId)) setBringing(undefined) }
  }
  // 页头位置:暂停理由可选,重开理由必填(必填只在前端做,后端 user_reason 可空)
  async function lifecycleAction(action: "pause" | "reopen") {
    if (!desk || (action === "reopen" && !lifecycleReason.trim())) return
    const currentGeneration = routeGeneration.current, currentId = workspaceId
    const envelope = command({ user_reason: lifecycleReason.trim() || null }, desk.sequence)
    try {
      if (action === "pause") await researchUniverse.pauseWorkspace(currentId, envelope)
      else await researchUniverse.reopenWorkspace(currentId, envelope)
      if (!isCurrent(currentGeneration, currentId)) return
      setLifecycleForm(null); setLifecycleReason("")
      void load(() => isCurrent(currentGeneration, currentId))
    } catch (e) { if (!isCurrent(currentGeneration, currentId)) return; setError(e instanceof Error ? e.message : (action === "pause" ? "暂停失败" : "重开失败")); if ((e as { status?: number }).status === 409) { setConflict(true); void load(() => isCurrent(currentGeneration, currentId)) } }
  }
  async function conclude() {
    if (!desk || concluding || !conclusionType || !conclusionText.trim() || !conclusionReason.trim() || (conclusionType === "deferred" && !revivalCondition.trim())) return
    const currentGeneration = routeGeneration.current, currentId = workspaceId
    setConcluding(true)
    try {
      await researchUniverse.concludeWorkspace(currentId, command({ conclusion_type: conclusionType, conclusion_text: conclusionText.trim(), user_reason: conclusionReason.trim(), basis_refs: [], revival_condition: conclusionType === "deferred" ? revivalCondition.trim() : null }, desk.sequence))
      if (!isCurrent(currentGeneration, currentId)) return
      setConclusionText(""); setConclusionType(null); setConclusionReason(""); setRevivalCondition(""); setDest(null); setSigned(false)
      void load(() => isCurrent(currentGeneration, currentId))
    } catch (e) { if (!isCurrent(currentGeneration, currentId)) return; setError(e instanceof Error ? e.message : "结晶失败"); if ((e as { status?: number }).status === 409) { setConflict(true); void load(() => isCurrent(currentGeneration, currentId)) } } finally { if (isCurrent(currentGeneration, currentId)) setConcluding(false) }
  }
  async function branch() {
    if (!desk || branchPending || !branchQuestion.trim() || !branchReason.trim()) return
    const currentGeneration = routeGeneration.current, currentId = workspaceId
    setBranchPending(true)
    try {
      const result = await researchUniverse.branchWorkspace(currentId, command({ new_question: branchQuestion.trim(), user_reason: branchReason.trim() }, desk.sequence))
      if (!isCurrent(currentGeneration, currentId)) return
      setBranchOpen(false); setBranchQuestion(""); setBranchReason("")
      navigate(`/workspaces/${result.result.successor_workspace_id}`)
    } catch (e) { if (!isCurrent(currentGeneration, currentId)) return; setError(e instanceof Error ? e.message : "分支失败"); if ((e as { status?: number }).status === 409) { setConflict(true); void load(() => isCurrent(currentGeneration, currentId)) } } finally { if (isCurrent(currentGeneration, currentId)) setBranchPending(false) }
  }
  async function absorb() {
    if (!desk || absorbPending || !absorbTarget.trim() || !absorbReason.trim()) return
    const currentGeneration = routeGeneration.current, currentId = workspaceId
    setAbsorbPending(true)
    try {
      await researchUniverse.absorbWorkspace(currentId, command({ target_workspace_id: absorbTarget.trim(), user_reason: absorbReason.trim() }, desk.sequence))
      if (!isCurrent(currentGeneration, currentId)) return
      setAbsorbOpen(false); setAbsorbTarget(""); setAbsorbReason("")
      void load(() => isCurrent(currentGeneration, currentId))
    } catch (e) { if (!isCurrent(currentGeneration, currentId)) return; setError(e instanceof Error ? e.message : "吸收失败"); if ((e as { status?: number }).status === 409) { setConflict(true); void load(() => isCurrent(currentGeneration, currentId)) } } finally { if (isCurrent(currentGeneration, currentId)) setAbsorbPending(false) }
  }
  async function loadHome() { try { const active = await researchUniverse.active(); setHome(await researchUniverse.home(active.id)); setHomeError(false) } catch { setHomeError(true) } }
  // 这次结论去哪:挂已有 / 从 gap 新建 = 一条原子命令(写入的都是新聚合 ⇒ expected_sequence 0);只留本次 = 本机标记,不调方向命令
  async function settleDestination() {
    const conclusion = desk?.conclusion
    if (!desk || !conclusion || destBusy || !dest) return
    if (dest === "local") { patch({ keptLocal: conclusion.id }); return }
    if (dest === "attach" ? !destDirection : !signed || !proposition.trim()) return
    const currentGeneration = routeGeneration.current, currentId = workspaceId
    setDestBusy(true)
    try {
      await researchUniverse.crystallizeIntoDirection(currentId, command({ conclusion_id: conclusion.id, direction_id: dest === "attach" ? destDirection : null, new_proposition: dest === "new" ? proposition.trim() : null, user_reason: null }, 0))
      if (!isCurrent(currentGeneration, currentId)) return
      await loadHome() // 回执与阶段完成都读首页投影里的这条结晶
      void load(() => isCurrent(currentGeneration, currentId))
    } catch (e) { if (!isCurrent(currentGeneration, currentId)) return; setError(e instanceof Error ? e.message : "结晶到方向失败"); if ((e as { status?: number }).status === 409) { setConflict(true); void load(() => isCurrent(currentGeneration, currentId)) } } finally { if (isCurrent(currentGeneration, currentId)) setDestBusy(false) }
  }
  useEffect(() => { const hinted = sourceReleaseId && desk ? (desk.park_release_refs ?? []).find(item => item.id === sourceReleaseId) : undefined; setSourceRef(current => current?.id === hinted?.id ? current : hinted) }, [desk, sourceReleaseId, workspaceId])
  // 从锻「跳过锻,直接提交已成形自写 Claim」带着来源回来 → 打开写 claim 的阶段
  useEffect(() => { if (sourceRef && sourceRef.id === sourceReleaseId) setOpen(3) }, [sourceRef, sourceReleaseId])

  // ——— 会话草稿(原文献探讨会话页) ———
  /** 本机没有的固化内容(claim、审查轮、gap)从轨迹接上,只在首次读到投影时做一次。 */
  function bootstrap(value: Desk) {
    if (bootstrapped.current) return
    bootstrapped.current = true
    const claims = value.claims ?? []
    const rounds = value.review_rounds ?? []
    const gaps = (value.landscape?.gaps ?? []).filter((g) => g.status === "confirmed").map((g) => g.id)
    if (claims.length === 0 && rounds.length === 0 && gaps.length === 0) return
    setState((prev) => ({
      ...prev,
      claimText: prev.claimText || (claims.length > 0 ? claims[claims.length - 1].text : ""),
      roundId: prev.roundId || (rounds.length > 0 ? rounds[rounds.length - 1].id : undefined),
      confirmedGapIds: [...new Set([...prev.confirmedGapIds, ...gaps])],
    }))
  }

  // 位置已确认 → 读首页投影:方向下拉,以及这条结论是否已结晶进某个方向(换设备也认得)
  useEffect(() => { if (desk?.user_position === "concluded") void loadHome() }, [desk?.user_position, desk?.conclusion?.id])
  const crystalDirection = desk?.conclusion ? home?.directions?.find((d) => d.crystallizations.some((c) => c.conclusion_id === desk.conclusion!.id)) : undefined

  const question = desk?.question.text ?? ""
  const journey = desk ? journeyStage(desk, state, Boolean(crystalDirection)) : undefined
  const uniqueKeywords = useMemo(() => [...new Set(state.keywordsText.split(/[;；]/).map((k) => k.trim()).filter(Boolean))], [state.keywordsText])
  const chosen: DialogueCandidate[] = state.candidates.filter((c) => state.selected.includes(c.locator))
  const corpusIds = chosen.filter((c) => c.material_id).map((c) => c.material_id as string)
  const externalRefs = chosen.filter((c) => !c.material_id).map((c) => ({ locator: c.locator, excerpt: c.excerpt ?? c.title, url: c.url ?? null }))

  useEffect(() => {
    saveDialogueDraft(workspaceId, state)
  }, [workspaceId, state])
  // <800px 右侧面堆在左栏下方:打开一轮时把它滚进视野,否则点了 claim 看不到变化
  useEffect(() => { if (roundId && window.matchMedia?.("(max-width: 800px)").matches) panelRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }) }, [roundId, Boolean(desk)])
  // 点开的卡成了推导出的当前阶段 → 回到"跟随"模式,之后随阶段前进
  useEffect(() => { if (open !== null && open === journey?.current) setOpen(null) }, [open, journey?.current])

  function patch(partial: Partial<DialogueDraft>) { setState((prev) => ({ ...prev, ...partial })) }

  function invalidateDownstream(partial: Partial<DialogueDraft> = {}) {
    patch({ summary: undefined, summaryCheck: undefined, gapDraft: undefined, relatedWork: undefined, relatedWorkCheck: undefined, ...partial })
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
    setOpen(2)
  }

  function editKeywords(value: string) {
    const kept = state.selectedKeywords.filter((k) => value.includes(k))
    const selectionChanged = kept.join("|") !== state.selectedKeywords.join("|")
    patch({ keywordsText: value, ...(selectionChanged ? { selectedKeywords: kept } : {}) })
  }

  function toggleKeyword(keyword: string) {
    const has = state.selectedKeywords.includes(keyword)
    patch(has
      ? { selectedKeywords: state.selectedKeywords.filter((k) => k !== keyword) }
      : { selectedKeywords: [...state.selectedKeywords, keyword] })
  }

  // 勾选/取消关键词 → 只触发一次合并检索(单 query,500ms 防抖)。
  // 恢复的草稿已带候选 → 视为该组关键词已检索过,重进页面不重跑(否则会清空已选文献)。
  const searchedSelection = useRef(state.candidates.length > 0 ? state.selectedKeywords.join(" ") : "")
  useEffect(() => {
    const selection = state.selectedKeywords.join(" ")
    if (!selection || !question || selection === searchedSelection.current) return
    const timer = window.setTimeout(() => { searchedSelection.current = selection; void runSearch(selection) }, 500)
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
      invalidateDownstream({ candidates: result.candidates, selected: [], searchQueries: result.executed_queries })
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
      patch({ summary: result.text, summaryCheck: result })
      setOpen(3)
    } catch (e) { setError(e instanceof Error ? e.message : "梳理失败") } finally { setBusy(false) }
  }

  function setClaimKind(kind: ClaimKind) {
    const meta = CLAIM_KINDS.find((c) => c.kind === kind)
    patch(meta && !state.claimText.trim()
      ? { claimKind: kind, claimText: meta.skeleton }
      : { claimKind: kind })
  }

  // 固化 claim 并开审查轮:意图(含 PARK 来源谱系)跨重试复用同一组命令,审查轮失败后重试不会重复创建 claim。
  async function openReview() {
    if (busy || !state.claimText.trim() || hasClaimBlanks(state.claimText)) return
    const currentGeneration = routeGeneration.current, currentId = workspaceId
    claimIntent.current ??= { claim: command({ text: state.claimText.trim(), ...(state.claimKind && state.claimKind !== "custom" ? { kind: state.claimKind } : {}) }, 0) }
    const intent = claimIntent.current
    setBusy(true); setError(undefined)
    try {
      if (!intent.claimId) {
        intent.claimId = (await researchUniverse.createClaim(currentId, intent.claim)).result.claim_id
        if (!isCurrent(currentGeneration, currentId)) return
        if (sourceRef) intent.provenance = command({ claim_id: intent.claimId, capture_id: sourceRef.capture_id, release_id: sourceRef.id }, 0)
      }
      if (intent.provenance) { await researchUniverse.forgeProvenance(currentId, intent.provenance); if (!isCurrent(currentGeneration, currentId)) return }
      intent.review ??= command({}, 0)
      const review = await researchUniverse.startReview(intent.claimId, intent.review)
      if (!isCurrent(currentGeneration, currentId)) return
      claimIntent.current = undefined
      patch({ roundId: review.result.review_round_id, claimAck: false })
      setRewriting(false); setOpen(4)
      void load(() => isCurrent(currentGeneration, currentId))
      navigate(`/workspaces/${currentId}/rounds/${review.result.review_round_id}`)
    } catch (e) {
      if (!isCurrent(currentGeneration, currentId)) return
      setError(intent.claimId ? "主张已保存，但挑战尚未形成。可以重试，不会重复创建主张。" : (e instanceof Error ? e.message : "开审查轮失败"))
      // 建 claim 就 409:这条命令已作废,丢掉意图并按最新投影重读(若 claim 其实已落库,旅程会接上它);其他失败保留意图,同文重试幂等
      if ((e as { status?: number }).status === 409 && !intent.claimId) { claimIntent.current = undefined; void load(() => isCurrent(currentGeneration, currentId)) }
    } finally { if (isCurrent(currentGeneration, currentId)) setBusy(false) }
  }

  // 开轮失败留下的 claim(没有任何审查轮)在对抗卡上补开
  async function startRound(claimId: string) {
    if (busy) return
    setBusy(true); setError(undefined)
    try { const review = await researchUniverse.startReview(claimId, command({}, 0)); navigate(`/workspaces/${workspaceId}/rounds/${review.result.review_round_id}`) } catch (e) { setError(e instanceof Error ? e.message : "开审查轮失败") } finally { setBusy(false) }
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
        search_query: state.searchQueries.join(" ; ") || "(未检索,手工登记)",
        search_scope: "active",
        matched_locators: state.selected,
        external_refs: externalRefs,
        searched_at: new Date().toISOString().slice(0, 10),
        counterexample_invitation: invitation,
      }, 0))
      const gapId = proposed.result.gap_candidate_id
      await researchUniverse.confirmGapCandidate(gapId, command({ user_reason: "人审确认" }, 1))
      patch({ gapDraft: undefined, confirmedGapIds: [...state.confirmedGapIds, gapId] })
      setOpen(6)
      void load()
    } catch (e) { setError(e instanceof Error ? e.message : "登记 gap 失败") } finally { setBusy(false) }
  }

  async function draftRelatedWork() {
    if (busy || state.selected.length === 0) return
    setBusy(true); setError(undefined)
    try {
      const result = await researchUniverse.relatedWorkDraft(workspaceId, corpusIds, state.confirmedGapIds, externalRefs)
      patch({ relatedWork: result.text, relatedWorkCheck: result })
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
    setSearchedEmpty(false); setError(undefined); setOpen(null); setHasProgress(false)
  }

  if (!desk || !journey) return <section className="ru-state" role={error ? "alert" : undefined}>{error ?? "正在展开问题工作区…"}{error && <button className="ru-ink-button" onClick={() => void load()}>重试</button>}</section>
  const anchorReady = Boolean(selected && desk.note && note === desk.note.text && !savePending), releaseRefs = desk.park_release_refs ?? []
  const forgeRef = forgeReleaseRefId ? releaseRefs.find(item => item.id === forgeReleaseRefId) : undefined
  if (forgeReleaseRefId && !forgeRef) return <section className="ru-state" role="alert">未找到这份放行引用。<button className="ru-ink-button" onClick={() => navigate(`/workspaces/${workspaceId}`)}>回到工作区</button></section>
  const forging = Boolean(forgeRef)
  const position = desk.user_position ?? "exploring"
  const verdicts = desk.review_rounds.filter(r => r.verdict)
  // 待回应 = status=pending(同审查面「仍待回应」);投影里的已回应未裁决不算
  const pendingItems = desk.pending_challenges.filter(c => c.status === "pending")
  const { current, done } = journey
  const shown = open ?? current
  const pendingCount = pendingItems.length
  const confirmedGapCount = (desk.landscape?.gaps ?? []).filter((g) => g.status === "confirmed" || g.status === "corrected").length
  const gapClaimIds = new Set((desk.landscape?.gaps ?? []).flatMap((g) => (g.challenges ?? []).map((c) => c.claim_id))) // 反证 gap 写成的 claim
  const evidenceMaterials = (desk.materials ?? []).filter((m) => m.purpose === "evidence")
  const inDesk = (locator: string) => evidenceMaterials.some((m) => m.parse_status === "parsed" && m.source_locator === locator) // 同后端去重口径

  const positionControls = <div className="ru-lifecycle" aria-label="工作区位置">
    {!lifecycleForm && position === "exploring" && <button className="ru-outline-button" onClick={() => setLifecycleForm("pause")}>暂停</button>}
    {!lifecycleForm && (position === "paused" || position === "concluded") && <button className="ru-outline-button" onClick={() => setLifecycleForm("reopen")}>重开</button>}
    {lifecycleForm && <>
      <input className="ru-revival-input" aria-label={lifecycleForm === "pause" ? "暂停理由" : "重开理由"} value={lifecycleReason} onChange={(e) => setLifecycleReason(e.target.value)} placeholder={lifecycleForm === "pause" ? "暂停理由（可选）" : "为什么重开？（必填）"} />
      <button className="ru-outline-button" disabled={lifecycleForm === "reopen" && !lifecycleReason.trim()} onClick={() => void lifecycleAction(lifecycleForm)}>{lifecycleForm === "pause" ? "确认暂停" : "确认重开"}</button>
      <button className="ru-quiet-button" onClick={() => { setLifecycleForm(null); setLifecycleReason("") }}>取消</button>
    </>}
  </div>
  const branchForm = branchOpen ? <section className="ru-lifecycle-form" aria-labelledby="branch-title"><p className="ru-kicker">分支</p><h2 id="branch-title">把这个探索拆出一条后继问题</h2><p className="ru-reading-copy">Cui 不会替你推断要开什么问题；由你写出后继问题与理由。</p><label htmlFor="branch-question">后继问题</label><textarea id="branch-question" className="ru-conclusion-text" value={branchQuestion} onChange={(e) => setBranchQuestion(e.target.value)} placeholder="分支的新问题…" required /><label htmlFor="branch-reason">为什么分支</label><input id="branch-reason" className="ru-revival-input" value={branchReason} onChange={(e) => setBranchReason(e.target.value)} placeholder="写理由" required /><div className="ru-crystal-actions"><button className="ru-quiet-button" onClick={() => { setBranchOpen(false); setBranchQuestion(""); setBranchReason("") }}>取消</button><button className="ru-ink-button ru-active" disabled={branchPending || !branchQuestion.trim() || !branchReason.trim()} onClick={() => void branch()}>{branchPending ? "正在分支…" : "确认分支"}</button></div></section> : null
  const absorbForm = absorbOpen ? <section className="ru-lifecycle-form" aria-labelledby="absorb-title"><p className="ru-kicker">吸收</p><h2 id="absorb-title">把这一支并入另一条探索</h2><p className="ru-reading-copy">Cui 不会替你推断要并入哪里；由你写下目标工作区与理由。</p><label htmlFor="absorb-target">并入哪一条工作区</label><input id="absorb-target" className="ru-revival-input" value={absorbTarget} onChange={(e) => setAbsorbTarget(e.target.value)} placeholder="目标工作区" required /><label htmlFor="absorb-reason">为什么并入</label><input id="absorb-reason" className="ru-revival-input" value={absorbReason} onChange={(e) => setAbsorbReason(e.target.value)} placeholder="写理由" required /><div className="ru-crystal-actions"><button className="ru-quiet-button" onClick={() => { setAbsorbOpen(false); setAbsorbTarget(""); setAbsorbReason("") }}>取消</button><button className="ru-ink-button ru-active" disabled={absorbPending || !absorbTarget.trim() || !absorbReason.trim()} onClick={() => void absorb()}>{absorbPending ? "正在并入…" : "确认吸收"}</button></div></section> : null

  const oneLine: Record<number, string> = {
    1: state.skipHypotheses ? "不设假设,直接检索" : `候选假设 ${state.hypothesesText.split("\n").filter((l) => l.trim()).length} 条 · ${uniqueKeywords.length} 个检索词`,
    2: `检索并选入 ${state.selected.length} 篇`,
    3: `${state.summary ? "覆盖梳理已生成 · " : ""}已写 ${desk.claims.length} 条 claim`,
    4: "claim 已固化,审查轮已开",
    5: `✓ gap 已确认 ×${confirmedGapCount}`,
    6: position !== "concluded" ? POSITION_LABELS[position] : crystalDirection ? `结晶到方向「${crystalDirection.proposition}」` : "结论只留在本次探索", // 只在阶段 6 完成时显示
  }
  const rowLine = (n: number) => n === 4 && pendingCount > 0 ? `待回应 ${pendingCount} 条` : done[n - 1] ? oneLine[n] : STAGE_DESCRIPTIONS[n - 1]
  // 进 gap / 结晶阶段 = 右侧换成现状 / 账本;开着的审查轮先收起(在这两个阶段里再点开的轮才留在右侧)
  const goStage = (n: number) => { setOpen(n === current ? null : n); if ((n === 5 || n === 6) && roundId) navigate(`/workspaces/${workspaceId}`) }
  const openRound = (rid: string) => navigate(`/workspaces/${workspaceId}/rounds/${rid}`)

  const page = <section className="ru-journey" aria-labelledby="journey-title">
    <header className="ru-journey-head">
      <p className="ru-kicker">问题 · {POSITION_LABELS[position]}</p>
      <h1 id="journey-title">{desk.question.text}</h1>
      {positionControls}
    </header>
    {hasProgress && <p className="ru-resume-note" role="status">已恢复上次会话:当前在第 {current} 步({STAGE_LABELS[current - 1]})。<button type="button" className="ru-link-button" onClick={clearAll}>清空并重新开始</button></p>}
    {error && <p className="ru-error" role="alert">{error}</p>}
    {conflict && <button className="ru-quiet-button" onClick={reapply}>按最新版本重新应用</button>}

    {/* <800px:竖排行收起,只留这条顶部阶段条 + 展开的那张卡 */}
    <nav className="ru-journey-strip" aria-label="阶段条">
      {STAGE_LABELS.map((label, i) => <button key={label} type="button" className={i + 1 === current ? "is-current" : done[i] ? "is-done" : undefined} aria-pressed={i + 1 === shown} onClick={() => goStage(i + 1)}>{i + 1 === current ? "▶" : done[i] ? "✓" : i + 1} {label}{i === 3 && pendingCount > 0 && <small> {pendingCount}</small>}</button>)}
    </nav>
    <ol className="ru-journey-stages" aria-label="会话阶段">
      {STAGE_LABELS.map((label, i) => {
        const n = i + 1
        const isDone = done[i]
        const isCurrent = n === current
        const dot = <span className={isCurrent ? "ru-journey-dot is-current" : isDone ? "ru-journey-dot is-done" : "ru-journey-dot"} aria-hidden="true">{isCurrent ? "▶" : isDone ? "✓" : n}</span>
        if (n !== shown) {
          return <li key={label} className={isDone || isCurrent ? "ru-journey-stage is-row" : "ru-journey-stage is-row is-todo"} aria-current={isCurrent ? "step" : undefined}>{dot}
            <section className="ru-done-step" aria-label={`${isDone ? "已完成" : isCurrent ? "当前阶段" : "未开始"}:第 ${n} 步 ${label}`}>
              <button type="button" className="ru-done-step-toggle" onClick={() => goStage(n)}>
                <span className="ru-done-step-title">{label}</span>
                <span className={n === 4 && pendingCount > 0 ? "ru-done-step-line ru-pending-line" : "ru-done-step-line"}>{rowLine(n)}</span>
                <span className="ru-done-step-action">{isDone && !isCurrent ? "展开修改" : "打开"}</span>
              </button>
            </section>
          </li>
        }
        const inRevisit = !isCurrent
        return <li key={label} className="ru-journey-stage" aria-current={isCurrent ? "step" : undefined}>{dot}
          <section className={inRevisit ? "ru-stage-card ru-stage-card-revisit" : "ru-stage-card"}>
            <div className="ru-stage-card-title">
              <h2>{n}. {label}</h2>
              {n === 4 && pendingCount > 0 && <span className="ru-pending-line">待回应 {pendingCount} 条</span>}
              <small>{!inRevisit ? "当前阶段" : isDone ? "回看/修改中 · 内容会接续到后续步骤" : "不是当前阶段 · 不锁,可以先做"}</small>
            </div>
            {n === 1 && bodyOne()}
            {n === 2 && bodyTwo()}
            {n === 3 && bodyThree()}
            {n === 4 && bodyFour()}
            {n === 5 && bodyFive()}
            {n === 6 && bodySix()}
            {inRevisit && <button type="button" className="ru-link-button ru-link-close-revisit" onClick={() => setOpen(null)}>收起,回到第 {current} 步</button>}
          </section>
        </li>
      })}
    </ol>

    {chosen.length > 0 && <section className="ru-papers" aria-label="已选文献">
      <p className="ru-sec-head"><b>已选文献 · {chosen.length}</b><span className="ru-paper-meta">来自「选料」· 本机草稿</span></p>
      <ul className="ru-plain">{chosen.map((c) => <li key={c.locator} className="ru-paper">
        <div><span className="ru-paper-title">{c.title}</span><span className="ru-paper-meta">{c.source && c.source !== "corpus" ? `${c.source} · ` : "语料 · "}{c.locator}</span></div>
        {inDesk(c.locator) ? <span className="ru-in-desk">✓ 已在证据台</span> : <button type="button" className="ru-outline-button" disabled={Boolean(bringing)} onClick={() => void bringToDesk(c)}>{bringing === c.locator ? "带入中…" : "带进证据台"}</button>}
      </li>)}</ul>
    </section>}

    <details className="ru-journey-tools">
      <summary>工具<small>探索稿 · 手动加一份材料 · PARK 放行引用</small></summary>
      <details className="ru-journey-tool">
        <summary>探索稿<small>{desk.anchors.length} 个锚点</small></summary>
        <div className="ru-journey-tool-body">
          <div className="ru-surface-heading"><small>自由记录观察、猜测和未成形判断。Cui 不会在这里回复，也不会自动把内容升格为 Claim 或证据。</small><button className="ru-quiet-button" disabled={savePending} onClick={() => void saveNote()}>保存当前版本</button></div>
          <textarea aria-label="探索稿" className="ru-note" value={note} onChange={(e) => editNote(e.target.value)} onSelect={(e) => { const t = e.currentTarget; const selected_text = t.value.slice(t.selectionStart, t.selectionEnd); setSelected(note === desk.note?.text && selected_text ? { start: t.selectionStart, end: t.selectionEnd, selected_text } : undefined) }} placeholder="写下观察、猜测、反例或尚未成形的判断。" />
          <button className="ru-quiet-button" disabled={!anchorReady} onClick={() => void anchor()}>保留所选片段</button>
        </div>
      </details>
      <details className="ru-journey-tool">
        <summary>手动加一份材料<small>已带入 {desk.materials?.length ?? 0} 份</small></summary>
        <div className="ru-journey-tool-body">
          <p className="ru-challenge-note">材料先中立进入，保存不可变摘录；进入时它不声明支持或反对任何 claim。</p>
          <form className="ru-material-form" onSubmit={(e) => { e.preventDefault(); void addMaterial() }}><label htmlFor="material-source">来源（可选）</label><input id="material-source" value={materialSource} onChange={(e) => setMaterialSource(e.target.value)} placeholder="标题 / 链接 / 作者……" /><label htmlFor="material-excerpt">摘录或观察</label><textarea id="material-excerpt" value={materialExcerpt} onChange={(e) => setMaterialExcerpt(e.target.value)} placeholder="写下不可变摘录；保存后不可改写。" required /><fieldset className="ru-material-purpose"><legend>它进入这个问题，暂时是：</legend><label><input type="radio" name="material-purpose" checked={materialPurpose === "evidence"} onChange={() => setMaterialPurpose("evidence")} /> 待取证材料</label><label><input type="radio" name="material-purpose" checked={materialPurpose === "reference"} onChange={() => setMaterialPurpose("reference")} /> 只作探索参考</label></fieldset><label className="ru-material-unparsable"><input type="checkbox" checked={materialUnparsable} onChange={(e) => setMaterialUnparsable(e.target.checked)} /> 这段摘录我无法判断</label><button className="ru-ink-button ru-active" disabled={materialPending || !materialExcerpt.trim()}>{materialPending ? "正在带入…" : "带入材料"}</button></form>
          {(desk.materials?.length ?? 0) > 0 && <div className="ru-materials-list"><p className="ru-kicker">已带入材料</p>{desk.materials!.map((m) => <article key={m.id} className="ru-material-card"><p className="ru-reading-copy">{m.excerpt}</p><p className="ru-provenance">{m.source_locator ?? "无来源定位"} · {m.purpose === "evidence" ? "待取证材料" : "只作探索参考"} · {m.parse_status === "failed" ? "无法判断" : "已解析"}</p></article>)}</div>}
        </div>
      </details>
      <details className="ru-journey-tool">
        <summary>PARK 放行引用<small>{releaseRefs.length}</small></summary>
        <div className="ru-journey-tool-body">
          {releaseRefs.length === 0 && <p className="ru-edge-empty">这个问题没有来自 PARK 的放行引用。</p>}
          {releaseRefs.map(ref => <p key={ref.id} className="ru-provenance">来自密封 PARK 原件的放行引用 · {ref.provisional_role}{!forging && <> · <a href={`/workspaces/${workspaceId}/forge/${ref.id}`}>从此原件锻造自写 claim</a> · <button className="ru-quiet-button" onClick={() => setSourceRef(sourceRef?.id === ref.id ? undefined : ref)}>{sourceRef?.id === ref.id ? "不作为本次 claim 来源" : "作为本次 claim 来源"}</button></>}</p>)}
        </div>
      </details>
    </details>
  </section>
  // 右侧聚焦面:锻 / 审查轮(gap、结晶阶段里收起 = 回到现状、账本)/ gap 阶段的现状图景 / 结晶阶段的账本 / 都没开时一行安静提示
  const panel = forging ? <ReleaseForge workspaceId={workspaceId} releaseRef={forgeRef!} />
    : roundId ? <ReviewRoundDesk key={roundId} roundId={roundId} fromGap={gapClaimIds.has(desk.review_rounds.find((r) => r.id === roundId)?.claim_id ?? "")} onClose={() => navigate(`/workspaces/${workspaceId}`)} closeLabel={shown === 5 ? "回到现状" : shown === 6 ? "回到账本" : undefined} onLoaded={() => void load()} literature={{ selection: chosen.length > 0 ? { material_ids: corpusIds, external_refs: externalRefs } : undefined, evidence: evidenceMaterials }} citable={{ materials: evidenceMaterials, anchors: desk.anchors }} />
    : shown === 6 ? <LedgerPanel claims={desk.claims} rounds={desk.review_rounds} pending={pendingItems} landscape={desk.landscape} fromGap={gapClaimIds} onOpen={openRound} />
    : shown === 5 && desk.landscape ? <LandscapePanel landscape={desk.landscape} rounds={desk.review_rounds} onOpen={openRound} coverage={{ summary: state.summary, papers: chosen.map((c) => ({ locator: c.locator, title: c.title, relation: c.relation ? RELATION_LABELS[c.relation.kind] ?? c.relation.kind : undefined })) }} />
    : <div className="ru-panel-empty"><p className="ru-kicker">审查轮</p><p>{shown === 4 ? "点一条 claim，它的审查轮在这里打开；左栏保持可见，不离开这一页。" : "从「对抗」打开一条 claim 的审查轮。"}</p></div>
  return <div className="ru-journey-layout">{page}<aside ref={panelRef} className="ru-journey-panel" aria-label="聚焦面">{panel}</aside></div>

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
        <button type="button" className="ru-ink-button ru-active" disabled={!drafted} onClick={() => { patch({ hypothesesDone: true }); setOpen(2) }}>就用这版假设,去选料 →</button>
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
    const fixed = Boolean(state.roundId) && !rewriting
    const claimSaved = Boolean(claimIntent.current?.claimId)
    return <div className="ru-stage-body">
      {state.summary && <div className="ru-ai-block">
        <p className="ru-kicker">覆盖梳理(Cui 起草,临时;基于已选 {state.selected.length} 篇)</p>
        <p className="ru-ai-content">{state.summary}</p>
        <CitationCheckList report={state.summaryCheck} />
        <div className="ru-secondary-row">
          <button type="button" className="ru-quiet-button" disabled={busy} onClick={() => void summarize()}>重新梳理</button>
        </div>
      </div>}
      {fixed
        ? <div>
          <p className="ru-ok-note">claim 已固化,对抗在第 4 步等你去看审查轮;这里只读回看。</p>
          <div className="ru-secondary-row">
            <button type="button" className="ru-quiet-button" onClick={() => setRewriting(true)}>再写一条 claim</button>
            <span className="ru-muted-note">已入轨迹的 claim 不改写;在这里改写 = 再写一条新 claim。</span>
          </div>
        </div>
        : <div>
          <p className="ru-copy">读上面的覆盖梳理,写你对文献格局的一句判断。探索性综述不需要论文式论点——共识、分歧、空缺都算,审查轮会替它找反例;打不烂的才写进综述正文。claim 由你签名,Cui 只攻击。</p>
          <div className="ru-kind-row" role="group" aria-label="claim 类型">
            {CLAIM_KINDS.map((c) => <button key={c.kind} type="button" className={state.claimKind === c.kind ? "ru-chip ru-chip-on" : "ru-chip"} onClick={() => setClaimKind(c.kind)}>{c.label}</button>)}
          </div>
          <p className="ru-quiet-hint">点类型会把骨架句填进下方文本框(____ 处填空),再由你写实;选"自写立场"或直接改即可。</p>
          {sourceRef && <p className="ru-provenance">本次 claim 将记录来源:密封 PARK 原件的放行引用 · {sourceRef.provisional_role}(可在「工具 · PARK 放行引用」取消)</p>}
          <div className="ru-material-form">
            <label htmlFor="claim">由你写下的 claim</label>
            <textarea id="claim" className="ru-conclusion-text" rows={5} value={state.claimText} disabled={busy || claimSaved} onChange={(e) => { patch({ claimText: e.target.value }); claimIntent.current = undefined }} placeholder="读了这些之后,你究竟要断言什么?" />
          </div>
          <div className="ru-stage-actions">
            {rewriting && <button type="button" className="ru-link-button" onClick={() => setRewriting(false)}>取消</button>}
            <button type="button" className="ru-ink-button ru-active" disabled={busy || !state.claimText.trim() || hasClaimBlanks(state.claimText)} onClick={() => void openReview()}>{busy ? "正在固化…" : claimSaved ? "重新形成挑战" : "固化 claim 并开审查轮"}</button>
            {hasClaimBlanks(state.claimText) && <span className="ru-muted-note">还有 ____ 没填</span>}
          </div>
        </div>}
    </div>
  }

  function bodyFour() {
    if (desk!.claims.length === 0) return <div className="ru-stage-body"><p className="ru-edge-empty">还没有固化的 claim。先在「覆盖与 claim」写一条,审查轮会在这里接上。</p></div>
    // 按 claim_id 分组;数组顺序最后一条 = 最新轮(rounds[].sequence 是该轮自身计数,不是全局序)
    const rows = desk!.claims.map((claim) => { const rounds = desk!.review_rounds.filter((r) => r.claim_id === claim.id); return { claim, count: rounds.length, latest: rounds.at(-1) } })
    const card = ({ claim, count, latest }: (typeof rows)[number]) => {
      const pending = latest ? pendingItems.filter((c) => c.review_round_id === latest.id).length : 0
      const isOpen = Boolean(latest && latest.id === roundId)
      const meta = <span className="ru-claim-meta">
        {gapClaimIds.has(claim.id) && <span className="ru-tag">来自 gap</span>}
        {latest ? <span>审查轮 {String(count).padStart(2, "0")}</span> : <span>未开审查轮</span>}
        {latest?.verdict ? <span className="ru-decided">已裁决 · {VERDICT_LABELS[latest.verdict.verdict_type]}</span> : pending > 0 ? <span className="ru-pending-line">待回应 {pending} 条</span> : latest && <span>未裁决</span>}
        {isOpen && <span className="ru-open-mark">审查面已打开</span>}
      </span>
      const tone = latest?.verdict ? " is-decided" : pending > 0 ? "" : " is-quiet"
      return <li key={claim.id}>{latest
        ? <button type="button" className={`ru-claim${tone}${isOpen ? " is-open" : ""}`} aria-current={isOpen || undefined} onClick={() => navigate(`/workspaces/${workspaceId}/rounds/${latest.id}`)}><span className="ru-claim-text">{claim.text}</span>{meta}</button>
        : <div className={`ru-claim${tone}`}><span className="ru-claim-text">{claim.text}</span>{meta}<button type="button" className="ru-quiet-button" disabled={busy} onClick={() => void startRound(claim.id)}>开审查轮</button></div>}</li>
    }
    const undecided = rows.filter((r) => !r.latest?.verdict), decided = rows.filter((r) => r.latest?.verdict)
    return <div className="ru-stage-body">
      <p className="ru-quiet-hint">点一条 claim，它的审查轮在<span className="ru-wide">右侧</span><span className="ru-narrow">下方</span>打开。</p>
      {undecided.length > 0 && <ul className="ru-claims" aria-label="未裁决的 claim">{undecided.map(card)}</ul>}
      {decided.length > 0 && <details className="ru-claims-fold" open><summary>已裁决 · {decided.length}</summary><ul className="ru-claims" aria-label="已裁决的 claim">{decided.map(card)}</ul></details>}
      <div className="ru-stage-actions">
        <button type="button" className="ru-quiet-button" onClick={() => { setRewriting(true); setOpen(3) }}>再写一条 claim</button>
        {verdicts.length === 0 && <span className="ru-muted-note ru-no-verdict">尚无裁决</span>}
        <button type="button" className="ru-ink-button ru-active" onClick={() => { patch({ claimAck: true }); goStage(5) }}>继续到 gap</button>
      </div>
    </div>
  }

  // gap 阶段卡(S5 一条路径):gap 列表 + 写一个 gap。起草可选(要本机选料),手写同样能提交;提交即确认。
  function bodyFive() {
    const landscape = desk!.landscape, gaps = landscape?.gaps ?? []
    const draft = state.gapDraft ?? { coverage_statement: "", counterexample_invitation: "" }
    const written = Boolean(draft.coverage_statement.trim() || draft.counterexample_invitation.trim())
    const noLocalDraft = state.selected.length === 0
    return <div className="ru-stage-body">
      {landscape && <p className="ru-quiet-hint">现状图景在<span className="ru-wide">右侧</span><span className="ru-narrow">下方</span>:存活 claim {survivingClaims(landscape).length} · 已确认取证 {landscape.confirmed_facts.length} · 已确认 gap {confirmedGapCount}</p>}
      {gaps.length > 0 && <><p className="ru-col-title">本问题的 gap · {gaps.length}</p><GapList workspaceId={workspaceId} gaps={gaps} onChanged={() => void load()} onOpen={openRound} /></>}
      <p className="ru-col-title">{gaps.length > 0 ? "再写一个 gap" : "写一个 gap"}</p>
      <div className="ru-secondary-row">
        <button type="button" className="ru-quiet-button" disabled={busy || noLocalDraft} onClick={() => void draftGap()}>{busy ? "起草中…" : written ? "让 Cui 重新起草(覆盖下面的草稿)" : "让 Cui 起草 gap 候选"}</button>
        <span className="ru-muted-note">{noLocalDraft ? "这台设备上没有选料草稿,起草不可用;可以直接手写。" : "或者直接手写;你改,你署名"}</span>
      </div>
      <p className="ru-quiet-hint">检索记录(实际执行):{state.searchQueries.join(" ; ") || "(未检索,手工登记)"}</p>
      <div className="ru-material-form">
        <label htmlFor="d-coverage">覆盖范围声明(哪些已被覆盖、缺口在哪)</label>
        <textarea id="d-coverage" className="ru-conclusion-text" value={draft.coverage_statement} placeholder="至少 10 个字:现有文献覆盖了……但没有覆盖……" onChange={(e) => patch({ gapDraft: { ...draft, coverage_statement: e.target.value, citation_checks: [], citation_check_status: "ok" } })} /* 改写后旧核对不再适用 */ />
        <CitationCheckList report={state.gapDraft} />
        <label htmlFor="d-invitation">邀请反例</label>
        <input id="d-invitation" className="ru-revival-input" value={draft.counterexample_invitation} placeholder="什么样的研究会推翻这个 gap?" onChange={(e) => patch({ gapDraft: { ...draft, counterexample_invitation: e.target.value } })} />
      </div>
      <div className="ru-stage-actions">
        <span className="ru-muted-note">提交即确认,入轨迹</span>
        <button type="button" className="ru-ink-button ru-active" disabled={busy || draft.coverage_statement.trim().length < 10 || !draft.counterexample_invitation.trim()} onClick={() => void proposeGap()}>{busy ? "提交中…" : "提交并确认这个 gap"}</button>
      </div>
    </div>
  }

  // 结晶阶段卡(S6):确认位置(6 类结论 + 理由,暂缓须写复活条件)→ 同一张卡接着定这次结论去哪;拆分/转向时次级动作是分支、吸收。
  // 依据在右侧账本;有已确认 gap 后卡底是次级的导出区块(S7:related-work 不再是旅程终点)。
  function bodySix() {
    const recorded = position === "exploring" || position === "paused" ? null : desk!.conclusion
    const type = recorded ? recorded.type : conclusionType
    const allGaps = desk!.landscape?.gaps ?? [], gaps = allGaps.filter((g) => g.status === "confirmed" || g.status === "corrected")
    const directions = home?.directions ?? []
    const elsewhere = position === "branched" ? desk!.successor_workspace_id : desk!.absorb_target_workspace_id
    const locateHint = !conclusionType ? "先选结论类型" : !conclusionText.trim() || !conclusionReason.trim() ? "写下结论与理由" : conclusionType === "deferred" && !revivalCondition.trim() ? "暂缓必须写复活条件" : ""
    const destHint = dest === "attach" && !destDirection ? "选一个方向" : dest === "new" && !signed ? "签名后才能新建" : ""
    const pickGap = (id: string) => { setDestGap(id); setProposition(gaps.find((g) => g.id === id)?.coverage_statement ?? ""); setSigned(false) }
    const side = type === "split_or_turn" && (position === "exploring" || position === "concluded") && <div>
      <div className="ru-secondary-row" role="group" aria-label="拆分/转向">
        <button type="button" className="ru-quiet-button" aria-pressed={branchOpen} onClick={() => { setBranchOpen(true); setAbsorbOpen(false) }}>分支出新问题</button>
        <button type="button" className="ru-quiet-button" aria-pressed={absorbOpen} onClick={() => { setAbsorbOpen(true); setBranchOpen(false) }}>吸收进另一个问题</button>
      </div>
      {branchForm}{absorbForm}
    </div>
    return <div className="ru-stage-body">
      <p className="ru-quiet-hint">结论的依据见<span className="ru-wide">右侧</span><span className="ru-narrow">下方</span>账本{pendingCount > 0 && <span className="ru-pending-line"> · 仍待回应 {pendingCount} 条——结晶不会关掉它们</span>}</p>
      {position === "paused" && <p className="ru-copy">这个问题已暂停;在页头「重开」后再确认位置。</p>}
      {position === "exploring" && <>
        <fieldset className="ru-conclusion-types"><legend>结论类型</legend>{CONCLUSION_OPTIONS.map((opt) => <label key={opt.type}><input type="radio" name="conclusion-type" checked={conclusionType === opt.type} onChange={() => setConclusionType(opt.type)} /><span>{opt.label}</span><small>{opt.note}</small></label>)}</fieldset>
        {side}
        <div className="ru-material-form ru-crystal-form">
          <label htmlFor="conclusion-text">结论</label>
          <textarea id="conclusion-text" className="ru-conclusion-text" rows={3} value={conclusionText} onChange={(e) => setConclusionText(e.target.value)} placeholder="用你自己的话写下这次探索的位置;Cui 不会替你总结。" />
          <label htmlFor="conclusion-reason">理由</label>
          <textarea id="conclusion-reason" className="ru-conclusion-text" rows={2} value={conclusionReason} onChange={(e) => setConclusionReason(e.target.value)} placeholder="依据账本里的哪些 claim、取证与 gap?" />
          {conclusionType === "deferred" && <><label htmlFor="revival-condition">复活条件（暂缓必填）</label><input id="revival-condition" className="ru-revival-input" value={revivalCondition} onChange={(e) => setRevivalCondition(e.target.value)} placeholder="什么出现时重新打开这个问题?" /></>}
        </div>
        <div className="ru-stage-actions">
          <span className="ru-muted-note">{locateHint}</span>
          <button type="button" className="ru-ink-button ru-active" disabled={concluding || Boolean(locateHint)} onClick={() => void conclude()}>{concluding ? "正在记录…" : "确认这次探索的位置"}</button>
        </div>
      </>}
      {recorded && <div className="ru-receipt">
        <p className="ru-provenance"><span className="ru-qdot" />位置已确认 · {CONCLUSION_OPTIONS.find((o) => o.type === recorded.type)?.label}</p>
        <p>{recorded.text}</p>
        {recorded.revival_condition && <p className="ru-provenance">复活条件:{recorded.revival_condition}</p>}
      </div>}
      {position === "concluded" && side}
      {(position === "branched" || position === "absorbed") && <p className="ru-receipt"><span className="ru-qdot" />{position === "branched" ? "已分支出新问题" : "已并入另一个问题"}{elsewhere && <> · <a href={`/workspaces/${elsewhere}`}>打开它</a></>}</p>}
      {position === "concluded" && recorded && (crystalDirection
        ? <div className="ru-receipt">
          <p><span className="ru-qdot" />已结晶到方向「{crystalDirection.proposition}」</p>
          <p className="ru-provenance">首页「方向地形」能看到这个方向和这条结晶。</p>
          <button type="button" className="ru-link-button" onClick={() => navigate(`/directions/${crystalDirection.id}?rephrase=1&source_conclusion=${encodeURIComponent(recorded.id)}`)}>促使我重述方向命题</button>
        </div>
        : state.keptLocal === recorded.id
          ? <div className="ru-receipt">
            <p><span className="ru-qdot" />这次结论只留在本次探索</p>
            <p className="ru-provenance">不挂方向;结论只留在这个问题的轨迹里。</p>
            <button type="button" className="ru-link-button" onClick={() => patch({ keptLocal: undefined })}>改为挂到方向</button>
          </div>
          : <>
            <fieldset className="ru-dest">
              <legend>这次结论去哪</legend>
              <div className="ru-dopt">
                <label><input type="radio" name="dest" checked={dest === "attach"} disabled={Boolean(home) && directions.length === 0} onChange={() => setDest("attach")} />挂到已有方向</label>
                {home && directions.length === 0 && <small>研究宇宙里还没有方向</small>}
                {dest === "attach" && <div className="ru-dopt-body">{home
                  ? <select className="ru-revival-input" aria-label="已有方向" value={destDirection} onChange={(e) => setDestDirection(e.target.value)}><option value="">选择一个方向…</option>{directions.map((d) => <option key={d.id} value={d.id}>{d.proposition}</option>)}</select>
                  : <span className="ru-muted-note">{homeError ? <>未能读取方向列表 <button type="button" className="ru-link-button" onClick={() => void loadHome()}>重试</button></> : "正在读取方向…"}</span>}</div>}
              </div>
              <div className="ru-dopt">
                <label><input type="radio" name="dest" checked={dest === "new"} disabled={gaps.length === 0} onChange={() => { setDest("new"); if (!destGap && gaps[0]) pickGap(gaps[0].id) }} />从 gap 新建方向</label>
                <small>{gaps.length === 0 ? "还没有已确认的 gap" : "命题用所选 gap 的文本预填;你签名后才生效"}</small>
                {dest === "new" && <div className="ru-dopt-body">
                  {gaps.length > 1 && <select className="ru-revival-input" aria-label="用哪个 gap 预填" value={destGap} onChange={(e) => pickGap(e.target.value)}>{gaps.map((g) => <option key={g.id} value={g.id}>gap {String(allGaps.indexOf(g) + 1).padStart(2, "0")} · {short(g.coverage_statement, 26)}</option>)}</select>}
                  <label htmlFor="direction-proposition">方向命题</label>
                  <textarea id="direction-proposition" className="ru-conclusion-text" rows={4} value={proposition} onChange={(e) => { setProposition(e.target.value); setSigned(false) }} />
                  {signed
                    ? <p className="ru-ok-note">已签名 · 再改命题会撤销签名</p>
                    : <div className="ru-secondary-row"><button type="button" className="ru-outline-button" disabled={!proposition.trim()} onClick={() => setSigned(true)}>签名：这是我的方向命题</button><span className="ru-muted-note">预填自 gap,可以改写;签名这一下才生效</span></div>}
                </div>}
              </div>
              <div className="ru-dopt">
                <label><input type="radio" name="dest" checked={dest === "local"} onChange={() => setDest("local")} />只留在本次探索</label>
                <small>不挂方向;结论只留在这个问题的轨迹里</small>
              </div>
            </fieldset>
            <div className="ru-stage-actions">
              <span className="ru-muted-note">{destHint}</span>
              <button type="button" className="ru-ink-button ru-active" disabled={destBusy || !dest || Boolean(destHint)} onClick={() => void settleDestination()}>{destBusy ? "正在结晶…" : dest === "attach" ? "挂到这个方向" : dest === "new" ? "新建方向并结晶" : dest === "local" ? "只留在本次" : "选择去向"}</button>
            </div>
          </>)}
      {confirmedGapCount > 0 && <section className="ru-export" aria-label="导出 related-work 草稿">
        <p className="ru-export-head"><b>导出 related-work 草稿</b><span className="ru-muted-note">基于已选文献与已确认 gap · 不入轨迹</span></p>
        {state.relatedWork
          ? <>
            <pre className="ru-dialogue-pre">{state.relatedWork}</pre>
            <CitationCheckList report={state.relatedWorkCheck} />
            <div className="ru-secondary-row">
              <button type="button" className="ru-quiet-button" onClick={() => void copyDraft()}>{copied ? "已复制" : "复制"}</button>
              <button type="button" className="ru-quiet-button" onClick={downloadDraft}>下载 .md</button>
              <button type="button" className="ru-quiet-button" disabled={busy} onClick={() => void draftRelatedWork()}>{busy ? "生成中…" : "重新生成"}</button>
            </div>
          </>
          : <div className="ru-secondary-row">
            <button type="button" className="ru-outline-button" disabled={busy || state.selected.length === 0} onClick={() => void draftRelatedWork()}>{busy ? "生成中…" : "生成草稿"}</button>
            {state.selected.length === 0 && <span className="ru-muted-note">这台设备上没有选料草稿,生成不可用。</span>}
          </div>}
      </section>}
    </div>
  }
}
