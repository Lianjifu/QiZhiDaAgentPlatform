"""HTTP adapter for admin skills + user catalog.

Routes (mounted as-is so the web client `/api/admin/skills` and
`/api/catalog/skills` do not need a rewrite):

  GET/POST     /api/admin/skills
  POST         /api/admin/skills/bulk
  GET/PATCH/DELETE /api/admin/skills/{id}
  GET          /api/catalog/skills
  GET          /api/catalog/skills/{id}
  POST         /api/catalog/skills/{id}/favorite
  POST         /api/catalog/skills/{id}/record-use
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from qzdap.modules.skill.application.services import SkillService


def _owner_id(request: Request, fallback: UUID) -> UUID:
    principal = getattr(request.state, "principal", None)
    pid = getattr(principal, "id", None)
    if pid is None:
        return fallback
    return UUID(str(pid))


async def skill_dependency(request: Request) -> SkillService:
    factory = getattr(request.app.state, "skill_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="skill factory not wired")
    sf = container.session_factory()
    async with sf.session() as session:
        svc = factory.for_session(session)
        try:
            yield svc
        except Exception:
            await session.rollback()
            raise
        await session.commit()


def build_router() -> APIRouter:
    router = APIRouter(tags=["skills"])

    @router.get("/api/admin/skills")
    async def list_admin_skills(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        type: str = Query(default="all"),
        status: str = Query(default="all"),
        q: str = Query(default=""),
        sort: str = Query(default="updated"),
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_admin(
            workspace_id=x_workspace_id,
            type_filter=type,
            status_filter=status,
            q=q,
            sort=sort,
        )

    @router.post("/api/admin/skills", status_code=201)
    async def create_admin_skill(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.post("/api/admin/skills/bulk")
    async def bulk_admin_skills(
        body: dict[str, Any],
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> dict[str, int]:
        actor = str(_owner_id(request, x_user_id))
        return await svc.bulk(
            ids=[str(item) for item in (body.get("ids") or [])],
            action=str(body.get("action") or "publish"),
            actor=actor,
        )

    @router.get("/api/admin/skills/{skill_id}")
    async def get_admin_skill(
        skill_id: UUID,
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_admin(skill_id)

    @router.patch("/api/admin/skills/{skill_id}")
    async def patch_admin_skill(
        skill_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        actor = str(_owner_id(request, x_user_id))
        return await svc.update(skill_id=skill_id, body=body, actor=actor)

    @router.delete("/api/admin/skills/{skill_id}")
    async def delete_admin_skill(
        skill_id: UUID,
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.delete(skill_id)

    @router.get("/api/catalog/skills")
    async def list_catalog_skills(
        request: Request,
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        user_id = _owner_id(request, x_user_id)
        return await svc.list_catalog(workspace_id=x_workspace_id, user_id=user_id)

    @router.get("/api/catalog/skills/{skill_id}")
    async def get_catalog_skill(
        skill_id: UUID,
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        user_id = _owner_id(request, x_user_id)
        return await svc.get_catalog(skill_id=skill_id, user_id=user_id)

    @router.post("/api/catalog/skills/{skill_id}/favorite")
    async def favorite_catalog_skill(
        skill_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        user_id = _owner_id(request, x_user_id)
        return await svc.set_favorite(
            skill_id=skill_id, user_id=user_id, on=bool(body.get("on"))
        )

    @router.post("/api/catalog/skills/{skill_id}/record-use")
    async def record_catalog_use(
        skill_id: UUID,
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        user_id = _owner_id(request, x_user_id)
        return await svc.record_use(skill_id=skill_id, user_id=user_id)

    @router.get("/api/user/skills")
    async def list_user_skills_alias(
        request: Request,
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: SkillService = Depends(skill_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        user_id = _owner_id(request, x_user_id)
        return await svc.list_catalog(workspace_id=x_workspace_id, user_id=user_id)

    return router
