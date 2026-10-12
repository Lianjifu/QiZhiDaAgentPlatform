/**
 * 管理侧「模型配置」hooks — 列表 / CRUD / 路由 / 健康监控。
 */
import { useMutation } from '@tanstack/react-query';
import { getApiClient } from '@qzdap/web-api';
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type {
  Model, ModelDetail, Provider, RouteRule, HealthEvent, ModelFilters,
  ConnectivityTestVars, ConnectivityTestResult,
  CreateModelVars, ProbeModelsVars, ProbeModelsResult, CreateRouteVars, UpdateModelVars,
  ToggleRouteVars, DeleteModelVars, ToggleStarVars, BatchStatusVars,
} from './schema';

const ROOT = qk.admin.models.root;

export function useModelsList(filters: ModelFilters = {}) {
  return useApiQuery<Model[]>(
    [...qk.admin.models.list],
    '/api/admin/models',
    { query: filters as Record<string, unknown> },
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useModelDetail(id: string) {
  return useApiQuery<ModelDetail>(
    [...qk.admin.models.detail(id)],
    `/api/admin/models/${id}`,
    {},
    { enabled: id.length > 0 },
  );
}

export function useProviders() {
  return useApiQuery<Provider[]>(
    [...qk.admin.models.providers],
    '/api/admin/models/providers',
    {},
    { staleTime: 60_000 },
  );
}

export function useRouteRules() {
  return useApiQuery<RouteRule[]>(
    [...qk.admin.models.routes],
    '/api/admin/models/routes',
    {},
    { staleTime: 30_000 },
  );
}

export function useHealthEvents() {
  return useApiQuery<HealthEvent[]>(
    [...qk.admin.models.health],
    '/api/admin/models/health',
    {},
    { staleTime: 15_000 },
  );
}

export function useCreateModel() {
  return useApiMutation<Model, CreateModelVars>(
    '/api/admin/models',
    { invalidateKeys: [ROOT] },
  );
}

export function useProbeProviderModels() {
  return useApiMutation<ProbeModelsResult, ProbeModelsVars>(
    '/api/admin/models/catalog',
    { invalidateKeys: [['admin', 'models', 'catalog']] },
  );
}

export function useModelConnectivityTest() {
  return useMutation<ConnectivityTestResult, Error, ConnectivityTestVars>({
    mutationFn: (vars) => getApiClient().post<ConnectivityTestResult>(
      '/api/admin/models/connectivity-test', vars, { timeoutMs: 40_000 },
    ),
    retry: false,
  });
}

export function useUpdateModel() {
  return useApiMutation<Model, UpdateModelVars>(
    (v) => `/api/admin/models/${v.id}`,
    { invalidateKeys: [ROOT] },
    'PATCH',
  );
}

export function useDeleteModel() {
  return useApiMutation<{ id: string }, DeleteModelVars>(
    (v) => `/api/admin/models/${v.id}`,
    { invalidateKeys: [ROOT] },
    'DELETE',
  );
}

export function useToggleStar() {
  return useApiMutation<Model, ToggleStarVars>(
    (v) => `/api/admin/models/${v.id}/star`,
    { invalidateKeys: [ROOT] },
  );
}

export function useCreateRoute() {
  return useApiMutation<RouteRule, CreateRouteVars>(
    '/api/admin/models/routes',
    { invalidateKeys: [ROOT] },
  );
}

export function useToggleRoute() {
  return useApiMutation<RouteRule, ToggleRouteVars>(
    (v) => `/api/admin/models/routes/${v.id}/toggle`,
    { invalidateKeys: [ROOT] },
  );
}

export function useDeleteRoute() {
  return useApiMutation<{ id: string }, { id: string }>(
    (v) => `/api/admin/models/routes/${v.id}`,
    { invalidateKeys: [ROOT] },
    'DELETE',
  );
}

export function useBatchSetStatus() {
  return useApiMutation<{ ids: string[] }, BatchStatusVars>(
    '/api/admin/models/batch-status',
    { invalidateKeys: [ROOT] },
  );
}
