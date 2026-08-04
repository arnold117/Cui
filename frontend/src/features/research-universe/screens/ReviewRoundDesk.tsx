import { useEffect, useRef, useState } from "react"
import { researchUniverse } from "../api"
import type { ReviewRound } from "../types"

export function ReviewRoundDesk({ roundId }: { roundId: string }) {
  const [round, setRound] = useState<ReviewRound | null>(null)
  const [error, setError] = useState<string | null>(null)
  const generation = useRef(0)
  async function load() { const current = ++generation.current; try { const value = await researchUniverse.reviewRound(roundId); if (current === generation.current) { setError(null); setRound(value) } } catch (reason) { if (current === generation.current) setError(reason instanceof Error ? reason.message : "未能读取审查轮次。") } }
  useEffect(() => { void load(); return () => { generation.current++ } }, [roundId])
  if (error) return <section className="ru-state" role="alert"><p>未能打开审查轮次：{error}</p><button className="ru-ink-button" onClick={() => void load()}>重试</button></section>
  if (!round) return <section className="ru-state" aria-live="polite">正在读取审查快照…</section>
  const challenge = round.challenges[0]
  if (!challenge) return <section className="ru-state">这个审查轮次尚无待回应 challenge。</section>
  return <section className="ru-review" aria-labelledby="review-title"><p className="ru-kicker">审查轮次 · 不可变快照</p><h1 id="review-title">审查这一条 claim</h1><div className="ru-snapshot-grid"><article><h2>当时的问题</h2><p className="ru-reading-copy">{round.question_snapshot.text}</p><small>问题快照 {round.question_snapshot.version_id ?? round.question_snapshot.id ?? "已记录"}</small></article><article><h2>当时的 claim</h2><p className="ru-reading-copy">{round.claim_snapshot.text}</p><small>Claim 快照 {round.claim_snapshot.version_id ?? round.claim_snapshot.id ?? "已记录"}</small></article></div><aside className="ru-challenge" aria-labelledby="challenge-title"><p className="ru-kicker">Cui 的待回应候选 · pending</p><h2 id="challenge-title">{challenge.attack_surface}</h2><dl><div><dt>为什么重要</dt><dd>{challenge.why_it_matters}</dd></div><div><dt>可以怎样自检</dt><dd>{challenge.self_check_method}</dd></div></dl>{challenge.provenance && <p className="ru-provenance">生成依据：{challenge.provenance.basis_refs?.join(" · ") ?? "已记录"} · 不确定性：{challenge.provenance.uncertainty ?? "未说明"}</p>}<p className="ru-challenge-note">这条挑战仍待回应。这里不替你回答、裁决或改变 claim。回应与本轮裁决将在后续审查交互中完成；现在可以回到工作区继续探索，或回研究宇宙查看它所在的上下文。</p><nav className="ru-review-exits" aria-label="离开审查轮次"><a className="ru-ink-button" href={`/workspaces/${round.workspace_id}`}>回工作区继续探索</a><a className="ru-quiet-button" href="/">回研究宇宙查看上下文</a></nav></aside></section>
}
