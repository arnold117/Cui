"""v4 exporters cherry-picked into the legacy archive (T6 item 3; slice1 产物导出).

Pure formatting only — BibTeX entry generation, citation styles and pandoc
document/argument construction. No v4 internals (store/llm/models/agents),
no subprocess execution, no network: pandoc execution is left to
slice1/the caller (see ``cui.legacy_archive.exporters.pandoc`` for the
caller-side recipe).

Modules keep their v4 names (``bibtex``, ``citation_formatter``, ``pandoc``).
Shared input shape is the plain ``PaperLike`` dataclass (``paper_like.py``),
standing in for v4's pydantic ``Paper`` so the port stays dependency-free.
"""

from cui.legacy_archive.exporters.bibtex import (
    BibTeXEntry,
    detect_entry_type,
    escape_bibtex,
    generate_cite_key,
    normalize_author_name,
    papers_to_bibtex,
)
from cui.legacy_archive.exporters.citation_formatter import (
    CitationStyle,
    format_authors_apa,
    format_authors_chicago,
    format_authors_gbt7714,
    format_authors_ieee,
    format_authors_mla,
    format_citation,
    format_citations,
)
from cui.legacy_archive.exporters.pandoc import (
    ExportConfig,
    ExportFormat,
    build_markdown,
    build_pandoc_command,
    resolve_output_path,
)
from cui.legacy_archive.exporters.paper_like import PaperLike

__all__ = [
    # shape
    "PaperLike",
    # bibtex
    "BibTeXEntry",
    "escape_bibtex",
    "normalize_author_name",
    "generate_cite_key",
    "detect_entry_type",
    "papers_to_bibtex",
    # citation_formatter
    "CitationStyle",
    "format_authors_apa",
    "format_authors_mla",
    "format_authors_ieee",
    "format_authors_chicago",
    "format_authors_gbt7714",
    "format_citation",
    "format_citations",
    # pandoc
    "ExportFormat",
    "ExportConfig",
    "resolve_output_path",
    "build_markdown",
    "build_pandoc_command",
]
