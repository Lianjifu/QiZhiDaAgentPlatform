"""Branded UUID types for every cross-module entity.

A branded type is a `NewType`-derived UUID alias that the type-checker treats
as distinct from raw UUID. This stops you from passing a SessionId where a
UserId is expected — a category of bug the type-checker can't otherwise catch.
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
