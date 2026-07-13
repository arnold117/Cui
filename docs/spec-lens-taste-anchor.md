# Spec: Lens 第二刀 — 品味锚（Taste Anchor）

> 状态：草案 v0.1（2026-06-19，待 grill）
> 路线位置：P2 · Lens = 价值梯子 L3 的第二刀（① 品味锚）。第一刀 ② 跨想法矛盾检测已完成。
> 来源：LitScribe grill 已把 taste 模型啃透（`project_idea_mvp_spec.md` IdeaDoc schema 的 `taste` 字段 + 三层分级 + 红线）。本 spec 不重 grill 方向，把它落成 Cui 原生第一刀。
> **第一刀范围（Arnold 拍）= 两锚合一**：相对文献（prior_art）+ 相对用户自己的 grilled 历史，一起给定位。

---

## 0. 一句话

grill 一个 claim 时，Lens 把它**锚在两类事实上**——相对**真实文献**的新颖位置 + 相对**你自己 grilled 历史**的品味位置——用四档 rubric（`replication / incremental / novel_but_tasteless / tasteful`）作框架，**带具体出处的理由**，作为一条**可反驳的 pending CHALLENGE** 抛回给你（"这相对 X 已做过、且跟你 kill 过的 N 个同型，值得做的增量在哪？"）。**Lens 只锚 + 问，绝不裁决"有没有品味"，更不是凭空绝对打分。**

> **什么是品味（这刀的地基，2026-06-19 grill 拍）**：品味 = 对"**值不值得做**"的私人判断，**可反潮流**，且**独立于新颖性/可发表性**。两个反证：(汽车) 全行业运动化年轻化是共识，但你觉得丑、老车更好看 → 品味 ≠ 跟共识；(材料) 干啥都能发论文 → 品味 ≠ 新颖/可发表。**两个轴别糊**：新颖轴（被做过没/多增量，文献能量）vs 品味轴（值不值得，量不出、绝不能从共识推）。`novel_but_tasteless` 档正是"新颖拉满、品味为零"。

---

## 1. 为什么是这一刀（两锚合一）

1. taste 是护城河尖端（"值不值得做"，非"能不能做"），GPT 最弱、Lens 最该长的地方。
2. **两套机器都已就绪**：prior_art 锚用 P1（多源搜索 + grounding），用户历史锚用 ② 的候选枚举（Library 内 grilled claim）。
3. **两锚都是"事实锚"，一起压彩虹屁**：文献锚把**新颖性**钉在真实 paper 上（防 LLM 瞎说"这很新"），历史锚把**品味**钉在你真实的 kill/survive 记录上（防 LLM 瞎夸"这很 tasteful"）。两个轴各有事实锚 → 无锚不出 verdict 的硬约束才兜得住整刀。

---

## 2. 已决定（grill 已拍 / 红线，不翻案）

- **两锚的角色分清（2026-06-19 grill，命门修正）**：
  - **文献锚 = 新颖轴的事实输入**——"这被 X 做过 / 多增量"。它**只管新颖，不产出品味**。
  - **历史锚 = 品味的真正来源**——品味私人、可反潮流，所以**只能锚你自己 revealed 的偏好**（你 kill 过什么、为什么为 survive 的辩护、反复选做什么不做什么），**绝不锚"大家在做什么"**（把 on-trend/共识当 tasteful = 正错，会奖励跟风、惩罚反潮流品味 = 汽车反证）。
  - **Lens 只锚 + 问，绝不下"这没品味"的定见**（取证不定见）：它摆出新颖事实 + 你的历史事实，把"值不值得做"抛回给你裁决。Lens 学并反射**你的**品味，不输出客观品味。
- **四档 rubric**：`replication`（已被做过）/ `incremental`（小增量）/ `novel_but_tasteless`（新但不值得）/ `tasteful`（新且值得）。带 `reasoning` + `anchored_refs`（papers 和/或 past_claims）。
- **形态 = 顾问不裁判 + 可反驳**：作为 pending CHALLENGE 浮现，用户可答辩/撤回，走现有 challenge→answer→verdict 闸门。**绝不裁决 claim 死活、绝不改 claim status。**
- **红线 = 绝不绝对打分**：输出是**相对定位**（相对这些 papers、相对你这些过去 claim），不是"这想法 7/10 / 好不好"。tier 必须由 anchored_refs 支撑。
- **⚠️ 反彩虹屁是命门**：LLM 默认迎合共识 = 品味的反面，**做砸比不做更糟、腐蚀 grounded 信任**。所以：
  - **无锚不出 verdict**：给不出具体 anchored_refs（真实 paper / 真实旧 claim）就不浮现，不许凭 vibes 说"tasteful"。
  - **怀疑式默认**：偏向找"这不新在哪"，正面档（tasteful）要更强的 anchored 证据才给。
- **反彩虹屁机制（Q-C 已决 2026-06-19，命门）= 四层，前两层结构硬约束**：
  1. **无锚不出 verdict（硬）**：tier 必须挂 ≥1 个真实锚（真返回的 paper / 真实旧 claim）；锚不出来 → `return []`。让"凭 vibes 给档"结构上不可能。
  2. **锚先于档 / two-pass（硬）**：LLM 调用结构成"先找最近 prior work + 最像的旧 claim，再据此定位"；档从锚推出，不是先有好感再找理由。
  3. **怀疑式非对称门槛（软）**：`tasteful` 要更高举证（显式论证"为什么不只是 incremental/replication" + 更强锚）；replication/incremental 是默认档。
  4. **prompt 明令（软）**：告诉 LLM"你默认会拍马屁，这是失败模式；要诚实相对定位、点名什么不新"。
  - **暂不上**独立的"挑刺前置步"（先单独跑一轮找反例再定档）——更抗彩虹屁但多一次调用，1+2+3+4 先跑，不够再加。
- **事件建模（Q-B 已决 2026-06-19）**：复用 `CHALLENGE` + `payload.kind="taste"`（同 ②），白嫖 challenge-centric 板 + 闸门，零投影改动。4 档 verdict 进 payload，本质仍是"逼你辩护值不值得做"的 challenge。
- **永不 gate（Q-E 已决 2026-06-19）**：taste tier 纯顾问，绝不参与 debt/promote/任何硬拦、绝不改 claim status。
- **锚可用性门槛（Q-G 已决 2026-06-19）= 历史必需、文献可选**：
  - **无 grilled 历史 → 不浮现**（品味唯一合法来源是历史；冷启动就该沉默，Lens 需轨迹喂——拿文献共识凑 = 禁的"共识当品味"）。
  - **有历史无文献 → 照常浮现**（品味轴有锚）；新颖档钉不准，reasoning 注明"文献未查到对位，以下基于你的历史"。
  - **有文献无历史 → 不浮现**（无品味来源；文献单独只是新颖事实，近 ② 地盘，不冒充 taste）。
- **只吃 grilled trajectory**：用户历史锚的候选 = Library 内 grilled（survived/killed）旧 claim，永不吃 PARK（同 ②）。
- **取证不定见**：摆出"相对 X 你这是 incremental"这个 anchored 事实 + 提问；裁决归用户。

---

## 3. 数据流 + 事件（草案）

```
当下 claim C（grill 中）
   │
   ├─ prior_art 锚：search_all(C 的主题) → 取最相关 top-K Material（paper）
   │     → 这些 paper 相对 C 的定位（已做过？多大增量？）
   │
   ├─ 历史锚：枚举 Library 内 grilled 旧 claim（复用 ② 的候选逻辑）
   │     → C 落在你历史里的模式（第 N 个 incremental？同一 angle 反复？）
   │
   ├─ LLM 综合：给 C 一个 rubric tier + reasoning + anchored_refs
   │     反彩虹屁 prompt：默认怀疑、无锚不给正面档、只做相对定位不打分
   │     无 grilled 历史锚 → 不浮现（return []，Q-G）；文献锚可缺（降级）
   │
   └─ 输出：pending CHALLENGE
         type=CHALLENGE（复用，payload.kind="taste"）
         actor="system", confirmed=False, target_ref=C.claim_id
         payload={
           kind: "taste",
           tier: "replication|incremental|novel_but_tasteless|tasteful",
           reasoning: "<相对定位，无打分>",
           anchored_papers: [{material_id, title}],
           anchored_claims: [{past_claim_id, past_outcome}],
           question: "<可反驳的挑战，如：值得做的增量在哪？>",
           auto_generated: true,
         }
```

- 复用 challenge-centric grill 机器（answer→verdict→确认/撤回）+ 多 challenge 板；前端按 `payload.kind=="taste"` 加专属徽章（区别于 ② 的 lens_contradiction 和文献证据）。

---

## 4. 待定（= grill 靶子）

- ~~Q-B 事件类型~~ → **已决：复用 `CHALLENGE` + payload.kind="taste"**（见 §2）。
- ~~Q-E tier 永不 gate~~ → **已决：纯顾问，绝不 gate / 改 status**（见 §2）。
- ~~Q-A 触发~~ → **已决 2026-06-19：显式「评品味」按钮**（非自动）。taste 是主动去问的刻意检查、主要靠历史定位；② 的「撞脸=自动」论证不适用。第一刀显式，以后想自动再说。
- ~~Q-D prior_art 深度~~ → **已决 2026-06-19：轻量**——单源 OpenAlex top-K、不做完整 grounding。文献锚只供新颖事实，单源 top-K 标题/摘要够用；无锚不出 verdict 兜底。
- ~~Q-C 反彩虹屁机制~~ → **已决（见 §2，命门）**：1 无锚不出 + 2 锚先于档（硬）+ 3 怀疑非对称门槛 + 4 prompt 明令（软）；独立挑刺前置步暂不上。
- ~~Q-F 与 ② 的关系/去重~~ → **已决 2026-06-19：划清分工**。② = pairwise 逻辑（硬矛盾 + 重复）；① = aggregate 品味定位，**收编 incremental-pattern**。②的软张力本就是①的安全子集+默认关，① 上线即取代之——② 实战只跑 hard+duplicate。不删 ②的 `include_soft`（默认关、无害），spec 注明 ① 为 incremental-pattern 唯一出口。零重叠。
- ~~Q-G 锚定源的取舍~~ → **已决：历史必需、文献可选**（见 §2）。无历史沉默；有历史无文献降级浮现；有文献无历史沉默。

> **grill 收敛 2026-06-19**：§4 七问（Q-A…Q-G）全部已决，决定见 §2 各节。spec 进入可实现态。

---

## 5. 验收（第一刀算「通」）

- [ ] grill 一个"撞了现有文献 + 你历史上同类 incremental"的 claim → 浮现一条 pending CHALLENGE，tier 合理、**带真实 anchored_papers 和/或 anchored_claims**。
- [ ] 给不出任何真实锚 → **不浮现**（绝不凭 vibes 出 verdict）。
- [ ] **冷启动（无 grilled 历史）→ 不浮现**，哪怕文献搜到一堆（Q-G：无品味来源）。
- [ ] **有历史无文献 → 照常浮现**，reasoning 注明基于历史、文献未对位。
- [ ] 正面档（tasteful）只在有强 anchored 证据时出现（怀疑默认）。
- [ ] 浮现的是 pending CHALLENGE，**不改 claim status、不 gate 任何东西**；可答辩/撤回。
- [ ] 历史锚候选**只含 grilled（survived/killed）**旧 claim；PARK/open 不算。
- [ ] 全程**无 LLM 绝对打分 / "好不好"措辞**，只有相对定位。
- [ ] 真 LLM（DeepSeek）live 验证：种"明显 incremental"的 claim → 给 incremental + 锚；种真新的 claim → 不轻易给 tasteful（不拍马屁）。

---

## 6. 备注

- **反彩虹屁（Q-C）是这刀的生死线**。其余都好办；这条做不对就是 AI 拍马屁、腐蚀前面 P1 攒的 grounded 信任，宁可不上。grill 重点砸这条。
- 与 ② 共享的基建：候选枚举（grilled claim）、CHALLENGE 复用、challenge-centric 板、Lens 即时算不持久。
- 仍不建 embedding / 持久 Lens 存储（prior_art 锚用 P1 即时搜，历史锚用 ② 即时枚举）。真要持久化等 ③ 可查询语料那刀。
- 守的铁律：只吃 grilled trajectory；取证不定见；**taste 红线（不绝对打分）**。

---

## 7. 实现备注（非 grill 岔口，落地时知道即可）

- **复用 ② 的候选枚举** —— `LensService` 里取 Library 内 grilled（survived/killed）旧 claim 的逻辑（含 `list_claims` + `claim_status` 过滤 + 词面粗筛）已有，历史锚直接复用。
- **复用 P1 搜索** —— prior_art 锚调 `search_openalex`（单源 top-K，不 ground）。
- **新 prompt** —— `build_taste_prompt(claim, prior_art_papers, past_claims)`：实现反彩虹屁 1+2+3+4（无锚不出、锚先于档、tasteful 高门槛、明令别拍马屁），返回 `{tier, reasoning, anchored_papers, anchored_claims, question}`，**无 grilled 历史则上游直接不调**。
- **service** —— 放进现有 `LensService`（加 `assess_taste(...)`）还是新 `TasteService`，落地时定；倾向并进 `LensService`（共享候选枚举）。
- **API + 前端** —— `POST /lens/{id}/assess-taste`（显式触发，非自动）；前端 grill 里加「评品味」按钮 + `payload.kind=="taste"` 的专属徽章（区别 lens_contradiction / 文献证据）。
- **② 软张力** —— 保持 `include_soft` 默认关、不删；① 为 incremental-pattern 唯一出口。

---

> **grill 收敛 2026-06-19**：七问全决，spec 可实现。下一步 = 提交 spec + 实现（分阶段交 subagent，主循环审）。
