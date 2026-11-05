# skill — 技能

> 能力域之一。负责技能的注册、元数据管理、MCP 接入与**沙箱执行**。

## 职责

- 技能的注册、查询、更新、删除、批量操作
- 技能的分类与标签
- **MCP 服务器接入与探测**
- 技能在**沙箱**中执行（gVisor / runsc）
- 技能调用记录与状态

## 与 tool 的分工

| | tool | skill |
|---|---|---|
| 本质 | 平台内置 / 外部 API 的调用单元 | **上传的代码包**，在沙箱里跑 |
| 执行位置 | qzdap-app 进程内 | gVisor 沙箱容器 |
| 来源 | 平台声明的 spec | 管理员上传的包（manifest + entrypoint） |

agent 的工具白名单里，skill 与 tool 统一进 `tools` 字段，通过 `catalog_binding_reader` 读取。执行顺序是 **skill → sandbox → 目录工具**，同名时先 skill。

## 源码位置

```
backend/modules/skill/src/qzdap/modules/skill/
├── domain/          entities.py（SkillPackage · Invocation）· errors.py · events.py
├── application/     services.py（SkillService）· ports.py
└── adapter/
    ├── http/         router.py
    ├── persistence/  models.py · repositories.py
    └── mcp/          mcp_client.py（JSON-RPC）
```

沙箱执行在独立运行时：

```
backend/runtimes/sandbox_runtime/src/qzdap/runtimes/sandbox_runtime/
├── executor.py       GvisorExecutor（runsc）
├── service.py        作业编排 · 镜像白名单校验
├── settings.py       QZDAP_SANDBOX_* 配置
└── jobs.py
```

## HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/admin/skills` | 技能列表 |
| POST | `/api/admin/skills` | 注册技能 |
| GET | `/api/admin/skills/{skill_id}` | 技能详情 |
| PATCH | `/api/admin/skills/{skill_id}` | 更新技能 |
| DELETE | `/api/admin/skills/{skill_id}` | 删除技能 |
| POST | `/api/admin/skills/bulk` | 批量操作 |
| POST | `/api/admin/skills/mcp/probe` | **MCP 服务器探测** |
| GET | `/api/catalog/skills` | 用户侧目录 |
| GET | `/api/catalog/skills/{skill_id}` | 技能详情（用户侧） |
| POST | `/api/catalog/skills/{skill_id}/favorite` | 收藏 |
| POST | `/api/catalog/skills/{skill_id}/record-use` | 记录使用 |
| GET | `/api/user/skills` | 我可用的技能 |
| POST | `/api/dev/skills/{name}/invoke` | 开发态直接调用 |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `admin_skill_packages` | 技能包 | id / tenant_id / name / version / manifest(JSONB) / **network_policy**(ENUM) / cpu_quota / memory_bytes / timeout_seconds / status |
| `admin_skill_invocations` | 调用记录 | id / skill_id / turn_id / status / input / output / duration_ms |

`network_policy` 枚举：`none` / `default` / `unrestricted`（建表时定义于迁移 0005）。

## 实现要点

- **沙箱用 gVisor**：`executor.py:106` 的 `GvisorExecutor` 声明 `runtime_name="runsc"`；启动前 `ensure_runsc()` 查 Docker `/info` 的 Runtimes，没有 `runsc` 就抛 `SANDBOX_RUNSC_UNAVAILABLE`
- **容器加固**：`ReadonlyRootfs` + `CapDrop:["ALL"]` + `SecurityOpt:["no-new-privileges"]` + `PidsLimit` + `NanoCpus` + `Memory` + `Tmpfs /tmp 64m`
- **镜像白名单强制**：`settings.py` 的 `QZDAP_SANDBOX_IMAGES`（逗号分隔），`service.py:34` 在执行前校验，不在白名单直接拒绝
- **网络三档**：`risk == "low"` 的技能强制 `network="none"`；其余由 manifest 的 `network_policy` 收窄为 `none` / `bridge`
- **MCP 走 JSON-RPC**：`adapter/mcp/mcp_client.py`，`POST /api/admin/skills/mcp/probe` 用于管理员填服务器地址时先探一次

## 已知边界

- ⚠️ **网络出站没有域名级白名单**：只有 `none` / `bridge` 两档，`bridge` 意味着容器可出网但无法限定目标域名。方案见 [待实施 · 沙箱网络出站管控](../planned/sandbox-network-egress-control.md)
- ⚠️ `admin_skill_packages.network_policy` 的 `unrestricted` 取值在运行时**被收窄为 `bridge`**——设计意图与实现有落差
- ⚠️ `executor.py` 的 `ensure_runsc()` 在没装 gVisor 的机器上直接失败——本地开发需要 Docker 支持 runsc
