"""v4 diff utilities cherry-pick: text-diff helpers (T6 item 5).

来源: LitScribe v4 ``litscribe/tools/diff.py`` @ ``027583c``. The whole v4
module is pure, stdlib-only logic (``difflib`` + ANSI escapes) with no
litscribe-internal imports, so ALL of it is ported — semantics verbatim (the
v4 file's unused ``from typing import Any`` is the only thing not carried
over). No native Cui equivalent exists.

NOT ported: nothing. (slice1 needing the original file verbatim can take it
back from ``LitScribe/litscribe/tools/diff.py`` — this module is a byte-level
port minus the dead import.)

Formatting quirks kept on purpose (archive 保真; do not "fix"):
- ``colored_diff`` classifies by ``line.startswith``, so a hunk header that
  begins with ``+``/``-`` before ``@@`` would mis-color — difflib does not
  emit such lines, but the ordering of checks here matches v4 exactly;
- ``diff_stats.unchanged`` = ``len(new_lines) - added`` (v4 definition);
- ``html_diff`` wraps at column 80 via ``difflib.HtmlDiff``.
"""

from __future__ import annotations

import difflib


def unified_diff(old: str, new: str, old_name: str = "before", new_name: str = "after") -> str:
    """Unified diff of two texts as a string (line-perfect, ``keepends``)."""

    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff = difflib.unified_diff(old_lines, new_lines, fromfile=old_name, tofile=new_name)
    return "".join(diff)


def colored_diff(old: str, new: str) -> str:
    """Unified diff with ANSI colors: bold headers, green adds, red removals,
    cyan hunk markers. Context lines stay uncolored."""

    old_lines = old.splitlines()
    new_lines = new.splitlines()

    diff = difflib.unified_diff(old_lines, new_lines, lineterm="")
    lines = []
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            lines.append(f"\033[1m{line}\033[0m")
        elif line.startswith("+"):
            lines.append(f"\033[32m{line}\033[0m")
        elif line.startswith("-"):
            lines.append(f"\033[31m{line}\033[0m")
        elif line.startswith("@@"):
            lines.append(f"\033[36m{line}\033[0m")
        else:
            lines.append(line)

    return "\n".join(lines)


def diff_stats(old: str, new: str) -> dict[str, int]:
    """Count added/removed/unchanged lines between two texts (v4 definition:
    ``unchanged`` = ``len(new_lines) - added``)."""

    old_lines = old.splitlines()
    new_lines = new.splitlines()

    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

    return {"added": added, "removed": removed, "unchanged": len(new_lines) - added}


def html_diff(old: str, new: str) -> str:
    """Side-by-side HTML diff table (``difflib.HtmlDiff``, wrapcolumn=80)."""

    old_lines = old.splitlines()
    new_lines = new.splitlines()

    differ = difflib.HtmlDiff(wrapcolumn=80)
    return differ.make_table(old_lines, new_lines, fromdesc="Before", todesc="After")
