"""Use case: drain a ``RunTurnUseCase`` async generator to completion.

The orchestration ``SubAgentAdapter`` and the channel ``ChannelDispatchSubscriber``
both need the *final* outcome of a turn — not the streaming chunks.  This
use case pulls a single ``RunTurnUseCase.execute()`` stream to its terminal
``DoneChunk`` and packages a structured dict
``{final_message, turn_id, input_tokens, output_tokens}`` for callers.

Design notes
------------
- Streams the inner generator chunk-by-chunk; per-chunk overhead is
  constant so first-chunk latency is unchanged.
- ``ErrorChunk`` is converted into a terminal ``AppError`` so callers
  see a normal exception path instead of having to inspect the chunk
  stream.
- The use case does NOT itself touch the session / turn repos — those
  are owned by ``RunTurnUseCase``.  It only observes the chunk stream.
- Token totals are taken from the last ``UsageChunk`` (or from the
  persisted turn if the stream ends without one).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qzdap_kernel.errors import AppError
from qzdap_schema.dtos.turn import DoneChunk, ErrorChunk, TurnChunk, UsageChunk

from qzdap.modules.agent_runtime.application.use_cases.run_turn import (
    RunTurnUseCase,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class RunTurnCompletionResult:
    final_message: str | None
    turn_id: UUID
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class RunTurnCompletionUseCase:
    """Drain a single ``RunTurnUseCase.execute()`` to its terminal chunk."""

    def __init__(self, run_turn: RunTurnUseCase) -> None:
        self._run_turn = run_turn

    async def execute(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        session_id: UUID,
        user_input: str,
        model: str,
    ) -> RunTurnCompletionResult:
        stream: AsyncIterator[TurnChunk] = self._run_turn.execute(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            session_id=session_id,
            user_input=user_input,
            model=model,
        )

        final_message: str | None = None
        turn_id: UUID | None = None
        input_tokens = 0
        output_tokens = 0
        cache_read_tokens = 0
        cache_write_tokens = 0

        async for chunk in stream:
            if isinstance(chunk, DoneChunk):
                final_message = chunk.final_message
                turn_id = chunk.turn_id
            elif isinstance(chunk, UsageChunk):
                input_tokens = chunk.input_tokens
                output_tokens = chunk.output_tokens
                cache_read_tokens = chunk.cache_read_tokens
                cache_write_tokens = chunk.cache_write_tokens
                if turn_id is None:
                    turn_id = chunk.turn_id
            elif isinstance(chunk, ErrorChunk):
                raise AppError(
                    f"run_turn failed: {chunk.message}",
                    code=chunk.code,
                    status=500 if chunk.retriable else 400,
                )

        if turn_id is None:
            # Stream ended without any chunk — nothing to return.
            raise AppError(
                "run_turn produced no chunks; session may be closed",
                code="RUN_TURN_EMPTY_STREAM",
                status=500,
            )

        return RunTurnCompletionResult(
            final_message=final_message,
            turn_id=turn_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )


__all__ = ["RunTurnCompletionResult", "RunTurnCompletionUseCase"]
_ = (Any,)
