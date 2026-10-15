"""In-memory mock LLM for dev + tests.

Deterministic echo with a configurable latency. Used by `MockLLMClient`.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from qzdap_llm.client import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LLMChunk,
    LLMClient,
    Usage,
)
from qzdap_llm.config import LLMConfig


# ---------------------------------------------------------------------------
# Round-7 触发词: 命中后通过 synthetic_chunks 注入 plan / artifact /
# workflow 事件, 让前端在 mock 模式下也能跑 UI 流程
# ---------------------------------------------------------------------------

_TRIGGERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"做.*?计划|做.*?规划|拆解成|分步|step\s*by\s*step|分阶段|做.*?方案|给我.*?计划|列.*?计划|列.*?步骤|怎么.*?做|如何.*?做"), "plan"),
    (re.compile(r"生成(一份|个|一篇)?(报告|文档|说明书|手册|方案|计划书|需求|纪要|模板)|写(一份|个|一篇)?(报告|文档|说明书|手册|模板)|(报告|文档|说明书|手册|计划书|纪要|模板)"), "artifact"),
    (re.compile(r"跑(一下|个)?(命令|脚本|shell|bash)?|执行(命令|脚本)|^\s*ls\s*$|^\s*pwd\s*$|^\s*whoami\s*$|^\s*echo\s|^\s*grep\s"), "workflow"),
]

_PLAN_TEMPLATES = [
    [
        {"id": "s1", "title": "梳理需求与边界", "description": "读取用户输入, 列出关键约束与产出标准", "kind": "ask"},
        {"id": "s2", "title": "检索相关知识", "description": "在知识库中查最相关的 5 条文档", "kind": "tool", "tool_name": "knowledge_search"},
        {"id": "s3", "title": "起草正文", "description": "用模型生成主文档", "kind": "subagent"},
        {"id": "s4", "title": "导出 Markdown", "description": "保存为 session_artifacts, 暴露下载端点", "kind": "tool", "tool_name": "write_markdown"},
    ],
    [
        {"id": "s1", "title": "明确输入输出", "description": "列出范围与角色", "kind": "ask"},
        {"id": "s2", "title": "拆解任务", "description": "把目标分成 3-5 个原子步骤", "kind": "subagent"},
        {"id": "s3", "title": "调用工具执行", "description": "对每个原子步骤调一个工具", "kind": "tool", "tool_name": "shell"},
        {"id": "s4", "title": "回写结果", "description": "汇总步骤结果, 反馈给用户", "kind": "tool", "tool_name": "write_markdown"},
    ],
]

_ARTIFACT_TEMPLATES = [
    (
        "新员工入职手册.md",
        "text/markdown",
        "# 新员工入职手册\n\n## 第一周目标\n- 熟悉团队成员与职责边界\n- 完成公司制度学习\n- 配置开发环境 (本机 + 远程)\n\n## 必读文档\n1. 公司愿景与价值观\n2. 工程规范与发布流程\n3. 客服/运营红线手册\n\n## 工具栈\n- 代码: VS Code + pnpm + uv\n- 沟通: 企智搭 + 飞书\n- 文档: 本工作区 / workspace\n",
    ),
    (
        "产品需求文档.md",
        "text/markdown",
        "# 产品需求文档 (PRD)\n\n## 背景\n随着企业知识沉淀规模扩大, 员工在检索文档时面临路径长、命中低的问题.\n\n## 目标\n为员工提供 1-3 步内可命中的知识检索体验, 7 天内新员工首查成功率 ≥ 80%.\n\n## 范围\n- 仅限本工作区已发布知识\n- 检索响应 ≤ 800ms (P95)\n- 引用必须可点击回源\n\n## 验收\n- GTM 上线 4 周内: 周活 ≥ 60%, 命中率 ≥ 70%\n- NSS ≥ 4.2/5\n",
    ),
    (
        "会议纪要模板.md",
        "text/markdown",
        "# 会议纪要\n\n## 一、会议信息\n| 项目 | 内容 |\n|---|---|\n| 主题 |  |\n| 时间 |  |\n| 主持人 |  |\n| 记录人 |  |\n\n## 二、决策项\n| 编号 | 决策 | 责任人 |\n|---|---|---|\n|  |  |  |\n\n## 三、待办事项\n| 编号 | 描述 | 责任人 | 截止 |\n|---|---|---|---|\n|  |  |  |  |\n\n## 四、风险与议题\n-  |\n\n## 五、下次会议\n- 时间:\n- 主题:\n",
    ),
]

_WORKFLOW_LOG = [
    ("pwd", "/workspace/qizhida-agent-platform"),
    ("ls", "frontend  backend  docs  README.md  .claude  bin"),
    ("whoami", "demo-user"),
    ("git status", "On branch main · working tree clean"),
]


class MockLLMClient(LLMClient):
    name = "mock"

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._cfg = config or LLMConfig()
        # 触发生成的产物落本地 (前端通过 download_path 拉取); 单进程内足够.
        self._artifact_dir = Path("/tmp/qzdap-mock-artifacts")
        self._artifact_dir.mkdir(parents=True, exist_ok=True)

    async def chat(self, req: ChatRequest) -> ChatResponse:
        await asyncio.sleep(self._cfg.mock_latency_ms / 1000)
        content = _mock_response_text(req.messages)
        return ChatResponse(
            model=req.model,
            message=ChatMessage(role="assistant", content=content),
            finish_reason="stop",
            usage=Usage(input_tokens=10, output_tokens=len(content) // 4),
            raw={"mock": True},
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        content = _mock_response_text(req.messages)
        for i, word in enumerate(content.split(" ")):
            await asyncio.sleep(
                self._cfg.mock_latency_ms / 1000 / max(len(content.split(" ")), 1)
            )
            yield LLMChunk(model=req.model, delta=word + " ")
        yield LLMChunk(model=req.model, delta="", finish_reason="stop")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Deterministic pseudo-embedding from text hash. NOT real semantics;
        # for tests only.
        out: list[list[float]] = []
        for t in texts:
            seed = abs(hash(t)) % (2**32)
            v = [(seed >> i & 0xFF) / 255.0 for i in range(8)]
            out.append(v + [0.0] * (self._cfg.embedding_dim - 8))
        return out

    # ------------------------------------------------------------------
    # Round-7: 触发词 → 注入 plan / artifact / workflow 事件
    # ------------------------------------------------------------------

    async def synthetic_chunks(
        self,
        user_input: str,
        *,
        turn_id: Any = None,
    ) -> list[dict]:
        """根据 user_input 触发词, 生成 0~3 个 chunk dict (kind + 字段).

        runner 会在 chat stream 完成后调用本方法, 把这些 chunk 转换为
        对应 TurnChunk 并 yield 到前端 SSE.
        """
        text = (user_input or "").strip()
        if not text:
            return []
        hits: list[str] = []
        for pattern, name in _TRIGGERS:
            if pattern.search(text):
                hits.append(name)
        if not hits:
            return []

        chunks: list[dict] = []
        for kind in hits:
            if kind == "plan":
                steps = _PLAN_TEMPLATES[hash(text) % len(_PLAN_TEMPLATES)]
                chunks.append(
                    {
                        "_kind": "plan_proposed",
                        "plan_id": str(uuid.uuid4()),
                        "title": f"为「{text[:24]}」生成的计划",
                        "steps": steps,
                        "reason": "按步执行, 任何一步可暂停/编辑/拒绝",
                    }
                )
            elif kind == "artifact":
                name_value, mime, body = _ARTIFACT_TEMPLATES[
                    hash(text) % len(_ARTIFACT_TEMPLATES)
                ]
                artifact_id = str(uuid.uuid4())
                # 落本地, 暴露给前端 blob 端点
                file_path = self._artifact_dir / f"{artifact_id}.md"
                file_path.write_text(body, encoding="utf-8")
                chunks.append(
                    {
                        "_kind": "artifact_ready",
                        "artifact_id": artifact_id,
                        "kind_": "markdown",
                        "name": name_value,
                        "mime": mime,
                        "size_bytes": len(body.encode("utf-8")),
                        "download_path": f"/api/artifacts/{artifact_id}/content",
                        "preview_path": None,
                        "snippet": body[:800],
                        "_local_path": str(file_path),
                    }
                )
            elif kind == "workflow":
                cmd, output = _WORKFLOW_LOG[hash(text) % len(_WORKFLOW_LOG)]
                # workflow_invocation (status=started) + tool_call (执行) + tool_result (回写)
                invocation_id = str(uuid.uuid4())
                chunks.append(
                    {
                        "_kind": "workflow_invocation",
                        "invocation_id": invocation_id,
                        "workflow_name": "shell-runner",
                        "status": "started",
                    }
                )
                chunks.append(
                    {
                        "_kind": "tool_call",
                        "tool_call_id": invocation_id,
                        "tool_name": "shell",
                        "arguments": {"command": cmd},
                    }
                )
                chunks.append(
                    {
                        "_kind": "tool_result",
                        "tool_call_id": invocation_id,
                        "output": f"$ {cmd}\n{output}",
                        "is_error": False,
                        "latency_ms": 12,
                    }
                )
                chunks.append(
                    {
                        "_kind": "workflow_invocation",
                        "invocation_id": invocation_id,
                        "workflow_name": "shell-runner",
                        "status": "succeeded",
                    }
                )
        return chunks


def _mock_response_text(messages: list[ChatMessage]) -> str:
    user = next((m for m in reversed(messages) if m.role == "user"), None)
    body = (user.content if user else "hello").strip()
    return f"echo: {body}"
