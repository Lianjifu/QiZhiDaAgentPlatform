"""**⑦ Agent Loop** —— 循环本体与它的部件 ✓。

依据：Agent 方案 §3（Agent Loop ✓）、§8.1（``agent_loop/*`` ✓）。

⚠️ **本包只放「部件」** ✓ —— 循环的编排（六个终止条件 ✓）归
``runner.py`` ✓（Stage 5 ✓）；图装配（LangGraph 6 节点 ✓）归 ``graph.py`` ✓
（Stage 5 ✓）。
"""

from .reason import Reasoner, ToolCallAccumulator

__all__ = ["Reasoner", "ToolCallAccumulator"]
