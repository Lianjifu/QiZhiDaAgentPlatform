# observability — 可观测

> 能力域之一。负责调用链路记录、成本归集与质量评分，是「成本可追溯」与「调用链路可还原」的落点。

## 职责

- **运行记录**（run）：每一次 LLM / 工具 / 技能 / 记忆 / 知识 / 工作流 / 渠道 / 评测 / 治理动作
- **成本记录**（cost）：按次或按量归集美元成本
- **质量评分**：按模板 + 版本查评测结果
- 事件总线上的**记录订阅器**

## 源码位置

```
backend/modules/observability_module/src/qzdap/modules/observability_module/
├── domain/          entities.py（RunRecord · CostRecord）· enums.py（RunType · RunStatus · CostType）· errors.py
├── application/
│   ├── services.py   ObservabilityService
│   ├── recorder.py   ObservabilityRecorder（EventBus handler）
│   ├── pricing.py    PricingCatalog · ModelPricing
│   └── use_cases/    build() 工厂：record_run · record_cost · list_runs · list_costs · aggregate_costs · get_quality_score
└── adapter/
    ├── http/         router.py
    └── persistence/  models.py · repositories.py
```

## HTTP 端点

前缀 `/v1/observability`。**只有 3 个读端点，没有写端点**。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/v1/observability/runs` | 运行记录列表（可按 `run_type` 过滤） |
| GET | `/v1/observability/costs` | 成本明细或聚合（`group_by=cost_type\|workspace\|model`） |
| GET | `/v1/observability/quality/{template_id}/{version_id}` | 某 agent 某版本的质量分 |

所有记录都来自事件总线，**没有 HTTP 写入路径**。

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `run_records` | 运行记录 | id / tenant_id / run_type(llm\|tool\|skill\|memory\|knowledge\|workflow\|channel\|eval\|governance) / source_id / actor_id / latency_ms / status |
| `cost_records` | 成本记录 | id / run_id(FK RESTRICT) / cost_type / amount_usd(NUMERIC 12,6) / quantity / unit / model_id |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `RunRecord` `CostRecord` | 聚合根 |
| domain | `RunType` `RunStatus` `CostType` | 枚举 |
| application | `ObservabilityService` | 模块门面 |
| application | `ObservabilityRecorder` | **事件订阅器** |
| application | `PricingCatalog` `ModelPricing` | 定价表 |
| application | `record_run` `record_cost` `list_runs` `list_costs` `aggregate_costs` `get_quality_score` | 用例（由 `build()` 工厂装配） |

## 实现要点

- **订阅 10 个事件名**：`SUBSCRIBED_EVENTS` 列出关心的事件；`handle()` **永不抛异常**，缺 `tenant_id` 就丢弃——观测组件不能拖垮业务
- **成本定价兜底**：`PricingCatalog.llm_cost` 对未知 model 回落到 `default` 定价，不会因为模型没登记就漏记成本
- **成本可归属到 turn**：`UsageChunk` 带 6 个归属维度（tenant / workspace / user / agent / agent_version / model_version），与本模块的记录口径一致
- **错误码统一**：`ObservabilityPolicyDenied` 是权限异常，`RunRecordNotFound` / `CostRecordNotFound` / `QualityScoreNotFound` 是查找异常
- **链路用 OpenTelemetry**：span 由 `libs/observability` 的 `get_tracer` 打出，本模块负责把关键事件**持久化**成可查询的记录
- **Prometheus 指标**：`/metrics` 暴露指标

## 已知边界

- ⚠️ **订阅的 5 类事件永远没有记录**：`ModelInvoked` / `SkillInvocationCompleted` / `MemoryWritten` / `KnowledgeAssetIngested` / `WorkflowRunCompleted` —— model / skill / memory / knowledge / orchestration 五个模块都**没有 `domain/events.py`**，也没有 publish 调用。实际只有 `ToolCompleted` / `ToolFailed` / `ChannelReplySent` / `EvalRunCompleted` 有发布方
- ⚠️ **quality 端点恒返回 404**：`get_quality_score` 依赖 `service.eval_query`（`EvalRunQueryPort`），而 `lifespan.py:1455` 构造 `ObservabilityService.from_parts` **只传了 run_repo / cost_repo / pricing，没传 eval_query**
