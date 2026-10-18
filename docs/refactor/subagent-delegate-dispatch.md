# Ticket: Sub-Agent 派发 — 真把任务交给目标 Agent

> **状态**: ✅ 完成 (2026-10-18)
>
> 实现:
> - `DelegateSubagentUseCase` — 校验 + 创建 sub_session + 同步跑 sub-agent turn
> - 嵌套深度限制 `max_delegation_depth = 3`, 跨租户/跨工作区拒绝
> - Runner 注入 `parent_session_id` 到 `delegate_to_agent` arguments
> - Stub 工具不再 emit `interactive_action` chunk — sub-agent 真跑了, 结果直接喂回 LLM
> - 前端 CopilotPage 去掉 `router.push` + auto-sendMessage, 改成 toast 通知
>
> 测试: 10/10 新 use case 单测通过; tool 单测 126 + 集成 35 全过.

## 背景

前一个 ticket (frontend-interactive-tools.md) 的 `delegate_to_agent` stub
tool 实现了前端跳转 (`router.push`), 但**没有真正把任务派给目标
agent** — 只是给用户切了个页面, 目标 agent turn 不会自动跑.

用户需求:LLM 调 `delegate_to_agent(agent_id, "xxx")` 后, 目标 agent 应该
真的拿到这个 task, 在自己的 turn 里执行 (或 spawn 一个 sub-turn), 然后
把结果回传给父 agent.

## 现状

后端 stub tool 返回 `{_pending_frontend_action: "delegate_agent"}`,前端
拿到事件后只调 `router.push` 跳页面 — **sub-agent 调度逻辑 0 处**.

## 目标

实现完整的 sub-agent 派发链路:
```
LLM (父 agent) → 调 delegate_to_agent(target_id, task, context)
                  ↓
后端: 在父 turn 里 spawn 一个 sub-agent turn, 把 task 灌进去
                  ↓
sub-agent 跑 (stream 自己的 SSE)
                  ↓
sub-agent done → 把 final_response 注入父 turn 的 messages 里
                  ↓
LLM (父 agent) 继续生成 (基于 sub-agent 结果)
```

## 设计选择

### A. Sub-agent 作为 tool call

`delegate_to_agent` 在父 agent 视角就是个 **tool**:
- tool name: `delegate_to_agent`
- tool result: `{final_response, sub_session_id, status, duration_ms}`

后端实现:
1. 校验 target agent 存在 + 用户有权限
2. 创建 sub_session (parent_session_id = current_session_id)
3. 调 `RunTurnUseCase` 在新 session 里跑一个 turn, 输入 = task
4. 收集 final_response + 关键 events
5. 把 final_response 喂回父 turn 的 messages,继续

### B. 同步 vs 异步

**同步**(本期做这个): sub-agent 跑完, 父 agent 等结果再继续. 简单, 不会出
race condition. 适合短任务 (LLM 调一次 delegate 通常是想等结果).

**异步**(二期): sub-agent 后台跑, 父 agent 立即收到"已派发" ack, 完了通过
notification 反哺. 适合长任务.

### C. 上下文传递

`context` 字段透传给 sub-agent:
- 拼成 sub-agent 的 system prompt 补充 (在原始 system_prompt 之后追加)
- 或作为 user message 的前置 context 块

我选后者 — 简单, 不动 sub-agent 的 prompt 模板.

## 实现路径

### 后端 (3 个文件)

#### 1. 新增 sub-agent dispatch use case

`backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/application/use_cases/delegate_subagent.py` (新):

```python
class DelegateSubagentUseCase:
    def __init__(self, agent_runtime, agent_factory, session_repo):
        ...

    async def execute(
        self,
        *,
        parent_session_id: UUID,
        target_agent_id: str,
        task: str,
        context: dict,
        tenant_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> dict:
        # 1. 找 target agent
        target = await self._agent_factory.get(target_agent_id)
        if target is None:
            return {"ok": False, "error_code": "AGENT_NOT_FOUND", "error": f"agent {target_agent_id} not found"}
        # 2. 校验权限 (同一 tenant + workspace)
        if target.tenant_id != tenant_id:
            return {"ok": False, "error_code": "CROSS_TENANT", "error": "cross-tenant dispatch denied"}
        # 3. 创建 sub_session
        sub_session = await self._session_repo.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=actor_id,
            agent_id=target_agent_id,
            agent_version=target.version,
            metadata={
                "parent_session_id": str(parent_session_id),
                "delegated_task": task,
                "delegation_context": context,
            },
        )
        # 4. 拼 user message (context + task)
        user_input = self._format_task(task, context)
        # 5. 跑 turn
        result = await self._agent_runtime.run_turn(
            session_id=sub_session.id,
            content=user_input,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            timeout_seconds=300,
        )
        # 6. 收结果
        return {
            "ok": result.ok,
            "sub_session_id": str(sub_session.id),
            "final_response": result.final_response,
            "status": result.status,
            "duration_ms": result.duration_ms,
            "error_code": result.error_code,
        }

    def _format_task(self, task: str, context: dict) -> str:
        if not context:
            return task
        ctx_lines = "\n".join(f"- {k}: {v}" for k, v in context.items())
        return f"{task}\n\n上下文:\n{ctx_lines}"
```

#### 2. 改 `custom_invoker.py` 的 `delegate_to_agent` builtin

`backend/modules/tool/src/qzdap/modules/tool/adapter/adapters/builtin_extra_tools.py`:

```python
async def built_in_invoke_delegate_to_agent(
    arguments, *, tenant_id, workspace_id, call_id, actor_id,
) -> dict:
    agent_id = (arguments.get("agent_id") or "").strip()
    task = (arguments.get("task") or "").strip()
    context = arguments.get("context") or {}
    if not agent_id: return {"error": "agent_id required"}
    if not task: return {"error": "task required"}

    # 找 parent_session_id: 从 session store (按 tenant + workspace 找最近一个)
    # 或者要求 arguments 里有 parent_session_id
    parent_session_id_str = arguments.get("parent_session_id")
    if not parent_session_id_str:
        return {"error": "parent_session_id required (frontend must pass it)"}

    usecase = _get_delegate_subagent_usecase()  # 从 container 拿
    result = await usecase.execute(
        parent_session_id=UUID(parent_session_id_str),
        target_agent_id=agent_id,
        task=task, context=context,
        tenant_id=tenant_id, workspace_id=workspace_id, actor_id=actor_id,
    )
    return result
```

#### 3. 改 CopilotPage SSE 流转

`frontend/web/src/features/user/copilot/CopilotPage.tsx`:
- delegate_agent 不再 router.push + 自己 sendMessage
- 改成: 在 stub tool call 里把 `parent_session_id` 传给 backend
- 后端同步执行 sub-agent
- stub tool 返回 `{final_response, sub_session_id}` — LLM 看到 result
- 前端只 push toast 通知 "已派给 X, 用时 Ns"

这样 LLM 自动拿到 sub-agent 的回答,可以继续生成. **不需要 frontend 跳页面.**

(原有的 router.push 行为如果用户想自己看 sub-agent session, 可以保留作为
"view in new tab" 二级按钮.)

### 4. SSE 流改造 (可选)

如果想让前端实时看到 sub-agent 的中间步骤, 加一个 `subagent_progress`
事件:
```
event: subagent_progress
data: {"session_id": "...", "event": "tool_call", ...}
```
前端透传到右侧 drawer 显示.

本期**先不做**, v2 加.

## 边界 / 风险

1. **超时**: sub-agent 跑 5min (timeout_seconds=300) 默认. 超过 → 父 agent 拿
   timeout error, 决定下一步. 可以后续让用户调.
2. **嵌套深度**: sub-agent 内部又调 delegate_to_agent → 嵌套递归. 需加
   `max_delegation_depth = 3`, 超过拒绝.
3. **配额**: 每个 sub-agent 跑也消耗 LLM tokens. 算在父 session 还是
   sub_session? 算各自(更公平), 但 audit 聚合时按 task_id 上溯.
4. **权限**: 必须严格 tenant + workspace 隔离, 跨租户派发直接拒绝
   (返回 `CROSS_TENANT`).
5. **审计**: audit_log 记 `tool.delegate_to_agent` 含 parent_session_id,
   target_agent_id, sub_session_id, duration_ms.

## 测试计划

1. **happy path**: 父 agent 调 delegate_to_agent(search_agent, "查最近 7 天
   news") → 后端跑 search_agent → 返回 final_response → 父 agent 继续生成
2. **agent 不存在**: 返回 AGENT_NOT_FOUND
3. **跨租户**: tenant A 调 tenant B 的 agent → 返回 CROSS_TENANT
4. **嵌套超深**: A → B → C → D (depth 4) → 拒绝 + 报错
5. **超时**: sub-agent 卡 6 分钟 → 父 turn 收到 timeout error
6. **失败传播**: sub-agent raise exception → 父 turn 收到 ok=false + error

## 工作量

| 块 | 天数 |
|---|---|
| 后端 DelegateSubagentUseCase | 1 |
| 改 stub + Container 注入 | 0.5 |
| SSE 改 (去掉 router.push, 改 push toast) | 0.25 |
| 测试 | 0.5 |
| 文档 | 0.25 |
| **合计** | **2-3 天** |

## 文件改动

**后端** (3):
- `modules/agent_runtime/.../application/use_cases/delegate_subagent.py` (新)
- `modules/tool/.../adapter/adapters/builtin_extra_tools.py` (改 stub)
- `composition/qzdap_app/src/qzdap/composition/container.py` (注入 use case)
- `composition/qzdap_app/src/qzdap/composition/lifespan.py` (注册)

**前端** (1):
- `features/user/copilot/CopilotPage.tsx` (去掉 router.push, 改 toast)

## 不做 (out of scope)

- ❌ async sub-agent (后台跑, 完了通知) — v2
- ❌ sub-agent 实时流回前端 (subagent_progress SSE) — v2
- ❌ sub-agent 结果 stream 反馈给父 agent 的 system prompt — v2
- ❌ 多 sub-agent 并行 — v2 (本期一次只能派一个)
- ❌ sub-agent 选择 UI (用户在前端选 agent, 不让 LLM 选) — v2
- ❌ sub-agent 配额 / 计费分离 — 后续单 ticket

## 关联

- 前 ticket `frontend-interactive-tools.md` — stub tool 基础
- 后 ticket `agent-builtin-tools-v2.md` — stub tool 后端实现
- 前 ticket `sandbox-network-egress-control.md` — workspace 安全