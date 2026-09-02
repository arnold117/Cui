"""BibTeX entry generation — ported from v4 ``litscribe/exporters/bibtex.py``.

Cherry-picked verbatim into the legacy archive (T6 item 3; 产物导出, slice1
用): entry-type detection, cite-key generation, BibTeX escaping and whole-file
assembly. Pure string logic only — no v4 internals, no I/O.

Input type substitution: v4 took its pydantic ``litscribe.models.paper.Paper``;
here functions take the same-shaped plain ``PaperLike`` (see ``paper_like.py``)
so the module stays dependency-free. Function bodies are v4-verbatim.

未搬清单 (not ported):
- 无 —— 本模块全部为纯格式化逻辑, 逐函数搬入。适配三处: ① 输入类型
  ``Paper`` → ``PaperLike``; ② 删除 v4 未使用的 ``typing.List`` import;
  ③ v4 已知问题修复 (见 ``escape_bibtex`` docstring): 字符串 replacement 经
  ``re.sub`` 时 ``\t`` 被解释为 TAB 控制符, 使 ``~``/``^`` 的转义输出损坏,
  改 callable replacement 保证字面输出。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict

from cui.legacy_archive.exporters.paper_like import PaperLike


@dataclass
class BibTeXEntry:
    """A single BibTeX entry."""

    entry_type: str  # article, inproceedings, misc, etc.
    cite_key: str
    fields: Dict[str, str]

    def to_bibtex(self) -> str:
        """Convert to BibTeX string format."""
        lines = [f"@{self.entry_type}{{{self.cite_key},"]
        for key, value in self.fields.items():
            if value:
                escaped = escape_bibtex(value)
                lines.append(f"  {key} = {{{escaped}}},")
        lines.append("}")
        return "\n".join(lines)


def escape_bibtex(text: str) -> str:
    """Escape special LaTeX/BibTeX characters.

    Args:
        text: Raw text to escape

    Returns:
        Text with special characters escaped
    """
    if not text:
        return ""

    replacements = [
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]

    result = text
    for old, new in replacements:
        # Callable replacement (not the string ``new`` directly): re.sub
        # interprets backslash escapes in string replacements, so v4's
        # r"\textasciitilde{}" / r"\textasciicircum{}" came out as a literal
        # TAB + "extasciitilde{}" (the "\t" prefix was eaten) — corrupt .bib
        # output. v4 已知问题修复: a callable emits ``new`` verbatim.
        result = re.sub(rf"(?<!\\){re.escape(old)}", lambda _match: new, result)

    return result


def normalize_author_name(name: str) -> str:
    """Normalize author name for BibTeX (Last, First format)."""
    name = name.strip()
    if "," in name:
        return name
    parts = name.split()
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[1]}, {parts[0]}"
    else:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"


def generate_cite_key(authors: list[str], year: int, title: str) -> str:
    """Generate a citation key from author list, year, and title.

    Format: FirstAuthorLastname_Year_FirstWordOfTitle

    Args:
        authors: List of author name strings
        year: Publication year
        title: Paper title

    Returns:
        Citation key string
    """
    if authors:
        first_author = authors[0]
        if "," in first_author:
            last_name = first_author.split(",")[0]
        else:
            parts = first_author.split()
            if not parts:
                last_name = "Unknown"
            elif len(parts) >= 2 and len(parts[-1]) == 1:
                # Format "LastName I" — last token is a single initial
                last_name = parts[0]
            else:
                last_name = parts[-1]
    else:
        last_name = "Unknown"

    last_name = unicodedata.normalize("NFKD", last_name)
    last_name = last_name.encode("ascii", "ignore").decode("ascii")
    last_name = re.sub(r"[^a-zA-Z]", "", last_name)

    year_str = str(year) if year else "XXXX"

    title_words = re.sub(r"[^\w\s]", "", title).split()
    stop_words = {"a", "an", "the", "on", "in", "of", "for", "to", "with"}
    first_word = "paper"
    for word in title_words:
        if word.lower() not in stop_words:
            first_word = word
            break

    return f"{last_name}{year_str}{first_word}".lower()


def detect_entry_type(venue: str) -> str:
    """Detect the appropriate BibTeX entry type from a venue string.

    Args:
        venue: Publication venue name

    Returns:
        BibTeX entry type: 'article', 'inproceedings', or 'misc'
    """
    venue_lower = venue.lower()

    conference_keywords = [
        "conference", "proceedings", "workshop", "symposium",
        "icml", "neurips", "nips", "iclr", "cvpr", "iccv", "acl",
        "emnlp", "naacl", "aaai", "ijcai", "sigir", "kdd", "www",
    ]
    if any(kw in venue_lower for kw in conference_keywords):
        return "inproceedings"

    journal_keywords = [
        "journal", "transactions", "review", "letters", "magazine",
        "nature", "science", "cell", "lancet", "nejm", "jama",
    ]
    if any(kw in venue_lower for kw in journal_keywords):
        return "article"

    if "arxiv" in venue_lower:
        return "misc"

    return "misc"


def _generate_bibtex_entry(paper: PaperLike, used_keys: set[str] | None = None) -> BibTeXEntry:
    """Generate a BibTeX entry from a paper-like shape (v4 ``Paper`` logic)."""
    entry_type = detect_entry_type(paper.venue)
    cite_key = generate_cite_key(paper.authors, paper.year, paper.title)

    # Ensure unique key
    if used_keys is not None:
        if cite_key in used_keys:
            suffix = ord("a")
            while f"{cite_key}{chr(suffix)}" in used_keys:
                suffix += 1
            cite_key = f"{cite_key}{chr(suffix)}"
        used_keys.add(cite_key)

    fields: Dict[str, str] = {}

    if paper.title:
        fields["title"] = paper.title

    if paper.authors:
        normalized = [normalize_author_name(a) for a in paper.authors]
        fields["author"] = " and ".join(normalized)

    if paper.year:
        fields["year"] = str(paper.year)

    if paper.abstract:
        fields["abstract"] = paper.abstract

    if entry_type == "article":
        fields["journal"] = paper.venue if paper.venue else "Unknown Journal"
    elif entry_type == "inproceedings":
        fields["booktitle"] = paper.venue if paper.venue else "Unknown Conference"

    if paper.doi:
        fields["doi"] = paper.doi
    elif paper.paper_id.startswith("10."):
        fields["doi"] = paper.paper_id

    # arXiv source handling
    arxiv_id = paper.sources.get("arxiv", "")
    if arxiv_id:
        fields["eprint"] = arxiv_id
        fields["archiveprefix"] = "arXiv"

    return BibTeXEntry(entry_type=entry_type, cite_key=cite_key, fields=fields)


def papers_to_bibtex(papers: list[PaperLike]) -> str:
    """Generate a BibTeX bibliography string from a list of paper-like shapes.

    Args:
        papers: List of paper-like objects (see ``paper_like.py``)

    Returns:
        Complete BibTeX file content as a string
    """
    used_keys: set[str] = set()
    entries = [_generate_bibtex_entry(p, used_keys) for p in papers]

    lines = [
        "% BibTeX bibliography generated by LitScribe",
        f"% Contains {len(entries)} entries",
        "%",
        "% Citation keys follow the format: AuthorYearFirstword",
        "% e.g., smith2023deep for 'Deep Learning for NLP' by Smith (2023)",
        "",
    ]
    for entry in entries:
        lines.append(entry.to_bibtex())
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "BibTeXEntry",
    "escape_bibtex",
    "normalize_author_name",
    "generate_cite_key",
    "detect_entry_type",
    "papers_to_bibtex",
]
