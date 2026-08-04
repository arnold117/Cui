import { useEffect, useState } from "react"
import { researchUniverse, type ActiveUniverse } from "../api"

export function StartStation() {
  const [universe, setUniverse] = useState<ActiveUniverse | null | undefined>(undefined)

  useEffect(() => {
    let active = true
    researchUniverse.active()
      .then((value) => active && setUniverse(value))
      .catch(() => active && setUniverse(null))
    return () => { active = false }
  }, [])

  return (
    <section className="ru-start-station" aria-labelledby="start-title">
      <p className="ru-kicker">研究宇宙</p>
      <h1 id="start-title">从哪里开始？</h1>
      <p className="ru-reading-copy">带进一个此刻值得停留的问题。Cui 不会替你形成主张或安排议程。</p>
      <label className="ru-field-label" htmlFor="starting-intention">你此刻想带进 Cui 的问题或长期意图</label>
      <textarea id="starting-intention" className="ru-intention" placeholder="写下你准备探索的问题……" disabled />
      <fieldset className="ru-intent-choice" disabled>
        <legend>开始方式</legend>
        <label><input type="radio" name="intent" defaultChecked /> 我想探索一个具体问题</label>
        <label><input type="radio" name="intent" /> 我已有一条长期研究方向</label>
      </fieldset>
      <p className="ru-slice-note">起始台将在下一切片连接问题工作区。现在保留研究桌，而不伪造流程。</p>
      <footer>
        <span className="ru-universe-status" aria-live="polite">
          {universe === undefined ? "正在读取研究宇宙…" : universe ? "研究宇宙已就绪" : "尚未读取到活跃研究宇宙"}
        </span>
        <button type="button" className="ru-ink-button" disabled>继续</button>
      </footer>
    </section>
  )
}
