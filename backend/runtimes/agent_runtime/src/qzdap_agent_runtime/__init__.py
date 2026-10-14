"""qzdap_agent_runtime — LangGraph-based agent runtime library.

见 docs/refactor/session-module-refactor-plan.md §3.1 / §7.2。
当前文件仅承载 Stage 4 + Stage 6b 范围内的 Deep Agents 启发式分类器
（§2.5 阻塞 6），其余 19 节点 + Postgres checkpointer + channel gateway
等由后续 Stage PR 补齐。
"""

from __future__ import annotations

__all__: list[str] = []