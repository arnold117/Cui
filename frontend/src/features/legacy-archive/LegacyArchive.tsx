import { useEffect, useState } from "react"
import { legacyArchive, type ArchiveArtifact, type ArchiveEvent } from "./api"

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString()
}

type LegacyArchiveProps = { artifactId?: string | null; redirectedFrom?: string }

export function LegacyArchive({ artifactId = null, redirectedFrom }: LegacyArchiveProps) {
  const [artifacts, setArtifacts] = useState<ArchiveArtifact[]>([])
  const [selected, setSelected] = useState<ArchiveArtifact | null>(null)
  const [events, setEvents] = useState<ArchiveEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    legacyArchive.list()
      .then(({ artifacts: items }) => { if (active) setArtifacts(items) })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "无法读取 archive") })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!artifactId) return
    let active = true
    legacyArchive.artifact(artifactId)
      .then(({ artifact }) => { if (active) setSelected(artifact) })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "无法读取旧记录") })
    return () => { active = false }
  }, [artifactId])

  useEffect(() => {
    if (!selected) { setEvents([]); return }
    let active = true
    legacyArchive.trajectory(selected.id)
      .then(({ events: items }) => { if (active) setEvents(items) })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "无法读取轨迹") })
    return () => { active = false }
  }, [selected])

  return (
    <div className="archive-shell">
      <header className="archive-topbar">
        <a className="ru-wordmark" href="/" aria-label="返回 Cui 研究宇宙"><span>淬</span> Cui</a>
        <p>旧研究 archive <span>· 只读</span></p>
        <a href="/">返回研究宇宙</a>
      </header>
      <main className="archive-main">
        <section className="archive-intro">
          <p className="ru-kicker">历史研究</p>
          <h1>旧轨迹，保持原样。</h1>
          <p className="ru-reading-copy">这里保存此前的研究记录。它不会参与新的研究宇宙，也不能在此修改。</p>
          {redirectedFrom && <p className="archive-redirect">已从退役路径 <code>{redirectedFrom}</code> 打开这条只读记录。</p>}
        </section>
        {error && <p className="archive-error" role="alert">{error}</p>}
        <div className="archive-layout">
          <section className="archive-list" aria-label="归档想法">
            <h2>想法</h2>
            {loading ? <p>正在读取…</p> : artifacts.length === 0 ? <p>没有可读的旧记录。</p> : <ol>{artifacts.map((artifact) => <li key={artifact.id}><button type="button" onClick={() => setSelected(artifact)} className={selected?.id === artifact.id ? "is-selected" : ""}><strong>{artifact.title || artifact.goal || "未命名想法"}</strong><small>{artifact.kind} · {formatDate(artifact.updated_at)}</small></button></li>)}</ol>}
          </section>
          <section className="archive-readback" aria-live="polite">
            {selected ? <><p className="ru-kicker">原始记录</p><h2>{selected.title || "未命名想法"}</h2><p className="archive-goal">{selected.goal}</p><div className="archive-trajectory"><h3>轨迹</h3>{events.length === 0 ? <p>没有可读轨迹。</p> : <ol>{events.map((event) => <li key={event.id}><span>{event.type}</span><time>{formatDate(event.ts)}</time><p>{event.confirmed ? "已确认" : "未确认"} · {event.actor}</p></li>)}</ol>}</div></> : <p className="archive-empty">选择一条旧记录，查看其原始轨迹。</p>}
          </section>
        </div>
      </main>
    </div>
  )
}
