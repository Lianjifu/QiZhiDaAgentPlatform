"""Agent factory value objects — status enums + limits."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MAX_NAME_LEN = 256
MAX_DESCRIPTION_LEN = 1024
MAX_VERSION_TAG_LEN = 64
MAX_PROMPT_LEN = 32 * 1024  # 32 KiB
MAX_ALLOWED_TOOLS = 64
MAX_ALLOWED_SKILLS = 64
MAX_KNOWLEDGE_PACKAGE_IDS = 32
MAX_REVIEW_LEN = 1024


class AgentTemplateStatus(StrEnum):
    """Lifecycle of an :class:`AgentTemplate`."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class AgentVersionStatus(StrEnum):
    """Lifecycle of an :class:`AgentVersion`.

    State machine: ``draft → published → released → retired``.

    - ``draft``     : mutable; release_notes can still be edited.
    - ``published`` : immutable.  Released by a successful gate.
    - ``released``  : immutable.  Currently the GA version.
    - ``retired``   : immutable.  Superseded by a newer release.
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    RELEASED = "released"
    RETIRED = "retired"


class ReleaseStatus(StrEnum):
    """Lifecycle of a :class:`Release`."""

    RELEASED = "released"  # final state


@dataclass(slots=True, frozen=True)
class AgentFactoryLimits:
    """Hard caps enforced at the use-case boundary."""

    max_total_steps: int = 64
    max_versions_per_template: int = 1000


__all__ = [
    "MAX_ALLOWED_SKILLS",
    "MAX_ALLOWED_TOOLS",
    "MAX_DESCRIPTION_LEN",
    "MAX_KNOWLEDGE_PACKAGE_IDS",
    "MAX_NAME_LEN",
    "MAX_PROMPT_LEN",
    "MAX_REVIEW_LEN",
    "MAX_VERSION_TAG_LEN",
    "AgentFactoryLimits",
    "AgentTemplateStatus",
    "AgentVersionStatus",
    "ReleaseStatus",
]
