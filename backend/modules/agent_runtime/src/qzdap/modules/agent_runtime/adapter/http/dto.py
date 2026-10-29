"""HTTP DTOs for the agent runtime.

⚠️ 这里只留 **`/api/sessions*`** 还在用的形状 —— 旧的 `/v1/sessions*`
（`CreateSessionRequest` / `SessionResponse` / `RunTurnRequest` /
`TurnResponse`）随 Gateway Stage 5 的删除一并清掉（台账 G7 / G8）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InteractiveAnswerRequest(BaseModel):
    """User's response to a frontend-coupled stub tool (ask_user_question /
    plan_submit / todo_write / delegate_agent).

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
    action: Literal[
        "show_question_card",
        "toast",
        "render_plan",
        "render_todo_list",
        "delegate_agent",
    ]
    payload: dict = Field(default_factory=dict)


__all__ = ["InteractiveAnswerRequest"]
