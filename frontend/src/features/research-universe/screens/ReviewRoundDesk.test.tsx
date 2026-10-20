import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ReviewRoundDesk } from "./ReviewRoundDesk"
import { researchUniverse } from "../api"
import { AppRouter } from "../../../router"

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api")
  return { ...actual, researchUniverse: {
    reviewRound: vi.fn(),
    answerChallenge: vi.fn(),
    deferChallenge: vi.fn(),
    withdrawChallenge: vi.fn(),
    confirmVerdict: vi.fn(),
    startReview: vi.fn(),
    literatureChallenge: vi.fn(),
    active: vi.fn(),
    createWorkspace: vi.fn(),
    desk: vi.fn(),
    addMaterial: vi.fn(),
    proposeEvidenceCandidate: vi.fn(),
    confirmEvidence: vi.fn(),
    correctEvidence: vi.fn(),
    rejectEvidence: vi.fn(),
    withdrawEvidence: vi.fn(),
  } }
})

const challenge = { id: "ch-1", review_round_id: "r-1", claim_id: "c-1", status: "pending" as const, sequence: 1, attack_surface: "边界尚未说明", why_it_matters: "无法判断适用范围", self_check_method: "写下一种失效条件", answers: [], provenance: { basis_refs: ["question", "claim"], uncertainty: "待检验" } }
const snapshot = { id: "c-1", version_id: "cv-1", text: "主张" }
function makeRound(overrides: Record<string, unknown> = {}) {
  return { id: "r-1", workspace_id: "w-1", question_snapshot: { version_id: "q-1", text: "问题" }, claim_snapshot: snapshot, sequence: 1, verdict: null, challenges: [challenge], ledger: { answered: [], deferred: [], pending: [challenge], brought_unconfirmed: [] }, rounds: [], ...overrides }
}
const responded = <T extends Record<string, unknown>>(payload: T) => ({ commit_position: 2, event_ids: [] as string[], result: payload })

afterEach(() => cleanup())

describe("ReviewRoundDesk review lifecycle", () => {
  it("keeps the challenge pending, has no page-level exits, and exposes Slice 3 answer/verdict surfaces", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound())
    const onClose = vi.fn()
    render(<AppRouter><ReviewRoundDesk roundId="r-1" onClose={onClose} /></AppRouter>)
    expect(await screen.findByText("边界尚未说明")).toBeInTheDocument()
    // 嵌入右侧面:没有「回工作区 / 回研究宇宙 / 回文献探讨」页级出口,只有收起
    expect(screen.queryByRole("navigation", { name: "离开审查轮次" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "回工作区继续探索" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "收起" }))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText("我目前的回应")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "保存答辩" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "裁决" })).toBeInTheDocument()
  })

  it("saves an answer, keeps the challenge open, and shows the saved reply", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.answerChallenge).mockResolvedValue(responded({ challenge_id: "ch-1", review_round_id: "r-1", answer_version_id: "av-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ challenges: [{ ...challenge, status: "answered", sequence: 2, answers: [{ version_id: "av-1", text: "my reply", provisional_anchor_refs: [] }] }], ledger: { answered: [{ ...challenge, status: "answered", answers: [{ version_id: "av-1", text: "my reply", provisional_anchor_refs: [] }] }], deferred: [], pending: [], brought_unconfirmed: [] } }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.change(screen.getByLabelText("我目前的回应"), { target: { value: "my reply" } })
    fireEvent.click(screen.getByRole("button", { name: "保存答辩" }))
    await waitFor(() => expect(researchUniverse.answerChallenge).toHaveBeenCalledWith("ch-1", expect.objectContaining({ answer_text: "my reply", expected_sequence: 1, provisional_anchor_refs: [] })))
    expect(await screen.findByText("my reply")).toBeInTheDocument()
    expect(screen.getByText(/答辩已保存，挑战仍待裁决/)).toBeInTheDocument()
  })

  it("defers a challenge with a revisit condition and closes it", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.deferChallenge).mockResolvedValue(responded({ challenge_id: "ch-1", review_round_id: "r-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ challenges: [{ ...challenge, status: "deferred", sequence: 2, defer: { reason: "暂缓这条挑战", condition: "读到 Paper A 之后" } }], ledger: { answered: [], deferred: [{ ...challenge, status: "deferred" }], pending: [], brought_unconfirmed: [] } }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("button", { name: "我还不能回应 ▾" }))
    fireEvent.click(screen.getByRole("button", { name: /暂缓这条挑战/ }))
    fireEvent.change(screen.getByLabelText("何时重看"), { target: { value: "读到 Paper A 之后" } })
    fireEvent.click(screen.getByRole("button", { name: "确认暂缓" }))
    await waitFor(() => expect(researchUniverse.deferChallenge).toHaveBeenCalledWith("ch-1", expect.objectContaining({ reason: "暂缓这条挑战", condition: "读到 Paper A 之后", expected_sequence: 1 })))
    expect(await screen.findByText(/何时重看：读到 Paper A 之后/)).toBeInTheDocument()
    expect(screen.queryByLabelText("我目前的回应")).not.toBeInTheDocument()
  })

  it("withdraws a challenge with a reason and closes it", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.withdrawChallenge).mockResolvedValue(responded({ challenge_id: "ch-1", review_round_id: "r-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound({ challenges: [{ ...challenge, status: "withdrawn", sequence: 2, withdraw: { reason: "no longer relevant" } }], ledger: { answered: [], deferred: [], pending: [], brought_unconfirmed: [] } }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("button", { name: "撤回这条挑战" }))
    fireEvent.change(screen.getByLabelText("撤回理由"), { target: { value: "no longer relevant" } })
    fireEvent.click(screen.getByRole("button", { name: "确认撤回" }))
    await waitFor(() => expect(researchUniverse.withdrawChallenge).toHaveBeenCalledWith("ch-1", expect.objectContaining({ reason: "no longer relevant", expected_sequence: 1 })))
    expect(await screen.findByText(/理由：no longer relevant/)).toBeInTheDocument()
  })

  it("records a verdict through the ledger with an explicit user reason", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound())
    vi.mocked(researchUniverse.confirmVerdict).mockResolvedValue(responded({ review_round_id: "r-1", verdict_type: "survived" }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("tab", { name: "裁决" }))
    expect(screen.getByText(/这是一项你的判断。Cui 不会替你决定结果。/)).toBeInTheDocument()
    expect(screen.getByText("已回应")).toBeInTheDocument()
    expect(screen.getByText("仍待回应")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("radio", { name: /暂时站住了/ }))
    fireEvent.change(screen.getByLabelText("你的理由"), { target: { value: "stood this round" } })
    fireEvent.click(screen.getByRole("button", { name: "确认裁决" }))
    await waitFor(() => expect(researchUniverse.confirmVerdict).toHaveBeenCalledWith("r-1", expect.objectContaining({ verdict_type: "survived", user_reason: "stood this round", revival_condition: null, expected_sequence: 1 })))
  })

  it("requires a revival condition for a circumstantial verdict", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound())
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("tab", { name: "裁决" }))
    fireEvent.click(screen.getByRole("radio", { name: /现在先不投入/ }))
    const confirm = screen.getByRole("button", { name: "确认裁决" })
    expect(confirm).toBeDisabled()
    fireEvent.change(screen.getByLabelText("你的理由"), { target: { value: "not now" } })
    expect(confirm).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/何时、什么条件下再回来/), { target: { value: "when measured" } })
    expect(confirm).toBeEnabled()
  })

  it("offers re-review and shows round history after a verdict", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound({ verdict: { round_id: "r-1", verdict_type: "survived", user_reason: "x" }, challenges: [{ ...challenge, status: "resolved_by_verdict" }], rounds: [{ id: "r-1", claim_id: "c-1", question_snapshot: { version_id: "q-1", text: "问题" }, claim_snapshot: snapshot, verdict: { round_id: "r-1", verdict_type: "survived", user_reason: "x" } }] }))
    vi.mocked(researchUniverse.startReview).mockResolvedValue(responded({ review_round_id: "r-2" }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    const again = await screen.findByRole("button", { name: "再次审查这一条 claim" })
    expect(screen.getByText(/裁决：survived/)).toBeInTheDocument()
    fireEvent.click(again)
    await waitFor(() => expect(researchUniverse.startReview).toHaveBeenCalledWith("c-1", expect.objectContaining({ expected_sequence: 0 })))
    // 再次审查:切到同一旅程页右侧面的新一轮,不整页跳
    expect(window.location.pathname).toBe("/workspaces/w-1/rounds/r-2")
  })

  it("shows the boundary lineage after a boundary verdict", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound({ verdict: { round_id: "r-1", verdict_type: "boundary", user_reason: "needs narrowing" }, challenges: [{ ...challenge, status: "resolved_by_verdict" }], rounds: [{ id: "r-1", claim_id: "c-1", question_snapshot: { version_id: "q-1", text: "问题" }, claim_snapshot: snapshot, verdict: { round_id: "r-1", verdict_type: "boundary", user_reason: "needs narrowing" } }] }))
    vi.mocked(researchUniverse.active).mockResolvedValue({ id: "u-1" })
    vi.mocked(researchUniverse.createWorkspace).mockResolvedValue(responded({ workspace_id: "w-2" }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    expect(await screen.findByText(/这条 claim 已保留为本轮结论/)).toBeInTheDocument()
    expect(screen.getByText(/理由：needs narrowing/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "围绕这条边界开一个新问题" }))
    await waitFor(() => expect(researchUniverse.createWorkspace).toHaveBeenCalledWith("u-1", expect.objectContaining({ question: "把这条边界做成一个开放问题：主张" })))
    expect(window.location.pathname).toBe("/workspaces/w-2")
  })
})

describe("ReviewRoundDesk attack surface and segments (S3)", () => {
  const ch = (id: string, attack_surface: string, extra: Record<string, unknown> = {}) => ({ ...challenge, id, attack_surface, ...extra })
  // 已回应 / 暂缓 / 撤回都不算「仍待回应」（ledger 口径）
  const settled = [
    ch("ch-1", "已回应的一关", { status: "answered", answers: [{ version_id: "av-1", text: "r", provisional_anchor_refs: [] }] }),
    ch("ch-2", "暂缓的一关", { status: "deferred", defer: { reason: "暂缓这条挑战", condition: "读完 Paper A" } }),
    ch("ch-3", "撤回的一关", { status: "withdrawn", withdraw: { reason: "不适用" } }),
  ]
  const candidate = (status: string) => ({ id: "ec-1", round_id: "r-1", workspace_id: "w-1", claim_snapshot: snapshot, material_anchor: { id: "m-1", excerpt: "摘录", source_locator: null }, relation: "supports", status, sequence: 1 })
  const expandedRow = () => screen.getByRole("button", { expanded: true })

  it.each([
    ["应答", "a still-pending challenge", makeRound({ challenges: [...settled, ch("ch-4", "仍待回应的一关")], evidence_candidates: [candidate("pending")] }), "仍待回应 1"],
    ["取证", "no pending challenge but a pending evidence candidate", makeRound({ challenges: settled, evidence_candidates: [candidate("pending")] }), "没有仍待回应的挑战"],
    ["裁决", "nothing pending", makeRound({ challenges: settled, evidence_candidates: [candidate("confirmed")] }), "没有仍待回应的挑战"],
  ])("opens on %s when there is %s, and never locks the other segments", async (tab, _why, round, hint) => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(round)
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    expect(await screen.findByRole("tab", { name: tab, selected: true })).toBeInTheDocument()
    expect(screen.getAllByRole("tab", { selected: true })).toHaveLength(1)
    expect(screen.getByText(hint)).toBeInTheDocument()
    for (const other of ["应答", "取证", "裁决"]) {
      fireEvent.click(screen.getByRole("tab", { name: other }))
      expect(screen.getByRole("tab", { name: other, selected: true })).toBeInTheDocument()
      expect(screen.getByText(hint)).toBeInTheDocument()
    }
  })

  it("shows a titled challenge's title in its row, the full attack surface in its expanded body, and the title in the ledger", async () => {
    const titled = ch("ch-a", "模型给出的攻击面全文常常两三行，列表里放不下，所以只在展开体里给出", { title: "替代解释：是不是训练还不够久？" })
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound({ challenges: [titled], ledger: { answered: [], deferred: [], pending: [titled], brought_unconfirmed: [] } }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    expect(await screen.findByRole("button", { name: /替代解释：是不是训练还不够久？/ })).toHaveAttribute("aria-expanded", "true")
    expect(expandedRow()).not.toHaveTextContent(titled.attack_surface)
    expect(screen.getByRole("complementary", { name: /替代解释/ })).toHaveTextContent(titled.attack_surface)
    fireEvent.click(screen.getByRole("tab", { name: "裁决" }))
    expect(screen.getByText("替代解释：是不是训练还不够久？", { selector: ".ru-ledger-item" })).toBeInTheDocument()
  })

  it("clamps an untitled attack surface to two lines while collapsed and shows it in full when expanded", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound({ challenges: [ch("ch-a", "第一关"), ch("ch-b", "第二关")] }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    expect(await screen.findByText("第一关")).not.toHaveClass("ru-line-clamp-2")
    expect(screen.getByText("第二关")).toHaveClass("ru-line-clamp-2")
    fireEvent.click(screen.getByRole("button", { name: /第二关/ }))
    expect(screen.getByText("第二关")).not.toHaveClass("ru-line-clamp-2")
    expect(screen.getByText("第一关")).toHaveClass("ru-line-clamp-2")
  })

  it("expands exactly one challenge at a time and keeps each draft when focus moves", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound({ challenges: [ch("ch-a", "第一关"), ch("ch-b", "第二关"), ch("ch-c", "第三关")] }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("第一关")
    expect(expandedRow()).toHaveAccessibleName(/第一关/)
    expect(screen.getAllByLabelText("我目前的回应")).toHaveLength(1)
    fireEvent.change(screen.getByLabelText("我目前的回应"), { target: { value: "draft a" } })
    fireEvent.click(screen.getByRole("button", { name: /第二关/ }))
    expect(expandedRow()).toHaveAccessibleName(/第二关/)
    expect(screen.getAllByLabelText("我目前的回应")).toHaveLength(1)
    expect(screen.getByLabelText("我目前的回应")).toHaveValue("")
    fireEvent.click(screen.getByRole("button", { name: /第一关/ }))
    expect(screen.getByLabelText("我目前的回应")).toHaveValue("draft a")
  })

  it("moves focus to the next still-pending challenge after answer, defer and withdraw", async () => {
    const [a, b, c] = [ch("ch-a", "第一关"), ch("ch-b", "第二关"), ch("ch-c", "第三关")]
    const bAnswered = { ...b, status: "answered", sequence: 2, answers: [{ version_id: "av-b", text: "reply b", provisional_anchor_refs: [] }] }
    const cDeferred = { ...c, status: "deferred", sequence: 2, defer: { reason: "暂缓这条挑战", condition: "later" } }
    const aWithdrawn = { ...a, status: "withdrawn", sequence: 2, withdraw: { reason: "不适用" } }
    vi.mocked(researchUniverse.reviewRound)
      .mockResolvedValueOnce(makeRound({ challenges: [a, b, c] }))
      .mockResolvedValueOnce(makeRound({ challenges: [a, bAnswered, c] }))
      .mockResolvedValueOnce(makeRound({ challenges: [a, bAnswered, cDeferred] }))
      .mockResolvedValueOnce(makeRound({ challenges: [aWithdrawn, bAnswered, cDeferred] }))
    vi.mocked(researchUniverse.answerChallenge).mockResolvedValue(responded({ challenge_id: "ch-b", review_round_id: "r-1", answer_version_id: "av-b" }))
    vi.mocked(researchUniverse.deferChallenge).mockResolvedValue(responded({ challenge_id: "ch-c", review_round_id: "r-1" }))
    vi.mocked(researchUniverse.withdrawChallenge).mockResolvedValue(responded({ challenge_id: "ch-a", review_round_id: "r-1" }))
    render(<AppRouter><ReviewRoundDesk roundId="r-1" /></AppRouter>)
    await screen.findByText("第一关")
    fireEvent.click(screen.getByRole("button", { name: /第二关/ }))
    fireEvent.change(screen.getByLabelText("我目前的回应"), { target: { value: "reply b" } })
    fireEvent.click(screen.getByRole("button", { name: "保存答辩" }))
    // 答了第二关 → 聚焦它后面那条仍待回应的第三关
    expect(await screen.findByText("仍待回应 2")).toBeInTheDocument()
    expect(expandedRow()).toHaveAccessibleName(/第三关/)
    fireEvent.click(screen.getByRole("button", { name: "我还不能回应 ▾" }))
    fireEvent.click(screen.getByRole("button", { name: /暂缓这条挑战/ }))
    fireEvent.change(screen.getByLabelText("何时重看"), { target: { value: "later" } })
    fireEvent.click(screen.getByRole("button", { name: "确认暂缓" }))
    // 暂缓第三关 → 后面没有了，绕回第一关
    expect(await screen.findByText("仍待回应 1")).toBeInTheDocument()
    expect(expandedRow()).toHaveAccessibleName(/第一关/)
    fireEvent.click(screen.getByRole("button", { name: "撤回这条挑战" }))
    fireEvent.change(screen.getByLabelText("撤回理由"), { target: { value: "不适用" } })
    fireEvent.click(screen.getByRole("button", { name: "确认撤回" }))
    // 撤回后已无仍待回应：停在刚处理的这一关
    expect(await screen.findByText("没有仍待回应的挑战")).toBeInTheDocument()
    expect(expandedRow()).toHaveAccessibleName(/第一关/)
    expect(screen.getByText("理由：不适用")).toBeInTheDocument()
  })
})

describe("ReviewRoundDesk literature challenge in the embedded panel (S2)", () => {
  const evidence = [{ id: "m-1", excerpt: "第一份摘录", source_locator: "Paper A", parse_status: "parsed" as const, purpose: "evidence" as const }, { id: "m-2", excerpt: "第二份摘录", source_locator: null, parse_status: "parsed" as const, purpose: "evidence" as const }]
  const litChallenge = { ...challenge, id: "ch-lit", attack_surface: "文献里的反例" }

  it("with a local selection, sends it as before and focuses the new challenge", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValueOnce(makeRound()).mockResolvedValueOnce(makeRound({ challenges: [challenge, litChallenge] }))
    vi.mocked(researchUniverse.literatureChallenge).mockResolvedValue(responded({ challenge_id: "ch-lit", review_round_id: "r-1" }))
    const onLoaded = vi.fn()
    const selection = { material_ids: ["m-9"], external_refs: [{ locator: "arxiv:1", excerpt: "摘要", url: null }] }
    render(<AppRouter><ReviewRoundDesk roundId="r-1" onLoaded={onLoaded} literature={{ selection, evidence }} /></AppRouter>)
    await screen.findByText("边界尚未说明")
    expect(onLoaded).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole("button", { name: "用所选文献发难" }))
    await waitFor(() => expect(researchUniverse.literatureChallenge).toHaveBeenCalledWith("r-1", expect.objectContaining({ ...selection, expected_sequence: 0 })))
    await waitFor(() => expect(screen.getByRole("button", { expanded: true })).toHaveAccessibleName(/文献里的反例/))
    expect(onLoaded).toHaveBeenCalledTimes(2) // 改动后重读这一轮 → 宿主刷新左栏
  })

  it("without a local draft, lists evidence materials unchecked and sends the picked ones as material_ids", async () => {
    vi.mocked(researchUniverse.literatureChallenge).mockReset().mockResolvedValue(responded({ challenge_id: "ch-lit", review_round_id: "r-1" }))
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound())
    render(<AppRouter><ReviewRoundDesk roundId="r-1" literature={{ evidence }} /></AppRouter>)
    await screen.findByText("边界尚未说明")
    fireEvent.click(screen.getByRole("button", { name: "用所选文献发难" }))
    const boxes = screen.getAllByRole("checkbox")
    expect(boxes).toHaveLength(2)
    expect(boxes.every((b) => !(b as HTMLInputElement).checked)).toBe(true)
    const send = screen.getByRole("button", { name: "发难" })
    expect(send).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/第二份摘录/))
    fireEvent.click(send)
    await waitFor(() => expect(researchUniverse.literatureChallenge).toHaveBeenCalledWith("r-1", expect.objectContaining({ material_ids: ["m-2"], external_refs: [] })))
  })

  it("is disabled when there is neither a local selection nor evidence material", async () => {
    vi.mocked(researchUniverse.reviewRound).mockResolvedValue(makeRound())
    render(<AppRouter><ReviewRoundDesk roundId="r-1" literature={{ evidence: [] }} /></AppRouter>)
    expect(await screen.findByRole("button", { name: "用所选文献发难" })).toBeDisabled()
  })
})
