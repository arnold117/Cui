# Spec: Trajectory Spine — 统一拷问引擎，护城河第一刀

> 状态：草案 v0.1（2026-06-14，grill 收敛产出）
> 原始项目：LitScribe（已 archive）→ 迁移至 淬·Anneal
> 这是**纯地基**第一刀，第一个里程碑刻意"看不见"——不新增可见功能，只统一动词。

---

## 0. 一句话

把 **TRAJECTORY（打斗全记录）立成脊柱对象**，让现有的"综述"和"想法"都重构成往同一条 trajectory 写。先统一动词，再谈别的。

---

## 1. 为什么是这一刀（依赖顺序，不是偏好）

1. 护城河（学习制 Lens）要吃 trajectory → trajectory 必须**先存在、且格式统一**。
2. "综述 / 想法割裂"的根因 = 两套动词、各写各的库 → 钉统一 trajectory **同时止血**。
3. PARK、Project 容器、Lens 全挂在 trajectory 这条脊柱上 → 它是依赖图的**根**。

排除的错误起点：
- ❌ 不从 UI 开始（地基没钉死先画界面 = 往错骨架贴皮）。
- ❌ 不从 Lens/学习制开始（它吃 trajectory，而今天一条都没有 = 造没水的池子）。

---

## 2. 已决定（grill 中钉死，不再翻案）

### 2.1 产品定位 / 护城河
- 淬·Anneal **不是**综述生成器，**不是**项目管理器。它是一个**学会并复用「你这个特定研究者怎么提炼文献、怎么辩护 claim」、并让这套程序在你跳的任何领域间可移植**的系统。
- 综述、想法只是这套程序被**执行和捕获**的两个**表面**。
- 护城河 = **学习制 Lens**，吃 **grilled trajectory**，跨 Project 穿透"你这个大脑"。
- 别人抄不走的不是幸存结论（公共知识），是**阵亡想法**（用你的失败史训练出的私有资产）。

### 2.2 三区模型
```
PARK 灵感停车场 ──── 快速捕获 · 隔离 · 不喂 Lens · 不算任何进度
   │   「回头真要弄」→ 从零开始拷问，无偷渡（停过车 ≠ 拿到学分）
   ▼
GRILL 拷问场（强度可调）──── 全程录像 → TRAJECTORY ──→ 喂 Lens（护城河）
   │   幸存
   ▼
DOC 干净产出 ──── 只留 verified
```
- **PARK = 密封隔离区**。唯一通往护城河的路是穿过拷问场。PARK 作为交互模式职责极纯：放松态灵感来了，零摩擦、帮你快速完整记下来，不挑战/不生成/不评判。捕获工具，非思考工具。
- **GRILL = 闸门 + 录像机**。强度可调（放松式：先想象回头挨打 ↔ 毒打式：上来前置）。旋钮控制的是**闸门时机**，不是有没有闸门；放松 ≠ 跳过，= 拷问延迟（欠 verification debt，债总要还）。
- **TRAJECTORY** 全程录像，含**幸存者 + 阵亡者**（被秒杀的蠢想法**永久保留**，是矿不是垃圾）。
- **DOC** 只留 verified 幸存者。

### 2.3 红线复述（重新理解）
- 「绝不 auto」「❌输入即生成」的真意 = **不许未经拷问的东西冒充已验证**，而非"不许 AI 自动提炼"。
- 因此：**学习制 / 自动辅助提炼是允许的**，只要 grill 是闸门、没有东西能绕过它进入"已验证"。

### 2.4 不是"综述工具"，是"写作引擎"（2026-06-14 拓维）
- **本质**：一个「朝某目标、在约束下、基于你收集并拷问过的材料去写 X」的引擎。综述只是其中一个 `kind`。
- **写作产物（Artifact）的 kind 是开放集**，都跑同一引擎：
  - `idea`：为某 claim **辩护**的拷问。
  - `review`：为某 claim **取证** + 综合的小综述（一个 project 下 N 个，每个覆盖一类）。
  - `paper`：从**实验数据**写论文（gap = "你还缺哪些数据"）。
  - `revision`：在**约束**下改写（"投某刊砍到 4000 字 / 套该刊格式"）。
- 统一动词：所有 kind 都写进**同一条事件流**，只是事件组合不同。割裂靠**重构成同一引擎**消失，**不搭桥**。
- **材料（Material）也拓维**：从"只有 paper" → `paper | dataset | result | draft | figure …`。引用保真护城河顺势扩成 **data provenance**（数据也要可溯源）。
- **纪律（关键）**：**泛化抽象，不泛化实现**。schema 现在就设成通用（kind/材料类型无关/约束感知），但第一刀只建 `idea`+`review`、material 只认 `paper`、不做约束事件。`paper`/`revision` 在 schema 里有槽位、不实现 → 将来插入**不改 schema**（避免"先做 review 专用、后来推倒重来"那种屎山）。

### 2.5 结构层（2026-06-14 重定，三层 + 顶层边界）
- **Library / 内容库（vault）= 顶层隔离边界 = 权限边界**。默认 **1 个用户 = 1 个库**，库内全互通。墙是 **opt-in 例外**：用户主动开第二个库才隔离。**Lens 作用域 = 库内**——跨库不学（墙之所以是真墙，正因为它是 Lens 的边界，不只是 UI 过滤）。
  - **墙 = 硬墙 + 单向阀（方向性权限保护，2026-06-14 决）**：认知**快照可 IN（拷进去，冻结副本，垫底新库的 Lens，不从零起步），任何东西不可 OUT**（库内从敏感内容学到的认知永久出不去 = 合规焊死）。快照是副本非活链，转入后两边各自演化、永不回流。
  - 机制（快照导入导出 + 权限管理）→ **deferred，后面再弄**。第一刀只认 `library_id` 字段 + 单库默认。
- **Trajectory = 脊柱本体，无主**。不被任何 Project 拥有，自己存在于某个 Library 内。
- **Project = 轻标签 + 目标锚定的存档视图（乙）**，不是重容器。
  - 身份 = 它的**目标 / 交付物**（"一种新型手持超声探伤仪""一种新型多普勒超声成像方法"）。
  - 成员关系 = **many-to-many**：一条 trajectory 服务几个目标就戴几个标签，**相交免费**（探伤仪 ∩ 多普勒成像 共享换能器/信号处理 trajectory）。
  - **Project ≠ Domain**（领域=paper 池，大致不相交；项目=目标合集，可跨域、可相交）。
  - 防"标签汤"：成员关系由 **Lens 按目标相关性建议、用户审**（Lens 在此第一次干活），非纯手动。
- **Lens** = 库内穿透层对象，不属任何单个 Project。投毒防护：**只吃 grilled trajectory（幸存者 + 阵亡者），永不吃 PARK**。

### 2.6 会话 vs 文档：谁是中心（2026-06-15 已定）
**修正**：原模型把 Artifact（文档）当脊柱、`events[]` 挂在文档下 → 会话沦为文档附属。但真实工作流是反的：**一个 project 下一堆对话 + 一堆想法在游动，交集组合 → 冒出新想法 → 顺带精炼出文件**。中心是**思考（对话+想法）**，文档是**副产品**。

**架构决定：单向数据流，三层分离**
```
Conversation   原始对话（噪声满满：幻觉、争论、重复、修正）
     ↓  提炼（闸门：默认手动确认）
Events[]       结构化事件流 = 唯一真相源（只追加、不可变）
     ↓  投影
Document       干净产出（从 events 投影，无独立状态）
```

**五个已定决策（2026-06-15 grill 收敛）：**

1. **否决对等模型，采用单向投影。** 文档不是独立一等状态，是 event stream 的投影。Conversation 也不是真相源——event stream 才是。对话是产生 event 的原始媒介，文档是消费 event 的渲染终端。没有循环引用，没有双状态冲突。
2. **Event 确认闸门：默认手动确认，bypass 可选但非默认。** 防止 LLM 幻觉直接沉淀进 trajectory。Bypass 产生的 event 统一标 `debt=true`，不进 DOC 投影，直到用户回来确认还债。与 grill bypass 的 debt 逻辑统一。
3. **Conversation 属 library 层，`project_ids: str[]`（m:n）。** 对话不被任何 project 拥有，和 trajectory 的 m:n 哲学一致。**第一刀简化**：实现时当单选用，schema 已留多标签位，将来不改 schema。
4. **文档编辑统一产生 `edit` event，带 `scope: "surface" | "substance"`。** 系统自动判断 scope（LLM），用户确认时可纠正。Lens 只吃 `substance`，不被文气噪声污染。trajectory 完整保留一切，消费端按 scope 过滤。
5. **编辑确认用批量模式。** 编辑时实时暂存，用户点"完成编辑"时一次性 review 所有 pending edit event 的 scope 标记。类似 git staging——改的时候随便改，提交时过一遍。避免逐条确认的高频摩擦，保住人类闸门纪律。

```
Library
  └ Project(目标标签)
Conversation[]   属 library 层，project_ids: str[] (m:n，第一刀当单选)
  ├ Claim[]      想法=漂浮节点(claim 为本)，可跨对话组合
  ├ Material[]   收集的信息
  └ Document[]   event stream 的投影（无独立状态）
```

---

## 3. 第一刀范围（纵向细线，薄薄一层，每区都活）

一根线穿透全脊柱：

> PARK 一个灵感 → 拉进拷问场 → 拷问产出一条 **trajectory（里面故意留一个被打死的想法）** → 幸存者进 DOC → 那条 trajectory 成为 Lens 的**第一口饲料**。

### 3.0 方式：原生重建 + cherry-pick，不 retrofit
- **原生建新模型**（Artifact + events + claim 为本），**不**把新模型套在旧的有状态流水线上、再用链接缝（"到处链接" = 屎山）。
- 旧码里**cherry-pick 可复用零件**：搜索、grounding、contradiction detection、prompt、`_call_llm_json`、chat loop。这些是无状态/纯逻辑件；**旧的状态/持久化结构不搬**，原生重写。
- **spec 停在模型高度**。最易错的底层管道留到实现时 test-driven 决定。

### 3.1 必须落地（原生）
1. **Artifact 脊柱对象 + 事件流**：原生 schema，可序列化、只追加事件。
2. **两个 kind（idea/review）原生跑同一事件流**。
3. **PARK 捕获入口 + 隔离存储**。
4. **PARK→GRILL 转化**：从零开始，无偷渡。
5. **Lens 空表钩子**：MVP 空表 + 投喂写入点（不做学习算法）。

### 3.2 第一刀**不做**（明确推迟）
- ❌ Lens 的学习/蒸馏算法本体。
- ❌ 跨域迁移发现。
- ❌ Project 管理 UI。
- ❌ 强度旋钮的完整 UX 打磨。
- ❌ 任何搭桥转换器。
- ❌ 库的快照导入/导出 + 权限管理。

### 3.3 数据结构 + 事件 草案

七层：`Library → Project(标签) → Artifact(写作产物，脊柱) → events[](轨迹) → projections(投影)`，外加 `Conversation(对话)`、`Claim(独立漂浮节点)`、`Material(材料)`。

```
Library                          # 顶层隔离/权限边界，Lens 作用域
  id · name · created_at

Project                          # 轻标签 + 目标锚定视图，非容器
  id · library_id
  goal          : str

Conversation                     # 属 library 层，不被 project 拥有
  id · library_id
  project_ids   : str[]          # m:n 标签（第一刀当单选用）
  created_at · updated_at

Claim                            # 独立漂浮节点，可跨 Artifact/Conversation 引用
  id · library_id
  body          : str            # claim 内容
  artifact_ids  : str[]          # 被哪些 artifact 引用
  created_at · updated_at
  # status (open/survived/killed/parked) 是投影，从 events 算，不存

Material                         # 收集来的材料；引用/数据皆可溯源
  id · library_id
  kind          : "paper" | "dataset" | "result" | "draft" | "figure" | ...
  provenance    : {...}
  payload       : {...}
  # 第一刀只实现 kind="paper"

Artifact                         # 脊柱对象
  id · library_id
  kind          : "idea" | "review" | "paper" | "revision" | ...
  goal          : str
  constraints   : Constraint[]
  project_ids   : str[]          # many-to-many 标签
  material_ids  : str[]
  title · created_at · updated_at
  events        : Event[]        # 事件流 = 唯一真相

Event                            # 不可变、只追加；默认需用户手动确认
  id · ts
  type          : <见动词表>
  actor         : "user" | "system"
  strictness    : int | null
  debt          : bool           # bypass 产生的 event 统一标 debt=true
  confirmed     : bool           # 用户是否已确认（未确认 = pending）
  target_ref    : str | null
  payload       : {...}

# 派生视图（投影，全从 events 算出，不单独存）
versions[]  = snapshot_projection(events)
doc         = project(events: survive AND NOT debt AND confirmed)
lens_feed   = project(events: grilled AND scope != "surface")
```

**事件动词表**：

| 阶段 | 事件 | 说明 |
|---|---|---|
| 捕获 | `park` | 灵感入隔离区 |
| 收集 | `collect_material` | 挂 paper/dataset/result |
| 分析 | `analyze_material` | 提炼材料 |
| 拷问 | `challenge`→`answer`→`verdict(survive\|kill)` | 苏格拉底闸门 |
| 缺口 | `gap` | 缺数据/无证据/覆盖有洞 |
| 写 | `draft` | 产出文本（默认 debt=true） |
| 约束 | `constrain`→`revise` | 注册约束→改写满足 |
| 取证 | `ground` | 引用/数据 provenance 校验 |
| 落定 | `promote` | survivor → doc |
| 编辑 | `edit` | 用户手改；带 `scope: "surface" \| "substance"`（系统猜+用户纠正）；批量确认（暂存→"完成编辑"时一次性 review scope） |
| 确认 | `confirm` | 用户确认 pending event（闸门动作） |
| 撤回 | `retract` | 用户否决已写入的 event（追加否定，不删历史） |

---

## 4. 已定（原待定，2026-06-15 grill 收敛）

- **Q-D｜verification debt 记账（已定）**：硬拦截。`promote` / `export` / 引用带 `debt=true` 的 claim 时全部硬拦——不还债就不让做，没有"带着 debt 继续"的软选项。日常工作不打扰，出货时拦住。
- **Q-E｜claim 粒度（已定）**：Claim 是独立实体，属 library 层，可被多个 Artifact / Conversation 引用（漂浮节点）。最小 schema：`id · library_id · body · artifact_ids · created_at · updated_at`。`status` 是投影，从 events 算，不存。后续按需加减字段。

---

## 5. 验收（第一刀算"通"的标准）

- [ ] 能 park 一个灵感，它存在隔离区、标 `ungrilled`、查询学习料时查不到它。
- [ ] 能把这条 park 拉进拷问场，经历至少一轮 challenge→answer→verdict。
- [ ] 拷问中产生**至少一个被 kill 的想法**，它**永久留在 trajectory 里**、可回放。
- [ ] 幸存者能 promote 进 DOC，DOC 里**不含**任何 ungrilled / killed 内容。
- [ ] 这条完整 trajectory 能被写入 Lens 投喂点（哪怕下游只是落库、不学习）。
- [ ] 想法流程和综述流程**都**走同一条 trajectory schema（动词统一的证明）。
- [ ] 尝试 promote 一个带 `debt=true` 的 claim，系统硬拦不让过；还清 debt 后才能 promote。

---

## 6. 备注
- 第一个里程碑刻意**零新可见功能**——这是地基重构。
- 任何"顺手加个可见功能"的冲动 → 回看 §3.2。
