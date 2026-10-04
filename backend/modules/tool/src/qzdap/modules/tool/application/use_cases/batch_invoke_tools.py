"""Use case: batch-invoke N tools concurrently; return per-item status.

Each call is dispatched independently via `InvokeToolUseCase`. Successful
items become status=200 with their `result`; domain errors (ToolNotFound /
ToolDisabled / ToolCallTimeout / UpstreamUnavailable) become status =
error.status with a small `error` envelope. Unexpected exceptions become
status=500 + INTERNAL_ERROR. The batch never fails as a whole.

Each batch item runs on its OWN ToolService + DB session. SQLAlchemy's
async session does not permit concurrent operations on a shared session
("this Session is provisioning a new connection"), so we cannot
`asyncio.gather` over a single service. The `service_factory` argument
opens a fresh service per item; in the composition root this is wired
to `container.session_factory()` + `_ToolFactory.for_session`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qzdap.modules.tool.application.tool_factory import ToolServiceFactory
from qzdap.modules.tool.domain import ToolCall
from qzdap.modules.tool.domain.errors import (
    InvalidToolSpec,
    ToolCallTimeout,
    ToolDisabled,
    ToolError,
    ToolNotFound,
    UpstreamUnavailable,
)


@dataclass(slots=True, frozen=True)
class BatchInvokeInput:
    tool_name: str
    arguments: dict


@dataclass(slots=True, frozen=True)
class BatchInvokeResultItem:
    tool_name: str
    status: int
    result: dict | None
    error: dict | None
    latency_ms: int | None


_STATUS_FROM_ERROR: dict[type, int] = {
    ToolNotFound: 404,
    ToolDisabled: 409,
    InvalidToolSpec: 422,
    UpstreamUnavailable: 502,
    ToolCallTimeout: 504,
}


async def _run_one(
    service_factory: ToolServiceFactory,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    owner_id: UUID,
    tool_name: str,
    arguments: dict,
) -> ToolCall:
    """Open a fresh service and execute a single invoke.

    The session inside the service is committed on success or rolled
    back on exception; the next batch item then opens its own.
    """
    async with service_factory() as svc:
        return await svc.invoke_tool().execute(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            tool_name=tool_name,
            arguments=arguments,
        )


class BatchInvokeToolsUseCase:
    def __init__(self, service_factory: ToolServiceFactory) -> None:
        self._service_factory = service_factory

    async def execute(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        calls: list[BatchInvokeInput],
    ) -> list[BatchInvokeResultItem]:
        if not calls:
            return []

        coros = [
            _run_one(
                self._service_factory,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
                tool_name=c.tool_name,
                arguments=c.arguments,
            )
            for c in calls
        ]
        outcomes: list[Any] = await asyncio.gather(*coros, return_exceptions=True)

        results: list[BatchInvokeResultItem] = []
        for inp, outcome in zip(calls, outcomes, strict=True):
            if isinstance(outcome, ToolCall):
                results.append(
                    BatchInvokeResultItem(
                        tool_name=inp.tool_name,
                        status=200,
                        result=outcome.result,
                        error=None,
                        latency_ms=outcome.latency_ms,
                    )
                )
                continue
            if isinstance(outcome, ToolError):
                status = _STATUS_FROM_ERROR.get(type(outcome), 400)
                results.append(
                    BatchInvokeResultItem(
                        tool_name=inp.tool_name,
                        status=status,
                        result=None,
                        error={"code": outcome.code, "message": str(outcome)},
                        latency_ms=None,
                    )
                )
                continue
            if isinstance(outcome, BaseException):
                results.append(
                    BatchInvokeResultItem(
                        tool_name=inp.tool_name,
                        status=500,
                        result=None,
                        error={"code": "INTERNAL_ERROR", "message": str(outcome)},
                        latency_ms=None,
                    )
                )
                continue
            # Defensive — `gather(return_exceptions=True)` shouldn't yield non-Exception.
            results.append(
                BatchInvokeResultItem(
                    tool_name=inp.tool_name,
                    status=500,
                    result=None,
                    error={"code": "INTERNAL_ERROR", "message": "unknown outcome"},
                    latency_ms=None,
                )
            )
        return results
