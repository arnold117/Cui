import { useState } from "react"
import { command, researchUniverse } from "../api"
import { GapChallengeComposer } from "./GapChallengeComposer"
import { RELATION_LABELS } from "./EvidenceSurface"
import type { GapCandidate, GapChallenge, WorkspaceLandscape } from "../types"

const STATUS_LABELS: Record<GapCandidate["status"], string> = {
  pending: "待你裁决",
  confirmed: "已确认 gap",
  corrected: "已修订",
  rejected: "已拒绝",
  withdrawn: "已撤回",
}
/** 反证进展只展示,gap 状态由用户自己裁决(永不自动化定见) */
function outcomeLabel(outcome: string): string {
  if (outcome === "open") return "反证中"
  if (outcome === "survived") return "反证结果:未能推翻"
  if (outcome === "refuted") return "反证结果:已被推翻 — 这个 gap 可能需要你重新判断"
  return `反证结果:${VERDICT_LABELS[outcome] ?? outcome}`
}
export const VERDICT_LABELS: Record<string, string> = {
  survived: "存活", circumstantial: "有条件存活", refuted: "已证伪", not_worth: "不值一探", boundary: "划界", open: "未裁决",
}
const short = (text: string, n: number) => text.length > n ? `${text.slice(0, n)}…` : text
/** 指向聚焦面的文案:宽屏「右侧」,<800px「下方」 */
const Where = () => <><span className="ru-wide">右侧</span><span className="ru-narrow">下方</span></>
/** 投影的 alive_claims 含未裁决的;「存活」只算已裁决且未被证伪/不值一探的 */
export const survivingClaims = (landscape: WorkspaceLandscape) => landscape.alive_claims.filter((c) => (landscape.claim_verdicts[c.id] ?? "open") !== "open")

function GapChallengeLines({ challenges, onOpen }: { challenges: GapChallenge[]; onOpen: (roundId: string) => void }) {
  return <>{challenges.map((c) => c.round_id
    ? <button key={c.claim_id} type="button" className="ru-link-button ru-gap-claim" onClick={() => onOpen(c.round_id!)}>反证 claim「{short(c.claim_text, 24)}」· {outcomeLabel(c.outcome)} → 在<Where />打开</button>
    : <p key={c.claim_id} className="ru-provenance">反证 claim「{short(c.claim_text, 24)}」· {outcomeLabel(c.outcome)}</p>)}</>
}

/** gap 阶段卡上的 gap 列表:旧登记路径留下的待裁决 gap 照常可确认/拒绝;已确认的可发起反证。 */
export function GapList({ workspaceId, gaps, onChanged, onOpen }: { workspaceId: string; gaps: GapCandidate[]; onChanged: () => void; onOpen: (roundId: string) => void }) {
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

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

  return <>
    {error && <p className="ru-error" role="alert">{error}</p>}
    <ul className="ru-gaps" aria-label="本问题的 gap">{gaps.map((gap, i) => <li key={gap.id} className="ru-gap">
      <p className="ru-gap-head"><span className={`ru-gap-status is-${gap.status}`}>{STATUS_LABELS[gap.status]}</span><span className="ru-provenance">gap {String(i + 1).padStart(2, "0")}{gap.decision_reason ? ` · ${gap.decision_reason}` : ""}</span></p>
      <p className="ru-gap-text">{gap.coverage_statement}</p>
      <p className="ru-provenance">邀请反例:{gap.counterexample_invitation}</p>
      <p className="ru-provenance">检索:{gap.search_record.query}{gap.search_record.matched_locators.length > 0 ? ` · 命中 ${gap.search_record.matched_locators.length} 篇` : ""}{gap.search_record.searched_at ? ` · ${gap.search_record.searched_at}` : ""}</p>
      {gap.status === "pending" && <div className="ru-secondary-row"><button className="ru-quiet-button" disabled={busy} onClick={() => void decide(gap, "reject")}>拒绝</button><button className="ru-quiet-button" disabled={busy} onClick={() => void decide(gap, "confirm")}>确认这个 gap</button></div>}
      {gap.challenges && gap.challenges.length > 0 && <GapChallengeLines challenges={gap.challenges} onOpen={onOpen} />}
      {(gap.status === "confirmed" || gap.status === "corrected") && <GapChallengeComposer workspaceId={workspaceId} gapId={gap.id} coverage={gap.coverage_statement} />}
    </li>)}</ul>
  </>
}

/** 本机草稿里的覆盖梳理与已选文献(relation = 与假设的支撑关系,已译成标签;旧草稿可能没有) */
export interface LocalCoverage { summary?: string; papers: { locator: string; title: string; relation?: string }[] }

/**
 * gap 阶段的右侧聚焦面:现状图景(只读)。存活 claim 与取证来自 desk.landscape;点存活 claim 在同一面打开它的最新一轮。
 * 覆盖梳理只在本机草稿里 → 有草稿才显示,换设备时整段不出现。
 */
export function LandscapePanel({ landscape, rounds, onOpen, coverage }: { landscape: WorkspaceLandscape; rounds: { id: string; claim_id?: string }[]; onOpen: (roundId: string) => void; coverage?: LocalCoverage }) {
  const kept = survivingClaims(landscape)
  const others = Object.keys(landscape.claim_verdicts).length - kept.length
  const fromGap = new Set(landscape.gaps.flatMap((g) => (g.challenges ?? []).map((c) => c.claim_id)))
  return <section className="ru-landscape-panel" aria-labelledby="landscape-title">
    <p className="ru-kicker">现状图景 · 只读</p>
    <h2 id="landscape-title">写 gap 时可以倚靠的</h2>
    <section>
      <p className="ru-col-title">存活的 claim · {kept.length}</p>
      {kept.length > 0 ? <ul className="ru-plain">{kept.map((c) => {
        const own = rounds.filter((r) => r.claim_id === c.id), latest = own.at(-1)
        const meta = <span className="ru-provenance"><span className="ru-decided">{VERDICT_LABELS[landscape.claim_verdicts[c.id]] ?? landscape.claim_verdicts[c.id]}</span>{fromGap.has(c.id) && " · 来自 gap"}{latest && ` · 审查轮 ${String(own.length).padStart(2, "0")}`}</span>
        return <li key={c.id}>{latest
          ? <button type="button" className="ru-landscape-claim" onClick={() => onOpen(latest.id)}>{meta}<span className="ru-gap-text">{c.text}</span></button>
          : <div className="ru-landscape-claim">{meta}<span className="ru-gap-text">{c.text}</span></div>}</li>
      })}</ul> : <p className="ru-ledger-empty">还没有裁决为存活的 claim。</p>}
      {others > 0 && <p className="ru-provenance">另有 {others} 条 claim 未裁决或未存活，在「对抗」里。</p>}
    </section>
    <section>
      <p className="ru-col-title">已确认的取证事实 · {landscape.confirmed_facts.length}</p>
      {landscape.confirmed_facts.length > 0 ? <ul className="ru-plain ru-landscape-facts">{landscape.confirmed_facts.map((f) => <li key={f.candidate_id}>
        <p className="ru-provenance"><span className="ru-qdot" />{RELATION_LABELS[f.relation] ?? f.relation} · {f.material_locator ?? "无定位"} → claim「{short(f.claim_text, 18)}」</p>
        {f.decision_reason && <p className="ru-gap-text">{f.decision_reason}</p>}
      </li>)}</ul> : <p className="ru-ledger-empty">还没有确认的取证事实。</p>}
    </section>
    {coverage && (coverage.summary || coverage.papers.length > 0) && <section>
      <p className="ru-col-title">{coverage.summary ? "覆盖梳理 · " : ""}已选文献 {coverage.papers.length} 篇</p>
      {coverage.summary && <p className="ru-ai-content">{coverage.summary}</p>}
      {coverage.papers.length > 0 && <ul className="ru-plain">{coverage.papers.map((p) => <li key={p.locator} className="ru-provenance">{p.title} · {p.locator}{p.relation && ` · 与假设:${p.relation}`}</li>)}</ul>}
    </section>}
  </section>
}
