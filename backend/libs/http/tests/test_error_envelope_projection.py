"""错误信封的**文案投影**（Gateway Stage 0 · G-02 的 http 投放面）。

**为什么要有它**：没有自定义消息的领域异常，信封里装的是**裸码**
（`AppError.__init__` 是 `message or self.code`）—— 裸码对调用方毫无意义。
投影表给出一句话，**码仍然在 `code` 字段里**（机器可读的那部分不变）。
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from qzdap_http.error_envelope import error_envelope_middleware
from qzdap_kernel.errors import ForbiddenError
from qzdap_schema.dtos.errors import ErrorCode


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(BaseHTTPMiddleware, dispatch=error_envelope_middleware)  # type: ignore[arg-type]

    @app.get("/boom")
    async def boom() -> dict:
        # **不带消息** —— `AppError.__init__` 是 `message or self.code`，
        # 于是信封里本来会是裸码（正是投影要治的病）。
        raise ForbiddenError()

    @app.get("/specific")
    async def specific() -> dict:
        raise ForbiddenError("channel 42 does not belong to this workspace")

    return app


async def test_a_code_without_a_custom_message_gets_the_projected_copy() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_app()), base_url="http://testserver"
    ) as client:
        resp = await client.get("/boom")

    body = resp.json()
    assert resp.status_code == 403
    assert body["code"] == "FORBIDDEN"
    assert body["message"] == "无权访问该资源"


async def test_a_specific_message_is_never_replaced() -> None:
    """有具体消息就用具体的 —— 投影文案只兜底，不覆盖有用的细节。"""
    async with AsyncClient(
        transport=ASGITransport(app=_app()), base_url="http://testserver"
    ) as client:
        resp = await client.get("/specific")

    body = resp.json()
    assert body["message"] == "channel 42 does not belong to this workspace"


async def test_the_projected_copy_is_used_for_a_known_code() -> None:
    """码已知 → 用它自己的投影文案（不是通用兜底）。"""
    from qzdap_schema.dtos.errors import project_error

    async with AsyncClient(
        transport=ASGITransport(app=_app()), base_url="http://testserver"
    ) as client:
        resp = await client.get("/boom")

    assert resp.json()["message"] == project_error(ErrorCode.FORBIDDEN, "http")
