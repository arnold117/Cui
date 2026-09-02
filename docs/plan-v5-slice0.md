# Plan: Cui v5 slice0 — repo 重组 + 边界固化 + 语料入厂

> 决策依据:`docs/spec-v5-merge.md`(已收敛,S1–S25)。执行工作树 = Dev/Anneal(Cui trunk)。
> 惯例(Cui):主循环收敛 → worktree subagent 实现 → 主循环亲手审计 → cherry-pick 保线性历史 → canary → push。
> **slice0 零新功能**:只搬移、扫除、固化、入厂;一切重写/新功能归 slice1。

## 0. 目标与边界

- 目标:① repo 从 Anneal 时代更名为 Cui 时代(代码层 rename)② legacy 债务扫除 ③ kernel/SDK 边界机器执法 ④ v4 语料三源入厂(PG 唯一真相)⑤ 基线与 canary 全绿。
- 不做:review/gap 闭环(slice1)、/api/v3 路由重排(slice1 随 importer API 一起)、UI 新功能、方向结晶、PDF 批量补下。
- 退出条件:全量测试绿 + canary C1–C4 绿 + importer 幂等验收 + 真库 e2e(material→evidence→confirm 一条真流)。

## 1. 执行顺序与依赖

```
T0 文档迁入(依赖:无)
 └→ T1 基线快照(依赖:T0)
     ├→ T2 rename anneal→cui(独立,最大 diff)
     ├→ T3 legacy 审计与摘除(可与 T2 并行于不同 worktree,cherry-pick 先后)
     └→ T4 import-linter + 契约测试骨架(依赖 T2)
T5 语料 importer(依赖 T2,T4;可并行 T3 的审阅)
 └→ T6 v4 cherry-pick 清单(依赖 T1;逐件小步)
T7 收尾验收(依赖全部)
```

## 2. 任务清单

### T0 文档迁入(半小时)
- ✅ **2026-09-02 已执行**:三件套 canonical 已在本 repo docs/(LitScribe/docs 副本为前史不再更新);commit 见 git log。
- 若本 repo docs 三件套缺失或被改动,先 `git log` 找回,勿重建。
- 验收:三文件在 trunk docs/,README/CLAUDE.md v5 指针就位。

### T1 基线快照(半天内,先跑通再动刀)
- 环境核对:`conda activate anneal`、PG 起、`.env`(CUI_DATABASE_URL)就位、alembic 在 `sealed_park_v1`。
- 复跑基线并**记录数字**:`pytest`(预期 850 passed/34 skipped)、两个 canary(`scripts/canary_l3.py`、`canary_native_slice6.py`,真 key)双绿、前端 `tsc`/`vitest`/build 绿。
- 打基线 tag:`v5-baseline`(当前 HEAD 5c35bf4 或其后);后续每 task 一个 commit,可随时 `git diff v5-baseline` 整体审计。
- 产出:`docs/plan-v5-slice0.md` 追加"基线记录"段(测试数/canary/环境)。

### T2 rename anneal→cui(一天级,codemod 非重构)
- 范围清单(实测 90+ py 文件引用):
  - `git mv backend/anneal backend/cui`;包内 import `anneal.` → `cui.`
  - `backend/pyproject.toml`(name/任何 entry)、`backend/alembic.ini`(script_location)、egg-info 目录
  - `backend/scripts/*.py`、`backend/tests/*`(conftest 引用)、canary 内路径
  - `.env.example` 注释、README/CLAUDE.md/CONTEXT.md 中代码层引用(品牌已是 Cui,只清代码名)
  - conda env:`conda rename -n anneal cui`(或 recreate;记得同步各 shell 的 feedback 习惯——**记忆里"用 anneal env"的规则随之改 cui**)
- 机械做法:sed 全量替换 → `grep -rn "anneal" backend/` 清到只剩必要字符串(如迁移脚本历史名)→ pytest 全绿。
- 验收:后端全量测试绿、canary 双绿;`import anneal` 零残留(除明确保留的 legacy 归档注释);前端不动(不 import python 包)。
- ⚠️ 风险:alembic 迁移文件头部若引用包路径要一起改;egg-info 重建(`pip install -e ".[dev]"` 于 cui env)。

### T3 legacy 审计与摘除(半天审计 + 一天实现)
- **先画使用映射表再删**(防误删 native 依赖):
  - API:`app.py` 中 `/api/v1` legacy_router(整组)+ `/api/v2` 下 `create_archive_router`(legacy tables 的 archive 端点——查前端是否还在调用;RU 原生已不依赖则摘)
  - 前端 legacy 视图/入口:Sidebar legacy 项、ParkView、DocView、GrillView/useGrillFlow 若已无路由可达(P2.5 后 RU 取代)→ 摘;CorpusGraphView/TrajectoryView/VersionsView 先查归属(native 投影在用则保留)
  - 服务:`services/` 下 legacy 专用且无 native 调用者(grounding_service/grill_service/lens_* 若只服务 legacy 端点)→ 移 `legacy_archive/` 目录而非直接删(git 历史可查,但保留归档便于将来回看);**lens_feed 阑尾**:摘(写-only、空数据,L3 全从事件流投影读)
  - DB:12 张空 legacy 表**冻结保留**(迁移链不断),不 drop
- 验收:后端测试绿(测试数下降属预期)、前端 tsc/vitest/build 绿、Playwright 冒烟 native 主路径(workspace→claim→review→evidence→verdict)全过、`grep useGrillFlow/ParkView` 零命中。
- ⚠️ 风险:GrillView 可能仍有 native 引用面(forge 复用?)——审计表先列引用方再动。

### T4 import-linter + 契约测试骨架(半天)
- 分层规则(据 spec S8/S15):
  - `cui.domain`(含 research_universe/domain)与 `cui.store` 层:**禁 import** `cui.llm`、httpx、`cui.api`、宿主与插件模块
  - `cui.llm` 只能被 services/challenge_generator/取证插件 import
  - 宿主/插件可 import SDK(service 接口层),反之不行
- 工具:`import-linter`(pip dev 依赖)+ `backend/linter/contracts.py` 规则文件 + `Makefile` 目标 `lint-contracts`,本地 gate;`.github/workflows` 可选后置(GitHub Actions 仓库现无 CI,先本地脚本,规则文件即契约)。
- 契约测试骨架:`backend/tests/contracts/`(接口签名快照/方向断言的最小目录 + README 说明写法);API `/api/v3` 重排与 importer 端点留 slice1。
- 验收:`make lint-contracts` 0 违规;新代码方向性错误能被 gate 抓住(写一个负例验证 gate 会红,然后删掉)。

### T5 语料 importer(1–2 天,slice0 最大件)
- 输入(见 v4-corpus-inventory.md):三源合并去重 → 预期 ~160–170 实体:
  1. `cache/litscribe.db` parsed_docs(149,含 89 arXiv + 56 DOI + 4 local)
  2. `cache/parsed/*.json`(161,取并集补漏)
  3. `data/pdfs/`(60,补 DOI 批的 file_hash/路径登记)
- 设计:
  - 迁移器 = 一次性脚本 + 可重跑幂等(材料锚 = file_hash / arXiv-ID / DOI 的归一化 ID;已存在则跳过并报告)
  - 落点:批量 `material_added` 事件(带 generator_kind=system + provenance:source=v4-cache-db、original_table、row 时间)→ 走现有 native commit 管线(取 PG contract 测试模式,建临时库验)
  - 元数据回填:联网 OpenAlex/arXiv API 按 ID 拉真实标题/作者/年/被引(免 key);失败的保留 markdown 首行标题并标记 `meta_pending`
  - 标签:`legacy`(生物工艺 ~60 + 老 arXiv ~42)与 `active`(LLM 群 ~47)两批;检索默认只进 active
  - 文本落盘:`~/.cui/materials/{id}.md`(repo 外);PDF 不批量补
  - v4 SQLite 退役:迁移完成后只读归档改名(`*.db.legacy-v4`),不删
- 验收:dry-run 报告(总数/新增/已存在/失败)一致;重跑幂等(第二次 0 新增);真库 e2e:任一 active 材料可走到 evidence candidate 三态(复用 slice4 端点,一条真流);时间盒内完成 160+ 实体入库。
- ⚠️ 风险:DOI/arXiv ID 归一化边界案例(版本号 v3、local: 哈希)→ 用 inventory 全表做 fixture 单测。

### T6 v4 cherry-pick 清单(逐件小步,每件一个 commit)
按 spec S16/S24/S7,逐件:定位 → 读全 → 审(v4 已知问题注记)→ 搬入 → 最小测试 → commit:
1. 搜索 CJK 修复 + IDF 权重(027583c 纯逻辑)
2. `pdf.py`(下载/哈希,无 MinerU 依赖部分)
3. exporters:pandoc/bibtex/citation_formatter(产物导出,slicel 用)
4. prompts/templates.py 的 related-work + outline(按 S24;grant/proposal 只留设计笔记)
5. contradictions/diff 纯逻辑(若无 native 等价物)
- 每件验收:搬入件有测试或明确"由 slice1 端点接管";grep 无半搬状态。
- ⚠️ v4 数据债注记(从 bug_audit 03-26 + 盘点):papers 元数据空表、FTS 空、word_count 全 0——**不搬表结构,只搬纯逻辑函数**。

### T7 收尾验收 + 冒烟(半天)
- 全量:`pytest` 绿(记录新数字)+ canary C1–C4 双脚本绿 + tsc/vitest/build + Playwright native 主路径 + importer 幂等复跑。
- 文档:README v5 状态段(主名 Cui、前身 LitScribe、双指针)、`docs/plan-v5-slice0.md` 收尾段(实际数字 vs 基线)。
- 记忆收尾(agent-memory):进度断点更新进 `_projects/anneal/project_progress.md`(或 v5 新进度文件),spec/plan 指针就位。
- push:trunk 各 commit push `arnold117/Cui`。

## 3. 风险与回滚

- rename 破坏 alembic/egg-info → T2 独立 commit,T1 tag 可回滚重来。
- legacy 误删 native 依赖 → T3 先出引用映射表(审计产物 commit),删完靠全量测试 + Playwright 兜底。
- importer 语义偏差(材料锚/标签错)→ dry-run 报告先人审再落真库;PG contract 走临时库。
- canary 依赖真 key/网络 → 环境失败不算实现失败,记录并降级为"待真跑"清单(但 T1 基线 must 真跑)。

## 4. slice1 预告(本 plan 不含)

- /api/v3 契约化 + 语料检索端点(active/legacy 分区)
- review/gap 闭环第一刀(现状 + gap 候选 + 人 confirm,复用候选生命周期;wedge a+b demo)
- related-work/outline 产物形状插件接线
