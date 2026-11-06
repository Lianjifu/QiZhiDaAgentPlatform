/**
 * AdminToolAudit hooks — 5 个列表查询(entries/risks/rules/scopes/stats)。
 * 收藏与风险处置由后端处理，选中项属于页面 UI 状态。
 */
import {
  useApiQuery,
  useApiMutation,
} from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type {
  AuditEntry, AuditRule, CreateAuditRuleInput, PermissionScope, RiskEvent,
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
