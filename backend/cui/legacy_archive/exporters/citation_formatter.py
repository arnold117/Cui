"""Citation formatters — ported from v4 ``litscribe/exporters/citation_formatter.py``.

Cherry-picked verbatim into the legacy archive (T6 item 3; 产物导出, slice1
用). Pure string construction for multiple academic styles:
- APA 7th Edition
- MLA 9th Edition
- IEEE
- Chicago (Author-Date)
- GB/T 7714-2015 (Chinese national standard)

Input type substitution: v4 took its pydantic ``litscribe.models.paper.Paper``;
here functions take the same-shaped plain ``PaperLike`` (see ``paper_like.py``)
so the module stays dependency-free. Function bodies are v4-verbatim.

未搬清单 (not ported):
- 无 —— 本模块全部为纯格式化逻辑 (作者串 + 单条/多条引文), 逐函数搬入。
  仅输入类型 ``Paper`` → ``PaperLike`` 一处适配。
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from cui.legacy_archive.exporters.paper_like import PaperLike


class CitationStyle(Enum):
    """Supported citation styles."""

    APA = "apa"
    MLA = "mla"
    IEEE = "ieee"
    CHICAGO = "chicago"
    GB_T_7714 = "gbt7714"  # Chinese national standard


def format_authors_apa(authors: List[str], max_authors: int = 20) -> str:
    """Format authors in APA style.

    Rules:
    - Up to 20 authors: list all
    - 21+ authors: first 19, ..., last author
    """
    if not authors:
        return ""

    def format_name(name: str) -> str:
        name = name.strip()
        if "," in name:
            parts = name.split(",")
            last = parts[0].strip()
            first = parts[1].strip() if len(parts) > 1 else ""
            initials = ". ".join(w[0].upper() for w in first.split() if w)
            return f"{last}, {initials}." if initials else last
        else:
            parts = name.split()
            if len(parts) == 1:
                return parts[0]
            last = parts[-1]
            initials = ". ".join(w[0].upper() for w in parts[:-1] if w)
            return f"{last}, {initials}." if initials else last

    formatted = [format_name(a) for a in authors]

    if len(formatted) == 1:
        return formatted[0]
    elif len(formatted) == 2:
        return f"{formatted[0]}, & {formatted[1]}"
    elif len(formatted) <= max_authors:
        return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"
    else:
        return ", ".join(formatted[:19]) + ", ... " + formatted[-1]


def format_authors_mla(authors: List[str]) -> str:
    """Format authors in MLA style.

    Rules:
    - 1 author: Last, First.
    - 2 authors: Last, First, and First Last.
    - 3+ authors: Last, First, et al.
    """
    if not authors:
        return ""

    def format_first(name: str) -> str:
        name = name.strip()
        if "," in name:
            return name
        parts = name.split()
        if len(parts) == 1:
            return parts[0]
        return f"{parts[-1]}, {' '.join(parts[:-1])}"

    def format_other(name: str) -> str:
        name = name.strip()
        if "," not in name:
            return name
        parts = name.split(",")
        return f"{parts[1].strip()} {parts[0].strip()}"

    if len(authors) == 1:
        return format_first(authors[0])
    elif len(authors) == 2:
        return f"{format_first(authors[0])}, and {format_other(authors[1])}"
    else:
        return f"{format_first(authors[0])}, et al."


def format_authors_ieee(authors: List[str]) -> str:
    """Format authors in IEEE style.

    Format: F. Last, F. M. Last, and F. Last
    """
    if not authors:
        return ""

    def format_name(name: str) -> str:
        name = name.strip()
        if "," in name:
            parts = name.split(",")
            last = parts[0].strip()
            first = parts[1].strip() if len(parts) > 1 else ""
            initials = " ".join(w[0].upper() + "." for w in first.split() if w)
            return f"{initials} {last}" if initials else last
        else:
            parts = name.split()
            if len(parts) == 1:
                return parts[0]
            last = parts[-1]
            initials = " ".join(w[0].upper() + "." for w in parts[:-1] if w)
            return f"{initials} {last}" if initials else last

    formatted = [format_name(a) for a in authors]

    if len(formatted) == 1:
        return formatted[0]
    elif len(formatted) == 2:
        return f"{formatted[0]} and {formatted[1]}"
    else:
        return ", ".join(formatted[:-1]) + ", and " + formatted[-1]


def format_authors_chicago(authors: List[str]) -> str:
    """Format authors in Chicago style (Author-Date).

    Rules:
    - 1 author: Last, First
    - 2-3 authors: Last, First, First Last, and First Last
    - 4+ authors: Last, First, et al.
    """
    if not authors:
        return ""

    def format_first(name: str) -> str:
        name = name.strip()
        if "," in name:
            return name
        parts = name.split()
        if len(parts) == 1:
            return parts[0]
        return f"{parts[-1]}, {' '.join(parts[:-1])}"

    def format_other(name: str) -> str:
        name = name.strip()
        if "," not in name:
            return name
        parts = name.split(",")
        return f"{parts[1].strip()} {parts[0].strip()}"

    if len(authors) == 1:
        return format_first(authors[0])
    elif len(authors) <= 3:
        result = format_first(authors[0])
        for i, a in enumerate(authors[1:], 1):
            if i == len(authors) - 1:
                result += f", and {format_other(a)}"
            else:
                result += f", {format_other(a)}"
        return result
    else:
        return f"{format_first(authors[0])}, et al."


def format_authors_gbt7714(authors: List[str], max_authors: int = 3) -> str:
    """Format authors in GB/T 7714-2015 style (Chinese standard).

    Rules:
    - Up to 3 authors: list all, separated by commas
    - 4+ authors: first 3, 等 (et al.)
    """
    if not authors:
        return ""

    if len(authors) <= max_authors:
        return ", ".join(authors)
    else:
        return ", ".join(authors[:max_authors]) + ", 等"


def format_citation(paper: PaperLike, style: CitationStyle = CitationStyle.APA) -> str:
    """Format a single paper as a citation string.

    Args:
        paper: Paper-like object (see ``paper_like.py``)
        style: Citation style to use

    Returns:
        Formatted citation string
    """
    if style == CitationStyle.APA:
        return _format_apa(paper)
    elif style == CitationStyle.MLA:
        return _format_mla(paper)
    elif style == CitationStyle.IEEE:
        return _format_ieee(paper)
    elif style == CitationStyle.CHICAGO:
        return _format_chicago(paper)
    elif style == CitationStyle.GB_T_7714:
        return _format_gbt7714(paper)
    else:
        return _format_apa(paper)


def format_citations(
    papers: list[PaperLike],
    style: CitationStyle = CitationStyle.APA,
) -> list[str]:
    """Format multiple papers as citation strings.

    Args:
        papers: List of paper-like objects (see ``paper_like.py``)
        style: Citation style to use

    Returns:
        List of formatted citation strings
    """
    numbered_styles = {CitationStyle.IEEE, CitationStyle.GB_T_7714}
    result = []
    for i, paper in enumerate(papers, 1):
        if style == CitationStyle.IEEE:
            result.append(_format_ieee(paper, index=i))
        elif style == CitationStyle.GB_T_7714:
            result.append(_format_gbt7714(paper, index=i))
        else:
            result.append(format_citation(paper, style))
    return result


def _format_apa(paper: PaperLike) -> str:
    """Format in APA 7th Edition style."""
    authors = format_authors_apa(paper.authors)
    year = paper.year or "n.d."
    title = paper.title or "Untitled"
    venue = paper.venue

    parts = []
    if authors:
        parts.append(f"{authors} ({year}).")
    else:
        parts.append(f"({year}).")

    parts.append(f"{title}.")

    if venue:
        parts.append(f"*{venue}*.")

    if paper.doi:
        parts.append(f"https://doi.org/{paper.doi}")
    elif paper.sources.get("arxiv"):
        parts.append(f"https://arxiv.org/abs/{paper.sources['arxiv']}")

    return " ".join(parts)


def _format_mla(paper: PaperLike) -> str:
    """Format in MLA 9th Edition style."""
    authors = format_authors_mla(paper.authors)
    year = paper.year or "n.d."
    title = paper.title or "Untitled"
    venue = paper.venue

    parts = []
    if authors:
        parts.append(f"{authors}.")
    parts.append(f'"{title}."')
    if venue:
        parts.append(f"*{venue}*,")
    parts.append(f"{year}.")

    return " ".join(parts)


def _format_ieee(paper: PaperLike, index: Optional[int] = None) -> str:
    """Format in IEEE style."""
    authors = format_authors_ieee(paper.authors)
    year = paper.year
    title = paper.title or "Untitled"
    venue = paper.venue

    parts = []
    if index is not None:
        parts.append(f"[{index}]")
    if authors:
        parts.append(f"{authors},")
    parts.append(f'"{title},"')
    if venue:
        parts.append(f"*{venue}*,")
    if year:
        parts.append(f"{year}.")
    else:
        if parts:
            parts[-1] = parts[-1].rstrip(",") + "."

    return " ".join(parts)


def _format_chicago(paper: PaperLike) -> str:
    """Format in Chicago style (Author-Date)."""
    authors = format_authors_chicago(paper.authors)
    year = paper.year or "n.d."
    title = paper.title or "Untitled"
    venue = paper.venue

    parts = []
    if authors:
        parts.append(f"{authors}.")
    parts.append(f"{year}.")
    parts.append(f'"{title}."')
    if venue:
        parts.append(f"*{venue}*.")

    return " ".join(parts)


def _format_gbt7714(paper: PaperLike, index: Optional[int] = None) -> str:
    """Format in GB/T 7714-2015 style."""
    authors = format_authors_gbt7714(paper.authors)
    year = paper.year
    title = paper.title or "Untitled"
    venue = paper.venue

    if "conference" in venue.lower() or "proceedings" in venue.lower():
        doc_type = "[C]"
    elif paper.sources.get("arxiv"):
        doc_type = "[EB/OL]"
    else:
        doc_type = "[J]"

    parts = []
    if index is not None:
        parts.append(f"[{index}]")
    if authors:
        parts.append(f"{authors}.")
    parts.append(f"{title}{doc_type}.")
    if venue:
        parts.append(f"{venue},")
    if year:
        parts.append(f"{year}.")

    return " ".join(parts)


__all__ = [
    "CitationStyle",
    "format_authors_apa",
    "format_authors_mla",
    "format_authors_ieee",
    "format_authors_chicago",
    "format_authors_gbt7714",
    "format_citation",
    "format_citations",
]
