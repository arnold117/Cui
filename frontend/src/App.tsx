import { lazy, Suspense, useEffect, useState } from "react"
import { UniverseShell } from "./features/research-universe/shell/UniverseShell"
import { StartStation } from "./features/research-universe/screens/StartStation"
import { WorkspaceJourney } from "./features/research-universe/screens/WorkspaceJourney"
import { researchUniverse } from "./features/research-universe/api"
import { DirectionViewport } from "./features/research-universe/screens/DirectionViewport"
import { UniverseHome } from "./features/research-universe/screens/UniverseHome"
import { LegacyArchive } from "./features/legacy-archive/LegacyArchive"
import { ParkDesk } from "./features/finalized-assumption/ParkDesk"
import { AppRouter, useNavigation } from "./router"

const ResearchUniversePrototype = lazy(() => import("./prototypes/ResearchUniversePrototype"))
function RetiredPath({ pathname }: { pathname: string }) { return <UniverseShell><section className="ru-start-station ru-retired-path"><p className="ru-kicker">路径已退役</p><h1>这里不再是研究宇宙的入口。</h1><p className="ru-reading-copy"><code>{pathname}</code> 属于旧版界面，不能进入新的研究宇宙。旧记录仍可在只读 archive 中查看。</p><a className="ru-retired-link" href="/archive">查看旧记录</a></section></UniverseShell> }
function Redirect({ to }: { to: string }) { const { navigate } = useNavigation(); useEffect(() => { navigate(to, { replace: true }) }, [navigate, to]); return null }
/** 旧整页地址 /review-rounds/:rid:先读这一轮拿 workspace_id,再 replace 到旅程页右侧面(不在历史里留一跳) */
function ReviewRoundRedirect({ roundId }: { roundId: string }) {
  const { navigate } = useNavigation(); const [failure, setFailure] = useState<Error & { status?: number }>(); const [attempt, setAttempt] = useState(0)
  useEffect(() => { let live = true; setFailure(undefined); researchUniverse.reviewRound(roundId).then((round) => { if (live) navigate(`/workspaces/${round.workspace_id}/rounds/${roundId}`, { replace: true }) }, (e) => { if (live) setFailure(e) }); return () => { live = false } }, [navigate, roundId, attempt])
  if (failure?.status === 404) return <NotFound pathname={`/review-rounds/${roundId}`} />
  return <UniverseShell trail={["问题工作区", "审查轮次"]}>{failure ? <section className="ru-state" role="alert"><p>未能打开审查轮次：{failure.message}</p><button className="ru-ink-button" onClick={() => setAttempt((n) => n + 1)}>重试</button></section> : <section className="ru-state" aria-live="polite">正在定位这一轮所在的问题…</section>}</UniverseShell>
}
function NotFound({ pathname }: { pathname: string }) { return <UniverseShell><section className="ru-start-station ru-retired-path"><p className="ru-kicker">未找到路径</p><h1>这个位置不存在。</h1><p className="ru-reading-copy"><code>{pathname}</code> 不是 Cui 的可用研究路径。</p><a className="ru-retired-link" href="/">回到研究宇宙</a></section></UniverseShell> }

function RoutedApp() {
  const { location } = useNavigation(); const { pathname, search } = location
  const artifactMatch = pathname.match(/^\/artifact\/([^/]+)$/); const archiveArtifactMatch = pathname.match(/^\/archive\/artifacts\/([^/]+)$/)
  const workspaceMatch = pathname.match(/^\/workspaces\/([^/]+)$/); const dialogueMatch = pathname.match(/^\/workspaces\/([^/]+)\/dialogue$/); const forgeMatch = pathname.match(/^\/workspaces\/([^/]+)\/forge\/([^/]+)$/); const roundMatch = pathname.match(/^\/workspaces\/([^/]+)\/rounds\/([^/]+)$/); const reviewMatch = pathname.match(/^\/review-rounds\/([^/]+)$/); const directionMatch = pathname.match(/^\/directions\/([^/]+)$/); const prototypeVariant = new URLSearchParams(search).get("variant")
  if (pathname === "/__prototype/research-universe" && ["A", "B", "C", "D"].includes(prototypeVariant ?? "")) return <Suspense fallback={null}><ResearchUniversePrototype variant={prototypeVariant as "A" | "B" | "C" | "D"} /></Suspense>
  if (dialogueMatch) return <Redirect to={`/workspaces/${dialogueMatch[1]}`} />
  if (pathname === "/archive") return <LegacyArchive />
  if (archiveArtifactMatch) return <LegacyArchive artifactId={archiveArtifactMatch[1]} />
  if (artifactMatch) return <LegacyArchive artifactId={artifactMatch[1]} redirectedFrom={pathname} />
  if (/^\/library\/[^/]+\/graph$/.test(pathname) || pathname.startsWith("/claim/") || pathname.startsWith("/grill/")) return <RetiredPath pathname={pathname} />
  if (pathname === "/park") return <UniverseShell trail={["PARK"]}><ParkDesk /></UniverseShell>
  const parkDetailMatch = pathname.match(/^\/park\/([^/]+)$/)
  if (parkDetailMatch) return <UniverseShell trail={["PARK"]}><ParkDesk captureId={parkDetailMatch[1]} /></UniverseShell>
  // 旅程页按 workspaceId 加 key:换工作区即重建,本机会话草稿不串
  if (forgeMatch) return <UniverseShell trail={["问题工作区", "锻"]}><WorkspaceJourney key={forgeMatch[1]} workspaceId={forgeMatch[1]} forgeReleaseRefId={forgeMatch[2]} sourceReleaseId={new URLSearchParams(search).get("source-release") ?? undefined} /></UniverseShell>
  if (workspaceMatch) return <UniverseShell trail={["问题工作区"]}><WorkspaceJourney key={workspaceMatch[1]} workspaceId={workspaceMatch[1]} sourceReleaseId={new URLSearchParams(search).get("source-release") ?? undefined} /></UniverseShell>
  if (roundMatch) return <UniverseShell trail={["问题工作区", "审查轮次"]}><WorkspaceJourney key={roundMatch[1]} workspaceId={roundMatch[1]} roundId={roundMatch[2]} /></UniverseShell>
  if (reviewMatch) return <ReviewRoundRedirect roundId={reviewMatch[1]} />
  if (directionMatch) return <UniverseShell trail={["方向"]}><DirectionViewport directionId={directionMatch[1]} rephraseIntent={new URLSearchParams(search).get("rephrase") === "1"} sourceConclusionRef={new URLSearchParams(search).get("source_conclusion") ?? undefined} /></UniverseShell>
  if (pathname === "/") return <UniverseShell><div className="ru-root"><StartStation /><UniverseHome /></div></UniverseShell>
  return <NotFound pathname={pathname} />
}
function App() { return <AppRouter><RoutedApp /></AppRouter> }
export default App
