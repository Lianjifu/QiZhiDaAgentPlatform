"""Shared test fixtures for skill module tests."""

from __future__ import annotations

from uuid import UUID, uuid4

from qzdap_schema.ids import SkillId, TenantId, UserId, WorkspaceId


def make_tenant() -> TenantId:
    return TenantId(UUID("00000000-0000-0000-0000-000000000001"))


def make_workspace() -> WorkspaceId:
    return WorkspaceId(UUID("00000000-0000-0000-0000-000000000002"))


def make_user() -> UserId:
    return UserId(UUID("00000000-0000-0000-0000-000000000010"))


def make_skill_id() -> SkillId:
    return SkillId(uuid4())


def make_dummy_id() -> UUID:
    return uuid4()


__all__ = [
    "make_dummy_id",
    "make_skill_id",
    "make_tenant",
    "make_user",
    "make_workspace",
]
