"""Dependency-free stand-in for the v4 ``Paper`` model (T6 item 3 port).

v4 (LitScribe) fed its pydantic model ``litscribe.models.paper.Paper`` into the
exporters. The legacy archive must not depend on v4 internals (``models`` is
out of scope — 数据债注记: 只搬纯逻辑, 不搬模型/表结构), so the ported
formatters read this plain ``PaperLike`` dataclass instead: same field names,
types and default semantics as v4's ``Paper``, minus the fields the formatters
never touch (``citations``, ``pdf_urls``, ``relevance_score``,
``completeness_score``).

Mirrors the package idiom already used by ``cui.legacy_archive.search``
("neutral paper-like data, mapped at the boundary"): slice1/callers map their
own record shape onto ``PaperLike`` before calling the formatters.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PaperLike:
    """Plain immutable shape the v4 exporters read off a ``Paper``.

    Field order/types/defaults mirror v4's pydantic model
    (``litscribe/models/paper.py``): ``venue``/``doi`` default to "" and
    ``sources`` to {} exactly like there — the formatters only ever do
    ``sources.get("arxiv")`` and truthiness checks, so absent data degrades
    identically to v4 (e.g. no year -> "n.d.", no DOI -> arXiv link when the
    arxiv source is present).
    """

    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    year: int
    sources: dict[str, str] = field(default_factory=dict)
    venue: str = ""
    doi: str = ""
