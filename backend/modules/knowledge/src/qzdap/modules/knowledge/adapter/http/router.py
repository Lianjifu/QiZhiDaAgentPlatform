"""HTTP adapter for admin knowledge + user catalog.

  GET/POST  /api/admin/knowledge/kbs
  GET       /api/admin/knowledge/kbs/{id}
  POST      /api/admin/knowledge/kbs/{id}/toggle-status
  POST      /api/admin/knowledge/kbs/__batch__
  GET/POST  /api/admin/knowledge/docs
  GET/POST  /api/admin/knowledge/sources
  GET       /api/admin/knowledge/tasks
  GET       /api/admin/knowledge/eval
  GET       /api/catalog/knowledge
  POST      /api/catalog/knowledge/__noop__/ask
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from qzdap.modules.knowledge.application.services import KnowledgeService


def _owner_label(request: Request) -> str:
    principal = getattr(request.state, "principal", None)
    name = getattr(principal, "display_name", None) or getattr(principal, "name", None)
    if name:
        return str(name)
    return "管理员"


async def knowledge_dependency(request: Request) -> KnowledgeService:
    factory = getattr(request.app.state, "knowledge_service_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="knowledge factory not wired")
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
    router = APIRouter(tags=["knowledge"])

    @router.get("/api/admin/knowledge/kbs")
    async def list_kbs(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_kbs(workspace_id=x_workspace_id)

    @router.post("/api/admin/knowledge/kbs", status_code=201)
    async def create_kb(
        body: dict[str, Any],
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_kb(
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            body=body,
            owner=_owner_label(request),
        )

    @router.post("/api/admin/knowledge/kbs/__batch__")
    async def batch_kbs(
        body: dict[str, Any],
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> dict[str, int]:
        return await svc.batch_kbs(
            ids=[str(item) for item in (body.get("ids") or [])],
            action=str(body.get("action") or "pause"),
        )

    @router.get("/api/admin/knowledge/kbs/{kb_id}")
    async def get_kb(
        kb_id: UUID,
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_kb(kb_id)

    @router.post("/api/admin/knowledge/kbs/{kb_id}/toggle-status")
    async def toggle_kb(
        kb_id: UUID,
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.toggle_kb_status(kb_id)

    @router.get("/api/admin/knowledge/docs")
    async def list_docs(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_docs(workspace_id=x_workspace_id)

    @router.post("/api/admin/knowledge/docs", status_code=201)
    async def ingest_doc(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.ingest_doc(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.get("/api/admin/knowledge/sources")
    async def list_sources(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_sources(workspace_id=x_workspace_id)

    @router.post("/api/admin/knowledge/sources", status_code=201)
    async def create_source(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_source(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.get("/api/admin/knowledge/tasks")
    async def list_tasks(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_tasks(workspace_id=x_workspace_id)

    @router.get("/api/admin/knowledge/eval")
    async def list_eval(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_eval_cases(workspace_id=x_workspace_id)

    @router.get("/api/catalog/knowledge")
    async def list_catalog(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_catalog(workspace_id=x_workspace_id)

    @router.post("/api/catalog/knowledge/__noop__/ask")
    async def ask_catalog(
        body: dict[str, Any],
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_tenant_id: UUID | None = Header(default=None, alias="X-Tenant-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.ask(
            workspace_id=x_workspace_id,
            question=str(body.get("question") or ""),
            tenant_id=x_tenant_id,
        )

    @router.get("/api/knowledge/docs")
    async def list_user_docs_alias(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: KnowledgeService = Depends(knowledge_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_catalog(workspace_id=x_workspace_id)

    return router
