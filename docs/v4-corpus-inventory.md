# v4 语料盘点(2026-09-02)

> 供 spec-v5-merge §6 importer 设计使用。结论:正文资产**基本完整且三群主题清晰**;PDF 二进制部分散失;`cache/parsed` 是冗余解析副本。

## 资产事实(硬结论)

### 正文(可迁移本体):`cache/litscribe.db` parsed_docs = 149 篇全文
- **89 篇 arXiv(YYMM 可解析)**:2023 前 42(老 arXiv:物理/生物/化学跨学科)+ 2023–2026 47(**LLM 时代**:微调/训练、科研自动化/综述、评测、agent、推理)
- **56 篇 DOI 生物工艺文献**(CHO 细胞培养/CRISPR/植物次生代谢/紫杉醇——2026-02~05 生物碱与 CHO 项目时代,Nature 2023、BMC Plant Biology、Frontiers 等)
- **4 篇 `local:`**(Taxus 紫杉醇/红花等,同时代手工导入)
- 文本总 ~30MB,每篇 36–58KB,全部在表内可直接迁移

### 冗余/物理层
- `cache/parsed/`:161 个 JSON(105 arXiv 名 + 56 DOI 名)= 早期解析 dump,与 DB 部分重叠(差 12 条,含个别 DB 没有的条目)→ **importer 取并集**
- `data/pdfs/`:60 个 PDF(170MB)= **53 个 DOI 生物文献(基本齐全)** + 7 个 arXiv;**arXiv 批 PDF 基本散失**(DB pdfs 表 142 条指向文件不在盘);含 39.6MB 扫描件 `0901.0512v4.pdf`(2009 老 arXiv)

## 主题三群(全 149 篇)

| 群 | 构成 | 量级 | 与 wedge 关系 |
|---|---|---|---|
| 生物工艺/植物次生代谢 | DOI + local(CHO 细胞、CRISPR、Taxus、红花、萜类) | ~60 | 无关 → legacy 标签 |
| LLM 微调与科研自动化 | 2023+ arXiv(instruction mixing、RL、synthesis 自动化、eval) | ~47 | **相关**(开题/related-work 可用) |
| 老 arXiv 跨学科杂篇 | 2023 前 arXiv(蛋白结构、离子通道、物理) | ~42 | 无关 → legacy 标签 |

## importer 设计输入

1. 合并键 = arXiv ID / DOI / 文件哈希;三源(DB parsed_docs ∪ cache/parsed ∪ disk pdfs)去重,预期实体 **~160–170 篇**。
2. 主源 = DB markdown;PDF 不批量补下(grounding 用文本),arXiv/DOI 按需重下。
3. 元数据回填走 OpenAlex/arXiv API(真实标题/作者/被引/分类),本地关键词桶只做预分类。
4. **legacy 隔离**:生物工艺 ~60 + 老 arXiv ~42 打 `legacy` 标签或归档子库;wedge(开题/related-work)首库只激活 LLM 群 ~47 篇 + 用户自传新料——冷启动检索不脏。
5. 53 个 DOI PDF 决定:与当前 wedge 无关,PDF 先不补解析(文本已在 DB),归档即可。
