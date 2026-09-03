"""Canonical corpus workspace identity (slice0 T5 importer -> slice1 dialogue).

Single source of truth for the two deterministic corpus workspaces: their
command ids, creation questions and workspace ids (uuid5 of the command). The
v4 importer creates them; the corpus search and the literature dialogue
reference them library-wide. Imported by tools/application/API — must stay a
pure leaf (stdlib only).
"""
from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

ACTIVE_WS_COMMAND = "v4-corpus-active"
LEGACY_WS_COMMAND = "v4-corpus-legacy"
WS_QUESTIONS = {
    ACTIVE_WS_COMMAND: "语料库·active — v4 迁移 LLM 时代 arXiv 群(2026-09-02 importer)",
    LEGACY_WS_COMMAND: "语料库·legacy — v4 迁移生物工艺/DOI/老 arXiv 群(2026-09-02 importer)",
}
CORPUS_COMMANDS = (ACTIVE_WS_COMMAND, LEGACY_WS_COMMAND)


def workspace_id_for(command_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"slice1:workspace:{command_id}"))


def corpus_workspace_ids() -> set[str]:
    return {workspace_id_for(command) for command in CORPUS_COMMANDS}
