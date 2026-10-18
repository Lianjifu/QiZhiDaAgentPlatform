# Ticket: 前端适配 5 个 agent stub tool 的交互 UI

## 背景

backend 已经在 `docs/refactor/agent-builtin-tools-v2.md` 落地了 18 个工具,其中 5 个是**前端 hook stub**:

| 工具 | 后端返回的 `_pending_frontend_action` | 前端要做的事 |
|---|---|---|
| `ask_user_question` | `"show_question_card"` | 多选问题卡 + 用户选完 push 回 turn |
| `notify_user` | `"toast"` | toast 通知(标题/正文/级别) |
| `plan_submit` | `"render_plan"` | 计划卡片 + 批准/拒绝按钮(可复用 PlanProposalCard) |
| `todo_write` | `"render_todo_list"` | 侧栏任务清单 |
| `delegate_to_agent` | `"delegate_agent"` | 跳到对应 agent 的会话 |

后端 stub **不阻塞 turn** — 立即返回 payload 给 LLM,前端 catch 到 `_pending_frontend_action` 后渲染对应 UI。

## 后端 → 前端的 payload 契约 (字段确定)

### ask_user_question
```json
{
  "questions": [
    {
      "question": "Which approach?",
      "options": [
        {"label": "A", "description": "Postgres + pgvector"},
        {"label": "B", "description": "Elasticsearch"}
      ],
      "multi_select": false,
      "header": "DB"  // 可选,短标签(<=12 chars),用于卡片头
    }
  ],
  "_pending_frontend_action": "show_question_card",
  "_status": "awaiting_user_input",
  "_stub_hint": "..."
}
```
**前端回应**: 用户选完 → POST 答案 → 后端继续 turn 流。答案格式:
```
POST /api/sessions/{id}/answer
{"answers": [{"question_index": 0, "selected": ["A"]}]}
```
后端把这答案 push 回 turn,LLM 继续。

### notify_user
```json
{
  "title": "审批通过",
  "body": "订单 #1234 已确认发货",
  "level": "info" | "warn" | "error" | "success",
  "delivered_at": "2026-10-18T13:45:00Z",
  "_pending_frontend_action": "toast",
  "_stub_hint": "..."
}
```
**纯展示**: 4 秒自动消失 (info) / 长显 (error)。无用户交互。

### plan_submit
```json
{
  "plan_id": "plan-abc",
  "title": "迁移到新架构",
  "steps": [
    {"id": "s1", "title": "备份数据", "description": "...", "status": "pending"},
    {"id": "s2", "title": "切流量", "description": "...", "status": "pending"}
  ],
  "reason": "需要用户批准",
  "_pending_frontend_action": "render_plan",
  "_stub_hint": "..."
}
```
**前端回应**: 用户点批准/拒绝 → POST → 后端继续。答案格式:
```
POST /api/sessions/{id}/answer
{"plan_id": "plan-abc", "decision": "approve" | "reject"}
```

### todo_write
```json
{
  "todos": [
    {
      "id": "todo-0",
      "content": "调研向量数据库",
      "status": "pending" | "in_progress" | "completed",
      "active_form": "正在调研向量数据库"
    }
  ],
  "_pending_frontend_action": "render_todo_list",
  "_stub_hint": "..."
}
```
**纯展示**: 侧栏组件,只读。后端返回什么就显示什么(LLM 持续更新)。

### delegate_to_agent
```json
{
  "agent_id": "uuid-of-target-agent",
  "task": "用 search_assistant 把刚才的研究报告总结成 PPT",
  "context": {"key": "value"},  // 透传给 sub-agent
  "_pending_frontend_action": "delegate_agent",
  "_stub_hint": "..."
}
```
**前端回应**: 立即 push 到 `/copilot?agentId={target_agent_id}&sessionId={new}`。

## SSE 流改造

当前 SSE 流里 `tool_result` 事件只把 result 塞进 `message.extras.toolCalls`。改:
- `tool_result.result` 里如果包含 `_pending_frontend_action` → **额外的 SSE event** `interactive_action`, payload 透传 result。
- 前端 `streamCopilotTurn` 在 `interactive_action` 事件回调里 dispatch 到对应 UI 组件。

```ts
// copilotApi.ts
type InteractiveAction = {
  call_id: string
  action: 'show_question_card' | 'toast' | 'render_plan' | 'render_todo_list' | 'delegate_agent'
  payload: Record<string, unknown>
}

streamCopilotTurn(sid, content, (event, data) => {
  ...
  if (event === 'interactive_action') {
    dispatchInteractiveAction(data as InteractiveAction)
  }
})
```

backend 配合改动: `agent_runtime/adapter/http/sse.py` 在 tool_result emit 时检测 `_pending_frontend_action` 并发 `interactive_action` event。

## 后端配合改动 (小)

`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/result/events.py`:
```python
class InteractiveActionEvent(_EventBase):
    kind: Literal["interactive_action"] = "interactive_action"
    call_id: str
    action: str
    payload: dict
```

`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/graph/nodes.py` (tool_result handler):
```python
result = ...
if isinstance(result, dict) and "_pending_frontend_action" in result:
    yield InteractiveActionEvent(
        call_id=call_id,
        action=result["_pending_frontend_action"],
        payload={k: v for k, v in result.items() if k != "_pending_frontend_action"},
    )
```

`backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/http/sse.py`:
新增事件 `interactive_action` → yield SSE line.

## 前端改造 (5 个新组件 + 1 个 store)

### 新组件

```
frontend/web/src/features/user/copilot/blocks/
├── InteractiveQuestionCard.tsx      # 多选问题卡
├── InteractiveToastHost.tsx          # 监听 toast 事件 + 渲染
├── InteractivePlanCard.tsx           # 计划卡(复用 PlanProposalCard 视觉)
├── InteractiveTodoList.tsx           # 侧栏 todo 列表
└── InteractiveAgentRouter.tsx        # 跳转目标 agent
```

### 新 store

```
frontend/web/src/features/user/copilot/state/
└── interactiveStore.ts               # 当前 pending interactive actions 队列
```

```ts
// interactiveStore.ts
type PendingQuestion = { call_id, questions, onResolve }
type PendingPlan = { call_id, plan_id, title, steps, onResolve }
type PendingDelegate = { call_id, agent_id, task, onResolve }

interface InteractiveStore {
  question: PendingQuestion | null
  plan: PendingPlan | null
  delegate: PendingDelegate | null
  toasts: ToastMsg[]                  // 队列,FIFO 自动消失
  todos: Todo[]                       // 累计,LWW
  setQuestion, resolveQuestion, dismissQuestion,
  setPlan, resolvePlan,
  setDelegate,
  pushToast, dismissToast,
  setTodos,
}
```

### 集成点

`CopilotPage.tsx` 在 main 区上方或下方挂载 `<InteractionHost>`:
```tsx
<InteractionHost />
```

`InteractionHost` 监听 `interactiveStore`:
- `question` → 弹 `<InteractiveQuestionCard>` modal
- `plan` → 显示 `<InteractivePlanCard>` 顶部条
- `delegate` → 立即调 router.push(`/copilot?agentId=...&sessionId=...`)
- `toasts` → 右下 toast 队列
- `todos` → 右侧 drawer

`streamCopilotTurn` 回调增加 `interactive_action` 分支:
```ts
case 'interactive_action': {
  const { call_id, action, payload } = data
  if (action === 'show_question_card') {
    interactiveStore.setQuestion({ call_id, questions: payload.questions, onResolve: submitAnswer })
  } else if (action === 'toast') {
    interactiveStore.pushToast({ title: payload.title, body: payload.body, level: payload.level })
  } else if (action === 'render_plan') {
    interactiveStore.setPlan({ call_id, plan_id: payload.plan_id, title: payload.title, steps: payload.steps, onResolve: submitPlanDecision })
  } else if (action === 'render_todo_list') {
    interactiveStore.setTodos(payload.todos)
  } else if (action === 'delegate_agent') {
    interactiveStore.setDelegate({ call_id, agent_id: payload.agent_id, task: payload.task })
    router.push(`/copilot?agentId=${payload.agent_id}`)
  }
}
```

### 后端 answer 接口 (新增)

`backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/http/session_router.py`:

```python
@router.post("/api/sessions/{sid}/answer")
async def submit_answer(sid: UUID, body: AnswerBody):
    """Push user's interactive-action answer back into the agent turn queue.
    The LLM stream resumes after the next tool_call loop iteration."""
    ...
```

数据流:
1. 用户在 UI 选答案 → `onResolve(answer)` → POST `/api/sessions/{sid}/answer`
2. 后端把 answer push 到 `agent_sessions.turns` 队里
3. 后端唤醒 (或下次轮询) → LLM 拿 answer 当上下文继续
4. SSE 流继续输出

`turns` 表加列:
```sql
ALTER TABLE agent_turns ADD COLUMN interactive_answer JSONB;
```

## 文件改动清单

### 后端 (3 处)

1. **`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/result/events.py`** — 加 `InteractiveActionEvent`
2. **`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/graph/nodes.py`** — tool_result 节点 emit `interactive_action`
3. **`backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/http/session_router.py`** — `POST /api/sessions/{sid}/answer`
4. **`backend/migrations/versions/004X_agent_turns_answer.py`** (新) — 加 `interactive_answer` 列
5. **`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/adapter/http/sse.py`** — 透传 `interactive_action` 事件

### 前端 (7 处)

1. **`frontend/web/src/features/user/copilot/state/interactiveStore.ts`** (新) — zustand store
2. **`frontend/web/src/features/user/copilot/copilotApi.ts`** — `interactive_action` event 分支
3. **`frontend/web/src/features/user/copilot/blocks/InteractiveQuestionCard.tsx`** (新)
4. **`frontend/web/src/features/user/copilot/blocks/InteractiveToastHost.tsx`** (新)
5. **`frontend/web/src/features/user/copilot/blocks/InteractivePlanCard.tsx`** (新)
6. **`frontend/web/src/features/user/copilot/blocks/InteractiveTodoList.tsx`** (新)
7. **`frontend/web/src/features/user/copilot/blocks/InteractiveAgentRouter.tsx`** (新,或合并到 InteractionHost)
8. **`frontend/web/src/features/user/copilot/CopilotPage.tsx`** — 挂载 `<InteractionHost>`,注入 interactiveStore 订阅

## 工作量

| 块 | 天数 |
|---|---|
| 后端 InteractiveActionEvent + emit | 0.5 天 |
| 后端 /answer 接口 + migration | 0.5 天 |
| 前端 5 个组件 + store | 2-3 天 |
| 联调 | 0.5 天 |
| 测试 | 0.5 天 |
| **合计** | **4-5 天** |

## UI 设计要点

### InteractiveQuestionCard
- 居中 modal, 最大宽 600px
- 每个 question 单独卡片,header(可选短标签)在卡片头
- 选项是 radio / checkbox(根据 multi_select)
- 提交按钮 disabled 除非每题都选了
- ESC 关闭 = "skip"(后端收到空 answer 表示用户跳过了)
- 多个 question 滚动在表单里

### InteractivePlanCard
- 主区顶部 sticky 条
- 显示 title + steps 折叠列表 + 批准/拒绝两个按钮
- 拒绝时弹一个小文本框输入 reason(可选)
- 已响应后变灰,显示用户的决定

### InteractiveTodoList
- 右侧 drawer(默认展开 240px,可折叠)
- 顶部一个 progress 数字:"3 / 7"
- pending → in_progress → completed 三态颜色 + ✓ 标记
- 当前 in_progress 的 todo 加 active_form 副标题

### InteractiveToastHost
- 右下角堆叠 toast
- info 4s / warn 6s / error 长显(需手动关)
- success 3s

### InteractiveAgentRouter
- 不渲染组件,直接 router.push
- 如果目标 agent_id 不存在或用户无权限 → 弹 toast 报错,不跳转

## 边界 / 错误处理

- LLM 在 ask_user 后不继续: 用户不响应就一直挂着,直到 dismiss (后端记一个空 answer,LLM 用默认值继续)
- answer 接口超时(30s): 后端重试 3 次后放弃,记 audit
- delegate 跳转时原 session 暂停还是关闭? **暂停**(用户可手动回来继续)
- ask_user 期间新 tool_result 到达: 排队,在 question 关闭后逐个渲染(toast/plan/todo 可并发)

## 测试计划

1. **后端**: 单元测试 `interactive_action` 事件 emit / `/answer` 接口 push turn
2. **后端**: integration 测试完整流(LLM tool_call → stub → /answer → 继续 turn)
3. **前端**: 组件单元测试(render + onResolve + dismiss)
4. **前端**: e2e 流测试(模拟 SSE events,验证 store 状态转换)
5. **手测**: 启动 dev,让 LLM 调 ask_user / plan_submit / todo_write / notify_user / delegate_to_agent,目视验证 UI + 后续 turn 正确

## 不做 (out of scope)

- ❌ 多 modal 同时存在(只允许一个 question / 一个 plan 同时)
- ❌ answer 流式 streaming(answer 是单次 POST)
- ❌ 撤回已确认的 plan / 选过的 question(走后续 turn 让 LLM 重新调)
- ❌ 实时协同(同一 session 多人) — 用户是单点

## 关联

- 后端 ticket `agent-builtin-tools-v2.md` — 这 5 个 stub 的源头
- 上一篇 `agent-builtin-tools.md` — 第一个 7 工具批次,已 frontend 适配

## 时间线

本周: 后端 InteractiveActionEvent + /answer 接口 + 1 个前端组件 (question)
下周: 剩下 4 个前端组件 + 联调 + 测试
总计 2 周。