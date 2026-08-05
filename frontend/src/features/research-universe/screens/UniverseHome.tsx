import { useEffect, useRef, useState } from "react"
import { researchUniverse } from "../api"
import type { HomeProjection } from "../types"

export function UniverseHome() {
  const [home, setHome] = useState<HomeProjection | null>(null); const [error, setError] = useState<string | null>(null); const generation = useRef(0)
  async function load() { const current = ++generation.current; try { const active = await researchUniverse.active(); if (current !== generation.current) return; const projection = await researchUniverse.home(active.id); if (current !== generation.current) return; setHome(projection); setError(null) } catch (e) { if (current === generation.current) setError(e instanceof Error ? e.message : "未能读取研究宇宙。") } }
  useEffect(() => { void load(); return () => { generation.current++ } }, [])
  if (error) return <section className="ru-universe-home"><p className="ru-error" role="alert">{error}</p><button className="ru-quiet-button" onClick={() => void load()}>重试</button></section>
  if (!home) return <section className="ru-universe-home" aria-live="polite">正在读取研究宇宙中的事实… <button className="ru-quiet-button" onClick={() => void load()}>重新读取</button></section>
  const facts = home.pending_facts ?? []
  const directions = home.directions ?? []
  return <section className="ru-universe-home" aria-labelledby="universe-title"><p className="ru-kicker">研究宇宙</p><h1 id="universe-title">这片地形正在等待你的解释</h1>
    {directions.length > 0 && <div className="ru-home-directions" aria-labelledby="directions-title"><p className="ru-kicker" id="directions-title">方向地形</p>{directions.map(d => <article key={d.id} className="ru-direction-card"><a href={`/directions/${d.id}`}><span>方向 · {d.status}</span><strong>{d.proposition}</strong><small>{d.attached_workspaces_count} 个问题试验 · {d.crystallizations_count} 项结晶</small></a>{d.crystallizations.length > 0 && <div className="ru-home-crystallizations">{d.crystallizations.map(c => <p key={c.crystallization_id} className="ru-home-crystal">最近结晶：{c.conclusion_text}</p>)}</div>}</article>)}</div>}
    {facts.length ? <div className="ru-home-facts">{facts.map((fact) => <a key={fact.id} href={`/review-rounds/${fact.review_round_id}`}><span>未归属的探索 / {fact.question}</span><strong>一条待回应 challenge：{fact.attack_surface}</strong><small>仍在当前问题与 claim 的审查轮次中。</small></a>)}</div> : <p className="ru-reading-copy">{directions.length ? "方向已呈现；这里还没有待回应事实。" : "还没有待回应事实。你可以从一个问题开始，而不是从待办清单开始。"}</p>}</section>
}
