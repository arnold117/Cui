import { describe, expect, it } from "vitest"
import { emptyDraft, journeyStage, type JourneyDesk } from "./dialogueDraft"

// spec-workspace-journey S1 推导表:每行一条完成条件 + 当前阶段规则
const desk = (over: Record<string, unknown> = {}) => ({ claims: [], review_rounds: [], pending_challenges: [], materials: [], user_position: "exploring", ...over }) as unknown as JourneyDesk
const draft = (over: Record<string, unknown> = {}) => ({ ...emptyDraft("w"), ...over })
const claim = { id: "c1", text: "c" }
const round = (verdict: unknown = null) => ({ id: "r1", claim_snapshot: { text: "c" }, question_snapshot: { text: "q" }, verdict })
const gaps = (status: string) => ({ landscape: { gaps: [{ id: "g1", status }] } })
const conc = { id: "x", type: "tentative_answer", text: "t" }
const pending = { pending_challenges: [{ id: "ch1", review_round_id: "r1", status: "pending" }] }

describe("journeyStage done table", () => {
  it.each([
    ["1 出发点 · hypothesesDone", 1, desk(), draft({ hypothesesDone: true }), true],
    ["1 出发点 · skipHypotheses", 1, desk(), draft({ skipHypotheses: true }), true],
    ["1 出发点 · 服务端已有 claim", 1, desk({ claims: [claim] }), draft(), true],
    ["1 出发点 · 服务端已有材料", 1, desk({ materials: [{ id: "m1" }] }), draft(), true],
    ["1 出发点 · 空草稿空工作区", 1, desk(), draft({ hypothesesText: "未确认的草稿" }), false],
    ["2 选料 · 草稿有覆盖梳理", 2, desk(), draft({ summary: "s" }), true],
    ["2 选料 · 服务端已有 claim", 2, desk({ claims: [claim] }), draft(), true],
    ["2 选料 · 只有选料没有梳理", 2, desk(), draft({ selected: ["a"] }), false],
    ["3 覆盖与 claim · 服务端已有 claim", 3, desk({ claims: [claim] }), draft(), true],
    ["3 覆盖与 claim · 草稿 roundId 不算", 3, desk(), draft({ summary: "s", roundId: "r1" }), false],
    ["4 对抗 · claimAck", 4, desk(), draft({ claimAck: true }), true],
    ["4 对抗 · 有一轮已裁决", 4, desk({ review_rounds: [round({ verdict_type: "survived" })] }), draft(), true],
    ["4 对抗 · gap 已完成", 4, desk(gaps("confirmed")), draft(), true],
    ["4 对抗 · 只有未裁决的轮次", 4, desk({ review_rounds: [round()] }), draft(), false],
    ["5 gap · confirmed", 5, desk(gaps("confirmed")), draft(), true],
    ["5 gap · corrected", 5, desk(gaps("corrected")), draft(), true],
    ["5 gap · pending 不算", 5, desk(gaps("pending")), draft({ confirmedGapIds: ["g1"] }), false],
    ["6 结晶 · concluded 但还没定去向不算", 6, desk({ user_position: "concluded", conclusion: conc }), draft(), false],
    ["6 结晶 · concluded + 本机点过「只留在本次」", 6, desk({ user_position: "concluded", conclusion: conc }), draft({ keptLocal: "x" }), true],
    ["6 结晶 · 「只留在本次」是给旧结论点的不算", 6, desk({ user_position: "concluded", conclusion: conc }), draft({ keptLocal: "older" }), false],
    ["6 结晶 · branched", 6, desk({ user_position: "branched" }), draft(), true],
    ["6 结晶 · absorbed", 6, desk({ user_position: "absorbed" }), draft(), true],
    ["6 结晶 · paused 不算", 6, desk({ user_position: "paused" }), draft(), false],
    ["6 结晶 · 重开后 conclusion 仍在也不算", 6, desk({ user_position: "exploring", conclusion: { id: "x", type: "tentative_answer", text: "t" } }), draft(), false],
  ])("%s", (_name, stage, d, dr, expected) => {
    expect(journeyStage(d, dr).done[stage - 1]).toBe(expected)
  })
  it("6 结晶 · concluded + 这条结论已结晶进方向(首页投影)", () => {
    expect(journeyStage(desk({ user_position: "concluded", conclusion: conc }), draft(), true).done[5]).toBe(true)
    expect(journeyStage(desk({ user_position: "exploring", conclusion: conc }), draft(), true).done[5]).toBe(false)
  })
})

describe("journeyStage current stage", () => {
  const allButSix = { claims: [claim], ...gaps("confirmed") }
  it("first not-done stage on a fresh workspace", () => {
    expect(journeyStage(desk(), draft()).current).toBe(1)
    expect(journeyStage(desk(), draft({ hypothesesDone: true })).current).toBe(2)
    expect(journeyStage(desk(), draft({ hypothesesDone: true, summary: "s" })).current).toBe(3)
  })
  it("another device (empty draft) with claims lands on 对抗, not stage 1", () => {
    expect(journeyStage(desk({ claims: [claim], review_rounds: [round()] }), draft()).current).toBe(4)
  })
  it("pending challenges keep 对抗 current even when later stages are done", () => {
    expect(journeyStage(desk({ ...allButSix, ...pending }), draft({ claimAck: true })).current).toBe(4)
  })
  it("answered-but-unverdicted challenges are not 待回应: they don't hold 对抗 current", () => {
    const answeredOnly = { pending_challenges: [{ id: "ch2", review_round_id: "r1", status: "answered" }] }
    expect(journeyStage(desk({ ...allButSix, ...answeredOnly }), draft({ claimAck: true })).current).toBe(6)
    expect(journeyStage(desk({ ...allButSix, pending_challenges: [...answeredOnly.pending_challenges, ...pending.pending_challenges] }), draft({ claimAck: true })).current).toBe(4)
  })
  it("pending challenges do not pull a crystallized workspace back to 对抗", () => {
    expect(journeyStage(desk({ ...allButSix, ...pending, user_position: "concluded" }), draft()).current).toBe(6)
  })
  it("all done stays on 6; reopen makes 6 not done again", () => {
    expect(journeyStage(desk({ ...allButSix, user_position: "concluded", conclusion: conc }), draft()).current).toBe(6) // 位置已确认、去向未定:停在 6
    const concluded = journeyStage(desk({ ...allButSix, user_position: "concluded", conclusion: conc }), draft({ keptLocal: "x" }))
    expect(concluded).toEqual({ current: 6, done: [true, true, true, true, true, true] })
    const reopened = journeyStage(desk({ ...allButSix, user_position: "exploring", conclusion: { id: "x", type: "tentative_answer", text: "t" } }), draft())
    expect(reopened.done[5]).toBe(false)
    expect(reopened.current).toBe(6)
  })
})
