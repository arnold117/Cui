import { lazy, Suspense } from "react"
import { UniverseShell } from "./features/research-universe/shell/UniverseShell"
import { StartStation } from "./features/research-universe/screens/StartStation"
import { WorkspaceDesk } from "./features/research-universe/screens/WorkspaceDesk"
import { DialogueDesk } from "./features/research-universe/screens/DialogueDesk"
import { ReviewRoundDesk } from "./features/research-universe/screens/ReviewRoundDesk"
import { DirectionViewport } from "./features/research-universe/screens/DirectionViewport"
import { UniverseHome } from "./features/research-universe/screens/UniverseHome"
import { LegacyArchive } from "./features/legacy-archive/LegacyArchive"
import { ParkDesk } from "./features/finalized-assumption/ParkDesk"
import { AppRouter, useNavigation } from "./router"

const ResearchUniversePrototype = lazy(() => import("./prototypes/ResearchUniversePrototype"))
function RetiredPath({ pathname }: { pathname: string }) { return <UniverseShell><section className="ru-start-station ru-retired-path"><p className="ru-kicker">路径已退役</p><h1>这里不再是研究宇宙的入口。</h1><p className="ru-reading-copy"><code>{pathname}</code> 属于旧版界面，不能进入新的研究宇宙。旧记录仍可在只读 archive 中查看。</p><a className="ru-retired-link" href="/archive">查看旧记录</a></section></UniverseShell> }
function NotFound({ pathname }: { pathname: string }) { return <UniverseShell><section className="ru-start-station ru-retired-path"><p className="ru-kicker">未找到路径</p><h1>这个位置不存在。</h1><p className="ru-reading-copy"><code>{pathname}</code> 不是 Cui 的可用研究路径。</p><a className="ru-retired-link" href="/">回到研究宇宙</a></section></UniverseShell> }

function RoutedApp() {
  const { location } = useNavigation(); const { pathname, search } = location
  const artifactMatch = pathname.match(/^\/artifact\/([^/]+)$/); const archiveArtifactMatch = pathname.match(/^\/archive\/artifacts\/([^/]+)$/)
  const workspaceMatch = pathname.match(/^\/workspaces\/([^/]+)$/); const dialogueMatch = pathname.match(/^\/workspaces\/([^/]+)\/dialogue$/); const forgeMatch = pathname.match(/^\/workspaces\/([^/]+)\/forge\/([^/]+)$/); const reviewMatch = pathname.match(/^\/review-rounds\/([^/]+)$/); const directionMatch = pathname.match(/^\/directions\/([^/]+)$/); const prototypeVariant = new URLSearchParams(search).get("variant")
  if (pathname === "/__prototype/research-universe" && ["A", "B", "C", "D"].includes(prototypeVariant ?? "")) return <Suspense fallback={null}><ResearchUniversePrototype variant={prototypeVariant as "A" | "B" | "C" | "D"} /></Suspense>
  if (dialogueMatch) return <UniverseShell trail={["问题工作区", "文献探讨"]}><DialogueDesk workspaceId={dialogueMatch[1]} /></UniverseShell>
  if (pathname === "/archive") return <LegacyArchive />
  if (archiveArtifactMatch) return <LegacyArchive artifactId={archiveArtifactMatch[1]} />
  if (artifactMatch) return <LegacyArchive artifactId={artifactMatch[1]} redirectedFrom={pathname} />
  if (/^\/library\/[^/]+\/graph$/.test(pathname) || pathname.startsWith("/claim/") || pathname.startsWith("/grill/")) return <RetiredPath pathname={pathname} />
  if (pathname === "/park") return <UniverseShell trail={["PARK"]}><ParkDesk /></UniverseShell>
  const parkDetailMatch = pathname.match(/^\/park\/([^/]+)$/)
  if (parkDetailMatch) return <UniverseShell trail={["PARK"]}><ParkDesk captureId={parkDetailMatch[1]} /></UniverseShell>
  if (forgeMatch) return <UniverseShell trail={["问题工作区", "锻"]}><WorkspaceDesk workspaceId={forgeMatch[1]} forgeReleaseRefId={forgeMatch[2]} sourceReleaseId={new URLSearchParams(search).get("source-release") ?? undefined} /></UniverseShell>
  if (workspaceMatch) return <UniverseShell trail={["问题工作区"]}><WorkspaceDesk workspaceId={workspaceMatch[1]} sourceReleaseId={new URLSearchParams(search).get("source-release") ?? undefined} /></UniverseShell>
  if (reviewMatch) return <UniverseShell trail={["问题工作区", "审查轮次"]}><ReviewRoundDesk roundId={reviewMatch[1]} /></UniverseShell>
  if (directionMatch) return <UniverseShell trail={["方向"]}><DirectionViewport directionId={directionMatch[1]} rephraseIntent={new URLSearchParams(search).get("rephrase") === "1"} sourceConclusionRef={new URLSearchParams(search).get("source_conclusion") ?? undefined} /></UniverseShell>
  if (pathname === "/") return <UniverseShell><div className="ru-root"><StartStation /><UniverseHome /></div></UniverseShell>
  return <NotFound pathname={pathname} />
}
function App() { return <AppRouter><RoutedApp /></AppRouter> }
export default App
