"""LLM port adapter: saved models use tenant-scoped provider streaming."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from uuid import UUID

from qzdap_llm.client import ChatRequest, LLMChunk, LLMClient
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext

from qzdap.modules.agent_runtime.application.ports import LLMPort


@dataclass(slots=True, frozen=True)
class ModelInvocationMeta:
    """Compatibility projection of a real caller identity (never a system actor)."""

    tenant_id: str
    workspace_id: str | None = None
    principal_id: str | None = None


class LLMPortAdapter(LLMPort):
    def __init__(self, client: LLMClient, *, model_service=None) -> None:
        self._client = client
        self._model_service = model_service

    async def stream(
        self,
        req: ChatRequest,
        *,
        model_id: ModelId | None = None,
        actor: ActorContext | ModelInvocationMeta | None = None,
    ) -> AsyncIterator[LLMChunk]:
        if model_id is None:
            stream = self._client.stream(req)
        else:
            if self._model_service is None:
                raise RuntimeError("saved model requested but model service is unavailable")
            if actor is None or actor.principal_id is None:
                raise RuntimeError("saved model streaming requires a real caller actor context")
            if isinstance(actor, ModelInvocationMeta):
                actor = ActorContext(
                    tenant_id=UUID(actor.tenant_id),
                    workspace_id=UUID(actor.workspace_id) if actor.workspace_id else None,
                    principal_id=UUID(actor.principal_id),
                )
            if actor.principal_id.int == 0:
                raise RuntimeError("saved model streaming requires a real caller identity")
            stream = self._model_service.stream(actor=actor, model_id=model_id, req=req)
        async with aclosing(stream):
            async for chunk in stream:
                yield chunk


__all__ = ["LLMPortAdapter", "ModelInvocationMeta"]
