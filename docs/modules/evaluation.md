# evaluation — 评测

> 能力域之一。负责评测数据集、用例、运行与评分，为 agent 版本发布提供门禁依据。

## 职责

- 评测数据集（dataset）与用例（case）的管理
- **评测运行的调度与执行**
- **评分**：关键词命中率 + 时延约束
- 评测结果供 agent_factory 的版本发布门禁反查

## 源码位置

```
backend/modules/evaluation/src/qzdap/modules/evaluation/
├── domain/          entities.py（EvalDataset · EvalCase · EvalRun · EvalScoreRecord）· errors.py · events.py
├── application/
│   ├── services.py    EvaluationService
│   ├── runner.py      EvalRunner（并发跑用例）
│   ├── scoring.py     score_case（评分规则）
│   ├── use_cases/     StartEvalRun · GetEvalRun · ListEvalRuns · GetEvalDataset · ListEvalDatasets · ListEvalCases
│   └── ports.py       EvalDatasetRepository · EvalRunRepository · SubAgentPort
└── adapter/
    ├── http/         router.py
    ├── persistence/  models.py · repositories.py
    └── sub_agent_stub.py
```

黄金集在 `backend/composition/qzdap_app/src/qzdap/composition/fixtures/golden_dataset.py`（50 条）。

## HTTP 端点

前缀 `/v1/eval`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/v1/eval/datasets` | 数据集列表 |
| GET | `/v1/eval/datasets/{did}` | 数据集详情 |
| GET | `/v1/eval/datasets/{did}/cases` | 用例列表 |
| POST | `/v1/eval/runs` | **发起评测运行**（返回 202，后台异步跑） |
| GET | `/v1/eval/runs` | 运行列表 |
| GET | `/v1/eval/runs/{rid}` | 运行详情 |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `eval_datasets` | 数据集 | id / tenant_id / name / kind(builtin\|custom) / status / case_count / metadata |
| `eval_cases` | 用例 | id / dataset_id(CASCADE) / ordinal / input / expected_keywords(ARRAY) / min_keywords_hit_ratio / max_latency_ms |
| `eval_runs` | 运行 | id / tenant_id / template_id / version_id / status / mean_score / passed_count / failed_count / idempotency_key（部分唯一索引） |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `EvalDataset` `EvalCase` `EvalRun` `EvalScoreRecord` | 聚合根 |
| application | `EvaluationService` | 模块门面 |
| application | `EvalRunner` | 并发执行评测 |
| application | `score_case` | 单用例评分 |
| application | `StartEvalRunUseCase` 等 6 个 | 具体用例 |
| domain | `EvalRunStarted` `EvalRunCompleted` `EvalRunFailed` | 领域事件 |

## 实现要点

- **发起运行先过策略闸门**：`StartEvalRunUseCase.execute` 先调 `policy_guard.check(action="evaluation:run:start")`
- **幂等**：按 `idempotency_key` 查重，冲突抛 `IdempotencyKeyConflict`
- **异步执行**：`asyncio.create_task` 起后台任务，用 `_BACKGROUND_TASKS` 集合保引用防 GC
- **并发受控**：`asyncio.Semaphore(concurrency=4)` 限流
- **单用例超时 60s**：走 `SubAgentPort.run_turn_to_completion`
- **评分规则**：**大小写不敏感子串命中**算 `hit_ratio`，与 `min_keywords_hit_ratio` 和 `max_latency_ms` 一起判过；**任一用例出错则整轮 failed**
- **发布门禁**：`EvalGateFailed` 是业务规则异常，agent_factory 的版本发布会反查评测运行

## 已知边界

- ⚠️ **没有创建 / 修改 dataset 或 case 的 HTTP 端点**——只有 GET 与 `POST /runs`。数据集靠 `fixtures/golden_dataset.py` 播种，自定义数据集目前无法通过 API 建
- ⚠️ `adapter/sub_agent_stub.py` 的 `StubSubAgentPort` 返回 `[stub:输入]`，在 `ar_factory` 缺失时启用（`lifespan.py:1250-1265`），此时**评测必挂**
- ⚠️ 事件 topic 有两套命名：evaluation 的 `TOPIC = "evaluation.run.completed"`（dotted），而 `EventEnvelope.wrap` 用类名 `event_name`（`EvalRunCompleted`）——observability 订阅的是类名，对得上；governance 的订阅表里记的却是 dotted 名，两边不一致
