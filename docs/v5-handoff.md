# Handoff: Cui v5 slice0 — 新 session 启动包(2026-09-02)

> **你(新 session)的第一动作:读完本文件 + `docs/plan-v5-slice0.md`,然后按 Arnold 指示执行。**
> 本文件是给"在 Cui/Anneal 工作区开的新 session"的交接;决策真相在 `docs/spec-v5-merge.md`;语料盘点在 `docs/v4-corpus-inventory.md`(importer 用)。

## 1. 你在干什么(一句话)

执行 **Cui v5 slice0**:把 LitScribe 融入 Cui 后的第一个迁移里程碑——rename、legacy 扫除、kernel/SDK 边界固化、v4 语料入厂。**slice0 零新功能**,一切重写归 slice1(review/gap 闭环)。

## 2. 背景(三行)

- 2026-09 两场 grill 收敛:**LitScribe(文献综述引擎,2026-01 起,软著 V1.0 已提交)融入 Cui(淬,思考引擎)升级为 v5**,主名 Cui;产品终点 = 现状图景 / gap 清单 / 可行方向,综述文档只是导出形式;竞争 = 认输取证层、赢判断层。
- 架构:状态机 kernel(事件+围栏+投影+守门,零 LLM/agent/HTTP)+ SDK(python 接口规范真相 + REST thin adapter)+ host 本体 + 插件(静态注册 + disposable 惯例,参考 cordis/DSH 但不做运行时生命周期)。
- 25 条决策(S1–S25)全在 `docs/spec-v5-merge.md`;**已决事项不要翻案**,除非 Arnold 重新 grill。

## 3. 本次 session 建议节奏(worktree 惯例)

- 照 Cui 惯例:主循环(Arnold/agent)收敛 → worktree subagent 实现 → **主循环亲手审计** → cherry-pick 保线性历史 → 测试/canary → push。
- **一次只推一个 task(T0 复查 → T1 基线 → T2 rename → T3 legacy → T4 边界 → T5 importer → T6 cherry-pick → T7 收尾),做完停下汇报,别一口气跑飞。**
- T1 基线是硬前提:环境不绿不许动刀。

## 4. 环境与命令(精确;T2 rename 后终态)

- conda env:**`cui`**(T2 由 `anneal` rename 而来;本节已是终态)。永远不往 base 装。
- 测试:`conda run -n cui pytest`(backend/ 下;基线 ~850 passed/34 skipped;**legacy 摘除后数字下降属预期**)。
- canary(真 key,双绿才算环境好):`python scripts/canary_l3.py`、`python scripts/canary_native_slice6.py`。失败要先区分环境/网络 vs 实现。
- 后端起服:`cd backend && conda run -n cui uvicorn "cui.api.app:create_app" --factory --port 8000`(**是 factory 不是 app:app**);路由:`/api/v2` native(7 组 router)+ `/api/v1` legacy(待摘)。
- PG:`localhost:5432/anneal`,alembic head `sealed_park_v1`。**绝不用测试碰 app 库**——保险 `5c35bf4` 已在 collect 阶段拦(URL 指向 anneal/cui 即 raise);PG contract 测试一律走 `backend/tests/pg_temp_db.py` 临时库。共享 `postgres` 管理库不碰。
- `.env`:CUI_* 变量;**只改 `.env.example`,`.env` sacred**。
- 前端:`frontend/`;vite proxy → 8000;`tsc`/`vitest`/`vite build`;Playwright 走缓存 chromium(记忆:需指 `~/Library/Caches/ms-playwright/chromium-1228/...`)。
- v4 数据(importer 输入,**只读**):`/Users/arnold/Documents/Dev/LitScribe/{cache/litscribe.db, cache/parsed/, data/pdfs/}`;产出落 `~/.cui/`(需自建)。
- git 身份:本 repo 个人开源 → 仓库配置若未设则不要乱 commit,问 Arnold。

## 5. 纪律(铁律 + 记忆 feedback,违反会返工)

- **自动化取证,永不自动化定见**;Lens 只吃 grilled trajectory;survived ≠ 正确性证书;taste 只锚不判。
- slice0 零新功能;prompt 类改动必须真跑验证(单测只证明指令在场)。
- 代码/测试交给 subagent 实现,主循环只做质疑者审计;不要 EnterPlanMode(会丢上下文)。
- legacy 摘除前**先画引用映射表再删**(GrillView/ParkView 可能有 native 残留引用);lens_feed 阑尾摘除;12 张空 legacy 表冻结不 drop。
- importer:三源(DB parsed_docs 149 ∪ cache/parsed 161 ∪ disk pdfs 60)按 arXiv ID/DOI/哈希去重;legacy(生物工艺 ~60 + 老 arXiv ~42)与 active(LLM 群 ~47)分区;幂等验收 + dry-run 人审;PDF 不批量补。

## 6. AgentMemory(按 agent-memory 协议检索/写回)

- `~/Documents/AgentMemory/_projects/anneal/`:`project_v5_merge.md`(本次决策锚)、`project_progress.md`(进度断点,做完 task 要更新)、`project_direction.md`、`project_origin.md`
- `~/Documents/AgentMemory/_projects/lit-scribe/`:v4 前史(双库位置/数据债/copyright)
- 收尾跑 `bash ~/Documents/AgentMemory/scripts/memory-dsh-end.sh`

## 7. 完成判据(T7 退出条件)

全量测试绿 + canary 双绿 + importer 幂等(重跑 0 新增)+ 真库 e2e(material→evidence candidate 三态→confirm 一条真流)+ 前端 tsc/build 绿 + Playwright native 主路径冒烟。完成后更新记忆断点并 push。
