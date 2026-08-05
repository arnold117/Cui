import type { ReactNode } from "react"

type UniverseShellProps = { children: ReactNode; trail?: string[] }

export function UniverseShell({ children, trail = [] }: UniverseShellProps) {
  return <div className="ru-shell"><header className="ru-topbar"><a className="ru-wordmark" href="/" aria-label="Cui research universe"><span>淬</span> Cui</a><nav className="ru-path" aria-label="研究路径"><a href="/">研究宇宙</a>{trail.map((item, index) => <span key={`${item}-${index}`}> <b>/</b> {item}</span>)}</nav><div className="ru-top-actions"><a className="ru-park-link" href="/park">密封捕获</a><a className="ru-start" href="/">＋ 开始</a></div></header><main className="ru-main">{children}</main></div>
}
