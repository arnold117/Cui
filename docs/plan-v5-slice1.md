# Plan: Cui v5 slice1 — review/gap 闭环第一刀(草案 v0,收敛用)

> 依据:spec-v5-merge S19–S21/S23/S24(slice0 全完成后开)。本文件为启动包+任务草案;
> 决策真相仍是 `docs/spec-v5-merge.md`;slice0 执行记录 `docs/plan-v5-slice0.md` §5–§11。
> slice1 是新功能里程碑(slice0 零新功能纪律解除),每一刀照惯例:收敛 → 计划 → 实现 → 审计 → canary。

## 0. 从哪接(slice0 终点资产)

- 语料:163 篇 native materials(active 57 / legacy 103,双语料 workspace `v4-corpus-active`/`-legacy`),检索默认只进 active(slice1 兑现)。
- 可用生命周期:claim → review round(LLM 挑战)→ evidence candidate propose/confirm/correct/reject/withdraw;confirmed contradiction → 同 commit 确定性 challenge;verdict(survive/kill/boundary)+ re-review;direction 人工结晶已可用。
- 待接线(v4 cherry-pick 已归档在 `cui/legacy_archive/`):`search/ranking.py`(CJK+IDF 纯函数)、`exporters/*`(pandoc/bibtex/citation)、`templates.py`(related-work/outline)。
- 里程碑目标(S19):终点 = **现状图景 / gap 清单 / 可行方向**;综述文档只是导出。

## 1. 第一刀范围(S21 方案 1,wedge = 开题 gap 论证 + related-work 可信段)

1. **现状图景**:工作区内,把该处已走通的料(存活 claim + confirmed facts + confirmed gaps)整理成可读的"现状",供 gap 论证引用。第一刀最小形态:读回视图(新投影),不做新事件。
2. **gap 候选生命周期**(新 kinds,仿 evidence 候选):
   - `gap_candidate_proposed`(形状按 S20:覆盖范围声明 + 可复现检索记录(query/来源集/日期) + 反例邀请;generator_kind=user 起步,propose 禁"所以你应该做 Y")
   - confirm/correct/reject(withdraw)复用候选决策流;**confirmed gap → 同 commit 确定性 challenge(可被反证,阵亡喂 Lens——第二刀)**;confirmed gap 进轨迹。
3. **人 confirm 闸**:gap 只有人 confirm 才算数(自动化取证,永不自动化定见)。
4. wedge 演示验收:任意 active 材料集上走通一条真流 = 现状 → gap 候选(带可复现检索记录)→ 人 confirm → 反证 challenge 在场;related-work/outline 导出接线(S24)作为本刀收尾件(用 `legacy_archive/templates.py`)。

## 2. 任务草案(每件 commit,先决策后实现)

- S1.0 决策收敛(本文):现状形态 / gap 形状 / kinds 与生命周期映射 / UI 落点 —— 见 §3 待答问题,答完定稿本文。
- S1.1 kernel:kinds(events 目录开放,S12)新增 gap 事件 + 命令守门 + 投影(现状图景/候选状态机);kernel 纯度契约不动(llm/httpx/api 禁入)。
- S1.2 API:第一刀端点挂现 v2 还是先立 `/api/v3` 契约化重排 —— 待答 Q1;契约测试骨架(slice0 T4 已备)随端点补。
- S1.3 语料检索(active 优先):复用 `legacy_archive/search/ranking.py` 的 IDF 纯函数 + 现有 native material 读面,最小检索端点(按词/锚),供 gap 的"可复现检索记录"引用。
- S1.4 UI:现状图景 + gap 候选面板 + 人 confirm 流(研究宇宙视觉体系内)。
- S1.5 收尾:双 canary + importer 幂等复跑 + Playwright gap 主路径冒烟 + README 状态更新。

## 3. 待答问题(收敛后再定稿/动代码)

- **Q1 入口顺序**:gap 闭环先行(本刀,推荐)vs 先 /api/v3 工程重排?建议:gap 闭环先行(v3 重排作为同里程碑第二刀,避免一刀摊两件大工程)。
- **Q2 现状图景第一刀粒度**:工作区级(推荐,与 claim/evidence 天然同界)vs 库/方向级聚合?
- **Q3 gap 生命周期**:仿 evidence 新 kinds(推荐:独立语义、kernel kinds 盲零改动)vs 借壳现有 candidate kinds?
- **Q4 检索记录落地**:gap 候选的"可复现检索记录"第一刀 = 手工登记的 query+来源集字段(推荐,先不接真检索),语料检索端点(S1.3)随后供其自动填充?

## 4. 验收线(第一刀)

真流 e2e(HTTP):工作区建现状 → 人写 gap 候选(含检索记录+反例邀请)→ confirm → 确定性反证 challenge 同 commit 出现;UI 上同一旅程可点通;全量测试绿 + 双 canary 绿 + Playwright 冒烟;README 更新。第二刀预告:方向结晶自动化(文献锚+Lens 历史锚→direction,等第一批判例)、/api/v3 契约化重排 + 语料检索、exporters 导出插件接线。
