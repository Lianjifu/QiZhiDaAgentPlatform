"""Agent factory module — AgentTemplate / AgentVersion / Release management.

P8 of doc 12 (实施计划 §12).  Owns the version lifecycle:

- CreateTemplate → 持久化 AgentTemplate
- CreateVersion (draft) → 在模板下创建不可变 draft 版本
- PublishVersion (draft → published) → 一次性 commit；之后版本只读
- ReleaseVersion (published → released) → 必须通过 eval gate (EVAL_GATE_FAILED → 422)

Release 校验由 ``ReleaseAgentVersionUseCase`` 在内部完成 — 调
``EvaluationQueryPort.latest_passed_run`` 拉取最新通过评测；score < threshold
或缺失 → 拒绝发布。
"""

from __future__ import annotations

__all__: list[str] = []
