"""Shared FastAPI dependencies for the identity module's HTTP router.

Kept in its own module so the main router and the auth/login subrouter can
both import without circularity.
"""

from __future__ import annotations

from fastapi import Request

from qzdap.modules.identity.application.services import IdentityService


async def get_identity_service(request: Request) -> IdentityService:
    """FastAPI dependency — opens a per-request session and binds an
    IdentityService to it for the lifetime of the request. The session is
    committed on success and rolled back on exception."""
    factory = getattr(request.app.state, "identity_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise RuntimeError("IdentityService factory not wired on app.state")
    sf = container.session_factory()
    async with sf.session() as session:
        svc = factory.for_session(session)
        request.state.identity_service = svc
        try:
            yield svc
        except Exception:
            await session.rollback()
            raise
        await session.commit()