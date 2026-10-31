"""Branded UUID types for every cross-module entity.

A branded type is a `NewType`-derived UUID alias that the type-checker treats
as distinct from raw UUID. This stops you from passing a SessionId where a
UserId is expected — a category of bug the type-checker can't otherwise catch.

⚠️ **为什么住在 kernel 而不是 schema** ✓（2026-10-31，P-13 ✓）——
品牌 ID 是**最底层的值对象** ✓；**每一层**（libs ✓ / modules ✓ / composition ✓ /
契约层 ✓）都已经依赖 `qzdap_kernel` ✓ → 住在这里，**整条栈共用同一套品牌词汇** ✓
（住 schema 的话 kernel 自己用不上 ✓ —— `Principal` / `EventEnvelope` / 上下文
就只能是裸 `UUID` ✗✗ → 「进应用层前转品牌 ID」这条规则**在 kernel 层就断了** ✗）。

**边界规则**（P-13 的落点 ✓）：
- **裸 `UUID` 只允许出现在最外层** ✓ —— HTTP 头 / 查询参数 / JWT 解析 / DB 行 ✓；
- **进到应用层之前**转成品牌 ID ✓；
- 应用层往下（用例 / 端口 / 领域实体）**一律品牌 ID** ✓。
"""

from __future__ import annotations

from typing import NewType
from uuid import UUID

# ── Identity ──────────────────────────────────────────────────────────────
TenantId = NewType("TenantId", UUID)
WorkspaceId = NewType("WorkspaceId", UUID)
UserId = NewType("UserId", UUID)
ApiKeyId = NewType("ApiKeyId", UUID)

# ── Agent runtime ─────────────────────────────────────────────────────────
AgentId = NewType("AgentId", UUID)
AgentTemplateId = NewType("AgentTemplateId", UUID)
AgentVersionId = NewType("AgentVersionId", UUID)
SessionId = NewType("SessionId", UUID)
TurnId = NewType("TurnId", UUID)

# ── Tool ──────────────────────────────────────────────────────────────────
ToolId = NewType("ToolId", UUID)
ToolCallId = NewType("ToolCallId", UUID)

# ── Skill ─────────────────────────────────────────────────────────────────
SkillId = NewType("SkillId", UUID)
SkillInstallId = NewType("SkillInstallId", UUID)
SkillInvocationId = NewType("SkillInvocationId", UUID)

# ── Memory / Knowledge ────────────────────────────────────────────────────
MemoryEntryId = NewType("MemoryEntryId", UUID)
KnowledgePackageId = NewType("KnowledgePackageId", UUID)
KnowledgeAssetId = NewType("KnowledgeAssetId", UUID)
KnowledgeChunkId = NewType("KnowledgeChunkId", UUID)

# ── Governance / Platform ─────────────────────────────────────────────────
PolicyId = NewType("PolicyId", UUID)
ApprovalId = NewType("ApprovalId", UUID)
DecisionEventId = NewType("DecisionEventId", UUID)
AuditLogId = NewType("AuditLogId", UUID)
PlanId = NewType("PlanId", UUID)
WorkflowRunId = NewType("WorkflowRunId", UUID)
StepRunId = NewType("StepRunId", UUID)

# ── Model / Channel ───────────────────────────────────────────────────────
ModelId = NewType("ModelId", UUID)
CredentialId = NewType("CredentialId", UUID)
RoutingPolicyId = NewType("RoutingPolicyId", UUID)
QuotaCounterId = NewType("QuotaCounterId", UUID)
ChannelId = NewType("ChannelId", UUID)
ChannelSecretId = NewType("ChannelSecretId", UUID)
ChannelDeliveryId = NewType("ChannelDeliveryId", UUID)

# ── Agent factory / Evaluation (P8) ───────────────────────────────────────
ReleaseId = NewType("ReleaseId", UUID)
EvalDatasetId = NewType("EvalDatasetId", UUID)
EvalCaseId = NewType("EvalCaseId", UUID)
EvalRunId = NewType("EvalRunId", UUID)

# ── Observability / Platform (P9) ──────────────────────────────────────────
RunRecordId = NewType("RunRecordId", UUID)
CostRecordId = NewType("CostRecordId", UUID)
SubscriptionId = NewType("SubscriptionId", UUID)
TenantSettingId = NewType("TenantSettingId", UUID)

# ── Self-Evolution (A4 / P10+) ─────────────────────────────────────────────
EvolveCandidateId = NewType("EvolveCandidateId", UUID)
