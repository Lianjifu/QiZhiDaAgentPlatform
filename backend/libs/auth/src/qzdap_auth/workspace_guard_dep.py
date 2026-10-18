"""FastAPI dependency: validate ``X-Workspace-Id`` header references a real,
active workspace in the request's tenant.

Background: an earlier seed/test script wrote ``admin_workflows`` and
``admin_knowledge_kbs`` rows with a hard-coded workspace id
(``00000000-...-0002``) that did NOT exist in the ``workspaces`` table.
Reads filter by ``x_workspace_id`` so the data silently disappeared from
the admin UI; the user could not see or recover it without a database
migration.

This dependency guards against the same shape of bug recurring: any write
endpoint that opts in (via ``dependencies=[Depends(_require_active_workspace)]``)
will reject requests whose ``X-Workspace-Id`` does not resolve to an
``active`` workspace inside the JWT-bound tenant.

Read endpoints (``GET``/``HEAD``/``OPTIONS``) skip the DB check — they are
filter-only and do not mutate state.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Header, HTTPException, Request


# HTTP methods that don't mutate state — DB lookup is skipped.
_READ_ONLY = frozenset({"GET", "HEAD", "OPTIONS"})


async def _require_active_workspace(
    request: Request,
    x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
) -> UUID:
    if request.method in _READ_ONLY:
        return x_workspace_id

    container = getattr(request.app.state, "container", None)
    if container is None:
        # Container not wired yet — fall through; route-level checks apply.
        return x_workspace_id

    principal = getattr(request.state, "principal", None)
    tenant_id = getattr(principal, "tenant_id", None)
    if tenant_id is None:
        # No JWT principal bound — let AuthMiddleware / route decide.
        return x_workspace_id

    # Lazy import: identity models live behind the composition root.
    from sqlalchemy import select

    from qzdap.modules.identity.adapter.persistence.models import WorkspaceORM

    session_factory = container.session_factory()
    async with session_factory.session() as session:
        workspace = await session.scalar(
            select(WorkspaceORM.id).where(
                WorkspaceORM.id == x_workspace_id,
                WorkspaceORM.tenant_id == tenant_id,
                WorkspaceORM.status == "active",
            )
        )
    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "E_WORKSPACE_NOT_FOUND",
                "message": (
                    f"workspace {x_workspace_id} not found or not active "
                    f"in tenant {tenant_id}"
                ),
            },
        )
    return x_workspace_id