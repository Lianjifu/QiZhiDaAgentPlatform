"""HTTP adapter package.

⚠️ 这里**不再导出** `build_router` —— 旧的 `/v1/sessions*` 路由随 Gateway
Stage 5 删除（台账 G7 / G8）；会话 API 的入口是
`adapter.http.session_router.build_session_router`。
"""

__all__: list[str] = []
