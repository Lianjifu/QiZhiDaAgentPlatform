/**
 * AdminToolAudit hooks — 5 个列表查询(entries/risks/rules/scopes/stats)。
 * 收藏 / 选中 / 风险解决等乐观更新保持在 page 层 local state。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type {
  AuditEntry, AuditStats, AuditRule, CreateAuditRuleInput, PermissionScope, RiskEvent,
} from './schema';

export function useAuditEntries() {
  return useApiQuery<AuditEntry[]>([...qk.admin.audit.entries], '/api/admin/audit/entries', undefined, {
    staleTime: 30_000,
  });
}

export function useAuditRisks() {
  return useApiQuery<RiskEvent[]>([...qk.admin.audit.risks], '/api/admin/audit/risks', undefined, {
    staleTime: 30_000,
  });
}

export function useAuditRules() {
  return useApiQuery<AuditRule[]>([...qk.admin.audit.rules], '/api/admin/audit/rules', undefined, {
    staleTime: 60_000,
  });
}

export function useCreateAuditRule() {
  return useApiMutation<AuditRule, CreateAuditRuleInput>(
    () => '/api/admin/audit/rules',
    { invalidateKeys: [qk.admin.audit.rules] },
    'POST',
  );
}

export function usePermissionScopes() {
  return useApiQuery<PermissionScope[]>([...qk.admin.audit.scopes], '/api/admin/audit/scopes', undefined, {
    staleTime: 60_000,
  });
}

export function useAuditStats(entries: AuditEntry[]): AuditStats {
  const total = entries.length;
  const denied = entries.filter((e) => e.outcome === 'denied').length;
  const critical = entries.filter((e) => e.severity === 'critical').length;
  const sensitive = entries.filter((e) => e.hasSensitive).length;
  const allowed = entries.filter((e) => e.outcome === 'allowed').length;
  const blocked = entries.filter((e) => e.outcome === 'denied' || e.outcome === 'timeout').length;
  const pending = entries.filter((e) => e.outcome === 'pending').length;
  const timeout = entries.filter((e) => e.outcome === 'timeout').length;
  const byCategory = {
    tool: entries.filter((e) => e.category === 'tool').length,
    data: entries.filter((e) => e.category === 'data').length,
    auth: entries.filter((e) => e.category === 'auth').length,
    mcp: entries.filter((e) => e.category === 'mcp').length,
  };
  const denyRate = Math.round((denied / Math.max(total, 1)) * 1000) / 10;
  return { total, denied, critical, sensitive, allowed, blocked, pending, timeout, denyRate, byCategory };
}
