"""Skill catalog unit tests — admin CRUD + user projection."""

from __future__ import annotations

from uuid import UUID

import pytest

from qzdap.modules.skill.application.ports import (
    SkillRepository,
    SkillUserStateRepository,
)
from qzdap.modules.skill.application.services import SkillService
from qzdap.modules.skill.domain.entities import Skill
from qzdap.modules.skill.domain.errors import SkillDisabled, SkillNotFound

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
USER = UUID("00000000-0000-0000-0000-000000000010")


class InMemorySkillRepository(SkillRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Skill] = {}

    async def add(self, skill: Skill) -> None:
        self._by_id[skill.id] = skill

    async def get(self, skill_id: UUID) -> Skill | None:
        return self._by_id.get(skill_id)

    async def get_by_name(self, *, workspace_id: UUID, name: str) -> Skill | None:
        for skill in self._by_id.values():
            if skill.workspace_id == workspace_id and skill.name == name:
                return skill
        return None

    async def list_for_workspace(self, workspace_id: UUID) -> list[Skill]:
        return [skill for skill in self._by_id.values() if skill.workspace_id == workspace_id]

    async def update(self, skill: Skill) -> None:
        self._by_id[skill.id] = skill

    async def delete(self, skill_id: UUID) -> None:
        self._by_id.pop(skill_id, None)


class InMemorySkillUserStateRepository(SkillUserStateRepository):
    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, UUID], tuple[bool, str | None]] = {}

    async def get(self, *, user_id: UUID, skill_id: UUID) -> tuple[bool, str | None]:
        return self._rows.get((user_id, skill_id), (False, None))

    async def set_favorite(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        skill_id: UUID,
        on: bool,
    ) -> None:
        _ = (tenant_id, workspace_id)
        fav, last = self._rows.get((user_id, skill_id), (False, None))
        self._rows[(user_id, skill_id)] = (on, last)
        _ = fav

    async def record_use(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        skill_id: UUID,
        at: str,
    ) -> None:
        _ = (tenant_id, workspace_id)
        fav, _last = self._rows.get((user_id, skill_id), (False, None))
        self._rows[(user_id, skill_id)] = (fav, at)


def _svc() -> SkillService:
    return SkillService(InMemorySkillRepository(), InMemorySkillUserStateRepository())


@pytest.mark.asyncio
async def test_create_list_and_catalog_visibility() -> None:
    svc = _svc()
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "邮件分拣", "type": "Skill", "owner": "管理员", "risk": "low"},
    )
    assert created["status"] == "draft"
    listed = await svc.list_admin(workspace_id=WORKSPACE)
    assert len(listed) == 1
    catalog = await svc.list_catalog(workspace_id=WORKSPACE, user_id=USER)
    assert catalog == []

    skill_id = UUID(created["id"])
    published = await svc.update(
        skill_id=skill_id, body={"patch": {"status": "published"}}, actor="管理员"
    )
    assert published["status"] == "published"
    assert published["version"].startswith("v")
    catalog = await svc.list_catalog(workspace_id=WORKSPACE, user_id=USER)
    assert len(catalog) == 1
    assert catalog[0]["name"] == "邮件分拣"
    assert catalog[0]["status"] == "available"


@pytest.mark.asyncio
async def test_bulk_retire_hides_from_catalog() -> None:
    svc = _svc()
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "合同抽取", "type": "Tool", "owner": "法务"},
    )
    skill_id = created["id"]
    await svc.bulk(ids=[skill_id], action="publish", actor="管理员")
    assert (await svc.list_catalog(workspace_id=WORKSPACE, user_id=USER))
    await svc.bulk(ids=[skill_id], action="retire", actor="管理员")
    assert await svc.list_catalog(workspace_id=WORKSPACE, user_id=USER) == []


@pytest.mark.asyncio
async def test_delete_and_not_found() -> None:
    svc = _svc()
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "临时技能", "type": "MCP", "owner": "运维"},
    )
    skill_id = UUID(created["id"])
    deleted = await svc.delete(skill_id)
    assert deleted == {"ok": True, "id": str(skill_id)}
    with pytest.raises(SkillNotFound):
        await svc.get_admin(skill_id)


@pytest.mark.asyncio
async def test_bump_and_describe_requires_published() -> None:
    svc = _svc()
    await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "周报助手", "type": "Skill", "owner": "管理员"},
    )
    with pytest.raises(SkillDisabled):
        await svc.bump_and_describe(workspace_id=WORKSPACE, name="周报助手")
    listed = await svc.list_admin(workspace_id=WORKSPACE)
    await svc.bulk(ids=[listed[0]["id"]], action="publish", actor="管理员")
    result = await svc.bump_and_describe(workspace_id=WORKSPACE, name="周报助手")
    assert result["ok"] is True
    again = await svc.get_admin(UUID(listed[0]["id"]))
    assert again["calls"] == 1


class _FakeSandbox:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run_job(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return {"status": "succeeded", "stdout": "done", "stderr": "", "exit_code": 0}


@pytest.mark.asyncio
async def test_invoke_in_sandbox_records_metrics() -> None:
    from uuid import uuid4

    sandbox = _FakeSandbox()
    svc = SkillService(
        InMemorySkillRepository(),
        InMemorySkillUserStateRepository(),
        sandbox_jobs=sandbox,
    )
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "name": "沙箱技能",
            "type": "Skill",
            "owner": "管理员",
            "runtime": {
                "enabled": True,
                "source": "print(open('/work/input.json').read())",
                "entry": "main.py",
                "image": "qzdap/sandbox-python:latest",
            },
        },
    )
    await svc.bulk(ids=[created["id"]], action="publish", actor="管理员")
    result = await svc.invoke_in_sandbox(
        workspace_id=WORKSPACE,
        name="沙箱技能",
        arguments={},
        call_id=uuid4(),
    )
    assert result["ok"] is True
    assert sandbox.calls
    again = await svc.get_admin(UUID(created["id"]))
    assert again["calls"] == 1
    assert again["successRate"] == 100.0


@pytest.mark.asyncio
async def test_invoke_requires_runtime_and_confirm() -> None:
    from uuid import uuid4

    from qzdap.modules.skill.domain.errors import SkillNeedsConfirm, SkillNotExecutable

    svc = _svc()
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "无运行时", "type": "Skill", "owner": "管理员", "needConfirm": True},
    )
    await svc.bulk(ids=[created["id"]], action="publish", actor="管理员")
    with pytest.raises(SkillNeedsConfirm):
        await svc.invoke_in_sandbox(
            workspace_id=WORKSPACE, name="无运行时", arguments={}, call_id=uuid4()
        )
    await svc.update(
        skill_id=UUID(created["id"]),
        body={"patch": {"needConfirm": False}},
        actor="管理员",
    )
    with pytest.raises(SkillNotExecutable):
        await svc.invoke_in_sandbox(
            workspace_id=WORKSPACE, name="无运行时", arguments={}, call_id=uuid4()
        )


@pytest.mark.asyncio
async def test_record_use_and_favorite() -> None:
    svc = _svc()
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "客服话术", "type": "Skill", "owner": "客服"},
    )
    skill_id = UUID(created["id"])
    await svc.bulk(ids=[str(skill_id)], action="publish", actor="客服")
    fav = await svc.set_favorite(skill_id=skill_id, user_id=USER, on=True)
    assert fav["on"] is True
    used = await svc.record_use(skill_id=skill_id, user_id=USER)
    assert used["recordedAt"]
    detail = await svc.get_catalog(skill_id=skill_id, user_id=USER)
    assert detail["id"] == str(skill_id)
