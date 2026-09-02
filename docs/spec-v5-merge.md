# Spec: Cui v5(淬) — LitScribe 融入升级 + 状态机/SDK/本体分层

> **状态:已收敛(2026-09-02,grill-with-docs 全部 Q 决)。决策见 §1;执行见 §6。**
> 本文档是 v5 的决策真相之一;配套记忆:`AgentMemory/_projects/anneal/project_v5_merge.md`。
> 相关锚:记忆库 lit-scribe / anneal 目录;Cui `docs/prd-research-universe.md` + `CONTEXT.md`(术语唯一真相);LitScribe v4 代码与双库。

## 0. 背景与动因

- 06-11→14 两场 grill:**综述与想法是同一引擎的两个表面**(综述=为 claim 取证,想法=为 claim 辩护)→ 重构成同一引擎。
- 06-15 硬分叉出淬·Cui;LitScribe 休眠。Cui 独自 4 个月:空库冷启动、形态被自己判"很无聊很不对"、8-05 后停摆。
- **2026-09 复活决定:方法(轨迹+闸门)是对的;两个项目合体升级为 v5,主名 Cui(淬)。**
- 架构诉求:**状态机与 SDK 与本体分离,轻量插件化**(参考 cordis/pi/DSH)。
- 产品目的再定义:**综述不是终点——终点 = 现状图景 + gap 清单 + 可行方向**,文档只是导出形式。
- 竞争判断:取证层 commodity、赢判断层;agent 输出可作取证源;aspiration=被 agent 生态调用(判断后端)。

## 1. 已定决策(settled,全部 Q 已决)

### 第一轮:复活骨架
- **S1 主名 = Cui(淬)**:叙事 = "LitScribe 融入 Cui 并升级为 v5"。repo `arnold117/Cui` 保持主干零手术;`arnold117/LitScribe` 保持 v4 证据/归档(301 保留),README 双指针过渡;软著 V1.0 不受影响(v4.0.0 快照登记照常提交),v5 稳定后登记 V2(Cui 名)。Cui public 身份 = 产品本身(不再退为模式名)。
- **S2 主干树 = Cui main**;v4 纯逻辑 cherry-pick,不合并两棵 git 历史。
- **S3 PG 事件库 = 唯一真相**;SQLite/chroma/checkpoints 退役;语料落盘 repo 外。
- **S4 第一刀 = 文献 → 证据三态闸 → 人裁决 → 产物闭环**(按 S21 重切)。
- **S5 语料图 = Cui Tier1**;v4 GraphRAG 不迁;不建 embedding。
- **S6 铁律继承**:自动化取证、永不自动化定见;Lens 只吃 grilled;survived≠证书;taste 只锚不判;代笔红线。
- **S7 v4 数据归并表**:149 篇→Materials(kind=paper,哈希锚);25 旧 session→Material(kind=draft)只读,不冒充 grilled;graph/checkpoints 不迁;`~/.litscribe/output` 3 篇人工收编。

### 第二轮:分层与插件化
- **S8 术语**:kernel(状态机:事件+围栏+投影+守门,零 HTTP/宿主假设/kinds 盲)/ SDK(python 接口规范真相 + REST thin adapter)/ host(本体=产品实例)。API 立 `/api/v3`。
- **S9 动因**:换宿主/再分叉内核可平移 > agent 零锁死(事实:domain/store 零 LLM/agent)。
- **S10 插件化 = 边界缝+静态注册+disposable 惯例**(借 cordis 三样;不做运行时生命周期)。
- **S11 SDK**:python=规范真相,kernel 零 HTTP;OpenAPI 契约;CLI 属本体。
- **S12 扩展点**:kinds/事件新类型/取证生成器(`generator_kind`);**Lens=第一方插件**。
- **S13 slice0 = repo 重组+边界固化,零功能零重写**;单 pyproject + import-linter。

### 第三轮:执行决策 + 产品目的
- **S14(改)rename 一次到位:包名 anneal→cui + conda env**;legacy 路由/UI/lens_feed slice0 摘除;空 legacy 表冻结。
- **S15 kernel 纯度机器执法**:import-linter + CI 红门 + 契约测试。
- **S16 语料全量入厂**:149 篇首库;paper_id=arXiv ID;元数据 markdown 重建;检索双轨。
- **S17 起草闸复用证据候选生命周期**(propose→confirm/correct/reject),灰显未闸。
- **S18 物理搬迁全走 git 分支/工作树。**
- **S19 终产物三层资产**:现状图景 / **gap 清单** / **可行方向**;综述文档=导出渲染。
- **S20 gap 定义钉死**:取证形状 = 覆盖范围声明 + 可复现检索记录 + **反例邀请**;propose 禁"所以你应该做 Y";confirm/correct/reject 走候选生命周期;confirmed gap 进轨迹、可被反证挑战、阵亡喂 Lens;taste 永不入候选形状。
- **S21 第一刀 scope = 方案 1**:现状 + gap 候选 + 人 confirm gap;方向结晶自动化(文献锚+Lens 历史锚→direction)留第二刀(等第一批判例);人工结晶 direction 允许。

### 第四轮:竞争原则 + wedge
- **S22 竞争原则(立)**:① 认输取证层、赢判断层(不比检索/报告速度,比"哪些结论你敢签字");② agent 输出可作取证源插件;③ aspiration=被 agent 生态调用(可信判断后端);④ 判据:每个功能问"离对手更远还是更近"。
- **S23 wedge = 开题 gap 论证 + 投稿 related-work 可信段**(a+b);一句话叙事:"**开题/立项前,用文献把你的方向和 gap 论证到敢签字**";临床留纵深;中文检索债不阻塞。
- **S24 模板收编**:related-work + outline 进第一刀产物形状插件;abstract 归 DOC 形状族候补;grant/proposal PARK;translation/rebuttal 不进主路。

### 第五轮(2026-09-02):主名定稿
- **S25 主名 Cui 定稿 + 简历口径**:产品线一条叙事 —— "Cui(淬,前身 LitScribe)持续开发自 2026-01"(事实锚:LitScribe 首 commit 2026-01-17;最早真实 session 2026-02-07;v4 软著 06-11;Cui 硬分叉 06-15;v5 合体 2026-09)。简历融合照此写,面试故事=改名+重写+合并的进化史。

## 2. 分层架构(定形)

```
kernel   事件目录+commit 围栏+投影机制+命令守门+跨 kind 不变量(零 LLM/agent/HTTP)
SDK      python 服务接口(规范真相)+ REST thin adapter(/api/v3)+ 契约测试
host     本体 = Cui 产品实例(语料管道/产品流/UI/CLI/导出)
plugins  搜索源/解析器/取证生成器(generator_kind)/Lens(第一方)/导出器/UI 视图
```

## 3. 竞争分析:vs Claude Code / Codex research mode(摘要)

- 对手形状:任务终点 + 会话级浅状态 + 顺从 + 弱证据纪律;记忆=摘要 blob、定见无闸、引用纪律弱。
- 取证层已 commodity(我们第一天就主动认输);检索源/agent 输出=可替换插件。
- 稀缺资产:定见结构(人签+可反证+阵亡记录)+ 私人判断史(Lens 反射 taste)。时间不对称:第一天我们输,第 N 天他们追不上。
- 诚实风险:感觉像"更慢的 CC research mode"则必死;冷启动靠"闸门当天有价值"。

## 4. 决策树

**frontier 已空(2026-09-02)。** 遗留待办见 §5,执行见 §6。

## 5. 待办/已办(2026-09-02 更新)

- [x] **GitHub archive 状态**:`arnold117/LitScribe` 未 archive(Arnold 确认)——主名 Cui 后无需任何动作。
- [x] **软著 V1.0**:已在官网提交(2026-09-02);流水号待补记。
- [x] **语料盘点**:完成 → `docs/v4-corpus-inventory.md`(三源:DB parsed_docs 149 + cache/parsed 161 JSON + disk 60 PDF;三主题群:生物工艺 ~60 / LLM 2023+ ~47 / 老 arXiv ~42;importer 设计输入)。
- [ ] **dump v4 问题清单(08-24 欠账)**:已解释——可选。替代方案 = slice0 cherry-pick 逐件审已知问题(参考 bug_audit 2026-03-26 快照 + 本次数据债),不单独 dump。

## 6. 执行计划草案(slice0 迁移 session)

> **细化可执行清单已出:`docs/plan-v5-slice0.md`**(T0 文档迁入 → T1 基线 → T2 rename → T3 legacy 扫除 → T4 import-linter/契约 → T5 语料 importer → T6 cherry-pick → T7 收尾验收;每任务带验收线与风险)。执行时先做 plan T0:三份文档迁入 Anneal repo docs/ 并以那里为准。

> 照 Cui 惯例:主循环收敛 → worktree subagent 实现 → 亲手审计 → cherry-pick → canary。slice0 零新功能。

1. **repo/环境**:本地 trunk = Dev/Anneal 继续;conda env `anneal`→`cui`;包名 codemod `anneal`→`cui`(~253 import;`git mv` + sed + 全量测试绿 + canary 8/8);`.env.example` 同步。
2. **legacy 扫除**:摘 `/api/v1` legacy 路由、前端 legacy 入口、legacy_archive 代码、lens_feed 阑尾;12 张空 legacy 表结构冻结保留;摘除后测试数下降但全绿。
3. **边界固化**:import-linter 规则(domain/store 禁 llm/httpx/host/plugin)+ CI 红门;契约测试目录(python 接口签名快照)。
4. **语料入厂(importer)**:读 v4 `cache/litscribe.db` + `data/pdfs`(149 篇)→ 批量 `material_added`(哈希锚幂等,paper_id=arXiv ID);markdown 首行重建标题元数据;PDF+markdown 落盘 repo 外(建议 `~/.cui/`),PG 存路径+哈希;dry-run + 重跑幂等验收;文件库/哈希 API 进 SDK 契约。
5. **v4 樱桃清单**(同一 session 或 slice1):services(CJK fix 027583c、pdf.py)、exporters(pandoc/bibtex/citation_formatter)、templates(related-work/outline,按 S24)、contradictions/diff 纯逻辑。
6. **验收线**:全量测试绿 + canary C1–C4 不变绿 + importer 幂等 + 真库 e2e(材料进厂→证据候选→人 confirm 一条真流)。
7. **slice1 起**(另 session):review/gap 闭环第一刀(现状+gap 候选+人 confirm,复用候选生命周期),wedge a+b demo。
