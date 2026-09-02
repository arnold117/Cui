"""Pandoc export helpers — ported from v4 ``litscribe/exporters/pandoc.py``.

Cherry-picked into the legacy archive (T6 item 3; 产物导出, slice1 用) as
PURE construction only: the full markdown document (YAML front matter + body +
references) and the pandoc argv for each export format. Nothing here spawns a
process, touches the filesystem, or probes for the pandoc binary.

v4's ``export_review`` performed I/O around these builders (tempfile 落盘、
``shutil.which`` 探测、``subprocess.run``、扩展名修正); 按 plan-v5-slice0 T6
注记 ("不搬表结构, 只搬纯逻辑函数"), 真实执行归 slice1/调用方:

    out = resolve_output_path(output_path, config.format)      # caller decides
    markdown = build_markdown(text, papers, config)            # document text
    if config.format == ExportFormat.MARKDOWN:                 # v4: no pandoc
        out.write_text(markdown)                               # caller I/O
    else:
        # caller: write markdown (+ refs.bib from papers_to_bibtex when
        # config.include_references and papers) to temp files, then run
        # subprocess.run(build_pandoc_command(...)).

Input type substitution: v4 took ``litscribe.models.paper.Paper`` (pydantic);
here the same-shaped plain ``PaperLike`` (see ``paper_like.py``) is used.
Function bodies mirror v4 line-for-line where they exist.

未搬清单 (not ported):
- ``export_review`` — v4 的 I/O 执行函数 (tempfile/落盘、shutil.which、
  subprocess.run、RuntimeError 包装) 未搬; 本模块的等价面 =
  ``build_markdown`` + ``resolve_output_path`` + ``build_pandoc_command``
  三步纯构造, 执行由 slice1/调用方负责 (见上面调用示例)。
- ``_build_markdown`` 中的 dead 局部变量 ``numbered_styles`` (v4 定义了但从未
  使用) 未搬。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from cui.legacy_archive.exporters.citation_formatter import (
    CitationStyle,
    format_citations,
)
from cui.legacy_archive.exporters.paper_like import PaperLike


class ExportFormat(Enum):
    """Supported export formats."""

    DOCX = "docx"
    PDF = "pdf"
    HTML = "html"
    LATEX = "latex"
    EPUB = "epub"
    MARKDOWN = "md"


@dataclass
class ExportConfig:
    """Configuration for export."""

    format: ExportFormat = ExportFormat.DOCX
    citation_style: CitationStyle = CitationStyle.APA
    language: str = "en"  # "en" or "zh"
    title: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None

    # PDF/LaTeX specific
    template: Optional[str] = None
    fontsize: str = "11pt"
    geometry: str = "margin=1in"

    # Document options
    include_toc: bool = True
    include_references: bool = True
    number_sections: bool = True

    # Additional Pandoc args
    extra_args: List[str] = field(default_factory=list)


def resolve_output_path(
    output_path: str | Path,
    export_format: ExportFormat,
) -> Path:
    """Normalize ``output_path`` to carry the extension of ``export_format``.

    Pure path logic, v4-verbatim: when the current suffix differs from
    ``.{export_format.value}`` it is replaced (appended when absent).

    Args:
        output_path: Caller-provided destination path (extension corrected).
        export_format: The format whose extension governs.

    Returns:
        Path with the correct extension.
    """
    out = Path(output_path)
    ext = f".{export_format.value}"
    if out.suffix != ext:
        out = out.with_suffix(ext)
    return out


def build_markdown(
    text: str,
    papers: list[PaperLike],
    config: ExportConfig,
) -> str:
    """Build the full Markdown document with YAML front matter and references.

    Pure construction (no I/O), mirroring v4 ``_build_markdown`` line for line.
    When ``config.date`` is None the current date (``datetime.now()``) is used
    — v4 behavior kept; tests/slice1 pass an explicit date for determinism.

    Args:
        text: The review body text (Markdown).
        papers: Paper-like objects to include as references.
        config: Export configuration.

    Returns:
        Complete markdown document as a string (caller writes it to disk).
    """
    lines: list[str] = []

    # YAML front matter
    lines.append("---")
    if config.title:
        lines.append(f'title: "{config.title}"')
    if config.author:
        lines.append(f'author: "{config.author}"')
    date = config.date or datetime.now().strftime("%Y-%m-%d")
    lines.append(f'date: "{date}"')
    if config.language == "zh":
        lines.append("lang: zh-CN")
        lines.append('CJKmainfont: "PingFang SC"')
    else:
        lines.append("lang: en")
    if config.format in (ExportFormat.PDF, ExportFormat.LATEX):
        lines.append(f"fontsize: {config.fontsize}")
        lines.append(f"geometry: {config.geometry}")
    if config.include_toc:
        lines.append("toc: true")
        lines.append("toc-depth: 3")
    if config.number_sections:
        lines.append("numbersections: true")
    lines.append("---")
    lines.append("")

    # Main body
    if text:
        lines.append(text)
        lines.append("")

    # References section
    if config.include_references and papers:
        heading = "# References" if config.language == "en" else "# 参考文献"
        lines.append(heading)
        lines.append("")
        citations = format_citations(papers, config.citation_style)
        for citation in citations:
            lines.append(citation)
            lines.append("")

    return "\n".join(lines)


def build_pandoc_command(
    markdown_path: str | Path,
    output_path: str | Path,
    config: ExportConfig,
    bibliography_path: str | Path | None = None,
) -> list[str]:
    """Construct the pandoc argv for ``config.format`` (pure, no execution).

    Mirrors v4 ``export_review``'s command assembly verbatim::
        pandoc <markdown> -o <output>
        + [--bibliography <bib> --citeproc]   (bibliography_path given)
        + [--pdf-engine=xelatex]              (PDF)
        + [-V CJKmainfont=PingFang SC]        (PDF + language == "zh")
        + [--reference-doc <template>]        (DOCX + config.template)
        + [--standalone --self-contained]     (HTML)
        + config.extra_args                   (always last)

    Args:
        markdown_path: Source markdown file (output of ``build_markdown``,
            written to disk by the caller).
        output_path: Destination path — pass the result of
            ``resolve_output_path`` so the extension is already correct.
        config: Export configuration.
        bibliography_path: Pass a .bib path (content from
            ``cui.legacy_archive.exporters.bibtex.papers_to_bibtex``, written
            by the caller) when ``config.include_references`` and the paper
            list is non-empty — the v4 condition that decided whether
            ``--bibliography/--citeproc`` were appended; None otherwise.

    Returns:
        pandoc argv ready for the caller to execute (subprocess.run or
        equivalent). Execution — and any "pandoc not installed" handling —
        belongs to slice1/the caller.

    Raises:
        ValueError: If ``config.format`` is MARKDOWN — v4 wrote markdown
            directly and never invoked pandoc for it; the caller should write
            ``build_markdown`` output to disk instead.
    """
    if config.format == ExportFormat.MARKDOWN:
        raise ValueError(
            "ExportFormat.MARKDOWN is written directly and never goes through "
            "pandoc (v4 behavior): write build_markdown() output to disk "
            "instead of calling build_pandoc_command()."
        )

    cmd = ["pandoc", str(markdown_path), "-o", str(output_path)]

    if bibliography_path is not None:
        cmd.extend(["--bibliography", str(bibliography_path), "--citeproc"])

    if config.format == ExportFormat.PDF:
        cmd.append("--pdf-engine=xelatex")
        if config.language == "zh":
            cmd.extend(["-V", "CJKmainfont=PingFang SC"])

    if config.format == ExportFormat.DOCX and config.template:
        cmd.extend(["--reference-doc", config.template])

    if config.format == ExportFormat.HTML:
        cmd.extend(["--standalone", "--self-contained"])

    cmd.extend(config.extra_args)

    return cmd


__all__ = [
    "ExportFormat",
    "ExportConfig",
    "resolve_output_path",
    "build_markdown",
    "build_pandoc_command",
]
