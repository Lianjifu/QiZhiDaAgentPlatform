"""Skill catalog service — CRUD + user catalog projection."""

from __future__ import annotations

import json
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.skill.application.ports import (
    SandboxJobPort,
    SkillRepository,
    SkillUserStateRepository,
)
from qzdap.modules.skill.domain.entities import (
    SKILL_STATUSES,
    SKILL_TYPES,
    VISIBLE_SCOPES,
    SchemaField,
    Skill,
    SkillRuntime,
    is_workspace_visible,
)
from qzdap.modules.skill.domain.errors import (
    SkillDisabled,
    SkillNeedsConfirm,
    SkillNotExecutable,
    SkillNotFound,
    SkillSandboxUnavailable,
)


class SkillService:
    def __init__(
        self,
        skills: SkillRepository,
        user_state: SkillUserStateRepository,
        sandbox_jobs: SandboxJobPort | None = None,
    ) -> None:
        self._skills = skills
        self._user_state = user_state
        self._sandbox_jobs = sandbox_jobs

    async def list_admin(
        self,
        *,
        workspace_id: UUID,
        type_filter: str = "all",
        status_filter: str = "all",
        q: str = "",
        sort: str = "updated",
    ) -> list[dict[str, Any]]:
        items = await self._skills.list_for_workspace(workspace_id)
        query = q.strip().lower()
        filtered: list[Skill] = []
        for skill in items:
            if type_filter not in ("all", "", None) and skill.type != type_filter:
                continue
            if status_filter not in ("all", "", None) and skill.status != status_filter:
                continue
            hay = f"{skill.name} {skill.description} {skill.owner} {' '.join(skill.tags)}".lower()
            if query and query not in hay:
                continue
            filtered.append(skill)
        if sort == "calls":
            filtered.sort(key=lambda item: item.calls, reverse=True)
        elif sort == "name":
            filtered.sort(key=lambda item: item.name)
        else:
            filtered.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in filtered]

    async def get_admin(self, skill_id: UUID) -> dict[str, Any]:
        skill = await self._require(skill_id)
        return skill.to_admin_dict()

    async def get_by_name(self, *, workspace_id: UUID, name: str) -> Skill | None:
        return await self._skills.get_by_name(workspace_id=workspace_id, name=name)

    async def create(self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        skill_type = body.get("type") or "Skill"
        if skill_type not in SKILL_TYPES:
            skill_type = "Skill"
        skill_id = _parse_id(body.get("id"))
        skill = Skill.create(
            id=skill_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=str(body.get("name") or "未命名技能"),
            description=str(body.get("description") or ""),
            type=skill_type,  # type: ignore[arg-type]
            owner=str(body.get("owner") or "管理员"),
            risk=body.get("risk") if body.get("risk") in {"low", "medium", "high"} else "low",
            need_confirm=bool(body.get("needConfirm", False)),
            input_schema=[
                SchemaField.from_dict(item)
                for item in (body.get("inputSchema") or [])
                if isinstance(item, dict)
            ],
            output_schema=[
                SchemaField.from_dict(item)
                for item in (body.get("outputSchema") or [])
                if isinstance(item, dict)
            ],
        )
        if isinstance(body.get("runtime"), dict):
            skill.runtime = SkillRuntime.from_dict(body["runtime"])
        if isinstance(body.get("tags"), list):
            skill.tags = [str(item) for item in body["tags"]]
        if isinstance(body.get("visibleScope"), list):
            skill.visible_scope = [
                item for item in body["visibleScope"] if item in VISIBLE_SCOPES
            ] or ["部门"]
        await self._skills.add(skill)
        return skill.to_admin_dict()

    async def update(self, *, skill_id: UUID, body: dict[str, Any], actor: str) -> dict[str, Any]:
        skill = await self._require(skill_id)
        patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
        updated = skill.apply_patch(patch, actor=actor)
        await self._skills.update(updated)
        return updated.to_admin_dict()

    async def delete(self, skill_id: UUID) -> dict[str, Any]:
        await self._require(skill_id)
        await self._skills.delete(skill_id)
        return {"ok": True, "id": str(skill_id)}

    async def bulk(self, *, ids: list[str], action: str, actor: str) -> dict[str, int]:
        affected = 0
        for raw in ids:
            try:
                skill_id = UUID(str(raw))
            except ValueError:
                continue
            skill = await self._skills.get(skill_id)
            if skill is None:
                continue
            if action == "publish":
                updated = skill.publish(actor=actor)
            else:
                updated = skill.retire(actor=actor)
            await self._skills.update(updated)
            affected += 1
        return {"affected": affected}

    async def list_catalog(self, *, workspace_id: UUID, user_id: UUID) -> list[dict[str, Any]]:
        items = await self._skills.list_for_workspace(workspace_id)
        out: list[dict[str, Any]] = []
        for skill in items:
            if skill.status not in {"published", "graying"}:
                continue
            if not is_workspace_visible(list(skill.visible_scope)):
                continue
            _fav, last_used = await self._user_state.get(user_id=user_id, skill_id=skill.id)
            out.append(skill.to_catalog_dict(last_used=last_used))
        return out

    async def get_catalog(self, *, skill_id: UUID, user_id: UUID) -> dict[str, Any]:
        skill = await self._require(skill_id)
        _fav, last_used = await self._user_state.get(user_id=user_id, skill_id=skill.id)
        return skill.to_catalog_dict(last_used=last_used)

    async def set_favorite(self, *, skill_id: UUID, user_id: UUID, on: bool) -> dict[str, Any]:
        skill = await self._require(skill_id)
        await self._user_state.set_favorite(
            tenant_id=skill.tenant_id,
            workspace_id=skill.workspace_id,
            user_id=user_id,
            skill_id=skill_id,
            on=on,
        )
        return {"id": str(skill_id), "on": on}

    async def record_use(self, *, skill_id: UUID, user_id: UUID) -> dict[str, Any]:
        skill = await self._require(skill_id)
        from datetime import UTC, datetime

        at = datetime.now(UTC).isoformat()
        await self._user_state.record_use(
            tenant_id=skill.tenant_id,
            workspace_id=skill.workspace_id,
            user_id=user_id,
            skill_id=skill_id,
            at=at,
        )
        await self._skills.update(skill.bump_call())
        return {"id": str(skill_id), "recordedAt": at}

    async def bump_and_describe(self, *, workspace_id: UUID, name: str) -> dict[str, Any]:
        skill = await self._skills.get_by_name(workspace_id=workspace_id, name=name)
        if skill is None:
            raise SkillNotFound(f"skill {name} not found")
        if skill.status not in {"published", "graying"}:
            raise SkillDisabled(f"skill {name} is {skill.status}")
        updated = skill.bump_call()
        await self._skills.update(updated)
        return {
            "ok": True,
            "skillId": str(updated.id),
            "name": updated.name,
            "type": updated.type,
        }

    async def list_executable(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._skills.list_for_workspace(workspace_id)
        out: list[dict[str, Any]] = []
        for skill in items:
            if skill.status not in {"published", "graying"}:
                continue
            if not skill.runtime.enabled:
                continue
            out.append(
                {
                    "name": skill.name,
                    "description": skill.description,
                    "inputSchema": [item.to_dict() for item in skill.input_schema],
                    "needConfirm": skill.need_confirm,
                    "risk": skill.risk,
                }
            )
        return out

    async def invoke_in_sandbox(
        self,
        *,
        workspace_id: UUID,
        name: str,
        arguments: dict[str, Any],
        call_id: UUID,
        agent_id: UUID | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        skill = await self._skills.get_by_name(workspace_id=workspace_id, name=name)
        if skill is None:
            raise SkillNotFound(f"skill {name} not found")
        if skill.status not in {"published", "graying"}:
            raise SkillDisabled(f"skill {name} is {skill.status}")
        if skill.need_confirm and not confirmed:
            raise SkillNeedsConfirm(f"skill {name} requires confirmation")
        if not skill.runtime.enabled or not skill.runtime.source.strip():
            raise SkillNotExecutable(f"skill {name} has no sandbox runtime")
        missing = [
            field.name
            for field in skill.input_schema
            if field.required and field.name not in arguments
        ]
        if missing:
            raise SkillNotExecutable(f"skill {name} missing required fields: {', '.join(missing)}")
        if self._sandbox_jobs is None:
            raise SkillSandboxUnavailable("sandbox_runtime is not configured")
        network = skill.runtime.network
        if skill.risk == "low":
            network = "none"
        started = monotonic()
        encoded = json.dumps(arguments, ensure_ascii=False)
        payload_files = {
            skill.runtime.entry: skill.runtime.source,
            "input.json": encoded,
        }
        result = await self._sandbox_jobs.run_job(
            kind="skill",
            tenant_id=skill.tenant_id,
            workspace_id=skill.workspace_id,
            call_id=call_id,
            image=skill.runtime.image,
            command=["python", f"/work/{skill.runtime.entry}"],
            files=payload_files,
            timeout_ms=skill.runtime.timeout_ms,
            network=network,
            memory_mb=skill.runtime.memory_mb,
            stdin=encoded,
            agent_id=agent_id,
        )
        latency_ms = int((monotonic() - started) * 1000)
        ok = result.get("status") == "succeeded"
        await self._skills.update(skill.record_outcome(ok=ok, latency_ms=latency_ms))
        return {
            "ok": ok,
            "skillId": str(skill.id),
            "name": skill.name,
            "type": skill.type,
            "call_id": str(call_id),
            "stdout": result.get("stdout") or "",
            "stderr": result.get("stderr") or "",
            "exit_code": result.get("exit_code"),
            "status": result.get("status"),
            "error_code": result.get("error_code"),
            "latency_ms": latency_ms,
        }

    async def _require(self, skill_id: UUID) -> Skill:
        skill = await self._skills.get(skill_id)
        if skill is None:
            raise SkillNotFound(f"skill {skill_id} not found")
        return skill


def _parse_id(raw: Any) -> UUID:
    if raw:
        try:
            return UUID(str(raw))
        except ValueError:
            pass
    return uuid4()


__all__ = ["SKILL_STATUSES", "SKILL_TYPES", "SkillService"]
