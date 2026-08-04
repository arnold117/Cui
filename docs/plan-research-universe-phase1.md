# Implementation Plan：Research Universe Phase 1 Native Rebuild

> 状态：Slice 0–1 已完成并验证；Slice 2 待实施（2026-08-04）。
>
> 产品权威：[`prd-research-universe.md`](prd-research-universe.md) · [`spec-research-universe-mvp.md`](spec-research-universe-mvp.md) · [`spec-research-universe-ux.md`](spec-research-universe-ux.md) · [`spec-research-universe-visual.md`](spec-research-universe-visual.md)。
>
> 本文定义实施顺序、native/legacy 硬墙、事件／投影／API／前端边界和每片验收。它不是旧 Artifact 架构的迁移计划；新宇宙从空开始，旧数据只读 archive。

---

## 0. 实施目标

Phase 1 完成时，真实应用必须跑通：

```text
密封 PARK 捕获
→ 用户放行到问题 Workspace
→ 自由探索并提交自写 Claim
→ Review Round / Challenge / Answer / 用户 Verdict
→ 手动材料 / Evidence Candidate / 用户确认
→ 用户亲写 Workspace Conclusion
→ 用户确认 Direction 影响
→ Universe Home 在真实上下文中呈现结晶与待回应事实
```

第一条独立可演示 tracer 不是 Direction／Workspace CRUD，而是：

```text
问题 Workspace
→ 自写 Claim
→ 绑定不可变问题／Claim 快照的 Review Round
→ 一条 pending Challenge
→ Workspace 研究边缘与 Universe Home 上下文读回同一事实
```

## 1. 总体架构

### 1.1 Native bounded context

新增独立代码边界：

```text
backend/anneal/research_universe/
  domain/          # typed events, value objects, invariants, pure projections
  application/     # semantic commands and queries
  store/           # native event store, repositories, SQLAlchemy schema
  api/             # /api/v2 DTOs and routers

backend/anneal/legacy_archive/
  application/     # read-only facade over legacy repository/event store
  api/             # read-only archive routes
```

禁止：

- 将 Workspace 实现成 `Artifact.kind`；
- 为旧 Artifact 添加 `workspace_id`；
- 为新 Workspace 添加兼容性 `artifact_id`；
- 将旧 Project／Conversation 改名为 Direction／Workspace；
- 新 projection 查询旧 Claim／Artifact／Material；
- 新 UI 调用 `/api/v1` mutation。

### 1.2 数据切换

旧表原样保留：

```text
libraries / projects / conversations / claims / artifacts / materials /
legacy events / lens_feed_entries / legacy joins
```

新表以明确 native 前缀／schema 创建：

```text
research_universes
ru_streams
ru_events
```

后续如读取性能证明需要，再由独立 migration 增加 projection 表；第一 tracer 优先使用纯投影，避免预建空 read-model 基础设施。

### 1.3 API 切断

```text
/api/v2/universes/...
/api/v2/legacy-archive/...
```

- `/api/v2/universes` 只接受 native IDs；
- Phase 1 archive facade 只允许 list/get/trajectory/export；删除仍按既有隐私契约处理，不在未定契约上新开 endpoint；
- 发布 native root 时，公开应用不再挂载 `/api/v1` mutation router；如需跑 legacy regression，必须由独立 test-only app factory 显式挂载，不能成为生产兼容 API；
- 不做 API alias、自动 ID 翻译或混合 list。

### 1.4 Phase 1 身份与 Library 范围

Phase 1 是**单用户、单选定 Library 的本地应用**，不是多租户授权系统：

- server startup 从持久化配置解析唯一 active Library；首次空库可创建它，但 request 不得传入或覆盖 `library_id`；
- `/universes/active` 由 server-side Library context 解析，一 Library 最多一个未归档 Universe；
- command actor 来自 server-side local principal dependency，不能相信 payload 中的 actor／Library；
- 所有 native refs 仍须校验同 Universe；未来引入多用户前必须另做 principal、ownership 与 authorization 设计，不能把本期 local principal 冒充成完整权限模型。

## 2. Migration 与持久化纪律

### 2.1 Alembic 先行

在任何 native 表落地前：

1. 将 `alembic` 加入 backend runtime/deployment dependency；
2. 创建 `backend/alembic.ini` 与 migration environment；
3. migration 读取 `CUI_DATABASE_URL`，不得读取／修改 `.env`；
4. 建立两个明确 revision：`legacy_baseline` 描述现有 legacy schema，`native_v1` 只创建 native root/stream/event/idempotency 表；
5. **新空数据库**执行 `alembic upgrade head`，由 baseline 创建 legacy schema，再由增量创建 native schema；
6. **已有 pre-Alembic 数据库**先运行只读 schema preflight（表、列、约束和版本指纹完全匹配）再 `alembic stamp legacy_baseline`，随后 `upgrade head`；不匹配时停止，禁止猜测或自动修补；
7. app startup 在 Slice 0 起不再调用 `metadata.create_all()`；legacy regression test app 自建 schema 的逻辑与生产 app factory 物理隔离；
8. 应用启动不自动执行 migration；运维／开发显式运行 `alembic upgrade head`；
9. `native_v1` downgrade 只删除 native 表并保留 legacy 数据；baseline 不作为生产数据回滚手段。

迁移前备份与恢复属于部署 runbook 的硬前置。Slice 0 必须同时覆盖 fresh bootstrap 和 populated legacy cutover，不能只测空库。

### 2.2 Native 表最小结构

```text
research_universes
  id UUID/str PK
  library_id
  model_generation = "research_universe_v1"
  created_at
  archived_at nullable
  UNIQUE(library_id) WHERE archived_at IS NULL

ru_streams
  id PK
  universe_id FK -> research_universes
  aggregate_type
  aggregate_id
  next_sequence
  created_at
  UNIQUE(universe_id, aggregate_type, aggregate_id)

ru_commits
  position BIGINT identity/sequence PK
  id UUID UNIQUE
  universe_id FK -> research_universes
  command_id UNIQUE
  command_fingerprint
  result_payload JSON
  actor_kind
  actor_id nullable
  committed_at

ru_events
  id PK
  universe_id FK -> research_universes
  stream_id FK -> ru_streams
  commit_position FK -> ru_commits.position
  commit_index
  sequence
  event_type
  occurred_at
  payload JSON
  causation_id nullable
  correlation_id nullable
  schema_version
  UNIQUE(stream_id, sequence)
  UNIQUE(commit_position, commit_index)
```

每个聚合只有一个确定地址 `(universe_id, aggregate_type, aggregate_id)`；事件不能自行另造 stream。跨聚合 query/projection 严格按 `(commit_position, commit_index)` replay，`occurred_at` 只作展示时间，不能决定领域顺序。

每个 command 必须携带 client-generated `command_id`。创建 root/stream、锁定已有 stream、校验 expected sequence、写入 `ru_commits`、递增 `next_sequence` 与 append 全部事件必须在同一数据库事务中完成：

- `command_id` 已成功存在且 canonical `command_fingerprint` 相同时，从 `result_payload` 返回原 durable IDs／commit position，不重复执行；
- 同一 `command_id` 但 fingerprint 不同时拒绝；fingerprint 必须由 command type、canonical payload、target aggregate 与 expected sequence 共同生成；
- 聚合创建失败不得留下空 stream 或可寻址 root；
- 禁止复用 legacy `max(seq)+1`。

一个 command 可在同一 commit 中原子写入多个 aggregate stream；必须以稳定排序锁 stream，避免死锁。若当前 slice 不需要跨聚合原子写，则 command 只写一个 aggregate，projection 通过 global commit order 汇合。

### 2.3 Native persistence / app factory 契约

明确分成三个 app factory，不由运行时静默猜测：

- `create_native_app(settings, native_store, library_context, principal)`：生产／开发入口；必须有 `CUI_DATABASE_URL` 且 schema revision = head，否则启动失败并给出明确错误；只挂 `/api/v2` native + read-only archive；
- `create_native_test_app(InMemoryNativeStore, ...)`：测试显式注入，绝不由缺少 DB URL 自动选择；
- `create_legacy_regression_app(...)`：只供现有 `/api/v1` regression tests，显式挂 legacy router，不作为部署入口。

不允许 product app 静默选择内存模式。可另设显式 ephemeral demo app，但 UI 必须有不可忽略的“重启会丢失”提示；Phase 1 默认不实现。

## 3. Native 事件模型

### 3.1 Event envelope

每个 native event 至少包含：

- `universe_id`；
- `aggregate_type` / `aggregate_id` / `stream_id` / `sequence`；
- `commit_position` / `commit_index`；
- `event_type`；
- `actor_kind = user | system`；
- `actor_id`；
- `occurred_at`；
- typed payload；
- `causation_id` / `correlation_id`；
- `schema_version`。

持久化 payload 可为 JSON，但 domain 层必须以 Pydantic discriminated union 校验，不允许 application service 写任意 dict。

### 3.2 首期事件族

#### Universe / Direction

- `universe_created`
- `direction_created`
- `direction_status_declared`
- `direction_proposition_rephrased`
- `workspace_direction_attached`
- `workspace_direction_detached`
- `workspace_crystallization_attached`

#### Workspace / Question / Notes

- `workspace_created`（含初始问题快照）
- `workspace_question_reframed`
- `exploration_note_saved`
- `exploration_anchor_created`
- `workspace_paused`
- `workspace_reopened`
- `workspace_concluded`
- `workspace_branched`（successor Workspace refs + reason）
- `workspace_absorbed`（target Workspace ref + reason）

#### PARK / Release

- `park_captured`
- `park_released`（source capture ID + target Workspace + provisional role）
- `claim_forged_from_capture`

#### Claim / Review Round

- `claim_created`
- `claim_text_clarified`（同一 Claim 的新可见版本；旧 snapshot 不变）
- `claim_reformulated`（新 Claim ID + immutable predecessor + lineage type，不覆盖原 Claim）
- `review_round_started`
- `challenge_created`
- `challenge_answered`
- `challenge_deferred`
- `challenge_withdrawn`
- `verdict_confirmed`

#### Material / Evidence

- `material_added`
- `evidence_relation_proposed`
- `evidence_relation_confirmed`
- `evidence_relation_corrected`
- `evidence_relation_rejected`
- `evidence_relation_withdrawn`

### 3.3 Typed event catalogue 闸门

Slice 0 不需要一次实现所有事件，但必须先建立一个 versioned catalogue；任何事件进入某 slice 前，catalogue 和 domain tests 必须先定义其完整 payload。每个 payload 至少明确：

- event 自身 ID、aggregate type/ID、parent/root IDs 与所有被引用 entity/version IDs；
- command actor 之外的 provenance（用户输入、system rule/model、basis refs）；
- immutable snapshot/ref，及该字段是否可空；
- 对应 transition 的前置状态和 replay 后状态；
- schema version 与未来 upcast policy。

首期关键 payload 合约：

| Event | Required semantic payload |
|---|---|
| `workspace_created` | workspace ID、initial question version ID/text、user position=`exploring` |
| `workspace_question_reframed` | old/new question version ID/text、change type、user reason |
| `claim_created` | claim ID、origin Workspace、claim version ID/text、author=`user` |
| `claim_text_clarified` | claim ID、old/new visible version、user declaration=`surface_clarification` |
| `claim_reformulated` | predecessor Claim/version、new Claim/version/text、lineage type、user confirmation |
| `review_round_started` | round ID、Workspace ID、question version/text snapshot、Claim ID/version/text snapshot |
| `challenge_created` | challenge ID、round + claim snapshot ref、attack surface、why it matters、generator kind/version/basis |
| `verdict_confirmed` | round ID、verdict type、user reason；kill cause；`circumstantial` revival condition |
| `material_added` | material ID、immutable excerpt、source locator/minimal metadata、parse status |
| `evidence_relation_proposed` | candidate ID、round + claim snapshot、material anchor snapshot、relation、uncertainty、generator provenance |
| evidence decisions | candidate ID、prior decision state、relation/reason as applicable；不可改写旧 decision |
| `workspace_concluded` | conclusion ID/type/text、basis refs、new user position |
| `workspace_branched` / `workspace_absorbed` | source Workspace、successor/target Workspace refs、user reason、resulting explicit position |
| Direction events | proposition version or explicit unnamed state、declared status、Workspace/conclusion refs、user reason |
| PARK events | capture ID + immutable original；release ID、target Workspace、provisional role、source ref |

Direction 的“暂不命名”必须用显式 proposition state 表示，不能用空字符串冒充命题。Event catalogue 是 Slice 1 开始前的 blocking artifact；application service 不得自行发明 payload。

### 3.4 Snapshot 规则

以下绑定时必须复制不可变文本，而非仅保存可编辑实体 ID：

- Review Round：Workspace 问题版本 ID + 问题文本；Claim 版本 ID + Claim 文本；
- Challenge／Answer／Verdict：Review Round ID + Claim snapshot ref；
- Evidence Candidate／Decision：材料摘录快照、来源 locator／最小元数据、Claim snapshot、Review Round ID；
- Direction rephrase：旧命题版本、新命题、用户理由、可选 Workspace conclusion event ref；
- PARK release：原 capture ID，原件永不移动／改写。

## 4. Projection 边界

后端拥有全部领域投影，React 不 replay 任意 event 或重实现状态规则。

### 4.1 最小 projections

- `UniverseHomeProjection`
  - Directions 与命题／声明状态；
  - 未归属 Workspaces；
  - 各上下文中的 pending facts；
  - 最近用户确认结晶。
- `WorkspaceProjection`
  - 当前问题脊柱和版本来路；
  - 用户位置；
  - exploration note/anchors；
  - Claims / Review Rounds；
  - materials；
  - research edge；
  - PARK release refs。
- `ReviewRoundProjection`
  - 问题／Claim 快照；
  - challenges 及生命周期；
  - answers；
  - evidence candidates／confirmed relations；
  - verdict ledger。
- `DirectionProjection`
  - 当前命题／状态；
  - associated Workspaces；
  - crystallizations；
  - contextual pending facts。
- `LegacyArchiveProjection`
  - legacy list/detail/trajectory，只读。

### 4.2 Pending Fact 最小生命周期

#### Challenge

```text
pending
  answer → pending（只记录答辩）
  defer(reason/condition) → deferred
  withdraw(reason) → withdrawn
  review-round verdict → resolved_by_verdict
```

#### Evidence candidate

```text
pending
  confirm → confirmed
  correct → corrected
  reject(reason optional) → rejected
  withdraw(reason optional) → withdrawn
```

旧 decision 永远不可重新打开或改写；只能创建新的 candidate／取证轮次。

#### Workspace pause

仅由用户显式动作产生；不会因时间／无活动自动出现或解除。

任何对象都不允许 `read=true` 作为退出默认入口的依据。

## 5. API 设计

### 5.1 Command endpoints

使用明确语义 command，禁止 generic PATCH：

```text
POST /api/v2/universes
POST /api/v2/universes/{id}/directions
POST /api/v2/universes/{id}/start-from-direction
POST /api/v2/directions/{id}/status-declarations
POST /api/v2/directions/{id}/rephrasings
POST /api/v2/universes/{id}/workspaces
POST /api/v2/workspaces/{id}/question-reframes
POST /api/v2/workspaces/{id}/pause
POST /api/v2/workspaces/{id}/reopen
POST /api/v2/workspaces/{id}/branch
POST /api/v2/workspaces/{id}/absorb
POST /api/v2/workspaces/{id}/direction-links
POST /api/v2/workspace-direction-links/{id}/detach
POST /api/v2/workspaces/{id}/notes
POST /api/v2/workspaces/{id}/anchors
POST /api/v2/workspaces/{id}/claims
POST /api/v2/claims/{id}/clarifications
POST /api/v2/claims/{id}/reformulations
POST /api/v2/claims/{id}/review-rounds
POST /api/v2/review-rounds/{id}/challenges
POST /api/v2/challenges/{id}/answers
POST /api/v2/challenges/{id}/defer
POST /api/v2/challenges/{id}/withdraw
POST /api/v2/review-rounds/{id}/verdicts
POST /api/v2/workspaces/{id}/materials
POST /api/v2/review-rounds/{id}/evidence-candidates
POST /api/v2/evidence-candidates/{id}/confirm
POST /api/v2/evidence-candidates/{id}/correct
POST /api/v2/evidence-candidates/{id}/reject
POST /api/v2/evidence-candidates/{id}/withdraw
POST /api/v2/workspaces/{id}/conclusions
POST /api/v2/directions/{id}/crystallizations
POST /api/v2/universes/{id}/park-captures
POST /api/v2/park-captures/{id}/release
```

每个 command request 都含 `command_id` 和所涉及 aggregate 的 `expected_sequence`；创建 command 使用“尚不存在”预期。`start-from-direction` 是 Start Station 的复合语义命令，必须在一个 commit 中原子创建 Direction、首个 question Workspace 与 attachment；任何一步失败都不能留下空 Direction。每个 command：

- 从 server-side context 取得 actor／Library；
- 校验所有 refs 同 Universe；
- 校验 transition 与 actor 可作该语义动作；
- 在一个 commit 中 append typed event(s)；
- 返回 durable command/event IDs、commit position／sequence + 受影响 projection fragment。

### 5.2 Query endpoints

```text
GET /api/v2/universes/active
GET /api/v2/universes/{id}/home
GET /api/v2/workspaces/{id}
GET /api/v2/review-rounds/{id}
GET /api/v2/directions/{id}
GET /api/v2/legacy-archive
GET /api/v2/legacy-archive/artifacts/{id}
GET /api/v2/legacy-archive/artifacts/{id}/trajectory
```

## 6. 前端生产边界

```text
frontend/src/features/research-universe/
  api/
  types/
  shell/UniverseShell
  screens/StartStation
  screens/UniverseHome
  screens/WorkspaceDesk
  surfaces/ExplorationSurface
  surfaces/ClaimForgeSurface
  surfaces/ReviewRoundSurface
  surfaces/EvidenceSurface
  surfaces/CrystallizationSurface
  surfaces/DirectionViewport

frontend/src/features/legacy-archive/
  LegacyArchiveList
  LegacyArtifactReadback
```

生产前端在 Slice 0 完成物理切断：

- 引入显式 router 与 direct-navigation fallback；`/`、Universe／Workspace routes 只加载 native feature，`/archive` 只加载 read-only archive feature；
- 原 `App.tsx` 不再 import／驱动 Sidebar、PARK、Grill、DOC、graph 或 legacy mutation client；旧交互组件可留在源码到 Phase 1 末，但不进入 production root bundle；
- native 与 archive 使用独立 feature-local API/type clients；archive client 无 mutation method；
- 安装并配置 Vitest + Testing Library + Playwright，Slice 0 即验证 `/` 和直接访问 `/archive`，不把测试基建推迟到后续 slice。

状态分层：

- URL/location：Universe／Direction／Workspace／Claim／Review Round；
- 后端 authoritative projection；
- pending command/loading/error；
- 短暂视觉确认（淬色）；
- 不在单一 App component 累积全领域状态。

生产 CSS：

- 从 visual spec 建 tokens 与 layout primitives；
- 不复制 prototype inline CSS；
- 原型 guide、硬编码假数据和线性 stage 全部丢弃；
- 前端加入 Vitest + Testing Library；关键旅程加入 Playwright（沿用项目已验证的浏览器走查纪律）。

## 7. 实施切片

### Slice 0 — Alembic、native skeleton、cutover hard wall

**交付：**

- Alembic baseline + native tables migration；
- NativeEventStore（InMemory test adapter + Postgres）；
- typed event envelope；
- router + native/archive API client hard split；
- Vitest、Testing Library、Playwright harness；
- versioned typed event catalogue（至少 Slice 1 所需 events 已具完整 schema/tests）；
- active Universe provision（server-selected Library 一 active universe，storage 层允许未来多个）；
- normal root 进入新 Universe shell／Start Station；
- `/archive` 只读入口；
- native mode 无 DB fail closed。

**验收：**

- fresh DB 从零 `upgrade head` 成功，`native_v1` downgrade 只移除 native 表；
- populated pre-Alembic legacy fixture 通过 preflight → stamp baseline → upgrade，legacy rows／constraints 完全不变；schema drift fixture 必须 fail closed；
- native append sequence 并发安全，global commit position 可确定重放，重复 `command_id` 不产生重复事实；
- native/legacy ID 双向拒绝；
- production app 不挂 `/api/v1`，archive facade/client 均无 write path；
- `/` 与直接访问 `/archive` 都可刷新进入正确 surface，production bundle 不 import legacy mutation client；
- native app 无 DB 或 revision 非 head 时 fail closed；仅显式 test app 可注入内存 store。

### Slice 1 — First Fact tracer / narrow live challenge port ✅

> **完成状态（2026-08-04）**：已在 native event store、`/api/v2` 与生产前端上贯通。后端 full suite `793 passed`；Alembic 创建的真实 PostgreSQL Slice 1 contract `4 passed`；前端 Vitest `23 passed`、build 通过、mock Playwright `5 passed`；另以真实 PostgreSQL + `deepseek-v4-flash` 跑通未 mock 的 Browser → Vite → FastAPI → LLM → Review Round 全栈旅程 `1 passed`（5.3s）。中英文 live challenge 均返回结构化攻击面、意义、自检方法与 provenance。Review 在 Slice 1 明示 pending，并提供返回 Workspace／Universe 的合法出口；Answer／Verdict 仍按计划留在 Slice 3。

**交付：**

```text
Start Station
→ Workspace(question)
→ exploration note/anchor
→ self-authored Claim
→ Review Round snapshots
→ narrow LLM-generated pending Challenge
→ Workspace + Universe contextual readback
```

Direction 可选；从 Direction 开始时，Start Station 必须调用 `start-from-direction`，原子创建 Direction、首个 Workspace 与关联并直接进入 Workspace，不得停在空 Direction。

Challenge port 在本片只接受 immutable question/Claim snapshots，输出必须包含具体 attack surface、why it matters 与通用自检方法，并记录 prompt/model/basis/uncertainty provenance。禁止用静态“请补充细节”占位挑战冒充 Grill；更完整的多 challenge／取证生成仍留在 Slice 6。

**验收：**

- Claim 不可由系统生成／预填；
- Review Round 回放固定当时问题与 Claim 文本；
- challenge 具有可指出的攻击面及方法意义，且通过中英文真模型 canary；
- Answer 不解决 challenge；
- pending fact 在 Workspace 与 Universe 同源显示；
- frontend 不自行推导领域状态。

### Slice 2 — Sealed PARK / Release / Forge provenance

**交付：**

- sealed `park_captured`；
- server-side context firewall；
- explicit release roles；
- Workspace release ref；
- `claim_forged_from_capture`；
- PARK→Workspace→Forge UI。

**验收：**

- 未放行捕获不出现在 prompt/search/projection/Lens；
- release 不移动／改写原件；
- Forge 只问不给；
- 用户可跳过 Forge 提交已成形自写 Claim。

### Slice 3 — Review lifecycle / Human verdict

**交付：**

- challenge answer/defer/withdraw；
- user verdict；
- death cause / revival condition；
- re-review creates new round；
- boundary lineage hook，不自动生成 successor。

**验收：**

- 无 auto-verdict；
- survived 明示仅本轮站住；
- pending challenge 生命周期符合 §4.2；
- 历史 round/verdict 永不覆盖。

### Slice 4 — Manual material / Evidence gate

**交付：**

- manual material + immutable source anchor；
- candidate supports/contradicts/silent/cannot_assess；
- user confirm/correct/reject/withdraw；
- confirmed contradiction deterministic pending challenge；
- 并列 Evidence Surface。

**验收：**

- parse failure 不等于 silent；
- candidate 不进入 confirmed facts；
- confirmed contradiction 不自动改变 verdict；
- rejection reason 可选且可回放。

### Slice 5 — Workspace crystallization / Direction impact

**交付：**

- pause/reopen/branch/absorb；
- user-authored conclusion + type；
- Direction attachment/crystallization/rephrase；
- Universe home readback；
- contextual facts remain visible。

**验收：**

- pending facts 不阻塞 conclusion；
- direction 不自动更新；
- rephrase 保留旧命题、conclusion ref、用户理由；
- 未归属 Workspace 是合法状态；
- branch/absorb 只能由用户声明，保留 source、successor/target 与理由，不自动推断工作区关系。

### Slice 6 — Expanded LLM evidence candidates / Live validation

**交付：**

- 扩展 Slice 1 narrow challenge port 至多 challenge 与更完整生成策略；
- generated candidate provenance；
- evidence candidate generation；
- 双语 live canary 扩展到挑战与取证。

**验收：**

- 真模型行为验证，不只 prompt 单测；
- prompt／model／basis／uncertainty 可追溯；
- 绝无 auto-verdict／auto-direction／auto-claim；
- legacy Lens data 不进入 native prompts。

## 8. 测试策略

### Legacy regression

现有 acceptance/API/service/projection tests 保持原样并改由 `create_legacy_regression_app` 驱动，作为历史行为回归；不改写成 native 语义，也不据此把 `/api/v1` 带回 production app。Archive facade 另测其只读投影契约。

### Native tests

每片必须有：

- pure domain event/projection tests；
- InMemory adapter contract；
- Postgres integration contract；
- API integration；
- frontend component/state tests；
- Slice 级 Playwright journey。

硬性测试：

- fresh bootstrap + populated legacy preflight/stamp/upgrade + native-only downgrade；
- legacy row/constraint preservation 与 schema drift fail-closed；
- fresh universe isolation；
- archive read-only，production app 不挂 v1 mutation；
- PARK context firewall；
- immutable review/evidence snapshots；
- cross-universe ref rejection；
- pending fact lifecycle（含 evidence withdrawal 与“新 candidate 才可重开”）；
- command idempotency、expected-sequence conflict、atomic aggregate creation；
- deterministic global projection replay 与 concurrent stream append ordering；
- no auto-verdict；
- conclusion/direction provenance；
- native persistence/revision fail-closed；
- frontend direct navigation、native/archive client isolation 与 bundle import boundary；
- visual acceptance：研究动作无通用 modal／对象主侧栏，状态不只靠颜色，中英文排印与 reduced motion 合格。

## 9. 退休计划

### Slice 0 后

- production root 已物理切断 legacy `App.tsx`／Sidebar imports，只挂 native routes；
- legacy UI 仅从 `/archive` 的独立 read-only feature 可达；
- `/api/v1` mutation router 仅存在于 legacy regression test app，不随产品部署。

### Phase 1 完成后删除／退役

- `Sidebar.tsx` / `SidebarItem.tsx`；
- `ParkView.tsx`；
- `CorpusGraphView.tsx` 主入口；
- `DocView.tsx` / `VersionsView.tsx` 主入口；
- `useGrillFlow` 的 auto-verdict、Lens、taste 流；
- Promote-to-DOC 控件；
- production app 中的 `/api/v1` mutation client；
- throwaway `ResearchUniversePrototype.tsx`（在 visual decisions 已生产化后删除）。

`TrajectoryView`／`EventCard` 可作为 legacy archive reader 暂留，不得接 native events。

## 10. 每片完成纪律

1. 先测试领域语义，再写服务／API／UI；
2. prompt 改动必须真模型 live 验证；
3. 每片结束运行 backend full suite、native Postgres contract、frontend build/tests、浏览器 journey；
4. 不将后续片的空架构夹带进当前片；
5. 每片都必须可演示用户价值，不以表数量或 endpoint 数量验收；
6. 发现必须跨 native/legacy 胶接时，停止并重新审架构，不加兼容字段。
