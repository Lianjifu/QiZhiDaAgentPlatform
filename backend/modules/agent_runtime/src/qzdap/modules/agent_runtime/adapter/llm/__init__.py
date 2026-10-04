"""LLM port adapter — wraps `qzdap_llm.LLMClient.stream` so the application
layer sees a clean `LLMPort` ABC instead of an LLMClient concrete type.

Single seam: swap implementations in composition root (`container.llm_client()`
returns a `MockLLMClient` in dev/test, `OpenAICompatibleClient` in staging,
`LLMRouter` for failover). The use cases don't care.

P6: when ``model_id`` is supplied, delegate to ``ModelService.invoke`` so
the per-tenant registry drives credential decryption, routing, and quota
tracking. When ``model_id`` is ``None``, fall back to the injected
``LLMClient`` (preserves P0–P5 behavior).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from qzdap.modules.model.application.services import ModelService
from qzdap_llm.client import ChatRequest, LLMChunk, LLMClient
from qzdap_schema.ids import ModelId

from qzdap.modules.agent_runtime.application.ports import LLMPort


@dataclass(slots=True, frozen=True)
class ModelInvocationMeta:
    """Lightweight caller context used by ModelService.invoke().

    The agent_runtime owns its own actor resolution (auth middleware); the
    adapter threads the resulting identity through to the model layer
    without leaking the kernel's ``ActorContext`` type into the model
    module's domain.
    """

    tenant_id: str
    workspace_id: str | None = None
    principal_id: str | None = None


class LLMPortAdapter(LLMPort):
    def __init__(
        self,
        client: LLMClient,
        *,
        model_service: ModelService | None = None,
    ) -> None:
        self._client = client
        self._model_service = model_service

    async def stream(
        self,
        req: ChatRequest,
        *,
        model_id: ModelId | None = None,
        actor: ModelInvocationMeta | None = None,
    ) -> AsyncIterator[LLMChunk]:
        if model_id is None or self._model_service is None:
            async for chunk in self._client.stream(req):
                yield chunk
            return

        if actor is None:
            raise RuntimeError(
                "model_id was supplied without an actor context; "
                "ModelService.invoke requires tenant scope"
            )

        from qzdap_vault.actor import ActorContext

        model_actor = ActorContext(
            tenant_id=UUID(actor.tenant_id),  # type: ignore[arg-type]
            workspace_id=UUID(actor.workspace_id) if actor.workspace_id else None,  # type: ignore[arg-type]
            principal_id=UUID(actor.principal_id) if actor.principal_id else None,  # type: ignore[arg-type]
            roles=frozenset({"agent"}),
        )
        resp = await self._model_service.invoke(
            actor=model_actor, model_id=model_id, req=req
        )
        yield LLMChunk(
            model=resp.model,
            delta=resp.message.content or "",
            finish_reason=resp.finish_reason,
            usage=resp.usage,
        )


__all__ = ["LLMPortAdapter", "ModelInvocationMeta"]
