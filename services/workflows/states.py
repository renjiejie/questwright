"""LangGraph workflow state (shared by every graph node).

Mirrors `ModuleWorkflowState` from 设计草案 §8.3. Phase 0 keeps only the
fields actually used by the minimal `generate -> END` graph; later phases
extend this in-place.
"""

from __future__ import annotations

from typing import Literal, TypedDict


Stage = Literal[
    "campaign_brief",
    "campaign_outline",
    "act_outline",
    "scene_draft",
    "final_module",
]

NextAction = Literal[
    "generate",
    "human_review",
    "revise",
    "audit",
    "audit_review",
    "commit",
    "advance_stage",
    "finish",
]


class ModuleWorkflowState(TypedDict, total=False):
    project_id: str
    run_id: str

    current_stage: Stage
    current_artifact_id: str | None
    parent_artifact_id: str | None

    user_brief: str
    human_feedback: list[dict]
    audit_report_id: str | None

    retrieved_chunk_ids: list[str]
    committed_artifact_ids: list[str]

    next_action: NextAction
    error: str | None
