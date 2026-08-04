import { createContext, useCallback, useContext, useSyncExternalStore, type ReactNode } from "react"

export interface AppLocation { pathname: string; search: string }

const NAVIGATION_EVENT = "cui:navigation"
let historyPatched = false

function locationSnapshot() {
  return `${window.location.pathname}${window.location.search}`
}

function subscribe(onChange: () => void) {
  const notify = () => onChange()
  window.addEventListener("popstate", notify)
  window.addEventListener(NAVIGATION_EVENT, notify)
  return () => {
    window.removeEventListener("popstate", notify)
    window.removeEventListener(NAVIGATION_EVENT, notify)
  }
}

function patchHistory() {
  if (historyPatched) return
  historyPatched = true
  for (const method of ["pushState", "replaceState"] as const) {
    const original = window.history[method]
    window.history[method] = function (...args: Parameters<History[typeof method]>) {
      const result = original.apply(this, args)
      window.dispatchEvent(new Event(NAVIGATION_EVENT))
      return result
    }
  }
}

interface Navigation { location: AppLocation; navigate: (to: string, options?: { replace?: boolean }) => void }
const NavigationContext = createContext<Navigation | null>(null)

export function AppRouter({ children }: { children: ReactNode }) {
  patchHistory()
  const snapshot = useSyncExternalStore(subscribe, locationSnapshot, () => "/")
  const location: AppLocation = { pathname: snapshot.split("?")[0], search: snapshot.includes("?") ? `?${snapshot.split("?").slice(1).join("?")}` : "" }
  const navigate = useCallback((to: string, options?: { replace?: boolean }) => {
    window.history[options?.replace ? "replaceState" : "pushState"]({}, "", to)
  }, [])
  return <NavigationContext.Provider value={{ location, navigate }}>{children}</NavigationContext.Provider>
}

export function useNavigation() {
  const value = useContext(NavigationContext)
  if (!value) throw new Error("useNavigation must be used inside AppRouter")
  return value
}
