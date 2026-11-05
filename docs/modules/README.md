# 功能模块文档

> **企智搭 · 智能体平台**的 15 个能力域，每域一篇。只写**当前代码已实现的行为**——不写改造计划。
>
> 平台以 agent 为中心：会话 = 某个智能体的某个版本在跑，其余能力围绕它组织。

## 怎么读

| 你的目的 | 建议路径 |
|---|---|
| 搞懂一次对话怎么跑起来 | [agent-runtime](./agent-runtime.md) → [tool](./tool.md) → [knowledge](./knowledge.md) → [memory](./memory.md) |
| 搞懂多租户隔离 | [identity](./identity.md) → [platform](./platform.md) |
| 搞懂治理与额度 | [governance](./governance.md) → [model](./model.md) |
| 搞懂管理台每个页面的数据来源 | [platform](./platform.md)（**注意看板是种子数据**）→ [observability](./observability.md) |
| 判断某个功能是不是真做完了 | 直接看每篇末尾的「已知边界」 |

## 能力域总表

| # | 域 | 一句话职责 | 文档 |
|---|---|---|---|
| 1 | `identity` | 租户 / 工作区 / 用户 / JWT / API 密钥 —— 全平台的信任根 | [identity.md](./identity.md) |
| 2 | `agent_runtime` | 会话与轮次、SSE 流式、多智能体派发、智能体目录 | [agent-runtime.md](./agent-runtime.md) |
| 3 | `agent_factory` | 智能体模板与版本化，版本发布门禁 | [agent-factory.md](./agent-factory.md) |
| 4 | `tool` | 工具注册 / 调用 / 幂等 / 重试 / 熔断 / 审计 | [tool.md](./tool.md) |
| 5 | `skill` | 技能包注册、MCP 接入、沙箱执行 | [skill.md](./skill.md) |
| 6 | `knowledge` | 知识库 · 分块 · 向量检索 · RAG · 知识源同步 | [knowledge.md](./knowledge.md) |
| 7 | `memory` | 会话缓冲 + L2 事实层，召回 / 晋升 / 淘汰 | [memory.md](./memory.md) |
| 8 | `model` | 模型供应商、路由、定价、**额度**、LLM 审计 | [model.md](./model.md) |
| 9 | `channel` | 飞书 / 企微 / 钉钉 / Web 的入站归一化与出站投递 | [channel.md](./channel.md) |
| 10 | `orchestration` | 工作流定义与执行引擎（按图遍历） | [orchestration.md](./orchestration.md) |
| 11 | `governance` | 策略判定 / 审批 / 审计 / 数据主体请求 | [governance.md](./governance.md) |
| 12 | `evaluation` | 评测数据集 / 用例 / 运行 / 评分 | [evaluation.md](./evaluation.md) |
| 13 | `self_evolution` | 进化候选的登记与审批（默认只写草稿） | [self-evolution.md](./self-evolution.md) |
| 14 | `observability` | 运行记录 / 成本归集 / 质量评分 | [observability.md](./observability.md) |
| 15 | `platform` | 租户设置 / 套餐订阅 / 管理台通用存储 | [platform.md](./platform.md) |

## 相关文档

| 文档 | 内容 |
|---|---|
| [../architecture/copilot-chat.md](../architecture/copilot-chat.md) | 对话模块的**逐层链路梳理**（读代码的先后顺序） |
| [../architecture/session-lifecycle.md](../architecture/session-lifecycle.md) | 会话完整生命周期的泳道与时序基线 |
| [../architecture/data-separation.md](../architecture/data-separation.md) | 演示数据与 API 数据的分离现状 |
| [../architecture/cleanup-ledger.md](../architecture/cleanup-ledger.md) | 旧实现清理台账（**CI 扫描规则的来源**） |
| [../architecture/oncall-runbook.md](../architecture/oncall-runbook.md) | 值班手册：告警响了怎么办 |
| [../planned/](../planned/) | **方案已写好、代码未实现**的待实施项 |

## 读之前先知道

这些是跨域的共性，读任意一篇都适用：

- **多租户隔离有四道防线**：ContextVar 注入 → ORM 层 `with_loader_criteria` 强制过滤 → HTTP 中间件校验头 → 显式 `assert_tenant_scope`。漏写 `.where` 也越不了权。
- **错误码只有一个词汇表**：`qzdap_kernel.error_codes.ErrorCode`（160 个成员），生产代码里不允许出现错误码字面量——有架构测试守着。
- **「一个关注点只有一套实现」**：台账的 47 条扫描规则进了 CI，违反即红。
- **事件总线目前是断的**：model / skill / memory / knowledge / orchestration 五个模块**不发布领域事件**，导致 observability 订阅的 5 类记录恒为空、governance 审计对应条目恒为空。详见各篇的「已知边界」。

## 能力缺口的现状

| 能力 | 状态 |
|---|---|
| 成本闸门 | ✅ 已接（上限取 `profile.maxCostUsd` ✓） |
| 治理拒绝（策略引擎） | ✅ 已接（`GovernancePolicyGuard` ✓） |
| 专家指令 | ✅ 已进 system prompt ✓ |
| 上下文预算口径 | ✅ 统一为窗口 × 0.70 ✓ |
| 任务清单 / 规划 | ✅ `todo_write` 真进循环状态 ✓ |
| 并行工具调用 | ✅ 只读并行、有副作用串行 ✓ |
| 每步重选专家 | ✅ 专家跟着步骤走 ✓ |
| 反思 / 失败后换策略 | ❌ 没有——只有空转护栏 ✓ |
| 结构化输出约束 | ❌ LLM 层支持 `response_format` ✓ —— agent 链路未接 ✓ |
| 子 agent 并行 | ❌ 串行同步派发 ✓ |
| 多 agent 通信协议 / 共享状态 | ❌ 只有「父传子、子回传 final_response」✓ |
