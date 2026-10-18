# Ticket: Agent 内置工具补齐 — 文件 I/O + Shell (对标 Claude Code)

## 背景

现状: qzdap agent 对话里只有 5 个内置工具 (`echo / reverse / clock / web_search / http_fetch`)。Claude Code 有 40+, 其中**核心 7 个文件 / shell 工具**是 LLM 体验的根本差异点:

| 工具 | Claude Code | 我们 |
|---|---|---|
| Bash (执行 shell) | ✅ | ❌ |
| Read (读文件) | ✅ | ❌ |
| Write (写文件) | ✅ | ❌ |
| Edit (按 old/new 编辑) | ✅ | ❌ |
| LS (列目录) | ✅ | ❌ |
| Glob (`*.md` pattern) | ✅ | ❌ |
| Grep (内容搜索) | ✅ | ❌ |

缺这些 = agent 只能"聊天", 不能"动手改东西"。

## 目标

在 `modules/tool/adapter/adapters/custom_invoker.py` 加 7 个 built-in, 在 lifespan 注册 + DB seed, 让 LLM 直接 tool_call 它们。

## 实现方案

### 路径选择

**全部走 CUSTOM 协议**(in-process),不走 sandbox。理由:
- 文件 I/O 必须看到 host filesystem,sandbox 在 container 里看不到
- shell 命令需要 `cd workspace_dir && exec`, 同样依赖 host fs
- latency 必须低(<100ms),sandbox 启动就要 200ms+

**安全边界**: 所有工具强制 workspace 路径前缀。LLM 给出 `/etc/passwd` 之类, 直接拒绝。

### 工具契约

每个工具签名:
```python
async def built_in_invoke_<name>(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]
```

返回 dict 给 LLM。错误用 `{"error": "..."}` 而不是抛异常 — LLM 看到 error 比看 500 友好。

### 工具详情

#### 1. `bash`
- **路径**: in-process `asyncio.create_subprocess_shell`, 不进 sandbox
- **arguments**:
  - `command: str` — 必填
  - `cwd: str` — 可选,默认 workspace_dir
  - `timeout_seconds: int` — 可选,默认 30, 最大 300
- **返回**: `{stdout, stderr, exit_code, duration_ms}`
- **安全**:
  - cwd 必须 ≤ workspace_dir + 一层白名单子目录(`tmp/`, `.cache/`),**不能 cd 到** workspace 外
  - 不限制命令内容,workspace 是 user 自己的
  - 输出最大 100 KiB (stdout + stderr 各),超截断 + 加 `[truncated]` 标记
- **审计**: 每次执行写一条 `audit_log` (event_type=`tool.bash_executed`)

#### 2. `read_file`
- **路径**: in-process `Path.read_text()`
- **arguments**:
  - `path: str` — 必填,workspace_dir 相对路径
  - `max_bytes: int` — 可选,默认 200_000 (~200 KB),最大 1 MB
  - `start_line: int` — 可选,默认 0
  - `end_line: int` — 可选,默认 EOF)
- **返回**: `{path, content, total_lines, encoding}` 或 `{path, content_slice, start_line, end_line, total_lines}` (分片)
- **安全**: `path` 解析后必须 `is_relative_to(workspace_dir)`,否则 `{"error": "path escapes workspace"}`
- **不读二进制**: 检查 magic bytes, 是 binary 就拒绝 + 提示 "use a specialized tool"

#### 3. `write_file`
- **路径**: in-process `Path.write_text()`
- **arguments**:
  - `path: str` — 必填,workspace_dir 相对
  - `content: str` — 必填
  - `create_parents: bool` — 可选,默认 False (避免 LLM 乱建目录)
- **返回**: `{path, bytes_written, mode}`
- **安全**:
  - 路径必须在 workspace_dir 下
  - 拒绝覆盖 `.git/`, `.claude/`, `node_modules/`, `.venv/` (保护性)
  - 写之前返回 dry-run 确认 (TODO: 先简单写,后续加 confirmation 流程)

#### 4. `edit_file`
- **路径**: in-process 字符串替换
- **arguments**:
  - `path: str` — 必填
  - `old_text: str` — 必填,文件中必须**精确**出现 1 次 (0 次或多于 1 次都报错)
  - `new_text: str` — 必填
- **返回**: `{path, replacements: 1, preview: <diff 或 snippet>}`
- **安全**: 同 write_file (路径 + 保护目录)
- **TODO**: 后续用 `diff-match-patch` 做 fuzzy match, 先做 exact

#### 5. `ls`
- **路径**: in-process `Path.iterdir()`
- **arguments**:
  - `path: str` — 必填,workspace_dir 相对,默认 `.` (workspace root)
  - `recursive: bool` — 可选,默认 False
  - `max_depth: int` — 可选,默认 3
  - `include_hidden: bool` — 可选,默认 False
- **返回**: `{path, entries: [{name, type, size, mtime}, ...], total}`
- **安全**: 路径必须 ≤ workspace_dir, **不能 ls parent**

#### 6. `glob`
- **路径**: in-process `Path.glob()`
- **arguments**:
  - `pattern: str` — 必填, gitignore-style (`**/*.py`, `src/**/*.ts`)
  - `cwd: str` — 可选,默认 workspace_dir
  - `max_results: int` — 可选,默认 1000, 最大 5000
- **返回**: `{pattern, matches: [path1, path2, ...], count}`
- **安全**: cwd 必须 ≤ workspace_dir
- **不跟随 symlink**: 用 `Path.rglob` 而非 `Path.glob` 时要小心, 加 `resolve()` 检查 final path

#### 7. `grep`
- **路径**: in-process, 读取每个匹配文件再正则
- **arguments**:
  - `pattern: str` — 必填,正则
  - `cwd: str` — 可选,默认 workspace_dir
  - `include: str` — 可选, glob pattern (e.g. `*.py`)
  - `max_results: int` — 可选,默认 200
  - `case_insensitive: bool` — 默认 False
- **返回**: `{pattern, matches: [{path, line_number, line, context_before, context_after}], count}`
- **安全**: cwd 必须 ≤ workspace_dir, 不读 `.git/`, `node_modules/`, `.venv/`, `dist/`, `build/`
- **性能**: 限制总读字节 (5 MB), 超限报错而不是 silently 截断

### 通用安全检查

**所有文件工具 (`read_file / write_file / edit_file / ls / glob / grep`)**:
1. 解析 path 为 absolute
2. 检查 `resolved_path.is_relative_to(workspace_dir)` — 失败返回 `{"error": "path escapes workspace_root"}`
3. 检查路径不指向 protected prefix (`.git/`, `.claude/`, `node_modules/`, `.venv/`)
4. audit_log 一条 (`tool.fs_access`, payload 含 path, op, tenant_id)

**所有工具**:
- workspace_dir 解析失败 (`workspace_id` 无效或 workspace 不存在) → `{"error": "workspace not found"}`
- 权限拒绝 → audit_log + `{"error": "permission denied"}`
- 每次 invocation 写一条 `audit_log` (event_type=`tool.fs_access` 或 `tool.bash_executed`), payload 含 {tenant_id, workspace_id, call_id, tool_name, duration_ms}

### workspace_dir 怎么来

现在 `CustomInvokerPort.invoke()` 已经接 `workspace_id`。再加一步:在 lifespan / ToolFactory 注入时,把 `workspace_id` 映射到 host 上的 workspace 目录。

具体路径设计:
```python
# backend/modules/tool/src/qzdap/modules/tool/adapter/adapters/workspace_paths.py
def resolve_workspace_dir(workspace_id: UUID) -> Path:
    """Map workspace_id to a host filesystem path.

    Phase 1: workspace_dir = settings.workspace_root / str(workspace_id)
             (env: QZDAP_WORKSPACE_ROOT=/var/qzdap/workspaces, default)
    Phase 2: 从 admin_workspaces 表读 sandbox_path 字段 (TODO)
    """
```

env var: `QZDAP_WORKSPACE_ROOT` (default `/var/qzdap/workspaces`),每个 workspace 一个子目录 `<root>/<workspace_id>/`。

dev 环境现在没这个目录, 测试时用 `/tmp/qzdap-workspaces/<workspace_id>/` 临时目录。

## 文件改动清单

1. **`backend/modules/tool/src/qzdap/modules/tool/adapter/adapters/custom_invoker.py`** — 加 7 个 built_in_invoke_*, 加 `_resolve_workspace_dir()` helper, 加 `_safe_resolve()` 安全检查
2. **`backend/modules/tool/src/qzdap/modules/tool/adapter/adapters/workspace_paths.py`** (新) — workspace_id → 路径
3. **`backend/modules/tool/src/qzdap/modules/tool/adapter/adapters/__init__.py`** — 导出新工具
4. **`backend/composition/qzdap_app/src/qzdap/composition/lifespan.py`** — 注册 7 个到 custom_invoker + seed 到 admin_tools 表 (含 existing 的 echo/reverse/clock/web_search/http_fetch)
5. **`backend/composition/qzdap_app/src/qzdap/composition/settings.py`** — 加 `workspace_root: str = "/var/qzdap/workspaces"`
6. **新文件 `backend/tests/manual/test_builtins_e2e.py`** (新) — 7 个工具的 e2e 跑通 (docker 内 / 沙箱外),验证路径安全
7. **`backend/tests/shared/fixtures.py`** — 测试 fixture 加 workspace_dir 创建

## 工作量

| 工具 | 实现 |
|---|---|
| workspace_paths.py + settings + helper | 0.5 天 |
| bash | 0.5 天 |
| read_file + write_file + edit_file | 1 天 |
| ls + glob + grep | 1 天 |
| 测试 + audit_log + lifespan seed | 1 天 |
| 安全渗透测试 (恶意 path / cd .. 等) | 0.5 天 |

总计约 **4 天**。每实现一个跑一次,确保不破现有 177 个测试。

## 测试计划

1. **happy path**: 每个工具在干净 workspace 里跑通, 返回预期 dict
2. **路径穿越**: `read_file("../../etc/passwd")`, `write_file("/etc/xxx")`, `ls "../"`, `glob "../../**"` 都必须返回 error
3. **protected prefix**: 尝试读写 `.git/config`, `node_modules/xxx`, `.venv/bin/python` 都拒绝
4. **bash cwd 限制**: `bash {command: "cd ../../../; ls"}` cwd=workspace_dir, 出来路径仍在 workspace
5. **audit_log**: 每次 invocation 后 `audit_log` 表有新行
6. **并发**: 同一 workspace 10 个并发 read_file, 文件锁正确(读不需要锁, 写需要)

## 不做 (out of scope)

- ❌ `Bash` 不在 sandbox 跑 (要 sandbox 化是另一个 ticket)
- ❌ `TaskCreate/Update/List/Get` (前端 todo 替代)
- ❌ `AskUserQuestion` (前端 NoticeBanner 替代)
- ❌ `EnterPlanMode` (前端 PlanProposalCard 替代)
- ❌ `Notebook*` (qzdap 不跑 notebook)
- ❌ `Mcp*` (qzdap 的 MCP 走 admin_tools 表)
- ❌ 文件锁 / 冲突合并 (`edit_file` 先做 exact match, merge 留给后续)

## 关联

- 上一篇 ticket `sandbox-network-egress-control.md` 收紧 sandbox 网络: 本次 ticket 不涉及 sandbox, 但 `bash` 的安全模型和它一致 (LLM 拿到 shell, 但走 workspace 白名单)
- 前一篇 `web_search / http_fetch` 已 done, 这次把它们一起列进 admin_tools seed