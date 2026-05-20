"""Minimal Phase 0 workflow graph: `generate -> END`.

Nodes are stubs that exercise state plumbing and checkpoint persistence
without real LLM calls. Real Story Generator / Auditor / Fixer / Human Review
nodes land in Phase 2.
"""

from __future__ import annotations

import uuid
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from .states import ModuleWorkflowState


def _generate_node(state: ModuleWorkflowState) -> dict[str, Any]:
    """Phase 0 stub: produce a placeholder artifact id without calling any LLM."""
    new_id = f"artifact_{uuid.uuid4().hex[:12]}"
    return {
        "current_artifact_id": new_id,
        "current_stage": state.get("current_stage", "campaign_brief"),
        "next_action": "human_review",
    }


def _build_graph_uncompiled() -> StateGraph:
    graph = StateGraph(ModuleWorkflowState)
    graph.add_node("generate", _generate_node)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", END)
    return graph


def make_checkpointer(db_path: str | Path) -> AbstractAsyncContextManager[AsyncSqliteSaver]:
    """Return an async context manager yielding the AsyncSqliteSaver.

    Caller is responsible for `async with` so the underlying connection closes
    cleanly. The DB file is created if missing.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return AsyncSqliteSaver.from_conn_string(str(db_path))


def build_graph(checkpointer: AsyncSqliteSaver | None = None):
    """Compile the Phase 0 graph.

    Pass a `checkpointer` for persistent runs; pass `None` for in-memory
    one-shot runs (useful in tests where checkpoint persistence isn't being
    asserted).
    """
    graph = _build_graph_uncompiled()
    if checkpointer is None:
        return graph.compile()
    return graph.compile(checkpointer=checkpointer)


__all__ = ["build_graph", "make_checkpointer", "ModuleWorkflowState"]
