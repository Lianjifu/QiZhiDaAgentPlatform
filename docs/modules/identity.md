# identity — 身份与租户

> 能力域之一。负责租户、工作区、用户、API 密钥与 JWT 鉴权，是所有其他能力域的信任根。

## 职责

- 建立**租户 → 工作区 → 用户**三层隔离结构
- 签发与校验登录令牌（JWT）
- 签发 / 吊销 API 密钥（只存 hash，明文不落库）
- 成员邀请与接受
- 账号设置读写

## 源码位置

```
backend/modules/identity/src/qzdap/modules/identity/
├── domain/          tenant.py · workspace.py · user.py · api_key.py · events.py
├── application/     services.py（IdentityService 门面）· use_cases/ · ports.py
└── adapter/
    ├── http/        router.py · account_router.py · auth/router.py · deps.py · mappers.py
    └── persistence/ models.py · control_models.py · repositories.py
```

## HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/v1/identity/login` | 账号密码登录，签发 JWT |
| POST | `/v1/identity/tenants` | 建租户 |
| GET | `/v1/identity/tenants/current` | 当前租户 |
| POST | `/v1/identity/users` | 注册用户 |
| GET | `/v1/identity/users/me` | 当前用户 |
| GET | `/v1/identity/users/{uid}` | 用户详情 |
| POST | `/v1/identity/users/{uid}/api-keys` | 签发 API 密钥 |
| POST | `/v1/identity/users/{uid}/api-keys/{kid}/revoke` | 吊销密钥 |
| GET | `/api/account/settings` | 账号设置读取 |
| PUT | `/api/account/settings` | 账号设置保存 |
| GET | `/api/workspaces/current/members` | 当前工作区成员列表 |
| POST | `/api/workspaces/current/members/invite` | 邀请成员 |
| POST | `/api/workspaces/current/invitations/{id}/accept` | 接受邀请 |
| GET | `/api/admin/settings/audit` | 控制面审计流水 |
| GET | `/api/home/insights` | 首页洞察数据 |

工作区的创建与查询在 `/v1/identity/workspaces`。

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `tenants` | 租户 | id / name / status |
| `workspaces` | 工作区（租户内的隔离单元） | id / tenant_id / name / status |
| `users` | 用户 | id / tenant_id / email / password_hash / metadata(JSONB) / status |
| `user_workspaces` | 用户 ↔ 工作区成员关系 | user_id / workspace_id / role |
| `api_keys` | API 密钥（**只存 hash**） | user_id / key_hash / revoked_at |
| `workspace_invitations` | 成员邀请 | workspace_id / token / status |
| `identity_control_audit` | 控制面操作审计 | actor_id / action / payload |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `Tenant` `Workspace` `User` `APIKey` | 四个聚合根，frozen dataclass + 状态迁移方法 |
| application | `IdentityService` | 模块门面，聚合各 use case |
| application | `CreateTenantUseCase` `RegisterUserUseCase` `CreateWorkspaceUseCase` `IssueAPIKeyUseCase` `RevokeAPIKeyUseCase` `LoginUseCase` | 具体用例 |
| adapter | `IdentityUserDirectory` | 把 `users.metadata` 里的 departments / tags / roles 收敛成 `UserAttributes` 端口 |

## 实现要点

- **API 密钥不存明文**：`api_keys` 表只有 hash，签发时明文只在响应里返回一次
- **租户作用域在 ORM 层强制**：`users` 等表继承 `TenantScopedMixin`，DB 层自动追加 `tenant_id` 过滤（详见 [功能模块总览](./README.md)）
- **JWT 校验后绑定租户**：`libs/auth` 的中间件验签后把 `tenant_id` 写入 `ContextVar` 与 request state，其余模块从统一上下文取，不再各自解析

## 已知边界

- ⚠️ **部门 / 标签 / 角色没有结构化列**，只靠 `users.metadata` 这个 JSONB 约定 —— 无法在 DB 层按部门过滤
- ⚠️ `adapter/persistence/repositories.py:154` 留有 TODO：同一用户匹配多条成员关系时取首条
- ⚠️ `GET /api/home/insights` **跨模块直查**了 agent_runtime 的 `session_turns` 表（`account_router.py:419`）—— 属越层依赖，模块间只走事件 / 端口的约定在此处被打破
