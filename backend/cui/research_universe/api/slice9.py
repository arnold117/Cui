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

import asyncio
import json
import re
from typing import Literal

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
    workspace_projection,
)
from cui.tools.v4_importer import first_title
from cui.research_universe.store.event_store import (
    CommandFingerprintConflict,
    ExpectedSequenceConflict,
    UniverseNotFound,
)

SYSTEM_LANDSCAPE_SUMMARY = """你是 Cui,和一个研究者一起梳理现状。用户选择了若干篇文献(每行以 locator 开头)。用中文输出两段 markdown:
## 这几篇覆盖了什么
逐篇一句话(带 locator),然后归纳共同覆盖的区域。
## 还没有被覆盖的
只陈述"未被这些文献覆盖/未被它们支持"的观察,不要建议研究课题、不要替用户下判断。
每篇文献标注了你能看到的范围:仅摘要的,不要断言摘要之外的细节。"""

SYSTEM_GAP_DRAFT = """你是 Cui 的 gap 起草助手。基于给定的研究问题(及研究者的 claim)与所选文献,起草一个 gap 候选。缺口必须相对这个研究问题来表述:文献里与问题无关的子话题不算缺口。只输出 JSON,键为:
coverage_statement(字符串:覆盖范围声明——哪些已被覆盖、缺口在哪,至少 10 字,不要说"所以你应该做 Y"),
search_query(字符串:可复现检索词),
counterexample_invitation(字符串:邀请反例的措辞)。
用中文。
每篇文献标注了你能看到的范围:仅摘要的,不要断言摘要之外的细节。"""

SYSTEM_RELATED_WORK = """你是 Cui 的 related-work 起草助手。基于现状梳理与已确认的 gap,写一段投稿 related-work 段落草稿(≤500 词,中文或与研究问题同语言),围绕给定的研究问题组织(而不是围绕文献各自的主题),客观陈述已有工作与缺口的边界,引用以 [locator] 标注,不要评价自己的工作。每篇文献标注了你能看到的范围:仅摘要的,不要断言摘要之外的细节。"""


SYSTEM_LITERATURE_SEARCH = """你是 Cui。基于研究者的问题(以及候选假设),从候选文献中挑出真正相关的最多 8 篇。对每篇给出:
- reason: 一句中文相关性理由;
- stance: 该文的主要观点/论证角度(2-3 句中文摘要,像人读书后转述);
- relation: {"kind": "supports" | "partial" | "opposes" | "background", "note": "它如何支持/反驳/仅仅背景式地联系我们的问题与假设(一句中文)"}。
只输出 JSON:
{"query": "实际建议的检索词", "results": [{"locator": "arxiv:... 或 doi:...", "reason": "...", "stance": "...", "relation": {"kind": "...", "note": "..."}}]}
只选与问题真正相关的;宁可少于 8 篇;探索性综述多给 1-2 篇边界相关的让研究者自己挑,比少给好;不要编造候选中不存在的 locator;locator 必须原样抄自候选列表。"""


class LiteratureChallengeCommand(Command):
    material_ids: list[str] = Field(default_factory=list)  # 可空:全选外部检索候选时只有 external_refs
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


class OrientationResponse(BaseModel):
    hypotheses: list[str]
    keywords: list[str]


class CandidateRelation(BaseModel):
    kind: Literal["supports", "partial", "opposes", "background"]
    note: str


class DialogueCandidate(BaseModel):
    material_id: str | None = None
    locator: str
    title: str
    reason: str
    source: str
    url: str | None = None
    excerpt: str
    stance: str
    relation: CandidateRelation


class LiteratureSearchResponse(BaseModel):
    query: str
    candidates: list[DialogueCandidate]


class CitationCheck(BaseModel):
    sentence: str
    locator: str
    verdict: Literal["supported", "unsupported", "not_selected"]
    # 核对者实际看到的范围;not_selected(引了没选的文献)没有可看的材料 → None
    scope: Literal["abstract", "excerpt", "full"] | None = None


class DraftTextResponse(BaseModel):
    text: str
    citation_check_status: Literal["ok", "unavailable"] = "ok"
    citation_checks: list[CitationCheck] = Field(default_factory=list)


class GapDraftResponse(BaseModel):
    coverage_statement: str
    search_query: str
    counterexample_invitation: str
    citation_check_status: Literal["ok", "unavailable"] = "ok"
    citation_checks: list[CitationCheck] = Field(default_factory=list)


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
        by_id[payload.material_id] = {"material_id": payload.material_id, "locator": payload.source_locator or payload.material_id, "title": first_title(payload.excerpt)[:80] if payload.excerpt else "", "excerpt": payload.excerpt, "content_scope": payload.content_scope}
    missing = set(material_ids) - set(by_id)
    if missing:
        raise HTTPException(404, f"material not in workspace nor corpus: {sorted(missing)[0]}")
    return [by_id[m] for m in material_ids]


def _drafting_context(store, universe_id: str, workspace_id: str, items: list[dict], *, with_claim: bool = True) -> tuple[str, str]:
    """三个起草端点共用:(锚, 材料行)。
    锚 = 研究问题(+最新 claim):不带它,LLM 只会顺着所选文献的主题漂移(#10);
    related-work 只锚问题(with_claim=False)——带 claim 时它会把文献按 claim 的结构掰弯、错配引用(Q2)。
    材料行带范围标注,让 LLM 知道自己手里只有摘要。"""
    ws = workspace_projection(store, universe_id, workspace_id)
    anchor = [f"研究问题:{ws['question']['text']}"]
    if with_claim and ws["claims"]:
        anchor.append(f"研究者的 claim:{ws['claims'][-1]['text']}")
    lines = []
    for i in items:
        excerpt = i.get("excerpt") or ""
        scope = "仅摘要" if i.get("content_scope") == "abstract" else ("全文,以下为开头摘录" if len(excerpt) > 1500 else "全文")
        lines.append(f"- [{i['locator']}] {i.get('title') or ''} (范围:{scope})\n  {excerpt[:1500]}")
    return "\n".join(anchor), "\n".join(lines)


def _chosen_items(store, universe_id: str, workspace_id: str, material_ids: list[str], external_refs: list[dict]) -> list[dict]:
    items = _selected_materials(store, universe_id, workspace_id, material_ids)
    for ref in external_refs:
        excerpt = (ref.get("excerpt") or "").strip()
        locator = (ref.get("locator") or "").strip()
        if not locator or not excerpt:
            raise HTTPException(422, "external_ref needs locator and excerpt")
        # 请求里临时带来的外部文献只有摘要
        items.append({"locator": locator, "title": "", "excerpt": excerpt, "url": ref.get("url"), "content_scope": "abstract"})
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


def _render_related_work_prompt(n_papers: int, papers: str, gaps_text: str) -> str:
    try:
        return RELATED_WORK_PROMPT.format(num_papers=str(n_papers), papers=papers, user_instructions=gaps_text)
    except (KeyError, IndexError, ValueError):
        return f"Write a related-work paragraph. Selected literature:\n{papers}\nConfirmed gaps:\n{gaps_text}\nObjective and [locator]-cited only."


SYSTEM_CITATION_CHECK = """你是引用核对员。下面给出若干 (句子, 文献) 对:句子里用 [locator] 引用了该文献。逐对判断:句子对该文献所作的断言,能否在给出的该文献文本中找到依据。
- supported=true:文本里有明确依据(转述也算);
- supported=false:文本里找不到依据,或与文本矛盾,或文本根本没谈到这件事。
只依据给出的文本判断,不要用你自己的背景知识替文献补充内容。只输出 JSON:
{"checks": [{"i": 1, "supported": true}, ...]}
每个 (句子, 文献) 对都必须有一条,i 为其编号。"""

CHECK_CHARS = 6000  # 核对者看的文本比起草时(1500)更长


def _citation_pairs(text: str) -> list[tuple[str, str]]:
    """(句子, 引用的 locator) 去重对。locator 不含空白;句子按句末标点/换行切。"""
    pairs: list[tuple[str, str]] = []
    for sentence in re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+|\n+", text):
        for loc in re.findall(r"\[([^\s\[\]]+)\]", sentence):
            if (sentence.strip(), loc) not in pairs:
                pairs.append((sentence.strip(), loc))
    return pairs


def _check_citations(llm, text: str, items: list[dict]) -> dict:
    """只标记,不改写不拦截;核对者调用失败/返回垃圾 → status=unavailable,草稿照常返回。"""
    pairs = _citation_pairs(text)
    by_loc = {_canonical_locator(i["locator"]): i for i in items}
    checks: list[dict] = []
    known: list[tuple[int, str, str, dict]] = []  # (checks 下标, 句子, locator, item)
    for sentence, loc in pairs:
        item = by_loc.get(_canonical_locator(loc))
        base = {"sentence": sentence[:240], "locator": loc}
        if item is None:
            checks.append({**base, "verdict": "not_selected", "scope": None})
        else:
            checks.append({**base, "verdict": "supported", "scope": None})
            known.append((len(checks) - 1, sentence, loc, item))
    if not known:
        return {"citation_check_status": "ok", "citation_checks": checks}
    seen: dict[str, dict] = {}
    for _, _, loc, item in known:
        seen.setdefault(_canonical_locator(loc), item)
    materials = "\n\n".join(f"### [{i['locator']}] {i.get('title') or ''}\n{(i.get('excerpt') or '')[:CHECK_CHARS]}" for i in seen.values())
    claims = "\n".join(f"{n}. 句子:{sentence}\n   引用:[{loc}]" for n, (_, sentence, loc, _) in enumerate(known, 1))
    try:
        data = llm.complete_json(SYSTEM_CITATION_CHECK, f"文献文本:\n{materials}\n\n待核对:\n{claims}")
        verdicts = {c["i"]: c["supported"] for c in data["checks"]}
        if any(not isinstance(verdicts.get(n), bool) for n in range(1, len(known) + 1)):
            raise ValueError("checker skipped or garbled a pair")
    except Exception:
        return {"citation_check_status": "unavailable", "citation_checks": [c for c in checks if c["verdict"] == "not_selected"]}
    for n, (idx, _, _, item) in enumerate(known, 1):
        excerpt = item.get("excerpt") or ""
        checks[idx]["scope"] = "abstract" if item.get("content_scope") == "abstract" else ("excerpt" if len(excerpt) > CHECK_CHARS else "full")
        checks[idx]["verdict"] = "supported" if verdicts[n] else "unsupported"
    return {"citation_check_status": "ok", "citation_checks": checks}


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

    @router.post("/workspaces/{workspace_id}/dialogue/orientation", response_model=OrientationResponse)
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

    @router.post("/workspaces/{workspace_id}/dialogue/literature-search", response_model=LiteratureSearchResponse)
    def literature_search(workspace_id: str, body: LiteratureSearchCommand):
        # sync def + asyncio.run: LLM client is synchronous, so an async handler
        # would freeze the whole event loop for every request (DeepSeek can take
        # 30s+). FastAPI runs sync handlers on the threadpool instead.
        universe_id = _universe_for_workspace(store, context, workspace_id)
        llm = _llm()
        from cui.research_universe.api.slice1 import _active
        query = (body.query or body.question)[:100]
        # 中文 query 先译成英文一次,同时用于语料检索与外部检索
        # (语料是英文 arXiv 群,中文检索词直接命中为 0)。
        translated_en = ""
        if re.search(r"[\u4e00-\u9fff]", query):
            try:
                translated = llm.complete_json(SYSTEM_QUERY_TRANSLATE, f"问题/关键词:{body.question or query}")
                candidate_en = (translated.get("query_en") if isinstance(translated, dict) else None) or ""
                if candidate_en.strip() and len(candidate_en) <= 200:
                    translated_en = candidate_en.strip()
            except Exception:
                pass
        corpus_query = translated_en or query
        external_query = translated_en or query
        ranked = ranked_corpus_hits(store, _active(store, context), "active", corpus_query, 10)
        pool: list[dict] = []
        seen: set[str] = set()
        for hit in ranked:
            pool.append({"locator": hit.source_locator, "title": hit.title, "excerpt": hit.snippet, "url": None, "source": "corpus", "material_id": hit.material_id})
            seen.add(hit.source_locator)
        if body.external:
            for ext in asyncio.run(external_search(external_query, per_source=6)):
                if ext["locator"] in seen:
                    continue
                seen.add(ext["locator"])
                pool.append({**ext, "source": ext["source"], "material_id": None})
        if not pool:
            return {"query": query, "candidates": []}
        candidate_lines = "\n".join(f"- [{c['locator']}] ({c['source']}) {c['title']}" for c in pool)
        prompt_context = f"问题:{body.question}"
        if translated_en and translated_en != query:
            prompt_context += f"\n(中文检索词已译为英文执行:{translated_en})"
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
            if len(picks) >= 8:
                break
        return {"query": (text.get("query") if isinstance(text, dict) else None) or query, "candidates": picks}

    def _llm():
        if client is None:
            raise HTTPException(503, "LLM client not configured in this app")
        return client

    @router.post("/workspaces/{workspace_id}/dialogue/landscape-summary", response_model=DraftTextResponse)
    def landscape_summary(workspace_id: str, body: MaterialSelectionCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        items = _chosen_items(store, universe_id, workspace_id, body.material_ids, [r.model_dump() for r in body.external_refs])
        llm = _llm()
        try:
            anchor, lines = _drafting_context(store, universe_id, workspace_id, items)
            text = llm.complete(SYSTEM_LANDSCAPE_SUMMARY, f"{anchor}\n所选文献:\n{lines}")
            return {"text": text, **_check_citations(llm, text, items)}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"landscape summary failed: {exc}") from exc

    @router.post("/workspaces/{workspace_id}/dialogue/gap-draft", response_model=GapDraftResponse)
    def gap_draft(workspace_id: str, body: MaterialSelectionCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        items = _chosen_items(store, universe_id, workspace_id, body.material_ids, [r.model_dump() for r in body.external_refs])
        llm = _llm()
        try:
            anchor, lines = _drafting_context(store, universe_id, workspace_id, items)
            text = llm.complete(SYSTEM_GAP_DRAFT, f"{anchor}\n所选文献:\n{lines}")
            draft = _parse_draft_json(text)
            return {**draft, **_check_citations(llm, draft["coverage_statement"], items)}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"gap draft failed: {exc}") from exc

    @router.post("/workspaces/{workspace_id}/dialogue/related-work-draft", response_model=DraftTextResponse)
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
        anchor, lines = _drafting_context(store, universe_id, workspace_id, items, with_claim=False)
        prompt = _render_related_work_prompt(len(items), lines, f"{anchor}\n已确认的 gap:{gaps_text}")
        try:
            text = llm.complete(SYSTEM_RELATED_WORK, prompt)
            return {"text": text, **_check_citations(llm, text, items)}
        except Exception as exc:
            raise HTTPException(502, f"related-work draft failed: {exc}") from exc

    return router
