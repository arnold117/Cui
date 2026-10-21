# Canary 候选：精神影像系统综述（召回金标准）

用途：拿一篇综述的研究问题当 X，把它的纳入研究当成"已知答案"，算我们的工具能找回多少（召回）。2026-10-21 核查，书目信息已经和 Crossref / PMC 对过。

---

## 候选 1（推荐）：Chen 2023, Front Neurosci

- **引用**：Chen Y, Zhao W, Yi S, Liu J. *The diagnostic performance of machine learning based on resting-state functional magnetic resonance imaging data for major depressive disorders: a systematic review and meta-analysis.* Front Neurosci 17:1174080, 2023-09-22.
- **DOI / PMID**：10.3389/fnins.2023.1174080 / 37811326。OA 版本在 PMC10559726，许可证 CC BY：https://pmc.ncbi.nlm.nih.gov/articles/PMC10559726/
- **研究问题**：用静息态 fMRI 做的机器学习区分 MDD 和健康对照，诊断性能（敏感度、特异度、AUC）有多高？
- **建议 X**：有没有人用静息态 fMRI 加机器学习，把抑郁症患者和健康人区分开？分类准确率到底有多高？
- **纳入研究**：31 篇，发表于 2010–2021 年。正文 Table 1 列了第一作者和年份，参考文献大多带 DOI 和 PubMed 链接，可以直接抽出来做 DOI/PMID 列表。Wang 2016（IEEE 会议）和 Sharaev 2018（ICDMW）这两篇没有 DOI，需要手工补。
- **检索策略**：检索了 PubMed、Embase、Web of Science 和 Cochrane，检索日期是 2022-02-23，没有写起始年份。完整 Boolean 检索式直接写在正文 Methods 里，不需要去翻补充材料。
- **PRISMA**：检出 455 条，去重后 320 条，题目/摘要筛选后剩 71 篇进全文，最终纳入 31 篇。各步数字能对上。
- **问题**：
  - 有 4 篇不是期刊论文：Chun 2020（EMBC）、Sharaev 2018（ICDMW）、Wang 2016（IEEE 会议）、Jacob 2020（Biol Psychiatry 增刊里的会议摘要）。论文的排除标准明写了排除摘要，但 Jacob 2020 还是被纳入了，前后矛盾。
  - 检索式里抑郁那一块写成了 `"Major Depressive Disorders"[Mesh] AND "Depression" AND "MDD"`，大概是把 OR 误写成了 AND。照字面复现的话会比作者实际的检索范围窄，正好可以拿来考我们的检索边界。
  - 纳入标准要求能重建 2×2 列联表，所以没报告敏感度/特异度的相关研究都被排除了。结果是工具会找到不少切题、但不在金标准里的论文，这时候精确率会被低估，应该只看召回。
  - 比对时要把发表日期截在 2022-02 之前。
  - 很多纳入论文要付费才能看全文（Brain、HBM、JAD、IEEE JBHI 等），但只按元数据和摘要比对就够了。
  - 参考文献里 Yu 2013 的 DOI 尾号（0083943）和文章号（e68250）对不上，建清单时要核一下。

## 候选 2：Chan 2025, NeuroImage（GNN，跨障碍）

- **引用**：Chan YH, Girish D, Gupta S, Xia J, Kasi C, He Y, Wang C, Rajapakse JC. *Discovering robust biomarkers of psychiatric disorders from resting-state functional MRI via graph neural networks: A systematic review.* NeuroImage 319:121422, 2025-10。
- **DOI**：10.1016/j.neuroimage.2025.121422。许可证 CC BY-NC 4.0（NeuroImage 自 2020 年起是全 OA 期刊）。另有预印本 arXiv:2405.00577 v2（2025-02），也可以免费读：https://arxiv.org/abs/2405.00577
- **研究问题**：用 GNN 在静息态 fMRI 上做精神障碍预测的研究，报出来的"生物标志物"在不同研究之间稳不稳、能不能复现？
- **建议 X**：有没有人用图神经网络在静息态功能连接上做精神障碍的诊断分类，并且报告了哪些脑区或连接是判别特征？如果只用 MDD 子集，就把 X 收窄到抑郁。
- **纳入研究**：摘要里说 65 篇。按障碍分表（Table 2–9）合计 77 行：ADHD 4、ASD 42、MDD 20、SZ 11，多出来的是同时研究几种障碍的论文被重复计入。没有一张总表；参考文献大多不带 DOI，ID 要靠题名反查。
- **检索策略**：检索了 PubMed（158 条）和 Scopus（480 条），截止 2024-10-09。检索式就在正文里：`("graph neural networks" OR "graph convolutional networks" OR "GNN" OR "GCN") AND ("fmri" OR "functional MRI" OR "functional connectivity")`。没有注册方案；PRISMA checklist 放在补充材料里。
- **问题**：
  - 约三成纳入研究是会议论文（MICCAI、ISBI、ICASSP 等）。
  - 纳入标准要求"明确报告了生物标志物"，所以只做分类、没报告特征的 GNN 论文都被排除了，金标准只覆盖 X 的一部分。
  - 只检索了两个库，没有查 arXiv 和 IEEE Xplore，专业检索的边界本身就窄。
  - 我只读了 arXiv v2，没有逐表核对它和 NeuroImage 正式版的纳入清单是否一致。
  - 总数超过 60。建议只用 MDD 的 20 篇当子集金标准。

## 候选 3：Zhang 2025, Psychol Med（静息态网络异常）

- **引用**：Zhang Z, Zhang Y, Wang H, … Hao X, Liu F. *Resting-state network alterations in depression: a comprehensive meta-analysis of functional connectivity.* Psychol Med 55:e63, 2025-02-26。
- **DOI / PMID**：10.1017/S0033291725000303 / 40008424。OA 版本在 PMC12080655，许可证 CC BY 4.0。
- **研究问题**：用种子点或 ICA 方法研究抑郁症的静息态网络时，网络内和网络间的连接发生了哪些一致的改变？
- **建议 X**：有没有人用种子点或 ICA 方法，比较过抑郁症患者和健康人的静息态网络连接（DMN、额顶网络、边缘系统等）？
- **纳入研究**：58 篇（52 篇种子点法，6 篇 ICA）。清单只在补充材料 docx（3.5 MB）里，正文没有列表。
- **检索策略**：检索了 PubMed 和 Web of Science，截止 2023-10。检索词只在正文里用文字描述，没有给可复现的检索式。检出 5689 条，去重后 3915 条，最终纳入 58 篇；中间各步的数字只在 PRISMA 图里。
- **问题**：
  - 只收英文、受试者年龄 18–65 岁、必须报告 MNI/Talairach 坐标，只做 ROI-to-ROI 分析的研究也被排除了。所以金标准比 X 窄很多。
  - 补充材料在 PMC 上，浏览器里不用登录就能下载；但用 curl 访问会遇到 JS 下载页，我没有打开。补充材料里列的是完整参考文献还是只有作者+年份，还没确认。

## 降级备选（各差一条硬标准）

- **Bondi et al. 2023**, Neurosci Biobehav Rev 144:104972（10.1016/j.neubiorev.2022.104972）：用 ML 和 rs-fMRI 区分 MDD 与健康对照，纳入 20 篇。没找到 OA 版本。
- **Meinke et al. 2024**, Neurosci Biobehav Rev 160:105640：用静息态功能连接预测内化障碍（跨诊断）的疗效，纳入 13 篇，少于 15 篇。洪堡大学 edoc 仓库有免费全文（绿色 OA）。

---

## 推荐：Chen 2023

做召回金标准需要的东西，它全部都在正文里：一张纳入研究表、带 DOI/PMID 的参考文献、完整的 Boolean 检索式，PRISMA 的数字也能逐步对上。论文在 PMC 上，CC BY，抓取时不会碰到登录或补充材料下载的问题。31 篇的规模适中，主题正是首选方向（静息态 fMRI 加 ML 诊断 MDD）。它的几个瑕疵反而有用：检索式里 AND/OR 的笔误、4 篇会议论文/摘要、2×2 表这条纳入门槛，正好可以分别检验三件事：我们的检索边界比专业检索员宽还是窄、能不能召回非期刊文献、以及"切题但不在金标准里"的论文该怎么计分。如果还想测 CS 一侧（会议论文多、DOI 少）的表现，就加 Chan 2025 的 MDD 子集（20 篇）作为第二个 canary。
