# Spec: Lens 第三刀 — 可查询语料 / 语料图（Corpus Graph）

> 状态：草案 v0.1（2026-06-19，待 grill）
> 路线位置：P2 · Lens = 价值梯子 L3 第三刀（③ 可查询语料）。①②（品味锚、跨想法矛盾检测）已完成。
> 来源：LitScribe grill 把 ③ 框为"**结构化、可跑矛盾检测的个人语料 + 版本轨迹**，不像 GPT 的浅摘要 blob 不可查询"。可查询是因为**结构化**，不是因为 embed。
> **形态（Arnold 拍）= 图结构，分期 0→1→2**。

---

## 0. 一句话

把用户的个人语料（grilled claim + 轨迹 + outcome + 关系）建成一张**图**——节点是 claim/material，边是它们之间的关系——让用户**主动查询**自己的思想史（PULL），与 ①② 在 grill 时自动浮现（PUSH）互补。**分期推进：Tier 0 纯结构图 → Tier 1 持久语义图 → Tier 2 完整 GraphRAG。**

---

## 1. 为什么图 + 为什么分期

1. **图贴"结构化语料"的本质**：claim 之间的关系（矛盾 / builds-on / 同方法 / 取证同一 material）是护城河的核心，图让关系成为一等公民。①② 本就在隐式做关系查询。
2. **PULL 补 PUSH**：①② 是 grill 时 Lens 自动捞；③ 是用户**主动问自己的库**（"我对 X 下过什么结论"、"哪些想法我 kill 过"）。新的面向用户能力。
3. **分期 0→1→2 = 先证明再承诺**：图天然想持久化（建一次查多次），而 ①② 刻意"即时算零持久"。Tier 0 先用**纯结构投影**证明图模型 + 查询有用，**不碰持久化/LLM/embedding**；Tier 1 才引入持久化（语义边）；Tier 2 才是完整 GraphRAG。每档独立里程碑，避免一步踩进大架构。

---

## 2. 已决定（grill / 框定，不翻案）

- **可查询 = 因为结构化**：语料是事件溯源的 claim/trajectory/outcome，本就结构化可查；**Tier 0/1 不碰 embedding**（你的 aversion + 原始框定）。
- **PULL，用户主动**：③ 是用户发起的查询，不是 grill 时自动浮现。
- **分期硬约束**：
  - **Tier 0（当前）= 纯结构图投影**。节点 + 边全部**从已有事件派生**，**零持久化、零 LLM、零 embedding**——和 ①② 一样即时算。
  - **Tier 1（后）= 持久语义图**。grill 时用 LLM（复用 ②）算语义边并**存下来**，图随 grill 生长。**这是持久 Lens 存储正式进入的地方**（③ = "Lens 持久化的开端"）。
  - **Tier 2（更后）= 完整 GraphRAG**。实体抽取 + 社区检测 + 摘要（+ dense vector）。**大架构承诺，单独决定，不闷头改**（LitScribe 标过的核心架构问题）。

---

## 3. Tier 0 数据流（草案）

```
GET /library/{library_id}/graph   （纯投影，即时算）
   │
   ├─ 节点：list_claims(library_id) → 每个 claim
   │     属性：id, body, status(claim_status 投影: survived/killed/open/parked)
   │     （Q-1：要不要也把 material 当节点）
   │
   ├─ 边：全部从事件/结构派生（无 LLM）
   │     - claim —in→ artifact（claim.artifact_ids）
   │     - claim —grounds→ material（确认的 ground 事件）
   │     - claim —contradicts→ claim（确认的 ② lens_contradiction CHALLENGE，past_claim_id）
   │     - claim —in→ project（artifact.project_ids）
   │     （Q-2：Tier 0 收哪几类边）
   │
   └─ 返回 { nodes:[...], edges:[...] }（前端可渲染图 / 可遍历）
       （Q-3：返回整库图，还是只返回某 claim 的邻居子图）
```

- 纯函数投影 + repo 读取，无写、无 LLM、无持久化——和现有投影同性质，可单测。

---

## 4. Tier 0 已决（2026-06-19，"开始弄就好"）

- **Q-1 节点**：claim 为主节点（id/body/status）+ material 次节点（被 ground 的那些）。artifact/project 暂作 claim 属性，不单列节点。
- **Q-2 边**：`contradicts`（已确认的 ② lens_contradiction，连 target_ref ↔ past_claim_id）+ `grounds`（已确认 ground，claim ↔ material）。这俩最有语义价值；artifact/project/taste-anchor 边后续按需加。
- **Q-3 输出**：整库图 `GET /library/{id}/graph` → `{nodes, edges}`；focus 邻居子图后续。
- **Q-4 前端**：分 0a（后端投影 + 测）→ 0b（最简图视图）。先 0a。
- **Q-5 边确认语义**：**只收已确认关系**（取证不定见）——pending 的 ② contradiction / ground 不进图。

---

## 5. 验收（Tier 0 算「通」）

- [ ] `GET /library/{id}/graph` 返回 Library 内 claim 节点（带 status）+ 结构边，纯投影、无 LLM/持久化。
- [ ] 一条已确认的 ② lens_contradiction → 图里有一条 claim—contradicts→claim 边。
- [ ] 一条已确认 ground → claim—grounds→material 边（若 material 入节点）。
- [ ] PARK/未确认的关系**不**进图（取证不定见）。
- [ ] 跨 Library 不串（作用域 = Library）。
- [ ] 前端能把它渲染成一张可读的图（最简即可）。

---

## 6. 备注（Tier 1 / Tier 2，分期后续）

- **Tier 1（持久语义图）= LLM 算的语义边记成 `link` 事件**（grill Tier 1 收敛中）。
  - **边集已被 L4 scoping 反推定死**（见 `docs/scope-l4-agenda-copilot.md`）：`contradicts`（②已有）+ `builds-on/depends-on`（新）+ `shares-method/shares-gap`（新）。跨 Project 可遍历、claim status 在图上、可算 centrality。**无 embedding。**
  - **Q1 已决（2026-06-19）= 边 = 事件**：边记成 `link` 事件（source_claim/target_claim/edge_type/reason），追加到 source claim 的 artifact 流；`corpus_graph` 投影顺带读 link 事件。**持久化白嫖事件存储、零新表/迁移、staleness 靠 retract/supersede 事件**——不建独立边表（dual-write 一致性债 + 索引优势当前过早；真慢了再从 link 事件派生只读索引 read-model，不破纯粹性）。
  - **Q2 已决（2026-06-19）= 懒算 + 出生 confirmed 可撤回**：边不在每次 grill 时算，而是**取图 / L4 扫议程时**对还没算过边的 claim 对**懒算一次**（复用 ② 词面粗筛框定候选对、不全配对），追加 `link` 事件；之后读缓存。link 事件**出生 confirmed=True、可 retract**（边是取证事实非定见，逐条确认摩擦太大；错边在图里看得见、撤掉即可）。
  - **Q3 已决（2026-06-19）= staleness 零 bespoke 逻辑**：现有模型下 claim body 不可变（无编辑流）、status 是投影永远当前、verdict 翻转**不失效边**（killed 依赖正是 L4 威胁信号）。retract link 事件 / retract claim 悬空 drop 全走现有机制。**未来 caveat**：若加 claim-body 编辑流 → retract 该 claim 的 link 事件 + 重算。
  - **Tier 1 实现要点**：新 `LINK` 事件类型（payload: source_claim_id/target_claim_id/edge_type/reason）；`corpus_graph` 投影扩展读 confirmed LINK 事件 → 新边；`LensService.compute_semantic_edges(library_id)`（async/LLM，懒触发、复用粗筛、compute-once 跳过已连对、append LINK）；`build_semantic_edges_prompt`；触发端点（取图前先 build）。corpus_graph **仍是纯读投影**（算边是独立 write-action，不污染投影纯度）。
- **Tier 2（完整 GraphRAG）**：实体抽取 + 社区检测 + 摘要 + dense vector。核心架构大决定，按 LitScribe 旧账"先拉出方向问题，不闷头改"。
- 守的铁律：作用域 Library；取证不定见（只收已确认关系）；Tier 0/1 不碰 embedding。
