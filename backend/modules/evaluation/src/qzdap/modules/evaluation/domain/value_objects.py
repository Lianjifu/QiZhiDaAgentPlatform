"""Value objects for the evaluation module."""

from __future__ import annotations

from enum import StrEnum

# ── bounds ────────────────────────────────────────────────────────────────
MAX_NAME_LEN = 256
MAX_DESCRIPTION_LEN = 1024
MAX_INPUT_LEN = 8192
MAX_KEYWORDS = 16
MAX_KEYWORD_LEN = 128

# ── enums ────────────────────────────────────────────────────────────────


class EvalDatasetKind(StrEnum):
    BUILTIN = "builtin"
    CUSTOM = "custom"


class EvalDatasetStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class EvalRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"


__all__ = [
    "MAX_DESCRIPTION_LEN",
    "MAX_INPUT_LEN",
    "MAX_KEYWORDS",
    "MAX_KEYWORD_LEN",
    "MAX_NAME_LEN",
    "EvalDatasetKind",
    "EvalDatasetStatus",
    "EvalRunStatus",
]
