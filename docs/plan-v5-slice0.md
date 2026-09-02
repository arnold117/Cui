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

## 5. T1 基线记录(2026-09-02 执行)

> tag:`v5-baseline` @ `416cdc5`(T0 d764ffd + skills setup 416cdc5 已 push)。执行者:唯一 session(DSH)。

**环境核对(全过)**

- conda env `anneal`(miniforge3,Python 3.11);PG `localhost:5432` accepting connections
- `backend/.env` 键齐(CUI_DATABASE_URL + CUI_LLM_* 等,值未外泄);alembic head = `sealed_park_v1`(head)
- canary 配置:`openai` provider / `deepseek-v4-flash`

**数字**

- 后端全量 pytest:**850 passed / 34 skipped**(12.5s,1 条 fastapi/httpx deprecation warning)
- 前端:vitest **66 passed**(18 files);`tsc -b` + `vite build` 干净
- canary L3(`scripts/canary_l3.py`,真 key):**8 PASS / 0 FLAKY / 0 FAIL = GREEN**
- canary native slice6(`scripts/canary_native_slice6.py`,真 key):**RED** — 两次独立复跑均为 4 PASS / 2 FAIL,失败用例不固定(第 1 次 C-multi + 1;第 2 次 C-challenge-en + C-multi)

**slice6 canary RED 根因(探针取证,非网络/非本轮代码改动)**

- 探针真调 8 次(Slice 1 SYSTEM + 英文 claim):键集 8/8 全部正确(无多键、无缺键),但 **6/8 次 `uncertainty` 是 JSON 数字**(float 0.2–0.85),而校验要求非空字符串(`challenge_generator.py:44` Slice 1 / `:52` Slice 6,同型严格检查)→ `ValueError: model response is not the Slice N challenge schema`。
- 8-05 断点记录的旧假设"DeepSeek 偶发多返回键触发 set 严格相等"**被今日探针证伪**:实际成因为模型把 uncertainty 当置信度数值输出 × 代码强类型(必须 str)。
- 这是 T0 后代码零改动前提下的既有脆弱点 × 现模型(deepseek-v4-flash)行为,属基线事实,不是回归引入。

**验收线判定**

- [x] 环境核对(conda/PG/.env/alembic)
- [x] 全量 pytest 850/34(记录)
- [x] canary L3 双绿之一
- [x] canary slice6 双绿之二 —— 见下方补记(修复后 6/6 GREEN)
- [x] 前端 tsc/vitest/build
- [x] tag `v5-baseline` @ 416cdc5
- [x] plan"基线记录"段 — 本段即产出(随 commit 落库)

**补记(2026-09-02,Arnold 决策"先修脆弱校验再进 T2")**

- 修复 commit `61f2852`:`challenge_generator.py` 校验容忍数值型 `uncertainty`(int/float → 统一转 str,payload 契约不变;bool/空串/非有限 float/缺键/多键仍拒绝);新增回归单测 `backend/tests/test_challenge_generator.py`(14 条:数值接受/字符串保留/旧失败形态仍拒绝/错误消息保留)。
- 修复后验证:全量 pytest **864 passed / 34 skipped**(850 基线 + 14 新增);slice6 canary **6 PASS / 0 FLAKY / 0 FAIL = GREEN**(真模型复跑)。
- 双 canary 至此全绿,基线验收线补齐。`v5-baseline` 仍 @ `416cdc5`(修复在其后,`git diff v5-baseline` 可见全貌)。

## 6. T2 执行记录(2026-09-02)

- **commit `b26bc78`** `refactor: rename anneal -> cui (T2)`:git mv `backend/anneal` → `backend/cui`;代码层替换(点路径/斜杠路径/裸词三类,91 文件,472+/472-);pyproject name → `cui` + setuptools 包发现限定 `include=["cui*"]`(否则 alembic 目录被平铺发现误报);CLAUDE.md(conda cui)/docs/v5-handoff.md §4(终态)同步。
- **保留项(按设计)**:数据库名 `anneal` 不 rename(PG 仍是 `/anneal`;5c35bf4 保险 `_FORBIDDEN` 集合同时拦 anneal/cui);测试 URL fixture、`annealing` 检索词、`anneal_cutover_` 临时库名;archive 文档与 plan 任务原文。
- **conda env rename** `anneal` → `cui`(2026-09-02);editable 重建于 cui env。
- **验证数字**(anneal env rename 前与 cui env rename 后两次):全量 pytest **864 passed / 34 skipped**;canary L3 **8/8 GREEN**;canary slice6 **6/6 GREEN**;`from anneal`/`import anneal` 零残留(代码);中性目录 `import cui` OK。
- 前端未动(零 python import)。下一步:T3 legacy 审计与摘除(先出引用映射表,12 张空 legacy 表冻结不 drop)。

## 7. T3 执行记录(2026-09-02)

**审计产物**:`docs/t3-legacy-audit.md`(commit `3b76166`)——面→引用方→判定映射表。

- **commit `4895022`**(T3 backend):v1 API 面整组摘除(`cui/api/routes.py` 30 端点 + `deps.py` + `create_legacy_regression_app`);legacy 垂直归档 `cui/legacy_archive/{services,search,lens}`(8 服务含 internal 前缀改写;canary_l3 import 改指归档路径);**lens_feed_service 阑尾删除**(非归档,写-only 空数据)+ `lens_feed_projection` 投影函数与测试摘除(`lens_feed_entries` 表冻结保留);legacy 测试整组删除(约 25 文件,含依赖已删 helper 的 test_native_slice1_pg 改本地定义);native/archive/store/domain 测试保留。
- **commit `7c0ccd3`**(T3 frontend):死 UI 级联删除——6 视图(ParkView/DocView/GrillView/CorpusGraphView/TrajectoryView/VersionsView)+ useGrillFlow + 第二层(Sidebar/SidebarItem/EvidencePanel/PrecedentTrace/GrillMessage/EventCard)+ EmptyState + 孤儿 `src/api.ts`(v1 BASE)/`src/utils.ts`/`src/types.ts`(Archive 类型本地化至 legacy-archive/api.ts)。保留:LegacyArchive(`/archive*` 活跃面)、ParkDesk(native)、RU 全部。
- **保留(按设计)**:`/api/v2/legacy-archive` 只读端点 + FE archive;12 张 legacy 表冻结 + preflight 清单;`cui/store/*` + `cui/domain/*`(archive/store 依赖);`libraries` 表(native 用)。
- **验证数字**:后端 pytest **396 passed / 15 skipped**(864→396,legacy 摘除预期);canary L3 **8/8 GREEN**(归档路径)、slice6 **6/6 GREEN**;前端 tsc/vitest **66/66 ×3**(一次瞬时 flaky 后稳定)/build 绿。
- **未做/延迟**:Playwright native 主路径冒烟(需真库 + 起服 + 浏览器,T7 收尾统一跑);vitest App.test 有一次与 act 警告相关的瞬时失败(复跑稳定,疑似既有 flake,观察)。
- 下一步:T4 import-linter + 契约测试骨架(依赖 T2 ✓)。

## 8. T4 执行记录(2026-09-02)

- **commit `507f368`**:层间契约 gate + kernel 纯度修复 + 契约测试骨架。
- **gate 基建**:`backend/linter/contracts.py` = 单一规则源(S8/S15 编码:kernel 纯度 / cui.llm leaf / SDK 不反向依赖 host/llm/plugins);`python -m linter`(backend/)把源包展开成具体模块喂 import-linter v2.14;根 `Makefile` 目标 `lint-contracts`;pyproject dev 依赖加 `import-linter`。
- **纯度为真(机器抓出 2 处真实违规,已修)**:① `cui.store.database` 引 dotenv → 剥离(kernel 永不装 .env),host(`cui.api.app.create_native_app`)显式 `load_dotenv()` 补位;② `cui.llm.prompts`(legacy 提示词文本)引 cui.domain → **移入 `cui/legacy_archive/prompts.py`**(importers 4 处 + 2 测试同步;cui.llm 变纯 transport/config)。会话开 `exclude_type_checking_imports`。
- **契约测试骨架**:`backend/tests/contracts/`(README 说明写法 + `test_native_store_interface.py` NativeEventStore 协议方法集快照)。
- **验收**:`make lint-contracts` → 3 kept / 0 broken(87 文件 303 依赖);**负例验证**:临时在 `cui/store` 塞 `from cui.llm.client import ...` → gate 红(1 broken) → 删 → 复绿 ✓;全量 pytest **397 passed / 15 skipped**(+1 快照);canary L3 复跑 **8/8 GREEN**(归档 prompts 路径端到端);前端未动。
- 注:`test_native_slice0` 的 fails-closed 测试因 host load_dotenv 补位而更新(中和 dotenv,契约语义不变)。
- 下一步:T5 语料 importer(依赖 T2/T4 ✓;T3 审阅可并行,此处串行)。
