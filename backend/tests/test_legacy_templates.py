"""T6 item 4 — v4 related-work/outline templates archived (S24).

Verifies backend/cui/legacy_archive/templates.py:
(a) both ported families carry their v4 template text (key instructions and
    placeholders present);
(b) placeholder rendering works — format the constants, output contains the
    supplied arguments;
(c) what the module docstring declares absent (grant/proposal bodies) truly is
    absent from the module's exports.
"""

from cui.legacy_archive import templates

# --- (a) ported content is present ----------------------------------------


def test_related_work_template_content():
    t = templates.RELATED_WORK_PROMPT
    # stable v4 fragments (litscribe/prompts/templates.py RELATED_WORK_PROMPT)
    assert t.startswith(
        "You are an expert academic writer generating a Related Work section"
    )
    assert "## Your Paper's Context\n{user_instructions}" in t
    assert "## Papers to Position Against ({num_papers} papers):\n{papers}" in t
    assert (
        "1. ORGANIZE by methodological or conceptual groupings"
        " (not one paragraph per paper)" in t
    )
    assert "## Citation Checklist — EVERY paper below MUST be cited at least once:\n{citation_checklist}" in t
    assert "- Target approximately {word_count} words" in t
    assert t.endswith("Write the Related Work section now:")


def test_outline_template_content():
    t = templates.OUTLINE_PROMPT
    # stable v4 fragments (litscribe/tools/local_review.py OUTLINE_PROMPT,
    # Mode B: References → Outline + Gap Analysis)
    assert t.startswith(
        "You are an expert research strategist. Given these papers,"
        " suggest what literature review could be written."
    )
    assert "Papers ({num_papers}):\n{papers_summary}" in t
    assert "4. What topics are MISSING — what additional papers should be found?" in t
    assert '"proposed_outline": ["## Introduction", "## Theme 1: ...", ...],' in t
    assert '"gaps": ["Missing topic 1", "Missing topic 2"],' in t
    assert '"search_queries": ["query to find missing papers 1", "query 2"]' in t


# --- (b) placeholder rendering is usable -----------------------------------


def test_related_work_render():
    out = templates.RELATED_WORK_PROMPT.format(
        user_instructions="Submission to a software-engineering venue; we propose LLM-based test repair.",
        num_papers=3,
        papers="[lin2021] Lin et al. (2021). Repairing tests with LLMs.\n  Abstract text.",
        citation_checklist="- [lin2021] Lin et al. (2021). Repairing tests with LLMs.",
        word_count=900,
    )
    assert "we propose LLM-based test repair" in out
    assert "## Papers to Position Against (3 papers):" in out
    assert "Repairing tests with LLMs." in out
    assert "Target approximately 900 words" in out


def test_outline_render_preserves_json_literals():
    out = templates.OUTLINE_PROMPT.format(
        num_papers=2,
        papers_summary="[doi:10.1] Theme A summary.\n[doi:10.2] Theme B summary.",
    )
    assert "Papers (2):" in out
    assert "[doi:10.1] Theme A summary.\n[doi:10.2] Theme B summary." in out
    # {{ / }} escapes must collapse to literal JSON braces after formatting
    assert 'Output JSON:\n{\n  "suggested_question"' in out
    assert (
        '"themes": [{"name": "...", "papers": ["paper1", "paper2"],'
        ' "description": "..."}]' in out
    )
    assert '"gaps": ["Missing topic 1", "Missing topic 2"]' in out


# --- (c) doc-declared absences hold on the module surface ------------------


def test_exports_are_only_the_two_port_families():
    # grant/proposal/abstract/translation/rebuttal names never exported
    exported = {n for n in dir(templates) if not n.startswith("_")}
    assert exported == {"RELATED_WORK_PROMPT", "OUTLINE_PROMPT"}
    assert set(templates.__all__) == exported
    for unported in (
        "GRANT_BACKGROUND_PROMPT",
        "RESEARCH_PROPOSAL_PROMPT",
        "ABSTRACT_GENERATE_PROMPT",
        "ABSTRACT_REWRITE_PROMPT",
        "TRANSLATION_PROMPT",
        "REBUTTAL_PROMPT",
    ):
        assert not hasattr(templates, unported)


def test_grant_proposal_bodies_absent_from_exported_templates():
    # representative v4 body fragments of the unported families
    exported_text = "\n".join(
        getattr(templates, name) for name in templates.__all__
    )
    assert "crafting a research background section for a funding application" not in exported_text
    assert "funding application" not in exported_text
    assert "Generate a complete research proposal" not in exported_text
    assert "structured abstract following the IMRAD format" not in exported_text
    assert "point-by-point rebuttal to reviewer comments" not in exported_text
    assert "specializing in scholarly writing across languages" not in exported_text


def test_docstring_declares_port_scope():
    # the one-line design note for grant/proposal is documented (S24)
    assert "S24" in templates.__doc__
    assert "grant/proposal 模板未搬——S24 归档为设计笔记,不在主路" in templates.__doc__
    assert "RELATED_WORK_PROMPT" in templates.__doc__ and "OUTLINE_PROMPT" in templates.__doc__
