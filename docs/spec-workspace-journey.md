# Spec：工作区旅程化（#21）

> 决策来源：`docs/grill-workspace-ia.md`（2026-10-19 Arnold 逐条定）。本 spec 只写「做成什么样」，不写进度；决定改动 ⇒ 升版。
> 版本：v1（2026-10-19，含冷读修订）

## 导读
| 你是 | 先看 |
|---|---|
| Arnold（核对决定） | 待评估汇总 → 每个故事的「用户看到的」 |
| 实现 subagent | 全局约定 → 你领的故事的「各层要做什么」「对接时再定」 |

## 路径、引用与术语
- 路径简写：前端文件在 `frontend/src/features/research-universe/`（含 `screens/`），后端在 `backend/cui/research_universe/`；`App.tsx` 在 `frontend/src/`。`types.ts` 指 research-universe 下那份。
- 「现状（已核）」列 = 2026-10-19 对过代码；`~` = 推荐值，实现时可调但须满足同行写明的约束。
- 文档引用：`journey:N` = `docs/product-journey-v5.md` 第 N 行；`visual:N` = `docs/spec-research-universe-visual.md`；`ux:N` = `docs/spec-research-universe-ux.md`；`10-01 Qn` = GitHub issue #1「2026-10-01 统一设计 grill」第 n 条；「UI 交互规则」= 一页分阶段、每步单主按钮、disabled 视觉诚实、退出-恢复闭环、跨页跳转克制。
- `desk` = `GET /api/v2/workspaces/:id` 返回的工作区投影（类型 `WorkspaceDesk`，与将删除的同名组件无关）。

| 术语 | 含义 |
|---|---|
| 审查轮 / 挑战 / 应答 | review round / challenge / answer；一条 claim 可有多轮，每轮若干挑战 |
| 攻击面 | 一条挑战的一句话标题（`attack_surface`） |
| 取证 / 证据台 | 对材料提取证候选（supports/contradicts/silent/cannot_assess）并由人确认；`EvidenceSurface` |
| 裁决（5 类） | `verdict_type`：survived 存活 / circumstantial 有条件存活 / refuted 已证伪 / not_worth 不值一探 / boundary 划界（标签见 `LandscapePanel.tsx:25-26`） |
| 结论（6 类） | `conclusion_type`：tentative_answer / negated_path / boundary / key_unknown / deferred（须 `revival_condition` 复活条件）/ split_or_turn |
| 位置 | `user_position`：exploring / paused / concluded / branched / absorbed |
| 分支 / 吸收 | 由本问题派生新问题 / 并入另一个问题（`/branch`、`/absorb`） |
| 方向 / 方向地形 | 用户拥有的长期研究命题 / 首页的方向列表 |
| 现状图景 | `desk.landscape`：存活 claim、已确认取证、gap 列表 |
| PARK 放行引用 / 锻 | 从密封捕获层放行进本问题的原件引用 / 从原件写 claim 的右侧面（`ReleaseForge`，路由参数 `refId`） |
| 研究边缘 | 现工作区右栏 `<aside>`，本次删除 |

## 待评估汇总
| # | 故事 | 问题 | 做法 A（推荐） | 做法 B |
|---|---|---|---|---|
| E1 | S1 | 阶段推导放哪（✓ Arnold 10-19 选 A） | 前端纯函数 `journeyStage(desk, draft)`，替换 `contentStage` | 后端投影出 `journey_stage` 字段 |
| ~~E2~~ | S2 | 审查面怎么嵌 | ✓ 直接改 `ReviewRoundDesk` 为嵌入式（整页只剩重定向，不需要双模式） | — |
| E3 | S4 | 应答引用的 id 是否校验（✓ Arnold 10-19 选 A） | 后端 `answer_challenge` 校验 ref ∈ 本工作区 material/anchor | 不校验，前端只给合法选项 |
| E4 | S6 | 「结晶到方向」的原子命令形状（✓ Arnold 10-19 选 A） | 一条新命令：attach（可选新建）+ crystallize，`_append_many` | 前端顺序调三条现有命令 + 失败提示（**已否**：会留孤儿方向） |

## 全局约定（所有故事共用，先定）

**G1 路由**（`frontend/src/App.tsx:19-36` 现为正则匹配）
| 路径 | 渲染 | 现状 | 由谁交付 |
|---|---|---|---|
| `/workspaces/:id` | 旅程页（新 `WorkspaceJourney`，取代 `WorkspaceDesk` + `DialogueDesk` 两页）；保留 `?source-release=` 透传 | 现为 WorkspaceDesk | S1 |
| `/workspaces/:id/forge/:refId` | 旅程页 + 右侧 ReleaseForge；保留 `?source-release=` | 保留，宿主换成旅程页 | S1 |
| `/workspaces/:id/dialogue` | 重定向 → `/workspaces/:id` | 现为 DialogueDesk | S1 |
| `/workspaces/:id/rounds/:rid` | 旅程页 + 右侧审查面打开 `rid` | 新增 | S2 |
| `/review-rounds/:rid` | 先 `GET /review-rounds/:rid` 取 `workspace_id`，再 replace 跳到 `/workspaces/:wid/rounds/:rid`；加载中显示占位，404 走 `NotFound` | 现为 ReviewRoundDesk 整页 | S2（S1 期间保持整页不动） |

路由是自写的 `useNavigation`/`AppRouter`（`router.tsx`），不是 react-router；重定向用其 replace 导航。所有站内跳到审查轮的链接（S2 交付）改用新路径：`UniverseHome.tsx:15`、`GapChallengeComposer.tsx:19`、`LandscapePanel.tsx:23`、`ReleaseForge.tsx:10`、ReReview（`ReviewRoundDesk.tsx:115`）。

**G2 阶段**：6 个阶段，标签改为 `["出发点", "选料", "覆盖与 claim", "对抗", "gap", "结晶"]`（`dialogueDraft.ts:49` 现末步为「收尾」）。阶段由内容推导，**任何阶段都可点开，不锁**（journey:16）；推导结果只决定默认展开哪一张阶段卡、阶段条高亮哪一格。

**G3 存储边界不变**：假设、检索词、候选、选料、覆盖梳理、gap 草稿、related-work 草稿仍只在 localStorage（`cui:dialogue-draft:v2:<wid>`，`dialogueDraft.ts:60`）；claim、审查轮、挑战、应答、取证、gap、结论、方向才入事件。`roundId`、`confirmedGapIds` 不再作为阶段依据（服务端已有）；`claimAck`（用户点过「继续到 gap」）保留为本机标记，只作阶段 4 完成的条件之一。

**G4 页面骨架**：左栏 = 竖排阶段条 + 当前阶段卡 + 已完成阶段折叠行 + 折叠「工具」区；右侧聚焦面 = 审查轮或 forge（visual:96）。<800px 上下堆叠，左栏收成顶部阶段条（`index.css:104` 现有断点）。每张阶段卡只有一个主按钮（feedback_ui_interaction §3）。

**G5 删除/迁移清单**（Arnold 已批）
| 现有 | 去向 |
|---|---|
| 入口条 `DialogueResumeLink.tsx` | 删 |
| 研究边缘 `<aside>`（`WorkspaceDesk.tsx:125`） | 删，由左栏阶段条 + 待回应计数取代 |
| 工作台 claim 表单（`WorkspaceDesk.tsx:29`） | 删，由「覆盖与 claim」阶段取代 |
| 「登记一个 gap 候选」表单（`LandscapePanel.tsx`） | 删，由 gap 阶段取代 |
| 探索稿 + 锚点、带入材料（手动加一份）、PARK 放行引用 | 进「工具」区 |
| 页头「确认这次探索的位置」「分支」「吸收」「方向影响」 | 进结晶阶段 |
| 「回文献探讨继续收尾」「回工作区继续探索」等审查轮页级出口（`ReviewRoundDesk.tsx:42`） | 删（嵌入后不需要回程） |

---

## S1 进工作区就是旅程

**用户看到的**
- 打开一个问题，看到问题标题、左侧竖排 6 个阶段，当前阶段卡展开，已完成的折叠成一行（可「展开修改」）。
- 页头只有「暂停」「重开」两个位置按钮（按位置显示），重开要填理由。
- 「工具」区默认折叠：探索稿（含锚点）、手动加一份材料、PARK 放行引用。
- 在另一台设备打开同一问题：已有 claim 的会落在「对抗」，不会被打回第 1 步。
- 已完成阶段「展开修改」只改本机草稿；已入事件的对象不改写——在「覆盖与 claim」改写 = 再写一条新 claim。

**本故事范围**：新壳 + 路由（G1 中标 S1 的行）+ `journeyStage` + 页头 + 工具区。阶段卡**原样搬入** DialogueDesk 现有步骤内容；旧页头的结晶/分支/吸收/方向影响暂放结晶阶段卡（原样），由 S6 重做；审查轮仍链向整页（S2 再改）；gap 列表与「登记 gap」表单暂留（S5 再改）。`WorkspaceDesk`/`DialogueDesk` 的子组件保留供后续故事复用，只删两个页级组件。

**数据怎么流动**
1. 前端 `GET /api/v2/workspaces/:id`（`api/slice1.py:62-67`，含 `landscape`）→ `WorkspaceDesk` 投影
2. 前端读 localStorage 草稿 `loadDialogueDraft(wid)`
3. `journeyStage(desk, draft)` → 当前阶段 1..6
4. 渲染阶段卡；各阶段卡复用 DialogueDesk 现有步骤内容

**各层要做什么**
| 层 | 做什么 | 现状（已核） |
|---|---|---|
| 路由 | 按 G1 改 `App.tsx` | `App.tsx:19-36` |
| 页面 | 新 `WorkspaceJourney`：合并 `WorkspaceDesk`（页头、工具区、forge 宿主）与 `DialogueDesk`（阶段卡） | 两页分立；DialogueDesk 退出按钮 `:270` 删 |
| 阶段推导 | `journeyStage` 取代 `contentStage`（`dialogueDraft.ts:112-119`） | 现只看草稿 |
| 页头 | exploring 显示「暂停」；paused/concluded 显示「重开」（同现 `WorkspaceDesk.tsx:120`）；branched/absorbed 不显示。重开弹理由输入（必填），暂停理由可选 | `WorkspaceDesk.tsx:53-54` 现发 `user_reason: null`；后端 `ReopenCommand.user_reason: str \| None`（`api/slice5.py:16`）——必填只在前端做 |

`journeyStage` 推导规则（~ 实现时可调，但须满足「服务端事实优先」）：
| 阶段完成条件 | 依据 |
|---|---|
| 1 出发点 | `draft.hypothesesDone \|\| draft.skipHypotheses \|\| desk.claims.length > 0 \|\| desk.materials.length > 0` |
| 2 选料 | `draft.summary \|\| desk.claims.length > 0` |
| 3 覆盖与 claim | `desk.claims.length > 0` |
| 4 对抗 | `draft.claimAck \|\| desk.review_rounds.some(r => r.verdict) \|\| 阶段 5 已完成` |
| 5 gap | `desk.landscape.gaps.some(g => g.status === "confirmed" \|\| g.status === "corrected")` |
| 6 结晶 | `desk.user_position` ∈ {concluded, branched, absorbed}（**不用** `desk.conclusion != null`：重开后 conclusion 仍在投影里，`application.py:333`） |
当前阶段 = 第一个未完成的；全部完成时停在 6（只读回看）。重开后回到 exploring ⇒ 阶段 6 重新变为未完成。

**待评估**：E1。A 前端纯函数：改动集中、可单测；代价是规则在前端，后端不知道阶段。B 后端投影：多端一致；代价是会话草稿（summary、hypothesesDone）后端看不到，推不全。推荐 A。

**最终输出**：`WorkspaceJourney.tsx`、`journeyStage`（+ vitest 覆盖上表每行）、`App.tsx` 路由与重定向；`WorkspaceDesk.tsx`、`DialogueDesk.tsx`、`DialogueResumeLink.tsx` 删除或只剩被复用的子组件。

**对接时再定**：工具区里三块的顺序；阶段条的待回应计数放哪一格（倾向「对抗」）。

---

## S2 对抗阶段：claim 列表 + 右侧审查面

**用户看到的**
- 「对抗」阶段卡列出本问题的所有 claim，每条显示最新一轮：「待回应 n 条」或「已裁决 · 存活/证伪…」。来自 gap 反证的 claim 标「来自 gap」。已裁决的折叠在下面。
- 点一条 → 右侧打开它的审查轮，左栏仍可见（已选文献、覆盖梳理、claim 只读）。
- 次级动作「再写一条 claim」→ 展开「覆盖与 claim」阶段卡。
- 主按钮「继续到 gap」；若还没有任何裁决，按钮旁提示「尚无裁决」（不锁）。
- 从首页待回应、gap 卡片、再次审查进来，都是同一个页面、同一个右侧面。

**数据怎么流动**
1. claim 列表 = `desk.claims` × `desk.review_rounds`（按 `claim_id` 分组，**数组顺序**最后一条为最新轮——`review_rounds[].sequence` 是该轮自身计数，不是全局序；`verdict.verdict_type` 映射标签用术语表的 5 类）。没有任何轮次的 claim（开轮失败时会出现）显示「未开审查轮」+ 次级按钮「开审查轮」（`POST /claims/:id/review-rounds`）
2. 待回应数 = `desk.pending_challenges`（`Challenge[]`，含 `review_round_id`，`types.ts:21`）按 `review_round_id` 计数
3. 「来自 gap」= claim id ∈ `desk.landscape.gaps[].challenges[].claim_id`（`types.ts:119`），**不需改投影**
4. 右侧面 `GET /review-rounds/:rid`（`application.py:383-395`）

**各层要做什么**
| 层 | 做什么 | 现状（已核） |
|---|---|---|
| 路由 | `/workspaces/:id/rounds/:rid` 打开右侧面；`/review-rounds/:rid` 重定向（G1） | 审查轮为整页 |
| 组件 | 审查轮可嵌入（E2）；去掉页级出口 `:42`；ReReview 开新轮后切到新 `rid`，不整页跳 | `ReviewRoundDesk({ roundId })` 已可单独渲染（vitest 即如此用） |
| 文献发难 | 「用所选文献发难」从 DialogueDesk 第 4 步（`:429`）移进右侧面，与「生成更多挑战」（`:36`）并列 | 端点 `POST /review-rounds/:rid/literature-challenges` 收 `material_ids` + `external_refs`（`api/slice9.py:321-325`） |
| 文献发难来源 | 有本地选料 → `external_refs` 照旧；无本地草稿 → 列出本工作区 purpose=evidence 的材料供用户勾选（默认不勾），作 `material_ids` | 端点已收 `material_ids`（V4 ✓） |
| DialogueDesk 第 4 步 | 「去审查轮完整应答与裁决 →」（`:428`）与提示文案删 | |

**待评估**：无（E2 已定：直接改 `ReviewRoundDesk` 为嵌入式）。**交付约束**：嵌入面、新路由、`/review-rounds` 重定向、全部链接改写必须同一个 PR，否则审查轮链接会断。

**最终输出**：对抗阶段卡组件；嵌入式审查面；路由；改所有链向审查轮的地方（G1 列表）；vitest：claim 列表分组与「来自 gap」标签、无裁决提示。

**对接时再定**：已裁决 claim 折叠阈值；ReReview 后旧轮是否在列表里可展开历史（倾向可展开）。

---

## S3 审查面：攻击面优先、分段推进

**用户看到的**
- 审查面顶部是所有挑战的标题列表（攻击面），一次只展开一关；回应完一关自动聚焦下一关。
- 审查面分三段，各一个主按钮：**应答**（逐关回应/暂缓/撤回）→ **取证**（证据台）→ **裁决**（账本 + 五类裁决）。可以随时点段名跳段，不锁。

**数据怎么流动**
1. `GET /review-rounds/:rid` 的 `challenges`、`ledger`、`evidence_candidates`、`confirmed_facts`（`application.py:394`）
2. 段的默认位置：有「仍待回应」挑战（`ledger` 口径：已回应、暂缓、撤回都不算待回应）→ 应答；否则有 pending 取证候选 → 取证；否则 → 裁决。回应完一关自动聚焦下一条「仍待回应」

**各层要做什么**
| 层 | 做什么 | 现状（已核） |
|---|---|---|
| 组件 | `ReviewRoundDesk` 的挑战区从「全部堆叠」（`:35`）改为标题列表 + 单关展开；三段导航 | 挑战逐个 `ChallengePanel`（`:45-83`）全展开 |
| 证据台 | `EvidenceSurface` 放进「取证」段，不再与挑战同屏 | `EvidenceSurface.tsx:92-170` |
| 裁决 | `VerdictForge` 放进「裁决」段 | `:85-106` |

**待评估**：无。

**最终输出**：改版的审查面；vitest：默认段选择规则、一次一关展开。

**对接时再定**：段导航样式；「先理解这一关」「回到探索」两个次级动作在嵌入后的去处（后者可删）。

---

## S4 带进证据台 + 应答时引用

**用户看到的**
- 左栏每篇已选文献旁有「带进证据台」；点了变成「已在证据台」，同一篇不会带两次。
- 证据台的材料里出现这些文献（标「摘要」）。
- 写应答时可以「引用」：从本问题的证据材料和探索稿锚点里选；裁决账本里这些显示为「带入但未确认」。

**数据怎么流动**
1. 前端从草稿 `candidates`（locator、摘要、url）取一篇 → `POST /workspaces/:wid/materials`，`purpose="evidence"`、`parse_status="parsed"`、`content_scope="abstract"`、`source_locator=locator`、`excerpt=摘要`
2. 后端：同一工作区已有相同 `source_locator` 的 evidence 材料 → 返回已有 `material_id`，不追加事件
3. 应答 `POST /challenges/:cid/answers`（`api/slice3.py:44`），`provisional_anchor_refs=[material_id | anchor_id …]`
4. 账本 `brought_unconfirmed` 已按「应答带 refs」统计（`application.py:243`），不需改

**各层要做什么**
| 层 | 做什么 | 现状（已核） |
|---|---|---|
| API | `MaterialCommand` 加 `content_scope: Literal["full","abstract"] = "full"` | `api/slice4.py:12-16` 无此字段 |
| 应用 | `add_material` 透传 `content_scope`；同工作区同 `source_locator`（非空）的 evidence 材料去重：命中则不追加事件，`result` 返回已有 `material_id` 与 `deduplicated: true`、`event_ids: []`；`source_locator` 为空不去重 | `application.py:808-812`；`MaterialAddedPayload.content_scope` 已有（`events.py:145`） |
| 应用 | （E3）`answer_challenge` 校验 refs：每个 ref 必须是本工作区的 material id（evidence 或 reference）或 anchor id，否则 `BoundaryViolation`（HTTP 409） | `application.py:749` 不校验 |
| 投影 | `workspace_projection` 的 materials 加 `content_scope`（前端「摘要」标签要用） | `application.py:329` 未投影此字段 |
| 前端 | 左栏按钮；应答引用选择器（选项来自旅程页已取的 `desk.materials` + `desk.anchors`，由页面传入审查面，不另发请求）；`ChallengePanel` 发 refs | `ReviewRoundDesk.tsx:60` 永远发 `[]` |
| 契约 | `make contract` 重新生成 `api.gen.ts`（10-01 Q9 单一来源） | `Makefile:8-12` |

**待评估**：E3。A 后端校验：坏 id 进不了事件（事件不可撤，这是信任边界）；代价是一处查询。B 不校验：零后端改动；代价是脏 ref 永久留在轨迹里。推荐 A。

**最终输出**：后端字段 + 去重 + 校验 + pytest（去重返回同 id 且不追加事件、非法 ref 被拒）；前端按钮与引用选择器 + vitest。

**对接时再定**：去重时摘要文本不同（重新检索拿到新摘要）是否更新——倾向不更新，保留第一次快照。

---

## S5 gap 阶段：一条路径

**用户看到的**
- gap 阶段卡：可以「让 Cui 起草」，也可以直接手写；改完点「提交并确认这个 gap」（提交即确认，保持现状）。
- 卡上列出本问题已确认的 gap（原「现状图景与 gap」面板的 gap 列表并入这里），每个 gap 可「对这个 gap 发起反证」。
- 没有本地草稿时（换设备），起草按钮不可用，可以手写。

**数据怎么流动**
1. 起草 `POST /workspaces/:wid/dialogue/gap-draft`（不入库）
2. 提交 `POST /gap-candidates` → 立即 `POST /gap-candidates/:id/confirm`（`DialogueDesk.tsx:206-216` 现状）
3. 列表 = `desk.landscape.gaps`

**各层要做什么**
| 层 | 做什么 | 现状（已核） |
|---|---|---|
| 前端 | gap 阶段卡合并 DialogueDesk 第 5 步 + LandscapePanel 的 gap 列表/确认/拒绝/反证；删「登记一个 gap 候选」表单 | 两处各一份 |
| 前端 | 现状计数与存活 claim 列表（LandscapePanel 上半）放进「对抗」或「gap」阶段卡顶部 | ~ 位置实现时定 |

**待评估**：无。

**最终输出**：gap 阶段卡；`LandscapePanel.tsx` 拆分或删除；vitest：手写路径、无草稿时起草不可用。

**对接时再定**：pending 状态的历史 gap（旧登记路径留下的）怎么显示——倾向照常显示确认/拒绝按钮。

---

## S6 结晶阶段：确认位置 → 方向

**用户看到的**
- 「结晶」阶段卡，主按钮「确认这次探索的位置」：选结论类型（6 类）、写结论与理由；选「暂缓」必须写复活条件。
- 确认后同一张卡继续：这次结论去哪——
  - 挂到已有方向（下拉，列出研究宇宙里的方向）
  - 从 gap 新建方向（命题用所选 gap 的文本预填，你改写后签名才生效）
  - 只留在本次探索
- 选「拆分/转向」时，次级动作出现「分支出新问题」「吸收进另一个问题」。
- 结晶后，首页「方向地形」能看到这个方向和这条结晶。

**数据怎么流动**
1. `POST /workspaces/:wid/conclusions`（`ConcludeCommand`，`api/slice5.py:28-43`）→ `conclusion_id`
2. 方向列表：首页投影 `home.directions`（`UniverseHome.tsx:12`）
3. 挂已有 / 新建：**一条新命令**（E4）→ 后端同一次 `_append_many` 写：[可选 `direction_created`] + `workspace_direction_attached` + `workspace_crystallization_attached`
4. 只留本次：不调方向命令
5. 分支/吸收：现有 `POST /workspaces/:wid/branch`、`/absorb`

**各层要做什么**
| 层 | 做什么 | 现状（已核） |
|---|---|---|
| API | 新 `POST /workspaces/:wid/crystallize-into-direction`（放 `api/slice5.py`），body：`conclusion_id`、`direction_id \| null`、`new_proposition \| null`（恰好二选一，否则 422）、`user_reason \| null`（写进 attach 与 crystallization 两个事件）、`command_id`、`expected_sequence`（= 0：写入的都是新聚合——新方向、新 link、新 crystallization）；响应 `CommandResponse`，`result` 含 `direction_id`、`direction_link_id \| null`、`crystallization_id`；`make contract` | 现有三条分立：`/universes/:uid/directions`（`:143`）、`/workspaces/:wid/direction-links`（`:129`）、`/directions/:did/crystallizations`（`:164`） |
| 应用 | **先重构**：把三个方法的校验与 payload 构造抽成纯 builder（不读 store 里「本批次」的新方向——`attach_*` 现在都调 `direction_projection`，看不到同批新建的方向）；新方法用 builder 合成一次 `_append_many`（`:520`）。「已关联」= 该工作区存在指向同一方向、且未 detach 的 link ⇒ 跳过 attach（新逻辑：现 `attach_direction` 不去重）。三个旧命令与端点保留不动 | 三者各自 `_append` |
| 前端 | 结晶阶段卡：搬 `WorkspaceDesk` 的结晶台（`:121`）与方向影响台（`:122`）；补方向下拉与新建 | 方向影响台只在已有 link 时渲染，`attachDirection`/`createDirection`（`api.ts:53,55`）无人调用 |
| 前端 | 「促使我重述方向命题」保留，走 `/directions/:id?rephrase=1` | 现状 |

**待评估**：E4。A 新原子命令：不会留孤儿方向，符合 10-01 Q8 同类做法；代价是一条新命令和 pytest。B 前端顺序调三条：零后端；代价是中途失败留下已建未挂的方向（**Arnold 10-19 已选 A**）。

**最终输出**：后端命令 + pytest（新建/挂已有/已关联跳过/conclusion 不匹配被拒/原子性：任一步失败无事件）；结晶阶段卡 + vitest。

**对接时再定**：新建方向时预填用哪个 gap（多个已确认 gap 时让用户选）；「只留本次」是否需要显式点一下（倾向需要，作为结晶阶段完成的确认）。

---

## S7 导出 related-work

**用户看到的**
- 有已确认 gap 后，左栏底部（或结晶阶段卡里）出现次级动作「导出 related-work 草稿」；生成、复制、下载 .md、重新生成照旧。
- 不再是旅程终点，会话走完文案（`DialogueDesk.tsx:483`）删掉。

**数据怎么流动**：`POST /workspaces/:wid/dialogue/related-work-draft`（不入库，`api/slice9.py`）→ 草稿存 localStorage `relatedWork`。

**各层要做什么**：前端把 DialogueDesk 第 6 步（`:469-486`）搬成次级区块；第 6 步里的 gap 反证入口（`:485-486`）移到 gap 阶段卡（S5 已含）。

**待评估**：无。 **最终输出**：导出区块；vitest 沿用现有草稿测试。 **对接时再定**：放左栏底部还是结晶卡内。

---

## 建议切片（交 map-wide 拆票的输入）
| PR | 内容 | 依赖 | 能否单独合入 |
|---|---|---|---|
| A #24 | 后端：S4（content_scope、去重、E3 校验、投影字段）+ S6 原子命令；pytest；`make contract` | — | 能（无 UI 变化） |
| B #25 | S3 审查面改版（先在现整页上做） | — | 能 |
| C #26 | S1 旅程壳 + 路由 + `journeyStage` + T5 | — | 能（只删两个页级组件，子组件保留） |
| D #27 | S2 嵌入面 + 新路由 + 重定向 + 全部链接改写 + 文献发难移位 | C，最好在 B 后 | 必须整包 |
| E #28 | S5 gap 阶段 | C | 能 |
| F #29 | S7 导出 | **E 之后**（S7 删第 6 步的 gap 反证入口，只有 S5 的 gap 卡接住它；先做会回退 be51bdf/c2c1aeb） | 能 |
| G #30 | S6 前端 | A、C | 能 |
| H #31 | S4 前端 | A、D、B | 能 |
| — | T1–T3 文档 | 任意时点 | 能 |

## 非故事任务

| # | 任务 | 依赖 |
|---|---|---|
| T1 | 改 `docs/spec-research-universe-ux.md` 原则 6（`:26`）为「不给效率/优先级建议，但显示行程位置」；§5.2 研究边缘标为已由左栏取代 | Arnold 已批 |
| T2 | 改 `docs/spec-research-universe-visual.md:172`：旅程阶段是产品形态，但不锁、不显示完成度百分比 | Arnold 已批 |
| T3 | 更新 `docs/product-journey-v5.md` 映射表（`:47-59` 停在五步旧版）为本 spec 的 6 阶段 | S1–S7 |
| T4 | 每个故事的 PR 同时改它碰到的 Playwright 用例，e2e 全绿是合并门槛。涉及（`frontend/e2e/`：dialogue-desk、first-fact、review-lifecycle、evidence-gate、evidence-generation、landscape-gap、crystallization 等）改新路由与 DOM；先列出受影响用例（V1） | S1、S2 |
| T5 | `make canary-journey` 若断言阶段名或步骤，随 G2 同步 | S1 |

## 仍未验证
| # | 内容 | 在哪个故事 |
|---|---|---|
| V1 | Playwright/canary 具体绑了哪些 DOM 与路由 | T4、T5 |
| V4 ✓ | 文献发难端点收 `material_ids`（`api/slice9.py:321-325`）——已核 | S2 |
| ~ | `journeyStage` 推导规则表是推荐，实现时可调 | S1 |
| ~ | 现状计数块放哪张阶段卡 | S5 |

## 不在本次
- 第 1 步 LLM 起草假设（代笔）→ #22
- 选料/梳理入库（会话不入轨迹，journey:41、10-01 Q4 不翻案）
- `_events` 全量读的性能债
