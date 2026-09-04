import { useState } from "react"
import { useNavigation } from "../../../router"
import { dialogueProgress, STAGE_LABELS } from "../dialogueDraft"

/** 工作区 → 文献探讨的入口/继续条。会话进度存本机,这里只读摘要。 */
export function DialogueResumeLink({ workspaceId }: { workspaceId: string }) {
  const { navigate } = useNavigation()
  const [progress] = useState(() => dialogueProgress(workspaceId))

  return <div className="ru-dialogue-entry" aria-label="文献探讨入口">
    <div>
      <p className="ru-kicker">与 Cui 一起读文献</p>
      <p className="ru-copy">
        {progress.exists
          ? <>上次会话已走到第 <strong>{progress.stage}</strong> 步({STAGE_LABELS[progress.stage - 1]}),接着走完:检索选料 → 覆盖梳理 → 对抗审查 → gap → 综述草稿。</>
          : <>检索选料 → 覆盖梳理 → 对抗审查 → gap → 综述草稿。会话进度保存在本机浏览器,可随时退出后继续;claim 与 gap 仍以轨迹为准。</>}
      </p>
    </div>
    <button type="button" className="ru-ink-button ru-active" onClick={() => navigate(`/workspaces/${workspaceId}/dialogue`)}>
      {progress.exists ? `继续文献探讨 · 第 ${progress.stage}/${STAGE_LABELS.length} 步 →` : "开始文献探讨 →"}
    </button>
  </div>
}
