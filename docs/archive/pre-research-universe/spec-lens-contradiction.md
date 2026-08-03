# Spec: Lens 第一刀 — 跨想法矛盾检测（Cross-Idea Contradiction）

> 状态：草案 v0.1（2026-06-19）
> 路线位置：P2 · Lens 护城河 = 价值梯子 L3「跨时间挑战思维轨迹」的**第一刀**。
> 前置：L2 已达成（P0 轨迹脊柱 + P1 搜索结晶/证据对辩）。
> 来源：LitScribe 两场 grill（`project_idea_grill_direction.md` + `project_idea_mvp_spec.md`「④L3起步」）已把 Lens 概念啃透，本 spec 不重 grill 方向，只把 ② 这条候选落成第一刀。

---

## 0. 一句话

当下 grill 一个 claim 时，**Lens 翻出用户自己 Library 内已拷问过的旧 claim（survived / killed），检出与当下 claim 的矛盾或张力，作为一条带轨迹出处的 challenge 浮现**（pending，用户确认）。这是 Lens 的第一个「读出」机制 —— L3 的 tracer bullet。

---

## 1. 为什么是这一刀（依赖顺序，不是偏好）

1. **L2 已牢，前置解锁**。grill 记录定的顺序「L2 打牢再 L3」已满足：脊柱在、grilled trajectory 在产出、证据对辩闭环通。
2. **三候选里 ② 落地最实**。靠现有事件流 + `claim_status` 投影就能拿到旧结论；矛盾判定可 cherry-pick LitScribe 的 contradiction 纯逻辑，接 Cui 自己的 LLM client。
3. **它是「读出」的最小垂直切片**。喂入点（`lens_feed_projection`）早有，缺的是「读出 → 影响当下 grill」。② 用最少的料证明这条回路通，且**不碰 taste 红线**（① 品味锚才碰）。

排除的错误起点：
- ❌ 不从 taste 绝对打分起（红线，留给 ① 且要先把逻辑做对）。
- ❌ 不从 Lens 持久化 / embedding 索引 / 学习算法起（grill 已定「没料别起学习算法」）。第一刀**不建持久 Lens 对象**，纯在 grill 时即时算。

---

## 2. 已决定（grill 已拍，不翻案）

- **作用域 = Library 内穿透**。候选只在当前 Library 取，跨库硬墙（合规焊死，deferred）。
- **只吃 grilled trajectory**。候选集 = Library 内**有确认 verdict** 的 claim，状态 ∈ {`survived`, `killed`}。**永不含 PARK / `open`**（防投毒 = grill 已定铁律）。
- **阵亡也是料**。`killed` 旧 claim 同样进候选——「你以前杀过这个想法」是强信号，正是「把垃圾变矿」。
- **取证不定见**。矛盾检出 → **pending 的 challenge 事件**，走现有确认闸门。系统呈现「你在 X 里 survived/killed 过 Y、与当下冲突」这个**事实**，**不替用户裁决当下 claim 的死活**。
- **红线**：不做 LLM 绝对 taste 打分。判定锚在**真实旧 claim** 上，输出是「这两条冲突吗 + 冲突在哪」，不是「这个想法好不好」。
- **检测档位（Q-C 已决 2026-06-19）**：
  - **硬矛盾 + 重复 = 常开**。C 断言 X、旧 claim 断言 ¬X（逻辑冲突）；或 C 本质是你已 killed/survived 过的同一想法（重复）。这是第一刀的 tracer，信号最干净。
  - **软张力 = 可开、默认关**。如「你这条和过去 N 条都是 method-X 的 incremental 变体」。必须长成**取证形状**（事实模式 + 一个问题，判断留给用户），**永不**输出对想法好坏的绝对评价（= 守 taste 红线）。
  - **① 品味锚仍是独立的后续一刀**。② 的软张力只是 ① 的安全子集（跨想法 incremental 模式，取证形状）；完整 ① 品味锚（学习研究品味画像、可能打分/排序）单独做，由它正面解决打分红线。
- **事件建模（Q-D / Q-F 已决 2026-06-19）**：**复用现有 `CHALLENGE` 动词，不新增 verb**。Lens 浮现的矛盾就是一条 challenge，只是来源是「你的历史」（类比 `auto_generated` 来源是 LLM）。靠 `payload.kind="lens_contradiction"` + 出处区分。
  - 白嫖整套 grill 机器：challenge → answer → verdict → 确认/撤回。用户**答辩**旧结论冲突，系统判这次理由站不站得住——历史真正进到 grill 被解决，不是飘个提示。
  - 零投影改动（lens_feed / doc / claim_status 已认 CHALLENGE）；前端复用 GrillMessage，按 `payload.kind` 加「⟲ 来自你的轨迹」徽章。
  - 硬/软、survived/killed 的差异全压进 payload（`tension_type`、`past_outcome`），**不拆动词**。措辞差异只是渲染/prompt 细节。
- **前端集成（Q-D 落地时新增，2026-06-19 已决）**：Q-D「lens challenge 走完整 challenge→answer→verdict」与现有 `useGrillFlow` 的**线性单线程** phase 状态机冲突（注入 lens challenge 会灌水轮数、错乱 answer 路由）。选**重做状态机为 challenge 为中心**（option 3）：
  - 每条 challenge（LLM 或 lens）**各自一个生命周期**，从事件派生：`awaiting_answer → awaiting_verdict → awaiting_decision → resolved`。lens 与 LLM challenge **同生命周期**（真守 Q-D）。
  - claim 整体状态 = 所有 challenge 的 rollup（全 resolved 才解锁 继续/到此/promote）。
  - UI：线性聊天 → **多 challenge 并行板**，每条 inline 答辩框 / 确认-撤回 / resolved 徽章。
  - `submitAnswer(challengeId, text)` 按 challenge id 定向，不再「找最后一个 challenge」。
  - 全局 phase 是当初的简化；这次把「claim 整体状态」与「单条 challenge 状态」两层拆开。

---

## 3. 数据流 + 事件（草案）

```
当下 claim C（grill 中）
   │
   ├─ 候选检索：枚举 Library 内 claims（排除 C 所属 artifact）
   │     过滤 claim_status(events) ∈ {survived, killed}
   │     【实现注：repository 暂无 list_claims(library_id)，需补，
   │       或经 list_artifacts(library_id) → 各 artifact 的 claims 派生】
   │
   ├─ 矛盾判定：对每个候选旧 claim P，LLM 判 C⟷P 是否矛盾/张力
   │     cherry-pick contradiction 纯逻辑 + Cui LLM client
   │     返回 {contradicts: bool, tension: str}
   │     （词面/主题词粗筛 shortlist top-K → 只对 shortlist 跑 LLM；Q-B 已决）
   │
   └─ 输出：对命中的 (C, P) → 产一条 pending challenge 事件
         type=CHALLENGE（复用，不新增动词 — Q-D 已决）
         actor="system"，confirmed=False，target_ref=C.claim_id
         payload={
           kind: "lens_contradiction",
           past_claim_id, past_artifact_id,
           past_outcome: "survived" | "killed",
           tension_type: "hard" | "duplicate" | "soft",
           tension: "<冲突在哪>",
           auto_generated: true,
         }
```

- 复用现有 challenge 渲染 + 确认/撤回闸门；前端加「⟲ 来自你的轨迹」标记（区别于普通 grill challenge 和文献证据徽章）。
- 这是 Lens「读出」的首形态：第一刀只补「读出→当下 grill」这一段回路。

---

## 4. 待定（= 下次 grill 的靶子）

- ~~Q-A 触发时机~~ → **已决 2026-06-19：grill 起手自动扫一次**（不是每轮、不是每次改字）。命中 → 浮现 pending challenge；零命中 → 无事发生。理由：矛盾的价值在「用户事先不知道」，显式按钮会阉掉撞脸价值；且检测是取证（可自动化），产出 pending（定见仍人定）。grounding 的「显式」先例不适用（那是用户驱动 claim×paper，这里用户不知道冲突在哪）。
- ~~Q-B 候选粗筛~~ → **已决 2026-06-19：词面/主题词粗筛（共享主题词 shortlist top-K）+ 对 shortlist 跑 LLM 判矛盾**。**不建 embedding 索引、不起持久 Lens 存储**（那是把 ③ 可查询语料 + Lens 持久化提前拉进来，推到它自己那一刀）。词面筛用完即弃、对 solo 库规模够用。诚实代价：连主题词都不共享的纯语义隐蔽矛盾会漏（召回 <100%），记 backlog，词面筛实在不够再上 embedding。
- ~~Q-C 矛盾 vs 重复 vs 软张力~~ → **已决（见 §2 检测档位）**：硬矛盾+重复常开，软张力可开默认关、取证形状，① 仍独立。
- ~~Q-D 事件类型~~ → **已决（见 §2 事件建模）**：复用 `CHALLENGE` + `payload.kind`，不新增动词。
- ~~Q-F survived vs killed 措辞~~ → **已决（随 Q-D）**：同一 `CHALLENGE` 事件，`payload.past_outcome` 区分；措辞是渲染/prompt 细节，非独立岔口。
- ~~Q-E 旧 claim 的 retract / 改写~~ → **已决 2026-06-19**：retract **免费处理**——候选过滤 = `claim_status ∈ {survived, killed}`，而 `claim_status` 本就把 retract 的 verdict 折掉（退回 open → 自动落选）。改写：拿当下 body 比，不特殊处理（substance-edit-要重新拷问的铁律兜住语义漂移）。
- **Q-F survived vs killed 的措辞**：撞 survived 旧 claim（「你已确立相反结论」）和撞 killed 旧 claim（「你已否决过这个想法」）措辞应不同——一个事件类型 + payload.past_outcome 够，还是要分。

---

## 5. 验收（第一刀算「通」的标准）

- [ ] Library 内造两个 claim：旧的经 grill `survived`，新的与之矛盾 → grill 新 claim 时浮现一条带出处（`past_claim_id` + `past_outcome=survived`）的 **pending** challenge。
- [ ] 候选**只含** grilled（survived/killed）旧 claim；PARK / `open` 的旧 claim **不**触发。
- [ ] 撞 `killed` 旧 claim 同样能浮现（阵亡也是料）。
- [ ] 浮现的是 pending challenge，用户确认前**不改**当下 claim 任何状态；可撤回。
- [ ] 候选**不跨 Library**。
- [ ] 全程**不出现** LLM 绝对 taste 打分。

---

## 6. 备注

- 这是 L3 的 **tracer**：证明「历史 → 当下 grill」的读出回路通。① 品味锚（碰 taste 红线、要先把逻辑做对）、③ 可查询语料（基建）排在此之后。
- **Lens 存储刻意不在第一刀建**：纯在 grill 时即时算。持久化 / 索引 / 学习算法等真实轨迹攒厚、需求清楚了再起（呼应 grill「没料别起学习算法」）。Q-B 的 embedding 筛是第一个可能撬动持久化的点，单独拍。
- 守的两条铁律：**只吃 grilled trajectory，永不吃 PARK**；**取证（翻出矛盾事实）不定见（不替你裁决）**。

---

## 7. 实现备注（非 grill 岔口，落地时知道即可）

- **`repository` 缺 `list_claims(library_id)`** —— 现仅有 `list_artifacts` + `get_claim`。枚举 Library 旧 claim 需补此方法（InMemory + Postgres），或经 `list_artifacts → 各 claim` 派生。候选检索的前提。
- **矛盾判定逻辑** —— cherry-pick LitScribe `litscribe/tools/contradictions.py` 的纯逻辑，接 Cui 自己的 LLM client（不引 langchain），新增 `build_contradiction_prompt`。
- **软张力开关** —— 默认关。第一刀做成简单的 request 参数 / 设置项即可（`include_soft: bool=false`），不单列 UI。
- **词面粗筛** —— 提取当下 claim 与候选 claim 的主题词（名词/实体）做 overlap shortlist；纯函数、可测。
- **前端徽章** —— GrillMessage 按 `payload.kind=="lens_contradiction"` 渲染「⟲ 来自你的轨迹」+ past_outcome 措辞，复用证据徽章那套。

---

> **grill 收敛 2026-06-19**：§4 六问（Q-A…Q-F）全部已决，决定见上各节。spec 进入可实现态。

