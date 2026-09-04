import type { DialogueCandidate, GapDraftFields } from "./types"

/** 文献探讨会话的类型:claim 步的起草辅助(不入事件;仅存本机草稿)。 */
export type ClaimKind = "consensus" | "division" | "vacancy" | "custom"

export const CLAIM_KINDS: { kind: ClaimKind; label: string; hint: string; skeleton: string }[] = [
  { kind: "consensus", label: "共识断言", hint: "这批文献在哪一点上趋于一致", skeleton: "这批文献在 ______ 上趋于一致:______。" },
  { kind: "division", label: "分歧断言", hint: "这批文献在哪个轴上分成哪几派", skeleton: "文献在 ______ 上分成两派:一派认为 ______,另一派认为 ______。" },
  { kind: "vacancy", label: "空缺断言", hint: "这批文献普遍没回答什么", skeleton: "这批文献大多只处理了 ______,对 ______ 几乎没有系统回答。" },
  { kind: "custom", label: "自写立场", hint: "按自己的话写一句可被攻击的断言", skeleton: "" },
]

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
  searchQuery: string
  summary?: string
  claimKind?: ClaimKind
  claimText: string
  roundId?: string
  /** claim 固化后停在第 4 步,直到用户看过审查轮情况并点"继续起草 gap"。 */
  claimAck?: boolean
  gapDraft?: GapDraftFields
  confirmedGapIds: string[]
  relatedWork?: string
  skipHypotheses?: boolean
  savedAt?: string
}

export function emptyDraft(workspaceId: string): DialogueDraft {
  return { v: 2, workspaceId, hypothesesText: "", hypothesesDone: false, keywordsText: "", selectedKeywords: [], candidates: [], selected: [], searchQuery: "", claimText: "", claimAck: false, confirmedGapIds: [] }
}

export const STAGE_COUNT = 6

export const STAGE_LABELS = ["出发点", "选料", "覆盖与 claim", "对抗", "gap", "收尾"]

export const STAGE_DESCRIPTIONS = [
  "候选假设与检索词(起草后可改,点确认才前进)",
  "检索、读每篇的观点与支撑关系,选 1–5 篇后梳理覆盖",
  "读覆盖梳理,用骨架或自己的话写出 claim",
  "审查轮:应答/裁决,或追加文献发难;看过后再收尾",
  "起草、署名并确认缺口",
  "生成 related-work 综述草稿并导出",
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

/**
 * 按草稿内容推导当前应停在哪一步(1..6)。
 * 已固化入轨迹的东西(claim/审查轮/gap)也参与推导,使"别处回来后能接上"。
 */
/**
 * 按内容推导当前停在哪一步(1..6)。门控:
 * 1 出发点:假设需用户点"就用这版"确认;2 选料:等覆盖梳理生成;
 * 3 覆盖与 claim:等 claim 固化(roundId);4 对抗:等用户看过审查轮(claimAck);
 * 5 gap:等确认 ≥1 个;6 收尾。固化入轨迹的内容也参与推导,别处回来后能接上。
 */
export function contentStage(d: Pick<DialogueDraft, "hypothesesText" | "hypothesesDone" | "skipHypotheses" | "summary" | "roundId" | "claimAck" | "confirmedGapIds" | "relatedWork">): number {
  if (!d.skipHypotheses && !d.hypothesesDone) return 1
  if (!d.summary) return 2
  if (!d.roundId) return 3
  if (!d.claimAck) return 4
  if (d.confirmedGapIds.length === 0) return 5
  return 6
}

export interface DraftProgress { exists: boolean; stage: number; savedAt?: string }

/** 供工作区入口读取的摘要。 */
export function dialogueProgress(workspaceId: string): DraftProgress {
  const draft = loadDialogueDraft(workspaceId)
  const exists = Boolean(draft.hypothesesText || draft.skipHypotheses || draft.candidates.length || draft.summary || draft.claimText || draft.roundId || draft.confirmedGapIds.length || draft.relatedWork)
  return { exists, stage: contentStage(draft), savedAt: draft.savedAt }
}
