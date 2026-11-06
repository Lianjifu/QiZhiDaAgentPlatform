/**
 * 管理侧「额度管理」hooks — 4 类实体 list + create / update / toggle。
 * 端点 /api/admin/quotas/* 走后端 API（运行时不再有 mock 接管 ✓）。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type {
  EnterpriseBudget, DepartmentQuota, UsageMetric, AlertRule,
  CreateBudgetVars, CreateAlertVars, UpdateBudgetVars, ToggleAlertVars,
} from './schema';

const PATH = '/api/admin/quotas';

export function useQuotasBudgets() {
  return useApiQuery<EnterpriseBudget[]>(
    [...qk.admin.quotas.root, 'budgets'],
    `${PATH}/budgets`,
    undefined,
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useQuotasDepartments() {
  return useApiQuery<DepartmentQuota[]>(
    [...qk.admin.quotas.root, 'departments'],
    `${PATH}/departments`,
    undefined,
    { staleTime: 60_000, placeholderData: (prev) => prev },
  );
}

export function useQuotasUsage() {
  return useApiQuery<UsageMetric[]>(
    [...qk.admin.quotas.root, 'usage'],
    `${PATH}/usage`,
    undefined,
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useQuotasAlerts() {
  return useApiQuery<AlertRule[]>(
    [...qk.admin.quotas.root, 'alerts'],
    `${PATH}/alerts`,
    undefined,
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useCreateBudget() {
  return useApiMutation<EnterpriseBudget, CreateBudgetVars>(
    () => `${PATH}/budgets`,
    { invalidateKeys: [qk.admin.quotas.root] },
    'POST',
  );
}

export function useUpdateBudget() {
  return useApiMutation<EnterpriseBudget, UpdateBudgetVars>(
    (vars) => `${PATH}/budgets/${vars.id}`,
    { invalidateKeys: [qk.admin.quotas.root] },
    'PATCH',
  );
}

export function useCreateAlert() {
  return useApiMutation<AlertRule, CreateAlertVars>(
    () => `${PATH}/alerts`,
    { invalidateKeys: [qk.admin.quotas.root] },
    'POST',
  );
}

export function useToggleAlert() {
  return useApiMutation<AlertRule, ToggleAlertVars>(
    (vars) => `${PATH}/alerts/${vars.id}/toggle`,
    { invalidateKeys: [qk.admin.quotas.root] },
    'POST',
  );
}