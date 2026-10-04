"""Skill integration test fixtures.

Adds the unit-tests dir to sys.path so we can reuse the in-memory doubles
defined in `tests/unit/_in_memory.py` and the test-id helpers in
`tests/unit/conftest.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID, uuid4

from qzdap_schema.ids import SkillId, TenantId, UserId, WorkspaceId

UNIT_DIR = Path(__file__).resolve().parents[1] / "unit"
if str(UNIT_DIR) not in sys.path:
    sys.path.insert(0, str(UNIT_DIR))


def make_tenant() -> TenantId:
    return TenantId(UUID("00000000-0000-0000-0000-000000000001"))


def make_workspace() -> WorkspaceId:
    return WorkspaceId(UUID("00000000-0000-0000-0000-000000000002"))


def make_user() -> UserId:
    return UserId(UUID("00000000-0000-0000-0000-000000000010"))


def make_skill_id() -> SkillId:
    return SkillId(uuid4())
