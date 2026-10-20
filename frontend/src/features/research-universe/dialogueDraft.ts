import type { CitationReport, DialogueCandidate, GapDraftFields, WorkspaceDesk } from "./types"

/** 文献探讨会话的类型:claim 步的起草辅助(不入事件;仅存本机草稿)。 */
export type ClaimKind = "consensus" | "division" | "vacancy" | "custom"

export const CLAIM_KINDS: { kind: ClaimKind; label: string; hint: string; skeleton: string }[] = [
  { kind: "consensus", label: "共识断言", hint: "这批文献在哪一点上趋于一致", skeleton: "这批文献在 ______ 上趋于一致:______。" },
  { kind: "division", label: "分歧断言", hint: "这批文献在哪个轴上分成哪几派", skeleton: "文献在 ______ 上分成两派:一派认为 ______,另一派认为 ______。" },
  { kind: "vacancy", label: "空缺断言", hint: "这批文献普遍没回答什么", skeleton: "这批文献大多只处理了 ______,对 ______ 几乎没有系统回答。" },
  { kind: "custom", label: "自写立场", hint: "按自己的话写一句可被攻击的断言", skeleton: "" },
]

/** 骨架占位(三个及以上连续下划线)未填完 → 不可固化。 */
export const hasClaimBlanks = (text: string) => /_{3,}/.test(text)

export interface DialogueDraft {
  v: 2
  workspaceId: string
  hypothesesText: string
  /** 用户看过并认可假设草稿(或改写完成);未认可前停在第 1 步,避免输入中途被顶走。 */
  hypothesesDone?: boolean
  keywordsText: string
  selectedKeywords: string[]
  candidates: DialogueCandidate[]
  selected: string[] // locators
  /** literature-search 实际执行的检索词(S20 可复现检索记录);LLM 建议词不入档。 */
  searchQueries: string[]
  summary?: string
  summaryCheck?: CitationReport
  claimKind?: ClaimKind
  claimText: string
  roundId?: string
  /** 用户点过"继续起草 gap"(本机标记,阶段 4 完成的条件之一)。 */
  claimAck?: boolean
  gapDraft?: GapDraftFields
  confirmedGapIds: string[]
  relatedWork?: string
  relatedWorkCheck?: CitationReport
  skipHypotheses?: boolean
  savedAt?: string
}

export function emptyDraft(workspaceId: string): DialogueDraft {
  return { v: 2, workspaceId, hypothesesText: "", hypothesesDone: false, keywordsText: "", selectedKeywords: [], candidates: [], selected: [], searchQueries: [], claimText: "", claimAck: false, confirmedGapIds: [] }
}

export const STAGE_COUNT = 6

export const STAGE_LABELS = ["出发点", "选料", "覆盖与 claim", "对抗", "gap", "结晶"]

export const STAGE_DESCRIPTIONS = [
  "候选假设与检索词(起草后可改,点确认才前进)",
  "检索、读每篇的观点与支撑关系,选 1–5 篇后梳理覆盖",
  "读覆盖梳理,用骨架或自己的话写出 claim",
  "审查轮:应答/裁决,或追加文献发难;看过后再去 gap",
  "起草、署名并确认缺口",
  "确认这次探索的位置(结晶/分支/吸收);导出 related-work 综述草稿",
]

export const DRAFT_KEY_PREFIX = "cui:dialogue-draft:v2:"
function storageKey(workspaceId: string) { return `${DRAFT_KEY_PREFIX}${workspaceId}` }
function legacyKey(workspaceId: string) { return `cui-dialogue-${workspaceId}` }

/** 运行时优先 localStorage(关页不丢);测试/受限环境退到 sessionStorage。 */
function resolveStorage(): Storage | null {
  try { const g = globalThis as { localStorage?: Storage }; if (g.localStorage && typeof g.localStorage.getItem === "function") return g.localStorage } catch { /* ignore */ }
  try { const g = globalThis as { sessionStorage?: Storage }; if (g.sessionStorage && typeof g.sessionStorage.getItem === "function") return g.sessionStorage } catch { /* ignore */ }
  return null
}

/** 读取草稿:v2(本地/会话)优先;兼容旧的 v1 sessionStorage 形状。 */
export function loadDialogueDraft(workspaceId: string): DialogueDraft {
  const store = resolveStorage()
  try {
    if (store) {
      const raw = store.getItem(storageKey(workspaceId))
      if (raw) return { ...emptyDraft(workspaceId), ...JSON.parse(raw) }
    }
  } catch { /* ignore */ }
  try {
    const legacy = sessionStorage.getItem(legacyKey(workspaceId))
    if (legacy) return { ...emptyDraft(workspaceId), ...JSON.parse(legacy) }
  } catch { /* ignore */ }
  return emptyDraft(workspaceId)
}

export function saveDialogueDraft(workspaceId: string, draft: DialogueDraft) {
  try {
    const store = resolveStorage()
    if (store) store.setItem(storageKey(workspaceId), JSON.stringify({ ...draft, workspaceId, savedAt: new Date().toISOString() }))
  } catch { /* quota/unavailable: 草稿是便利不是保证 */ }
}

export function clearDialogueDraft(workspaceId: string) {
  try {
    const store = resolveStorage()
    if (store) store.removeItem(storageKey(workspaceId))
    sessionStorage.removeItem(legacyKey(workspaceId))
  } catch { /* ignore */ }
}

export type JourneyDesk = Pick<WorkspaceDesk, "claims" | "review_rounds" | "pending_challenges" | "materials" | "landscape" | "user_position">

/**
 * 旅程阶段推导(spec-workspace-journey S1):服务端事实优先,本机草稿只补会话内进度。
 * done[i] = 第 i+1 阶段是否完成;current = 未结晶且有待回应挑战 ⇒ 对抗(4),否则第一个未完成的,全完成停在 6。
 * 待回应 = status=pending(同审查面账本);投影的 pending_challenges 还含已回应未裁决,那些不把阶段拽回对抗。
 * 结晶看 user_position 而非 conclusion:重开后 conclusion 仍在投影里,但阶段 6 要重新变为未完成。
 */
export function journeyStage(desk: JourneyDesk, d: Pick<DialogueDraft, "hypothesesDone" | "skipHypotheses" | "summary" | "claimAck">): { current: number; done: boolean[] } {
  const hasClaims = desk.claims.length > 0
  const gapDone = (desk.landscape?.gaps ?? []).some((g) => g.status === "confirmed" || g.status === "corrected")
  const crystallized = ["concluded", "branched", "absorbed"].includes(desk.user_position ?? "exploring")
  const done = [
    Boolean(d.hypothesesDone || d.skipHypotheses || hasClaims || (desk.materials?.length ?? 0) > 0),
    Boolean(d.summary) || hasClaims,
    hasClaims,
    Boolean(d.claimAck) || desk.review_rounds.some((r) => r.verdict) || gapDone,
    gapDone,
    crystallized,
  ]
  const current = !crystallized && desk.pending_challenges.some((c) => c.status === "pending") ? 4 : done.indexOf(false) + 1 || STAGE_COUNT
  return { current, done }
}

export interface DraftProgress { exists: boolean; savedAt?: string }

/** 本机是否已有会话进度(旅程页据此显示恢复横幅)。 */
export function dialogueProgress(workspaceId: string): DraftProgress {
  const draft = loadDialogueDraft(workspaceId)
  const exists = Boolean(draft.hypothesesText || draft.skipHypotheses || draft.candidates.length || draft.summary || draft.claimText || draft.roundId || draft.confirmedGapIds.length || draft.relatedWork)
  return { exists, savedAt: draft.savedAt }
}
