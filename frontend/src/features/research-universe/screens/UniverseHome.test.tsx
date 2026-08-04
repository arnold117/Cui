import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { UniverseHome } from "./UniverseHome"
import { researchUniverse } from "../api"
import type { HomeProjection } from "../types"
vi.mock("../api", () => ({ researchUniverse: { active: vi.fn(), home: vi.fn() } }))
const active = vi.mocked(researchUniverse.active), home = vi.mocked(researchUniverse.home)
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
const fact = (label: string): HomeProjection => ({ universe_id: "u", workspaces: [], pending_facts: [{ id: `ch-${label}`, workspace_id: "w", question: `${label} question`, review_round_id: `r-${label}`, attack_surface: label, why_it_matters: "why", self_check_method: "check", status: "pending", provenance: { generator_kind: "system", prompt_version: "v1", model_identifier: "test-model", basis_refs: ["test"], uncertainty: "test uncertainty" } }] })
describe("UniverseHome guarded read chains", () => {
  it("does not write stale home state after unmount", async () => { const later = deferred<HomeProjection>(); active.mockResolvedValueOnce({ id: "u" }); home.mockReturnValueOnce(later.promise); const view = render(<UniverseHome />); await waitFor(() => expect(home).toHaveBeenCalledWith("u")); view.unmount(); later.resolve({ universe_id: "u", workspaces: [], pending_facts: [] }); await Promise.resolve(); expect(document.body.textContent).not.toContain("还没有待回应事实") })
  it("retry invalidates a prior deferred chain before it can overwrite the new result", async () => { const first = deferred<HomeProjection>(); active.mockResolvedValue({ id: "u" }); home.mockReturnValueOnce(first.promise).mockResolvedValueOnce(fact("NEW")); render(<UniverseHome />); await waitFor(() => expect(home).toHaveBeenCalledTimes(1)); screen.getByRole("button", { name: "重新读取" }).click(); await screen.findByText("一条待回应 challenge：NEW", { exact: true }); first.resolve(fact("OLD")); await Promise.resolve(); expect(screen.queryByText("一条待回应 challenge：OLD", { exact: true })).not.toBeInTheDocument(); expect(screen.getByText("一条待回应 challenge：NEW", { exact: true })).toBeInTheDocument() })
})
