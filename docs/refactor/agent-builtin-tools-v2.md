# Ticket: Agent 内置工具扩展 — 18 个新工具

## 背景

前一个 ticket (agent-builtin-tools.md) 加了 bash / read_file / write_file / edit_file / ls / glob / grep 共 7 个 FS 工具。

用户后续要求:把剩下对 LLM 高价值的工具全部加上。共 3 个分类:

### 🟢 纯后端,LLM 可立即用 (13 个)

| 工具 | 作用 |
|---|---|
| `apply_patch` | 一次 patch 多文件 (类似 Claude Code MultiEdit) |
| `diff` | 2 个文件 / 2 段文本的 unified diff |
| `image_view` | 读图返回 base64 + 缩略图,LLM 多模态识别 |
| `pdf_read` | PDF 抽文本,支持前 N 页 |
| `json_query` | jq-like JSONPath 查询 |
| `csv_query` | CSV 行过滤 + 列选择 |
| `git_status` | git status --short |
| `git_diff` | git diff (staged / unstaged) |
| `git_log` | git log -n N --oneline |
| `code_search` | ast-grep (有) / grep 兜底,语法感知代码搜索 |
| `convert_format` | md→html / csv→json / json→yaml |
| `fetch_url_with_auth` | http_fetch + 自定义 headers / cookies / auth |
| `calculator` | 安全数学表达式求值 (LLM 自算易错 0.1+0.2) |

### 🟡 后端 stub + 前端 hook (5 个)

后端实现 tool 入口,返回结构化 payload,前端渲染交互:

| 工具 | 作用 | 前端要做 |
|---|---|---|
| `ask_user_question` | LLM 多选问澄清 | 多选卡片 + 选择提交 |
| `notify_user` | LLM 推送通知 | toast / bell |
| `plan_submit` | LLM 提交计划等用户批准 | 用现有 PlanProposalCard |
| `todo_write` | LLM 维护任务清单 | 任务列表组件 |
| `delegate_to_agent` | LLM 分任务给 sub-agent | agent picker + 重路由 |

### 全部 18 个工具的工作量

| 类别 | 工作量 |
|---|---|
| 13 个纯后端 | 1.5 天 (大都是 stdlib + 一个 PDF + 一个 Pillow) |
| 5 个 stub | 后端 0.5 天 + 前端 1-2 天 |
| 测试 | 1 天 |
| 文档 + admin_tools seed | 0.5 天 |
| **合计** | **4-5 天** |

## 实现路径

### 依赖

新增 (pyproject.toml `[project.dependencies]`):
- `pypdf>=4.0` — PDF 文本抽取 (纯 Python, 无 system dep)
- `pillow>=10.0` — 图片读 + 缩略图

### 文件结构

新增 `backend/modules/tool/src/qzdap/modules/tool/adapter/adapters/builtin_extra_tools.py`:
- 13 个纯后端工具函数 (按类别分 4 段: 编辑/查看/查询/git-代码)
- 5 个 stub 工具函数(返回结构化 payload + 标注 pending_frontend)

保持 `custom_invoker.py` 不动(避免一次 diff 太大)。

### 各工具契约

#### `apply_patch`
```json
{"patches": [
  {"path": "foo.py", "old_text": "a == b", "new_text": "a != b"},
  {"path": "bar.py", "old_text": "...", "new_text": "..."}
]}
```
- 每个 patch 用 edit_file 同样校验 (1 次匹配)
- 返回 `{applied: N, failed: [{path, error}], total: M}`

#### `diff`
```json
{"a_path": "...", "b_path": "...", "context_lines": 3}
// 或 {"a_text": "...", "b_text": "..."}
```
- 返回 `{diff: "--- a\\n+++ b\\n@@ ..."}`

#### `image_view`
```json
{"path": "...", "max_dim": 1024, "format": "base64"}
```
- Pillow 读 + 转 RGB + 缩放 (max_dim 长边)
- 返回 `{path, format: "png"|"jpeg", data_base64, width, height}`

#### `pdf_read`
```json
{"path": "...", "max_pages": 20}
```
- pypdf 读, 抽前 max_pages 页文本
- 返回 `{path, total_pages, pages_read, text, truncated}`

#### `json_query`
```json
{"data": {...}, "path": "$.items[?(@.status=='active')].id"}
```
- 简化 JSONPath: 支持 `$.a.b`, `$.a[0]`, `$.a[*]`, `$.a[?(@.x==y)]`
- 返回 `{matches: [...], count}`

#### `csv_query`
```json
{"path": "...", "where": "status == 'active'", "columns": ["id", "name"], "limit": 100}
```
- `where` 用 Python 表达式,提供 row 字典作为上下文
- 返回 `{path, rows: [{...}], count, total}`

#### `git_status`, `git_diff`, `git_log`
- subprocess `git ...` 在 workspace_dir 内
- cwd 限定 workspace_dir (safe_resolve)
- 输出 100 KiB 上限

#### `code_search`
- 优先 `ast-grep run --pattern 'PATTERN' --lang py LANG`, 找不到 ast-grep 退到 grep
- 返回 `{matches: [{path, line, pattern_matched}], count}`

#### `convert_format`
```json
{"from": "csv", "to": "json", "input": "..."|{path: "..."}}
```
- 支持 csv↔json, json↔yaml (yaml 用纯 Python 写)
- 返回 `{output: "..."}`

#### `fetch_url_with_auth`
- 同 http_fetch, 多 `headers: {...}`, `cookies: {...}`, `bearer_token: "..."`
- 返回 同 http_fetch

#### `calculator`
```json
{"expression": "sqrt(2) * 100"}
```
- **不调 eval()**。自己实现 parser, 只允许数字 + 算术运算符 + `sqrt/abs/min/max/round`
- 返回 `{value: float, formatted: str}

### Stubs (前端 hook)

每个返回结构化 payload + `_pending_frontend_action` 字段标识前端要做的事。

#### `ask_user_question`
返回:
```json
{
  "questions": [{
    "question": "Which approach?",
    "options": [{"label": "A", "description": "..."}, {"label": "B"}],
    "multi_select": false
  }],
  "_pending_frontend_action": "show_question_card",
  "_status": "awaiting_user_input"
}
```
前端: 弹多选卡片 → 用户选完 → POST 答案 push 回 turn 队列。

#### `notify_user`
返回:
```json
{"title": "审批通过", "body": "...", "level": "info"|"warn"|"error", "_pending_frontend_action": "toast"}
```

#### `plan_submit`
返回 plan 列表,前端复用 `PlanProposalCard` 渲染"批准/拒绝"按钮。

#### `todo_write`
返回 `{todos: [{id, content, status, active_form}]}`,前端渲染为侧边栏。

#### `delegate_to_agent`
返回 `{agent_id, task}`,前端跳转到对应 agent 会话。

后端 stub 不实际执行前端 action,只是返回 payload 让前端 catch SSE event 渲染。后端 ticket 跟踪具体前端实现。

### 安全

所有 FS 工具走 `_safe_resolve()`,不绕过。
git_* 走 bash subprocess 但限定 cwd = workspace_dir。
calculator 不用 eval(),用受限 AST。
fetch_url_with_auth 仍走 _safe_get,允许列表 content-type 同 http_fetch。

### 路由配置

全部走 CUSTOM 协议,跟现有 12 个 built-in 一致。lifespan 注册 + DB seed 进 admin_tools 表(workspace 默认)。

## 测试计划

每个工具:
1. happy path (输入正确 → 预期输出)
2. 错误 path (缺参 / 错参 → `{"error": "..."}`)
3. 安全 path (路径穿越 / cwd 越权 / 受保护前缀)

特殊:
- calculator: `(2+3)*4 == 20`; `__import__('os').system('rm -rf /')` → 拒绝
- json_query: 路径 `$.x[?(@.y<5)]` 过滤
- csv_query: where 表达式 row.get() not row['col']
- git_*: workspace 内 / workspace 外

## 不做 (out of scope)

- ❌ 真实执行前端 hook (UI 渲染)— frontend separate ticket
- ❌ delegate_to_agent 实际跑子 agent (sub-agent dispatch)— separate ticket
- ❌ calculator 单位换算 / 金融函数
- ❌ pdf_read OCR (扫描版 PDF)— 需要 tesseract,太大