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
    (re.compile(r"你.*?(可以|能)做.*?什么|你.*?能做.*?(什么|哪些)|能(力|做什么)|介绍.*?能力|help|你能.*?帮|有什么.*?功能|what\s+can\s+you"), "capability"),
]

_CAPABILITY_INTRO = """我是 QZDAP 企业助手, 通常能帮你做下面这些事:

- **整理思路**: 把模糊的需求拆成步骤清晰、可执行的计划
- **起草文档**: 报告 / 需求 / 会议纪要 / 操作手册, 直接存为产物供你下载
- **查知识库**: 命中你工作区里发布过的资料, 给出引用
- **跑命令**: 沙箱里跑 shell, 拿到结果回填
- **画流程**: 必要时附 mermaid 图

下面给你演示一遍, 我从工具 / 技能 / 知识 / 工作流 四个维度各跑一次:
"""

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
        content = _mock_response_text(req.messages, self._cfg.mock_latency_ms)
        return ChatResponse(
            model=req.model,
            message=ChatMessage(role="assistant", content=content),
            finish_reason="stop",
            usage=Usage(input_tokens=10, output_tokens=len(content) // 4),
            raw={"mock": True},
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        content = _mock_response_text(req.messages, self._cfg.mock_latency_ms)
        # 把响应拆成 8~14 块, 块间留延迟, 让前端能看出流式效果
        words = content.split(" ")
        # 不让句子被切得太碎, 每块 2~4 个词
        import random
        rng = random.Random(content)
        groups: list[str] = []
        i = 0
        while i < len(words):
            size = rng.randint(2, 4)
            groups.append(" ".join(words[i : i + size]))
            i += size
        total_ms = max(80, self._cfg.mock_latency_ms * 2)
        per_chunk = total_ms / max(len(groups), 1)
        for group in groups:
            await asyncio.sleep(per_chunk / 1000)
            yield LLMChunk(model=req.model, delta=group + " ")
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
            elif kind == "capability":
                # 能力问询 → 一次性 demo 五件套:
                #   1) tool_call + tool_result (echo demo)
                #   2) skill_invocation
                #   3) knowledge_search
                #   4) workflow_invocation (shell 演示)
                tool_id = str(uuid.uuid4())
                chunks.append(
                    {
                        "_kind": "tool_call",
                        "tool_call_id": tool_id,
                        "tool_name": "echo",
                        "arguments": {"text": "hello from QZDAP"},
                    }
                )
                chunks.append(
                    {
                        "_kind": "tool_result",
                        "tool_call_id": tool_id,
                        "output": "hello from QZDAP",
                        "is_error": False,
                        "latency_ms": 6,
                    }
                )
                chunks.append(
                    {
                        "_kind": "skill_invocation",
                        "invocation_id": str(uuid.uuid4()),
                        "skill_name": "summarize_doc",
                        "status": "succeeded",
                    }
                )
                chunks.append(
                    {
                        "_kind": "knowledge_search",
                        "query": "入职 制度",
                        "hits": [
                            {
                                "id": "kb-001",
                                "title": "员工手册 · 入职流程",
                                "snippet": "本手册覆盖新员工入职第一周的全部流程, 包括系统账号开通、公司制度学习、行政手续办理。",
                                "score": 0.92,
                            },
                            {
                                "id": "kb-002",
                                "title": "公司行为准则",
                                "snippet": "明确员工日常工作中的行为边界, 包括信息安全、对外沟通、利益冲突申报。",
                                "score": 0.81,
                            },
                        ],
                        "citations": ["kb-001", "kb-002"],
                        "degraded": False,
                    }
                )
                wfl_id = str(uuid.uuid4())
                chunks.append(
                    {
                        "_kind": "workflow_invocation",
                        "invocation_id": wfl_id,
                        "workflow_name": "shell-runner",
                        "status": "started",
                    }
                )
                chunks.append(
                    {
                        "_kind": "tool_call",
                        "tool_call_id": wfl_id,
                        "tool_name": "shell",
                        "arguments": {"command": "date"},
                    }
                )
                chunks.append(
                    {
                        "_kind": "tool_result",
                        "tool_call_id": wfl_id,
                        "output": "$ date\nThu Oct 16 00:00:00 CST 2026",
                        "is_error": False,
                        "latency_ms": 9,
                    }
                )
                chunks.append(
                    {
                        "_kind": "workflow_invocation",
                        "invocation_id": wfl_id,
                        "workflow_name": "shell-runner",
                        "status": "succeeded",
                    }
                )
        return chunks


def _mock_response_text(messages: list[ChatMessage], mock_latency_ms: int = 200) -> str:
    """根据最近一条 user 消息的内容挑选回复模板.

    触发词 (与 _TRIGGERS 同步) 命中时, 给出一个"有内容"的开场, 让前端
    能看到流式 / markdown / 工具块等效果; 不命中时给一个简短自然回应,
    不再是死板的 "echo: ...".
    """
    import re

    user = next((m for m in reversed(messages) if m.role == "user"), None)
    body = (user.content if user else "hello").strip()
    if not body:
        return "你好, 我是 QZDAP 企业助手, 有什么可以帮你的?"

    # 1) 能力问询 → 完整 markdown 介绍, 后面跟 demo chunks
    if re.search(r"你.*?(可以|能)做.*?什么|你.*?能做.*?(什么|哪些)|能(力|做什么)|介绍.*?能力|help|你能.*?帮|有什么.*?功能|what\s+can\s+you", body, re.IGNORECASE):
        return _CAPABILITY_INTRO

    # 2) 计划类触发
    if re.search(r"做.*?计划|做.*?规划|拆解成|分步|step\s*by\s*step|分阶段|做.*?方案|给我.*?计划|列.*?计划|列.*?步骤|怎么.*?做|如何.*?做", body):
        return f"好的, 我先给你列个计划, 跑下来大概 4 步, 你可以先看一下再决定要不要继续。"

    # 3) 产物类触发
    if re.search(r"生成(一份|个|一篇)?(报告|文档|说明书|手册|方案|计划书|需求|纪要|模板)|写(一份|个|一篇)?(报告|文档|说明书|手册|模板)|(报告|文档|说明书|手册|计划书|纪要|模板)", body):
        return f"行, 给你起草一份, 我会同时把结果存为产物, 你可以直接预览或下载。"

    # 4) 工作流 / 命令类触发
    if re.search(r"跑(一下|个)?(命令|脚本|shell|bash)?|执行(命令|脚本)|^\s*ls\s*$|^\s*pwd\s*$|^\s*whoami\s*$|^\s*echo\s|^\s*grep\s", body):
        return "好, 跑一下:"

    # 5) 默认: 简短自然回应, 不再 echo
    if len(body) <= 8:
        return f"好的, 关于「{body}」, 我可以帮你做计划、生成文档、查知识库, 或者跑命令。说具体一点?"
    return f"收到, 这条问题我需要更多信息。先给一个简短的回应: 你说的是「{body[:80]}{'...' if len(body) > 80 else ''}」。"

