# Spec: Verdict 判例增强 — 死因分诊 + Lens 吃理由

> 状态：已收敛（2026-07-13 grill，五问全决）
> 来源：viewpoints 库吸收（尸检分诊 / 判例回流 / 三层知识注入），吸收记录见用户记忆 `project_viewpoints_absorption.md`
> 术语已入 `CONTEXT.md`「死因分诊」一节

---

## 0. 一句话

kill 不是布尔：VERDICT(kill) 必带死因四档，偶然死必附复活条件；Lens 消费判例四元组（outcome + 死因 + 理由 + 复活条件），把「锚记录」升级成「锚判例」。

---

## 1. 为什么是这一刀（依赖顺序，不是偏好）

1. **捕获侧已在、消费侧断线**。verdict `rationale` 已必填且前端已渲染；但 ② 矛盾检测和 ① 品味锚的 prompt 只喂 `(claim_body, outcome)`——理由从没进过 Lens。接线是纯增量。
2. **schema 是时间敏感资产**。事件不可变：死因字段晚上线一天，轨迹就永久缺一天的死因数据，事后补不了。
3. **品味锚缺最肥一列**。taste-kill（「对，但不值得」）今天不可机读——revealed taste 的最高信号判例读不出来。
4. **L4 前置**。L4 已 scope「地基被别处 kill」威胁，其镜像「阵亡想法的复活条件被新证据满足」以本刀的复活条件为前置。

---

## 2. 已决定（grill 钉死，不再翻案）

### Q1+Q2+Q5 — 死因四档，kill 时必填

| 档 | 死在哪根轴 | 终局性 | 备注 |
|---|---|---|---|
| `refuted` 本质死 | 真值轴：就是错的 | 终局 | 含重复死（同构想法早已 kill） |
| `not_worth` 品味死 | 价值轴：对，但不值得 | 终局 | revealed taste 最高信号，① 的直接养料 |
| `boundary` 划界死 | 收窄换活 | 转世 | 可选关联后继 claim（`successor_claim_id`）→ 语料图免费得确定性 `narrowed_from` 边（非 LLM 来源） |
| `circumstantial` 偶然死 | 哪根轴都没死透 | **非终局** | **必附复活条件**——想不出复活条件 = 该选品味死。「等排期 ≠ 被判定不值得」结构强制，不靠自觉 |

- kill verdict 死因**必填**，不设「未分类」逃生口；「未分类」只是 legacy 事件的投影语义，不给新数据当懒惰默认。
- survive verdict 无死因。
- `auto_verdict`（LLM 起草）同步提议死因，走既有 confirmed=False + 人确认闸——机器起草人签名，模式照旧。

### Q3 — 复活条件 = 自由文本

- 不设结构化 DSL（抽象的时机：今天真实复活条件数量为零，凭空设计必错）。将来攒够真实语料再从数据反推结构；事件 payload 是 JSON，结构化是加法，不烧退路。
- UI placeholder 引导「可判定条件」写法（如「Tier 1 证明不够 + 接受 embedding」），不引导模糊愿望。
- 近期唯一消费者是 L4 的 LLM 议程扫描，读散文无障碍；确定性 trigger 引擎是后议的大架构。

### Q4 — Lens 判例注入

- 注入**四元组**：`outcome + death_cause + rationale（截断）+ revival_condition（仅偶然死）`。
- **量控 = 确定性截断**：单条 rationale 截前 300 字加省略号；不上 LLM 摘要压缩（多一跳调用 / 摘要幻觉 / 违背确定性优先）。
- ② pairwise 与 ① aggregate 两处统一注入；候选枚举 top-K=8 粗筛**不动**。
- legacy 事件缺死因 → prompt 标「死因未分类」，不假装有。
- 信任链复用：`claim_status` 只认 confirmed verdict，注入的理由天然是人写或人签过名的——闸已在，不新建。
- 死因的判别价值：② 里旧 claim 品味死 + 新 claim 相似 ≠ 硬矛盾（降误报）；① 里 `not_worth` 判例显式标出。

---

## 3. 刻意不做（负清单）

- 不动候选枚举 / 粗筛逻辑。
- 不做复活条件的确定性监控引擎（L4 后议）。
- 不做死因的 legacy 批量回填——历史保持未分类；将来若补，是显式新事件，不是改历史。
- `narrowed_from` 边由语料图投影读 verdict payload 产出（纯读、零新存储），不新增 LINK 事件类型。
- spec 停模型高度：字段命名细节、UI 形态、投影函数签名留实现时 test-driven 定。

---

## 4. 验收要点（就绪闸，非正确性证书）

- 新 kill verdict 无死因 → 拒绝；`circumstantial` 无复活条件 → 拒绝；survive 带死因 → 拒绝。
- legacy 事件回放不炸；投影对缺失字段给「未分类」。
- ②① 的 prompt 含判例四元组（测试断言注入内容与 300 字截断）。
- `boundary` + successor → 语料图出现 `narrowed_from` 边。
- 全测试套件过；**本刀合并后 L3 canary 必跑**（prompt 变了，正是 canary 的触发纪律第一条）。
