"""SkillServiceAdapter — adapts `SkillService` to `SkillPort`.

Resolves a published catalog skill and executes it in sandbox_runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from qzdap.modules.skill.application.services import SkillService
from qzdap.modules.skill.domain.errors import (
    SkillDisabled,
    SkillNeedsConfirm,
    SkillNotExecutable,
    SkillNotFound,
    SkillSandboxUnavailable,
)
from qzdap_schema.ids import TenantId, UserId, WorkspaceId

from qzdap.modules.agent_runtime.application.ports import SkillPort


@dataclass(slots=True)
class SkillServiceAdapter(SkillPort):
    svc: SkillService
    tenant_id: TenantId
    workspace_id: WorkspaceId
    owner_id: UserId

    async def list_executable(self) -> list[dict]:
        return await self.svc.list_executable(workspace_id=self.workspace_id)

    async def invoke(
        self,
        *,
        call_id: UUID,
        skill_name: str,
        arguments: dict,
        confirmed: bool = False,
    ) -> dict:
        try:
            result = await self.svc.invoke_in_sandbox(
                workspace_id=self.workspace_id,
                name=skill_name,
                arguments=arguments,
                call_id=call_id,
                confirmed=confirmed,
            )
        except SkillNotFound:
            return {
                "ok": False,
                "error_code": "SKILL_NOT_FOUND",
                "error_message": f"skill {skill_name} not found",
                "call_id": str(call_id),
            }
        except SkillDisabled:
            return {
                "ok": False,
                "error_code": "SKILL_DISABLED",
                "error_message": f"skill {skill_name} is not published",
                "call_id": str(call_id),
            }
        except SkillNeedsConfirm:
            return {
                "ok": False,
                "error_code": "SKILL_NEEDS_CONFIRM",
                "error_message": f"skill {skill_name} requires confirmation",
                "call_id": str(call_id),
            }
        except SkillNotExecutable as exc:
            return {
                "ok": False,
                "error_code": "SKILL_NOT_EXECUTABLE",
                "error_message": str(exc),
                "call_id": str(call_id),
            }
        except SkillSandboxUnavailable as exc:
            return {
                "ok": False,
                "error_code": "SANDBOX_UNAVAILABLE",
                "error_message": str(exc),
                "call_id": str(call_id),
            }
        return {**result, "call_id": str(call_id)}


__all__ = ["SkillServiceAdapter"]
