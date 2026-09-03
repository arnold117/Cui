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
from pydantic import BaseModel, Field

from cui.legacy_archive.templates import RELATED_WORK_PROMPT
from cui.research_universe.api.routes import LibraryContext, LocalPrincipal
from cui.research_universe.api.slice7 import ranked_corpus_hits
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


SYSTEM_LITERATURE_SEARCH = """你是 Cui。基于研究者的问题,从候选文献中挑出真正相关的最多 6 篇,并为每篇写一句中文的相关性理由。只输出 JSON:
{"query": "实际建议的检索词", "results": [{"locator": "arxiv:... 或 doi:...", "reason": "一句理由"}]}
只选与问题真正相关的;宁可少于 6 篇;不要编造候选中不存在的 locator。"""


class LiteratureChallengeCommand(Command):
    material_ids: list[str] = Field(min_length=1)


class LiteratureSearchCommand(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    query: str | None = None

class MaterialSelectionCommand(BaseModel):
    material_ids: list[str] = Field(min_length=1)


class RelatedWorkDraftCommand(BaseModel):
    material_ids: list[str] = Field(min_length=1)
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
            result = service.generate_literature_challenge(universe_id, round_id, body.material_ids, body.command_id, body.expected_sequence)
            return CommandResponse(commit_position=result.commit_position, event_ids=result.event_ids, result=result.result_payload, fragment=review_round_projection(store, universe_id, round_id))
        except Exception as exc:
            fail(exc)

    @router.post("/workspaces/{workspace_id}/dialogue/literature-search")
    def literature_search(workspace_id: str, body: LiteratureSearchCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        llm = _llm()
        from cui.research_universe.api.slice1 import _active
        ranked = ranked_corpus_hits(store, _active(store, context), "active", (body.query or body.question)[:100], 12)
        if not ranked:
            return {"query": body.query or body.question, "candidates": []}
        candidate_lines = "\n".join(f"- [{h.source_locator}] {h.title}" for h in ranked)
        try:
            text = llm.complete_json(SYSTEM_LITERATURE_SEARCH, f"问题:{body.question}\n候选文献:\n{candidate_lines}")
        except Exception as exc:
            raise HTTPException(502, f"literature search reasoning failed: {exc}") from exc
        allowed = {h.source_locator for h in ranked}
        picks = []
        for item in (text.get("results") or []) if isinstance(text, dict) else []:
            locator = item.get("locator") if isinstance(item, dict) else None
            if locator in allowed:
                hit = next(h for h in ranked if h.source_locator == locator)
                picks.append({"material_id": hit.material_id, "locator": locator, "title": hit.title, "reason": (item.get("reason") or "")[:200]})
            if len(picks) >= 6:
                break
        return {"query": (text.get("query") if isinstance(text, dict) else None) or body.query or body.question, "candidates": picks}

    def _llm():
        if client is None:
            raise HTTPException(503, "LLM client not configured in this app")
        return client

    @router.post("/workspaces/{workspace_id}/dialogue/landscape-summary")
    def landscape_summary(workspace_id: str, body: MaterialSelectionCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        materials = _selected_materials(store, universe_id, workspace_id, body.material_ids)
        llm = _llm()
        try:
            user = "\n".join(f"- [{m['locator']}] {m['excerpt'][:1500]}" for m in materials)
            text = llm.complete(SYSTEM_LANDSCAPE_SUMMARY, f"问题方向:{workspace_id}\n所选文献:\n{user}")
            return {"text": text}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"landscape summary failed: {exc}") from exc

    @router.post("/workspaces/{workspace_id}/dialogue/gap-draft")
    def gap_draft(workspace_id: str, body: MaterialSelectionCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        materials = _selected_materials(store, universe_id, workspace_id, body.material_ids)
        llm = _llm()
        try:
            user = "\n".join(f"- [{m['locator']}] {m['excerpt'][:1500]}" for m in materials)
            text = llm.complete(SYSTEM_GAP_DRAFT, f"所选文献:\n{user}")
            return _parse_draft_json(text)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"gap draft failed: {exc}") from exc

    @router.post("/workspaces/{workspace_id}/dialogue/related-work-draft")
    def related_work_draft(workspace_id: str, body: RelatedWorkDraftCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        materials = _selected_materials(store, universe_id, workspace_id, body.material_ids)
        llm = _llm()
        gaps_text = ""
        try:
            from cui.research_universe.application import _gap_candidate_states
            for state in _gap_candidate_states(store.read_events(universe_id)).values():
                if state["workspace_id"] == workspace_id and state["status"] in ("confirmed", "corrected"):
                    gaps_text += f"\n- {state['coverage_statement']}"
        except Exception:
            pass
        prompt = _render_related_work_prompt(materials, gaps_text)
        try:
            text = llm.complete(SYSTEM_RELATED_WORK, prompt)
            return {"text": text}
        except Exception as exc:
            raise HTTPException(502, f"related-work draft failed: {exc}") from exc

    return router
