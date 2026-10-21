# 竞品扫描:缺口 / 先例检索("有没有人做过 X?")

调研日期 2026-10-21。只看公开网页、文档、论文,未注册、未登录。凡写"据官方介绍"的,都是厂商自述,未经验证。来源编号 `[S#]` 见文末。

## 一句话结论

**没有任何 AI 产品端到端交付"可审计的缺席证明"。** 离得最近的三家各只占一段:**Edison Precedent**(原 FutureHouse Owl / HasAnyone)问的正是这个问题,但只给一个黑箱答案,没有检索边界,没有逐篇人工裁决,也没有公开评测;**Elicit Systematic Review** 的审计骨架最完整,但它是为"纳入证据"设计的,不是为"证明缺席",而且完整审计功能锁在 Enterprise;**Undermind** 是唯一说得出"为什么停"的(发现曲线饱和、覆盖率估计),但过程不透明,也没有边界报告可导出。真正端到端做"带边界的新颖性否定结论"的是中国的**人工科技查新**(查新报告),不是任何 AI 产品。

## 对比表

图例:✓ 有 / partial 部分 / ✗ 无 / ? 未能核实。为了可读,表格拆成两张,列号对应任务里的 10 列。

### 表 A(第 1–5 列)

| 产品(2026-10 状态) | 1 明确回答"有没有人做过" | 2 检索透明度(query/源/数量/日期/停止原因) | 3 全文段落级证据 | 4 逐篇人工判定 / AI 反驳 | 5 全文来源 |
|---|---|---|---|---|---|
| **Edison Precedent**(FutureHouse 平台迁入 Edison Scientific;Owl→HasAnyone→Precedent) | ✓ 专门 agent:"Has anyone done this before?"、找 gap、避免重复 [S2] | partial:UI 有 Reasoning/References 标签 [S9];API 只返回 `answer`/`formatted_answer`/`has_successful_answer`,verbose 模式给 agent_state 和 contexts,没有检索式、命中数或停止原因 [S3] | ✓ PaperQA 系列在全文分块上取证;Literature 回答附所用图表与页码 [S4][S8] | ✗ 未见任何标注或覆盖入口 | partial:平台语料 175M 论文/试验/专利 [S2];Springer Nature 60 本刊目前只进 enterprise Kosmos [S7];开源 PaperQA 可跑本地 PDF [S8];平台能否用用户自己的 PDF ? |
| **Edison Literature**(PaperQA3,2026-02-18) | partial:通用文献问答 | 同上 | ✓ 多模态读图表 [S4] | ✗ | 同上 |
| **Undermind**(含 2026-05 Projects 改版) | partial:定位"找到别人漏掉的论文",不做显式新颖性判定 [S11] | partial:检索式不可见、不可编辑,JCHLA 书评称这是最大弱点 [S15];但有"发现曲线"覆盖率估计和 converged 判定,是唯一给出停止依据的 [S13][S15] | partial:2024 年时只用题名+摘要 [S13];现 Pro 标"full texts 最深分析",Projects agent 可引用"摘要或全文(如有)"[S11][S14];能否定位到段落 ? | partial:AI 相关性表,可排序、过滤 [S11];用户能否标注或推翻 ? | partial:Semantic Scholar 语料 [S15];Pro 支持 files/paper libraries [S11] |
| **Ai2 Asta – Find papers**(= Paper Finder) | partial:找论文集合,不做新颖性判定 | partial:可实时看到 query 拆解和每一步 [S16][S9];2026-07 起 Deep search 默认"自评结果不足就继续搜"[S18];不输出检索日志或停止原因 | ✓ 返回句级以上 snippet + 章节标题;12.4M 全文 / 108M 摘要 [S16][S17] | partial:AI 按子标准分别判"perfectly / somewhat relevant"并附证据 [S16][S9];用户只能排序、过滤 [S17] | partial:只用 OA 全文;未见用户 PDF 入口 |
| **Elicit Systematic Review** | ✗ 为系统综述设计,没有"先例"模式 | ✓/partial:Boolean 关键词模式"可完美复现";源=138M 自有语料 + PubMed + ClinicalTrials.gov + 导入的检索 [S20][S21];自动生成 PRISMA 图 [S20];未见逐库命中数日志 [S21] | partial:每个筛选决定附原文引句;抽取单元格可点开 supporting quotes [S21] | ✓(人工)/ ✗(反驳):人工 Include/Exclude 覆盖 AI 决定,排除必须填理由;有阈值滑条;Enterprise 双人审 + audit trail [S21];AI 不反驳 | partial:全文靠浏览器插件或手动上传;免费版也可导入 Zotero [S21][S22] |
| **Consensus Deep Search** | ✗ 偏 yes/no 式共识问题;报告含 Research Gaps Matrix [S26] | ✓/partial:侧栏可展开每段 query;PRISMA 式流程图(例:20 次检索 1004 命中 + 引文追溯 43 → 去重剩 714 → 剔低相关 141 → 573 → 取前 50)[S26];停止规则是固定取前 N,不是饱和判断 | partial:标出是否用了全文,但点 details 不会跳到所用段落 [S26] | ✗ 未见 | partial:OpenAlex + S2,以 OA 为主;Sage、T&F 付费全文只用于相关性和预览 [S26][S28];LibKey 机构链接 [S26];2026-06 起可附论文、对 library 跑 Deep Search [S27] |
| **SciSpace**(Deep Review / Agents) | ✗ 官方未见;Agent Gallery 有第三方自建 agent ? | partial:先拆子问题 [S30];CASRAI 称它不提供可复现检索策略 [S30] | ? | ? | ?:第三方称有 280M+ 论文库 [S30] |
| **scite** | ✗ 针对"这条 claim 被支持还是被反驳" | partial:Assistant 侧栏 "Search Strategy" 显示 Boolean 检索式;参考列表可导出 [S35] | ✓ 每条 claim 链到原文具体句子;引用语境分 supporting / contrasting [S32] | ✗ | ✓ 44+ 出版商协议(Wiley、SAGE 等)+ OA,323M 全文 [S32] |
| **OpenAI Deep Research** | ✗ 通用 | partial:可实时看进度、中途插话;2026-02 起可限定可信站点和 MCP/apps [S36];没有结构化日志 | partial:引用的是网页,不定位学术全文段落 | ✗ | partial:web + 连接器 + 上传文件 [S36] |
| **Gemini Deep Research** | ✗ | partial:先出可编辑的研究计划,并显示 thinking 面板 [S37] | partial:网页 | ✗ | partial:web + 上传 + Gmail/Drive [S37] |
| **Perplexity**(academic) | ✗ | ✗/partial:列出来源;academic 模式只是"偏向"学术库 [S38] | partial | ✗ | partial:web |
| **NotebookLM** | ✗ | partial:Deep Research 返回带注释的来源列表 [S39] | partial:只对已导入的源 | ✗ | ✓ 用户自己的文件 [S39] |
| **Google Scholar Labs**(2025-11 起,实验性) | ✗ 但会逐篇解释"这篇如何回应你的问题"[S40] | partial:拆成子话题分别检索,不显示检索式 [S40] | partial:每篇一句说明 + 两条要点;是否基于全文 ? | ✗ | ? |
| **ResearchRabbit / Litmaps / Connected Papers** | ✗ | partial:引文图是确定性的,种子定了结果可复现,但这不是检索日志 | ✗ 只有元数据 | partial:用户自己挑种子、收藏;没有 AI 判断 | ✗ |
| **OpenNovelty**(复旦 + WisPaper.ai,研究系统,2026-01) | ✓ 抽贡献点 → 检索 → 层级分类 → 逐贡献全文比较 → 新颖性报告 [S42] | ? | ✓ 报告含引用和证据片段 [S42] | ✗ 面向审稿 | ? |
| **Idea Novelty Checker**(Ai2 等,研究原型,2025-06) | ✓ 判 novel / not novel 并附依据 [S43] | ✗ | partial:基于 snippet | ✗ | ? |
| **ResearchChecker**(医学,个人项目,2026) | ✓ 给新颖性分级 [S44] | ✗ 不显示检索式 [S44] | ✗ | ✗ | ✗ |
| *参照:中国科技查新(人工服务)* | ✓ 判查新点新颖性 [S45] | ✓ 报告必须写实际使用的检索工具及时间范围、检索词、布尔检索式 [S45] | partial:逐篇描述对比文献 [S45] | ✓ 查新员 + 审核员人工判定并签字 [S45] | 机构订购库 |

### 表 B(第 6–10 列)

| 产品 | 6 生医覆盖 | 7 可导出审计/证明报告 | 8 跨查询持久化 | 9 价格 / 中文 | 10 公开评测(先例任务) |
|---|---|---|---|---|---|
| **Edison Precedent / Literature** | ✓ 生医是主场;PubMed、临床试验 [S2][S9] | ✗ 只有答案文本 | ? | 免费 10 credits/月;.edu 另有 650 欢迎额度;Kosmos 档 $200/月 [S6];据索引摘要,Precedent 每次约 1 credit [S10];中文 ? | **Precedent ✗ 无公开评测**,2025-11 的平台性能文章只评了 Literature、Analysis、Molecules [S5];PaperQA2 在 LitQA2 上精度 85.2%、准确率 66.0%(9 名专家为 73.8% / 67.7%),21.9% 回答"信息不足"[S8];PaperQA3 准确率比 PaperQA2 高 15–45%,数字只在图里 [S4];LABBench2 未见先例子集 [S47] |
| **Undermind** | partial:经 Semantic Scholar 覆盖 PubMed 元数据;无 MeSH [S15] | partial:报告 + 引用;Pro 可导出 CSV/BibTeX/RIS 到 Zotero/EndNote/Covidence [S15];没有边界报告 | ✓ Projects:去重统一库、三个 agent、可协作 [S14] | Free / Pro $16/月(年付)/ Team $15/人 [S11];中文 ? | partial:自测 23 个 query,10 分钟内找回 top-20 最相关论文的 85%,前沿 web agent 为 43–50%,精度 58%,金标准由 LLM 读摘要构建 [S11];v1 白皮书对比 Google Scholar [S12];无独立评测 |
| **Asta Find papers** | partial:S2 含生医;report 索引 CS/医学/环境/生物 [S17] | ✗ 只能分享链接 [S17] | partial:登录后保存查询历史 [S17] | 免费 [S16];中文 ? | partial:LitSearch 改造版上,full 模式 89% 的 query 找到 perfectly relevant;不报召回 [S16];25 万+ 真实 query 中 research gap 类只占 2.3%(PF)/ 5.2%(SQA)[S19] |
| **Elicit SR** | ✓ PubMed + ClinicalTrials.gov [S20] | partial:PRISMA 图 + 各步 CSV;完整 audit trail 只在 Enterprise 双人审里 [S20][S21] | ✓ Library [S21] | Pro $49/月(SR 上限 5000 篇)/ Scale $169 / Enterprise 4 万篇 [S22];中文 ? | partial:厂商称 2026-05 在 994 篇 Cochrane 综述上检索召回 95% [S24],2025 年筛选召回 93.6% [S23];**独立研究**:Lau & Golder 2025 测得检索敏感度 39.5%(原综述 94.5%)[S25];Lagisz 等 2026 认为抽取只宜作第二审 [S48] |
| **Consensus** | partial | ? | ✓ library [S27] | 据第三方:Free 每月 3 次 Deep;Pro 约 $15/月 15 次;Deep 档 $65/月 200 次 [S29];中文 ? | ✗;SciSpace 自测里 Consensus 的 top-1 精度最高 [S31] |
| **SciSpace** | ? | ? | ? | credits 制,免费 100/月(第三方)[S30];中文 ? | partial:自测 200 个 query,LLM 评委打分,Deep Review 平均每 query 26.3 篇相关(Elicit 13.0、Consensus 约 16);不报召回 [S31] |
| **scite** | partial:Pro 起含临床试验数据集 [S34] | partial:参考列表导出、citation 报告 [S33][S35] | ✓ Collections + alerts [S34] | Basic $12/月,Pro $40/月(年付),7 天试用 [S34];中文 ? | ✗ |
| **OpenAI / Gemini Deep Research、Perplexity** | partial:只到网页可达的部分 | partial:报告,不带边界 | partial | 订阅制;Gemini 支持 45+ 语言 [S37],均能用中文提问 | ✗ 未见先例任务评测 |
| **NotebookLM** | ✗ | ✗ | ✓ notebooks | 免费 + 付费;中文 ✓ | ✗ |
| **Google Scholar Labs** | partial | ✗ | ? | 免费,需登录;所有语言 [S40] | ✗ |
| **RR / Litmaps / CP** | partial(元数据) | partial:文献列表导出 | ✓ collections / maps / alerts [S41] | RR+ $12.5/月;Litmaps Pro $10/月;Litmaps 2025-05 收购 RR [S41] | ✗ |
| **OpenNovelty** | ✗(ML / ICLR) | ✓ 500+ 篇 ICLR 2026 投稿的报告公开 [S42] | ✗ | 研究系统;中国团队 | ✗ 无定量指标 [S42] |
| **Idea Novelty Checker** | ✗ | ✗ | ✗ | 研究原型 | partial:与专家一致率比现有方法高约 13% [S43] |
| **ResearchChecker** | ✓ PubMed、Europe PMC、ClinicalTrials.gov、PROSPERO [S44] | partial:可下载 PDF,但不带边界 [S44] | ✗ 不存储 | ? | ✗ 自称只是筛查辅助 [S44] |
| *中国科技查新* | 视查新站 | ✓ 正式报告,结论分"区域结论""日期结论",签字盖章 [S45] | — | 付费人工服务(价格、周期未核);中文 ✓ | — |

## 最接近的三家

**Edison Precedent(原 Owl / HasAnyone)。** 它是唯一一个产品层面就叫"有没有人做过"的 agent。2025-05 随 FutureHouse Platform 发布 [S1],之后平台迁到商业分拆公司 Edison Scientific,2026-02 换上 PaperQA3 底座 [S4]。它做得好的地方:跨领域检索,在全文分块上取证,Literature 回答附页码和图表 [S4][S8],生医覆盖强,API 可编程 [S3]。它明显不做的:(1) 输出是一段答案外加一个 `has_successful_answer` 布尔值 [S3],没有检索式、命中数、日期、停止原因,也就是没有边界;(2) 用户不能逐篇判定;(3) 没有可导出的证明;(4) Precedent 本身没有任何公开评测,LitQA2 的数字测的是问答,不是"证明没有"[S8];(5) 唯一的第三方试用评价是"underwhelming"[S9]。Edison 当前的重心是 Kosmos 和企业客户 [S7],Precedent 是"保留在 playground"的老 agent。

**Elicit Systematic Review。** 它在审计这一层最接近我们:Boolean 检索可复现,PubMed 和 ClinicalTrials.gov 是一等数据源,自动生成 PRISMA 2020 流程图(2026-08)[S20],每个筛选决定都附原文引句,人可以推翻并必须填理由,Enterprise 还有双人审和 audit trail [S21]。它明显不做的:(1) 目标是"把该纳入的找全",不是"证明某个 X 不存在",没有先例模式;(2) 用户推翻 AI 时,AI 不会反驳;(3) 反检索(同义词、引文追溯)不是用户可见的步骤;(4) 完整审计功能在 Scale/Enterprise,硕博个人用不起;(5) 厂商宣称的 95% 检索召回和独立测得的 39.5% 敏感度差距巨大 [S24][S25]。

**Undermind。** 它是唯一认真处理"什么时候可以停"的:用发现曲线估计"已找到约 93% 的相关论文",判定 converged 后才停,覆盖率低时建议延长搜索 [S13][S15]。这是我们第 5 步"带边界停止"最接近的现成做法。它的召回自测也最好(top-20 召回 85%,web agent 为 43–50%)[S11];2026-05 加了 Projects 持久化 [S14]。它明显不做的:检索式不可见、不可编辑,书评称这是主要弱点 [S15][S9];覆盖率估计说的是"相关论文集合找全了多少",不是"X 不存在的置信度";用户不能逐篇裁决;全文使用范围不清楚。

(第四名:**Consensus Deep Search** 的检索透明度是 AI 产品里最好的,query 可见、带 PRISMA 式计数 [S26],但它不做新颖性判断,不做逐篇裁决,停止规则是"取前 50"。)

## Cui 还剩什么差异

先说结论:**能力层几乎没有差异,剩下的是协议和交互层。** 检索、全文、引文追溯、段落定位,每一项都有人做得和我们一样好甚至更好。

1. **把"缺席"本身当交付物。** 没有 AI 产品输出"在源 S、检索式 Q、日期 D 的范围内,没有找到覆盖 X 的论文;A、B 在某些方面部分覆盖"这种结论。业界把"找不到"当作弃权:PaperQA2 有 21.9% 回答"信息不足"[S8],Precedent 只返回一个布尔值 [S3]。这一条差异是真的,而且有现成格式可抄:科技查新报告要求写明检索工具及时间范围、检索词、检索式、对比文献,并给出"区域结论"和"日期结论"[S45]。中国硕博本来就认得这套格式。
2. **逐篇三档覆盖判定,并且 AI 在用户驳回时反驳。** Elicit 允许人推翻,但不反驳 [S21];Paper Finder 的 AI 会按子标准打"部分相关",但用户不能裁决 [S16]。没有任何产品把"用户驳回一篇论文"当作需要证据的动作。这是最具体的空白,但也最容易被抄,Elicit 一个迭代就能加上。
3. **由驳回触发的反检索,并记入边界。** 同义改写和引文追溯人人都做(Paper Finder、PaperQA2、Undermind、Consensus 的引文检索 [S16][S8][S13][S26]),但都是黑箱里的内部步骤,不和用户的判断挂钩,也不写进边界。scite 的 contrasting 引用 [S32] 是现成的反证通道,还没人用在新颖性上。
4. **带边界的证明导出。** AI 产品里只有 Elicit 的 PRISMA 图(为综述服务、高价档)和 ResearchChecker 的 PDF(没有边界)[S20][S44]。人工查新报告完整,但它是付费、人工、慢的机构服务。
5. **诚实地说,不是差异的部分。** 召回:Undermind 有自测数据,我们没有。全文覆盖:scite 有 44+ 出版商协议 [S32],Consensus 有 Sage、T&F [S28],Edison 有 175M 语料加 Springer Nature [S2][S7];Cui 如果只靠 OA,会更弱。生医:Elicit、Edison、ResearchChecker 都直接接 PubMed / ClinicalTrials.gov。持久化:Undermind Projects、Elicit Library、Consensus library 都有。检索层可以接 Asta Scientific Corpus Tool(MCP,12.4M 全文 / 285M passages)[S17]、scite MCP [S33] 或 Edison API [S3],不一定要自建。
6. **需求规模风险。** Asta 的 25 万+ 真实 query 里,research gap 类只占 2.3–5.2% [S19]。这可以解读为"通用工具没服务好这类需求",也可以解读为"这本来就是小需求"。
7. **中文。** 所查文档里没有任何产品提到 CNKI 或万方。如果 Cui 要覆盖中文文献,这是一条差异;但 Cui 目前没有这个能力,这里不能当卖点。

**总评:**Cui 的护城河在"可审计的否定结论"这套协议(边界 + 逐篇人判 + AI 反驳 + 反检索留痕 + 查新式导出)。它可以被复制,技术门槛低。值不值,要看用户在开题、基金申请、回复审稿这些场合,是否真的需要一份能拿出去辩护的证明,而不是一个快答案。

## 未能核实

- **Edison Precedent 的实际界面**(需登录):是否展示检索轨迹或候选论文列表,未核。Labs 页面写有版本 v.20260216、每次 1 credit,但该页现已 301 重定向,这条信息来自搜索索引摘要 [S10]。
- **Undermind**:当前全文的使用范围;用户能否标注或推翻相关性;Projects 里有没有导出。官方 FAQ 和 benchmark 页面打不开(404)。
- **SciSpace**:官方页面返回 403,表中信息全部来自第三方;Agent Gallery 里的 PRISMA / 双人审 agent 在 staging 域名上,没有当作官方功能。
- **Consensus**:导出格式、中文支持,以及来自第三方的价格。
- **OpenAI 帮助中心和博客返回 403**:功能描述来自 OpenAI 页面的检索摘要和 Wikipedia [S36]。
- **Lau & Golder 2025 的数字**:PMC 页面有验证码,Wiley 返回 403,数字来自检索摘要 [S25]。Lagisz 2026 只核了定性结论 [S48]。
- **中文支持**:除 Gemini 和 Scholar Labs 外,其他产品文档都没写;这不等于不支持。
- **科技查新的费用和周期**:未核。

## Sources

- [S1] FutureHouse Platform 发布(2025-05):https://www.futurehouse.org/research-announcements/launching-futurehouse-platform-ai-agents
- [S2] Edison Agents 文档(含 Precedent):https://docs.edisonscientific.com/agents
- [S3] Edison client 文档(JobNames.PRECEDENT / OWL、PQATaskResponse):https://github.com/EdisonScientific/edison-client-docs
- [S4] Edison Literature / PaperQA3(2026-02-18):https://edisonscientific.com/news/edison-literature-agent
- [S5] Edison 平台 agent 性能(2025-11-20):https://edisonscientific.com/news/performance-of-our-platform-agents
- [S6] Edison 价格与 FAQ:https://edisonscientific.com/pricing ;https://edisonscientific.com/faqs
- [S7] Edison × Springer Nature(2026-09-24):https://finance.yahoo.com/technology/ai/articles/edison-scientific-announces-agreement-springer-120000986.html
- [S8] PaperQA2 论文(Skarlinski 等,2024):https://arxiv.org/abs/2409.13740
- [S9] Aaron Tay, Ai2 Paper Finder and FutureHouse:https://aarontay.substack.com/p/ai2-paper-finder-and-futurehouse
- [S10] Edison Labs agents 页面(现重定向至 advances.edisonscientific.com):https://labs.edisonscientific.com/agents
- [S11] Undermind 官网(价格、benchmark 摘要):https://www.undermind.ai/
- [S12] Undermind v1 白皮书(2024-01):https://www.undermind.ai/whitepaper.pdf
- [S13] Aaron Tay 评 Undermind(2024-04,2025-04 修订):https://aarontay.substack.com/p/undermindai-different-type-of-ai-agent
- [S14] SMU Libraries:Undermind Projects 改版(2026-05-11):https://library.smu.edu.sg/topics-insights/undermindai-platform-has-been-revamped-undermind-projects-feature
- [S15] JCHLA 书评:Undermind.ai(Giustini,2025):https://journals.library.ualberta.ca/jchla/index.php/jchla/article/download/29854/22212?inline=1
- [S16] Ai2 Paper Finder 博客(2025-03-26):https://allenai.org/blog/paper-finder
- [S17] Asta Getting Started Guide(2026-02):https://allenai.org/papers/asta-guide
- [S18] Ai2 on X,Asta Deep search 更新(2026-07-21):https://x.com/allen_ai/status/2079616640237408377
- [S19] Asta Interaction Dataset(arXiv 2602.23335):https://arxiv.org/html/2602.23335v1
- [S20] Elicit SR 支持 PRISMA 2020(2026-08-26):https://support.elicit.com/en/articles/15018527-elicit-systematic-review-now-supports-prisma-2020-guidelines
- [S21] Elicit Systematic Reviews 帮助文档:https://support.elicit.com/en/articles/7927169
- [S22] Elicit 价格:https://elicit.com/pricing
- [S23] How we evaluated Elicit Systematic Review(2025-03):https://elicit.com/blog/how-we-evaluated-elicit-systematic-review
- [S24] Elicit 2026-05-06 评测文章(作者页):https://elicit.com/blog/author/pradyumna-prasad
- [S25] Lau & Golder, Comparison of Elicit AI and Traditional Literature Searching(CESM,2025-09):https://pmc.ncbi.nlm.nih.gov/articles/PMC12483133/
- [S26] SMU Libraries:Consensus Pro / Deep Search(2025-11-06):https://library.smu.edu.sg/topics-insights/access-consensus-pro-smu-libraries
- [S27] Consensus news June 2026: Deep Search:https://hlrnet.com/sites/ai/?p=19924
- [S28] Consensus × Sage:https://consensus.app/home/blog/sage-partners-with-consensus-to-bring/ ;Consensus × Taylor & Francis:https://consensus.app/home/blog/announcing-our-partnership-with-taylor-francis/
- [S29] Consensus 价格(第三方):https://costbench.com/software/ai-research-tools/consensus
- [S30] UBC Wiki: SciSpace:https://wiki.ubc.ca/SciSpace ;CASRAI 评 SciSpace Deep Review:https://casrai.org/guides/scispace-discovery-literature-review-feature
- [S31] SciSpace vs Elicit vs Consensus benchmark(SciSpace 自测,2026-06):https://scispace.com/resources/scispace-vs-elicit-vs-consensus-an-ai-literature-search-benchmark-across-200-queries/
- [S32] scite 官网:https://scite.ai/
- [S33] scite February 2026 Release Notes(含 MCP):https://scite.ai/blog/february-2026-release-notes
- [S34] scite 价格:https://scite.ai/pricing
- [S35] scite Search Strategy 说明:https://effortlessacademic.com/scite-ai-review-2026-literature-review-tool-for-researchers/ ;https://library.hkust.edu.hk/sc/scite-pro-tips/
- [S36] OpenAI deep research:https://openai.com/index/introducing-deep-research/ ;https://en.wikipedia.org/wiki/ChatGPT_Deep_Research
- [S37] Gemini Deep Research:https://gemini.google/overview/deep-research/
- [S38] Perplexity academic filter 文档:https://docs.perplexity.ai/guides/academic-filter-guide
- [S39] NotebookLM Deep Research(2025-11):https://www.androidauthority.com/notebook-lm-deep-research-3615722
- [S40] Google Scholar Labs:https://blog.google/outreach-initiatives/education/google-scholar-labs/ ;https://scholar.googleblog.com/ ;https://library.smu.edu.sg/topics-insights/google-scholar-labs-google-notebooklm-enhancements
- [S41] ResearchRabbit 2025 改版:https://www.researchrabbit.ai/announcement-researchrabbit-release-2025 ;RR 价格:https://www.researchrabbit.ai/pricing ;Litmaps 收购 RR:https://itbrief.co.nz/story/litmaps-acquires-researchrabbit-raises-1-million-for-ai ;Litmaps 价格:https://www.litmaps.com/pricing
- [S42] OpenNovelty(arXiv 2601.01576):https://arxiv.org/abs/2601.01576
- [S43] Literature-Grounded Novelty Assessment of Scientific Ideas(arXiv 2506.22026):https://arxiv.org/abs/2506.22026
- [S44] ResearchChecker:https://research-checker.com/
- [S45] 教育部科技查新工作站《查新报告撰写规范》修订说明(2026-05):https://www.cutech.edu.cn/images/20260528/ca9c455e9c9bc8e157afbe0c.pdf
- [S47] LABBench2:https://edisonscientific.com/news/labbench2-an-improved-benchmark
- [S48] Lagisz 等,Using Elicit for data extraction(Research Synthesis Methods,2026):https://www.cambridge.org/core/product/C97DAEC70C3173A260F0B12E729E7250/core-reader
