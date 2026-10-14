"""Authenticated console APIs backed by identity, membership and runtime rows."""

# FastAPI dependency declarations intentionally use Depends/File defaults.
# ruff: noqa: B008

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.identity.adapter.persistence.control_models import (
    IdentityControlAuditORM,
    WorkspaceInvitationORM,
)
from qzdap.modules.identity.adapter.persistence.models import (
    UserORM,
    UserWorkspaceORM,
    WorkspaceORM,
)


def actor(request: Request):
    principal = getattr(request.state, "principal", None)
    principal = getattr(principal, "principal", principal)
    if principal is None or getattr(principal, "type", None) != "user":
        raise HTTPException(401, "authenticated user required")
    for header, expected in [
        ("x-tenant-id", principal.tenant_id),
        ("x-user-id", principal.id),
        ("x-workspace-id", principal.workspace_id),
    ]:
        value = request.headers.get(header)
        if value and expected is not None and value != str(expected):
            raise HTTPException(403, "identity scope mismatch")
    return principal


async def control_session(request: Request):
    actor(request)
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(503, "database not configured")
    async with container.session_factory().session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def current_user(request, session):
    principal = actor(request)
    user = await session.scalar(
        select(UserORM).where(
            UserORM.id == principal.id,
            UserORM.tenant_id == principal.tenant_id,
            UserORM.status == "active",
        )
    )
    if user is None:
        raise HTTPException(403, "active user not found")
    return user


async def workspace_access(request, session, *, admin=False):
    principal = actor(request)
    raw = request.headers.get("x-workspace-id") or principal.workspace_id
    try:
        workspace_id = UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "workspace required") from exc
    workspace = await session.scalar(
        select(WorkspaceORM).where(
            WorkspaceORM.id == workspace_id,
            WorkspaceORM.tenant_id == principal.tenant_id,
            WorkspaceORM.status == "active",
        )
    )
    if workspace is None:
        raise HTTPException(404, "workspace not found")
    member = await session.scalar(
        select(UserWorkspaceORM).where(
            UserWorkspaceORM.tenant_id == principal.tenant_id,
            UserWorkspaceORM.workspace_id == workspace_id,
            UserWorkspaceORM.user_id == principal.id,
        )
    )
    elevated = bool(set(principal.roles) & {"platform_admin", "tenant_admin"})
    if member is None and not elevated:
        raise HTTPException(403, "workspace membership required")
    if (
        admin
        and not elevated
        and member.role
        not in {"admin", "owner", "管理员", "workspace_admin", "workspace_owner"}
    ):
        raise HTTPException(403, "workspace administrator required")
    return workspace_id


class AccountSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    displayName: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=255)
    language: str = Field(default="zh-CN", pattern="^(zh-CN|en-US)$")
    digest: bool = False
    taskAlert: bool = False

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("invalid email")
        return value


class Invitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=255)
    role: str = "成员"
    team: str = Field(default="", max_length=120)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        return AccountSettings.valid_email(value)

    @field_validator("role")
    @classmethod
    def valid_role(cls, value):
        roles = {
            "成员": "member",
            "管理员": "admin",
            "member": "member",
            "admin": "admin",
        }
        if value not in roles:
            raise ValueError("unsupported invitation role")
        return roles[value]


def settings_dict(user):
    prefs = (user.metadata_ or {}).get("accountSettings") or {}
    return {
        "displayName": user.display_name,
        "email": user.email,
        "language": prefs.get("language", "zh-CN"),
        "digest": bool(prefs.get("digest", False)),
        "taskAlert": bool(prefs.get("taskAlert", False)),
    }


def add_audit(session, request, user, workspace_id, action, payload):
    session.add(
        IdentityControlAuditORM(
            id=uuid4(),
            tenant_id=actor(request).tenant_id,
            workspace_id=workspace_id,
            actor_id=user.id,
            actor_name=user.display_name,
            action=action,
            payload=payload,
        )
    )


def build_account_router():
    router = APIRouter(tags=["account"])

    @router.get("/api/account/settings")
    async def get_settings(
        request: Request, session: AsyncSession = Depends(control_session)
    ):
        return settings_dict(await current_user(request, session))

    @router.put("/api/account/settings")
    async def put_settings(
        body: AccountSettings,
        request: Request,
        session: AsyncSession = Depends(control_session),
    ):
        user = await current_user(request, session)
        duplicate = await session.scalar(
            select(UserORM.id).where(
                UserORM.tenant_id == user.tenant_id,
                UserORM.email == body.email,
                UserORM.id != user.id,
            )
        )
        if duplicate:
            raise HTTPException(409, "email already registered")
        user.display_name = body.displayName.strip()
        if not user.display_name:
            raise HTTPException(422, "displayName cannot be blank")
        user.email = body.email
        user.metadata_ = {
            **(user.metadata_ or {}),
            "accountSettings": body.model_dump(exclude={"displayName", "email"}),
        }
        add_audit(
            session,
            request,
            user,
            None,
            "account.settings.updated",
            {"fields": list(AccountSettings.model_fields)},
        )
        await session.flush()
        return settings_dict(user)

    @router.get("/api/workspaces/current/members")
    async def members(
        request: Request, session: AsyncSession = Depends(control_session)
    ):
        user = await current_user(request, session)
        workspace_id = await workspace_access(request, session)
        rows = (
            await session.execute(
                select(UserORM, UserWorkspaceORM)
                .join(UserWorkspaceORM, UserORM.id == UserWorkspaceORM.user_id)
                .where(
                    UserORM.tenant_id == user.tenant_id,
                    UserWorkspaceORM.tenant_id == user.tenant_id,
                    UserWorkspaceORM.workspace_id == workspace_id,
                    UserORM.status != "deleted",
                )
                .order_by(UserORM.display_name)
            )
        ).all()
        return [
            {
                "id": str(member.id),
                "name": member.display_name,
                "email": member.email,
                "role": "管理员"
                if link.role in {"admin", "owner", "workspace_admin", "workspace_owner"}
                else "成员",
                "team": (member.metadata_ or {}).get("team", ""),
                "status": member.status,
            }
            for member, link in rows
        ]

    @router.post("/api/workspaces/current/members/invite", status_code=201)
    async def invite(
        body: Invitation,
        request: Request,
        session: AsyncSession = Depends(control_session),
    ):
        user = await current_user(request, session)
        workspace_id = await workspace_access(request, session, admin=True)
        already_member = await session.scalar(
            select(UserORM.id)
            .join(UserWorkspaceORM, UserORM.id == UserWorkspaceORM.user_id)
            .where(
                UserORM.tenant_id == user.tenant_id,
                UserWorkspaceORM.tenant_id == user.tenant_id,
                UserWorkspaceORM.workspace_id == workspace_id,
                UserORM.email == body.email,
            )
        )
        pending = await session.scalar(
            select(WorkspaceInvitationORM.id).where(
                WorkspaceInvitationORM.tenant_id == user.tenant_id,
                WorkspaceInvitationORM.workspace_id == workspace_id,
                WorkspaceInvitationORM.email == body.email,
            )
        )
        if already_member or pending:
            raise HTTPException(409, "member or invitation already exists")
        item = WorkspaceInvitationORM(
            id=uuid4(),
            tenant_id=user.tenant_id,
            workspace_id=workspace_id,
            email=body.email,
            role=body.role,
            team=body.team,
            invited_by=user.id,
            status="pending",
        )
        session.add(item)
        add_audit(
            session,
            request,
            user,
            workspace_id,
            "workspace.invitation.created",
            {"email": body.email, "role": body.role},
        )
        try:
            await session.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "invitation already exists") from exc
        return {
            "id": str(item.id),
            "workspaceId": str(workspace_id),
            "email": item.email,
            "role": item.role,
            "team": item.team,
            "status": "pending",
            "deliveryStatus": "not_configured",
        }

    @router.post("/api/workspaces/current/invitations/{invitation_id}/accept")
    async def accept_invitation(
        invitation_id: UUID,
        request: Request,
        session: AsyncSession = Depends(control_session),
    ):
        user = await current_user(request, session)
        invitation = await session.scalar(
            select(WorkspaceInvitationORM)
            .where(
                WorkspaceInvitationORM.id == invitation_id,
                WorkspaceInvitationORM.tenant_id == user.tenant_id,
                WorkspaceInvitationORM.email == user.email,
                WorkspaceInvitationORM.status == "pending",
            )
            .with_for_update()
        )
        if invitation is None:
            raise HTTPException(404, "pending invitation not found for this account")
        existing = await session.scalar(
            select(UserWorkspaceORM).where(
                UserWorkspaceORM.tenant_id == user.tenant_id,
                UserWorkspaceORM.workspace_id == invitation.workspace_id,
                UserWorkspaceORM.user_id == user.id,
            )
        )
        if existing is None:
            session.add(
                UserWorkspaceORM(
                    id=uuid4(),
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    workspace_id=invitation.workspace_id,
                    role=invitation.role,
                )
            )
        invitation.status = "accepted"
        add_audit(
            session,
            request,
            user,
            invitation.workspace_id,
            "workspace.invitation.accepted",
            {"invitationId": str(invitation.id)},
        )
        await session.flush()
        return {
            "id": str(invitation.workspace_id),
            "workspaceId": str(invitation.workspace_id),
            "role": invitation.role,
            "status": "active",
        }

    @router.get("/api/admin/settings/audit")
    async def audit(request: Request, session: AsyncSession = Depends(control_session)):
        user = await current_user(request, session)
        workspace_id = await workspace_access(request, session, admin=True)
        rows = (
            await session.scalars(
                select(IdentityControlAuditORM)
                .where(
                    IdentityControlAuditORM.tenant_id == user.tenant_id,
                    (IdentityControlAuditORM.workspace_id == workspace_id)
                    | (
                        IdentityControlAuditORM.workspace_id.is_(None)
                        & IdentityControlAuditORM.action.like("platform.settings.%")
                    ),
                    IdentityControlAuditORM.created_at
                    >= datetime.now(UTC) - timedelta(days=7),
                )
                .order_by(IdentityControlAuditORM.created_at.desc())
                .limit(200)
            )
        ).all()
        return [
            {
                "time": row.created_at.isoformat(),
                "actor": row.actor_name,
                "action": row.action,
                "result": "success",
                "id": str(row.id),
            }
            for row in rows
        ]

    @router.get("/api/home/insights")
    async def insights(
        request: Request,
        range: str = Query(default="近 7 天"),
        session: AsyncSession = Depends(control_session),
    ):
        from qzdap.modules.agent_runtime.adapter.persistence.models import (
            SessionORM,
            TurnORM,
        )

        user = await current_user(request, session)
        workspace_id = await workspace_access(request, session)
        now = datetime.now(UTC)
        if range == "本季度":
            start = now.replace(
                month=((now.month - 1) // 3) * 3 + 1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        elif range in {"近 7 天", "近 30 天"}:
            start = now - timedelta(days=7 if range == "近 7 天" else 30)
        else:
            raise HTTPException(422, "unsupported insight range")
        rows = (
            await session.execute(
                select(TurnORM, SessionORM)
                .join(SessionORM, TurnORM.session_id == SessionORM.id)
                .where(
                    TurnORM.tenant_id == user.tenant_id,
                    SessionORM.tenant_id == user.tenant_id,
                    TurnORM.workspace_id == workspace_id,
                    SessionORM.workspace_id == workspace_id,
                    SessionORM.owner_id == user.id,
                    TurnORM.started_at >= start,
                    TurnORM.started_at <= now,
                )
                .order_by(TurnORM.started_at)
            )
        ).all()
        daily = {}
        for turn, _ in rows:
            day = turn.started_at.strftime("%m-%d")
            entry = daily.setdefault(
                day, {"label": day, "tasks": 0, "completed": 0, "total": 0}
            )
            entry["total"] += 1
            if turn.status == "succeeded":
                entry["completed"] += 1
                entry["tasks"] += 1
        points = [
            {
                "label": day,
                "tasks": data["tasks"],
                "value": round(100 * data["completed"] / data["total"]),
            }
            for day, data in daily.items()
        ]
        outcomes = [
            {
                "title": turn.user_input[:120],
                "meta": turn.started_at.isoformat(),
                "type": "agent_turn",
                "status": turn.status,
            }
            for turn, _ in rows[-20:]
        ]
        return {"points": points, "scenarios": [], "outcomes": outcomes, "range": range}

    return router
