# self_evolution — 自进化

> 能力域之一。负责「进化候选」的登记、审批与落地——把观察到的改进点变成可审的候选改动。

⚠️ **本模块没有反馈池，也没有知识回流**。平台 README 描述的「反馈池 / 规则分诊 / 知识回流」这条线，代码里的实现范围远小于描述。

## 职责

- 进化候选（candidate）的创建、查询、审批、拒绝、落地
- 按 `kind` 分派到不同的落地守卫
- **默认只写草稿**，不碰线上

## 四种候选类型

`kind` ∈ `memory_promote` / `skill_patch` / `routing_hint` / `dream`，每种对应一个 `ApplyGuard`：

| kind | 守卫 | 落地目标 |
|---|---|---|
| `memory_promote` | `MemoryWorkingLayerGuard` | 记忆工作层 |
| `skill_patch` | `SkillDraftGuard` | 技能草稿 |
| `routing_hint` | `RoutingDraftGuard` | 路由提示 |
| `dream` | `DreamGuard` | 自由形式 |
| 未知 | `DirectApplyGuard` | 兜底，什么都不做 |

## 源码位置

```
backend/modules/self_evolution/src/qzdap/modules/self_evolution/
├── domain/          entities.py（EvolveCandidate）· errors.py · events.py
├── application/
│   ├── evolution_service.py  EvolutionCandidateService
│   ├── apply_guard.py        ApplyGuard 协议 + 4 个 kind 守卫 + KindDispatchingApplyGuard + DirectApplyGuard
│   └── ports.py              EvolutionCandidateRepository · EvolutionEventPublisher · ClockPort · IdGeneratorPort · DraftStore
└── adapter/
    ├── http/         router.py
    └── persistence/  models.py · repositories.py
```

## HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/v1/evolve/candidates` | 创建候选 |
| GET | `/v1/evolve/candidates?status=` | 候选列表 |
| GET | `/v1/evolve/candidates/{id}` | 候选详情 |
| POST | `/v1/evolve/candidates/{id}/approve` | 批准 |
| POST | `/v1/evolve/candidates/{id}/reject` | 拒绝 |
| POST | `/v1/evolve/candidates/{id}/apply` | **落地** |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `evolve_candidates` | 进化候选（**本模块唯一的表**） | id / tenant_id / kind / payload(JSONB) / confidence / trigger_reason / **fingerprint**（租户内唯一，去重）/ status(pending\|approved\|rejected\|applied) / requester / approver / reviewed_at / applied_at / expires_at |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `EvolveCandidate` | 聚合根；`EvolveStatus` 状态枚举 |
| application | `EvolutionCandidateService` | create / get / list_by_status / approve / reject / apply / expire_if_due |
| application | `KindDispatchingApplyGuard` | 按 kind 分派到具体守卫 |
| application | `MemoryWorkingLayerGuard` `SkillDraftGuard` `RoutingDraftGuard` `DreamGuard` | 四种 kind 的落地策略 |
| application | `DirectApplyGuard` | 未知 kind 的兜底 |
| application | `JsonlDraftStore` `InMemoryDraftStore` | 草稿存储 |

领域事件：`EvolutionCandidateCreated` / `EvolutionCandidateDecided` / `EvolutionCandidateApplied`。

## 实现要点

- **租户内去重**：`fingerprint` 唯一键——同一指纹的候选不会重复创建
- **人工审批是硬门**：`apply` 只能对 `approved` 状态的候选执行
- **落地模式可配**：`composition/settings.py:243` 的 `evolution_apply_guard_mode`，默认 `"drafts"`，可切 `"direct"`
- **草稿落 JSONL**：所有 kind 守卫只往 `<base>/<tenant>/<kind>.jsonl` 追加，标记 `promotion_target: "draft_only"`

## 已知边界

- ⚠️ **apply 只写草稿，从不改线上**——不写 live memory / skill registry / routing table。正式晋升流程在 `apply_guard.py` 的模块 docstring 里明说 "out of scope"
- ⚠️ **切 `direct` 模式等于关闭全部落地**：`DirectApplyGuard` 什么都不做，只记 `mode: "direct"`
- ⚠️ **没有反馈池，也没有知识回流**：本模块 grep 不到 `feedback` / `knowledge` / 回流相关实现。平台侧的 `feedback.*` collection 是 platform 里的**种子 JSON 文档**，不回流到本模块
- ⚠️ **没有任何模块自动创建 candidate**：唯一的创建入口是 HTTP router（人工创建），没有从反馈、失败样本、评测结果自动生成候选的链路
