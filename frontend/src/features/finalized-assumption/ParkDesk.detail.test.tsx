import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppRouter } from "../../router"
import { ParkDesk } from "./ParkDesk"
const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock)
const ok = (x: unknown, status = 200) => new Response(JSON.stringify(x), { status })
const detail = (id = "p", original_text = "RAW_SENTINEL") => ({ id, original_text, status: "sealed", released: false, releases: [], forged_into: [] })
afterEach(cleanup); beforeEach(() => fetchMock.mockReset())
function view(id?: string) { return render(<AppRouter><ParkDesk captureId={id} /></AppRouter>) }
describe("PARK list and detail boundary", () => {
 it("never renders list raw sentinel", async () => { fetchMock.mockResolvedValueOnce(ok({ library_id:"lib", captures:[{ id:"p", status:"sealed", released:false, releases:[], forged_into:[] }] })).mockResolvedValue(ok({id:"u",workspaces:[],pending_facts:[]})); view(); await screen.findByText("一份密封捕获"); expect(screen.queryByText("RAW_SENTINEL")).not.toBeInTheDocument(); expect(fetchMock.mock.calls[0][0]).toContain("/park-captures") })
 it("detail fetches and renders raw only after GET", async () => { fetchMock.mockResolvedValueOnce(ok(detail())).mockResolvedValue(ok({id:"u",workspaces:[],pending_facts:[]})); view("p"); expect(await screen.findByText("RAW_SENTINEL")).toBeInTheDocument(); expect(fetchMock.mock.calls[0][0]).toContain("/park-captures/p") })
 it("retries failed detail read", async () => { let attempts=0; fetchMock.mockImplementation((url: unknown) => { const path=String(url); if (path.endsWith("/park-captures/p")) return Promise.resolve(++attempts === 1 ? ok({detail:"no"},503) : ok(detail())); return Promise.resolve(ok({id:"u",workspaces:[],pending_facts:[]})) }); view("p"); fireEvent.click(await screen.findByRole("button",{name:"重试"})); expect(await screen.findByText("RAW_SENTINEL")).toBeInTheDocument() })
 it("late A detail cannot overwrite B", async () => { let resolveA!: (r: Response)=>void; fetchMock.mockImplementation((url: unknown) => { const path=String(url); if (path.endsWith("/park-captures/a")) return new Promise<Response>(r=>resolveA=r); if (path.endsWith("/park-captures/b")) return Promise.resolve(ok(detail("b","B_RAW"))); return Promise.resolve(ok({id:"u",workspaces:[],pending_facts:[]})) }); const r=view("a"); r.rerender(<AppRouter><ParkDesk captureId="b" /></AppRouter>); expect(await screen.findByText("B_RAW")).toBeInTheDocument(); resolveA(ok(detail("a","A_RAW"))); await waitFor(()=>expect(screen.queryByText("A_RAW")).not.toBeInTheDocument()) })
})
