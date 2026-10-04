import { useState } from "react"
import { command, researchUniverse } from "../api"
import { useNavigation } from "../../../router"

/** 对已确认 gap 发起反证:预填 claim 草稿,用户改写并署名后才创建 claim、开审查轮(永不自动化定见)。 */
export function GapChallengeComposer({ workspaceId, gapId, coverage }: { workspaceId: string; gapId: string; coverage: string }) {
  const { navigate } = useNavigation()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  async function sign() {
    if (busy || !text.trim()) return
    setBusy(true); setError(undefined)
    try {
      const made = await researchUniverse.createClaim(workspaceId, command({ text: text.trim(), kind: "vacancy", origin_gap_id: gapId }, 0))
      const review = await researchUniverse.startReview(made.result.claim_id!, command({}, 0))
      navigate(`/review-rounds/${review.result.review_round_id}`)
    } catch (e) { setError(e instanceof Error ? e.message : "开审查轮失败") } finally { setBusy(false) }
  }

  if (!open) return <button type="button" className="ru-quiet-button" onClick={() => { setText(`目前没有文献覆盖:${coverage}`); setOpen(true) }}>对这个 gap 发起反证</button>
  return <div className="ru-material-form">
    <p className="ru-quiet-hint">把这个缺口写成一条 claim,走审查轮被挑战;反证 = 找到覆盖这个缺口的文献。草稿可改,你署名才固化。</p>
    {error && <p className="ru-error" role="alert">{error}</p>}
    <label>反证用 claim(空缺断言)
      <textarea className="ru-conclusion-text" value={text} onChange={(e) => setText(e.target.value)} />
    </label>
    <div className="ru-crystal-actions">
      <button type="button" className="ru-quiet-button" disabled={busy} onClick={() => setOpen(false)}>取消</button>
      <button type="button" className="ru-ink-button ru-active" disabled={busy || !text.trim()} onClick={() => void sign()}>{busy ? "正在固化…" : "署名固化为 claim 并开审查轮"}</button>
    </div>
  </div>
}
