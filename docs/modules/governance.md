# governance — 策略、审批与审计

> 能力域之一。负责策略引擎、人工审批、审计留痕与数据主体请求。

⚠️ **额度不在本模块**——额度是模型侧的算力与成本约束，实现见 [model](./model.md)。

## 职责

- **策略**：可配的规则，判定某个动作是允许 / 拒绝 / 需审批
- **审批**：高风险动作的人工放行，含 TTL 与幂等
- **审计**：把系统事件落成审计流水
- **数据主体请求**：个人数据的导出与删除

## 源码位置

```
backend/modules/governance/src/qzdap/modules/governance/
├── domain/          entities.py · errors.py · events.py
├── application/
│   ├── policy_service.py     PolicyService
│   ├── approval_service.py   ApprovalService
│   ├── policy_evaluator.py   PolicyEvaluator（判定核心）
│   ├── audit_recorder.py     AuditRecorder（事件订阅写审计）
│   ├── data_subject.py       DataSubjectService（导出 / 删除）
│   └── ports.py
└── adapter/
    ├── http/         router.py
    ├── persistence/  models.py · repositories.py
    ├── guard/        decorator.py（policy_check 策略装饰器）
    └── subscribers/  audit_subscriber.py
```

## HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/v1/policies` | 建策略 |
| GET | `/v1/policies` | 策略列表 |
| GET | `/v1/policies/{rule_id}` | 策略详情 |
| PATCH | `/v1/policies/{rule_id}` | 更新策略 |
| DELETE | `/v1/policies/{rule_id}` | 删策略 |
| GET | `/v1/approvals` | 审批列表（`pending_only` 默认 true） |
| GET | `/v1/approvals/{approval_id}` | 审批详情 |
| POST | `/v1/approvals/{approval_id}/approve` | 批准 |
| POST | `/v1/approvals/{approval_id}/deny` | 拒绝 |
| POST | `/v1/data-subject/delete` | 数据主体删除 |
| POST | `/v1/data-subject/export` | 数据主体导出 |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `policies` | 策略规则 | id / tenant_id / subject_type / subject_ref / action_pattern / effect / priority / approval_required / quota(JSONB) / enabled |
| `approvals` | 审批单 | id / requester / resource / action / status / approver / expires_at / correlation_id |
| `decision_events` | 判定留痕 | id / actor / action / effect / rule_id / approval_id / latency_ms |
| `audit_log` | 审计流水 | id / actor_id / event_type / payload(JSONB) |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| application | `PolicyService` | 策略增删改查 |
| application | `ApprovalService` | create / approve / deny / expire_due / list_pending |
| application | `PolicyEvaluator` | **判定核心**：evaluate → allow / deny / require_approval |
| application | `AuditRecorder` | 订阅事件写审计 |
| application | `DataSubjectService` | export / delete |
| adapter | `policy_check` | 策略装饰器，在动作执行前套一层判定 |

## 实现要点

- **默认放行**：没有匹配策略时 `PolicyEvaluator` 返回 allow —— 策略是**收紧**机制，不是**许可**机制
- **热路径带缓存**：`PolicyEvaluator` 有 30s TTL 的规则缓存，避免每次调用都查库
- **优先级明确**：多个策略命中时按 `priority` 选 winner，不做全量求值
- **DENY 是终局**：命中 DENY 直接拒绝，不进入审批流
- **REQUIRE_APPROVAL 会铸一张审批单**：生成审批记录并落 `DecisionEvent`
- **审批参数摘要防串**：审批单存参数指纹，恢复时校验参数一致——批的是 A 工具就不能执行 B 工具
- **审批 TTL 与过期清理**：`ApprovalService.expire` 定期把过期审批置为过期态，过期不执行
- **`correlation_id` 做审批幂等**：同一次审批决策重复提交不会重复执行
- **审计是订阅式的**：`AuditRecorder` 订阅领域事件写审计，模块本身不需要主动调用
- **审计脱敏**：`AuditRecorder._scrub` 会把 payload 里的 `password` / `api_key` / `secret` / `token` 洗掉
- **工具调用 100% 审计**：工具侧另在 tool 模块落 `audit_log`（actor_id / workspace_id / duration_ms / risk_level）

## 已知边界

- ⚠️ **`policies.quota` 是死字段**：只在策略 CRUD 里存取，**评估器从不读它**。真正的额度实现在 [model](./model.md) 的 `QuotaService`
- ⚠️ **数据主体删除只覆盖 memory 一个 scope**：`lifespan.py:1105-1128` 只注册了 `MemoryDataSubjectScope`，knowledge / session / eval 等域都没有 scope
- ⚠️ **审计事件表有一半是空的**：`audit_recorder.py:158+` 的订阅列表里 `SkillInstalled` / `MemoryWritten` / `KnowledgeAssetIngested` / `WorkflowRunCompleted` / `model.*` **没有任何模块发布**——这些模块根本没有 `domain/events.py`
- ⚠️ `DecisionRecorded` 事件类存在但**从未被 publish**，observability 里对应的分支是死代码
- ⚠️ `adapter/http/router.py:54-58` 的 `_require_actor` / `_require_admin` 是 placeholder，靠组合根的 `dependency_overrides` 覆盖
