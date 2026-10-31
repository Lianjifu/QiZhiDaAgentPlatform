# Context 层重构方案

> 版本：1.2（审查修正后 + 按审查结论重排骨架）
> 适用项目：`QiZhiDaAgentPlatform`
> 状态：**已定稿**（17 条审查问题已修正 + **本轮重排**，逐条见附录 C；附录 A 的 7 条决策于 2026-10-29 逐条确认）
> 方案集入口：[`README.md`](README.md)
> 上位基线：[`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) —— 本方案实现其中 **Context 泳道**
> 收敛机制：[`cleanup-ledger.md`](cleanup-ledger.md) —— 本方案对应条目 **X8、X9、X10**
> 硬约束：**最终态只有一个实现**；先上新、后清旧
> 方案集导航：落地路线与里程碑见 [`README.md`](README.md) §6 · 系统级验收见 §7 · 外部前置依赖见 §8 · 跨层不变量见 [`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) §6

---

## 0. 定位与范围

### 0.1 Context 在基线图上的位置

```
Session ──构建上下文──▶ Context ──检索相关记忆──▶ Memory
                          │                          │
                          │◀────返回记忆片段─────────┘
                          │
                          └──完整上下文──▶ Agent Loop
```

**注意基线图上的方向**：**Context 主动向 Memory 发起检索**（不是 Memory 推给 Context）。Context 是「召回的发起方与组装方」，Memory 是「记忆的存取方」。

### 0.2 本层的前提：三个子件不是流水线

**读这一节就够理解 Context 层了**：

| # | 前提 | 含义 |
|---|---|---|
| 1 | **三个子件不是流水线** | Builder → Compressor → Persistence 看着像串行，**其实不是** —— 压缩是装配的**条件分支**（装得下就不压），而**压缩的结果要回到装配里**。§2 的图必须按这个读 |
| 2 | **Context 是召回的发起方** | 记忆与知识**由 Context 主动发起检索**，Memory 只提供存取 —— **不是 Memory 推给 Context**（基线图方向）|
| 3 | **Context 只装配、不判权** | 可见范围、模型与工具的取值**都不归本层**（§0.3）—— 检索侧的可见范围归 Memory，模型与工具归 Agent 层 Execution |
| 4 | **本层的收敛形态与别层不同** | 旧实现**还在服役**（旧循环仍调 `runner._load_messages` 与 `adapter/graph/compact.py`）→ Stage 1–3 **只新建、不动调用点**，「旧代码减少」是 0；停用推迟到 Stage 4，删除归 Agent 层 |

### 0.2.1 三个子件

| 子件 | 职责 | 回答的问题 |
|---|---|---|
| **Builder** | 拼装 Prompt / 上下文（历史消息 + 检索内容 + 系统指令） | 这一轮**喂给模型什么** |
| **Compressor** | 上下文压缩（超长对话的摘要 / 裁剪，避免超出窗口） | 装不下时**丢掉什么、怎么丢** |
| **Persistence** | 上下文持久化存储 | 这次**实际喂了什么**，事后能查、能回放、能评测 |

### 0.3 Context 明确不做

| 不做 | 归属 |
|---|---|
| 协议、鉴权、幂等、渠道回包 | Gateway |
| 选 agent / 路由 / 消息排序 | Router |
| 会话生命周期、轮次状态、事件落库 | Session |
| **记忆与知识的存取**（Context 只发起召回、只消费结果） | Memory / Knowledge |
| 推理、**模型与工具的取值**、实际执行 | **Agent Loop**（循环）/ **Agent Router**（只选专家）/ **Execution**（取值与执行）|

### 0.4 实现收敛规则

**最终态只有一个实现**；**先上新、后清旧**。清理机制由 [`cleanup-ledger.md`](cleanup-ledger.md) 统一管理（弃用标记 → 调用打点 → 指标归零 → 删除 → CI 扫描脚本 → 阶段门禁）。

本方案涉及台账条目 **X8**（`_load_messages`）、**X9**（`compact.py`）、**X10**（四套 prompt 模板）。

**本层的收敛形态**：与其它层不同 —— Context 的旧实现**大部分还在服役**（旧循环仍调 `runner._load_messages` 与 `adapter/graph/compact.py`），所以本层的 Stage 1–3 **只新建、不动调用点**（这就是为什么那三个 Stage 的「旧代码减少」是 0）。


> **一句话**：Context 管的是「**这一轮给模型看什么、装不下时怎么裁、事后能查**」。

---

## 1. 现状盘点

### 1.1 🔴 两套上下文实现，都是半成品

| 实现 | 位置 | 状态 |
|---|---|---|
| ① 旧路径 | `adapter/graph/runner.py:495-566` `_load_messages` + `adapter/graph/compact.py` | **在跑**。组装正确但压缩是字符截断、无 manifest |
| ② 新 runtime | `runtimes/.../context/budget.py` | **未接线**（`assemble_context` 节点依赖默认 None，实际不跑）。有 manifest 与预算骨架，但**输出形状是错的** |

### 1.2 🔴 新 runtime 的 `ContextAssembler` 有四处硬伤

**① `assemble()` 返回的 `messages` 是字符串片段列表，不是 LLM 消息列表**

```python
# runtimes/.../context/budget.py:265, 271-317（return 在 :320）
parts: list[str] = []
parts.append(system_prompt)      # ← 纯字符串
parts.append(agent_text)
...
return AssembledContext(messages=parts, ...)
```

`AssembledContext.messages` 的注释写着「最终喂给 LLM 的消息列表」，但实际是 `["系统提示…", "agent_id=…", "租户…", "记忆…"]` 这样一串文本片段。**LLM 需要的是 `[{"role": "system", "content": …}]`** —— 这个输出**根本不能喂给模型**。

而旧路径的 `_load_messages` 是**正确**的：产出 `[{"role": "system", …}, {"role": "user", …}, …]`，并把 agent 的 prompts（soul / prompt / agents / tools / user）拼进 system。

**② `_downgrade()` 只打标记，不实际降级**

```python
# runtimes/.../context/budget.py:359-371
def _downgrade(self, manifest, parts, knowledge_hits) -> dict[str, bool]:
    """… 当前实现：标记 compaction_degraded；删 knowledge_hits 直到 budget 内 …
    简化：标记 degraded，不实际重算 parts（生产环境按精确优先级重排）"""
    return {"compaction_degraded": True}
```

超限时**上下文不会被裁剪**，照样整份喂给模型 → 直接撞模型的上下文窗口上限。这不是「降级」，是「标记完继续超限」。

**③ agent 的 prompts 完全没进上下文**

`_format_agent()` 只输出一行 `agent_id=… version=…`（`budget.py:328-329`）。旧路径的 agent 配置（soul / prompt / agents / tools / user 五段）**在这条路径上全部丢失** —— agent 会以「你是企业助手」这个通用身份回答。

**④ `assemble_context` 节点把组装结果丢掉了**

```python
# runtimes/.../graph/nodes.py:436-477
return {
    "context_manifest": ctx.manifest.to_dict(),
    "degraded": {**(state.get("degraded") or {}), **ctx.degraded_flags},
}
```

节点**只回传 manifest 与 degraded**，**`ctx.messages` 从未写回 graph state** —— 即使把 assembler 注进去，图里用的仍是 `state["messages"]` 原始列表。

> **修复**：Builder 的产物必须**整体**进 state（含 messages）—— 否则「接线」是假的。
>
> **附带两处硬编码占位**：`nodes.py:455` 的 `system_prompt="You are a helpful assistant."`（注释「实际从 agent catalog 注入 (Stage 4)」）与 `nodes.py:494` 的 `target_tokens = 4000` —— 连**安全系统提示词**与**预算**都是占位。

### 1.3 🔴 `Compactor` 的四个问题

| # | 问题 | 位置 |
|---|---|---|
| 1 | **同步实现，在 async 上下文里阻塞事件循环**。`Compactor.compact()` 是同步方法，摘要模型调用同步执行；代码用 `run_async_from_sync` 做绕行（`budget.py:191-197`） | `budget.py:191-197` |
| 2 | **压缩后不复验预算**。只检查了压缩前的 `before <= target_tokens`，压缩后的 `after` 没有再断言 → 仍可能超限 | `budget.py:210-226` |
| 3 | **`removed_ids` 计算逻辑错**：`if m not in new_messages` 是 O(n²) 且对内容相同的两条消息会同时判定为「已移除」 | `budget.py:214-218` |
| 4 | 摘要输入是 head 消息的**全文拼接**，不区分 role、不做结构化 → 摘要质量无法保证 | `budget.py:188` |

### 1.4 🔴 旧路径的压缩是纯字符截断

`adapter/graph/compact.py`（**53 行**）：

- 每条消息取**前 180 字**拼成 `｜` 分隔的「摘要」；
- 最多保留最近 **20** 条摘要片段，summary 截 **4000** 字；
- **没有任何摘要模型调用**；
- token 估算走 `state.py:24` 的 `estimate_tokens(messages)` —— 逐条 `len(content)//4` 并计入 `tool_calls`，**对中文严重低估**。

「滚动摘要」名不副实：它是**字符串切片**，不是摘要。

#### 1.4.1 迁移时**必须继承**的三项行为（方案初稿漏了）

| # | 行为 | 位置 | 为什么必须继承 |
|---|---|---|---|
| 1 | **工具结果清洗**：`role=="tool"` 且内容以 `ERROR` 开头 / 含 `SKILL_DENIED` / 超过 **4000** 字 → **截到 1500 字** | `compact.py:22-31` | **正确性相关** —— 错误原文与超长工具输出必须截断，否则会撑爆上下文 |
| 2 | **第一个 system 消息永远保留**；其余消息取最近 `KEEP_RECENT=6` 条 | `compact.py:10,37-39` | 保证安全提示与治理约束不被压缩掉（对应 §3.1 优先级 1「永不降级」） |
| 3 | **摘要是累加的**：`summary = (rolling_summary + "\n") + 新 digest`，再截 4000 字 | `compact.py:43-46` | **不是替换** —— 替换会丢掉此前所有轮次的结论 |

> **⚠️ 新 runtime 的确定性降级恰恰是「替换」**：`budget.py:205-208` 在摘要失败时把 `existing_summary` 覆盖成占位串 `"[deterministic compaction: N messages dropped]"` —— **历史摘要全部丢失**。
> 新的 Compressor **必须**改成「`existing_summary` + 新增要点」而不是覆盖（见 §4.3）。

### 1.4.2 🔴 旧路径**静默吞掉召回失败**

```python
# modules/agent_runtime/.../adapter/graph/runner.py:523, 549
except Exception:  # noqa: BLE001
    memories = []
```

记忆 / 知识召回失败时**只吞不报** —— 没有 `recall_degraded`，前端与审计都看不出「这次没用上记忆」。
**旧路径「组装正确」指的是消息形状正确**（`[{role, content}]`），不代表降级是可见的。

> **本层必须修**：Builder 召回失败时产出 `recall_degraded = True`（§5.3.1），并在 manifest 里记 `filtered_reason = "recall_failed"`。

### 1.5 无 manifest 落库

两套实现都不记录「这次实际喂了什么」。后果：

- **无法回答**「这条回答是基于哪些记忆、哪些知识、哪段历史得出的」；
- **无法做上下文消融评测**（去掉记忆片段，看回答质量变化）；
- **无法审计**「是否泄漏了不该给这个用户看的片段」。

### 1.6 ✅ 可直接复用的资产

| 资产 | 位置 | 状态 |
|---|---|---|
| `ContextManifest` / `ManifestEntry`（来源、token、版本） | `runtimes/.../context/budget.py:58-96` | ✅ 结构可用 —— **`filtered_reason` 字段已存在**（`budget.py:62`），本层要补的是 `ref_id` / `score` 两个命中标识 |
| `Compactor` 骨架（摘要优先、失败降级确定性窗口） | `runtimes/.../context/budget.py:152-227` | ✅ 骨架可用，**六处缺陷**需修（§1.3 的四处 + §4.3 的两处） |
| `SummaryModel` Protocol | `runtimes/.../context/budget.py:101` | ✅ 契约可用（注意：当前实现是**同步** `summarize`，需改异步端口 —— §1.3①） |
| `AssembledContext`（messages + manifest + degraded） | `budget.py:234-240` | ✅ 形状对，但 `messages` 填错 |
| 旧路径 `_load_messages`（正确的消息列表 + agent prompts + 多源拼接） | `adapter/graph/runner.py:495-566` | ✅ **可直接作为 Builder 的实现基础**（但它的 `top_k` / 400 字截断 / 召回失败静默吞 也要一并复刻，见 §3.2 与 §1.4.2） |
| 旧路径四套 prompt 模板 | `adapter/llm/prompts.py`（`build_system_prompt` / `_with_memory` / `_with_knowledge` / `_with_memory_and_knowledge`） | ⚠️ 四选一的模板分支，应合并为**一段式**（记忆/知识作为可选片段追加） |
| `context_compacted` chunk（已有前端契约） | `libs/schema/.../dtos/turn.py:96` | ✅ 压缩事件可复用 |
| `KnowledgePort.search` / `MemoryPort.recall` | `modules/agent_runtime/application/ports/__init__.py`（`MemoryPort:154` / `KnowledgePort:204`） | ✅ 召回端口已有 |

---

## 2. 目标架构

> ⚠️ **三个子件不是流水线**（§0.2 前提 1）：图上虽然画成 Builder → Compressor → Persistence，但**压缩是装配的条件分支**（装得下就不压），**且压缩的结果要回到装配里** —— Compressor 的输出是 Builder 的输入，不是它的下游。Persistence 则确实是旁路（只写不读回）。

```
                    ┌──────────────────────────────────────────┐
   Memory / Knowledge│  召回（Context 主动发起）                 │
        │           └──────────────┬───────────────────────────┘
        │                          │ RecallHit[]
        ▼                          ▼
  ┌────────────────────────────────────────────────┐
  │  ContextBuilder                                  │
  │  按固定优先级拼装 → [{role, content}]             │
  │  产出 AssembledContext{messages, manifest, flags}│
  └───────────────┬────────────────────────────────┘
                  │ 超预算？
                  ▼
  ┌────────────────────────────────────────────────┐
  │  ContextCompressor                               │
  │  摘要优先 → 失败降级确定性窗口 → 复验预算         │
  └───────────────┬────────────────────────────────┘
                  │
                  ▼
  ┌────────────────────────────────────────────────┐
  │  ContextPersistence                              │
  │  manifest 落库 · rolling_summary 落库 · 快照（暂不做，见决策 #3） │
  └───────────────┬────────────────────────────────┘
                  │
                  ▼
            Agent Loop（完整上下文）
```

**关键取舍**：三个子件**不是串行流水线，而是「装配 → 校验 → 必要时压缩 → 落库」**。压缩是装配的**条件分支**，不是独立阶段——因为压缩的结果要回到装配里（摘要是上下文的一段）。

---

## 3. Builder：拼装上下文

### 3.1 固定优先级（不可调换）

| 优先级 | 内容 | 不可降级？ |
|---|---|---|
| 1 | 安全系统提示词 + 治理约束 | ✅ 永不降级 |
| 2 | agent 版本、模型能力、工具白名单 | ✅ 永不降级 |
| 3 | 租户 / 工作区 / 用户 / 渠道 / 附件上下文 | ⚠️ 可精简附件内容 |
| 4 | 已确认的会话摘要 + 最近消息 | ⚠️ 可压缩 |
| 5 | L1/L2 记忆 + L3 知识召回结果 | ⚠️ 按分淘汰 |
| 6 | 当前 turn 的用户输入 + 工具结果 | ✅ 永不降级 |

> **优先级 6 永不降级**是硬规则：用户这句话和工具结果丢了，模型就是在答空气。压缩只能动 3/4/5。

### 3.2 输出形状（必须是 LLM 能吃的）

```python
@dataclass(frozen=True, slots=True)
class AssembledContext:
    messages: list[dict[str, Any]]     # [{"role": "system"|"user"|"assistant"|"tool", "content": str, ...}]
    manifest: ContextManifest
    degraded_flags: dict[str, bool]    # recall_degraded / compaction_degraded / ...
    tokens_estimated: int
```

**修掉 §1.2①**：不再是字符串片段列表。旧路径 `_load_messages` 的做法（构造 role/content 消息、agent prompts 拼进 system、记忆与知识作为额外 system 段追加）是正确范式，直接沿用。

> **⚠️ 迁移必须复刻的三个参数**（否则新旧行为漂移，线上表现不一致却查不出原因）：
> - **记忆 `top_k=8`**、**知识 `top_k=6`**（`runner.py:518,543`）；
> - 召回结果**按 `score` 降序**后再截断（`runner.py:551-556`）；
> - 每条命中内容**截 400 字**（`[:400]`，`runner.py:552,557`）。

### 3.3 agent prompts 的处理

旧路径把 agent 的五段配置拼成一个 system 段：

```python
# runner.py:505-513
system_parts = [prompts.get(k) for k in ("soul", "prompt", "agents", "tools", "user")]
system = "\n\n".join(p for p in system_parts if p) or "你是企业助手…"
```

新 runtime 的 `_format_agent` 只输出 `agent_id=… version=…` —— **agent 身份整个丢了**。修复：Builder 必须接收并使用 agent 的完整 prompts。

> **决策 #1（已定稿）**：agent prompts 的拼装**放在 Builder 内**（与旧路径一致、agent 的语言风格可控）—— 不下沉到 agent catalog 的「已渲染 system prompt」字段。

### 3.4 四套 prompt 模板合并

旧路径 `adapter/llm/prompts.py` 有四个函数（无记忆 / 有记忆 / 有知识 / 有记忆+知识），靠调用方二选一。**这是分支爆炸的源头**——新增一种来源（附件摘要？工具结果？）就要再加两个函数。

**目标**：单一模板 + 可选片段追加。

```python
def render_system_prompt(*, agent_prompts: dict, tenant_context: dict,
                         summary: str, memory_hits: list, knowledge_hits: list) -> str
```

记忆 / 知识是**可选段落**，不是模板变体。

### 3.5 manifest 的内容

每次模型调用记录一条：

| 字段 | 含义 |
|---|---|
| `source` | `system` / `agent` / `tenant` / `summary` / `memory` / `knowledge` / `recent` / `tool_result` / `attachment` |
| `tokens` | 该片段的 token 估算 |
| `version` | agent 版本 / 记忆批次版本 / 知识包版本 |
| `ref_id` | 命中项 ID（记忆 id / 知识 chunk id / 消息 id） |
| `score` | 召回得分（记忆 / 知识） |
| `filtered_reason` | **被淘汰的原因**（超预算被裁 / 低分淘汰 / 附件超长截断 / 召回失败）—— ✅ **该字段已存在**（`budget.py:62`），本层只需补齐取值 |
| `degraded` | 该来源是否降级（召回失败 / 摘要失败） |

> `filtered_reason` 是新增的关键字段——**没有它就不知道「什么没进去」**，消融评测与排障都依赖它。

### 3.6 token 估算

**现状是两个不同的函数**（初稿误以为是同一个）：

| 位置 | 签名 | 口径 |
|---|---|---|
| `budget.py:42` | `estimate_tokens(text: str) -> int` | **已经按语种估算**：CJK 每字 1 token，ASCII 每 4 字符 1 token |
| `state.py:24` | `estimate_tokens(messages: list[dict]) -> int` | 逐条 `len(content)//4` + 计入 `tool_calls`，**对中文严重低估** |

**所以真正的问题不是「选哪个算法」**，而是：**两条路径的预算口径不一致** —— 同一个会话，走新路径不超预算、走旧路径可能超，反之亦然；压缩的触发点也会漂移。

> **决策 #2（已定稿）**：token 估算口径 → **统一用 `budget.py:42` 的按语种估算**，并让旧路径也用它。
> - **(a) 统一用 `budget.py` 的按语种估算**（推荐）—— 新旧两条路径共用一个函数，中文按 1 字 1 token 估，**宁可高估**（预算控制的意义就是「不撞窗口」）
> - **(b) 统一用 `len//4`** —— 零改动，但中文继续低估
> - **(c) 引入 `tiktoken`** —— 最准，但要加依赖并接受「不同供应商口径不同」
>
> **建议 (a)**：初稿建议的 (c)「按语种估算」**已经是 `budget.py` 的现状**（无需开发）；本层要做的是把它**抽成 `tokens.py` 并让旧路径也用它**，而不是重新发明。

---

## 4. Compressor：上下文压缩

### 4.1 触发条件

```
tokens_estimated > budget(= context_window × 0.70)
```

沿用旧路径 `compact.py` 的 `WINDOW_RATIO = 0.70`（留 30% 给模型输出与工具结果）。

> **决策 #4（已定稿）**：阈值固定为 `context_window × 0.70`（沿用旧路径 `WINDOW_RATIO`）。**不引入模型窗口表** —— 窗口表本身是易过期的配置源，而压缩的目标是「留足输出与工具结果余量」，比例法足够。

### 4.2 压缩策略（两级）

| 级别 | 动作 | 失败降级 |
|---|---|---|
| **一级** | 摘要模型对「可折叠区」生成结构化摘要 | 摘要失败 → 二级 |
| **二级** | 确定性窗口：保留最近 N 条 + 最早的消息要点截断 | — |

**结构化摘要**要保留的东西（不能只写「聊过什么」）：

- 决策与结论（含数字、承诺、期限）
- 未完成事项
- 关键实体（人名、单号、参数）
- 来源消息 ID（可回溯）

> 这条来自 v3.1 §17 验收标准：「上下文压缩保留决策、数字、承诺、未完成事项和来源 ID」。

### 4.3 必须修掉的六个缺陷（§1.3 四处 + §1.4.1 两处）

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | 同步实现阻塞事件循环 | `Compressor.compact()` 改 **async**；摘要模型走异步端口；`run_async_from_sync` 这条绕行路径删除 |
| 2 | 压缩后不复验预算 | 压缩后 `tokens_after > target` → 进入二级确定性窗口；仍超限 → **抛 `CONTEXT_TOO_LARGE`**（`ErrorCode` 已有）而不是继续喂（**决策 #5**：明确错误，不静默截断） |
| 3 | `removed_ids` 计算错 | 按**索引**判定，不按值包含；或用 Session 已提供的稳定序号 **`session_messages.session_seq`**（会话内单调，迁移 0046 新增）做集合差。**注意：`session_messages` 没有 `message_id` 列**，不要引用不存在的列 |
| 4 | 摘要输入是全文拼接 | 按 role 分组构造摘要输入（user / assistant / tool 分开），并只折叠「可折叠区」 |
| 5 | **确定性降级会覆盖 `existing_summary`**（`budget.py:205-208` 用占位串替换）→ 丢历史摘要 | 降级时**追加**而不是替换：`new_summary = existing_summary + 新要点`（§1.4.1 行为 3） |
| 6 | **工具结果清洗缺失** | 复刻旧路径：工具错误 / 超长结果截 1500 字（§1.4.1 行为 1） |

### 4.4 降级序（固定）

超预算时的淘汰顺序（v3.1 §5.3）：

```
旧消息摘要  →  低分召回淘汰  →  附件摘要  →  明确错误（CONTEXT_TOO_LARGE）
```

**注意**：现实现的 `_downgrade` 只做了第二步的**声明**，没有实现（§1.2②）。本层必须真正实现它，并把每一步淘汰记进 manifest 的 `filtered_reason`。

> **降级时必须保留 `existing_summary`**（§4.3 缺陷 5）—— 旧路径的摘要是**累加**的，覆盖等于丢掉此前所有轮次的结论。

### 4.5 压缩事件

压缩发生时发 `context_compacted` chunk（`dtos/turn.py:96`）。

| 字段 | 现状 | 本层 |
|---|---|---|
| `tokens_before` | **恒为 0**（`runner.py:215` 写死） | 修：真实压缩前 token 数 |
| `tokens_after` | ✅ 正确（`estimate_tokens(messages)`） | 保持 |
| `degraded` | ❌ **字段不存在** —— `ContextCompactedChunk` 只有 `tokens_before` / `tokens_after`（带 `degraded` 的是 `KnowledgeSearchChunk`，`turn.py:203`） | **本层在 `libs/schema` 补一个可选字段** `degraded: bool = False`（**决策 #7**） |

> **契约变更影响**：前端目前只按 `kind` 提示「上下文已压缩」（`CopilotPage.tsx:489`），**不读任何字段** → 新增可选字段**向后兼容**。
> 若前端将来要展示「压缩降级」，读这个字段即可，不必去翻 `flags`。

---

## 5. Persistence：上下文持久化

### 5.1 存什么

| 对象 | 落点 | 用途 |
|---|---|---|
| **manifest** | 新表 `session_context_manifests`（`turn_id`, `step`, `manifest` JSONB, `tokens_total`, `degraded` JSONB） | 审计「这次喂了什么」、消融评测、排障 |
| **rolling summary** | `agent_sessions.rolling_summary`（**新增列**） | 下一轮组装的输入；历史版本由 manifest 留痕 |
| **完整快照** | `session_messages` 已有（消息本身） | 规范真相在 Session 层，Context 不重复存 |

> **为什么 manifest 要按 `step` 存**：ReAct 循环里**一轮可能有 N 次模型调用**（每次工具调用后重新组装）。manifest 是**每次模型调用**一条，不是一轮一条（**决策 #6**）。

### 5.1.1 `step` 的分配规则

`step` 是轮次内的**模型调用序号**，从 0 开始，由 **Session 层**的轮次执行上下文分配（不是 Context 自己维护计数器）：

| 规则 | 内容 |
|---|---|
| 分配主体 | Session 层的 turn 执行上下文持有 `step` 计数器，随轮次推进单调递增 |
| 单调性 | 同一 `turn_id` 内 `step` 严格递增，不复用、不回退 |
| 并发 | 同一轮次内模型调用**串行**（ReAct 本身串行），因此 `step` 无并发争用 |
| 并行分支 | 若未来引入并行工具调用，`step` 由**发起方**在投递前预占（`nextval` 语义），不允许两处拿到同一个 `step` |
| 唯一性保障 | `UNIQUE (turn_id, step)` 兜底；冲突即视为 bug（抛错，不静默覆盖） |
| **重试** | 同一轮次内模型调用失败重试 → `step` **继续递增**，不冲突 |
| **重放** | 「按 manifest 重放上下文」**不重新调模型** → **不写新 manifest 行**，无冲突 |
| **整轮重跑** | **不复用 `turn_id`** —— 走 `session_turns.idempotency_key` 的既有轮次（Session 层的幂等语义），或另起一轮；**不得用同一个 `turn_id` 重跑并期望 step 从 0 开始** |

> 之所以把 `step` 放在 Session 侧分配：Context 是**无状态函数**（同样的输入产出同样的输出），计数器若放在 Context 内部，会在重试/回放时错位。


### 5.2 manifest 的写入时机

```
组装 → 压缩（若超预算）→ 落 manifest → 交付 Agent Loop
```

**必须在交付模型之前落库**：否则模型已经基于某个上下文回答了，事后却查不到那次的组成，审计与评测就失去依据。

### 5.3 与 Session 层事件的关系

| | Session 的 `session_events` | Context 的 `session_context_manifests` |
|---|---|---|
| 内容 | 面向客户端的结果事件（message / tool_call / done…） | 面向内部的上下文组成记录 |
| 消费方 | SSE / 渠道 / 重放 | 审计 / 评测 / 排障 |
| 是否投递 | 是（有 `delivery_status`） | 否 |

**不要混用**：manifest 不是事件，不该走 outbox 投递。

### 5.3.1 降级标记到前端的通道

`degraded_flags`（`recall_degraded` / `compaction_degraded`）必须**走一条已存在的前端契约**，不能新造通道：

| 标记 | 承载 | 前端行为 |
|---|---|---|
| `compaction_degraded` | `context_compacted` chunk 的 `degraded` 字段（**本层新增**，§4.5） | 折叠为「已压缩」提示，不展示细节 |
| `recall_degraded` | `ResultEvent.flags`（Gateway §9.0 已定义 `recall_degraded` / `compaction_degraded` / `interactive_degraded` 三键） | 提示「未使用历史记忆」，**不暴露内部原因** |

> **约束**：`ResultEvent.flags` 的键集合由 **Gateway 层定义**（见 `gateway-refactor-plan.md` §9.0），Context 只允许使用已定义的键，**不得新增未登记的 flag**。新增 flag 必须先改 Gateway 的契约表，否则前端会收到未知键而静默忽略。

> **⚠️ 前端目前根本不消费 `flags`**：全前端源码对 `flags` / `recall_degraded` / `compaction_degraded` **零命中**（`CopilotPage.tsx:489` 只按 `kind` 提示「上下文已压缩」）。
> 所以「字段落地」与「用户看得见」是**两件事** —— 后端把 flag 放进 SSE 只是第一步；**前端消费是独立工作项**（§9 Stage 4）。

### 5.4 快照（可选，采样存）

> **本节当前不落地**：决策 #3 已定「先不做快照」。将来若开启，按**比例采样**（如 1%）存 `session_context_snapshots`，用于人工复核与回归夹具，**不做全量**。

> **决策 #3（已定稿）**：上下文快照**先不做** —— manifest 已能回答「喂了什么」；快照只在需要回归夹具时再开。

---

## 6. 与相邻层的边界

| 方向 | 契约 |
|---|---|
| **Gateway → Context** | `AttachmentRef.text_preview`（附件的文本预览）+ `actor`（租户 / 工作区 / 用户上下文）—— Gateway 方案 §7 的边界表已列 |
| **Session → Context** | **消息序列**：`session_messages` 按 `(session_id, session_seq)` 排序（`session_seq` 是 Session 迁移 0046 新增的会话内单调序号）；轮次上下文（**审批状态**）。⚠️ **不含工具白名单** —— 工具集来自 **agent 配置的绑定集**（Agent 方案 §5.3.1），不来自 Session |
| Context → Memory | **主动发起** `recall_memory(...)` → `list[RecallHit]`（基线图方向）。**Memory 不管知识** |
| Context → Knowledge | **主动发起** `KnowledgePort.search(...)` → 知识片段。**知识召回不经过 Memory**（Memory 决策 #1：L3 退役，知识统一归 `modules/knowledge`） |
| Context → Agent Loop | `AssembledContext.messages`（`[{role, content}]`，**可直接喂 LLM**） |
| Context → Session | manifest 落库（经 Session 的写端口，保证与轮次同事务） |

**三个容易混的边界**：

1. **Context 发起召回，Memory 负责存取** —— Context 不直接访问记忆表。
2. **Context 消费召回结果，Memory 负责写入** —— 写入由 **Agent Loop** 在 Observe/Evaluate 后触发（基线图方向），Context 不管写。
3. **Context 管「给模型看什么」，Agent Loop 管「模型怎么看」** —— 工具结果拼进上下文是 Context 的事；模型如何决定下一步是 Agent Loop 的事。

---

## 7. 数据与表

### 7.1 表终态

| 表 / 列 | 处置 | 说明 |
|---|---|---|
| `agent_sessions.rolling_summary` | **新增列** | 当前散在 `metadata` JSONB 里 |
| `session_context_manifests` | **新增表** | manifest 持久化 |
| `agent_sessions.metadata["rolling_summary"]` | **移除** | 迁到新列 |
| `session_messages` | 不动 | Context 只读 |
| `session_events` | 不动 | Context 不写 |

### 7.2 迁移草案（0047）

```sql
-- migrations/versions/0047_context_runtime.py
--
-- ⚠️ 依赖：Session 的迁移 0046 必须已执行 —— **物理顺序**（0047 在 0046 之后跑），
--    且本层要读 `session_messages.session_seq`（0046 新增的会话内单调序号）。
--    ⚠️ 与 `graph_state` 无关：graph_state 的迁出在 **Session Stage 6**，不在 0046。

-- 1) rolling_summary 独立成列
ALTER TABLE agent_sessions
    ADD COLUMN rolling_summary TEXT NOT NULL DEFAULT '';

-- 2) manifest 表
CREATE TABLE session_context_manifests (
    id             UUID NOT NULL,
    tenant_id      UUID NOT NULL,
    workspace_id   UUID NOT NULL,
    session_id     UUID NOT NULL,
    turn_id        UUID NOT NULL,
    step           INTEGER NOT NULL,
    manifest       JSONB NOT NULL,
    tokens_total   INTEGER NOT NULL DEFAULT 0,
    degraded       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_session_context_manifests PRIMARY KEY (id),
    CONSTRAINT uq_session_context_manifests_turn_step
        UNIQUE (turn_id, step)
);

CREATE INDEX ix_session_context_manifests_session
    ON session_context_manifests (tenant_id, session_id, created_at);
```

### 7.2.1 0047 的回滚

0047 是**纯新增**（1 列 + 1 表），回滚代价低但需显式：

```sql
-- 回滚
DROP TABLE IF EXISTS session_context_manifests;
ALTER TABLE agent_sessions DROP COLUMN IF EXISTS rolling_summary;
```

> 注意：`rolling_summary` 回滚会**丢失**从 `metadata` 迁出的摘要文本（迁出时已从 `metadata` 移除）。因此回滚脚本必须先执行 `metadata['rolling_summary'] = rolling_summary` 的回填，或接受摘要重建（下一轮重新生成）。**推荐前者**。

### 7.3 `rolling_summary` 的迁移

**权威值在 `graph_state`，`metadata` 只是持久化副本** —— 旧路径的写入顺序是（`copilot.py:379-380`）：

```python
summary = str((self._graph.last_loop_state or {}).get("rolling_summary") or meta.get("rolling_summary") or "")
meta["rolling_summary"] = summary
```

即 **`graph_state` 优先、`metadata` 兜底**（与 Session 方案 §7.3 的约定一致）。迁移脚本必须按同样的优先级回填：

```sql
-- 3a) graph_state 优先
UPDATE agent_sessions s
   SET rolling_summary = s.graph_state->>'rolling_summary'
 WHERE s.graph_state ? 'rolling_summary'
   AND COALESCE(s.graph_state->>'rolling_summary', '') <> '';

-- 3b) 再用 metadata 兜底（graph_state 为空的行）
UPDATE agent_sessions s
   SET rolling_summary = COALESCE(s.metadata->>'rolling_summary', '')
 WHERE COALESCE(s.graph_state->>'rolling_summary', '') = ''
   AND s.metadata ? 'rolling_summary';

-- 3c) 清空 metadata 里的旧副本（§7.1 声明要移除它）
-- ⚠️ **本迁移不执行**（2026-10-29 实施核对修正）：旧路径
--    （copilot.py:379-380 / runner.py）**仍是 rolling_summary 的唯一写者**，
--    直到 Context Stage 3 迁移写入点、Stage 4 停用旧循环。提前清空会把旧路径
--    正在写的副本删掉 —— 摘要丢失且无法重建。清理动作在 **Stage 4 之后**执行。
-- UPDATE agent_sessions
--    SET metadata = metadata - 'rolling_summary'
--  WHERE metadata ? 'rolling_summary';
```

> **⚠️ 只读 `metadata` 会丢摘要**：`graph_state` 里的值才是权威的（可能是更新的），`metadata` 是上一次持久化的副本。初稿只写了 `metadata` 回填 —— 与 Session 方案 §7.3 矛盾，已修正。
> **回滚**：必须先 `metadata['rolling_summary'] = rolling_summary` 回填（§7.2.1）。
>
> **⚠️ 清空 `metadata` 的时机（本轮实施核对修正）**：清理**不在 0047 里做** —— 旧路径还在写 `metadata['rolling_summary']`，提前清空会丢摘要且旧路径会立刻写回来。清理落在 **Stage 4（旧循环停用）之后**。迁移 0047 已按此实现（回填做、清空不做）。

---

## 8. 逐文件改造与删除清单

### 8.1 新增（`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/context/`）

| 文件 | 内容 |
|---|---|
| `builder.py` | `ContextBuilder`：固定优先级拼装 → `[{role, content}]` |
| `compressor.py` | `ContextCompressor`：**async** 摘要 + 确定性窗口 + 复验预算 |
| `persistence.py` | `ContextManifestStore` 端口与 SQL 实现 |
| `prompts.py` | **单一** system prompt 渲染（替代四套模板） |
| `tokens.py` | token 估算（按语种） |
| `types.py` | `AssembledContext` / `ContextManifest` / `ManifestEntry`（补 `filtered_reason`） |

### 8.2 迁移

| 旧位置 | 迁到 | 动作 |
|---|---|---|
| `adapter/graph/runner.py:495-566` `_load_messages` | `context/builder.py` | **作为实现基础迁入**（它是正确的） |
| `adapter/llm/prompts.py` 四套模板 | `context/prompts.py` 单段式 | 合并（§3.4） |
| 旧路径 `compact.py`（**53 行**） | `context/compressor.py` | **删除**（纯字符截断）—— ⚠️ 它的**工具结果清洗 / 首个 system 保留 / 摘要累加**三项行为要复刻（§1.4.1） |
| `runtimes/.../context/budget.py` `ContextAssembler` | `context/builder.py` | 重写（修 §1.2 的 **①–③** 三处硬伤；第 ④ 处是**新 runtime 的 `nodes.py` 节点**，见下一行）|
| `runtimes/.../graph/nodes.py` 的 `assemble_context` 节点 | `context/builder.py` | **改写**（新 runtime 侧的第 ④ 处硬伤：`ctx.messages` 整体写回 state，未接 Builder）。⚠️ 该文件在 Agent Stage 7 整体删除 —— **本层只改接线，不删文件** |
| `runtimes/.../context/budget.py` `Compactor` | `context/compressor.py` | 重写（修 §1.3 四处缺陷） |
| `runtimes/.../context/budget.py` `estimate_tokens` | `context/tokens.py` | 替换为按语种估算 |
| `runner.py:214-218` `ContextCompactedChunk(tokens_before=0)` | `context/compressor.py` | 修复 token 计数 |

### 8.3 保留但改造

| 文件 | 改造点 |
|---|---|
| `adapter/memory/memory_service_adapter.py` | `recall` → 供 Builder 调用；补 `ref_id` / `score` 到 hit 结构 |
| `adapter/knowledge/knowledge_service_adapter.py` | 同上 |
| `application/ports.py` `MemoryPort` / `KnowledgePort` | 契约不变（`recall` / `search` 已有） |

### 8.4 删除清单（Stage 5 执行）

| 类别 | 具体 |
|---|---|
| 旧压缩实现 | `adapter/graph/compact.py` |
| 旧四套模板 | `adapter/llm/prompts.py` 的 `build_system_prompt*` 四函数 |
| 旧组装逻辑 | `runner.py` 的 `_load_messages`（迁入后删除） |
| 旧 runtime 骨架 | `runtimes/.../context/budget.py`（拆入新文件后删除）—— ⚠️ 连带删掉里面的 `InMemorySummaryModel`：实施方案 §1.5 的 `InMemory*` 基线白名单**在 Context Stage 5 移除该类名**（不是 Agent Stage 7） |
| 散落的 summary 字段 | `agent_sessions.metadata['rolling_summary']` 的读写点 |

---

## 9. 实施阶段

> 每阶段验收都含「**旧代码减少了什么**」。

### Stage 0：契约与迁移

| 动作 | 细节 |
|---|---|
| 建 `context/` 骨架 + `types.py` | `AssembledContext` / `ContextManifest`（含 `filtered_reason`） |
| 迁移 0047 | `rolling_summary` 列 + `session_context_manifests` 表 + 数据回填 |
| `tokens.py` | 抽出 `budget.py:42` 的按语种估算（新 runtime **已经是这个口径**，本层是抽成共享函数让旧路径也用它）+ 单元测试（中文/英文/混合） |
| **收敛基础设施** | 建 `qzdap_legacy_calls_total` 指标（若尚未建立），并给本层台账条目的旧入口打点（`record_legacy_call("<编号>")`）。**没有打点就没有清理判据** —— 见 `cleanup-ledger.md` §3.2 |

**旧代码减少**：无（纯新增 + 迁移）。
**验收**：**新旧两条路径的 token 估算口径一致** —— 同一批中文 / 英文 / 混合语料上，`tokens.py`（按语种）与旧路径 `state.py:24` 的估算差异 **< 10%**；且中文语料上与 `tiktoken` 的偏差 < 15%（**tiktoken 仅作测试期对照，不进生产依赖**）。
**验收补充**：本层每个台账条目的旧入口都有打点；`/metrics` 能查到 `qzdap_legacy_calls_total`。

#### 实施记录（2026-10-30 · Stage 0：契约与迁移）

| 项 | 结果 |
|---|---|
| `context/tokens.py` | **按语种估算的唯一实现** ✓（CJK 1 字 1 token ✓ + 其余 4 字符 1 token ✓）；另带 `estimate_message_tokens` ✓（把**工具调用**也算进去 ✓ —— 它同样进上下文 ✓） |
| `context/types.py` | `AssembledContext` / `ContextManifest` / `ManifestEntry` ✓ —— 补齐 **``ref_id`` / ``score`` / ``degraded``** 三个字段 ✓（`filtered_reason` 早就存在 ✓）；来源枚举固化为 `CONTEXT_SOURCES` ✓ |
| `budget.py` | **不再自己定义**估算与契约类型 ✓ —— 改为从 `tokens.py` / `types.py` **导入** ✓（两份算法 = 口径又分叉 ✗✗）；文件本身**待拆**（Stage 1 → `builder.py` ✓、Stage 2 → `compressor.py` ✓、**Stage 5 整个删掉** ✓） |
| **旧路径改用共享函数** | `adapter/graph/state.py` 的 `estimate_tokens` **不再按 `len // 4` 一刀切** ✗✗ —— 改调契约层的按语种估算 ✓（决策 #2 ✓）。⚠️ **中文不再被低估约 4 倍** ✓ —— 这会**改变压缩触发点** ✓（中文会话更早触发压缩 ✓，方向是对的 ✓：预算控制的意义是「不撞窗口」✓） |
| 空内容 | 旧实现记 1 token ✗（白占预算 ✗）→ 现在记 **0** ✓ |
| 迁移 0047 | ✅ **已落地并 apply** ✓（`session_context_manifests` 表 + `agent_sessions.rolling_summary` 列 ✓ —— dev 库已确认存在 ✓） |
| 打点 | X8 / X9 已有 ✓（`runner.py:569` / `runner.py:212` ✓）；X10 的旧入口（`prompts.py`）**已随 Stage 5b 删除** ✓ → 打点自然归零 ✓（台账已记「已清理」✓） |
| 测试 | 契约层 10 条 ✓（中/英/混合语料 + 空串 + 工具调用 + **对 `tiktoken` 的偏差 < 15%** ✓ —— 中文实测 3.6% ✓）；模块侧 5 条 ✓（**新旧两条路径差异 < 10%** ✓ —— 实测 **0%** ✓，因为它们调的是同一个函数 ✓） |
| 依赖 | `tiktoken` 只进 **dev extras** ✓（仅测试期对照 ✓ —— 不进生产依赖 ✓） |

⚠️ **契约层的 `context/` 子包现在**被生产代码引用**了** ✓（`adapter/graph/state.py` ✓）—— 台账 **X1**（整包未接线）就这一块而言**不再是「整包未接线」** ✓。

### Stage 1：Builder 落地（以旧路径为基准）

| 动作 | 细节 |
|---|---|
| `ContextBuilder` | 固定优先级拼装 → `[{role, content}]` |
| agent prompts 完整接入 | 修 §1.2③ |
| 单段式 prompt 渲染 | 合并四套模板 |
| 召回发起 | Builder 主动调 `recall_memory` / `recall_knowledge`；**复刻旧路径参数**：`top_k=8`（记忆）/ `top_k=6`（知识）、按 `score` 降序、每条截 400 字 |
| **召回失败必须可见** | 修 §1.4.2：失败时置 `recall_degraded = True`（旧路径是静默吞掉的） |
| manifest 生成 | 含来源、token、版本、ref_id、score |

**旧代码减少**：无删除。⚠️ **本 Stage 不停用 `_load_messages`，也不停用四套模板** —— 它们**仍被 `runner._run_turn_inner` 调用**（`runner.py:179`），此刻停用会把还在服役的旧循环打断。**停用推迟到 Stage 4**（前置 = Agent Stage 5 的 A-26 接线完成）。
**验收**：产出可直接喂 LLM；agent 身份正确（不再是「企业助手」通用语）；manifest 完整；**四套模板调用点数归零**。

#### 实施记录（2026-10-30 · Stage 1：Builder 落地）

| 项 | 结果 |
|---|---|
| `context/builder.py` | `ContextBuilder` ✓ —— 按**固定优先级**拼成 `[{role, content}]` ✓（§3.1 ✓：系统提示 → agent → 租户 → 摘要 → 召回 → 最近消息 → 当前输入 ✓）。⚠️ **消息与清单条目成对** ✓ —— 降级时成对丢 ✓（对不上就说明「它喂了什么」不可信 ✗✗） |
| `context/prompts.py` | **单段式渲染** ✓ —— 一个模板 + 可选片段 ✓（四套模板已随 Stage 5b 删除 ✓，这里不再有「变体」✓）。agent 的五段配置（soul / prompt / agents / tools / user）**按原顺序**拼 ✓（旧路径同 ✓ —— 换顺序会改变模型行为 ✗✗） |
| agent 身份 | **不丢** ✓ —— 五段配置进 system ✓（新 runtime 原来只输出 `agent_id=… version=…` ✗✗ —— agent 身份整个丢了 ✗）。⚠️ agent 没配 prompt 时**不追加这一段** ✓（否则兜底句重复两遍 ✗✗） |
| **复刻旧路径的三个参数** | 记忆 `top_k=8` ✓、知识 `top_k=6` ✓、每条命中**截 400 字** ✓ —— 少一个，新旧行为就会漂移 ✗✗。召回命中**按 `score` 降序** ✓（顺序决定截断谁 ✓） |
| 记忆的用户过滤 | `user_id` 照旧传 ✓ —— 缺了会**跨用户泄漏** ✗✗（X14 ✓） |
| **召回失败可见** | 置 `degraded_flags["recall_degraded"] = True` ✓ —— 旧路径是**静默吞掉**的 ✗✗（模型以为没有记忆 ✗） |
| manifest | 每段一条 ✓ —— 来源 / token / 版本 / **`ref_id`** / **`score`** / **`filtered_reason`** ✓ / `degraded` ✓；总 token 与 `tokens_estimated` 一致 ✓ |
| 降级 | 超预算时按 **5 → 4 → 3** 丢片段 ✓（优先级 1 / 2 / 6 **永不降级** ✓ —— 用户这句话和工具结果丢了，模型就是在答空气 ✗✗）；被丢的片段**留一条记录** ✓（`filtered_reason='over_budget'` ✓） |
| 召回端口 | 契约层定义 `MemoryRecallPort` / `KnowledgeSearchPort` 协议 ✓（不引框架 ✓）；模块侧的 `MemoryServiceAdapter` / `KnowledgeServiceAdapter` **结构上满足** ✓（测试断言 ✓） |
| **只新建，不动调用点** | ✅ 旧路径 `_load_messages` **仍在服役** ✓（C-10 ✓）—— 本 Stage **没有**接线 ✓（Stage 4 才接 ✓，前置 = Agent Stage 5 的 A-26 ✗）—— ⚠️ **该前置已于 2026-10-30 满足** ✓（A-26 把旧循环改接 `ContextBuilder` ✓ → **Builder 现在有生产调用方** ✓） |
| 测试 | 19 条 ✓（优先级顺序 ✓ / agent 身份 ✓ / 三个复刻参数 ✓ / 降级可见 ✓ / manifest 字段 ✓ / 成对覆盖 ✓ / 端口结构 ✓ / 不引框架 ✓） |

⚠️ **本 Stage 是「建」不是「切」** ✓ —— Builder **暂时没有生产调用方** ✓；
接线的 Stage 4 的前置（**Agent Stage 5 的 A-26**）还没落地 ✗ → 归入
「未接管」表 ✓。

### Stage 2：Compressor 落地

| 动作 | 细节 |
|---|---|
| async 压缩器 | 修 §1.3① |
| 结构化摘要 | 保留决策 / 数字 / 承诺 / 未完成事项 / 来源 ID |
| 压缩后复验预算 | 修 §1.3②；仍超限 → `CONTEXT_TOO_LARGE` |
| `removed_ids` 按 id 差集 | 修 §1.3③ |
| 真正的降级序 | 修 §1.2②：摘要 → 低分淘汰 → 附件摘要 → 明确错误 |
| `context_compacted` 事件 | 修 `tokens_before=0`；**在 `libs/schema` 补 `degraded: bool = False`**（决策 #7） |
| 降级不丢历史摘要 | 确定性降级改为**追加**而非覆盖 `existing_summary`（§1.4.1 行为 3） |
| 工具结果清洗 | 复刻旧路径：工具错误 / 超长结果截 1500 字（§1.4.1 行为 1） |

**旧代码减少**：无删除。⚠️ **本 Stage 不停用 `compact.py`**（仍被旧循环调用）—— 停用推迟到 Stage 4。
**验收**：构造超长会话 → 压缩后 token 在预算内；摘要保留决策与数字；摘要模型故障 → 确定性降级不崩。

#### 实施记录（2026-10-30 · Stage 2：Compressor 落地）

| 项 | 结果 |
|---|---|
| `context/compressor.py` | `ContextCompressor` —— **async** ✓（缺陷 1 ✓：同步实现会**阻塞事件循环** ✗✗；摘要模型走**异步端口** ✓）。旧 runtime 那条 `run_async_from_sync` 绕行路径**不再需要** ✓ |
| 触发条件 | `tokens_estimated > 窗口 × 0.70` ✓（决策 #4 ✓ —— 不引入窗口表 ✓）；不超预算**不压** ✓ |
| **复验预算** | 压缩后**复验** ✓ → 仍超限 → 二级确定性窗口 ✓ → 仍超限 → **抛 `CONTEXT_TOO_LARGE`** ✓（决策 #5 ✓ —— **明确错误，不静默截断** ✗✗） |
| 结构化摘要 | 提示词**点名要保留**决策 / 数字 / 承诺 / 未完成事项 / 来源消息 ID ✓（§4.2 ✓）；摘要输入**按 role 分组** ✓（user / assistant / tool 分开 ✓ —— 缺陷 4 ✓）；**系统提示不进摘要** ✓（它是永不降级的那部分 ✓） |
| `removed_ids` | 按**稳定序号**报 ✓（`session_seq` ✓ —— 缺陷 3 ✓）；⚠️ **不引用 `message_id`** ✓（`session_messages` **没有**这一列 ✗✗） |
| **降级不覆盖旧摘要** | 降级时**追加**而不是替换 ✓（缺陷 5 ✓ —— 覆盖等于丢掉此前所有轮次的结论 ✗✗）；摘要模型的输出**同样追加** ✓ |
| 工具结果清洗 | 复刻旧路径 ✓：工具错误 / 超长结果**截 1500 字** ✓（缺陷 6 ✓） |
| 保留最近 | `KEEP_RECENT = 6` ✓（同旧路径 ✓） |
| 结果类型命名 | 新的是 **`CompactionOutcome`** ✓ —— 旧 runtime 里还有一个语义不同的 `CompactionResult` ✓（待 Stage 5 删 ✓）→ **同名会让人以为是一套** ✗✗ |
| `ContextCompactedChunk` | **补 `degraded: bool = False`** ✓（决策 #7 ✓ —— 可选字段 ✓ 向后兼容 ✓）；旧路径的 **`tokens_before=0` 修掉** ✓（改成压缩前的真实 token 数 ✓ —— 之前事件里「压缩了多少」永远是 0 ✓） |
| **只新建，不动调用点** | ✅ 旧路径 `compact.py` **仍在服役** ✓（C-17 ✓）—— 本 Stage **没有**接线 ✓（Stage 4 才接 ✓） |
| 测试 | 14 条 ✓（async ✓ / 结构化摘要四件事 ✓ / 按 role 分组 ✓ / 系统提示不入摘要 ✓ / 两级降级 ✓ / 明确错误 ✓ / 追加不覆盖 ✓ / `removed_ids` 稳定序号 ✓ / 工具结果清洗 ✓ / 预算比例 ✓）+ DTO 1 条 ✓ |

⚠️ **本 Stage 同样是「建」不是「切」** ✓ —— Compressor **暂时没有生产调用方** ✓；
接线归 Stage 4 ✓（前置 = Agent Stage 5 的 A-26 ✗）。

### Stage 3：Persistence 落地

| 动作 | 细节 |
|---|---|
| manifest 落库 | 按 `(turn_id, step)` |
| `rolling_summary` 读写迁移 | 从 `metadata` 迁到新列 |
| 交付前落库 | 保证「模型已回答」时 manifest 一定存在 |

**旧代码减少**：**行数减少 0**（本 Stage 只搬写入点）—— **写入点迁移**：`metadata['rolling_summary']` → 新列（旧写入点在 `copilot.py:379-380` 与 `runner.py`，**等 Stage 4 停用旧循环后才归零**）。⚠️ **旧写入点还归不了零** —— 它们在 `copilot.py:379-380` 与 `runner.py`（Session / Agent 的文件），要等旧循环退役（Stage 4 停用 + Agent A-26）才归零；本层只保证**新链路不再写 `metadata`**。
**验收**：任一轮都能查出它的每次模型调用的上下文组成与淘汰原因。

#### 实施记录（2026-10-30 · Stage 3：Persistence 落地）

| 项 | 结果 |
|---|---|
| 契约端口 | `context/persistence.py` 的 `ContextManifestStore` ✓ —— **不引框架** ✓（SQL 实现在模块侧 ✓） |
| 模块实现 | `adapter/persistence/context_manifest_store.py` 的 `PostgresContextManifestStore` ✓ —— 落 `session_context_manifests` ✓ + 写 `agent_sessions.rolling_summary` ✓ |
| 表结构 | 迁移 **0047** ✓（`manifest` JSONB + `tokens_total` + `degraded` JSONB ✓ + `UNIQUE (turn_id, step)` ✓） |
| **一次模型调用一条** | 按 `(turn_id, step)` 落 ✓（决策 #6 ✓）—— ReAct 一轮里多次调用 → 多个 step ✓ |
| **冲突即 bug** | 同一个 `(turn_id, step)` 落两次 → **抛错** ✓（不静默覆盖 ✗✗）；⚠️ 落库后**立刻 flush** ✓ —— 否则唯一约束要到**提交时**才报 ✗✗（那时报出来的是 DB 的错，不是「这是 bug」✗） |
| **manifest 不是事件** | **不进 outbox** ✓、不投递 ✓（§5.3 ✓）—— 面向审计 / 评测 / 排障 ✓ |
| 摘要新落点 | `save_rolling_summary` 写**新列** ✓（`agent_sessions.rolling_summary` ✓）；⚠️ 旧副本在 `metadata` 里 ✓ —— **不清** ✓（旧路径仍是当前写者 ✗ → 清理归 Stage 4 之后 ✓） |
| 租户隔离 | 摘要写入**按租户过滤** ✓ —— 越权写不到别人的会话 ✓（测试断言 ✓） |
| **只新建，不动调用点** | ✅ 本 Stage **没有**接线 ✓ —— 落库时机「**必须在交付模型之前**」（§5.2 ✓）是**接线阶段**的责任 ✓ → 归 Stage 4 ✓（前置 = Agent A-26 ✗） |
| 测试 | 真库 5 条 ✓（内容落位 ✓ / 同 step 冲突报错 ✓ / 多 step 多行 ✓ / 摘要进新列 ✓ / 跨租户写不到 ✓） |

### Stage 4：接线与端到端

| 动作 | 细节 |
|---|---|
| Agent Loop 调 Context | 替换「自己拼 messages」的逻辑 |
| 召回失败的 degraded 标记 | `recall_degraded` 传到前端（走 `ResultEvent.flags`，键已在 Gateway §9.0 登记） |
| 端到端回归 | 长会话、混合中英文、召回为空、摘要模型故障 |
| **前端消费降级标记** | ⚠️ 前端目前**零消费** `flags`（§5.3.1）→ 需要一个前端工作项：读 `context_compacted.degraded` 与 `ResultEvent.flags`，把「未使用历史记忆」提示出来 |

**旧代码减少**：Agent Loop 内「自己拼 messages」的分支下线（该分支当前分散在 `nodes.py` 的 `agent` 节点与旧 `runner._run_turn_inner` 中）→ 打点，进入清理窗口。
>
> ⚠️ **本 Stage 是「停用」的真正落点**（Stage 1 / Stage 2 只新建、不动调用点）：`_load_messages` / 四套模板 / `compact.py` 到这里才真正没有调用方。
>
> **前置（硬）**：**Agent Stage 5 的 A-26 已完成** —— 旧循环 `runner._run_turn_inner` 已改接 `context/builder.py` + `memory/writer.py`。✅ **已于 2026-10-30 达成** ✓（实测 `X8` 打点归零 ✓）。
> ⚠️ **Stage 4 剩下的活**（A-26 只做了「装配」那一半 ✓）：**压缩那一半** —— 旧 `compact.py` 仍在服役 ✓（实测 `X9` = 1 ✓）→ Compressor 接线 + 停用 + 打点 + 端到端回归 ✓。
>
> ⚠️ **删除责任在别处**：`_run_turn_inner` 属台账 **X17**（**Agent 层**的唯一 owner，见 `agent-refactor-plan.md` §8.4；注意 **X5 是 `compile_loop_graph`**，不是它）。本层只负责「**停用 + 打点 + 确认无残留调用方**」，**删除动作在 Agent Stage 7** —— 否则会与 Agent 的删除 PR 互相冲突。
**验收**：§10 全部检查项通过。

#### 实施记录（2026-10-30 · Stage 4：接线 —— 压缩 / manifest / 摘要落新列）

> ⚠️ **前置已满足** ✓（Agent A-26 于 2026-10-30 完成 ✓）。

| 项 | 结果 |
|---|---|
| **压缩接线** | 旧循环的**两处** `compact_messages` 调用 → **新的 `ContextCompressor.compact()`** ✓（async ✓）—— 环外一次 ✓、**每次模型调用前一次** ✓（ReAct 里工具结果会不断进上下文 ✓）。⚠️ **旧的 `compact.py` 从此没有调用方** ✓（台账 **X9** ✓ —— 删除归 Stage 5 ✓） |
| **摘要模型** | 新增模块侧 `LLMSummaryAdapter`（`adapter/context/summary_adapter.py` ✓）—— 实现契约层的 `SummaryModelPort` ✓（用平台 `LLMPort` 调一次模型 ✓）。⚠️ **失败就抛** ✓ → 由 Compressor 降级 ✓（这里吞掉就没人知道降级了 ✗） |
| **manifest 先于模型落库** | `runner` 注入 `ContextManifestStore`（模块侧 `PostgresContextManifestStore` ✓）→ **每次模型调用前落一条** ✓（`turn_id` + `step` = 轮次内模型调用序号 ✓）。⚠️ **清单按「消息对象身份」对齐** ✓ —— 压缩后留下的消息还是那些对象 ✓ → 能对上 Builder 的条目（来源 / `ref_id` / `score` ✓）；后来加的消息（工具结果 ✓）现算一条 ✓ |
| **实测（演示栈）** | `session_context_manifests` 落行 ✓（`step=0` ✓、`tokens_total=402` ✓、`degraded={"recall_degraded":false,"compaction_degraded":false}` ✓；条目含 `system` / `agent` / `tenant` / `knowledge` 四类来源 ✓，`ref_id` 与 `score` 齐全 ✓） |
| **摘要写新列** | `agent_sessions.rolling_summary` 成为**唯一落点** ✓ —— 旧的 `metadata['rolling_summary']` **不再写** ✓（Session 层的写入点归零 ✓）。读侧改读新列 ✓（旧副本**只作过渡回退** ✓ —— 切换前写的行 ✓；回退的清理归 Stage 5 ✓） |
| **降级标记** | `context_compacted` chunk 带 `degraded` ✓（摘要模型挂了 → 确定性窗口 ✓ → 前端能看见 ✓） |
| **顺手修掉的两个真 bug** | ① **摘要失败 → 拿空摘要去折消息** ✗✗ → 折掉的那段对话**直接消失** ✗ → 改成**直接走二级** ✓（§4.2 ✓）；② **摘要的 token 被算两遍** ✗（`_fold` 已经把它放进消息里了 ✓）→ 预算虚报 ✗ → 该压的没压、不该压的报超限 ✗ → `tokens_after` 只算留下的那批消息 ✓ |
| **打点搬家** | `record_legacy_call("X8"/"X9")` **撤除** ✓ → 改打 `record_new_call("X8"/"X9")` ✓（同 R2 的做法 ✓：同一个台账编号，两套计数器 ✓）。⚠️ **X15 仍打 legacy** ✓ —— L3 与 knowledge 的双份注入**还没解决** ✓（决策 #1 归 Memory Stage 7 ✓）→ 指标**不能归零** ✗✗ |
| **旧路径变小（实测）** | 演示栈发一轮真实请求后：`legacy_calls{X8}=0` ✓、`{X9}=0` ✓、`{X11}=0` ✓；`new_calls{X8}=1` ✓、`{X9}=2` ✓；仍为 legacy 的只有 `X3`（`graph_state` 列 ✓）/ `X5`（占位图 ✓）/ `X17`（旧循环本体 ✓ —— 归 Agent Stage 7 ✓） |
| 测试 | 新增 `modules/agent_runtime/tests/unit/test_context_wiring.py` ✓（9 条 ✓：旧压缩不再被调用 ✓ / 长会话被压 ✓ / 摘要失败可见降级 ✓ / 短会话不压 ✓ / manifest 先于模型 ✓ / 清单描述的是真正喂进去的消息 ✓ / 摘要写新列 ✓）；`test_context_compressor.py` 补一条「**摘要失败不丢折叠内容**」✓（修 bug 的回归测试 ✓） |

⚠️ **本 Stage 尚未完成的部分**：

| 项 | 状态 | 门禁 |
|---|---|---|
| **C-22 降级标记到前端** | ✗ 未做 | ⚠️ **`ResultEvent.flags` 契约还没实现** ✗（Gateway 层 §9.0 只在方案里 ✓）—— Context 只能产出 `degraded_flags` ✓，**没有可投递的通道** ✗ → 归 **Gateway 层** ✓ |
| **前端消费降级标记** | ✗ 未做 | 前端零消费 `flags` ✓（§5.3.1 ✓）→ 独立工作项 ✓ |
| **C-25 自拼 messages 分支停用** | ✅ 已达成（旧循环那半 ✓） | ⚠️ `nodes.py` 的 `agent` 节点那半是**死代码** ✓（19 节点图没有生产调用方 ✓）→ 删除归 Agent Stage 7 ✓ |

### Stage 5：清理与封口

| 动作 | 细节 |
|---|---|
| 删 `adapter/graph/compact.py`（**53 行**） | |
| 删 `adapter/llm/prompts.py` 四函数 | |
| 删 `runner.py` 的 `_load_messages` | |
| 删 `runtimes/.../context/budget.py` | 拆入新文件后删除 |
| 删 `metadata['rolling_summary']` 残留读写 | |
| 启用 CI 扫描脚本 | 台账 **X8 / X9 / X10** 段（脚本唯一来源：`cleanup-ledger.md` §3.1） |
| 更新台账状态 | **X8 / X9 / X10** → 已清理 |
| 更新现状文档 | `docs/copilot-chat-module-architecture.md` |

**旧代码减少**：§8.4 删除清单**归零** —— `adapter/graph/compact.py`（**53 行**）+ `adapter/llm/prompts.py` 四函数（~60 行）+ `runner.py` 的 `_load_messages`（~70 行）+ `runtimes/.../context/budget.py`（**384 行**）+ `metadata['rolling_summary']` 残留读写，**合计约 570 行**。
**验收**：台账本层条目全部「已清理」；扫描脚本无命中。

#### 实施记录（2026-10-30 · Stage 5：清理与封口）

| 项 | 结果 |
|---|---|
| **删 `adapter/graph/compact.py`** | ✅ 文件已删 ✓（**53 行** ✓）—— 调用点随 Stage 4 换掉 ✓ → 扫描规则 `compact.py`（X9 ✓）**已启用** ✓ |
| **删 `runner.py` 的 `_load_messages`** | ✅ 函数已删 ✓（**~70 行** ✓）—— 调用点随 A-26 换掉 ✓ → 扫描规则 `_load_messages`（X8 ✓）**已启用** ✓ |
| **四套 prompt 模板** | ✅ 旧模板随 **Session Stage 5b** 删除 ✓；新渲染（`context/prompts.py` 单段式 ✓）随 Stage 4 接上生产 ✓ → 台账 **X10** 已清理 ✓ |
| **删 `metadata['rolling_summary']` 残留** | ✅ Session 层**不再写** ✓、`copilot.py` **不再读** ✓（只读新列 `agent_sessions.rolling_summary` ✓ —— 迁移 0047 已回填历史行 ✓） |
| **扫描脚本** | 启用规则 **28 → 30** 条 ✓（X8 / X9 ✓）—— 扫描通过 ✓ |
| **台账** | **X8 / X9 / X10 → 已清理** ✓ |
| **旧代码减少** | **~183 行**（`compact.py` 53 ✓ + `_load_messages` ~70 ✓ + 摘要残留少量 ✓ + 四套模板 ~60 ✓ —— 后者随 Session S-33 ✓） |

⚠️ **本 Stage 有一项没做**（**不是漏了** ✓ —— 有前置 ✓）：

| 项 | 状态 | 原因 |
|---|---|---|
| **C-29 删 `runtimes/.../context/budget.py`**（**384 行** ✓） | ⚠️ **未删** ✓ | 它的两个旧类（`Compactor` / `ContextAssembler` ✓）还被 **19 节点图的 `nodes.py`** import ✓ —— 那图**没有生产调用方** ✓（死代码 ✓）→ **删除归 Agent Stage 7** ✓（连 `nodes.py` 一起删 ✓ —— 免得两个 PR 互相冲突 ✗✗） |


### 阶段与「旧代码减少」对照

| 阶段 | 删除/替换 | 旧代码减少（行） | **新写入量（估算）** | 旧路径状态 |
|---|---|---|---|---|
| Stage 0 | 无（纯新增 + 迁移 0047） | 0 | 1 表 + 1 列；manifest 表按模型调用写入 | — |
| Stage 1 | `runner._load_messages`（70 行） | 0（**只新建，不动调用点**） | manifest 行 = 模型调用次数 × 轮次 | **不停用**（停用在 Stage 4） |
| Stage 2 | `adapter/graph/compact.py`（**53 行**） | 0（**只新建，不动调用点**） | 同上 | **不停用**（停用在 Stage 4） |
| Stage 3 | 无（新增 `session_context_manifests` 写入） | 0 | 同上 | — |
| Stage 4 | `_load_messages` + 四套模板 + `compact.py` + Agent Loop 内自拼 messages 的分支 | **0**（**只停用 + 打点，不删**）| 同上 | **停用 + 打点**（前置 = Agent A-26）；**删除归 Agent 层 X17（~250 行）** |
| Stage 5 | 上述 + 四套 prompt 模板 + `budget.py` + `metadata['rolling_summary']` 读写点 | ~570 行 | 同上（不再新增） | **删除**（台账清零） |

> **新写入量的量级对照**：`session_context_manifests` 的行数 = **模型调用总次数**（不是消息数、不是轮次数）。ReAct 深度 3 的轮次 ≈ 3 行。粗估：单租户日均 1 万轮、平均深度 2.5 → ≈ 2.5 万行/天、每行约 2–8 KB JSONB → **约 50–200 MB/天**。这是本层**最大的新增存储成本**，缓解手段见 §11 风险表（保留期策略 / 只存摘要指纹）。

### 本层的「未接管」（都要等门禁 ✓，不能提前做 ✗）

| # | 事项 | 门禁 | 归属 |
|---|---|---|---|
| **Stage 4 接线** | Agent Loop 改调 `context/builder.py` + `memory/writer.py` | ✅ **已达成**（2026-10-30）—— 装配那一半随 **Agent A-26** 接上 ✓；**压缩那一半随 Context Stage 4 接上** ✓（旧的 `compact.py` 已无调用方 ✓，实测 `X9` = 0 ✓） | Context 层（Stage 4 ✓ 已达成） |
| **C-22 降级标记到前端** | `recall_degraded` 走 `ResultEvent.flags` | ✅ **已达成**（2026-10-31）—— `ResultEvent.flags` 契约已落地 ✓（Gateway §9.0 ✓ —— 内部事件与对外 chunk **同一个词汇** ✓）+ `ChunkEnvelope.flags` ✓ → **降级终于有可投递的通道** ✓（Context 产出 → 运行时 → 事件流 → SSE ✓） | — |
| **前端消费降级标记** | 读 `context_compacted.degraded` 与 `ResultEvent.flags` | ⚠️ 前端目前**零消费** `flags` ✓（§5.3.1 ✓）→ 独立工作项 ✓ | 前端 |
| **Stage 5 清理** | 删 `compact.py` / `_load_messages` / `budget.py` / `metadata['rolling_summary']` 残留 | ✅ **已达成**（2026-10-30）—— X8 / X9 / X10 已清理 ✓；扫描规则已启用 ✓；⚠️ **`budget.py`（384 行）未删** ✓ → **归 Agent Stage 7** ✓（`nodes.py` 还 import 它 ✓ —— 死代码 ✓） | 本层（Stage 5 ✓ 已达成 · `budget.py` 归 Agent） |
| **X9 / X8 的扫描规则启用** | `compact.py` / `_load_messages` 两条规则 | 旧实现删掉后才开 ✓（X10 的规则**已开** ✓ —— 2026-10-30） | 本层（Stage 5） |
| **前端消费降级标记** | 读 `context_compacted.degraded` 与 `ResultEvent.flags` | ⚠️ 前端目前**零消费** `flags` ✓（§5.3.1 ✓）→ 独立工作项 ✓ | 前端 |
| **快照** | `session_context_snapshots` | 决策 #3：**先不做** ✓ | — |

⚠️ **解锁链**（要接线就得按这个顺序走 ✓）：

```
Memory Stage 0–3（Writer 重写） ✓
        ↓
Agent Stage 5 · A-26（旧循环改接新 Builder / Writer） ✓（2026-10-30）
        ↓
Context Stage 4（接线：压缩 / manifest / 摘要落新列） ✓（2026-10-30）
        ↓
Context Stage 5（清理：删 compact.py / _load_messages / metadata 残留） ✓（2026-10-30）
        ↓
Memory Stage 7（M-43 删 runner._remember） ← **现在在这里**
```

---

## 10. 验收标准

> **本层在系统级验收中的责任**：
> 本层负责系统级验收的 **#8（上下文不超限）· #10（manifest 可查）**（完整清单见 [`README.md`](README.md) §7）。

### 10.1 功能验收

1. **输出可直接喂模型**：产出是 `[{role, content}]`，不是字符串片段；
2. **agent 身份正确**：上下文里含 agent 的 soul / prompt / agents / tools / user，不是通用语；
3. **优先级不可换**：安全提示与治理约束永远在最前，永不被淘汰；
4. **本轮输入永不降级**：用户输入与工具结果不因超预算被丢；
5. **压缩有效**：超长会话压缩后 token 在预算内；仍超限 → 明确 `CONTEXT_TOO_LARGE`，**不是**继续超限喂模型；
6. **摘要保真**：摘要保留决策、数字、承诺、未完成事项与来源 ID；
7. **摘要失败不崩**：降级为确定性窗口 + `compaction_degraded` 标记；
8. **降级序正确**：淘汰顺序是「旧消息摘要 → 低分召回 → 附件摘要 → 明确错误」，每一步记进 manifest；
9. **manifest 完整**：每次模型调用一条，含来源、token、版本、ref_id、score、`filtered_reason`；
10. **manifest 先于模型落库**：模型已回答时 manifest 一定存在；
11. **召回方向正确**：Context 主动发起召回；Memory 只提供存取；
12. **事件正确**：`context_compacted` 的 `tokens_before` 不再恒为 0；
13. **架构测试**：Context 层不得 import FastAPI / SQLAlchemy；
14. **召回失败可见**：记忆 / 知识召回失败 → `recall_degraded = true`（不再是静默吞掉）；
15. **降级不丢摘要**：确定性降级后 `rolling_summary` 仍包含此前轮次的结论；
16. **工具结果清洗保留**：工具错误 / 超长输出被截到 1500 字；
17. **口径一致**：新旧两条路径的 token 估算差异 < 10%。


---

### 10.2 架构测试

```python
# tests/architecture/test_context_boundary.py
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")

def test_context_layer_has_no_framework_imports():
    """Context 层不得依赖框架 —— 由 README §3.2 的边界判据派生。"""
    for path in _py_files(("backend/runtimes/agent_runtime/src/qzdap_agent_runtime/context",)):
        for mod in FORBIDDEN:
            assert mod not in _imports_of(path), f"{path} 引入了 {mod}"
```

另加三条本层特有的规则：

| # | 规则 | 检查方式 |
|---|---|---|
| 1 | **Context 不直接访问记忆表** | import 扫描（只能经 `MemoryPort` / `KnowledgePort`） |
| 2 | **Context 不写消息表** | import 扫描（`session_messages` / `session_turns` 只读） |
| 3 | **manifest 必须先于模型落库** | 集成测试断言：模型已被调用 ⇒ `session_context_manifests` 有对应 `(turn_id, step)` 行 |

### 10.3 「没有第二套实现」的扫描

**扫描脚本的唯一来源是 [`cleanup-ledger.md`](cleanup-ledger.md) §3.1**，本层不另写一份。Context 域对应的规则：

| 旧符号 | 台账条目 |
|---|---|
| `_load_messages` | X8 |
| `compact.py` | X9 |
| `build_system_prompt` | X10 |

> 启用时点：**Context Stage 5 合并时**，与旧实现删除在同一个提交里完成。

---

## 11. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **manifest 写入量** | 每模型调用一行 + JSONB | 按 `turn_id` 聚合；保留期策略；必要时只存摘要指纹 |
| **摘要模型成为延迟瓶颈** | 每轮多一次 LLM 调用 | 异步 + 仅在超预算时触发 + 结果缓存（按内容 hash） |
| **摘要质量不稳定** | 丢失关键决策 | 结构化摘要模板 + 保真度断言（关键决策必须出现在摘要里，否则标记 degraded） |
| **token 估算低估导致撞窗口** | 模型报上下文超限 | 决策 #2 选按语种估算；压缩后复验；仍超限明确报错 |
| **agent prompts 缺失的历史影响** | 旧路径已经正确，新 runtime 一直是错的 | 迁移时以旧路径为准；补一个「agent 身份在上下文中出现」的断言测试 |
| **与 Memory 层耦合** | 召回端口改动波及 Context | `MemoryPort` / `KnowledgePort` 契约不变（已存在） |

### 11.1 回退

| 时点 | 回退方式 | 代价 |
|---|---|---|
| Stage 1–3 | `git revert` 对应提交 | 无 |
| Stage 4（已接线） | `git revert` 接线提交 → 回落旧 `_load_messages` | 无（旧实现在场） |
| Stage 5（已清理） | 需**重新上线旧版本** | `session_context_manifests` 表留着（无害），**但 manifest 数据会缺失** |

> **本层特有的不可逆点**：几乎没有 —— manifest 表是**只写**的，删了也不影响主链路。
>
> **回退后仍可用的**：`agent_sessions.rolling_summary` 列（Context 建的，Session 也读）。
>
> **回退后不可用的**：**上下文消融评测**与**上下文审计**（依赖 manifest）。这是本层的分析能力，回退即失去 —— 属于可接受的代价，但要记在决策里。
---

## 12. 治理与可观测性落点

### 12.1 治理落点（Governance）

| 本层步骤 | 闸门 | 拒绝 / 降级时的行为 |
|---|---|---|
| 组装优先级 1–2 | 安全系统提示词与治理约束**永不降级** | 预算不足时也不裁剪；宁可整体超限报错 |
| 组装优先级 3 | 租户 / 工作区 / 用户上下文 | 越权内容**不进入上下文**（不是裁剪，是不装配） |
| 记忆 / 知识片段 | 由 Memory 层做可见范围过滤 | 过滤在 Memory 侧完成，Context **不二次判权**，也不兜底 |
| 压缩 | 用户输入与工具结果**永不降级** | 只裁 3/4/5 优先级；两级降级后仍超限 → `CONTEXT_TOO_LARGE` |
| 摘要调用 | 摘要模型本身受模型白名单与预算约束 | 摘要失败 → 二级确定性窗口 + `compaction_degraded` |

> **本层不拥有的治理**：检索侧的可见范围（Memory）、模型与工具的取值（Agent 层 Execution）。Context **只装配、不判权**。

### 12.2 可观测性指标（Observability）

指标名进 `qzdap_*` 命名空间，实现落在 `backend/libs/observability/src/qzdap_observability/metrics.py`。

| 指标名 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `qzdap_context_assemble_duration_seconds` | Histogram | `agent_id` | 组装耗时 |
| `qzdap_context_tokens` | Histogram | `agent_id`, `stage` | token 估算分布（`stage`：`assembled` / `after_compaction`） |
| `qzdap_context_compaction_total` | Counter | `outcome` | 压缩触发数（`outcome`：`summary` / `window` / `too_large`） |
| `qzdap_context_compaction_degraded_total` | Counter | `reason` | 降级次数（`reason`：`summary_failed` / `recall_failed`） |
| `qzdap_context_manifest_rows_total` | Counter | `tenant_id` | manifest 写入行数（与存储成本直接相关，见 §11 风险） |
| `qzdap_context_filtered_entries_total` | Counter | `source`, `reason` | 被淘汰片段数（`reason` 对应 manifest 的 `filtered_reason`） |
| `qzdap_context_recall_duration_seconds` | Histogram | `source` | 召回耗时（`source`：`memory` / `knowledge`） |
| `qzdap_legacy_calls_total` | Counter | `entry` | 旧实现调用计数（标签 `entry` 为台账编号） |

**Span 划分**：

| Span | 父子关系 | 属性 |
|---|---|---|
| `context.assemble` | 根 | `agent_id`, `tokens_estimated`, `degraded` |
| `context.recall` | `context.assemble` | `source`, `hit_count` |
| `context.compact` | `context.assemble` | `tokens_before`, `tokens_after`, `level` |
| `context.manifest.persist` | `context.assemble` | `turn_id`, `step` |

> **观测约束**：span 属性**不得包含记忆片段原文、知识正文、摘要正文**。只允许出现 token 数、条数、来源与淘汰原因。

### 12.3 审计

| 事件 | 何时写 | 内容 |
|---|---|---|
| `context.compaction.degraded` | 走确定性窗口降级 | 轮次、token 前后、降级原因 |
| `context.manifest.persisted` | manifest 落库 | `turn_id`、`step`、`tokens_total`、淘汰条数 |

> 审计写入走 Governance 模块。manifest 本身**不是审计事件**，二者不可混用（见 §5.3）。
---

## 附录 A：已定稿的决策（2026-10-29 逐条确认）

> 以下 **7 条**决策（#1–#7）已逐条确认并定稿。**改动其中任何一条，都必须同步修改正文对应章节，并在 §9 补记受影响的阶段。**

| # | 决策 | 定稿结果 | 备选 | 影响 |
|---|---|---|---|---|
| 1 | agent prompts 拼装位置 | **放在 Builder 内**（与旧路径一致、风格可控） | 下沉到 catalog 的「已渲染 system prompt」字段 | 每次改 prompt 的成本、风格一致性 |
| 2 | token 估算口径 | **统一用 `budget.py:42` 的按语种估算**（中文 ≈ 1 字 1 token，其他 ≈ len/4），并让旧路径也用它 | 统一用 `len//4` / 引入 `tiktoken` | 预算一致性（初稿把 `budget.py:42` 误读成 `len//4`，实际上它**已经是**按语种估算 —— 本决策的真问题是**两条路径口径不一致**） |
| 3 | 上下文快照 | **先不做**（manifest 已能回答「喂了什么」） | 采样存快照 | 存储成本、回归夹具能力 |
| 4 | 摘要触发阈值 | `context_window × 0.70`（沿用旧路径 `WINDOW_RATIO`） | 按模型的实际窗口表查 | 超限概率 |
| 5 | 仍超限时 | **抛 `CONTEXT_TOO_LARGE`**（明确错误，`ErrorCode` 已有） | 静默截断到硬上限 | 用户可诊断性 |
| 6 | manifest 存储粒度 | **每次模型调用一条**（`(turn_id, step)`） | 每轮一条 | 审计精度 vs 写入量 |
| 7 | `context_compacted` 的降级标记 | **给 `ContextCompactedChunk` 补一个可选 `degraded: bool = False`**（改 `libs/schema`） | 只走 `ResultEvent.flags`，不动共享契约 | 前端目前**不读 chunk 的任何字段**（只按 `kind` 提示）→ 补字段向后兼容；比让前端翻 `flags` 更直接 |

---

## 附录 B：现状 → 目标 文件对照速查

| 现状文件 | 目标状态 |
|---|---|
| `adapter/graph/runner.py` `_load_messages`（70 行） | 迁入 `context/builder.py` |
| `adapter/graph/compact.py`（**53 行**） | **删除** → `context/compressor.py` |
| `adapter/llm/prompts.py`（四套模板） | **删除** → `context/prompts.py` 单段式 |
| `runtimes/.../context/budget.py`（**384 行**） | 拆入 `context/{builder,compressor,tokens,types}.py`（含 `InMemorySummaryModel` 一并退役 → 实施方案 §1.5 基线白名单在 **Context Stage 5** 移除） |
| `runtimes/.../graph/nodes.py` 的 `assemble_context` 节点（`:436-477`） | **改**：把 `ctx.messages` 整体写回 state（§1.2④）；`system_prompt` / `target_tokens` 的硬编码占位改成真实注入 |
| `agent_sessions.metadata['rolling_summary']` | → `agent_sessions.rolling_summary` 列 |
| （无） | 新增 `session_context_manifests` 表 |
| （新增）`runtimes/.../context/` | builder / compressor / persistence / prompts / tokens / types |

---

## 附录 C：2026-10-29 审查修正记录

> 本方案 v1.0 → **v1.1** 的全部修正。**每条都对着 `backend/` 的代码核实过**。
>
> **决策定稿（2026-10-29）**：附录 A 的 **7 条**决策已由用户拍板，取值为本方案的建议值。

| # | 级别 | 问题 | 修正 | 落点 |
|---|---|---|---|---|
| **S1** | 严重 | `rolling_summary` 回填**只读 `metadata`**，漏了权威值所在的 `graph_state` —— 与 Session 方案 §7.3 直接矛盾，会丢摘要 | 回填改成三步：`graph_state` 优先 → `metadata` 兜底 → 清 `metadata` | §7.3 |
| **S2** | 严重 | 「`estimate_tokens = len//4`（`budget.py:42`）」是**误读** —— 它**已经是按语种估算**；且 `state.py:24` 是另一个函数（收消息列表）。决策 #2 建立在误读上 | 决策 #2 改写为「**两条路径口径对齐**」，真问题是新旧不一致 | §3.6 / 附录 A #2 |
| **S3** | 严重 | **停用阶段三处文档三个说法**：Context 方案说 Stage 4，实施方案 §1.2 关注点 #9–#11 说 Stage 1/2，台账 §5.4 说 Stage 1/2（X10） | 以 Context 方案为准：**统一 Stage 4**（前置 = Agent A-26）；实施方案 §1.2 与台账已同步 | §9 / 实施方案 §1.2 / 台账 §5.4 |
| **S4** | 严重 | `context_compacted` chunk **没有 `degraded` 字段**（带它的是 `KnowledgeSearchChunk`），而方案说「前端契约已有」 | 决策 #7：**在 `libs/schema` 补可选字段**（前端只按 `kind` 提示 → 向后兼容） | §4.5 / §5.3.1 / 附录 A #7 |
| **S5** | 严重 | 新 runtime 的 `assemble_context` 节点**把 `ctx.messages` 丢掉了**（只回传 manifest + degraded）—— §1.2 漏了第四处硬伤 | 补为硬伤 ④；迁移清单加入 `nodes.py` 的该节点 | §1.2④ / §8.2 |
| **M1** | 中 | 说 `ManifestEntry`「只需加过滤原因字段」—— **`filtered_reason` 已存在**（`budget.py:62`） | 改为「已存在」；本层要补的是 `ref_id` / `score` | §1.6 / §3.5 |
| **M2** | 中 | 旧路径**静默吞掉召回失败**（`runner.py:523,549`），没有 `recall_degraded` | 补为 §1.4.2；Stage 1 增加「召回失败必须可见」 | §1.4.2 / §9 Stage 1 |
| **M3** | 中 | 旧 `compact.py` 的三项行为没被继承（工具结果清洗 / 首个 system 保留 / **摘要累加**）；且新 runtime 的确定性降级**用占位串覆盖 `existing_summary`** → 照抄会丢历史摘要 | 补 §1.4.1；§4.3 缺陷表 +2 条（降级追加而非覆盖、工具结果清洗） | §1.4.1 / §4.3 |
| **M4** | 中 | `UNIQUE (turn_id, step)` 在**重放 / 整轮重跑**下会撞，而方案说「冲突即抛错」 | 补三行语义：重试 → step 递增；重放 → 不写新行；整轮重跑 → 不复用 `turn_id` | §5.1.1 |
| **M5** | 中 | 0047 的依赖理由写成「`graph_state` 已迁出」—— 那在 **Session Stage 6**，不在 0046 | 依赖改为「物理顺序 + 需要 `session_messages.session_seq`」 | §7.2 |
| **M6** | 中 | Stage 3 说「`metadata['rolling_summary']` 写入点归零」 —— 但写入点在 `copilot.py:379-380` 与 `runner.py`，旧循环退役前归不了零 | 改为「新写入改到新列；旧写入点等 Stage 4 停用后才归零」 | §9 Stage 3 |
| **M7** | 中 | §5.3.1 把「前端行为」写成既成事实 —— 但**前端零消费 `flags`** | 明确「字段落地 ≠ 用户看得见」，Stage 4 增前端工作项 | §5.3.1 / §9 Stage 4 |
| **M8** | 中 | `InMemorySummaryModel` 的删除归属冲突（实施方案 §1.5 说 Agent Stage 7，但 Context Stage 5 删 `budget.py` 就删了它） | 明确基线白名单在 **Context Stage 5** 移除 | §8.4 / 附录 B |
| **L1** | 轻 | `compact.py` 写 50 行，实测 **53 行**（多处） | 全部改为 53 | §1.4 / §8.2 / §8.4 / §9 / 附录 B |
| **L2** | 轻 | 行号：`budget.py:261` → 实际 **265**；`ports.py` → 实际 `application/ports/__init__.py` | 逐处修正 | §1.2 / §1.6 |
| **L3** | 轻 | 旧路径的 `top_k=8/6`、按 score 降序、每条 400 字截断没进迁移清单 | 补入 §3.2 与 Stage 1 | §3.2 / §9 Stage 1 |
| **L4** | 轻 | Stage 0 验收「与 tiktoken 偏差 < 15%」测的是**已经正确**的实现；tiktoken 未声明为测试依赖 | 改为「新旧两条路径口径差异 < 10%」，tiktoken 仅作测试期对照 | §9 Stage 0 |

> **同步改动**：`implementation-plan.md`（§1.2 关注点 #9–#11 / §1.5 / §1.6 / §3.4 / §4.3 附录 A）、`cleanup-ledger.md`（§5.4 X8 / X9 / X10 的停用阶段）、`README.md`（依赖与里程碑表述）。

### 本轮（v1.1 → v1.2）骨架重排

| # | 级别 | 问题 | 修正 | 落点 |
|---|---|---|---|---|
| **D1** | 严重 | **§0 缺「实现收敛规则」小节** —— 其余五层都有（Router §0.4 / Session §0.4 / Agent §0.5），README §5.1 的结构表也声称六份齐备；本层只在文档头一行提了「最终态只有一个实现」，**台账归属与「不可结转」在 §0 拿不到** | 新增 **§0.4 实现收敛规则**：台账条目 X8 / X9 / X10 + **本层特有的收敛形态**（旧实现还在服役 → Stage 1–3 只新建不动调用点，「旧代码减少」为 0；停用推迟到 Stage 4，删除归 Agent 层）| §0.4 |
| **D2** | 严重 | **§9 对照表把 Agent 的删除量记到本层头上** —— Stage 4 写「~200 行」，但该 Stage 只做停用 + 打点，**删除归 Agent 层 X17**；且 200 既不是本层的量、也不是台账口径（X17 是 ~250 行）| Stage 4「旧代码减少」改为 **0（只停用 + 打点）**，并注明删除量归 Agent X17 | §9 对照表 |
| **D3** | 中 | **§4.3 标题说「四个缺陷（§1.3）」，表里是六行** —— 其中 5、6 来自 §1.4.1 而非 §1.3 | 标题改为「**必须修掉的六个缺陷（§1.3 四处 + §1.4.1 两处）**」 | §4.3 |
| **D4** | 中 | **§8.2 迁移清单缺 `nodes.py` 那一行** —— 附录 C 的 S5 声称「迁移清单加入 nodes.py 的该节点」，但 §8.2 里没有；而第 ④ 处硬伤正是在那个节点上 | §8.2 补 `nodes.py` 的 `assemble_context` 行（**改写**，并注明该文件在 Agent Stage 7 整体删除，本层只改接线）| §8.2 |
| **D5** | 中 | **§6 边界表缺 `Gateway → Context` 行** —— 而 §3.1 优先级 3 要装「渠道 / 附件上下文」，其源头就是 Gateway 的 `InboundMessage` / `AttachmentRef` | §6 补 Gateway 行 | §6 |
| **D6** | 中 | **「工具白名单」归属三处不一** —— §3.1 说 Context 自己装、§6 说 Session 给、而 Agent §5.3.1 说来自 **agent 配置的绑定集** | §6 改为「**不含工具白名单**」并注明真实来源；§0.3 的「不做」表同步 | §3.1 / §6 |
| **D7** | 中 | **§0.3 把「模型与工具的取值」归给 Agent Router** —— 与 Agent v1.2 的新骨架（取值归 ⑨ Execution）冲突，且与本文 §12.1 自相矛盾 | §0.3 改为「**Agent Loop**（循环）/ **Agent Router**（只选专家）/ **Execution**（取值与执行）」| §0.3 |
| **D8** | 中 | **§2 目标架构图与紧随其后的文字矛盾** —— 图把三个子件画成单向串行无回边，而正文说「压缩是装配的条件分支、结果要回到装配里」 | §2 图上加「不是流水线」说明；**新增 §0.2 前提小节**（四条前提）作为全篇前提 | §0.2 / §2 |
| **D9** | 轻 | **§9 Stage 3 的「旧代码减少」口径与对照表不一致** —— 正文写「新写入全部改到新列」，对照表写 0 | 正文改为「**行数减少 0；写入点迁移**」，并注明旧写入点等 Stage 4 才归零 | §9 Stage 3 |

> **同步改动**：`README.md`（文档表状态、§5.1 结构表补 §0.4 收敛规则）、`implementation-plan.md`（§3.4 的 Stage 表与退出判据）。