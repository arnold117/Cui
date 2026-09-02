"""v4 写作模板收编 — related-work + outline 两族产物形状模板(S24,plan T6 item 4)。

来源(v4 = LitScribe,2026-06-11 快照 027583c):
- related-work 族 = ``litscribe/prompts/templates.py`` 的 ``RELATED_WORK_PROMPT``
  (v4 writing-mode id ``related-work``)。
- outline 族:v4 的 ``prompts/templates.py`` 里没有 outline 模板 —— 两族里只有
  related-work 在该文件。v4 的 outline 产物形状在 ``litscribe/tools/local_review.py``
  Mode B "References → Outline + Gap Analysis"(supervisor ``suggest_review_outline`` /
  ``/api/outline`` / CLI ``outline``),即 ``OUTLINE_PROMPT``;一并按 S24 收编。

按 spec S24(见 docs/spec-v5-merge.md):related-work + outline 进第一刀产物形状插件,
slice1 用。模板正文逐字搬入(字符串常量 + 原样占位符);已去掉对 v4 内部模块的一切
import —— 本模块是纯字符串归档:零 import、零依赖,kernel 契约不受影响。

未搬模板族:
- grant/proposal 模板未搬——S24 归档为设计笔记,不在主路。
- abstract 族(abstract-generate/abstract-rewrite)未搬——S24 归 DOC 形状族候补。
- translation/rebuttal 未搬——S24 不进主路。
"""

__all__ = ["RELATED_WORK_PROMPT", "OUTLINE_PROMPT"]

# v4 原文:litscribe/prompts/templates.py ``RELATED_WORK_PROMPT``
# (writing mode "related-work" · Related Work · 相关工作)。
RELATED_WORK_PROMPT = """You are an expert academic writer generating a Related Work section for a research paper.

## Your Paper's Context
{user_instructions}

## Papers to Position Against ({num_papers} papers):
{papers}

Write a Related Work section that:

1. ORGANIZE by methodological or conceptual groupings (not one paragraph per paper)
   - Group related papers into coherent subsections
   - Each group should represent a distinct approach, technique, or research thread

2. POSITION the user's work relative to existing literature
   - For each group, clearly explain how the user's approach differs
   - Highlight what existing methods lack that the user's work addresses
   - Use contrastive language: "Unlike [Author, Year] who..., our approach..."
   - End each subsection with a sentence connecting back to the user's contribution

3. MAINTAIN academic objectivity
   - Acknowledge strengths of prior work before noting limitations
   - Use fair characterizations — do not strawman other methods
   - Be specific about differences (not just "our method is better")

## Citation Checklist — EVERY paper below MUST be cited at least once:
{citation_checklist}

Requirements:
- CITATION FORMAT: Use [LastName, Year] or [LastName et al., Year] with exact author surnames from the papers above. Every citation MUST include the year.
- CITATION COVERAGE: Cite ALL {num_papers} papers at least once. If a paper is peripheral, use "see also [Author, Year]" or "consistent with findings in [Author, Year]".
- CITATION DENSITY: Every factual claim about prior work MUST include a citation.
- STRUCTURE: Use ## Related Work as the top heading. Use ### for subsections. Do NOT number sections.
- Write in formal academic prose
- Target approximately {word_count} words
- The final paragraph should summarize the gap your work fills

Write the Related Work section now:"""

# v4 原文:litscribe/tools/local_review.py ``OUTLINE_PROMPT``
# (Mode B: References → Outline + Gap Analysis;suggest_review_outline)。
# 注意正文里的 {{ / }} 是 v4 原样保留的 .format 转义 —— 渲染后变成字面 { / }。
OUTLINE_PROMPT = """You are an expert research strategist. Given these papers, suggest what literature review could be written.

Papers ({num_papers}):
{papers_summary}

Analyze:
1. What common themes emerge?
2. What research question could these papers answer?
3. What's a good structure for a review?
4. What topics are MISSING — what additional papers should be found?

Output JSON:
{{
  "suggested_question": "The research question these papers best address",
  "themes": [{{"name": "...", "papers": ["paper1", "paper2"], "description": "..."}}],
  "proposed_outline": ["## Introduction", "## Theme 1: ...", ...],
  "gaps": ["Missing topic 1", "Missing topic 2"],
  "search_queries": ["query to find missing papers 1", "query 2"]
}}"""
