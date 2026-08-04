import type { ReactNode } from "react"

type UniverseShellProps = { children: ReactNode }

export function UniverseShell({ children }: UniverseShellProps) {
  return (
    <div className="ru-shell">
      <header className="ru-topbar">
        <a className="ru-wordmark" href="/" aria-label="Cui research universe"><span>淬</span> Cui</a>
        <nav className="ru-path" aria-label="研究路径"><a href="/">研究宇宙</a></nav>
        <div className="ru-top-actions">
          <button type="button" className="ru-capture" disabled title="密封捕获将在后续切片开放">◇ 捕获</button>
          <button type="button" className="ru-start" disabled>＋ 开始</button>
        </div>
      </header>
      <main className="ru-main">{children}</main>
    </div>
  )
}
