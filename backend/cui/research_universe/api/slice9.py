"""slice1 second cut — literature dialogue surface (wedge demo).

Two kinds of surface:
  - ``literature-challenges``: the durable one — an explicit user command that
    adds a literature-grounded challenge to a review round (events, trajectory).
  - transient endpoints (landscape summary / agent gap draft / related-work
    draft): conversation helpers that call the LLM directly and store nothing
    (S6: only verdicts/confirmations enter the trajectory; drafts are export
    forms, S19).

Transient endpoints need an injected ``client`` (``None`` in test apps).
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from cui.legacy_archive.templates import RELATED_WORK_PROMPT
from cui.research_universe.api.routes import LibraryContext, LocalPrincipal
from cui.research_universe.api.slice7 import ranked_corpus_hits
from cui.research_universe.dialogue_sources import external_search
from cui.research_universe.api.slice1 import Command, CommandResponse, _active, _universe_for_round, _universe_for_workspace
from cui.research_universe.application import (
    BoundaryViolation,
    ChallengeGenerationFailed,
    NotFound,
    Slice1Service,
    review_round_projection,
)
from cui.research_universe.store.event_store import (
    CommandFingerprintConflict,
    ExpectedSequenceConflict,
    UniverseNotFound,
)

SYSTEM_LANDSCAPE_SUMMARY = """你是 Cui,和一个研究者一起梳理现状。用户选择了若干篇文献(每行以 locator 开头)。用中文输出两段 markdown:
## 这几篇覆盖了什么
逐篇一句话(带 locator),然后归纳共同覆盖的区域。
## 还没有被覆盖的
只陈述"未被这些文献覆盖/未被它们支持"的观察,不要建议研究课题、不要替用户下判断。"""

SYSTEM_GAP_DRAFT = """你是 Cui 的 gap 起草助手。基于给定的问题方向与所选文献,起草一个 gap 候选,只输出 JSON,键为:
coverage_statement(字符串:覆盖范围声明——哪些已被覆盖、缺口在哪,至少 10 字,不要说"所以你应该做 Y"),
search_query(字符串:可复现检索词),
counterexample_invitation(字符串:邀请反例的措辞)。
用中文。"""

SYSTEM_RELATED_WORK = """你是 Cui 的 related-work 起草助手。基于现状梳理与已确认的 gap,写一段投稿 related-work 段落草稿(≤500 词,中文或与 claim 同语言),客观陈述已有工作与缺口的边界,引用以 [locator] 标注,不要评价自己的工作。"""


SYSTEM_LITERATURE_SEARCH = """你是 Cui。基于研究者的问题(以及候选假设),从候选文献中挑出真正相关的最多 6 篇。对每篇给出:
- reason: 一句中文相关性理由;
- stance: 该文的主要观点/论证角度(2-3 句中文摘要,像人读书后转述);
- relation: {"kind": "supports" | "partial" | "opposes" | "background", "note": "它如何支持/反驳/仅仅背景式地联系我们的问题与假设(一句中文)"}。
只输出 JSON:
{"query": "实际建议的检索词", "results": [{"locator": "arxiv:... 或 doi:...", "reason": "...", "stance": "...", "relation": {"kind": "...", "note": "..."}}]}
只选与问题真正相关的;宁可少于 6 篇;不要编造候选中不存在的 locator;locator 必须原样抄自候选列表。"""


class LiteratureChallengeCommand(Command):
    material_ids: list[str] = Field(min_length=1)
    external_refs: list[ExternalRef] = Field(default_factory=list)


SYSTEM_QUERY_TRANSLATE = """你是学术检索助手。把下面的中文问题/关键词改写成 1-2 个用于英文文献库(arXiv/OpenAlex)检索的学术关键词短语。只输出 JSON: {"query_en": "..."}。"""


SYSTEM_ORIENTATION = """你是 Cui 的研究起点助手。面对一个全新的研究问题,先帮研究者做正向准备。只输出 JSON:
{"hypotheses": ["3-5 条候选假设,每条是完整的可检验陈述,中文"], "keywords": ["8-12 条检索关键词或短语(中文/英文均可),用于语料检索"]}
不要替用户下结论;假设是候选,不是定见。"""


class OrientationCommand(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ExternalRef(BaseModel):
    locator: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(min_length=1)
    url: str | None = None


class LiteratureSearchCommand(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    query: str | None = None
    external: bool = True

class MaterialSelectionCommand(BaseModel):
    material_ids: list[str] = Field(default_factory=list)
    external_refs: list[ExternalRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _nonempty(self) -> "MaterialSelectionCommand":
        if not self.material_ids and not self.external_refs:
            raise ValueError("at least one material_id or external_ref is required")
        return self


class RelatedWorkDraftCommand(MaterialSelectionCommand):
    gap_ids: list[str] = Field(default_factory=list)


def _selected_materials(store, universe_id: str, workspace_id: str, material_ids: list[str]) -> list[dict]:
    """Materials for a dialogue turn: anything in the dialogue workspace plus
    the shared corpus workspaces (the corpus is library-wide; transient reads
    never mutate it)."""
    from cui.research_universe.corpus import corpus_workspace_ids
    allowed = {workspace_id} | corpus_workspace_ids()
    by_id: dict[str, dict] = {}
    for event in store.read_events(universe_id):
        if event.event_type != "material_added":
            continue
        payload = event.validated_payload()
        if payload.workspace_id not in allowed:
            continue
        by_id[payload.material_id] = {"material_id": payload.material_id, "locator": payload.source_locator or payload.material_id, "title": payload.excerpt.splitlines()[0][:80] if payload.excerpt else "", "excerpt": payload.excerpt}
    missing = set(material_ids) - set(by_id)
    if missing:
        raise HTTPException(404, f"material not in workspace nor corpus: {sorted(missing)[0]}")
    return [by_id[m] for m in material_ids]


def _item_lines(items: list[dict]) -> str:
    return "\n".join(f"- [{i['locator']}] {i.get('title') or ''}\n  {(i.get('excerpt') or '')[:1500]}" for i in items)


def _chosen_items(store, universe_id: str, workspace_id: str, material_ids: list[str], external_refs: list[dict]) -> list[dict]:
    items = _selected_materials(store, universe_id, workspace_id, material_ids)
    for ref in external_refs:
        excerpt = (ref.get("excerpt") or "").strip()
        locator = (ref.get("locator") or "").strip()
        if not locator or not excerpt:
            raise HTTPException(422, "external_ref needs locator and excerpt")
        items.append({"locator": locator, "title": "", "excerpt": excerpt[:1500], "url": ref.get("url"), "external": True})
    if not items:
        raise HTTPException(422, "no material or external literature selected")
    return items


def _canonical_locator(raw: str) -> str:
    """Tolerant normalisation for LLM-returned locators (URLs / prefixes / case)."""
    value = (raw or "").strip().lower()
    import re as _re
    m = _re.match(r"^(?:https?://)?(?:dx\.)?doi\.org/(.+)$", value)
    if m:
        value = m.group(1)
    if _re.match(r"^10\.", value):
        return "doi:" + value
    m = _re.search(r"arxiv\.org/abs/([^/?#]+)", value)
    if m:
        value = _re.sub(r"v\d+$", "", m.group(1))
        return "arxiv:" + value
    if value.startswith("arxiv:"):
        return "arxiv:" + _re.sub(r"v\d+$", "", value[len("arxiv:"):])
    m = _re.search(r"openalex\.org/works/(w\d+)", value)
    if m:
        return "openalex:" + m.group(1)
    if value.startswith("doi:"):
        return value
    if value.startswith("openalex:"):
        return value
    return value


def _parse_draft_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise HTTPException(502, "gap draft did not return JSON")
    data = json.loads(match.group(0))
    for key in ("coverage_statement", "search_query", "counterexample_invitation"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise HTTPException(502, f"gap draft missing field: {key}")
    return data


def _render_related_work_prompt(materials: list[dict], gaps_text: str) -> str:
    papers = "\n".join(f"- [{m['locator']}] {m['title']}" for m in materials)
    try:
        return RELATED_WORK_PROMPT.format(num_papers=str(len(materials)), papers=papers, user_instructions=gaps_text)
    except (KeyError, IndexError, ValueError):
        return f"Write a related-work paragraph. Selected literature:\n{papers}\nConfirmed gaps:\n{gaps_text}\nObjective and [locator]-cited only."


def create_dialogue_router(service: Slice1Service, store, context: LibraryContext, principal: LocalPrincipal, client=None) -> APIRouter:
    router = APIRouter(tags=["research-universe-dialogue"])

    def fail(exc):
        if isinstance(exc, (ExpectedSequenceConflict, CommandFingerprintConflict, BoundaryViolation)):
            raise HTTPException(409, str(exc))
        if isinstance(exc, (NotFound, UniverseNotFound)):
            raise HTTPException(404, str(exc))
        if isinstance(exc, ChallengeGenerationFailed):
            raise HTTPException(502, str(exc))
        raise exc

    @router.post("/review-rounds/{round_id}/literature-challenges", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def literature_challenge(round_id: str, body: LiteratureChallengeCommand):
        universe_id = _universe_for_round(store, context, round_id)
        try:
            result = service.generate_literature_challenge(universe_id, round_id, body.material_ids, body.command_id, body.expected_sequence, externals=[{"locator": r.locator, "excerpt": r.excerpt, "url": r.url} for r in body.external_refs])
            return CommandResponse(commit_position=result.commit_position, event_ids=result.event_ids, result=result.result_payload, fragment=review_round_projection(store, universe_id, round_id))
        except Exception as exc:
            fail(exc)

    @router.post("/workspaces/{workspace_id}/dialogue/orientation")
    def orientation(workspace_id: str, body: OrientationCommand):
        """Fresh-question gate (product journey §0/§1): candidate hypotheses +
        search keywords for a brand-new question. Transient; nothing stored."""
        llm = _llm()
        try:
            text = llm.complete_json(SYSTEM_ORIENTATION, f"全新研究问题:\n{body.question}")
        except Exception as exc:
            raise HTTPException(502, f"orientation failed: {exc}") from exc
        hypotheses = [str(h) for h in (text.get("hypotheses") or []) if isinstance(h, str) and h.strip()][:5]
        keywords = [str(k) for k in (text.get("keywords") or []) if isinstance(k, str) and k.strip()][:12]
        if not hypotheses or not keywords:
            raise HTTPException(502, "orientation returned no usable hypotheses/keywords")
        return {"hypotheses": hypotheses, "keywords": keywords}

    @router.post("/workspaces/{workspace_id}/dialogue/literature-search")
    async def literature_search(workspace_id: str, body: LiteratureSearchCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        llm = _llm()
        from cui.research_universe.api.slice1 import _active
        query = (body.query or body.question)[:100]
        ranked = ranked_corpus_hits(store, _active(store, context), "active", query, 8)
        pool: list[dict] = []
        seen: set[str] = set()
        for hit in ranked:
            pool.append({"locator": hit.source_locator, "title": hit.title, "excerpt": hit.snippet, "url": None, "source": "corpus", "material_id": hit.material_id})
            seen.add(hit.source_locator)
        if body.external:
            external_query = query
            if re.search(r"[\u4e00-\u9fff]", query):
                try:
                    translated = llm.complete_json(SYSTEM_QUERY_TRANSLATE, f"问题/关键词:{body.question or query}")
                    candidate_en = (translated.get("query_en") if isinstance(translated, dict) else None) or ""
                    if candidate_en.strip() and len(candidate_en) <= 200:
                        external_query = candidate_en.strip()
                except Exception:
                    pass
            for ext in await external_search(external_query, per_source=5):
                if ext["locator"] in seen:
                    continue
                seen.add(ext["locator"])
                pool.append({**ext, "source": ext["source"], "material_id": None})
        if not pool:
            return {"query": query, "candidates": []}
        candidate_lines = "\n".join(f"- [{c['locator']}] ({c['source']}) {c['title']}" for c in pool)
        prompt_context = f"问题:{body.question}" + (f"\n(外部检索词:{external_query})" if body.external and external_query != query else "")
        try:
            text = llm.complete_json(SYSTEM_LITERATURE_SEARCH, f"{prompt_context}\n候选文献:\n{candidate_lines}")
        except Exception as exc:
            raise HTTPException(502, f"literature search reasoning failed: {exc}") from exc
        allowed = {c["locator"]: c for c in pool}
        picks = []
        for item in (text.get("results") or []) if isinstance(text, dict) else []:
            raw = item.get("locator") if isinstance(item, dict) else None
            hit = allowed.get(_canonical_locator(raw)) if raw else None
            if hit is not None:
                relation = item.get("relation") if isinstance(item, dict) else None
                relation = relation if isinstance(relation, dict) else {}
                kind = relation.get("kind") if relation.get("kind") in ("supports", "partial", "opposes", "background") else None
                picks.append({
                    "material_id": hit.get("material_id"), "locator": hit["locator"], "title": hit["title"],
                    "source": hit.get("source") or "external", "url": hit.get("url"),
                    "excerpt": (hit.get("excerpt") or "")[:1500],
                    "reason": (item.get("reason") or "")[:240],
                    "stance": (item.get("stance") or "")[:600],
                    "relation": {"kind": kind or "background", "note": (relation.get("note") or "")[:240]},
                })
            if len(picks) >= 6:
                break
        return {"query": (text.get("query") if isinstance(text, dict) else None) or query, "candidates": picks}

    def _llm():
        if client is None:
            raise HTTPException(503, "LLM client not configured in this app")
        return client

    @router.post("/workspaces/{workspace_id}/dialogue/landscape-summary")
    def landscape_summary(workspace_id: str, body: MaterialSelectionCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        items = _chosen_items(store, universe_id, workspace_id, body.material_ids, [r.model_dump() for r in body.external_refs])
        llm = _llm()
        try:
            user = _item_lines(items)
            text = llm.complete(SYSTEM_LANDSCAPE_SUMMARY, f"问题方向:{workspace_id}\n所选文献:\n{user}")
            return {"text": text}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"landscape summary failed: {exc}") from exc

    @router.post("/workspaces/{workspace_id}/dialogue/gap-draft")
    def gap_draft(workspace_id: str, body: MaterialSelectionCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        items = _chosen_items(store, universe_id, workspace_id, body.material_ids, [r.model_dump() for r in body.external_refs])
        llm = _llm()
        try:
            user = _item_lines(items)
            text = llm.complete(SYSTEM_GAP_DRAFT, f"所选文献:\n{user}")
            return _parse_draft_json(text)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"gap draft failed: {exc}") from exc

    @router.post("/workspaces/{workspace_id}/dialogue/related-work-draft")
    def related_work_draft(workspace_id: str, body: RelatedWorkDraftCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        items = _chosen_items(store, universe_id, workspace_id, body.material_ids, [r.model_dump() for r in body.external_refs])
        llm = _llm()
        gaps_text = ""
        try:
            from cui.research_universe.application import _gap_candidate_states
            for state in _gap_candidate_states(store.read_events(universe_id)).values():
                if state["workspace_id"] == workspace_id and state["status"] in ("confirmed", "corrected"):
                    gaps_text += f"\n- {state['coverage_statement']}"
        except Exception:
            pass
        prompt = _render_related_work_prompt(items, gaps_text)
        try:
            text = llm.complete(SYSTEM_RELATED_WORK, prompt)
            return {"text": text}
        except Exception as exc:
            raise HTTPException(502, f"related-work draft failed: {exc}") from exc

    return router
