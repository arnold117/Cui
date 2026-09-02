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
- **S1.5 wedge 真流验收(真库 HTTP)**:landscape(4 存活 claim + 3 confirmed facts)→ corpus search("reinforcement learning" 3 篇)→ gap propose(自动检索记录)→ confirm confirmed ✓。全量 pytest **543 passed / 15 skipped**;gate 3/3;vitest 69 + build 绿。
- **语义注记**:gap"可被反证挑战"由既有机制承载——把 confirmed gap 转写为 claim 走 review 流(不新增 round-less challenge);方向结晶自动化与 /api/v3 重排留第二刀。
- 下一步:第二刀(/api/v3 契约化重排 + 语料检索正式化 + exporters/related-work·outline 接线)。

## 3. 验收线(第一刀)

真流 e2e:工作区现状读回 → gap 候选 propose(携带检索记录+反例邀请)→ confirm → 确定性 challenge 同 commit;UI 同一旅程可点通;全量测试绿 + 双 canary 绿 + Playwright 冒烟;README 更新。

## 4. 第二刀预告

方向结晶自动化(文献锚+Lens 历史锚→direction,等第一批判例);/api/v3 契约化重排 + 语料检索端点正式化;exporters/related-work·outline 模板接线(S24);检索默认 active 的正式检索视图。
