"""Remaining admin document contracts, bound through closures (never query params)."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from qzdap.modules.platform.adapter.http.ops_router import _patch_body, ops_dependency
from qzdap.modules.platform.application.ops_service import AdminOpsService

Tenant = Annotated[UUID, Header(alias="X-Tenant-Id")]
Workspace = Annotated[UUID, Header(alias="X-Workspace-Id")]
Service = Annotated[AdminOpsService, Depends(ops_dependency)]

RESOURCES = {
    "evaluations/suites": "evaluations.suites",
    "regressions/tracks": "regressions.tracks",
    "regressions/alerts": "regressions.alerts",
    "feedback": "feedback.list",
    "feedback/rules": "feedback.rules",
    "audit/entries": "audit.entries",
    "audit/risks": "audit.risks",
    "audit/rules": "audit.rules",
    "operations/sessions": "operations.sessions",
    "operations/incidents": "operations.incidents",
    "metrics/dashboards": "metrics.dashboards",
    "metrics/thresholds": "metrics.thresholds",
}


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, "document not found")
    if isinstance(exc, NotImplementedError):
        return HTTPException(503, str(exc))
    return HTTPException(422, str(exc))


def _crud(collection: str, operation: str):
    if operation == "patch":
        async def patch(doc_id: str, body: dict[str, Any], x_tenant_id: Tenant, x_workspace_id: Workspace, svc: Service) -> dict[str, Any]:
            try:
                return await svc.patch(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, doc_key=doc_id, patch=_patch_body(body))
            except (KeyError, ValueError) as exc:
                raise _error(exc) from exc
        return patch
    async def delete(doc_id: str, x_tenant_id: Tenant, x_workspace_id: Workspace, svc: Service) -> Response:
        if not await svc.delete(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, doc_key=doc_id):
            raise HTTPException(404, "document not found")
        return Response(status_code=204)
    return delete


def _batch(collection: str, action: str):
    async def batch(body: dict[str, Any], request: Request, x_tenant_id: Tenant, x_workspace_id: Workspace, svc: Service) -> dict[str, Any]:
        ids = body.get("ids")
        if collection == "operations.incidents" and body.get("sessionIds") is not None:
            sessions = body["sessionIds"]
            rows = await svc.list_collection(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection)
            ids = [row["id"] for row in rows if row.get("sessionId") in sessions]
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
            raise HTTPException(422, "ids must be an array of strings")
        ids = list(dict.fromkeys(ids))
        try:
            if action == "delete":
                return await svc.batch_delete(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, ids=ids)
            if action == "run":
                # Validate every target before starting work; the request owns the
                # transaction and returns measured results, never a fictitious queue.
                for doc_id in ids:
                    await svc.validate_run(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, doc_key=doc_id)
                results = [await svc.run_collection(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, doc_key=doc_id, runner=getattr(request.app.state, "catalog_evaluation_runner", None), owner_id=_owner(request)) for doc_id in ids]
                return {"updated": len(results), "results": results}
            if collection == "operations.incidents":
                patch = {"resolved": True}
            elif action in {"enable", "disable"}:
                patch = {"enabled": action == "enable"}
            else:
                status = {"resolve": "stable" if collection == "regressions.tracks" else "resolved", "triage": "triaged", "investigate": "investigating", "review": "reviewed"}[action]
                patch = {"status": status}
            return await svc.batch_patch(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, ids=ids, patch=patch)
        except (KeyError, ValueError, NotImplementedError) as exc:
            raise _error(exc) from exc
    return batch


def _owner(request: Request) -> UUID:
    principal = getattr(request.state, "principal", None)
    user_id = getattr(principal, "id", None) or request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(401, "user identity required for execution")
    try:
        return UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(422, "invalid user identity") from exc


def _import(collection: str, prefix: str):
    async def import_docs(body: dict[str, Any], x_tenant_id: Tenant, x_workspace_id: Workspace, svc: Service) -> dict[str, int]:
        try:
            return await svc.import_docs(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, content=body.get("content", ""), format=body.get("format", "json"), prefix=prefix)
        except (ValueError, TypeError) as exc:
            raise _error(exc) from exc
    return import_docs


def _detail(collection: str, field: str):
    async def detail(doc_id: str, x_tenant_id: Tenant, x_workspace_id: Workspace, svc: Service) -> Any:
        try:
            row = await svc.get(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, doc_key=doc_id)
        except KeyError as exc:
            raise _error(exc) from exc
        return row.get(field, None if field == "response" else [])
    return detail


def _action(collection: str, action: str):
    async def perform(doc_id: str, request: Request, x_tenant_id: Tenant, x_workspace_id: Workspace, svc: Service, body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            if action == "duplicate":
                return await svc.duplicate(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, doc_key=doc_id, prefix=collection.split('.')[-1])
            if action == "run":
                return await svc.run_collection(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, doc_key=doc_id, runner=getattr(request.app.state, "catalog_evaluation_runner", None), owner_id=_owner(request))
            return await svc.action(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection=collection, doc_key=doc_id, action=action, body=body)
        except (KeyError, ValueError, NotImplementedError) as exc:
            raise _error(exc) from exc
    return perform


def build_mutation_router() -> APIRouter:
    router = APIRouter(tags=["admin-ops"])
    def add(path, endpoint, method, status=200):
        endpoint.__name__ = f"{method.lower()}_{path.replace('/', '_').replace('-', '_')}"
        router.add_api_route('/api/admin/' + path, endpoint, methods=[method], status_code=status)

    # Register literal actions before generic document IDs of the same method.
    for resource, actions in {
        "evaluations/suites": ("run", "delete"),
        "regressions/tracks": ("investigate", "resolve", "delete"),
        "feedback": ("triage", "resolve", "delete"),
        "audit/entries": ("resolve", "review"),
        "operations/incidents": ("resolve",),
        "metrics/dashboards": ("enable", "disable", "delete"),
    }.items():
        for action in actions:
            path = resource + ("/bulk-delete" if resource == "evaluations/suites" and action == "delete" else f"/batch-{action}")
            add(path, _batch(RESOURCES[resource], action), "POST")
            if path.endswith('/bulk-delete'):
                add(path, _batch(RESOURCES[resource], action), "DELETE")
    for resource, prefix in {
        "evaluations/suites": "suite", "regressions/tracks": "track", "feedback": "fb",
        "quotas/budgets": "bg", "notifications/channels": "ch", "metrics/dashboards": "db",
        "operations/incidents": "incident",
    }.items():
        collection = RESOURCES.get(resource, resource.replace('/', '.'))
        add(resource + '/import', _import(collection, prefix), 'POST')
    for resource, collection in RESOURCES.items():
        add(resource + '/{doc_id}', _crud(collection, 'patch'), 'PATCH')
        add(resource + '/{doc_id}', _crud(collection, 'delete'), 'DELETE', 204)
    for resource, fields in {
        "evaluations/suites": ('history',), "regressions/tracks": ('history',), "feedback": ('history',),
        "quotas/budgets": ('history',), "operations/sessions": ('context', 'logs'), "audit/entries": ('logs', 'response'),
    }.items():
        for field in fields:
            add(f'{resource}/{{doc_id}}/{field}', _detail(RESOURCES.get(resource, resource.replace('/', '.')), field), 'GET')
    for resource, actions in {"evaluations/suites": ('run', 'duplicate'), "regressions/tracks": ('run', 'duplicate'), "feedback": ('reply',), "audit/entries": ('resolve',), "operations/incidents": ('resolve',)}.items():
        for action in actions:
            add(f'{resource}/{{doc_id}}/{action}', _action(RESOURCES[resource], action), 'POST')

    @router.get('/api/admin/evaluations/templates')
    async def templates(x_tenant_id: Tenant, x_workspace_id: Workspace, svc: Service) -> list[dict[str, Any]]:
        return await svc.list_collection(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection='evaluations.templates')

    @router.post('/api/admin/audit/scopes/review')
    async def review(body: dict[str, Any], x_tenant_id: Tenant, x_workspace_id: Workspace, svc: Service) -> dict[str, int]:
        role = str(body.get('role') or '').strip()
        if not role:
            raise HTTPException(422, 'role required')
        rows = await svc.list_collection(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection='audit.scopes')
        ids = [row['id'] for row in rows if row.get('role') == role]
        return await svc.batch_patch(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection='audit.scopes', ids=ids, patch={'reviewed': True})

    @router.post('/api/admin/audit/investigations', status_code=201)
    async def investigation(x_tenant_id: Tenant, x_workspace_id: Workspace, svc: Service, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return await svc.create(tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection='audit.investigations', prefix='investigation', body={**(body or {}), 'status': 'open'})
    return router
