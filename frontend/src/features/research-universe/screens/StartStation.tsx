import { useEffect, useRef, useState, type FormEvent } from "react"
import { command, researchUniverse } from "../api"
import type { CommandEnvelope } from "../types"
import { useNavigation } from "../../../router"

export function StartStation() {
  const { navigate } = useNavigation(); const [question, setQuestion] = useState(""); const [universeId, setUniverseId] = useState<string>(); const [error, setError] = useState<string | null>(null); const [hint, setHint] = useState<string>(); const inputRef = useRef<HTMLTextAreaElement>(null); const envelope = useRef<(CommandEnvelope & { question: string }) | undefined>(undefined)
  async function loadActive() { try { setError(null); setUniverseId((await researchUniverse.active()).id) } catch (e) { setError(e instanceof Error ? e.message : "未能读取研究宇宙") } }
  useEffect(() => { void loadActive() }, [])
  async function begin(event: FormEvent) {
    event.preventDefault()
    if (!question.trim()) { setHint("请先写下你的问题,再点「继续」。"); inputRef.current?.focus(); return }
    if (!universeId) { setHint("研究宇宙尚未连接,正在重新连接…"); void loadActive(); return }
    envelope.current ??= command({ question: question.trim() }, 0)
    try { const response = await researchUniverse.createWorkspace(universeId, envelope.current); navigate(`/workspaces/${response.result.workspace_id}`) } catch (e) { setError(e instanceof Error ? e.message : "未能开始") }
  }
  return <section className="ru-start-station" aria-labelledby="start-title"><p className="ru-kicker">研究宇宙</p><h1 id="start-title">从哪里开始？</h1><p className="ru-reading-copy">带进一个此刻值得停留的问题。Cui 不会替你形成主张或安排议程。</p><form onSubmit={begin}><label className="ru-field-label" htmlFor="starting-question">你此刻想带进 Cui 的问题</label><textarea id="starting-question" ref={inputRef} className="ru-intention" autoFocus value={question} onChange={(e) => { setQuestion(e.target.value); envelope.current = undefined }} placeholder="写下你准备探索的问题……" required /><p className="ru-slice-note">这会创建一个围绕问题展开的工作区；它不是系统替你规划的流程。</p>{error && <p className="ru-error" role="alert">{error} <button type="button" className="ru-quiet-button" onClick={() => void loadActive()}>重试</button></p>}<footer><span className="ru-universe-status">{universeId ? "研究宇宙已就绪" : "正在连接研究宇宙…"}</span><p className="ru-provenance" aria-live="polite">{hint ?? (!universeId ? (error ? "连接失败——请点上面的「重试」或刷新页面。" : "正在连接后端,稍候片刻…") : question.trim() ? "可以开始了。" : "输入框正在等你写下问题。")}</p><button type="submit" className="ru-ink-button">继续</button></footer></form></section>
}
