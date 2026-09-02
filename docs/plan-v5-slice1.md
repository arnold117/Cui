# Plan: Cui v5 slice1 — review/gap 闭环第一刀(执行记录版,2026-09-02)

> 依据:spec-v5-merge S19–S21/S23/S24;slice0 执行记录 `docs/plan-v5-slice0.md` §5–§11。
> slice1 是新功能里程碑(slice0 零新功能纪律解除);每一刀照惯例:收敛 → 计划 → 实现 → 审计 → canary。

## 0. 从哪接(slice0 终点资产)

- 语料 163 篇 native materials(active 57 / legacy 103;双语料 workspace),检索默认只进 active。
- 可用:claim → review round(LLM 挑战)→ evidence candidate 决策流;confirmed contradiction → 同 commit 确定性 challenge;verdict + re-review;direction 人工结晶。
- 待接线:`legacy_archive/search/ranking.py`(CJK+IDF)、`exporters/*`、`templates.py`(related-work/outline)。
- 里程碑终点(S19):现状图景 / gap 清单 / 可行方向;文档只是导出。

## 1. 已收敛决策(2026-09-02 定稿)

- **Q1 入口顺序 = gap 闭环先行**;/api/v3 契约化重排与导出插件接线作为同里程碑第二刀(不摊进第一刀)。
- **Q2 现状图景粒度 = 工作区级**(存活 claim + confirmed facts + confirmed gaps 的读回视图;新投影,无新事件)。
- **Q3 gap 生命周期 = 仿 evidence 的独立新 kinds**(`gap_candidate_proposed/confirmed/corrected/rejected`;kernel kinds 盲,零 kernel 改动;语义不借壳)。
- **Q4 检索记录 = 语料检索端点先行**(S1.1),gap 候选 propose 自动携带可复现检索记录(query + 命中的 material 锚 + 日期),不手工登记。

## 2. 任务清单(每件 commit)

- **S1.1 语料检索端点(active 优先)**:只读 GET `/api/v2/corpus/search?q=&group=active|legacy&limit=` —— 复用 `legacy_archive/search/ranking.py` IDF 纯函数 + native material 读面;返回排名结果(material_id/source_locator/title 首行/得分/摘要片段);契约测试(排序确定性、active 过滤、空 query 422、kernel 纯度不受影响:ranking 在 host 层调用)。
- **S1.2 kernel gap kinds**:事件目录 + 命令守门(`propose_gap_candidate`/决策命令)+ 投影(候选状态机、现状图景 readback);payload 形状按 S20(覆盖范围声明 + 可复现检索记录 + 反例邀请;propose 禁"所以你应该做 Y")。
- **S1.3 gap API(先挂 /api/v2 扩展)**:propose/confirm/correct/reject/withdraw + 现状图景读回;confirmed gap → 同 commit 确定性 challenge(generator_kind=system,复用确定性反证模板);契约测试 + 单测。
- **S1.4 UI(研究宇宙体系内)**:现状图景 + gap 候选面板 + 人 confirm 流。
- **S1.5 收尾验收**:wedge 真流 e2e(HTTP + UI 冒烟:现状 → gap 候选(自动检索记录)→ confirm → 反证 challenge 在场);全量 + 双 canary + Playwright + README 更新。

## 3. 执行记录(2026-09-02,第一刀 S1.1–S1.5 完成)

- **S1.1 语料检索** `826cc2c`:GET `/api/v2/corpus/search`(IDF 排序,host 层调 legacy_archive ranking;active 默认;纯 CJK 整短语回退;空白 q 422)+ 7 契约测试;真库冒烟排序符合直觉。
- **S1.2/S1.3 gap 生命周期** `3f3bd35`:新 kinds(gap_candidate_proposed/confirmed/corrected/rejected/withdrawn,payload 强制 S20 形状:覆盖声明+检索记录+反例邀请);命令流镜像 evidence(终态一次性);端点 propose/confirm/correct/reject/withdraw + GET landscape(存活 claim= 非 refuted/not_worth 的最后裁决;confirmed facts 来自 evidence 决策;gaps 全状态)。
- **S1.4 UI** `92a3232`:`LandscapePanel`(现状图景 + gap 台 + 语料检索选取,prop 驱动,读数据并入 desk GET 响应——避免独立拉取打乱既有测试队列);WorkspaceDesk 集成;vitest 69(+3)。
- **S1.5 wedge 真流验收(真库 HTTP)**:landscape(4 存活 claim + 3 confirmed facts)→ corpus search("reinforcement learning" 3 篇)→ gap propose(自动检索记录)→ confirm confirmed ✓。全量 pytest **543 passed / 15 skipped**;gate 3/3;vitest 69 + build 绿;**Playwright 11 passed / 2 skipped(real)含 gap 冒烟**;双 canary 复验全绿;importer 复跑 created=0(155 replay + 1 指纹守卫)。
- **语义注记**:gap"可被反证挑战"由既有机制承载——把 confirmed gap 转写为 claim 走 review 流(不新增 round-less challenge);方向结晶自动化与 /api/v3 重排留第二刀。
- 下一步:第二刀(/api/v3 契约化重排 + 语料检索正式化 + exporters/related-work·outline 接线)。

## 3. 验收线(第一刀)

真流 e2e:工作区现状读回 → gap 候选 propose(携带检索记录+反例邀请)→ confirm → 确定性 challenge 同 commit;UI 同一旅程可点通;全量测试绿 + 双 canary 绿 + Playwright 冒烟;README 更新。

## 4. 第二刀预告

方向结晶自动化(文献锚+Lens 历史锚→direction,等第一批判例);/api/v3 契约化重排 + 语料检索端点正式化;exporters/related-work·outline 模板接线(S24);检索默认 active 的正式检索视图。

## 5. 第二刀设计定稿(2026-09-02 收敛):文献探讨对话面 — wedge demo

> 收敛问答记录见本会话;已决条目不再翻案。目标是把你说的核心流程做成可点的产品旅程。

### 决策(Q1–Q7 已答)
- 文献来源:第一刀只搜**已入厂 active 语料**(离线、可复现、S20 检索记录天然满足);外部实时检索(arXiv/OpenAlex)留后续增强。
- 载体:复用 **claim + review round**;中间对话不入轨迹,**裁决/confirmed gap/挑战事件才入库**(铁律:自动化取证,定见入库,过程是会话)。
- 流程两段式:先"选料+现状梳理"(临时)→ 你固化 claim 开审查轮 → agent 用选中文献对抗发问 → 裁决 → gap 候选(人 confirm,保持人署名)→ related-work 段草稿(导出形式,不入事件库)。
- 带料交互:agent 检 top-6(每篇一行理由)→ 你勾 3–5 篇进入引用。
- 挑战引用文献:**复用 challenge_created 的 basis_refs 存材料 locator**(引用即依据;文本内嵌引句),新 prompt 版本 `slice1b-literature-challenge-v1`,不新增事件类型。
- 入口:工作区专属模式页「文献探讨」(仿 forge 布局,从现状图景与 gap 区进入),产物(gap/裁决/草稿)回工作区可见。
- gap 候选仍由**人提交**(agent 只起草候选字段、预填表单供人修改后 propose,保持 user authorship;S6)。
- 草稿:related-work 段,复用 `legacy_archive/templates.py` RELATED_WORK_PROMPT,UI 卡片可重生成/复制/下载;不入事件(导出=渲染,S19)。

### 旅程验收(demo 一路点通)
① 开问题+一句话方向 → ② agent 检索 top-6+理由 → ③ 勾 3–5 篇 → ④ 现状梳理(覆盖/未覆盖) → ⑤ 固化 claim → 审查轮 → agent 引用文献逐条发难 → ⑥ 回答→裁决 → ⑦ agent 起草 gap 候选(检索记录自动带)→ 人 confirm ≥1 → ⑧ 生成 related-work 草稿。

### 执行记录(2026-09-02,L1–L3 完成)

- **L1 后端** `0739e07`:文献挑战 prompt `slice1b-literature-challenge-v1` + 服务 `generate_literature_challenge`(basis_refs=材料 locator,校验同区/parsed evidence)+ `POST /review-rounds/{rid}/literature-challenges`;瞬态端点:landscape-summary / gap-draft(JSON 形状校验)/ related-work-draft(复用 RELATED_WORK_PROMPT,兜底 prompt);`793c1ce`:agent literature-search(top-k 由 LLM 挑、逐篇理由、locator 白名单过滤;slice7 检索抽成 `ranked_corpus_hits` 复用)。
- **L2 前端** `9c3df01`:DialogueDesk 模式页(五步旅程:找文献→梳理现状→固化 claim 进审查轮+文献发难→gap 起草(人署名提交确认)→related-work 草稿卡片(复制/下载));`/workspaces/:id/dialogue` 路由 + LandscapePanel 入口;会话中间态 sessionStorage(不入库);vitest +1 全旅程测试。
- **L3 真库 wedge 旅程验收(真 LLM)**:检索(2 篇)→ 现状梳理 → claim → 审查轮挑战 → 文献挑战 201(basis=[arxiv:2311.09277, arxiv:2504.12501])→ gap 起草/confirm → related-work 草稿(含 [locator] 引用)全通。
- 数字:后端 **551 passed / 15 skipped**、gate 3/3、vitest **70**、build 绿、Playwright **11 passed / 2 skipped**、双 canary 复验绿。

### 任务草案
- L1 后端:prompt `slice1b-literature-challenge-v1`(引文献发难)+ 服务方法 `generate_literature_challenge`(basis=material locators)+ 端点;会话瞬态端点(现状梳理/相关草稿/agent gap 草稿)host 层直调 llm;契约测试(纯组装可测,LLM 注入 fake)。
- L2 前端:文献探讨模式页(两段式状态机、勾选、挑战/裁决复用现有组件、草稿卡片);vitest + Playwright 旅程冒烟。
- L3 验收:全量 + 双 canary + 真库 wedge 旅程走一遍 + README/记忆。
