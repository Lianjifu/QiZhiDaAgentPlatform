"""HTTP DTOs for the agent runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    agent_version: str = Field(min_length=1, max_length=64)
    metadata: dict = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    agent_id: UUID
    agent_version: str
    status: Literal["open", "closed"]
    created_at: datetime
    closed_at: datetime | None = None
    metadata: dict


class RunTurnRequest(BaseModel):
    content: str = Field(min_length=1, max_length=64_000)
    model: str | None = Field(default=None, max_length=128)
    metadata: dict = Field(default_factory=dict)


class TurnResponse(BaseModel):
    id: UUID
    session_id: UUID
    status: Literal["running", "succeeded", "failed", "denied"]
    started_at: datetime
    finished_at: datetime | None = None
    final_response: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: str | None = None


class InteractiveAnswerRequest(BaseModel):
    """User's response to a frontend-coupled stub tool (ask_user_question /
    plan_submit / todo_write / delegate_to_agent).

    The stub tool has already returned a synthetic answer to the LLM (so
    the LLM stream continues without pause). The frontend posts the user's
    *real* answer here so the platform can:
      - write an audit row (action=tool.interactive_answer)
      - surface the answer in the session transcript (for replay)
    The frontend then drives a follow-up user turn (calling
    POST /api/sessions/{id}/turns/stream) so the LLM is told the
    user's actual pick in the next turn.
    """
    call_id: str = Field(min_length=1, max_length=128)
    action: Literal["show_question_card", "toast", "render_plan",
                    "render_todo_list", "delegate_agent"]
    payload: dict = Field(default_factory=dict)
