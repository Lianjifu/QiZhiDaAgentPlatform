# memory — 记忆分层

> 能力域之一。负责会话缓冲与长期事实层的写入、召回、提炼、淘汰与策略管理。

## 职责

- **会话缓冲**：当前会话的消息历史（管理端按「L1」视图展示）
- **L2 事实层**：用户偏好 / 角色 / 部门等结构化事实，状态 `pending` / `confirmed` / `retired`
- **召回**：向量优先 + 关键词兜底，跨轮次给 agent 提供上下文
- **晋升**：L2 事实提升为团队知识候选 → 落到知识库
- **保留策略**：按标签配置的保留规则与淘汰
- **数据主体请求**：记忆范围内的导出与删除

## 分层现状

| 层 | 状态 | 落点 |
|---|---|---|
| 会话缓冲（原 L1） | ✅ 在用 | `session_memory_buffer` 表 |
| L2 事实层 | ✅ 在用 | `admin_memory_l2` 表 |
| L3 团队记忆 | ❌ **已退役** | 写入直接拒绝；晋升终点改为 knowledge |

`admin_memory_l1` 表已由迁移 0057 退役，`admin_memory_l3` 由 0059 退役。管理端看到的「L1」实际是会话缓冲的视图。

## 源码位置

```
backend/modules/memory/src/qzdap/modules/memory/
├── domain/          entities.py（L2Fact · PromotionEvent · RetentionPolicy）· errors.py
├── application/
│   ├── services.py        MemoryRuntimeService（运行时：写入 / 召回 / 淘汰）
│   ├── admin_service.py   MemoryAdminService（管理端：改写 / 晋升 / 策略 / 趋势）
│   ├── admin_rules.py     AdminEditRules（人工改写校验）
│   ├── governance.py      MemoryDataSubjectScope（数据主体删除范围）
│   └── ports.py
└── adapter/
    ├── persistence/  models.py · repositories.py · buffer_repository.py · vector_adapter.py
    ├── vectorize.py       L2 向量化
    ├── candidates.py      晋升候选
    ├── eviction.py        淘汰（置 retired，不物理删）
    └── embedding/         openai_adapter.py · http_adapter.py · noop_adapter.py
```

## HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/admin/memory/l1` | 会话缓冲列表（管理端视图） |
| GET | `/api/admin/memory/l1/{item_id}` | 单条详情 |
| POST | `/api/admin/memory/l1/{item_id}/flush` | 清除单条 |
| POST | `/api/admin/memory/l1/flush-all` | 全部清除 |
| GET | `/api/admin/memory/l2` | L2 事实列表 |
| GET | `/api/admin/memory/l2/{item_id}` | L2 详情 |
| PATCH | `/api/admin/memory/l2/{item_id}` | 人工改写 |
| POST | `/api/admin/memory/l2/promote` | 晋升到知识库 |
| GET | `/api/admin/memory/promotions` | 晋升记录 |
| GET | `/api/admin/memory/policies` | 保留策略列表 |
| GET | `/api/admin/memory/policies/{label}` | 策略详情 |
| POST | `/api/admin/memory/policies/{label}/publish` | 发布策略 |
| GET | `/api/admin/memory/policies/{label}/agents` | 策略绑定的 agent |
| GET | `/api/admin/memory/trend` | 使用趋势 |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `admin_memory_l2` | 长期事实 | id / tenant_id / workspace_id / user_id / label / content / status / confidence / source_turn_id |
| `session_memory_buffer` | 会话缓冲 | id / session_id / turn_id / role / content / updated_at |
| `admin_memory_promotions` | 晋升记录 | id / memory_id / target_kb_id / status |
| `admin_memory_policies` | 按标签的保留策略 | id / tenant_id / label / retention_days / scope / status |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `L2Fact` `PromotionEvent` `RetentionPolicy` | 聚合根；`MemoryLayer = Literal["l2"]` |
| application | `MemoryRuntimeService` | 运行时：`write_turn` / `recall` / `evict` / `refine_buffers` |
| application | `MemoryAdminService` | 管理端：改写 / 晋升 / 策略 / 趋势 |
| application | `AdminEditRules` | 人工改写的校验规则 |
| application | `MemoryDataSubjectScope` | 数据主体请求的记忆范围 |
| contract | `RetrievalPipeline` | 向量优先 + 词法兜底 + 阈值 abstain + 降级可见 |
| contract | `WriterPipeline` | 每轮结束写一次 |

## 实现要点

- **召回顺序**：向量优先 → 词法兜底 → 低于阈值 abstain（宁可不召回，也不给错记忆）
- **作用域三层隔离**：租户 / 工作区 / 用户 —— 用户 A 的会话召回结果里不含用户 B 的记忆，各有测试
- **淘汰不删数据**：`adapter/eviction.py` 置 `retired` 而非物理删除，审计仍在
- **晋升终点是知识库**：L2 事实 → `admin_memory_promotions` → `KnowledgeCandidateAdapter` → 知识库文档，没有 L3 表
- **写路径在每轮结束后触发**：`graph/runner.py:1184 _write_memories` → `WriterPipeline`
- **向量补写是异步的**：由 `Memory C5` 的补写队列处理（进程内基线白名单里的 `InMemory*` 之一）

## 已知边界

- ⚠️ **L3 已退役**，写团队级记忆会被直接拒绝（`admin_service.py:373`）
- ⚠️ **策略没有自动执行器**：`/policies/{label}/publish` 只存策略，没有后台任务按策略实际淘汰
- ⚠️ `NoOpEmbedding` 返回 1536 维**零向量**——只在 test / ci 允许；开发环境被 `UnavailableEmbeddingAdapter` 拦截（503），不会静默用零向量做召回
- ⚠️ 记忆策略的 `retentionDays` / `autoSummarize` 两个字段**运行时只消费 `enabled`**——字段形状保留是为了前端表单不坏，运行时不再读它们
