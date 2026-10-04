"""Observability domain value objects — status enums + caps."""

from __future__ import annotations

from enum import StrEnum


class RunType(StrEnum):
    """Source event family that produced a :class:`RunRecord`."""

    LLM = "llm"
    TOOL = "tool"
    SKILL = "skill"
    MEMORY = "memory"
    KNOWLEDGE = "knowledge"
    WORKFLOW = "workflow"
    CHANNEL = "channel"
    EVAL = "eval"
    GOVERNANCE = "governance"


class RunStatus(StrEnum):
    """Outcome of a recorded business action."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RUNNING = "running"


class CostType(StrEnum):
    """Bucket for a :class:`CostRecord`."""

    LLM_INPUT = "llm_input"
    LLM_OUTPUT = "llm_output"
    TOOL = "tool"
    SKILL = "skill"
    MEMORY = "memory"
    KNOWLEDGE = "knowledge"
    CHANNEL = "channel"


__all__ = [
    "CostType",
    "RunStatus",
    "RunType",
]
